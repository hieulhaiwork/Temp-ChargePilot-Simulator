"""Application service cho màn vận hành trạm (S5, S6) — đọc trạng thái, lập lịch lại, xếp tay.

Vì sao tách khỏi charging_service: hai vai trò có quyền và câu hỏi khác nhau (FR1).
Cư dân chỉ thấy lịch của mình; vận hành thấy toàn trạm và được ra lệnh — nhưng lệnh
của vận hành VẪN đi qua Guard (guard/dispatcher.py), không có cửa sau.

Hàm chỉ đọc là `def`; hàm phát sự kiện / ra lệnh là `async def` (ADR-007).

Owner: TV3 (backend) + TV4 (dùng ở dashboard). Task: T3.6 (đọc), T2.6 (replan), T3.2 (xếp tay).
"""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from src.guard import dispatcher
from src.models.api import ConnectorDetail, ErrorCode, StationOverview
from src.models.charging import Booking, BookingStatus, SchedulePlan
from src.models.control import Command, CommandSource, CommandType, DecisionLogEntry, Role
from src.models.events import EventType, StationEvent
from src.models.station import ConnectorStatus, LoadPoint
from src.services import control_loop, event_bus, repository
from src.services.errors import DomainError
from src.services.runtime import StationRuntime, get_runtime

AT_RISK_KWH = 0.1  # lịch giao thiếu hơn mức này so với kWh còn thiếu → nguy cơ trễ hạn (US5)


def build_overview(rt: StationRuntime) -> StationOverview:
    """S5 — dùng chung cho REST và bản tin station_snapshot của WebSocket."""
    state = rt.simulator.state()
    limit = state.available_power_kw
    grid_kw = state.total_power_kw / rt.config.power_conversion_efficiency
    at_risk: list[str] = []
    if rt.plan:
        progress = {s.booking_id: s.delivered_grid_kwh for s in state.sessions}
        for booking in rt.store.active_bookings():
            session = next((s for s in rt.plan.sessions if s.booking_id == booking.booking_id), None)
            planned = sum(x.power_kw for x in session.slots) * rt.plan.step_minutes / 60 if session else 0.0
            remaining = booking.energy.grid_energy_kwh - progress.get(booking.booking_id, 0.0)
            if remaining - planned > AT_RISK_KWH:
                at_risk.append(booking.booking_id)
    alerts = [f"Đầu nối {c.connector_id} đang lỗi" for c in state.connectors if c.status == ConnectorStatus.FAULT]
    nominal = rt.config.grid_input_limit_kw or rt.config.power_limit_kw
    if limit < nominal:
        alerts.append(f"Nguồn đang giảm: {limit:g}/{nominal:g} kW")
    return StationOverview(
        state=state,
        power_limit_kw=limit,
        utilization_pct=round(grid_kw / limit * 100, 1) if limit else 0.0,
        charging_count=sum(1 for c in state.connectors if c.power_kw > 0),
        queue_length=len(state.queue),
        at_risk_booking_ids=at_risk,
        alerts=alerts,
    )


def overview() -> StationOverview:
    """S5 — tải tổng so với giới hạn, số xe, lưới cột, cảnh báo, phiên có nguy cơ trễ hạn (US5)."""
    rt = get_runtime()
    rt.sync_clock()
    return build_overview(rt)


def load_history(hours: int) -> list[LoadPoint]:
    """S5 — biểu đồ tải có vạch giới hạn."""
    rt = get_runtime()
    return repository.list_load_points(rt.clock() - timedelta(hours=hours))


def connector_detail(connector_id: str) -> ConnectorDetail:
    """S5 — popup một cột: trạng thái, booking đang chiếm, lịch công suất, quyết định gần đây."""
    rt = get_runtime()
    rt.sync_clock()
    state = next((c for c in rt.simulator.state().connectors if c.connector_id == connector_id), None)
    if state is None:
        raise DomainError(ErrorCode.NOT_FOUND, f"Không có đầu nối {connector_id}")
    booking = repository.get_booking(state.booking_id) if state.booking_id else None
    plan = None
    if rt.plan and state.booking_id:
        plan = next((s for s in rt.plan.sessions if s.booking_id == state.booking_id), None)
    decisions = [d for d in repository.list_decisions(limit=200) if d.command.connector_id == connector_id][:20]
    return ConnectorDetail(state=state, booking=booking, plan=plan, recent_decisions=decisions)


def recent_events(limit: int) -> list[StationEvent]:
    """S5 — dòng "Sự kiện gần nhất"."""
    return repository.list_events(limit=limit)


def current_plan(on_date: date | None = None) -> SchedulePlan:
    """S6 — dữ liệu Gantt theo đầu nối. on_date=None = lịch hiện hành."""
    rt = get_runtime()
    plan = rt.plan or repository.latest_plan()
    if plan is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Chưa có lịch — bấm 'Lập lịch lại' để tính")
    if on_date is not None:
        tz = ZoneInfo(rt.config.timezone)
        if plan.horizon_start.astimezone(tz).date() != on_date:
            raise DomainError(ErrorCode.NOT_FOUND, f"Không có lịch cho ngày {on_date.isoformat()}")
    return plan


def list_bookings(status: BookingStatus | None = None) -> list[Booking]:
    """S6 — chi tiết hàng chờ ("#31 SoC 20% → 70%, trước 06:00"); SchedulePlan.queue chỉ có booking_id."""
    return repository.list_bookings(statuses=(status,) if status else None)


async def replan(operator_id: str) -> SchedulePlan:
    """S6 nút "Lập lịch lại" — control_loop.on_event(REPLAN_REQUESTED) ngay, không chờ bước LP."""
    rt = get_runtime()
    return await control_loop.on_event(
        StationEvent(type=EventType.REPLAN_REQUESTED, occurred_at=rt.clock(), detail=f"Vận hành {operator_id}"), rt
    )


async def manual_assign(booking_id: str, connector_id: str, operator_id: str) -> DecisionLogEntry:
    """S6 nút "Xếp thủ công" — tạo Command(source=OPERATOR) rồi đưa qua guard.dispatcher."""
    booking = repository.get_booking(booking_id)
    if booking is None or booking.status not in (BookingStatus.CONFIRMED, BookingStatus.QUEUED, BookingStatus.CHARGING):
        raise DomainError(ErrorCode.NOT_FOUND, "Không có booking đang hiệu lực này")
    rt = get_runtime()
    async with rt.lock:
        rt.sync_clock()
        state = rt.simulator.state()
        cmd = Command(
            type=CommandType.ASSIGN_CONNECTOR,
            connector_id=connector_id,
            booking_id=booking_id,
            source=CommandSource.OPERATOR,
            issued_by=operator_id,
            based_on_schedule_version=state.schedule_version,
            based_on_state_at=state.timestamp,
            created_at=rt.clock(),
            reason="Vận hành xếp thủ công (S6)",
        )
        entries = await dispatcher.submit(
            [cmd], control_loop.build_guard_context(rt, Role.OPERATOR), rt.simulator, rt.sinks
        )
    await event_bus.publish(
        StationEvent(
            type=EventType.REPLAN_REQUESTED, occurred_at=rt.clock(), booking_id=booking_id, detail="Sau xếp tay"
        )
    )
    return entries[0]
