"""Hợp đồng dữ liệu nghiệp vụ sạc: xe, yêu cầu, đặt lịch, phương án, lịch công suất.

Vì sao tồn tại: đây là "ngôn ngữ chung" giữa Agent (F1 trích xuất ChargeRequest),
bộ tối ưu (F2/F3 sinh SchedulePlan), API/web (F5) và đánh giá (F7). Tên field bám
đúng PRD FR2: vehicle_model, soc_now, soc_target, arrival_time, deadline, mode.

Quy ước: % pin là phần trăm 0–100; điện năng kWh; tiền VND; thời gian có múi giờ.
Module thuần dữ liệu — chỉ import src.models.* (tests/test_architecture.py).
"""

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class ChargeMode(StrEnum):
    """FR2 — cách cư dân tới sạc."""

    RESERVATION = "reservation"  # đặt trước
    WALK_IN = "walk_in"  # đến trực tiếp; hết đầu nối thì vào hàng đợi (US2)


ProvenanceStatus = Literal["verified", "oem_claim", "proxy", "assumed", "synthetic", "unverified"]


class FieldProvenance(BaseModel):
    """Nguồn và mức kiểm chứng của MỘT trường thông số xe (ADR-012)."""

    source: str = Field(min_length=1, description="Link / mô tả nguồn của giá trị")
    status: ProvenanceStatus


class VehicleSpec(BaseModel):
    """Một mẫu xe trong danh mục duy nhất config/vehicles.yaml (ADR-012)."""

    vehicle_model: str = Field(min_length=1, description="Mã xe, dùng trong ChargeRequest")
    display_name: str
    usable_capacity_kwh: float = Field(gt=0, description="Dung lượng pin KHẢ DỤNG")
    max_ac_power_kw: float = Field(gt=0, description="Công suất sạc AC tối đa của xe (OBC)")
    max_dc_kw: float | None = Field(
        default=None, gt=0, description="Công suất DC tối đa xe nhận; None = xe không sạc DC"
    )
    dc_curve: str | None = Field(
        default=None,
        description="Mã đường sạc DC trong registry của simulator (ADR-012); YAML chỉ chọn, không định nghĩa",
    )
    charging_efficiency: float | None = Field(default=None, gt=0, le=1, description="Ghi đè giả định của trạm")
    provenance: dict[str, FieldProvenance] = Field(
        default_factory=dict, description="Nguồn + trạng thái theo từng trường (ADR-012), khoá = tên field"
    )
    source: str = Field(min_length=1, description="DEPRECATED (ADR-012) — nguồn chung; dùng provenance theo trường")
    verified: bool = Field(default=False, description="DEPRECATED (ADR-012) — cờ chung; dùng provenance[*].status")

    @model_validator(mode="after")
    def _provenance_keys_are_fields(self) -> "VehicleSpec":
        unknown = set(self.provenance) - set(type(self).model_fields)
        if unknown:
            raise ValueError(f"provenance có khoá không phải field của VehicleSpec: {sorted(unknown)}")
        return self


class ChargeRequest(BaseModel):
    """Yêu cầu sạc đã chuẩn hoá — đầu ra trích xuất của Agent (FR2) HOẶC form thủ công.

    Validator chạy ngay tại ranh giới tool/API: LLM trích sai (target ≤ now, thiếu
    múi giờ, deadline trước giờ đến) thì fail ở đây, không lọt vào bộ tối ưu.
    """

    vehicle_model: str = Field(min_length=1, description="Mã xe trong config/vehicles.yaml")
    soc_now: float = Field(ge=0, le=100, description="% pin hiện tại")
    soc_target: float = Field(gt=0, le=100, description="% pin mong muốn")
    arrival_time: AwareDatetime | None = Field(default=None, description="Giờ cắm xe; None = đến ngay (walk-in)")
    deadline: AwareDatetime = Field(description="Giờ cần lấy xe — RÀNG BUỘC CỨNG (FR9)")
    mode: ChargeMode
    zone: Literal["AC", "DC"] = Field(default="AC", description="Vùng sạc (ADR-010): AC chậm qua đêm | DC sạc nhanh")

    @model_validator(mode="after")
    def _check_consistency(self) -> "ChargeRequest":
        if self.soc_target <= self.soc_now:
            raise ValueError("soc_target phải lớn hơn soc_now")
        if self.mode == ChargeMode.RESERVATION and self.arrival_time is None:
            raise ValueError("Đặt trước (reservation) cần arrival_time")
        if self.arrival_time is not None and self.deadline <= self.arrival_time:
            raise ValueError("deadline phải sau arrival_time")
        return self


class EnergyEstimate(BaseModel):
    """Kết quả FR3 — do CODE tính (src/services/energy.py), LLM không tự tính."""

    vehicle_model: str
    soc_now: float
    soc_target: float
    battery_energy_kwh: float = Field(ge=0, description="Điện nạp vào pin = dung lượng khả dụng × Δ%pin")
    grid_energy_kwh: float = Field(ge=0, description="Điện lấy từ lưới = điện nạp vào pin ÷ hiệu suất")
    efficiency: float = Field(gt=0, le=1)


class ConsentScope(BaseModel):
    """Phạm vi cư dân ĐÃ ĐỒNG Ý trước (FR13, F8).

    Điều chỉnh của bộ tối ưu vượt phạm vi này phải hỏi cư dân (màn S4).
    """

    max_start_delay_minutes: int = Field(default=0, ge=0, description="Được lùi giờ bắt đầu tối đa")
    allow_power_reduction: bool = Field(default=True, description="Được giảm công suất nếu vẫn kịp deadline")
    emergency_curtailment: bool = Field(default=True, description="Đồng ý trước bảo vệ khẩn cấp (FR13 dòng 2)")


class BookingStatus(StrEnum):
    CONFIRMED = "confirmed"  # đã chốt, chờ tới giờ / chờ cắm
    QUEUED = "queued"  # walk-in đang chờ đầu nối (US2)
    CHARGING = "charging"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Booking(BaseModel):
    """Lịch sạc đã chốt của một cư dân."""

    booking_id: str
    resident_id: str
    request: ChargeRequest
    status: BookingStatus
    energy: EnergyEstimate
    max_charge_power_kw: float = Field(
        gt=0, description="min(đầu nối, OBC của xe), CODE tính lúc đặt — optimizer/guard không được gọi catalog"
    )
    consent: ConsentScope = Field(default_factory=ConsentScope)
    connector_id: str | None = None
    planned_start: AwareDatetime | None = None
    planned_end: AwareDatetime | None = None
    estimated_cost_vnd: float | None = Field(default=None, ge=0)
    schedule_version: int = Field(ge=0)
    created_at: AwareDatetime


class AlternativeKind(StrEnum):
    """FR4 — các loại phương án thay thế khi không đạt được cam kết."""

    OTHER_TIME = "other_time"  # giờ khác
    LOWER_TARGET = "lower_target"  # mức pin thấp hơn
    JOIN_QUEUE = "join_queue"  # vào hàng đợi


class Alternative(BaseModel):
    kind: AlternativeKind
    description: str
    soc_target: float | None = Field(default=None, gt=0, le=100)
    deadline: AwareDatetime | None = None


class ScheduleProposal(BaseModel):
    """Phương án what-if cho màn S3 — CHƯA giữ chỗ.

    `reasons` do CODE sinh từ kết quả tối ưu; Agent chỉ diễn đạt lại (US3), không bịa.
    """

    feasible: bool
    energy: EnergyEstimate
    connector_id: str | None = None
    planned_start: AwareDatetime | None = None
    planned_end: AwareDatetime | None = None
    estimated_cost_vnd: float | None = Field(default=None, ge=0)
    slack_minutes: float | None = Field(default=None, description="Dư bao lâu so với deadline (S3: 'còn dư 1h30')")
    queue_position: int | None = Field(default=None, ge=1)
    reasons: list[str] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)

    @model_validator(mode="after")
    def _infeasible_needs_alternative(self) -> "ScheduleProposal":
        if not self.feasible and not self.alternatives:
            raise ValueError("FR4: không khả thi thì phải có ít nhất 1 phương án thay thế")
        return self


class StrategyName(StrEnum):
    """Policy của Planning Core (registry `src/optimizer/registry.py`, version 1) — chạy thật, benchmark, màn S8.

    A_fcfs / A_edf / B / C / D (LP backend cũ) đã bỏ hẳn (Tech Lead, quyết định Phase 4 số 1). Policy mới phải đăng ký
    trong registry rồi mới thêm giá trị ở đây.
    """

    SIM_B0 = "B0"  # FCFS + Equal Share AC/DC + Fixed Share
    SIM_M2B = "M2b"  # LLF + DC rolling LP + Fixed Share
    SIM_M3A = "M3a"  # LLF + AC/DC LP + Fixed Share (policy tham chiếu cho demo)
    SIM_M3B = "M3b"  # LLF + AC/DC LP + Dynamic Slack


class PowerSlot(BaseModel):
    """Công suất cấp cho một booking trong một bước MPC."""

    start: AwareDatetime
    power_kw: float = Field(ge=0)


class SessionPlan(BaseModel):
    booking_id: str
    connector_id: str | None = Field(default=None, description="None = đang trong hàng đợi")
    slots: list[PowerSlot] = Field(default_factory=list)


class SchedulePlan(BaseModel):
    """Đầu ra của bộ tối ưu — dữ liệu của Gantt S6."""

    version: int = Field(ge=0)
    strategy: StrategyName
    created_at: AwareDatetime
    horizon_start: AwareDatetime
    step_minutes: int = Field(gt=0)
    sessions: list[SessionPlan] = Field(default_factory=list)
    queue: list[str] = Field(default_factory=list, description="booking_id chờ đầu nối, đầu hàng trước")
    solve_time_s: float | None = Field(default=None, ge=0, description="Thời gian giải — đo MT5")


class ChargingSession(BaseModel):
    """Một phiên sạc lịch sử/mô phỏng — dữ liệu Na Uy/ACN chuẩn hoá về dạng này (F6)."""

    session_id: str
    user_id: str = Field(description="Mã giả danh — không dùng danh tính thật (NFR riêng tư)")
    site: str | None = Field(default=None, description="Địa điểm — để chia train/test theo địa điểm")
    connector_id: str | None = None
    plug_in_time: AwareDatetime
    unplug_time: AwareDatetime | None = Field(default=None, description="NHÃN của F6 — CẤM dùng làm feature")
    energy_kwh: float = Field(ge=0)
    declared_departure: AwareDatetime | None = Field(default=None, description="Giờ cư dân khai báo")
