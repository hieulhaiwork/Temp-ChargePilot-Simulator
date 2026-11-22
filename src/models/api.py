"""DTO request/response của REST API — hợp đồng với frontend (TV4).

Frontend nên sinh type TypeScript từ /openapi.json (vd `openapi-typescript`) thay vì
gõ tay: đổi model ở đây là type phía web đổi theo, hai bên không lệch nhau.
Model nghiệp vụ dùng lại từ charging/control/station/simulation; file này chỉ chứa
phần riêng của API.
"""

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from src.models.charging import Booking, ConsentScope, SessionPlan, StrategyName
from src.models.control import DecisionLogEntry, Role
from src.models.station import ConnectorState, SessionProgress, StationState


class ErrorCode(StrEnum):
    """Mã lỗi ổn định cho frontend switch (ADR-008) — không dò chuỗi `detail`."""

    UNAUTHENTICATED = "unauthenticated"  # 401
    FORBIDDEN = "forbidden"  # 403
    NOT_FOUND = "not_found"  # 404
    BOOKING_CONFLICT = "booking_conflict"  # 409 — cư dân đã có booking đang hiệu lực
    IDEMPOTENCY_MISMATCH = "idempotency_mismatch"  # 409 — cùng Idempotency-Key, khác body
    APPROVAL_ALREADY_DECIDED = "approval_already_decided"  # 409
    PROPOSAL_EXPIRED = "proposal_expired"  # 409 — trạng thái trạm đổi giữa lúc xem và lúc chốt
    NO_PENDING_CONFIRMATION = "no_pending_confirmation"  # 409 — /chat/resume khi phiên không còn chờ
    NOT_IMPLEMENTED = "not_implemented"  # 501 — stub [Txx]
    LLM_UNAVAILABLE = "llm_unavailable"  # 503 — frontend chuyển sang form (NFR khả dụng)
    DATABASE_UNAVAILABLE = "database_unavailable"  # 503
    INTERNAL_ERROR = "internal_error"  # 500
    HTTP_ERROR = "http_error"  # mã HTTP khác do framework sinh (405, 413…) — không có nghĩa nghiệp vụ riêng


class ErrorResponse(BaseModel):
    """Envelope lỗi chung (ADR-008). 422 giữ nguyên dạng mặc định của FastAPI."""

    detail: str
    code: ErrorCode
    task_id: str | None = Field(default=None, description="Mã task khi code=not_implemented, vd 'T2.2'")
    request_id: str | None = Field(default=None, description="Trùng header X-Request-ID — để tra log")
    status: Literal["not_implemented"] | None = Field(default=None, description="Giữ tương thích ADR-004")


class ReadinessReport(BaseModel):
    """GET /ready — readiness (khác /health là liveness, không đụng DB)."""

    status: Literal["ok", "degraded"]
    checks: dict[str, str] = Field(description="tên phần → 'ok' | 'not_implemented [Txx]' | 'error'")


class LoginRequest(BaseModel):
    """S1 — đăng nhập (FR1)."""

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    role: Role
    user_id: str
    display_name: str


class UserProfile(BaseModel):
    """User đã xác thực — `get_current_user` trả về model này."""

    user_id: str
    role: Role
    display_name: str
    vehicle_model: str | None = Field(default=None, description="Xe mặc định của cư dân (F8)")


class EnergyEstimateRequest(BaseModel):
    """FR3 — tính kWh cho form/web, cùng công thức với tool của Agent."""

    vehicle_model: str = Field(min_length=1)
    soc_now: float = Field(ge=0, le=100)
    soc_target: float = Field(gt=0, le=100)

    @model_validator(mode="after")
    def _target_above_now(self) -> "EnergyEstimateRequest":
        if self.soc_target <= self.soc_now:
            raise ValueError("soc_target phải lớn hơn soc_now")
        return self


class QueueStatus(BaseModel):
    """US2 / AC2 — vị trí hàng đợi và thời gian chờ dự kiến."""

    booking_id: str | None = None
    position: int | None = Field(default=None, ge=1, description="None = không ở trong hàng đợi")
    queue_length: int = Field(ge=0)
    estimated_wait_minutes: float | None = Field(default=None, ge=0)
    estimated_start: AwareDatetime | None = None


class NotificationKind(StrEnum):
    APPROVAL_REQUEST = "approval_request"  # S4
    SCHEDULE_CHANGED = "schedule_changed"
    EMERGENCY_CURTAILMENT = "emergency_curtailment"  # AC5 — báo SAU khi đã giảm
    INFO = "info"


class Notification(BaseModel):
    notification_id: str
    kind: NotificationKind
    title: str
    body: str
    created_at: AwareDatetime
    read: bool = False
    approval_id: str | None = None


class ApprovalDecisionRequest(BaseModel):
    """S4 (cư dân) / S7 (vận hành) — Đồng ý / Từ chối."""

    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)


class ManualAssignRequest(BaseModel):
    """S6 — "Xếp thủ công": lệnh vẫn phải qua Guard."""

    connector_id: str = Field(min_length=1)


class StationOverview(BaseModel):
    """S5 — thanh KPI + lưới cột sạc."""

    state: StationState
    power_limit_kw: float = Field(ge=0)
    utilization_pct: float = Field(ge=0, description="Tải tổng / giới hạn × 100")
    charging_count: int = Field(ge=0)
    queue_length: int = Field(ge=0)
    energy_cost_today_vnd: float | None = Field(default=None, ge=0)
    cost_vs_fcfs_pct: float | None = Field(default=None, description="S5: '-18% vs FCFS' (cần chạy bóng FCFS)")
    at_risk_booking_ids: list[str] = Field(default_factory=list, description="US5 — phiên có nguy cơ trễ hạn")
    alerts: list[str] = Field(default_factory=list)


class SimulationRunRequest(BaseModel):
    """S8 — chạy một kịch bản với một chiến lược; field None = giữ giá trị của kịch bản."""

    scenario_id: str = Field(min_length=1)
    strategy: StrategyName
    n_vehicles: int | None = Field(default=None, gt=0)
    power_limit_kw: float | None = Field(default=None, gt=0)
    seed: int | None = None


class ResidentProfile(BaseModel):
    """F8 — hồ sơ cư dân: xe mặc định, mức pin hay dùng, phạm vi đã đồng ý trước (FR13)."""

    user_id: str
    display_name: str
    vehicle_model: str | None = None
    default_soc_target: float | None = Field(default=None, gt=0, le=100)
    consent: ConsentScope = Field(default_factory=ConsentScope)


class ProfileUpdateRequest(BaseModel):
    """PUT /resident/profile — field None = giữ nguyên (NFR: cho phép sửa thông tin)."""

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    vehicle_model: str | None = Field(default=None, min_length=1)
    default_soc_target: float | None = Field(default=None, gt=0, le=100)
    consent: ConsentScope | None = None


class BookingChangeRequest(BaseModel):
    """PATCH /resident/bookings/{id} — FR8 "đổi yêu cầu". Ít nhất một field."""

    soc_target: float | None = Field(default=None, gt=0, le=100)
    deadline: AwareDatetime | None = None

    @model_validator(mode="after")
    def _at_least_one_change(self) -> "BookingChangeRequest":
        if self.soc_target is None and self.deadline is None:
            raise ValueError("Cần ít nhất một trong soc_target, deadline")
        return self


class ResidentSessionView(BaseModel):
    """S2 — thẻ xe: lịch + tiến độ sạc của CHÍNH cư dân đang đăng nhập (FR15)."""

    booking: Booking | None = None
    plan: SessionPlan | None = Field(default=None, description="Lịch công suất theo bước của booking này")
    progress: SessionProgress | None = None
    soc_estimate: float | None = Field(default=None, ge=0, le=100, description="% pin ước tính — CODE tính")


class ConnectorDetail(BaseModel):
    """S5 — popup khi vận hành bấm vào một cột sạc."""

    state: ConnectorState
    booking: Booking | None = None
    plan: SessionPlan | None = None
    recent_decisions: list[DecisionLogEntry] = Field(default_factory=list)
