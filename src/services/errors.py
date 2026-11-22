"""Lỗi nghiệp vụ dùng chung cho tầng services (ADR-008).

Vì sao tồn tại: service được gọi từ CẢ router lẫn tool của Agent, nên không được ném
HTTPException của FastAPI. Service ném DomainError; mỗi phía tự dịch:
  - router  → src/main.py:domain_error_handler → HTTP + envelope ErrorResponse
  - Agent   → act_node bắt exception → "TOOL_ERROR: …" cho vòng reason kế tiếp

Stub chưa làm KHÔNG dùng lớp này: vẫn `raise NotImplementedError("[Txx] …")` (ADR-004).
"""

from src.models.api import ErrorCode

# Mã HTTP mặc định cho từng mã lỗi — một chỗ duy nhất để frontend và backend khớp nhau.
HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.BOOKING_CONFLICT: 409,
    ErrorCode.IDEMPOTENCY_MISMATCH: 409,
    ErrorCode.APPROVAL_ALREADY_DECIDED: 409,
    ErrorCode.PROPOSAL_EXPIRED: 409,
    ErrorCode.NO_PENDING_CONFIRMATION: 409,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.LLM_UNAVAILABLE: 503,
    ErrorCode.DATABASE_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}


class DomainError(Exception):
    """Lỗi nghiệp vụ có mã ổn định. `detail` là câu cho người dùng — không chứa thông tin nội bộ."""

    def __init__(self, code: ErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail

    @property
    def http_status(self) -> int:
        return HTTP_STATUS[self.code]
