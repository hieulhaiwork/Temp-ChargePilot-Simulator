"""charging_service (T2.2, T2.5), event bus + control loop (T2.6), từ chối phê duyệt (T3.2).

Control loop chạy trên runtime mô phỏng (runtime.build_sim_runtime) — cùng on_event với production.
charging_service chạy trên runtime live với đồng hồ cố định (không phụ thuộc giờ chạy test).
"""

import asyncio
import logging
from datetime import datetime, timedelta

import pytest

from src.guard import dispatcher
from src.models.charging import BookingStatus, ChargeMode, ChargeRequest, ConsentScope, StrategyName
from src.models.control import ApprovalStatus, Command, CommandSource, CommandType, Role
from src.models.events import EventType, StationEvent
from src.models.identity import UserRecord
from src.services import catalog, charging_service, control_loop, event_bus, repository, runtime
from src.services.runtime import build_sim_runtime, visit_of
from tests.factories import NOW, booking

T0 = datetime(2026, 11, 23, 18, 0, tzinfo=NOW.tzinfo)


@pytest.fixture
def live(monkeypatch, clean_db):
    monkeypatch.setattr(runtime, "_live_clock", lambda config: lambda: T0)
    runtime.reset_runtime()
    for uid in ("res-a", "res-b"):
        repository.upsert_user(
            UserRecord(user_id=uid, email=f"{uid}@example.invalid", role=Role.RESIDENT, display_name=uid, created_at=T0)
        )
    return runtime.get_runtime()


def _request(zone="AC", hours=10, soc_now=30, soc_target=80, model="VF8_NEW_2026") -> ChargeRequest:
    return ChargeRequest(
        vehicle_model=model,
        soc_now=soc_now,
        soc_target=soc_target,
        deadline=T0 + timedelta(hours=hours),
        mode=ChargeMode.WALK_IN,
        zone=zone,
    )


# ---- T2.2 / T2.5 charging_service --------------------------------------------------------


def test_infeasible_quote_has_alternative(live):
    """FR4. Không kịp hạn → feasible=False, ≥1 Alternative, reasons nêu lý do (do code sinh)."""
    proposal = charging_service.quote(_request(hours=1, soc_now=10, soc_target=100), "res-a")
    assert proposal.feasible is False
    assert proposal.alternatives
    assert any("Thiếu" in r for r in proposal.reasons)


def test_quote_does_not_reserve_anything(live):
    before = live.simulator.state()
    proposal = charging_service.quote(_request(), "res-a")
    assert proposal.feasible
    assert repository.list_bookings() == []
    assert live.simulator.state() == before  # không có Command nào tới trạm, version không đổi
    assert live.plan is None


@pytest.mark.parametrize(
    ("model", "zone", "expected"),
    [("VF3", "AC", 11), ("VF3", "DC", 24), ("VF9_123", "DC", 60), ("VF8_NEW_2026", "DC", 60)],
)
def test_booking_copies_vehicle_power_cap(model, zone, expected):
    """Booking.max_charge_power_kw = min(cổng tốt nhất của vùng, giới hạn của xe) — code tính lúc đặt."""
    vehicle = catalog.get_vehicle(model)
    cap = charging_service.vehicle_power_cap(catalog.load_station_config(), _request(zone=zone, model=model), vehicle)
    assert cap == expected


async def test_explanation_comes_from_decision_log(live):
    """US3. Lịch bị đổi do nguồn giảm → explain trích lệnh EMERGENCY từ decision log, không suy diễn."""
    booking_ = await charging_service.book(_request(zone="DC", hours=2, soc_now=20), "res-a")
    from src.models.simulation import Incident, IncidentType
    from src.services import simulation_service

    await simulation_service.inject_incident(Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=20))
    facts = charging_service.explain("res-a")
    assert booking_.booking_id in facts[0]
    assert facts[0].startswith(f"Mã đặt lịch {booking_.booking_id}:")
    assert any("emergency" in f for f in facts)
    assert charging_service.explain("res-b") == ["Bạn chưa có lịch sạc nào đang hiệu lực."]


async def test_new_booking_id_uses_readable_cp_code(live):
    import re

    booking_ = await charging_service.book(_request(zone="DC", hours=2, soc_now=20), "res-a")
    assert re.fullmatch(r"CP-[2-9A-HJ-NP-Z]{6}", booking_.booking_id)


async def test_session_view_estimates_soc_from_delivered_energy(live):
    booking_ = await charging_service.book(_request(zone="DC", hours=2, soc_now=20), "res-a")
    view0 = charging_service.session_view("res-a")
    assert view0.booking.booking_id == booking_.booking_id
    assert view0.soc_estimate == 20
    live.simulator.step(10)
    view = charging_service.session_view("res-a")
    assert view.progress.delivered_grid_kwh > 0
    assert 20 < view.soc_estimate <= 80


# ---- T2.6 event bus + control loop -------------------------------------------------------


async def test_failing_handler_does_not_drop_event_for_others(caplog):
    seen = []

    async def broken(event):
        raise RuntimeError("boom")

    async def ok(event):
        seen.append(event.type)

    event_bus.clear()
    event_bus.subscribe(None, broken)
    event_bus.subscribe(EventType.TICK, ok)
    event_bus.subscribe(EventType.BOOKING_CREATED, ok)
    with caplog.at_level(logging.ERROR):
        await event_bus.publish(StationEvent(type=EventType.TICK, occurred_at=NOW))
    event_bus.clear()
    assert seen == [EventType.TICK]
    assert "FAILED" in caplog.text


def _sim_runtime():
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(NOW.date(), scenario.start_time, tzinfo=NOW.tzinfo)
    return build_sim_runtime(scenario, StrategyName.SIM_M3A, config, tariff, start)


async def test_every_event_type_triggers_replan():
    """FR8. on_event với từng EventType → mỗi lần một SchedulePlan, version tăng đúng 1."""
    rt = _sim_runtime()
    b = booking("b1", hours=10, now=rt.clock())
    rt.store.save_booking(b)
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    versions = []
    for event_type in EventType:
        event = StationEvent(type=event_type, occurred_at=rt.clock())
        if event_type == EventType.POWER_LIMIT_CHANGED:
            event = event.model_copy(update={"new_power_limit_kw": 106})
        versions.append((await control_loop.on_event(event, rt)).version)
    assert versions == list(range(versions[0], versions[0] + len(EventType)))


async def test_background_loop_runs_station_without_any_request(clean_db):
    """ADR-007: bật vòng nền → trạm tự chạy theo thời gian: đồng hồ simulator tiến và có TICK để tính lại lịch."""
    rt = _sim_runtime()
    started = rt.simulator.now
    t = {"now": rt.clock()}

    def clock():
        t["now"] += timedelta(minutes=20)
        return t["now"]

    rt.clock = clock
    stop, ticks = asyncio.Event(), []

    async def on_tick(event):
        ticks.append(event)
        stop.set()

    event_bus.clear()
    event_bus.subscribe(EventType.TICK, on_tick)
    try:
        await asyncio.wait_for(control_loop.run_forever(stop, rt), timeout=15)
    finally:
        event_bus.clear()
    assert ticks
    assert rt.simulator.now > started


async def test_concurrent_events_are_serialized():
    rt = _sim_runtime()
    e = StationEvent(type=EventType.TICK, occurred_at=rt.clock())
    p1, p2 = await asyncio.gather(control_loop.on_event(e, rt), control_loop.on_event(e, rt))
    assert p1.version != p2.version


async def test_only_first_step_becomes_commands():
    """Receding horizon: diff_commands chỉ sinh lệnh cho bước t=0 (gán cổng + 1 lệnh công suất).

    Planning Core (M3a) chỉ trả bước hiện tại — LP backend cũ trả 96 bước (đã xoá, ADR-019 Phase 3)."""
    rt = _sim_runtime()
    b = booking("d1", zone="DC", kwh=40, hours=2, now=rt.clock())
    rt.store.save_booking(b)
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    ctx = control_loop.build_planning_context(rt)
    plan = rt.scheduler.plan(ctx)
    commands = control_loop.diff_commands(None, plan, ctx.state)
    assert [c.type for c in commands] == [CommandType.ASSIGN_CONNECTOR, CommandType.SET_POWER]
    first = next(s for s in plan.sessions if s.booking_id == "d1").slots[0]
    assert commands[1].power_kw == pytest.approx(first.power_kw, abs=1e-3)
    assert all(c.based_on_schedule_version == ctx.state.schedule_version for c in commands)


async def test_benchmark_runtime_applies_plan_through_guard():
    """Benchmark đi đúng đường Guard: sau on_event xe được cắm và cấp điện, tổng ≤ ngân sách."""
    rt = _sim_runtime()
    for i in range(3):
        b = booking(f"d{i}", zone="DC", kwh=40, hours=2, now=rt.clock())
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    st = rt.simulator.state()
    assert sum(1 for c in st.connectors if c.booking_id) == 2 and st.queue == ["d2"]
    assert 0 < st.total_power_kw <= 78 + 1e-6
    assert rt.store.get_booking("d2").status == BookingStatus.QUEUED


async def test_rejected_adjustment_is_not_proposed_again(live):
    """AC4. Cư dân từ chối → booking vào hard_consent_booking_ids, vòng tính lại không hỏi lại đúng lệnh đó."""
    repository.upsert_user(
        repository.get_user("res-a").model_copy(update={"consent": ConsentScope(allow_power_reduction=False)})
    )
    booking_ = await charging_service.book(_request(zone="DC", hours=2, soc_now=20), "res-a")
    state = live.simulator.state()
    conn = next(c for c in state.connectors if c.booking_id == booking_.booking_id)
    cut = Command(
        type=CommandType.SET_POWER,
        connector_id=conn.connector_id,
        power_kw=10,
        booking_id=booking_.booking_id,
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=state.schedule_version,
        based_on_state_at=state.timestamp,
        created_at=state.timestamp,
    )
    entry = (await dispatcher.submit([cut], control_loop.build_guard_context(live, None), live.simulator, live.sinks))[
        0
    ]
    decided = await control_loop.resolve_approval(entry.approval_id, "reject", "res-a", actor_role=Role.RESIDENT)
    assert decided.status == ApprovalStatus.REJECTED
    assert booking_.booking_id in control_loop.build_planning_context(live).hard_consent_booking_ids
    assert repository.list_approvals(status=ApprovalStatus.PENDING) == []
    held = control_loop._filter_held(live, [cut])
    assert held == []
    assert next(c for c in live.simulator.state().connectors if c.connector_id == conn.connector_id).power_kw > 10
