"""Vòng điều khiển MPC — chạy ngay khi có sự kiện, và theo bước LP nếu bật vòng nền (FR6, FR8).

    StationEvent ─► [POWER_LIMIT_CHANGED: guard.emergency.curtail_to_limit → dispatcher.submit NGAY]
                 ─► build_planning_context(rt) ─► rt.scheduler.plan() → SchedulePlan v+1
                 ─► diff_commands() → Command[] (chỉ bước t=0 — receding horizon)
                 ─► guard.dispatcher.submit(commands, ctx, rt.simulator, rt.sinks)
                 ─► lưu lịch + WebSocket: schedule_changed / command_blocked / approval_request

Hai cách on_event được gọi (ADR-007):
  1. NGAY TRONG REQUEST: service phát sự kiện qua event_bus.publish → on_event chạy xong rồi
     request mới trả. Đặt lịch xong là có lịch mới, không phụ thuộc vòng nền (Render free ngủ).
  2. Vòng nền run_forever: chỉ lo việc theo THỜI GIAN (bước simulator, TICK, hết hạn phê duyệt).
     Bật bằng CONTROL_LOOP_ENABLED, mặc định tắt.

Benchmark (simulation_service) gọi CÙNG on_event với runtime mô phỏng — số đo offline phản
ánh đúng code production (MT4, MT5).

Owner: TV3 (khung) + TV1 (gọi optimizer). Task: T2.6; phê duyệt T3.2; đo MT5 ở T3.7.
"""

import asyncio
import logging
import time
from datetime import timedelta
from typing import Literal

from src.guard import approval as approval_rules
from src.guard import dispatcher, emergency
from src.guard.rules import GuardContext
from src.models.api import ErrorCode, Notification, NotificationKind
from src.models.charging import BookingStatus, SchedulePlan
from src.models.control import Approval, ApprovalStatus, Command, CommandSource, CommandType, DecisionLogEntry, Role
from src.models.events import EventType, StationEvent, WsMessage, WsMessageType
from src.models.station import LoadPoint, StationState
from src.optimizer.base import PlanningContext
from src.services import solver
from src.services.errors import DomainError
from src.services.runtime import StationRuntime

logger = logging.getLogger(__name__)

POWER_TOL_KW = 0.01  # đổi công suất nhỏ hơn mức này không sinh lệnh (tránh lệnh rác)


def _ws(kind: WsMessageType, payload, rt: StationRuntime) -> WsMessage:
    return WsMessage(type=kind, payload=payload.model_dump(mode="json"), sent_at=rt.clock())


async def on_event(event: StationEvent, rt: StationRuntime) -> SchedulePlan:
    """Tính lại lịch cho một sự kiện, tuần tự dưới rt.lock. Mục tiêu p95 ≤ 2 s (MT5).

    Việc nặng (solver) chạy trên thread solver duy nhất (services/solver.py) để không chặn WebSocket.
    """
    async with rt.lock:
        started = time.perf_counter()
        side_events = rt.sync_clock()
        for e in (*side_events, event):
            rt.store.record_event(e)
            await rt.sinks.notify(_ws(WsMessageType.EVENT, e, rt), None)
        if event.type == EventType.POWER_LIMIT_CHANGED and event.new_power_limit_kw is not None:
            await _emergency(rt, event.new_power_limit_kw)
        _sync_booking_status(rt, (*side_events, event))

        ctx = build_planning_context(rt)
        plan = await solver.run_async(rt.scheduler.plan, ctx)
        version = max(rt.plan.version if rt.plan else 0, ctx.state.schedule_version) + 1
        plan = plan.model_copy(update={"version": version})
        commands = _filter_held(rt, diff_commands(rt.plan, plan, ctx.state))
        if commands:
            await dispatcher.submit(
                commands,
                build_guard_context(rt, None),
                rt.simulator,
                rt.sinks,
                approval_ttl_minutes=rt.config.guard.approval_ttl_minutes,
            )
        rt.plan = plan
        rt.store.save_plan(plan)
        _sync_booking_status(rt, ())
        _record_load(rt)
        rt.recorder.replan_durations_s.append(time.perf_counter() - started)
        await rt.sinks.notify(_ws(WsMessageType.SCHEDULE_CHANGED, plan, rt), None)
        if rt.live:
            from src.services import station_service  # tránh vòng import lúc nạp module

            await rt.sinks.notify(_ws(WsMessageType.STATION_SNAPSHOT, station_service.build_overview(rt), rt), None)
        return plan


async def run_forever(stop: asyncio.Event, rt: StationRuntime) -> None:
    """Vòng nền: simulator.step, phát TICK mỗi planning_step_minutes, approval.expire_overdue — tới khi `stop` được set."""
    from src.config import get_settings
    from src.services import event_bus

    tick_every = timedelta(minutes=rt.config.optimizer.planning_step_minutes)
    last_tick = rt.clock()
    sleep_s = min(max(60 / get_settings().sim_time_scale, 1.0), 30.0)
    while not stop.is_set():
        try:
            async with rt.lock:
                events = rt.sync_clock()
            for event in events:
                await event_bus.publish(event)
            now = rt.clock()
            if not events and now - last_tick >= tick_every:
                await event_bus.publish(StationEvent(type=EventType.TICK, occurred_at=now))
                last_tick = now
            elif events:
                last_tick = now
            expire_overdue_approvals(rt)
        except Exception:
            logger.exception("control_loop.run_forever: lỗi một vòng, tiếp tục")
        try:
            await asyncio.wait_for(stop.wait(), timeout=sleep_s)
        except TimeoutError:
            pass


def expire_overdue_approvals(rt: StationRuntime) -> list[Approval]:
    """AC4: yêu cầu quá hạn → EXPIRED, ghi nhật ký executed=False — KHÔNG thực thi. Vòng nền gọi mỗi lượt."""
    from src.services import repository

    now = rt.clock()
    expired = approval_rules.expire_overdue(repository.overdue_approvals(now), now)
    for approval in expired:
        repository.save_approval(approval)
        repository.append_decision(
            DecisionLogEntry(
                timestamp=now,
                command=approval.command,
                verdict=approval.verdict,
                approval_id=approval.approval_id,
                executed=False,
                note="Hết hạn phê duyệt — không thực thi (AC4)",
            )
        )
    return expired


async def resolve_approval(
    approval_id: str,
    decision: Literal["approve", "reject"],
    actor_id: str,
    rt: StationRuntime | None = None,
    actor_role: Role | None = None,
) -> Approval:
    """Xử lý quyết định Đồng ý / Từ chối của cư dân (S4) hoặc vận hành (S7) — AC4.

    approve → guard.approval.decide → guard.dispatcher.execute_approved (kiểm Guard lần 2).
    reject  → ghi nhật ký executed=False → on_event(REPLAN_REQUESTED), với booking đó nằm trong
              PlanningContext.hard_consent_booking_ids để không đề xuất lại đúng lệnh cũ.
    rt=None nghĩa là runtime live (services.runtime.get_runtime()). Router gọi hàm này, KHÔNG
    gọi thẳng src.guard (tests/test_architecture.py). actor_role do router truyền (lấy từ token).
    """
    from src.services import repository
    from src.services.runtime import get_runtime

    rt = rt or get_runtime()
    pending = repository.get_approval(approval_id)
    if pending is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Không có yêu cầu phê duyệt này")
    if actor_role is None:
        user = repository.get_user(actor_id)
        if user is None:
            raise DomainError(ErrorCode.FORBIDDEN, "Không xác định được vai trò người duyệt")
        actor_role = user.role
    if actor_role == Role.RESIDENT and pending.requested_from != actor_id:
        raise DomainError(ErrorCode.NOT_FOUND, "Không có yêu cầu phê duyệt này")  # không lộ approval của người khác
    decided = approval_rules.decide(pending, decision, actor_id, actor_role, rt.clock())
    repository.save_approval(decided)
    if decided.status == ApprovalStatus.APPROVED:
        async with rt.lock:
            rt.sync_clock()
            await dispatcher.execute_approved(decided, build_guard_context(rt, None), rt.simulator, rt.sinks)
    else:
        repository.append_decision(
            DecisionLogEntry(
                timestamp=rt.clock(),
                command=decided.command,
                verdict=decided.verdict,
                approval_id=decided.approval_id,
                approved_by=actor_id,
                executed=False,
                note="Bị từ chối — không thực thi (AC4)",
            )
        )
        if decided.command.booking_id:
            rt.rejected_booking_ids.add(decided.command.booking_id)
    await on_event(StationEvent(type=EventType.REPLAN_REQUESTED, occurred_at=rt.clock(), detail="Sau phê duyệt"), rt)
    return decided


def build_planning_context(rt: StationRuntime) -> PlanningContext:
    """Gom dữ kiện cho optimizer: state, booking còn hiệu lực, giá, dự báo F6 (chỉ chiến lược C — đang hoãn)."""
    return PlanningContext(
        now=rt.clock(),
        state=rt.simulator.state(),
        bookings=tuple(rt.store.active_bookings()),
        config=rt.config,
        tariff=rt.tariff,
        departure_forecast=None,
        hard_consent_booking_ids=frozenset(rt.rejected_booking_ids),
        oracle_bookings=rt.oracle_bookings,
    )


def build_guard_context(rt: StationRuntime, actor_role: Role | None) -> GuardContext:
    """Gom dữ kiện cho 7 luật: state mới nhất, booking, lệnh gần đây. actor_role=None = hệ thống."""
    return GuardContext(
        now=rt.clock(),
        state=rt.simulator.state(),
        config=rt.config,
        actor_role=actor_role,
        bookings={b.booking_id: b for b in rt.store.active_bookings()},
        recent_commands=tuple(rt.recent_commands),
    )


def diff_commands(previous: SchedulePlan | None, new: SchedulePlan, state: StationState) -> list[Command]:
    """So lịch mới với trạng thái trạm → lệnh cho bước ĐẦU: ASSIGN_CONNECTOR rồi SET_POWER.

    Chỉ áp bước t=0 (receding horizon). Xe đang chờ chỉ được gán khi lịch cho nó cổng NGAY (không còn trong
    new.queue) và cổng đó đang trống. Công suất 0 = dừng (SET_POWER 0), nên luật anti_flapping vẫn áp.
    `previous` không dùng để quyết lệnh — trạng thái thật của trạm mới là gốc so sánh.
    """
    first_power = {
        s.booking_id: next((slot.power_kw for slot in s.slots if slot.start == new.horizon_start), 0.0)
        for s in new.sessions
    }
    planned_connector = {s.booking_id: s.connector_id for s in new.sessions if s.connector_id}
    occupant = {c.connector_id: c.booking_id for c in state.connectors}
    waiting = set(state.queue) - set(new.queue)

    def command(ctype: CommandType, connector_id: str, booking_id: str | None, power: float | None = None) -> Command:
        return Command(
            type=ctype,
            connector_id=connector_id,
            power_kw=power,
            booking_id=booking_id,
            source=CommandSource.OPTIMIZER,
            issued_by="optimizer",
            based_on_schedule_version=state.schedule_version,
            based_on_state_at=state.timestamp,
            created_at=state.timestamp,
            reason=f"Lịch v{new.version} ({new.strategy.value})",
        )

    commands: list[Command] = []
    for booking_id in sorted(waiting):
        connector_id = planned_connector.get(booking_id)
        if connector_id and occupant.get(connector_id) is None:
            commands.append(command(CommandType.ASSIGN_CONNECTOR, connector_id, booking_id))
            occupant[connector_id] = booking_id
    for conn in state.connectors:
        booking_id = occupant.get(conn.connector_id)
        desired = first_power.get(booking_id, 0.0) if booking_id else 0.0
        current = conn.power_kw if conn.booking_id == booking_id else 0.0
        if abs(desired - current) > POWER_TOL_KW:
            commands.append(command(CommandType.SET_POWER, conn.connector_id, booking_id, round(desired, 3)))
    return commands


# ---- nội bộ ------------------------------------------------------------------------------


async def _emergency(rt: StationRuntime, new_limit_kw: float) -> None:
    """AC5: hạ công suất NGAY, độc lập optimizer; báo cư dân SAU."""
    state = rt.simulator.state()
    commands = emergency.curtail_to_limit(state, new_limit_kw, rt.clock(), rt.config.power_conversion_efficiency)
    if not commands:
        return
    entries = await dispatcher.submit(commands, build_guard_context(rt, None), rt.simulator, rt.sinks)
    bookings = {b.booking_id: b for b in rt.store.active_bookings()}
    for entry in entries:
        booking = bookings.get(entry.command.booking_id or "")
        if not entry.executed or booking is None:
            continue
        note = Notification(
            notification_id=entry.entry_id,
            kind=NotificationKind.EMERGENCY_CURTAILMENT,
            title="Đã giảm công suất sạc do nguồn điện giảm",
            body=f"Công suất còn {entry.command.power_kw:g} kW. Lịch sẽ được tính lại để giữ cam kết nếu còn khả thi.",
            created_at=rt.clock(),
        )
        rt.store.add_notification(booking.resident_id, note)
        await rt.sinks.notify(_ws(WsMessageType.NOTIFICATION, note, rt), booking.resident_id)


def _filter_held(rt: StationRuntime, commands: list[Command]) -> list[Command]:
    """Bỏ lệnh của booking đang chờ phê duyệt (không hỏi lại liên tục) và lệnh cần duyệt của booking đã từ chối."""
    if not commands:
        return commands
    held = {a.command.booking_id for a in rt.store.pending_approvals() if a.command.booking_id}
    bookings = {b.booking_id: b for b in rt.store.active_bookings()}
    kept = []
    for cmd in commands:
        if cmd.booking_id in held:
            continue
        if cmd.booking_id in rt.rejected_booking_ids and approval_rules.requires_approval(
            cmd, bookings.get(cmd.booking_id)
        ):
            continue
        kept.append(cmd)
    return kept


def _sync_booking_status(rt: StationRuntime, events) -> None:
    """Trạng thái booking theo trạng thái vật lý của trạm: cắm → CHARGING, chờ → QUEUED, rời → COMPLETED."""
    state = rt.simulator.state()
    plugged = {c.booking_id: c.connector_id for c in state.connectors if c.booking_id}
    waiting = set(state.queue)
    departed = {e.booking_id for e in events if e.type == EventType.VEHICLE_DEPARTED and e.booking_id}
    present = {s.booking_id for s in state.sessions}
    now = rt.clock()
    for booking in rt.store.active_bookings():
        status, connector = booking.status, booking.connector_id
        if booking.booking_id in departed or (booking.booking_id not in present and booking.request.deadline <= now):
            status = BookingStatus.COMPLETED
        elif booking.booking_id in plugged:
            status, connector = BookingStatus.CHARGING, plugged[booking.booking_id]
        elif booking.booking_id in waiting:
            status = BookingStatus.QUEUED
        if rt.plan and booking.booking_id not in plugged:
            session = next((s for s in rt.plan.sessions if s.booking_id == booking.booking_id), None)
            connector = session.connector_id if session and session.connector_id else connector
        if (status, connector) != (booking.status, booking.connector_id):
            rt.store.save_booking(booking.model_copy(update={"status": status, "connector_id": connector}))


def _record_load(rt: StationRuntime) -> None:
    state = rt.simulator.state()
    rt.store.record_load(
        LoadPoint(
            timestamp=state.timestamp, total_power_kw=state.total_power_kw, power_limit_kw=state.available_power_kw
        )
    )
