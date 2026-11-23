"""Schema nội bộ của chat cư dân — output có cấu trúc mà LLM PHẢI trả (anti-hallucination, team 012).

Không nằm trong OpenAPI. DTO của API chat (`ChatRequest` / `ChatResponse`) ở `src/models/schemas.py`.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AgentDecision(BaseModel):
    """Output của node `reason` — LLM PHẢI trả đúng schema này.

    model_validator enforce nhất quán nội tại (action=tool thì phải có
    tool_name) — bắt lỗi schema ở chỗ sinh ra, không đợi chạy sai ở runtime.
    """

    thought: str = Field(..., min_length=1, description="Suy luận ngắn của agent ở vòng này")
    action: Literal["tool", "final"]
    tool_name: str | None = Field(default=None, description="Bắt buộc nếu action='tool'")
    tool_args: dict = Field(default_factory=dict, description="Tham số cho tool")
    enough_data: bool = Field(
        default=False,
        description="Self-assessment: đã đủ dữ kiện để trả lời chưa?",
    )
    draft_request: dict = Field(
        default_factory=dict,
        description="Các trường ChargeRequest đã thu được qua các lượt chat (FR2: hỏi lại chỗ thiếu)",
    )
    final_answer: str | None = Field(default=None, description="Bắt buộc nếu action='final'")
    suggestions: list[str] = Field(
        default_factory=list, description="2–3 gợi ý câu trả lời ngắn gọn (1 chạm) cho cư dân ở lượt tiếp theo"
    )

    @model_validator(mode="after")
    def _check_consistency(self) -> "AgentDecision":
        if self.action == "tool" and not self.tool_name:
            raise ValueError("action='tool' đòi hỏi tool_name không rỗng")
        if self.action == "final":
            if self.tool_name:
                raise ValueError("action='final' không được kèm tool_name")
            if not self.final_answer or not self.final_answer.strip():
                raise ValueError("action='final' đòi hỏi final_answer không rỗng")
        return self


class FinalAnswer(BaseModel):
    """Output của node `finalize` / `finalize_with_partial`."""

    answer: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    used_tools: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class AgentAnswer(BaseModel):
    """Output có cấu trúc của pattern RAG template (còn `nodes/validate_node.py` và test dùng; graph không nối).

    - `verdict` là Literal → LLM không thể bịa giá trị ngoài tập cho phép.
    - `confidence` bị kẹp trong [0, 1] → không có confidence 1.5 hay -0.3.
    - `citation_ids` ràng buộc: nếu verdict khác "uncertain" thì PHẢI có citation
      (check ở nodes/validate_node.py).
    """

    verdict: Literal["supported", "partially_supported", "unsupported", "uncertain"] = Field(
        description="Mức độ chắc chắn của câu trả lời so với ngữ cảnh"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Độ tin cậy, kẹp trong [0, 1]")
    answer: str = Field(min_length=1, max_length=2000, description="Câu trả lời cho user")
    citation_ids: list[str] = Field(default_factory=list, description="ID các chunk đã dùng, dạng ['chunk_1', ...]")

    # Quy tắc conservative: khoanh vùng "uncertain" thay vì bịa "supported" (inspire team 012).
    def is_safe(self) -> bool:
        if self.verdict != "uncertain" and not self.citation_ids:
            return False
        if self.verdict == "supported" and self.confidence < 0.6:
            return False
        return True
