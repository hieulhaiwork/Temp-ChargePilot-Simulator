"""Node `human_review` — HITL interrupt cho hành động rủi ro (LangGraph 1.x).

Vì sao tồn tại: gap-analysis guidebook cũ có 0 nội dung về HITL. Pattern
chuẩn langgraph 1.x: node gọi `interrupt(payload)` → graph DỪNG, trả
`__interrupt__` cho client; client resume bằng `Command(resume=...)` —
node chạy lại từ đầu và `interrupt()` trả về giá trị resume. Yêu cầu
graph phải compile với checkpointer (đã có MemorySaver).

ChargePilot: với `confirm_booking`, interrupt này CHÍNH LÀ màn S3 (FR2 "xác nhận với cư dân").
Payload mang theo `proposal` (ScheduleProposal do code tính) để web hiển thị số liệu có cấu trúc,
không phải đọc từ câu chữ của LLM. Đây KHÔNG phải cơ chế phê duyệt lệnh điều khiển (FR13) —
cái đó nằm ở src/guard/approval.py và lưu trong DB.
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.llm_chat.nodes.act_node import TOOL_ERROR_PREFIX
from src.llm_chat.state import AgentState
from src.llm_chat.tools import TOOL_REGISTRY
from src.llm_chat.tools.charging import CONFIRM_TOOL_NAME

logger = logging.getLogger("ai20k.human_review")

BLOCKED_BY_HUMAN = "BLOCKED_BY_HUMAN"  # output của tool khi người dùng từ chối (reject)


async def human_review_node(state: AgentState, config: RunnableConfig) -> dict:
    """Chờ human phê duyệt pending_action; approve thì chạy tool tại đây."""
    pending = state.get("pending_action")
    if not pending:
        # Vào node này mà không có gì chờ duyệt là bug graph — raise, không im lặng.
        raise RuntimeError("human_review được gọi nhưng pending_action trống")

    answer = interrupt(
        {
            "question": "Phê duyệt hành động rủi ro này của agent?",
            "tool": pending["tool"],
            "args": pending["args"],
            "proposal": state.get("proposal"),
        }
    )

    if answer not in ("approve", "reject"):
        raise ValueError(f"Giá trị resume không hợp lệ: {answer!r} (chờ 'approve' | 'reject')")

    decisions = list(state.get("human_decisions", []))
    trace = list(state.get("tool_trace", []))
    update: dict = {"pending_action": None, "stage": "assess"}

    if answer == "approve":
        try:
            output = await TOOL_REGISTRY[pending["tool"]].ainvoke(pending["args"], config)
        except Exception as exc:  # giống act_node: lỗi tool là DỮ KIỆN, không làm sập graph
            logger.error("FAILED human_review — tool %s lỗi: %s", pending["tool"], exc)
            output = f"{TOOL_ERROR_PREFIX}: {exc}"
        trace.append({"tool": pending["tool"], "args": pending["args"], "output": str(output)})
        decisions.append({"tool": pending["tool"], "decision": "approve"})
        logger.info("human_review APPROVE — %s đã chạy", pending["tool"])
        if pending["tool"] == CONFIRM_TOOL_NAME and not str(output).startswith(TOOL_ERROR_PREFIX):
            # Đã chốt lịch → xoá bản nháp của phiên, lượt chat sau bắt đầu yêu cầu mới.
            update["draft_request"] = {}
            update["proposal"] = None
    else:
        output = BLOCKED_BY_HUMAN
        trace.append({"tool": pending["tool"], "args": pending["args"], "output": output})
        decisions.append({"tool": pending["tool"], "decision": "reject"})
        logger.warning("human_review REJECT — %s bị chặn", pending["tool"])

    update["human_decisions"] = decisions
    update["tool_trace"] = trace
    return update
