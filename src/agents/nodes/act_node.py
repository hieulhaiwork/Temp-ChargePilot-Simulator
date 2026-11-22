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
from pydantic import ValidationError

from src.agents.state import AgentState
from src.agents.tools import RISKY_TOOL_NAMES, TOOL_REGISTRY
from src.agents.tools.charging import PROPOSAL_TOOL_NAME
from src.models.charging import ScheduleProposal

logger = logging.getLogger("ai20k.act")

TOOL_ERROR_PREFIX = "TOOL_ERROR"


def _parse_proposal(output: str) -> dict | None:
    """Kết quả propose_charging_plan → ScheduleProposal đã validate (payload cho màn S3)."""
    try:
        return ScheduleProposal.model_validate(json.loads(output)).model_dump(mode="json")
    except (ValueError, ValidationError):
        logger.error("FAILED act — %s trả kết quả không đúng schema ScheduleProposal", PROPOSAL_TOOL_NAME)
        return None


async def act_node(state: AgentState, config: RunnableConfig) -> dict:
    decision = state.get("last_decision", {})
    tool_name = decision.get("tool_name", "")
    tool_args: dict = decision.get("tool_args", {}) or {}
    trace = list(state.get("tool_trace", []))

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
