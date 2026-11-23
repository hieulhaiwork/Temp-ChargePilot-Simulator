"""Interface của trạm sạc giả lập — tách ĐỌC và GHI.

Vì sao tách hai Protocol (abstraction có lý do cụ thể): PRD bắt buộc "LLM không bao giờ
gửi lệnh thẳng tới simulator" và "lệnh vi phạm không tới simulator". Ai cũng được ĐỌC
trạng thái (StationReader), nhưng chỉ guard/dispatcher.py được GHI (StationActuator).
tests/test_architecture.py fail nếu module khác import StationActuator hoặc gọi
apply_commands — quy ước được khoá bằng test, không chỉ bằng lời.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from src.models.control import Command
from src.models.events import StationEvent
from src.models.simulation import Incident, Scenario
from src.models.station import StationState


@dataclass(frozen=True)
class VehicleVisit:
    """Một xe SẼ / ĐANG có mặt ở bãi — dữ kiện MÔI TRƯỜNG (xe đến, rời), không phải lệnh điều khiển.

    Simulator không biết booking hay cư dân; tầng services dịch Booking → VehicleVisit.
    `required_kwh` là điện năng phía đầu ra cổng (Booking.energy.grid_energy_kwh, FR3).
    """

    booking_id: str
    arrival_time: datetime  # có múi giờ
    departure_time: datetime  # giờ rời khai báo = deadline (FR9)
    required_kwh: float
    zone: Literal["AC", "DC"]
    max_power_kw: float  # giới hạn của xe (Booking.max_charge_power_kw)
    # Pin — HybridStation (EV2Gym + profile DC) cần; LiveStation bỏ qua. None ⇒ suy từ required_kwh.
    battery_kwh: float | None = None  # dung lượng khả dụng (VehicleSpec.usable_capacity_kwh)
    soc_now: float | None = None  # phân số 0–1 (simulator dùng phân số, booking dùng %)
    soc_target: float | None = None  # phân số 0–1
    vehicle_model: str | None = None  # chọn profile DC VinFast (vinfast_profiles_v0_1)


class StationReader(Protocol):
    """Phần ĐỌC — control_loop, dashboard, benchmark đều dùng được."""

    def reset(self, scenario: Scenario) -> StationState:
        """Khởi tạo trạm theo kịch bản; trả trạng thái ban đầu."""
        ...

    def step(self, minutes: int) -> list[StationEvent]:
        """Tiến đồng hồ mô phỏng; trả sự kiện phát sinh (xe đến/rút, trụ lỗi, nguồn đổi)."""
        ...

    def state(self) -> StationState: ...

    def inject_incident(self, incident: Incident) -> list[StationEvent]:
        """US6/FR18: bơm sự cố (trụ hỏng, nguồn giảm) vào trạm ĐANG CHẠY; trả sự kiện phát sinh.

        Đây là thay đổi của MÔI TRƯỜNG mô phỏng, không phải lệnh điều khiển trạm — nên nằm ở
        phần đọc/kịch bản, không đi qua Guard. Phản ứng của hệ thống (hạ công suất, tính lại)
        thì vẫn là Command và vẫn qua guard/dispatcher.py.
        """
        ...

    def upsert_vehicle(self, visit: VehicleVisit) -> list[StationEvent]:
        """Báo trước / cập nhật một xe (đặt lịch, đổi yêu cầu). Giờ đến ≤ now → xe vào hàng chờ ngay.

        Như inject_incident: thay đổi môi trường, không đi qua Guard. Việc gán cổng / cấp điện vẫn là Command.
        """
        ...

    def remove_vehicle(self, booking_id: str) -> list[StationEvent]:
        """Xe không tới / huỷ lịch: rời bãi, giải phóng cổng nếu đang cắm."""
        ...


class StationActuator(Protocol):
    """Phần GHI — áp lệnh lên trạm. CHỈ guard/dispatcher.py được dùng."""

    def apply_commands(self, commands: Sequence[Command]) -> None: ...


class StationSimulator(StationReader, StationActuator, Protocol):
    """Adapter cụ thể cài cả hai; composition root chỉ đưa phần Actuator cho dispatcher."""
