"""Node `act` — thực thi tool an toàn; tool rủi ro thì HOÃN sang human_review.

Vì sao tồn tại: cần một chỗ duy nhất trung gian giữa "LLM muốn gọi tool"
và "tool thực sự chạy" để (a) kiểm tra tool có rủi ro không (HITL route),
(b) ghi tool_trace làm minh chứng eval, (c) lỗi tool được ghi TƯỜNG MINH
vào trace cho vòng reason sau xử lý — không nuốt lỗi âm thầm.

ChargePilot (ADR-006): node nhận `config` của lượt chạy và chuyển NGUYÊN cho tool. Danh tính
cư dân nằm trong config["configurable"]["resident_id"] do router đặt từ token — tool_args (do LLM
điền) không bao giờ chứa nó. Tool luôn được gọi bằng `ainvoke`: tool async (ghi dữ liệu) không
hỗ trợ `invoke`, còn tool sync thì LangChain tự chạy trong executor nên không chặn event loop.
"""

from __future__ import annotations

import json
import logging

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import ValidationError

from src.llm_chat.state import AgentState
from src.llm_chat.tools import RISKY_TOOL_NAMES, TEMPLATE_DEMO_TOOL_NAMES, TOOL_REGISTRY
from src.llm_chat.tools.charging import PROPOSAL_TOOL_NAME
from src.llm_chat.tools.copilot import (
    COPILOT_TOOLS,
    MAX_COPILOT_TOOL_CALLS,
    MAX_SIMULATIONS_PER_TURN,
    SIMULATION_TOOLS,
    ChatContext,
    invoke_copilot_tool,
)
from src.models.charging import ScheduleProposal
from src.models.control import Role
from src.models.copilot_integration import CopilotNotice, JobReply, WhyReply
from src.services.errors import DomainError

logger = logging.getLogger("ai20k.act")

TOOL_ERROR_PREFIX = "TOOL_ERROR"


def _parse_proposal(output: str) -> dict | None:
    """Kết quả propose_charging_plan → ScheduleProposal đã validate (payload cho màn S3)."""
    try:
        return ScheduleProposal.model_validate(json.loads(output)).model_dump(mode="json")
    except (ValueError, ValidationError):
        logger.error("FAILED act — %s trả kết quả không đúng schema ScheduleProposal", PROPOSAL_TOOL_NAME)
        return None


async def _advisory(
    state: AgentState,
    context: ChatContext | None,
    name: str,
    args: dict,
    *,
    mixed: bool,
) -> dict:
    attempts = state.get("copilot_attempts", 0)
    simulations = state.get("simulation_attempts", 0)
    sim = name in SIMULATION_TOOLS
    stop = attempts >= MAX_COPILOT_TOOL_CALLS or (sim and simulations >= MAX_SIMULATIONS_PER_TURN)
    if mixed:
        result = CopilotNotice(
            code="unsupported", message="Hãy gửi yêu cầu phân tích và đặt hoặc sửa lịch ở hai lượt riêng."
        )
    elif stop:
        result = CopilotNotice(code="unsupported", message="Đã đến giới hạn phân tích của lượt này.")
    elif context is None:
        result = CopilotNotice(code="structured_fallback", message="Cần phiên đăng nhập để chạy phân tích.")
    else:
        try:
            result = await invoke_copilot_tool(name, args, context, message=state.get("query", ""))
        except ValidationError:
            result = CopilotNotice(code="clarify", message="Thông số phân tích còn thiếu hoặc không hợp lệ.")
        except DomainError as exc:
            result = CopilotNotice(code="structured_fallback", message=exc.detail)
    if isinstance(result, JobReply):
        # Subsequent reasoning needs a handle, not the full authorized projection.
        observation = f"job={result.job.job_id}, kind={result.job.job_kind}, status={result.job.status}"
        if result.job.result:
            observation += f". {result.job.result.summary}"
    elif isinstance(result, WhyReply):
        observation = result.summary + " " + " ".join(reason.summary for reason in result.result.reasons)
    else:
        observation = result.message
    trace = [*state.get("tool_trace", []), {"tool": name, "args": {}, "output": observation}]
    return {
        "copilot_attempts": attempts + 1,
        "simulation_attempts": simulations + int(sim),
        "copilot_results": [*state.get("copilot_results", []), result.model_dump(mode="json")],
        "tool_trace": trace,
        "stage": "act",
        "last_decision": {
            **state.get("last_decision", {}),
            "enough_data": isinstance(result, CopilotNotice) or bool(state.get("last_decision", {}).get("enough_data")),
        },
    }


async def act_node(state: AgentState, config: RunnableConfig, runtime: Runtime[ChatContext]) -> dict:
    decision = state.get("last_decision", {})
    tool_name = decision.get("tool_name", "")
    tool_args: dict = decision.get("tool_args", {}) or {}
    trace = list(state.get("tool_trace", []))

    context = runtime.context
    if tool_name == "explain_schedule" and context is not None and context.copilot is not None:
        # Legacy offline decision name maps to the same trace engine in authenticated chat.
        tool_name = "copilot_why"
        tool_args = tool_args or {
            "kind": "why",
            "topic": "queue",
            "subject": "station" if context.user.role == Role.OPERATOR else "own_booking",
        }
    if tool_name in COPILOT_TOOLS:
        mixed = any(item["tool"] in TOOL_REGISTRY for item in trace)
        return await _advisory(state, context, tool_name, tool_args, mixed=mixed)
    blocked_legacy = context is not None and (
        context.user.role == Role.OPERATOR or (context.copilot is not None and tool_name in TEMPLATE_DEMO_TOOL_NAMES)
    )
    if state.get("copilot_attempts") or blocked_legacy:
        return await _advisory(state, context, tool_name, {}, mixed=True)

    if tool_name in RISKY_TOOL_NAMES:
        # KHÔNG chạy — đẩy sang human_review chờ interrupt()/phê duyệt.
        logger.warning("act — tool rủi ro %s hoãn sang human_review", tool_name)
        return {"pending_action": {"tool": tool_name, "args": tool_args}, "stage": "human_review"}

    if tool_name not in TOOL_REGISTRY:
        # reason_node đã chặn, đây là defense-in-depth (belts and braces).
        logger.error("FAILED act — tool ngoài registry: %r", tool_name)
        raise ValueError(f"Tool ngoài registry: {tool_name!r}")

    tool = TOOL_REGISTRY[tool_name]
    try:
        output = await tool.ainvoke(tool_args, config)
    except Exception as exc:  # lỗi tool là DỮ KIỆN cho vòng reason sau
        logger.error("FAILED act — tool %s lỗi: %s", tool_name, exc)
        output = f"{TOOL_ERROR_PREFIX}: {exc}"
    trace.append({"tool": tool_name, "args": tool_args, "output": str(output)})
    logger.info("act — %s(%s) -> %s", tool_name, tool_args, str(output)[:80])

    update: dict = {"tool_trace": trace, "pending_action": None, "stage": "act"}
    if tool_name == PROPOSAL_TOOL_NAME and not str(output).startswith(TOOL_ERROR_PREFIX):
        update["proposal"] = _parse_proposal(str(output))
    return update
