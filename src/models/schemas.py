"""Pydantic schemas — schema-first anti-hallucination (good practice #4, team 012).

Vì sao tồn tại: output LLM không validate = không biết lúc nào agent bịa.
Mọi output quan trọng (quyết định reasoning, câu trả lời cuối) PHẢI đi qua
một Pydantic schema; sai schema → exception tường minh, không có
silent fallback.

File này giữ DTO của API chat (`ChatRequest` / `ChatResponse`, nằm trong OpenAPI). Kiểu nội bộ của graph
(`AgentDecision`, `FinalAnswer`, `AgentAnswer`) ở `src/llm_chat/schemas.py`.
"""

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.models.charging import ScheduleProposal


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")
    session_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Thread ID cho checkpointer (HITL multi-turn). Bỏ trống → mỗi request một thread mới",
    )


class ChatResponse(BaseModel):
    response: str = Field(..., description="Phản hồi từ agent")
    analysis: str = Field(default="", description="Phân tích nội bộ (tool trace tóm tắt)")
    session_id: str = Field(default="", description="Thread ID để gửi lại khi resume / chat tiếp")
    # ChargePilot (I2) — dữ liệu có cấu trúc cho màn S3; ba field trên giữ nguyên cho client cũ.
    status: Literal["answer", "needs_confirmation", "refused"] = Field(
        default="answer", description="needs_confirmation = graph đang dừng ở interrupt, chờ /chat/resume"
    )
    proposal: ScheduleProposal | None = Field(default=None, description="Phương án hiện ở S3 — số liệu do CODE tính")
    pending: dict | None = Field(default=None, description="Hành động đang chờ xác nhận: {tool, args}")
    suggestions: list[str] = Field(
        default_factory=list, description="2–3 gợi ý trả lời nhanh (1 chạm) cho lượt tiếp theo của cư dân"
    )
