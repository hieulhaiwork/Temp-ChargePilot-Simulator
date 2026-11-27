"""Node `finalize` / `finalize_with_partial` — sinh câu trả lời cuối qua schema.

Vì sao tồn tại: output cuối là thứ user nhìn thấy — PHẢI qua lớp guardrail
(viền FinalAnswer + check_output_text chống leak system prompt / API key).
Node partial là escape hatch: trả lời với dữ kiện có được + cảnh báo rõ
ràng là thiếu, thay vì treo hay bịa.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from time import monotonic

from src.config import get_settings
from src.llm_chat.guardrails import GuardrailViolation, guardrails
from src.llm_chat.mock_llm import mock_generate
from src.llm_chat.prompts import SHARED_RULES, render
from src.llm_chat.schemas import FinalAnswer
from src.llm_chat.state import (
    HISTORY_LIMIT,
    MAX_CLARIFICATION_TURN_CHARS,
    MAX_PENDING_CLARIFICATION_TURNS,
    AgentState,
    PendingCopilotClarification,
)
from src.models.control import Role
from src.models.copilot_integration import CopilotNotice
from src.services.copilot.integration import CopilotIntegration
from src.services.llm import get_structured_llm

logger = logging.getLogger("ai20k.finalize")

GenerateFn = Callable[..., Awaitable[FinalAnswer]]

PARTIAL_NOTE = "\nLƯU Ý: hết vòng lặp tối đa mà chưa đủ dữ kiện — trả lời phần có được và ghi rõ phần thiếu."


def build_generate_prompt(state: AgentState, partial: bool = False) -> str:
    """Dựng prompt câu trả lời cuối từ prompts/finalize.md — tách riêng để test được mà không gọi LLM.

    `draft_answer` là final_answer của bước reason (vd câu hỏi lại trường còn thiếu — FR2). Không truyền
    nó thì finalize chỉ thấy câu của cư dân và đánh mất câu hỏi lại mà reason đã quyết định.
    """
    trace = "\n".join(f"- {t['tool']}({t['args']}) -> {t['output']}" for t in state.get("tool_trace", []))
    decisions = "\n".join(f"- {d['tool']}: {d['decision']}" for d in state.get("human_decisions", []))
    return render(
        "finalize.md",
        query=state.get("query", ""),
        tool_trace=trace or "(không có tool nào được gọi)",
        human_decisions=decisions or "(không có)",
        partial_note=PARTIAL_NOTE if partial else "",
        shared_rules=SHARED_RULES,
        draft_answer=state.get("last_decision", {}).get("final_answer") or "(không có)",
    )


async def llm_generate(state: AgentState, partial: bool = False) -> FinalAnswer:
    """Default generate_fn — model mạnh (generate tier) hoặc mock_generate khi LLM_PROVIDER=mock.

    Tối ưu RPM / độ trễ (AC1 ≤ 2s): khi lượt chat không gọi tool nào (vd hỏi lại trường thiếu,
    từ chối ngoài phạm vi) và bước reason đã viết sẵn `final_answer`, dùng trực tiếp câu đó
    thay vì tốn thêm 1 request LLM ở tầng generate.
    """
    if get_settings().llm_provider == "mock":
        return await mock_generate(state, partial=partial)
    if not partial and not state.get("tool_trace"):
        decision = state.get("last_decision") or {}
        draft_answer = decision.get("final_answer")
        if isinstance(draft_answer, str) and draft_answer.strip():
            return FinalAnswer(
                answer=draft_answer.strip(),
                confidence=0.95,
                used_tools=[],
                suggestions=list(decision.get("suggestions") or []),
            )
    llm = get_structured_llm("generate", FinalAnswer)
    return await llm.ainvoke(build_generate_prompt(state, partial))


def _with_reply(state: AgentState, answer: str) -> list[dict]:
    """history sau khi thêm câu trả lời của trợ lý — để lượt chat sau có ngữ cảnh (FR2)."""
    now_ts = (state.get("turn_context") or {}).get("now")
    msg: dict = {"role": "assistant", "content": answer}
    if now_ts:
        msg["ts"] = now_ts
    history = [*state.get("history", []), msg]
    return history[-HISTORY_LIMIT:]


def _sanitize_suggestions(suggestions: list[str], state: AgentState) -> list[str]:
    """Option B guardrail: khi chưa biết `soc_now`, tuyệt đối không để gợi ý 1 chạm ép/đoán % pin hiện tại."""
    draft = state.get("draft_request") or {}
    missing_soc_now = draft.get("soc_now") is None
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in suggestions:
        item = str(raw).strip()
        if not item or item in seen:
            continue
        if missing_soc_now and "%" in item:
            low_item = item.lower()
            is_target_only = any(k in low_item for k in ("mục tiêu", "sạc đầy", "lên "))
            if not is_target_only:
                continue
        seen.add(item)
        cleaned.append(item)
        if len(cleaned) >= 3:
            break
    return cleaned


def _finalize_advisory(state: AgentState, partial: bool) -> dict | None:
    decision = state.get("last_decision") or {}
    action = decision.get("action")
    results = list(state.get("copilot_results", []))
    if not (
        results or action in ("clarify", "unsupported") or state.get("turn_context", {}).get("role") == Role.OPERATOR
    ):
        return None
    if action == "clarify":
        results.append(CopilotIntegration.clarification(decision["clarify_field"]).model_dump(mode="json"))
    if action == "unsupported":
        results.append(
            CopilotNotice(
                code="unsupported",
                message="Các điều kiện kết hợp này chưa được hỗ trợ. Hãy chọn một thay đổi để mô phỏng.",
            ).model_dump(mode="json")
        )

    next_pending: PendingCopilotClarification | None = None
    clarify_items = [item for item in results if item["kind"] == "notice" and item["code"] == "clarify"]
    terminal_items = [
        item for item in results if item["kind"] == "job" or (item["kind"] == "notice" and item["code"] != "clarify")
    ]
    if not partial and clarify_items and not terminal_items:
        prior_pending = state.get("pending_copilot_clarification") or {}
        existing_turns = [t for t in (prior_pending.get("turns") or ()) if isinstance(t, str) and t.strip()]
        raw_query, _ = CopilotIntegration.strip_explicit_reset(state.get("query", ""))
        cleaned_query = raw_query.strip()
        next_turns = [*existing_turns, cleaned_query] if cleaned_query else existing_turns
        if len(cleaned_query) > MAX_CLARIFICATION_TURN_CHARS or len(next_turns) > MAX_PENDING_CLARIFICATION_TURNS:
            overflow_notice = CopilotNotice(
                code="unsupported",
                message="Yêu cầu làm rõ vượt giới hạn độ dài hoặc số lượt. Vui lòng gửi lại một yêu cầu đầy đủ, ngắn gọn.",
            ).model_dump(mode="json")
            results = [
                overflow_notice if (item["kind"] == "notice" and item["code"] == "clarify") else item
                for item in results
            ]
        elif next_turns:
            opened_at = float(prior_pending.get("opened_at") or monotonic())
            next_pending = {
                "turns": next_turns,
                "field": str(clarify_items[-1].get("field") or "intent"),
                "opened_at": opened_at,
            }

    lines = []
    if results:
        for result in results:
            match result["kind"]:
                case "why":
                    lines.append(result["summary"])
                    lines.extend(reason["summary"] for reason in result["result"]["reasons"])
                case "job":
                    job = result["job"]
                    if job["result"]:
                        lines.append(job["result"]["summary"])
                    elif job["status"] in ("queued", "running"):
                        lines.append("Đã nhận tác vụ mô phỏng. Kết quả sẽ hiển thị khi hoàn tất.")
                    else:
                        lines.append("Tác vụ đã dừng hoặc kết quả đã hết hạn.")
                case "notice":
                    lines.append(result["message"])
    else:
        lines.append("Bạn muốn tìm lý do, mô phỏng thay đổi hạ tầng hay thử mức công suất cho các cam kết?")
    if partial:
        lines.append("Lượt này đã hết số vòng phân tích.")
    answer = "\n\n".join(dict.fromkeys(lines))
    guardrails.check_output_text(answer)
    return {
        "response": answer,
        "history": _with_reply(state, answer),
        "copilot_results": results,
        "pending_copilot_clarification": next_pending,
        "turn_in_progress": False,
        "suggestions": [],
        "stage": "partial" if partial else "finalize",
    }


def _make_finalize(generate_fn: GenerateFn | None, partial: bool):
    fn = generate_fn or llm_generate

    async def finalize_node(state: AgentState) -> dict:
        # Nhánh từ chối do guardrail input — không gọi LLM, trả lời canned tường minh.
        if state.get("refusal_reason"):
            refusal = FinalAnswer(
                answer=(f"Tôi không thể xử lý yêu cầu này: {state['refusal_reason']}"),
                confidence=1.0,
                used_tools=[],
            )
            return {
                "response": refusal.answer,
                "stage": "refusal",
                "pending_copilot_clarification": None,
                "turn_in_progress": False,
                "history": _with_reply(state, refusal.answer),
            }

        advisory = _finalize_advisory(state, partial)
        if advisory is not None:
            return advisory

        raw = await fn(state, partial=partial)
        final = guardrails.validate_output(raw, FinalAnswer, source="finalize")
        guardrails.check_output_text(final.answer)  # leak system prompt/key -> raise
        try:
            guardrails.check_grounded_numbers(final.answer, state.get("tool_trace", []))
        except GuardrailViolation:
            proposal = state.get("proposal")
            if not isinstance(proposal, dict) or not proposal.get("energy"):
                raise
            energy = proposal["energy"]
            conn = proposal.get("connector_id") or "hàng chờ"
            final = FinalAnswer(
                answer=(
                    f"Phương án đề xuất: sạc tại đầu nối {conn}, "
                    f"nạp {energy.get('battery_energy_kwh')} kWh vào pin "
                    f"({energy.get('grid_energy_kwh')} kWh từ lưới), "
                    f"chi phí ước tính {proposal.get('estimated_cost_vnd')} VND (ước tính, không phải cam kết)."
                    + (
                        " Kết quả còn phụ thuộc phê duyệt đang chờ."
                        if proposal.get("certainty") == "conditional"
                        else ""
                    )
                ),
                confidence=final.confidence,
                used_tools=final.used_tools,
            )

        if partial:
            warning = (
                "\n\n[Trả lời một phần] Agent đã hết số vòng tối đa "
                f"({state.get('max_iterations', 8)}) mà chưa đủ dữ kiện — "
                "câu trả lời dựa trên dữ kiện thu thập được đến thời điểm này."
            )
            answer = final.answer + warning
        else:
            answer = final.answer

        logger.info("finalize (partial=%s) confidence=%.2f", partial, final.confidence)
        return {
            "response": answer,
            "suggestions": _sanitize_suggestions(list(final.suggestions), state),
            "pending_copilot_clarification": None,
            "turn_in_progress": False,
            "stage": "partial" if partial else "finalize",
            "history": _with_reply(state, answer),
        }

    return finalize_node
