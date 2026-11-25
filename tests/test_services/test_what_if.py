"""Gate 4 independent energy, deadline, safety, authorization and job probes."""

import asyncio
import threading
from dataclasses import replace
from datetime import timedelta

import pytest
from pydantic import ValidationError

from src.models.charging import StrategyName
from src.models.control import Role
from src.models.copilot import ActorContext
from src.models.events import EventType, StationEvent
from src.models.simulation import Incident, IncidentType
from src.models.simulation_core import LimitEvent
from src.models.station import StationConfig
from src.models.what_if import PATCH_ADAPTER, WhatIfJobStatus
from src.services import catalog, control_loop
from src.services.copilot import capture_atomic_snapshot
from src.services.copilot import jobs as jobs_module
from src.services.copilot.jobs import WhatIfCapacityError, WhatIfJobs
from src.services.copilot.snapshot import build_sandbox_runtime
from src.services.copilot.what_if import WhatIfForbiddenError, _prepare_patch, run_what_if
from src.services.runtime import build_sim_runtime, visit_of
from src.simulator.hybrid_station import HybridStation
from tests.factories import NOW, booking


def _rt(*, config=None):
    return build_sim_runtime(
        catalog.load_scenario("hybrid_evening"),
        StrategyName.SIM_B0,
        config or catalog.load_station_config(),
        catalog.load_tariff(),
        NOW,
    )


def _actor(rt, name="operator", role=Role.OPERATOR):
    return ActorContext(actor_id=name, station_id=rt.config.station_id, role=role)


def _add(rt, name="a", **kwargs):
    record = booking(name, now=rt.clock(), **kwargs)
    rt.store.save_booking(record)
    rt.simulator.upsert_vehicle(visit_of(record, rt.clock()))
    return record


async def _replan(rt):
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)


def _target(b, pct):
    return {"op": "revise_vehicle", "booking_id": b.booking_id, "target_soc": pct}


async def test_target_soc_oracle_compares_original_and_revised_sla():
    rt = _rt()
    b = _add(rt, hours=0.5)
    await _replan(rt)
    at = rt.clock()
    snap = await capture_atomic_snapshot(rt, horizon_minutes=35)
    operator = _actor(rt)
    res = await run_what_if(snap, operator, _target(b, 21))
    assert res.applied is False and res.status == "completed"
    (row,) = res.affected_vehicles
    cap = catalog.get_vehicle("VF8_NEW_2026").usable_capacity_kwh
    required = cap / 100
    # AC acceptance spreads this headroom over the first 15 minutes.
    # The 0.001 kW command quantum rounds down, so the next minute supplies the remainder.
    expected_minute = 16
    assert row.baseline_original.target_soc == row.patched_original.target_soc == 80
    assert row.patched_revised.target_soc == 21
    assert row.patched_revised.target_reached_at == at + timedelta(minutes=expected_minute)
    assert row.patched_revised.met_deadline is True
    assert row.patched_original.met_deadline is False
    assert row.patched_horizon_battery_kwh == pytest.approx(required, abs=1e-6)
    assert res.patched.metrics.horizon_output_kwh == pytest.approx(required / 0.98, abs=1e-6)
    assert res.patched.metrics.horizon_grid_input_kwh == pytest.approx(required / 0.98 / 0.95, abs=1e-6)
    assert res.delta["horizon_output_kwh"] == pytest.approx(required / 0.98 - 11 * 30 / 60, abs=1e-6)
    assert res.feasible is True
    assert res.snapshot_digest == snap.recompute_digest()
    assert res.event_manifest_sha256 == snap.event_manifest.manifest_sha256
    assert res.baseline.input_sha256 == snap.envelope.snapshot_digest != res.patched.input_sha256


@pytest.mark.parametrize("zone", ["AC", "DC"])
async def test_already_satisfied_preserves_soc_energy_and_release(zone):
    rt = _rt()
    b = _add(rt, zone=zone, hours=2)
    await _replan(rt)
    rt.simulator.step(3)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=8)
    res = await run_what_if(snap, _actor(rt), _target(b, 0))
    (row,) = res.affected_vehicles
    assert row.patched_revised.already_satisfied_at_snapshot is True
    assert row.patched_revised.target_reached_at is None
    assert row.patched_revised.met_deadline is True
    assert row.patched_horizon_battery_kwh == 0
    assert row.patched_first_charge_at is None  # Historical timestamp unknown in G3.
    assert res.patched.metrics.horizon_grid_input_kwh == 0
    assert row.patched_release_at == (snap.envelope.as_of + timedelta(minutes=5) if zone == "DC" else None)
    assert rt.simulator.adapter.soc(b.booking_id) * 100 > 20
    assert snap.recompute_digest() == snap.envelope.snapshot_digest


async def test_target_increase_tracks_original_crossing_before_revised_target():
    rt = _rt()
    # Same fixture holds a small original target without changing the EV's initial SOC.
    b = _add(rt, hours=2)
    b.request.soc_target = 21
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await _replan(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=20)
    (row,) = (await run_what_if(snap, _actor(rt), _target(b, 22))).affected_vehicles
    assert row.patched_original.met_deadline and row.patched_revised.met_deadline
    assert row.patched_original.target_reached_at < row.patched_revised.target_reached_at
    assert row.patched_original.target_reached_at == snap.envelope.as_of + timedelta(minutes=8)
    assert row.baseline_original.target_reached_at == snap.envelope.as_of + timedelta(minutes=16)


@pytest.mark.parametrize("deadline_minutes", [7, 23])
async def test_deadline_oracle_energy_and_actual_release(deadline_minutes):
    rt = _rt()
    b = _add(rt, hours=0.25)
    await _replan(rt)
    at = rt.clock()
    snap = await capture_atomic_snapshot(rt, horizon_minutes=30)
    deadline = at + timedelta(minutes=deadline_minutes)
    result = await run_what_if(
        snap, _actor(rt), {"op": "revise_vehicle", "booking_id": b.booking_id, "deadline": deadline}
    )
    (row,) = result.affected_vehicles
    assert row.baseline_original.deadline == row.patched_original.deadline == b.request.deadline
    assert row.patched_revised.deadline == row.patched_release_at == deadline
    assert row.patched_original.met_deadline is False
    assert row.patched_revised.met_deadline is False
    assert result.delta["horizon_output_kwh"] == pytest.approx(11 * (deadline_minutes - 15) / 60, abs=1e-6)
    assert result.delta["horizon_grid_input_kwh"] == pytest.approx(11 * (deadline_minutes - 15) / 60 / 0.95, abs=1e-6)


async def test_reservation_censoring_and_noop_equality():
    rt = _rt()
    at = rt.clock()
    b = _add(rt, arrival=at + timedelta(minutes=20))
    snap = await capture_atomic_snapshot(rt, horizon_minutes=10)
    actor = _actor(rt, b.resident_id, Role.RESIDENT)
    noop = await run_what_if(snap, actor, _target(b, 80))
    assert all(value in (None, 0) for value in noop.delta.values())
    assert noop.feasible is None
    assert noop.patched.metrics.sla.denominator == 0
    assert noop.patched.metrics.sla.censored_count == 1
    revised = await run_what_if(snap, actor, _target(b, 70))
    assert revised.affected_vehicles[0].patched_revised.met_deadline is None
    assert revised.patched.metrics.horizon_battery_kwh == 0
    with pytest.raises(ValueError, match="arrival"):
        await run_what_if(
            snap, actor, {"op": "revise_vehicle", "booking_id": b.booking_id, "deadline": at + timedelta(minutes=5)}
        )


async def test_site_limit_units_known_events_and_copy_on_write():
    rt = _rt()
    _add(rt)
    cap_event = LimitEvent(4, 0, 5.0, {"AC-01": 11.0})
    rt.simulator.kernel.scenario = replace(rt.simulator.scenario, limit_events=(cap_event,))
    await _replan(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=8)
    baseline_fork = build_sandbox_runtime(snap)
    local_state = rt.simulator.snapshot_physics_state()
    actor = _actor(rt)
    op = {"op": "site_limit", "grid_input_kw": 8}
    res = await run_what_if(snap, actor, op)
    repeat = await run_what_if(snap, actor, op)
    assert res.status == "completed"
    assert res.delta == repeat.delta
    # B0 fixed shares reserve 22% of charger output for AC, even with no DC load.
    assert res.patched.metrics.horizon_grid_input_kwh == pytest.approx((8 + 5) * 0.22 * 4 / 60, abs=0.002)
    assert res.patched.metrics.peak_grid_input_kw == pytest.approx(8 * 0.22, abs=0.015)
    assert res.patched.metrics.peak_charger_output_kw == pytest.approx(8 * 0.22 * 0.95, abs=0.015)
    assert res.baseline.metrics.horizon_grid_input_kwh == pytest.approx((11 / 0.95 + 5 * 0.22) * 4 / 60, abs=0.002)
    expected_cost = res.patched.metrics.horizon_grid_input_kwh * rt.tariff.price_at(rt.clock().time())
    assert res.patched.metrics.horizon_energy_cost_vnd == pytest.approx(expected_cost, abs=0.03)
    assert res.baseline.config_sha256 != res.patched.config_sha256
    assert rt.simulator.snapshot_physics_state() == local_state
    assert baseline_fork.simulator.scenario.limit_events[0].cabinet_output_kw["AC-01"] == 11
    assert snap.recompute_digest() == snap.envelope.snapshot_digest


async def test_site_infrastructure_and_independent_validation():
    rt = _rt()
    snap = await capture_atomic_snapshot(rt, horizon_minutes=2)
    actor = _actor(rt)
    with pytest.raises(ValueError, match="hypothetical"):
        await run_what_if(snap, actor, {"op": "site_limit", "grid_input_kw": 120})
    result = await run_what_if(
        snap, actor, {"op": "site_limit", "grid_input_kw": 120, "hypothetical_infrastructure": True}
    )
    assert result.hypothetical_infrastructure is True
    with pytest.raises(ValueError, match="envelope"):
        await run_what_if(snap, actor, {"op": "site_limit", "grid_input_kw": 1000, "hypothetical_infrastructure": True})

    config = StationConfig.model_validate(
        {
            **rt.config.model_dump(),
            "supply_mode": "independent",
            "independent_grid_input_limit_kw": {"AC": 30, "DC": 90},
        }
    )
    independent = _rt(config=config)
    snap = await capture_atomic_snapshot(independent, horizon_minutes=2)
    with pytest.raises(ValueError, match="shared supply"):
        await run_what_if(snap, _actor(independent), {"op": "site_limit", "grid_input_kw": 8})


@pytest.mark.parametrize("restore_at_boundary", [False, True])
async def test_outage_oracle_one_connector_and_restore_at_boundary(restore_at_boundary):
    rt = _rt()
    at = rt.clock()
    _add(rt, arrival=at + timedelta(minutes=2))
    # This fault predates the patch and must survive. Only the other AC connector can serve the EV.
    original_fault = "AC-02-1"
    rt.simulator.inject_incident(Incident(type=IncidentType.CONNECTOR_FAULT, connector_id=original_fault))
    minutes = 5 if restore_at_boundary else 10
    snap = await capture_atomic_snapshot(rt, horizon_minutes=minutes)
    actor = _actor(rt)
    patch = {"op": "outage", "connector_id": "AC-01-1", "starts_at": at + timedelta(minutes=2), "duration_minutes": 3}
    result = await run_what_if(snap, actor, patch)
    assert result.status == "completed"
    assert result.delta["horizon_output_kwh"] == pytest.approx(-11 * 3 / 60, abs=1e-6)
    (row,) = result.affected_vehicles
    assert row.baseline_plug_in_at == at + timedelta(minutes=2)
    assert row.patched_plug_in_at == (None if restore_at_boundary else at + timedelta(minutes=5))
    assert any("patch-owned fault was restored" in line for line in result.assumptions)
    preserved = await run_what_if(snap, actor, {**patch, "connector_id": original_fault})
    assert all(value in (None, 0) for value in preserved.delta.values())
    assert "pre-existing fault was preserved" in preserved.assumptions[-1]
    assert rt.simulator.snapshot_physics_state()["faulted_connectors"] == [original_fault]


@pytest.mark.parametrize(
    "bad",
    [
        {"op": "add_vehicle"},
        {"op": "revise_vehicle", "booking_id": "a"},
        {"op": "revise_vehicle", "booking_id": "a", "target_soc": "25"},
        {"op": "revise_vehicle", "booking_id": "a", "deadline": 1700000000},
        {"op": "revise_vehicle", "booking_id": "a", "deadline": "2026-11-23T12:00:00"},
        {"op": "site_limit", "grid_input_kw": float("inf")},
        {"op": "site_limit", "grid_input_kw": 20, "charger_output_kw": 20},
        {"op": "outage", "connector_id": "x", "duration_minutes": True},
    ],
)
def test_strict_business_patch_schema(bad):
    with pytest.raises(ValidationError):
        PATCH_ADAPTER.validate_python(bad)


async def test_authorization_and_resident_projection():
    rt = _rt()
    mine = _add(rt, "me")
    other = _add(rt, "private-identity")
    snap = await capture_atomic_snapshot(rt, horizon_minutes=3)
    resident = _actor(rt, mine.resident_id, Role.RESIDENT)
    for patch in (_target(other, 21), _target(booking("absent"), 21), {"op": "site_limit", "grid_input_kw": 8}):
        with pytest.raises(WhatIfForbiddenError, match="not allowed"):
            await run_what_if(snap, resident, patch)
    with pytest.raises(WhatIfForbiddenError):
        await run_what_if(
            snap, ActorContext(actor_id="op", station_id="other-site", role=Role.OPERATOR), _target(mine, 21)
        )
    res = await run_what_if(snap, resident, _target(mine, 21))
    assert res.known_booking_count == 2
    assert [row.booking_id for row in res.affected_vehicles] == [mine.booking_id]
    assert other.booking_id not in res.model_dump_json()


async def test_unresolved_safety_suppresses_unequal_window_deltas(monkeypatch):
    rt = _rt()
    _add(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=6)
    original = HybridStation.step

    def step(station, minutes):
        events = original(station, minutes)
        if station.kernel.sandbox_grid_cap_kw and station.minute == 1:
            events.append(StationEvent(event_id="g4-hard", type=EventType.HARD_LIMIT_VIOLATED, occurred_at=station.now))
        return events

    monkeypatch.setattr(HybridStation, "step", step)
    res = await run_what_if(snap, _actor(rt), {"op": "site_limit", "grid_input_kw": 8})
    assert res.baseline.observed_until == snap.event_manifest.horizon_end
    assert res.patched.observed_until == snap.envelope.as_of + timedelta(minutes=1)
    assert res.patched.status == "unresolved_safety" and res.status == "unsafe"
    assert res.delta is None and res.feasible is False and res.applied is False


async def test_tampered_snapshot_and_live_intervention_attempt_are_rejected():
    from src.services.copilot.what_if import _WhatIfIntervention

    rt = _rt()
    b = _add(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=2)
    actor = _actor(rt)
    patch = _target(b, 21)
    prepared = _prepare_patch(snap, actor, patch)
    with pytest.raises(ValueError, match="isolated sandbox"):
        _WhatIfIntervention(prepared).at_minute(rt)
    snap.event_manifest.assumptions.append("unverified assumption")
    with pytest.raises(ValueError, match="integrity"):
        await run_what_if(snap, actor, patch)


async def _wait_status(service, actor, job_id, status):
    async with asyncio.timeout(4):
        while True:
            result = service.get(actor, job_id)
            if result.status == status:
                return result
            await asyncio.sleep(0)


async def test_jobs_owner_single_worker_capacity_and_cancellation(monkeypatch):
    rt = _rt()
    b = _add(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=2)
    owner = _actor(rt, b.resident_id, Role.RESIDENT)
    outsider = _actor(rt, "outsider", Role.RESIDENT)
    operator = _actor(rt)
    ran, cancelled = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        ran.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    monkeypatch.setattr(jobs_module, "run_what_if", slow)
    svc = WhatIfJobs(max_queued=1)
    active = svc.submit(owner, snap, _target(b, 21))
    try:
        await asyncio.wait_for(ran.wait(), 2)
        queued = svc.submit(owner, snap, _target(b, 22))
        with pytest.raises(WhatIfCapacityError):
            svc.submit(owner, snap, _target(b, 23))
        assert svc.get(outsider, active.job_id) is None
        assert svc.cancel(operator, queued.job_id) is None
        assert svc.cancel(owner, queued.job_id).status == WhatIfJobStatus.CANCELLED
        svc.cancel(owner, active.job_id)
        view = await _wait_status(svc, owner, active.job_id, WhatIfJobStatus.CANCELLED)
        assert cancelled.is_set()
        assert view.applied is False and view.result is None
    finally:
        await svc.close()


async def test_job_timeout_and_ttl(monkeypatch):
    rt = _rt()
    b = _add(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=2)
    owner = _actor(rt, b.resident_id, Role.RESIDENT)
    cleanup = asyncio.Event()

    async def slow(*args, timeout_s, **kwargs):
        try:
            async with asyncio.timeout(timeout_s):
                await asyncio.Future()
        finally:
            cleanup.set()

    monkeypatch.setattr(jobs_module, "run_what_if", slow)
    svc = WhatIfJobs(timeout_s=0.05, ttl_s=5)
    job = svc.submit(owner, snap, _target(b, 21))
    try:
        view = await _wait_status(svc, owner, job.job_id, WhatIfJobStatus.FAILED)
        assert view.error == "timeout" and cleanup.is_set() and not view.applied
        original_clock = svc._clock
        monkeypatch.setattr(svc, "_clock", lambda: original_clock() + 6)
        assert svc.get(owner, job.job_id).status == WhatIfJobStatus.EXPIRED
        monkeypatch.setattr(svc, "_clock", lambda: original_clock() + 20)
        assert svc.get(owner, job.job_id) is None
    finally:
        await svc.close()


async def test_job_result_detached_from_polling_client():
    rt = _rt()
    b = _add(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=3)
    owner = _actor(rt, b.resident_id, Role.RESIDENT)
    svc = WhatIfJobs()
    job = svc.submit(owner, snap, _target(b, 21))
    try:
        view = await _wait_status(svc, owner, job.job_id, WhatIfJobStatus.SUCCEEDED)
        assert view.result.applied is False
        view.result.patched.metrics.by_zone.clear()
        assert set(svc.get(owner, job.job_id).result.patched.metrics.by_zone) == {"AC", "DC"}
    finally:
        await svc.close()


async def test_finished_ac_session_can_resume_and_keeps_historical_completion():
    rt = _rt()
    b = _add(rt)
    b.request.soc_target = 21
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await _replan(rt)
    for _ in range(20):
        events = rt.simulator.step(1)
        await control_loop.on_minute(rt, events)
    assert rt.simulator.queue.sessions[b.booking_id].state == "FINISHED"
    snap = await capture_atomic_snapshot(rt, horizon_minutes=20)
    res = await run_what_if(snap, _actor(rt), _target(b, 22))
    (row,) = res.affected_vehicles
    assert row.baseline_original.target_reached_at == row.patched_original.target_reached_at
    assert row.patched_original.already_satisfied_at_snapshot
    assert row.patched_revised.target_reached_at > snap.envelope.as_of
    assert row.baseline_horizon_battery_kwh == 0.0 < row.patched_horizon_battery_kwh
    assert rt.simulator.queue.sessions[b.booking_id].state == "FINISHED"


async def test_attained_queued_vehicle_uses_no_connector():
    rt = _rt()
    for name in ("a", "b"):
        _add(rt, name)
    queued = _add(rt, "c")
    await _replan(rt)
    assert rt.simulator.queue.sessions[queued.booking_id].state == "QUEUED"
    snap = await capture_atomic_snapshot(rt, horizon_minutes=3)
    res = await run_what_if(snap, _actor(rt, queued.resident_id, Role.RESIDENT), _target(queued, 10))
    (row,) = res.affected_vehicles
    assert row.patched_revised.already_satisfied_at_snapshot
    assert row.patched_plug_in_at is None
    assert row.patched_horizon_battery_kwh == 0.0
    assert rt.simulator.queue.sessions[queued.booking_id].state == "QUEUED"


async def test_outage_rejects_past_misaligned_and_unknown_connector():
    rt = _rt()
    snap = await capture_atomic_snapshot(rt, horizon_minutes=5)
    actor = _actor(rt)
    patch = {"op": "outage", "connector_id": "AC-01-1", "duration_minutes": 1}
    for offset in (-60, 15, 300):
        with pytest.raises(ValueError, match="simulator minute"):
            await run_what_if(snap, actor, {**patch, "starts_at": rt.clock() + timedelta(seconds=offset)})
    with pytest.raises(ValueError, match="Unknown connector"):
        await run_what_if(snap, actor, {**patch, "connector_id": "CABINET-ONLY"})


async def test_g4_patch_uses_only_sandbox_sinks(monkeypatch, clean_db):
    from src.models.identity import UserRecord
    from src.services import realtime, repository, runtime

    monkeypatch.setattr(runtime, "_live_clock", lambda _: lambda: NOW)
    b = booking("live", now=NOW)
    repository.upsert_user(
        UserRecord(
            user_id=b.resident_id, email="g4@example.invalid", display_name="G4", role=Role.RESIDENT, created_at=NOW
        )
    )
    repository.save_booking(b)
    live = runtime.get_runtime()
    before = live.simulator.snapshot_physics_state()
    snap = await capture_atomic_snapshot(live, horizon_minutes=4)
    original = HybridStation.apply_commands

    def apply_commands(station, commands):
        assert station.is_fork
        return original(station, commands)

    def forbidden_write(*args, **kwargs):
        pytest.fail("WHAT-IF invoked a live effect")

    monkeypatch.setattr(HybridStation, "apply_commands", apply_commands)
    monkeypatch.setattr(realtime, "broadcast", forbidden_write)
    for name in ("save_booking", "save_plan", "append_event", "append_decision", "save_approval", "append_load_point"):
        monkeypatch.setattr(repository, name, forbidden_write)
    await run_what_if(snap, _actor(live), _target(b, 21))
    await run_what_if(snap, _actor(live), {"op": "site_limit", "grid_input_kw": 10})
    await run_what_if(snap, _actor(live), {"op": "outage", "connector_id": "AC-01-1", "duration_minutes": 2})
    assert live.simulator.snapshot_physics_state() == before
    assert repository.get_booking(b.booking_id) == b


async def test_site_cap_equal_to_current_still_limits_future_announced_increase():
    rt = _rt()
    _add(rt)
    rt.simulator.inject_incident(Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=8))
    rt.simulator.kernel.scenario = replace(rt.simulator.scenario, limit_events=(LimitEvent(4, 0, 20, {}),))
    snap = await capture_atomic_snapshot(rt, horizon_minutes=8)
    result = await run_what_if(snap, _actor(rt), {"op": "site_limit", "grid_input_kw": 8})
    assert result.status == "completed"
    assert result.patched.metrics.peak_grid_input_kw == pytest.approx(0.22 * 8, abs=0.002)
    assert result.baseline.metrics.peak_grid_input_kw == pytest.approx(0.22 * 20, abs=0.002)
    assert result.delta["horizon_grid_input_kwh"] == pytest.approx(0.22 * (8 - 20) * 4 / 60, abs=0.002)


async def test_resolved_hard_violation_remains_unsafe_at_equal_full_horizon(monkeypatch):
    rt = _rt()
    snap = await capture_atomic_snapshot(rt, horizon_minutes=2)
    original = HybridStation.step

    def step(station, minutes):
        events = original(station, minutes)
        if station.kernel.sandbox_grid_cap_kw and station.minute == 1:
            station.kernel.applied_constraint_violation_count += 1
            events.append(
                StationEvent(
                    type=EventType.HARD_LIMIT_VIOLATED, occurred_at=station.now, violation_kinds=["aggregate_power"]
                )
            )
        return events

    monkeypatch.setattr(HybridStation, "step", step)
    result = await run_what_if(snap, _actor(rt), {"op": "site_limit", "grid_input_kw": 8})
    assert result.baseline.observed_until == result.patched.observed_until == snap.event_manifest.horizon_end
    assert result.patched.status == "unsafe"
    assert result.patched.hard_violations == 1 and result.patched.unresolved_safety_count == 0
    assert result.delta is None and result.feasible is False


async def test_cancelling_native_job_never_submits_its_patched_branch(monkeypatch):
    rt = _rt()
    _add(rt)
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=4)
    actor = _actor(rt)
    scheduler_type = type(rt.scheduler)
    original = scheduler_type.plan
    worker_started, release_worker = threading.Event(), threading.Event()
    observed_grid = []

    def plan(scheduler, ctx):
        observed_grid.append(ctx.state.available_power_kw)
        if not worker_started.is_set():
            worker_started.set()
            assert release_worker.wait(5)
        return original(scheduler, ctx)

    monkeypatch.setattr(scheduler_type, "plan", plan)
    service = WhatIfJobs()
    first = service.submit(actor, snapshot, {"op": "site_limit", "grid_input_kw": 8})
    try:
        assert await asyncio.to_thread(worker_started.wait, 3)
        second = service.submit(actor, snapshot, {"op": "site_limit", "grid_input_kw": 20})
        service.cancel(actor, first.job_id)
        cancelled = await _wait_status(service, actor, first.job_id, WhatIfJobStatus.CANCELLED)
        assert cancelled.result is None
        assert not release_worker.is_set()
        release_worker.set()
        completed = await _wait_status(service, actor, second.job_id, WhatIfJobStatus.SUCCEEDED)
        assert not completed.result.applied
        assert 8 not in observed_grid and 20 in observed_grid
    finally:
        release_worker.set()
        await service.close()
