"""B / C — MPC cửa sổ trượt (horizon_hours, planning_step_minutes lấy từ config — ADR-003), mỗi lần giải một LP (FR6).

    plan(ctx) = assign_connectors(ctx)  →  solve_power_allocation(ctx, assignment)
    → control_loop chỉ áp bước ĐẦU của lịch, bước sau tính lại (receding horizon).

use_forecast=False → B: mốc đo giá trị AI (cùng bộ tối ưu, không ML).
use_forecast=True  → C: dùng ctx.departure_forecast (F6). F6 HOÃN khỏi sprint (ADR-015) nên ctx.departure_forecast
luôn None và C cho kết quả GIỐNG B — benchmark phải ghi rõ, không tuyên bố AI cải thiện (PRD §8).

Owner: TV1. Task: T2.1.
"""

from dataclasses import replace

from src.models.charging import SchedulePlan, StrategyName
from src.models.planning import PlanningContext
from src.optimizer.assignment import assign_connectors
from src.optimizer.lp_model import solve_power_allocation


class MpcScheduler:
    def __init__(self, use_forecast: bool) -> None:
        self.use_forecast = use_forecast
        self.name = StrategyName.OPT_ML if use_forecast else StrategyName.OPT_NO_ML

    def plan(self, ctx: PlanningContext) -> SchedulePlan:
        # B/C không được đọc tương lai (oracle_bookings chỉ dành cho D); B không được đọc dự báo.
        ctx = replace(ctx, oracle_bookings=())
        if not self.use_forecast:
            ctx = replace(ctx, departure_forecast=None)
        return solve_power_allocation(ctx, assign_connectors(ctx, "edf"), self.name)
