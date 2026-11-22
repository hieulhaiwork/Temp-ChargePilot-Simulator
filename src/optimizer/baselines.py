"""Phương án đối chứng A (quy tắc) và D (oracle) — PRD §8.

A là mốc vận hành mà Brief dùng để so ("giảm so với FCFS"); D là cận trên lý tưởng.
A chạy trên CÙNG lưới thời gian, cùng giới hạn tủ / vùng / lưới với B (src/optimizer/horizon.py),
không giải LP: mỗi bước chia công suất bằng luật đơn giản rồi trừ dần kWh còn thiếu.

  FCFS: hàng chờ theo thứ tự đến; công suất chia ĐỀU (water-filling) cho mọi xe đang cắm.
  EDF : hàng chờ theo hạn rời; công suất cấp tối đa lần lượt cho xe hạn gần nhất trước.
  D   : cùng LP với B nhưng thấy trước mọi yêu cầu của kịch bản (ctx.oracle_bookings).

Owner: TV1. Task: T1.5 (A), T3.4 (D).
"""

import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal

from src.models.charging import SchedulePlan, StrategyName
from src.optimizer.assignment import Assignment, assign_connectors
from src.optimizer.base import PlanningContext
from src.optimizer.horizon import (
    EPS,
    Group,
    SessionWindow,
    build_grid,
    constraint_groups,
    session_windows,
    to_session_plans,
)
from src.optimizer.lp_model import solve_power_allocation


def _headroom(groups: list[Group], used: list[list[float]], i: int, k: int) -> float:
    return min((g.limit_kw[k] - used[gi][k] for gi, g in enumerate(groups) if i in g.members), default=float("inf"))


def _allocate(
    ctx: PlanningContext, assignment: Assignment, rule: Literal["equal", "priority"]
) -> tuple[list[SessionWindow], list[list[float]]]:
    grid = build_grid(ctx)
    windows = session_windows(ctx, assignment, grid)
    groups = constraint_groups(ctx, windows, grid)
    used = [[0.0] * len(grid) for _ in groups]
    remaining = [w.remaining_kwh for w in windows]
    power = [[0.0] * len(grid) for _ in windows]
    order = sorted(range(len(windows)), key=lambda i: (windows[i].booking.request.deadline, i))
    for k in range(len(grid)):
        active = [i for i in order if windows[i].hours[k] > 0 and remaining[i] > EPS]
        want = {i: min(windows[i].cap_kw, remaining[i] / windows[i].hours[k]) for i in active}
        if rule == "priority":
            for i in active:
                give = max(0.0, min(want[i], _headroom(groups, used, i, k)))
                power[i][k] = give
                for gi, g in enumerate(groups):
                    if i in g.members:
                        used[gi][k] += give
        else:
            hungry = set(active)
            while hungry:
                # Tăng đều cho mọi xe còn thiếu, tới khi chạm giới hạn xe hoặc giới hạn nhóm chật nhất.
                step = min(want[i] - power[i][k] for i in hungry)
                for gi, g in enumerate(groups):
                    members = [i for i in hungry if i in g.members]
                    if members:
                        step = min(step, (g.limit_kw[k] - used[gi][k]) / len(members))
                step = max(step, 0.0)
                for i in hungry:
                    power[i][k] += step
                    for gi, g in enumerate(groups):
                        if i in g.members:
                            used[gi][k] += step
                full = {i for i in hungry if power[i][k] >= want[i] - EPS}
                blocked = {
                    i
                    for i in hungry
                    for gi, g in enumerate(groups)
                    if i in g.members and g.limit_kw[k] - used[gi][k] <= EPS
                }
                if not (full | blocked) and step <= EPS:
                    break
                hungry -= full | blocked
        for i in active:
            remaining[i] -= power[i][k] * windows[i].hours[k]
    return windows, power


def _plan(ctx: PlanningContext, strategy: StrategyName, order: Literal["edf", "fifo"], rule) -> SchedulePlan:
    started = time.perf_counter()
    ctx = replace(ctx, oracle_bookings=(), departure_forecast=None)
    assignment = assign_connectors(ctx, order)
    windows, power = _allocate(ctx, assignment, rule)
    grid = build_grid(ctx)
    return SchedulePlan(
        version=ctx.state.schedule_version + 1,
        strategy=strategy,
        created_at=datetime.now(UTC),
        horizon_start=ctx.now,
        step_minutes=ctx.config.optimizer.planning_step_minutes,
        sessions=to_session_plans(windows, power, grid, assignment),
        queue=list(assignment.queue),
        solve_time_s=round(time.perf_counter() - started, 4),
    )


class FcfsScheduler:
    """A — đến trước phục vụ trước; chia đều công suất khả dụng cho các xe đang cắm."""

    name = StrategyName.FCFS

    def plan(self, ctx: PlanningContext) -> SchedulePlan:
        return _plan(ctx, self.name, "fifo", "equal")


class EdfScheduler:
    """A — ưu tiên hạn rời gần nhất (Earliest Deadline First), chia công suất đơn giản."""

    name = StrategyName.EDF

    def plan(self, ctx: PlanningContext) -> SchedulePlan:
        return _plan(ctx, self.name, "edf", "priority")


class OracleScheduler:
    """D — biết trước toàn bộ yêu cầu của kịch bản (ctx.oracle_bookings). Chỉ dùng offline."""

    name = StrategyName.ORACLE

    def plan(self, ctx: PlanningContext) -> SchedulePlan:
        known = {b.booking_id for b in ctx.bookings}
        future = tuple(b for b in ctx.oracle_bookings if b.booking_id not in known)
        full = replace(ctx, bookings=(*ctx.bookings, *future), oracle_bookings=())
        return solve_power_allocation(full, assign_connectors(full, "edf"), self.name)
