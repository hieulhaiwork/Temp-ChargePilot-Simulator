"""Final Acceptance §1 — giao sự kiện an toàn (P0).

1. Mọi consumer gọi `rt.sync_clock()` (quote, session_view, queue_status, overview, …) KHÔNG bỏ sự kiện trạm: sự kiện
   vào `rt.outbox` và được giao cho control_loop (`deliver_pending`) — `hard_limit_violated` tới được fail-safe.
2. Catch-up nhiều phút dừng ĐÚNG ở phút vi phạm cứng; fail-safe chạy trước khi tích phân các phút còn lại.
3. `curtail_to_hard_limits` đưa trạm về trong MỌI trần (lưới / vùng / tủ).
4. Lỗi charging model (giảm tải tổng không sửa được) ⇒ ngắt công suất cổng của xe lỗi, giữ an toàn, ghi loại vi phạm
   trong sự kiện + DecisionTrace; các xe khác không bị co.
"""

import asyncio
import concurrent.futures
import dataclasses
from datetime import datetime, timedelta

import pytest

pytest.importorskip("ev2gym")

from src.guard import emergency  # noqa: E402
from src.guard.physical import adapter as physical  # noqa: E402
from src.models.charging import StrategyName  # noqa: E402
from src.models.control import CommandSource, CommandType, Role  # noqa: E402
from src.models.events import EventType, StationEvent, ViolationKind  # noqa: E402
from src.models.identity import UserRecord  # noqa: E402
from src.services import catalog, charging_service, control_loop, repository, runtime, station_service  # noqa: E402
from src.services.runtime import build_sim_runtime, visit_of  # noqa: E402
from tests.factories import NOW, VN, booking  # noqa: E402
from tests.factories import state as station_state  # noqa: E402

T0 = datetime(2026, 11, 23, 18, 0, tzinfo=NOW.tzinfo)
SILENT_LIMIT_KW = 30.0


def _fleet(now):
    return (
        booking("dc-a", zone="DC", kwh=40, hours=1.5, now=now),
        booking("dc-b", zone="DC", kwh=40, hours=1.5, now=now),
        booking("ac-a", zone="AC", kwh=20, hours=3, now=now),
    )


async def _wait_deliveries(rt) -> None:
    for future in list(rt.deliveries):
        if isinstance(future, concurrent.futures.Future):
            await asyncio.wrap_future(future)
        else:
            await future


# ---- 1. đường đọc → fail-safe (runtime live, đồng hồ điều khiển được) ----------------------------------------


@pytest.fixture
def live(monkeypatch, clean_db):
    clock = {"now": T0}
    monkeypatch.setattr(runtime, "_live_clock", lambda config: lambda: clock["now"])
    runtime.reset_runtime()
    rt = runtime.get_runtime()
    assert rt.config.guard.after_apply_failsafe is True  # config vận hành (Final Acceptance §1.1)
    return rt, clock


async def _charging_live(rt):
    for b in _fleet(rt.clock()):
        _save(b)
        rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    assert rt.simulator.state().total_power_kw / rt.config.power_conversion_efficiency > SILENT_LIMIT_KW


def _save(b) -> None:
    repository.upsert_user(
        UserRecord(
            user_id=b.resident_id,
            email=f"{b.resident_id}@example.invalid",
            role=Role.RESIDENT,
            display_name=b.resident_id,
            created_at=T0,
        )
    )
    repository.save_booking(b)


def _nearly_full(now):
    """Xe AC 78 → 80 %, hạn 1 h: sạc xong trong vài phút (CHARGE_COMPLETED trước giờ rời)."""
    b = booking("ac-s", zone="AC", kwh=2, hours=1, now=now)
    return b.model_copy(update={"request": b.request.model_copy(update={"soc_now": 78})})


def _emergency_decisions():
    return [d for d in repository.list_decisions(limit=500) if d.command.source == CommandSource.EMERGENCY]


@pytest.mark.parametrize(
    "read",
    [
        lambda: charging_service.queue_status("res-nobody"),
        lambda: charging_service.session_view("res-dc-a"),
        lambda: station_service.overview(),
    ],
    ids=["queue_status", "session_view", "overview"],
)
async def test_event_from_a_read_path_reaches_the_failsafe(live, read):
    rt, clock = live
    await _charging_live(rt)
    sim = rt.simulator
    sim.available_power_kw = SILENT_LIMIT_KW  # nguồn tụt "im lặng": không có POWER_LIMIT_CHANGED
    start, before = sim.minute, sim.applied_constraint_violation_count
    clock["now"] = T0 + timedelta(minutes=5)

    read()  # đường đọc: tiến đồng hồ → vi phạm → sự kiện vào outbox → lên lịch giao cho control_loop
    assert sim.minute == start + 1, "catch-up phải dừng ở phút vi phạm đầu tiên"
    assert [e.type for e in rt.outbox] == [EventType.HARD_LIMIT_VIOLATED]
    assert rt.deliveries, "sự kiện của đường đọc phải được đẩy tới control_loop"
    await _wait_deliveries(rt)

    assert not rt.outbox
    emergency_entries = _emergency_decisions()
    assert emergency_entries and all(d.executed for d in emergency_entries)
    assert sim.minute == start + 5  # các phút còn lại chạy SAU khi fail-safe đã giảm tải
    assert sim.applied_constraint_violation_count == before + 1  # chỉ đúng phút bị phát hiện
    assert sim.state().total_power_kw / rt.config.power_conversion_efficiency <= SILENT_LIMIT_KW + 1e-6
    kinds = {e.type.value for e in repository.list_events(limit=50)}
    assert EventType.HARD_LIMIT_VIOLATED.value in kinds


async def test_event_from_a_threadpool_read_path_reaches_the_failsafe(live):
    """Router đồng bộ chạy trong threadpool: giao về vòng sự kiện của runtime bằng run_coroutine_threadsafe."""
    rt, clock = live
    await _charging_live(rt)
    assert rt.loop is asyncio.get_running_loop()
    rt.simulator.available_power_kw = SILENT_LIMIT_KW
    clock["now"] = T0 + timedelta(minutes=3)
    await asyncio.to_thread(charging_service.queue_status, "res-nobody")
    await _wait_deliveries(rt)
    assert _emergency_decisions()
    assert rt.simulator.applied_constraint_violation_count == 1


async def test_charge_completed_from_a_read_path_is_not_dropped(live):
    rt, clock = live
    short = _nearly_full(rt.clock())
    _save(short)
    rt.simulator.upsert_vehicle(visit_of(short, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    clock["now"] = T0 + timedelta(minutes=50)
    charging_service.queue_status("res-nobody")
    assert EventType.CHARGE_COMPLETED in {e.type for e in rt.outbox}
    await _wait_deliveries(rt)
    assert not rt.outbox
    assert EventType.CHARGE_COMPLETED.value in {e.type.value for e in repository.list_events(limit=100)}


async def test_pending_events_are_taken_by_the_next_on_event_without_duplicates(live):
    """Không vòng sự kiện nào nhận (deliver=None): outbox chờ on_event kế tiếp; sự kiện truyền lại không bị ghi hai lần."""
    rt, clock = live
    rt.deliver = None
    short = _nearly_full(rt.clock())
    _save(short)
    rt.simulator.upsert_vehicle(visit_of(short, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    clock["now"] = T0 + timedelta(minutes=50)
    events = rt.sync_clock()
    assert events and list(rt.outbox) == events
    await control_loop.on_minute(rt, events)  # người gọi tự giao (như test luồng) — outbox bỏ trùng theo event_id
    assert not rt.outbox
    recorded = [e.event_id for e in repository.list_events(limit=200)]
    assert len(recorded) == len(set(recorded))
    assert {e.event_id for e in events} <= set(recorded)


# ---- 2. catch-up dừng ở phút vi phạm ------------------------------------------------------------------------


async def _sim_runtime(failsafe: bool):
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    config = config.model_copy(update={"guard": config.guard.model_copy(update={"after_apply_failsafe": failsafe})})
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=VN)
    rt = build_sim_runtime(scenario, StrategyName.SIM_M3A, config, tariff, start)
    for b in _fleet(rt.clock()):
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    await control_loop.on_minute(rt, rt.simulator.step(1))
    return rt


async def test_multi_minute_catch_up_stops_at_the_violation_minute():
    rt = await _sim_runtime(failsafe=True)
    sim = rt.simulator
    sim.available_power_kw = SILENT_LIMIT_KW
    start, before = sim.minute, sim.applied_constraint_violation_count
    events = sim.step(10)
    assert sim.minute == start + 1  # 9 phút còn lại KHÔNG bị tích phân với setpoint đang vi phạm
    assert sim.applied_constraint_violation_count == before + 1
    (violation,) = [e for e in events if e.type == EventType.HARD_LIMIT_VIOLATED]
    assert violation.violation_kinds == [ViolationKind.AGGREGATE_POWER]
    assert violation.occurred_at == sim.now

    # Không ai xử lý (fail-safe chưa chạy) ⇒ lần sau cùng vi phạm: không dừng lại nữa (đồng hồ không bị treo),
    # vẫn phát sự kiện để fail-safe thử lại.
    events = sim.step(3)
    assert sim.minute == start + 4
    assert [e.type for e in events].count(EventType.HARD_LIMIT_VIOLATED) == 1


async def test_catch_up_without_failsafe_keeps_old_behaviour():
    rt = await _sim_runtime(failsafe=False)
    sim = rt.simulator
    sim.available_power_kw = SILENT_LIMIT_KW
    start, before = sim.minute, sim.applied_constraint_violation_count
    events = sim.step(10)
    assert sim.minute == start + 10
    assert sim.applied_constraint_violation_count == before + 10
    assert not [e for e in events if e.type == EventType.HARD_LIMIT_VIOLATED]


async def test_failsafe_runs_before_the_clock_advances_in_on_event():
    """Sự kiện vi phạm tới on_event ⇒ giảm tải TRƯỚC `advance_clock`; phút kế tiếp không vi phạm."""
    rt = await _sim_runtime(failsafe=True)
    sim = rt.simulator
    sim.available_power_kw = SILENT_LIMIT_KW
    events = sim.step(1)
    order: list[str] = []
    real_advance, real_failsafe = rt.advance_clock, control_loop._failsafe

    def advance():
        order.append("advance")
        return real_advance()

    async def failsafe(*args, **kwargs):
        order.append("failsafe")
        return await real_failsafe(*args, **kwargs)

    rt.advance_clock = advance
    control_loop._failsafe = failsafe
    try:
        await control_loop.on_minute(rt, events)
    finally:
        control_loop._failsafe = real_failsafe
    assert order[:2] == ["failsafe", "advance"]
    after = sim.applied_constraint_violation_count
    sim.step(5)
    assert sim.applied_constraint_violation_count == after


# ---- 3. curtail_to_hard_limits về trong mọi trần ----------------------------------------------------------------


def _powered(st, power: dict[str, float]):
    connectors = [c.model_copy(update={"power_kw": power.get(c.connector_id, 0.0)}) for c in st.connectors]
    return st.model_copy(update={"connectors": connectors})


def _with(config, **update):
    return config.model_copy(update=update)


@pytest.mark.parametrize("tier", ["grid", "zone", "cabinet"])
def test_curtail_to_hard_limits_brings_every_tier_back_within_its_cap(tier):
    config = catalog.load_station_config()
    plugged = {"AC-01-1": "ac-a", "AC-02-1": "ac-b", "DC-01-1": "dc-a", "DC-01-2": "dc-b"}
    power = {"AC-01-1": 11.0, "AC-02-1": 11.0, "DC-01-1": 60.0, "DC-01-2": 60.0}
    available = 200.0
    if tier == "grid":
        available = SILENT_LIMIT_KW
    elif tier == "zone":
        config = _with(config, physical_zone_cap_kw={"AC": 22.0, "DC": 80.0}, grid_input_limit_kw=200.0)
    else:
        cabinets = [
            c.model_copy(update={"output_limit_kw": 70.0}) if c.cabinet_id == "DC-01" else c for c in config.cabinets
        ]
        config = _with(config, cabinets=cabinets, grid_input_limit_kw=200.0)
    st = _powered(station_state(plugged, available=available), power)
    occupants = {c.connector_id: c.booking_id for c in st.connectors}
    assert physical.check_site_allocation(config, st, power, occupants) is not None, tier

    commands = emergency.curtail_to_hard_limits(st, config, NOW, tier)
    after = dict(power)
    for cmd in commands:
        assert cmd.source == CommandSource.EMERGENCY and cmd.type == CommandType.SET_POWER
        assert cmd.power_kw <= power[cmd.connector_id]
        after[cmd.connector_id] = cmd.power_kw
    assert physical.check_site_allocation(config, st, after, occupants) is None, tier


# ---- 4. lỗi charging model: giảm tải tổng không sửa được -----------------------------------------------------


async def test_charging_model_fault_is_isolated_not_curtailed():
    rt = await _sim_runtime(failsafe=True)
    sim = rt.simulator
    real_step = sim.adapter.step

    def broken_step(vehicle_id, cabinet, output_kw, minutes):
        delivered = real_step(vehicle_id, cabinet, output_kw, minutes)
        if vehicle_id == "dc-a" and output_kw > 0:
            return dataclasses.replace(delivered, battery_kwh=delivered.battery_kwh * 3)  # năng lượng ≠ SOC: model lỗi
        return delivered

    sim.adapter.step = broken_step
    before_power = {c.connector_id: c.power_kw for c in sim.state().connectors}
    dc_a_port = next(c.connector_id for c in sim.state().connectors if c.booking_id == "dc-a")
    start = sim.minute
    events = sim.step(5)
    assert sim.minute == start + 1  # dừng ở phút vi phạm
    (violation,) = [e for e in events if e.type == EventType.HARD_LIMIT_VIOLATED]
    assert violation.violation_kinds == [ViolationKind.CHARGING_MODEL]
    assert violation.violation_booking_ids == ["dc-a"]
    # Giảm tải tổng không giúp gì: trạm vẫn trong mọi trần tổng
    assert emergency.curtail_to_hard_limits(sim.state(), rt.config, rt.clock()) == []

    decisions: list = []
    original = rt.sinks.log_decision
    rt.sinks = rt.sinks.__class__(
        log_decision=lambda e: (decisions.append(e), original(e)),
        save_approval=rt.sinks.save_approval,
        notify=rt.sinks.notify,
    )
    await control_loop.on_minute(rt, events)
    stops = [d for d in decisions if d.command.source == CommandSource.EMERGENCY]
    assert [(d.command.connector_id, d.command.power_kw, d.executed) for d in stops] == [(dc_a_port, 0.0, True)]
    assert "charging_model" in stops[0].command.reason
    assert rt.safety_hold_booking_ids == {"dc-a"}
    trace = rt.open_trace["trace"]
    assert trace["safety"]["hard_limit_violations"][0]["kinds"] == ["charging_model"]
    assert trace["safety"]["held_booking_ids"] == ["dc-a"]
    others = {c.connector_id: c.power_kw for c in sim.state().connectors if c.booking_id not in (None, "dc-a")}
    assert all(kw > 0 for kw in others.values()) and set(others) <= set(before_power)

    # Lỗi đã cô lập: các phút sau không vi phạm, các lần tính lại không cấp lại công suất cho xe lỗi
    after = sim.applied_constraint_violation_count
    for _ in range(20):
        await control_loop.on_minute(rt, sim.step(1))
    assert sim.applied_constraint_violation_count == after
    assert next(c.power_kw for c in sim.state().connectors if c.booking_id == "dc-a") == 0.0
    closed = rt.recorder.decision_traces
    assert any(d["kind"] == "charging_model" for t in closed for d in t["applied"]["hard_violation_details"])
