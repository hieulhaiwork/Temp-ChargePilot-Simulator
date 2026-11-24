"""Gate 3 (AI-4.2A WP3.1) fail-before / pass-after regression tests for runtime fork & admission readiness."""

from datetime import datetime

import pytest

pytest.importorskip("ev2gym")

from src.models.charging import StrategyName  # noqa: E402
from src.models.events import EventType, StationEvent  # noqa: E402
from src.services import admission, catalog, control_loop  # noqa: E402
from src.services.runtime import build_sim_runtime, fork_runtime, visit_of  # noqa: E402
from tests.factories import VN, booking  # noqa: E402


async def _build_runtime_with_queued_vehicle():
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=VN)
    rt = build_sim_runtime(scenario, StrategyName.SIM_M3A, config, tariff, start)
    queued = booking("dc-q1", zone="DC", kwh=25, hours=2.0, now=rt.clock())
    rt.store.save_booking(queued)
    rt.simulator.upsert_vehicle(visit_of(queued, rt.clock()))
    return rt


async def test_fork_runtime_inherits_pending_safety_and_suppresses_normal_dispatch():
    rt = await _build_runtime_with_queued_vehicle()
    hard_event = StationEvent(
        event_id="hard-pending-1",
        type=EventType.HARD_LIMIT_VIOLATED,
        occurred_at=rt.clock(),
        detail="Synthetic unresolved unattributed vehicle fault",
        violation_kinds=["charging_model"],
        violation_booking_ids=[],
    )
    rt.queue_events([hard_event])
    assert rt.has_pending_safety() is True

    frt = fork_runtime(rt, list(rt.store.active_bookings()))
    assert frt.has_pending_safety() is True

    # Normal TICK on fork must suppress non-safety commands just like live runtime.
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=frt.clock()), frt)
    assert frt.simulator.queue.sessions["dc-q1"].connector is None
    assert frt.advance_clock() == []


async def test_admission_fingerprint_reflects_pending_safety_transition():
    rt = await _build_runtime_with_queued_vehicle()
    fp_clean = rt.admission_fingerprint()

    hard_event = StationEvent(
        event_id="hard-pending-fp",
        type=EventType.HARD_LIMIT_VIOLATED,
        occurred_at=rt.clock(),
        detail="Synthetic unresolved unattributed vehicle fault",
        violation_kinds=["charging_model"],
        violation_booking_ids=[],
    )
    rt.queue_events([hard_event])
    fp_pending = rt.admission_fingerprint()
    assert fp_pending != fp_clean

    rt.acknowledge_safety([hard_event])
    assert rt.admission_fingerprint() == fp_clean


async def test_admission_evaluate_does_not_promise_allocation_while_hard_safety_pending():
    rt = await _build_runtime_with_queued_vehicle()
    hard_event = StationEvent(
        event_id="hard-pending-adm",
        type=EventType.HARD_LIMIT_VIOLATED,
        occurred_at=rt.clock(),
        detail="Synthetic unresolved unattributed vehicle fault",
        violation_kinds=["charging_model"],
        violation_booking_ids=[],
    )
    rt.queue_events([hard_event])
    assert rt.has_pending_safety() is True

    candidate = booking("cand-dc", zone="DC", kwh=20, hours=2.0, now=rt.clock())
    quoted = await admission.evaluate(rt, candidate)
    assert quoted.plugged_at is None
    assert quoted.delivered_kwh == 0.0
    assert quoted.unmet_kwh > 0.05
