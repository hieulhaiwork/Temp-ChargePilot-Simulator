"""Ngữ cảnh lập lịch của backend + Protocol `Scheduler` (chuyển từ `src/optimizer/base.py`, ADR-019 Phase 3).

Vì sao ở `src/models`: control_loop, Planning Core backend (`services/hybrid_planner.py`), admission và test cùng dùng;
không còn thuộc gói LP cũ. Pydantic thuần, không phụ thuộc ORM. Mỗi chiến lược nhận PlanningContext, trả SchedulePlan.
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


class Scheduler(Protocol):
    """Một chiến lược lập lịch. Hàm plan() phải thuần: cùng context → cùng kết quả."""

    name: StrategyName | str  # StrategyName cho B0 / M2b / M3a / M3b; id chuỗi cho policy đăng ký mới (registry)

    def plan(self, ctx: PlanningContext) -> SchedulePlan: ...
