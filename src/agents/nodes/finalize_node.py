"""Node `finalize` / `finalize_with_partial` — sinh câu trả lời cuối qua schema.

Vì sao tồn tại: output cuối là thứ user nhìn thấy — PHẢI qua lớp guardrail
(viền FinalAnswer + check_output_text chống leak system prompt / API key).
Node partial là escape hatch: trả lời với dữ kiện có được + cảnh báo rõ
ràng là thiếu, thay vì treo hay bịa.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from src.agents.guardrails import GuardrailViolation, guardrails
from src.agents.mock_llm import mock_generate
from src.agents.prompts import SHARED_RULES, render
from src.agents.state import HISTORY_LIMIT, AgentState
from src.config import get_settings
from src.models.schemas import FinalAnswer
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
            return {"response": refusal.answer, "stage": "refusal", "history": _with_reply(state, refusal.answer)}

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
                    f"chi phí ước tính {proposal.get('estimated_cost_vnd')} VND."
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
            "suggestions": list(final.suggestions)[:4],
            "stage": "partial" if partial else "finalize",
            "history": _with_reply(state, answer),
        }

    return finalize_node
