"""Pydantic schemas — schema-first anti-hallucination (good practice #4, team 012).

Vì sao tồn tại: output LLM không validate = không biết lúc nào agent bịa.
Mọi output quan trọng (quyết định reasoning, câu trả lời cuối) PHẢI đi qua
một Pydantic schema; sai schema → exception tường minh, không có
silent fallback.

File này giữ DTO của API chat (`ChatRequest` / `ChatResponse`, nằm trong OpenAPI). Kiểu nội bộ của graph
(`AgentDecision`, `FinalAnswer`, `AgentAnswer`) ở `src/llm_chat/schemas.py`.
"""

from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.models.charging import Booking, ChargeRequest, ScheduleProposal
from src.models.copilot_integration import CopilotNotice, JobReply, WhyReply

ChatAdvisory = Annotated[WhyReply | JobReply | CopilotNotice, Field(discriminator="kind")]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")
    session_id: str = Field(
        default_factory=lambda: uuid4().hex,
        min_length=1,
        max_length=128,
        description="Thread ID cho checkpointer (HITL multi-turn). Bỏ trống → mỗi request một thread mới",
    )


class ChatResponse(BaseModel):
    response: str = Field(..., description="Phản hồi từ agent")
    analysis: str = Field(default="", description="Phân tích nội bộ (tool trace tóm tắt)")
    session_id: str = Field(default="", description="Thread ID để gửi lại khi resume / chat tiếp")
    # ChargePilot (I2) — dữ liệu có cấu trúc cho màn S3; ba field trên giữ nguyên cho client cũ.
    status: Literal["answer", "needs_confirmation", "refused"] = Field(
        default="answer", description="needs_confirmation = graph đang dừng ở interrupt, chờ PATCH /chat/sessions/{id}"
    )
    advisory: list[ChatAdvisory] = Field(default_factory=list)
    proposal: ScheduleProposal | None = Field(default=None, description="Phương án hiện ở S3 — số liệu do CODE tính")
    request: ChargeRequest | None = Field(default=None, description="Yêu cầu đã chỉnh sẵn khi chờ xác nhận (G3)")
    booking: Booking | None = Field(default=None, description="Booking vừa được xác nhận (G4)")
    pending: dict | None = Field(default=None, description="Hành động đang chờ xác nhận: {tool, args}")
    suggestions: list[str] = Field(
        default_factory=list, description="0–3 gợi ý trả lời nhanh (1 chạm) cho lượt tiếp theo của cư dân"
    )
    draft: dict | None = Field(
        default=None,
        description="Các trường yêu cầu sạc đã thu được tới hiện tại (vehicle_model, soc_now, soc_target, zone, mode, deadline)",
    )


class TranscribeRequest(BaseModel):
    """Nhận âm thanh base64 từ trình duyệt (MediaRecorder) để chuyển thành văn bản tiếng Việt."""

    audio_base64: str = Field(
        ..., min_length=8, max_length=7_000_000, description="Dữ liệu âm thanh mã hoá base64 (≤ 5 MB)"
    )
    mime_type: str = Field(default="audio/webm", max_length=64, description="MIME của audio, vd audio/webm, audio/mp4")


class TranscribeResponse(BaseModel):
    """Văn bản tiếng Việt đã chuẩn hoá từ giọng nói đa vùng miền."""

    text: str = Field(..., description="Nội dung tiếng Việt đã nhận dạng")
    provider: str = Field(..., description="Nhà cung cấp ASR đã xử lý (gemini | local_phowhisper | mock)")
    fallback_used: bool = Field(default=False, description="True nếu API chính lỗi và đã chuyển sang fallback")
