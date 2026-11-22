"""Node `reason` — LLM quyết định vòng này gọi tool hay đã trả lời được.

Vì sao tồn tại: template cũ có analyze_node chỉ format chuỗi — tools
KHÔNG BAO GIỜ được gọi (đúng lỗi e1-current-docs). Node này là bước
reasoning thực của vòng ReAct: đầu ra là AgentDecision đã qua guardrail
schema-first; tên tool bịa sẽ bị chặn tại đây, không phải ở runtime xa.

ChargePilot: prompt nằm ở prompts/reason.md (+ charging_domain.md, charging_safeguards.md) —
KHÔNG nhúng prompt trong Python. Prompt nhận mô tả + tham số của từng tool (trước đây chỉ có
tên), hội thoại gần đây và draft_request để hỏi lại đúng chỗ thiếu qua nhiều lượt (FR2).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

from src.agents.guardrails import guardrails
from src.agents.mock_llm import mock_reason
from src.agents.prompts import load_prompt, render
from src.agents.state import AgentState
from src.agents.tools import RISKY_TOOL_NAMES, TEMPLATE_DEMO_TOOL_NAMES, TOOL_REGISTRY
from src.config import get_settings
from src.models.schemas import AgentDecision
from src.services.llm import get_structured_llm

logger = logging.getLogger("ai20k.reason")

ReasonFn = Callable[[AgentState], Awaitable[AgentDecision]]


def describe_tools() -> str:
    """Tên + mô tả + tham số của từng tool trong registry — để LLM chọn đúng tool và điền đúng args.

    Tham số lấy từ schema của tool; tham số do hệ thống tiêm (RunnableConfig — nơi chứa resident_id)
    không nằm trong schema nên không bao giờ xuất hiện ở đây. Tool demo của template bị ẩn khỏi LLM
    (vẫn trong registry cho test harness) để LLM không đề nghị gửi email / tra kiến thức với cư dân.
    """
    lines = []
    for name, tool in TOOL_REGISTRY.items():
        if name in TEMPLATE_DEMO_TOOL_NAMES:
            continue
        summary = " ".join((tool.description or "").split())
        risky = " [CẦN CƯ DÂN XÁC NHẬN]" if name in RISKY_TOOL_NAMES else ""
        lines.append(f"- {name}{risky}: {summary}\n  tham số: {json.dumps(tool.args, ensure_ascii=False)}")
    return "\n".join(lines)


def _format_history_line(m: dict) -> str:
    ts = m.get("ts")
    if isinstance(ts, str) and len(ts) >= 16 and "T" in ts:
        return f"[{ts[11:16]}] {m['role']}: {m['content']}"
    return f"{m['role']}: {m['content']}"


def build_reason_prompt(state: AgentState) -> str:
    """Dựng prompt cho bước reason từ state — tách riêng để test được mà không gọi LLM."""
    context = state.get("turn_context", {})
    history = "\n".join(_format_history_line(m) for m in state.get("history", []))
    trace = "\n".join(f"- {t['tool']}({t['args']}) -> {t['output']}" for t in state.get("tool_trace", []))
    return render(
        "reason.md",
        now=context.get("now", "(không rõ)"),
        timezone=context.get("timezone", "(không rõ)"),
        selected_vehicle=context.get("vehicle_model") or "(cư dân chưa chọn mẫu xe)",
        history=history or "(chưa có)",
        query=state.get("query", ""),
        draft_request=json.dumps(state.get("draft_request", {}), ensure_ascii=False),
        tool_trace=trace or "(chưa có)",
        iteration=state.get("iteration_count", 0),
        max_iterations=state.get("max_iterations", 8),
        tools=describe_tools(),
        domain_rules=load_prompt("charging_domain.md"),
        safeguards=load_prompt("charging_safeguards.md"),
    )


async def llm_reason(state: AgentState) -> AgentDecision:
    """Default reason_fn — dùng model rẻ (classify tier) hoặc mock_reason khi LLM_PROVIDER=mock."""
    if get_settings().llm_provider == "mock":
        return await mock_reason(state)
    llm = get_structured_llm("classify", AgentDecision)
    return await llm.ainvoke(build_reason_prompt(state))


def make_reason_node(reason_fn: ReasonFn | None = None):
    """Factory — cho test inject reason_fn giả định (không gọi API thật)."""
    fn = reason_fn or llm_reason

    async def reason_node(state: AgentState) -> dict:
        raw_decision = await fn(state)
        # Lớp guardrail 2: output của reason BẮT BUỘC qua schema — sai là
        # raise tại đây (fail loudly), không sửa khéo cho qua.
        decision = guardrails.validate_output(raw_decision, AgentDecision, source="reason")
        if decision.action == "tool" and decision.tool_name not in TOOL_REGISTRY:
            logger.error("FAILED reason — tool bịa %r ngoài registry", decision.tool_name)
            raise ValueError(
                f"AgentDecision chọn tool không tồn tại: {decision.tool_name!r}. Tool hợp lệ: {sorted(TOOL_REGISTRY)}"
            )
        logger.info(
            "reason iter=%d action=%s tool=%s", state.get("iteration_count", 0), decision.action, decision.tool_name
        )
        update: dict = {"last_decision": decision.model_dump(), "stage": "reason"}
        if decision.draft_request:
            # Gộp vào bản nháp của phiên — trường đã thu ở lượt trước không bị mất (FR2).
            update["draft_request"] = {**state.get("draft_request", {}), **decision.draft_request}
        return update

    return reason_node
