"""FR7 — gán booking vào đầu nối + xếp hàng đợi.

Luật (ADR-010, ADR-015 — bản sprint, không MILP):
  1. Xe đang cắm GIỮ cổng của mình (không ai rút cắm hộ). Cổng FINISHED vẫn bị chiếm tới khi xe rút.
  2. Xe đã đến nhưng chưa cắm: xếp theo `order` ("edf" = hạn rời gần nhất trước — FR7; "fifo" = đến
     trước — baseline FCFS), lần lượt nhận cổng TRỐNG cùng vùng (AC/DC), không lỗi. Hết cổng → hàng đợi.
  3. Booking đặt trước chưa đến: dự kiến nhận cổng lúc đến nếu khi đó có cổng cùng vùng được giải phóng
     (xe AC giữ cổng tới giờ rời khai báo; xe DC rời sau khi đầy + dc_unplug_delay). Không có → để
     trống, tính lại khi xe đến (receding horizon).
Với chiến lược C, `ctx.departure_forecast` thay giờ rời khai báo khi ước lượng lúc cổng được giải phóng
(F6 hoãn — ADR-015 — nên hiện luôn là None).

Owner: TV1 (thuật toán) + TV3 (hàng đợi trong simulator). Task: T2.2.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from src.models.charging import Booking, BookingStatus
from src.models.station import ConnectorStatus
from src.optimizer.base import PlanningContext


@dataclass(frozen=True)
class Assignment:
    connector_of: Mapping[str, str]  # booking_id → connector_id (đang cắm, gán ngay, hoặc DỰ KIẾN khi cổng rảnh)
    queue: tuple[str, ...]  # booking_id đã đến nhưng chưa cắm được, đầu hàng trước
    start_of: Mapping[str, datetime] = field(default_factory=dict)  # booking_id → lúc dự kiến cắm (nếu sau now)


def remaining_kwh(ctx: PlanningContext, booking: Booking) -> float:
    """kWh còn thiếu = kWh đã chấp thuận − kWh đã giao (state.sessions)."""
    progress = next((s for s in ctx.state.sessions if s.booking_id == booking.booking_id), None)
    return max(booking.energy.grid_energy_kwh - (progress.delivered_grid_kwh if progress else 0.0), 0.0)


def _release_time(ctx: PlanningContext, booking: Booking, port_kw: float, start: datetime) -> datetime:
    """Lúc cổng được giải phóng nếu booking này chiếm nó từ `start`."""
    departure = booking.request.deadline
    if ctx.departure_forecast and booking.booking_id in ctx.departure_forecast:
        departure = ctx.departure_forecast[booking.booking_id]  # chỉ ước lượng giải phóng cổng (FR9)
    if booking.request.zone == "DC":
        rate = max(min(port_kw, booking.max_charge_power_kw), 1e-6)
        full = start + timedelta(hours=remaining_kwh(ctx, booking) / rate)
        return min(departure, full + timedelta(minutes=ctx.config.dc_unplug_delay_minutes))
    return departure


def assign_connectors(ctx: PlanningContext, order: Literal["edf", "fifo"] = "edf") -> Assignment:
    """Gán đầu nối cho booking đang có mặt; xe còn lại vào hàng đợi theo `order`."""
    specs = {c.connector_id: c for c in ctx.config.connectors}
    bookings = {b.booking_id: b for b in (*ctx.bookings, *ctx.oracle_bookings)}
    present = {s.booking_id: s for s in ctx.state.sessions}
    connector_of: dict[str, str] = {}
    free_at: dict[str, datetime] = {}
    for conn in ctx.state.connectors:
        if conn.status == ConnectorStatus.FAULT or conn.connector_id not in specs:
            continue
        if conn.booking_id:
            connector_of[conn.booking_id] = conn.connector_id
            booking = bookings.get(conn.booking_id)
            spec_kw = specs[conn.connector_id].max_power_kw
            free_at[conn.connector_id] = _release_time(ctx, booking, spec_kw, ctx.now) if booking else ctx.now
        else:
            free_at[conn.connector_id] = ctx.now

    def zone_ports(zone: str) -> list[str]:
        return sorted(cid for cid in free_at if specs[cid].zone == zone)

    waiting = [bookings[b] for b in ctx.state.queue if b in bookings]
    waiting += [b for bid, b in bookings.items() if bid in present and bid not in connector_of and b not in waiting]
    if order == "edf":
        waiting.sort(key=lambda b: (b.request.deadline, b.created_at, b.booking_id))
    queue: list[str] = []
    start_of: dict[str, datetime] = {}

    def claim(booking: Booking, earliest: datetime) -> bool:
        """Cổng cùng vùng rảnh sớm nhất (≥ earliest), miễn là trước giờ rời. Không có → False."""
        candidates = [cid for cid in zone_ports(booking.request.zone) if free_at[cid] < booking.request.deadline]
        if not candidates:
            return False
        port = min(candidates, key=lambda cid: (max(free_at[cid], earliest), cid))
        start = max(free_at[port], earliest)
        if start >= booking.request.deadline:
            return False
        connector_of[booking.booking_id] = port
        if start > ctx.now:
            start_of[booking.booking_id] = start
        free_at[port] = _release_time(ctx, booking, specs[port].max_power_kw, start)
        return True

    for booking in waiting:
        claim(booking, ctx.now)
        if start_of.get(booking.booking_id) or booking.booking_id not in connector_of:
            queue.append(booking.booking_id)  # vẫn đang chờ cổng (có hoặc chưa có dự kiến)

    # Đặt trước chưa đến (giờ đến đã qua mà chưa thấy xe = coi như đến ngay — vd walk-in đang được quote).
    future = [
        b
        for bid, b in bookings.items()
        if bid not in present
        and bid not in connector_of
        and b.status in (BookingStatus.CONFIRMED, BookingStatus.QUEUED)
    ]

    def arrival(b: Booking) -> datetime:
        return max(b.request.arrival_time or ctx.now, ctx.now)

    for booking in sorted(future, key=lambda b: (arrival(b), b.request.deadline, b.booking_id)):
        claim(booking, arrival(booking))
    return Assignment(connector_of=connector_of, queue=tuple(queue), start_of=start_of)
