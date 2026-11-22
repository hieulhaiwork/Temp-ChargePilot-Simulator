"""Interface chung của mọi chiến lược lập lịch — A, B, C, D (PRD §8).

Vì sao có Protocol (abstraction có lý do cụ thể): benchmark A–D phải chạy CÙNG một
interface trên cùng tập phiên, cùng biểu giá. Mỗi chiến lược nhận PlanningContext,
trả SchedulePlan — đổi chiến lược = đổi một dòng ở màn S8 hoặc eval/run_benchmark.py.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from src.models.charging import Booking, SchedulePlan, StrategyName
from src.models.station import StationConfig, StationState, Tariff


@dataclass(frozen=True)
class PlanningContext:
    """Mọi dữ kiện bộ tối ưu cần — truyền vào, optimizer KHÔNG tự đọc file/DB/API.

    FR9: `departure_forecast` CHỈ dùng để ước lượng lúc đầu nối được giải phóng (xếp
    hàng đợi). Nó KHÔNG được nới `deadline` của booking — deadline là ràng buộc cứng.
    """

    now: datetime  # có múi giờ
    state: StationState
    bookings: tuple[Booking, ...]  # yêu cầu đã chấp nhận, còn hiệu lực
    config: StationConfig
    tariff: Tariff
    power_limit_forecast_kw: Mapping[datetime, float] = field(default_factory=dict)  # trống = giữ giới hạn hiện hành
    departure_forecast: Mapping[str, datetime] | None = (
        None  # booking_id → lúc dự kiến RÚT cổng; F6 hoãn (ADR-015) → None
    )
    # AC4: cư dân đã TỪ CHỐI một điều chỉnh → phạm vi consent của booking đó thành ràng buộc cứng,
    # nếu không vòng tính lại sau sẽ đề xuất đúng lệnh vừa bị từ chối.
    hard_consent_booking_ids: frozenset[str] = frozenset()
    # CHỈ chiến lược D (oracle): toàn bộ yêu cầu của kịch bản, kể cả xe chưa đến. Live luôn để trống.
    oracle_bookings: tuple[Booking, ...] = ()


class Scheduler(Protocol):
    """Một chiến lược lập lịch. Hàm plan() phải thuần: cùng context → cùng kết quả."""

    name: StrategyName

    def plan(self, ctx: PlanningContext) -> SchedulePlan: ...
