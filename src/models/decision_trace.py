"""Backend trace summary, schema version and per-step evidence."""

from dataclasses import dataclass

from pydantic import AwareDatetime, BaseModel, Field

from src.models.decisions import AppliedResult

TRACE_SCHEMA = "chargepilot.backend_decision_trace/2"


@dataclass(frozen=True)
class BackendAppliedSample:
    result: AppliedResult
    held_setpoints_kw: dict[str, float]


class DecisionTraceSummary(BaseModel):
    correlation_id: str = Field(min_length=1, max_length=32)
    decided_at: AwareDatetime
    trigger: str  # EventType của sự kiện kích hoạt (các sự kiện cùng thời điểm gộp ở artifact)
    policy_id: str
    policy_version: str
    state_version: int | None = None  # None khi Planning Core từ chối trước khi áp
    schedule_version: int
    interval_minutes: int = 0  # khoảng quyết định đã lập kế hoạch
    applied_minutes: int = 0  # số phút vật lý thực sự chạy dưới quyết định này (0 khi đang mở)
    reason_codes: list[str] = Field(default_factory=list)
    commands_total: int = 0
    commands_executed: int = 0
    commands_blocked: int = 0
    commands_pending_approval: int = 0
    load_reduction_priority: int = 0  # lệnh giảm tải an toàn được áp không chờ HITL
    budget_deviation_kw_max: float = 0.0
    command_deadband_kw_max: float = 0.0
    hard_violations: int = 0
    closed: bool = False
    artifact: str | None = None  # tên file JSONL trong DECISION_TRACE_DIR (không phải đường dẫn tuyệt đối)
