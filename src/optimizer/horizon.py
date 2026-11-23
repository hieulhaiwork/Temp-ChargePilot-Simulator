"""Lưới thời gian + dữ kiện từng phiên — dùng CHUNG cho LP (B/C/D) và baseline (A).

Vì sao một module riêng: cả bốn chiến lược phải đọc cùng một cách "xe nào sạc được ở bước nào, tối đa
bao nhiêu, còn thiếu bao nhiêu kWh, chịu những giới hạn tủ / vùng / lưới nào" — nếu mỗi chiến lược tự
tính, benchmark A–D không còn so sánh cùng điều kiện (PRD §8).

Bước LP = config.optimizer.planning_step_minutes; horizon = config.horizon_hours (ADR-003).
Công suất là công suất ĐẦU RA cổng; giới hạn lưới so Σ / power_conversion_efficiency (ADR-010).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.models.charging import Booking, PowerSlot, SessionPlan
from src.models.planning import PlanningContext
from src.optimizer.assignment import Assignment, remaining_kwh

EPS = 1e-6


@dataclass(frozen=True)
class Grid:
    starts: tuple[datetime, ...]
    step_h: float

    def __len__(self) -> int:
        return len(self.starts)


@dataclass(frozen=True)
class SessionWindow:
    """Một booking đã có (hoặc sẽ có) đầu nối trong horizon."""

    booking: Booking
    connector_id: str
    cap_kw: float  # min(cổng, xe)
    remaining_kwh: float
    hours: tuple[float, ...]  # số giờ booking CÓ MẶT ở cổng trong từng bước (0 = không sạc được)
    # Consent "được lùi giờ bắt đầu tối đa" (FR13): xe chưa nhận kWh nào phải được cấp ít nhất start_min_kw ở
    # bước start_step. None = không ràng buộc (đã bắt đầu, được lùi quá horizon, hoặc không còn kWh cần nạp).
    start_step: int | None = None
    start_min_kw: float = 0.0


@dataclass(frozen=True)
class Group:
    """Một ràng buộc tổng: Σ_{i ∈ members} p[i,k] ≤ limit_kw[k]."""

    name: str
    members: tuple[int, ...]
    limit_kw: tuple[float, ...]


def build_grid(ctx: PlanningContext) -> Grid:
    step = ctx.config.optimizer.planning_step_minutes
    n = max(1, ctx.config.horizon_hours * 60 // step)
    return Grid(starts=tuple(ctx.now + timedelta(minutes=step * k) for k in range(n)), step_h=step / 60)


def session_windows(ctx: PlanningContext, assignment: Assignment, grid: Grid) -> list[SessionWindow]:
    bookings = {b.booking_id: b for b in (*ctx.bookings, *ctx.oracle_bookings)}
    ports = {c.connector_id: c for c in ctx.config.connectors}
    progress = {s.booking_id: s for s in ctx.state.sessions}
    windows: list[SessionWindow] = []
    for booking_id, connector_id in sorted(assignment.connector_of.items()):
        booking = bookings.get(booking_id)
        if booking is None or connector_id not in ports:
            continue
        start = assignment.start_of.get(booking_id, ctx.now)
        end = booking.request.deadline
        hours = tuple(
            max(0.0, (min(t + timedelta(hours=grid.step_h), end) - max(t, start)).total_seconds() / 3600)
            for t in grid.starts
        )
        cap = min(ports[connector_id].max_power_kw, booking.max_charge_power_kw)
        remaining = remaining_kwh(ctx, booking)
        start_step, start_min_kw = _start_requirement(
            booking, progress.get(booking_id), start, hours, cap, remaining, grid
        )
        windows.append(
            SessionWindow(
                booking=booking,
                connector_id=connector_id,
                cap_kw=cap,
                remaining_kwh=remaining,
                hours=hours,
                start_step=start_step,
                start_min_kw=start_min_kw,
            )
        )
    return windows


def _start_requirement(booking: Booking, progress, start: datetime, hours, cap: float, remaining: float, grid: Grid):
    """Bước phải bắt đầu sạc theo consent.max_start_delay_minutes, và công suất tối thiểu ở bước đó.

    Mốc tính lùi giờ là lúc xe SẠC ĐƯỢC: đã cắm → plugged_in_at (cố định, không trôi theo mỗi lần tính lại);
    chưa cắm → lúc cổng dự kiến rảnh (start). Chờ vì hết cổng không phải "lùi giờ" — đó là hàng đợi.
    Không dùng Booking.planned_start: mốc đó do chính lịch sinh ra nên so với nó thì luôn bằng 0.
    """
    if progress is not None and progress.delivered_grid_kwh > EPS:
        return None, 0.0  # đã bắt đầu: giảm / tạm dừng sau đó thuộc consent allow_power_reduction (Guard xét)
    if remaining <= EPS:
        return None, 0.0
    anchor = progress.plugged_in_at if progress is not None and progress.plugged_in_at else start
    limit = anchor + timedelta(minutes=booking.consent.max_start_delay_minutes)
    step = timedelta(hours=grid.step_h)
    for k, t in enumerate(grid.starts):
        if hours[k] <= EPS or t + step <= limit:
            continue
        return k, min(cap, remaining / hours[k])
    return None, 0.0


def constraint_groups(ctx: PlanningContext, windows: Sequence[SessionWindow], grid: Grid) -> list[Group]:
    """Ba tầng của ADR-010: tủ, vùng, lưới (lưới đổi về phía đầu ra bằng × η)."""
    cfg = ctx.config
    ports = {c.connector_id: c for c in cfg.connectors}
    eta = cfg.power_conversion_efficiency
    limits = [
        min(ctx.power_limit_forecast_kw.get(t, ctx.state.available_power_kw), ctx.state.available_power_kw)
        if ctx.power_limit_forecast_kw
        else ctx.state.available_power_kw
        for t in grid.starts
    ]
    groups = [Group("grid", tuple(range(len(windows))), tuple(limit * eta for limit in limits))]
    for cab in cfg.cabinets:
        members = tuple(i for i, w in enumerate(windows) if ports[w.connector_id].cabinet_id == cab.cabinet_id)
        if members:
            groups.append(Group(f"cabinet:{cab.cabinet_id}", members, (cab.output_limit_kw,) * len(grid)))
    for zone, budget in (cfg.zone_budgets_kw or {}).items():
        members = tuple(i for i, w in enumerate(windows) if ports[w.connector_id].zone == zone)
        if members:
            groups.append(Group(f"zone:{zone}", members, (budget,) * len(grid)))
    return groups


def prices(ctx: PlanningContext, grid: Grid) -> tuple[float, ...]:
    tz = ZoneInfo(ctx.config.timezone)
    return tuple(ctx.tariff.price_at(t.astimezone(tz).time()) for t in grid.starts)


def to_session_plans(
    windows: Sequence[SessionWindow], power: Sequence[Sequence[float]], grid: Grid, assignment: Assignment
) -> list[SessionPlan]:
    plans = [
        SessionPlan(
            booking_id=w.booking.booking_id,
            connector_id=w.connector_id,
            slots=[
                PowerSlot(start=grid.starts[k], power_kw=round(power[i][k], 4))
                for k in range(len(grid))
                if power[i][k] > EPS
            ],
        )
        for i, w in enumerate(windows)
    ]
    # Xe đang chờ mà đã có cổng DỰ KIẾN thì đã nằm ở trên (connector_id = cổng dự kiến); chỉ thêm xe chưa có cổng.
    planned = {p.booking_id for p in plans}
    plans += [SessionPlan(booking_id=b, connector_id=None) for b in assignment.queue if b not in planned]
    return plans
