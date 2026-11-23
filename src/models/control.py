"""Hợp đồng LỆNH ĐIỀU KHIỂN, kết luận Guard, phê duyệt và nhật ký quyết định (F4).

Vì sao tồn tại: nguyên tắc "Bộ tối ưu tính phương án — Bộ kiểm tra an toàn kiểm soát
thực thi". Mọi thay đổi lên trạm là một `Command`; mọi Command có một `GuardVerdict`;
Command nhạy cảm có `Approval`; mọi bước ghi `DecisionLogEntry` (FR14).

Các field `issued_by`, `based_on_schedule_version`, `based_on_state_at` tồn tại để
Guard kiểm được các luật FR12: quyền thao tác, lịch đã cũ, dữ liệu cũ.
"""

import math
from enum import StrEnum
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, Field, model_validator

# Độ phân giải mã hoá công suất trong lịch / Command (kW). KHÁC với command deadband
# (control_loop.POWER_TOL_KW = 0,01 kW: chênh nhỏ hơn thì không gửi lệnh mới).
COMMAND_QUANTUM_KW = 0.001


def quantize_kw(kw: float) -> float:
    """Setpoint → giá trị gửi trạm, LÀM TRÒN XUỐNG theo COMMAND_QUANTUM_KW: không bao giờ lớn hơn setpoint đã qua
    Physical Guard (trần cứng kiểm với TOL 1e-7).

    Root-cause sai lệch AC +1,97 kW (PHASE3_REPORT §7; phút 560 `peak_evening` seed 2 M3b): kế hoạch dùng đúng 33,25 kW
    đầu ra = 35 kW lưới × 0,95; làm tròn GẦN NHẤT đẩy AC 7,278906 → 7,279 kW (+0,094 W) nên lô lệnh vượt trần lưới vài W,
    luật tổng công suất chặn cả lô (kể cả lệnh giảm AC) và setpoint AC cũ 9,25 kW tiếp tục chạy.
    """
    steps = math.floor(kw / COMMAND_QUANTUM_KW + 1e-9)  # +1e-9 bước: 4.35 không thành 4.349 vì sai số nhị phân
    return max(0.0, round(steps * COMMAND_QUANTUM_KW, 9))


class Role(StrEnum):
    """FR1 — hai vai trò đăng nhập."""

    RESIDENT = "resident"
    OPERATOR = "operator"


class CommandType(StrEnum):
    SET_POWER = "set_power"
    START = "start"
    STOP = "stop"
    ASSIGN_CONNECTOR = "assign_connector"


class CommandSource(StrEnum):
    """Thành phần đề xuất lệnh — ghi vào nhật ký quyết định (FR14)."""

    OPTIMIZER = "optimizer"
    LOAD_BALANCER = "load_balancer"
    EMERGENCY = "emergency"  # bảo vệ khẩn cấp, độc lập với AI (FR13)
    OPERATOR = "operator"  # vận hành xếp tay (S6)
    AGENT = "agent"  # chỉ ĐỀ XUẤT; luôn qua Guard + phê duyệt — Agent không tự quyết công suất (FR5)


class Command(BaseModel):
    """Một lệnh muốn áp lên trạm. Chỉ guard/dispatcher.py được đưa lệnh tới simulator."""

    command_id: str = Field(default_factory=lambda: uuid4().hex)
    type: CommandType
    connector_id: str
    power_kw: float | None = Field(default=None, ge=0, description="Bắt buộc với set_power")
    booking_id: str | None = Field(default=None, description="Bắt buộc với assign_connector")
    source: CommandSource
    issued_by: str = Field(min_length=1, description="user_id hoặc tên thành phần — luật quyền (FR12)")
    based_on_schedule_version: int = Field(ge=0, description="Luật phiên bản lịch (FR12)")
    based_on_state_at: AwareDatetime = Field(description="Luật dữ liệu cũ (FR12)")
    created_at: AwareDatetime
    reason: str = ""

    @model_validator(mode="after")
    def _check_payload(self) -> "Command":
        if self.type == CommandType.SET_POWER and self.power_kw is None:
            raise ValueError("set_power cần power_kw")
        if self.type == CommandType.ASSIGN_CONNECTOR and not self.booking_id:
            raise ValueError("assign_connector cần booking_id")
        return self


class GuardRule(StrEnum):
    """7 luật xác định của FR12 — mỗi luật một unit test (NFR an toàn)."""

    TOTAL_POWER = "total_power_limit"
    CONNECTOR_POWER = "connector_power_limit"
    ANTI_FLAPPING = "anti_flapping"
    STALE_STATE = "stale_state"
    PERMISSION = "permission"
    SCHEDULE_VERSION = "schedule_version"
    CONFLICT = "conflicting_commands"


class Violation(BaseModel):
    rule: GuardRule
    detail: str


class GuardVerdict(BaseModel):
    """Kết luận của Guard cho một lệnh. `passed` ⇔ không có vi phạm."""

    command_id: str
    passed: bool
    violations: list[Violation] = Field(default_factory=list)
    checked_at: AwareDatetime

    @model_validator(mode="after")
    def _passed_matches_violations(self) -> "GuardVerdict":
        if self.passed == bool(self.violations):
            raise ValueError("passed phải đúng khi và chỉ khi violations rỗng")
        return self


class ApprovalKind(StrEnum):
    RESIDENT_CONSENT = "resident_consent"  # FR13 dòng 1 — vượt phạm vi cư dân đã đồng ý (màn S4)
    OPERATOR_REVIEW = "operator_review"  # vận hành duyệt (màn S7)


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"  # hết hạn = KHÔNG thực thi (AC4)


class Approval(BaseModel):
    """Yêu cầu phê duyệt cho một lệnh đã QUA Guard."""

    approval_id: str = Field(default_factory=lambda: uuid4().hex)
    kind: ApprovalKind
    status: ApprovalStatus = ApprovalStatus.PENDING
    command: Command
    verdict: GuardVerdict
    requested_from: str = Field(description="resident_id, hoặc 'operator'")
    impact_summary: str = Field(description="Ảnh hưởng tới cam kết, vd 'Cam kết 80% lúc 7:00: vẫn giữ'")
    created_at: AwareDatetime
    expires_at: AwareDatetime | None = None
    decided_at: AwareDatetime | None = None
    decided_by: str | None = None

    @model_validator(mode="after")
    def _only_guard_passed_commands(self) -> "Approval":
        if not self.verdict.passed:
            raise ValueError("Lệnh bị Guard chặn không bao giờ được đưa đi phê duyệt")
        if self.verdict.command_id != self.command.command_id:
            raise ValueError("verdict không thuộc command này")
        return self


class DecisionLogEntry(BaseModel):
    """FR14 — ai/thành phần nào đề xuất, Guard kết luận gì, ai duyệt, lúc nào, có thực thi không."""

    entry_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: AwareDatetime
    command: Command
    verdict: GuardVerdict | None = None
    approval_id: str | None = None
    approved_by: str | None = None
    executed: bool
    note: str = ""
