"""Gate 4 independent energy, deadline, safety, authorization and job probes."""

import asyncio
import threading
from dataclasses import replace
from datetime import UTC, time, timedelta, timezone

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
from src.services.copilot import what_if as what_if_module
from src.services.copilot.counterfactual import run_sandbox_branch
from src.services.copilot.jobs import WhatIfCapacityError, WhatIfJobs
from src.services.copilot.snapshot import build_sandbox_runtime
from src.services.copilot.what_if import WhatIfForbiddenError, _prepare_patch, run_what_if
from src.services.runtime import build_sim_runtime, visit_of
from src.simulator.hybrid_station import HybridStation
from tests.factories import NOW, booking


def _rt(*, config=None, start=None):
    scenario = catalog.load_scenario("hybrid_evening")
    if start is not None:
        scenario = scenario.model_copy(update={"start_time": start})
    return build_sim_runtime(
        scenario,
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
    assert res.patched.metrics.plug_wait_unknown_count == 0
    assert res.patched.metrics.charge_wait_unknown_count == 1
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


async def test_explicit_half_minute_deadline_is_rejected_before_rollout():
    rt = _rt()
    at = rt.clock()
    revised = at + timedelta(minutes=7, seconds=30)
    first = _add(rt, "first", hours=0.25)
    second = _add(rt, "second", arrival=at + timedelta(minutes=1))
    rt.simulator.inject_incident(Incident(type=IncidentType.CONNECTOR_FAULT, connector_id="AC-02-1"))
    snap = await capture_atomic_snapshot(rt, horizon_minutes=20)
    patch = {"op": "revise_vehicle", "booking_id": first.booking_id, "deadline": revised}
    try:
        result = await run_what_if(snap, _actor(rt), patch)
    except ValidationError as exc:
        (error,) = exc.errors()
        assert error["loc"] == ("deadline",)
        assert error["type"] == "deadline_not_on_simulator_minute"
    else:
        # Fail-before diagnostics show where the silent ceil falls in the rollout.
        rows = {row.booking_id: row for row in result.affected_vehicles}
        a, b = rows[first.booking_id], rows[second.booking_id]
        assert a.patched_release_at == b.patched_plug_in_at == at + timedelta(minutes=8)
        assert a.patched_horizon_battery_kwh == pytest.approx(11 * 0.98 * 8 / 60, abs=1e-6)
        assert a.baseline_release_at == b.baseline_plug_in_at == at + timedelta(minutes=15)
        assert a.patched_original.met_deadline is a.patched_revised.met_deadline is False
        pytest.fail(
            f"Accepted {revised.isoformat()} and held the connector until {a.patched_release_at.isoformat()}. "
            f"Battery kWh for first/second: baseline {a.baseline_horizon_battery_kwh}/{b.baseline_horizon_battery_kwh}, "
            f"patched {a.patched_horizon_battery_kwh}/{b.patched_horizon_battery_kwh}. "
            f"First booking original/revised SLA: {a.patched_original.met_deadline}/{a.patched_revised.met_deadline}."
        )
    with pytest.raises(ValidationError, match="simulator minute"):
        WhatIfJobs().submit(_actor(rt), snap, patch)


async def test_deadline_grid_uses_snapshot_seconds_and_normalizes_offsets():
    rt = _rt(start=time(12, 0, 30, 123000))
    b = _add(rt, hours=0.25)
    rt.simulator.step(2)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=16)
    at = snap.envelope.as_of
    aligned = at + timedelta(minutes=7)
    other_offset = timezone(timedelta(hours=-3, minutes=-30))
    patch = {
        "op": "revise_vehicle",
        "booking_id": b.booking_id,
        "deadline": aligned.astimezone(other_offset).isoformat(),
    }
    result = await run_what_if(snap, _actor(rt), patch)
    (row,) = result.affected_vehicles
    assert result.patch.deadline.isoformat() == aligned.astimezone(UTC).isoformat()
    assert row.patched_revised.deadline == row.patched_release_at == aligned
    whole_wall_minute = aligned.replace(second=0, microsecond=0)
    for invalid in (whole_wall_minute, aligned + timedelta(microseconds=1)):
        with pytest.raises(ValidationError, match="simulator minute"):
            await run_what_if(snap, _actor(rt), {**patch, "deadline": invalid})
    with pytest.raises(ValidationError, match="timezone"):
        await run_what_if(snap, _actor(rt), {**patch, "deadline": aligned.replace(tzinfo=None)})


async def test_target_only_keeps_off_grid_original_deadline_and_physical_release():
    rt = _rt()
    b = _add(rt, hours=7.5 / 60)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=10)
    result = await run_what_if(snap, _actor(rt), _target(b, 70))
    (row,) = result.affected_vehicles
    assert result.patch.deadline is None
    assert row.baseline_original.deadline == row.patched_original.deadline == b.request.deadline
    assert row.patched_revised.deadline == b.request.deadline
    assert row.baseline_release_at == row.patched_release_at == snap.envelope.as_of + timedelta(minutes=8)
    assert row.patched_original.met_deadline is row.patched_revised.met_deadline is False


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
    assert noop.delta_reasons["plug_wait_mean_minutes"].code == "missing_data"
    assert noop.delta_reasons["sla.on_time_rate"].code == "missing_data"
    assert noop.delta_reasons["service_coverage_rate"].code == "missing_data"
    assert noop.delta_reasons["charged_coverage_rate"].code == "missing_data"
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
    if restore_at_boundary:
        assert result.delta["plug_wait_mean_minutes"] is None
        assert result.delta_reasons["plug_wait_mean_minutes"].code == "non_comparable_sample"
        assert result.delta["service_coverage_rate"] == -1
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
    assert res.delta_reasons is None


async def test_tampered_snapshot_and_live_intervention_attempt_are_rejected():
    from src.services.copilot.what_if import _WhatIfIntervention

    rt = _rt()
    b = _add(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=2)
    actor = _actor(rt)
    patch = _target(b, 21)
    prepared = _prepare_patch(snap, actor, patch)
    with pytest.raises(ValueError, match="isolated sandbox"):
        _WhatIfIntervention(prepared, capture_minute=prepared.as_of_minute).at_minute(rt)
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
    assert result.delta_reasons is None


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


async def test_wait_delta_does_not_reward_losing_a_slow_booking(monkeypatch):
    rt = _rt()
    a = _add(rt, "vehicle-a")
    b = _add(rt, "private-vehicle-b")
    snap = await capture_atomic_snapshot(rt, horizon_minutes=60)
    original = await run_sandbox_branch(snap)
    ledger = original.outcome_ledger
    a_row, b_row = (next(row for row in ledger.vehicles if row.booking_id == rec.booking_id) for rec in (a, b))
    baseline = ledger.model_copy(
        update={
            "vehicles": [
                _observed_wait(a_row, 10),
                _observed_wait(b_row, 50),
            ],
            "plug_wait_mean_minutes": 30,
            "plug_wait_p90_minutes": 50,
            "charge_start_wait_mean_minutes": 30,
            "charge_start_wait_p90_minutes": 50,
            "horizon_output_kwh": 8,
            "horizon_energy_cost_vnd": 4000,
        }
    )
    patched = baseline.model_copy(
        update={
            "vehicles": [
                _observed_wait(a_row, 15),
                b_row.model_copy(
                    update={
                        "plug_in_at": None,
                        "first_charge_at": None,
                        "plug_wait_minutes": None,
                        "charge_start_wait_minutes": None,
                        "censored_plug_wait_minutes": 60,
                        "censored_charge_start_wait_minutes": 60,
                        "final_session_state": "QUEUED",
                        "horizon_battery_stored_kwh": 0,
                        "horizon_output_kwh": 0,
                        "horizon_grid_input_kwh": 0,
                        "cumulative_battery_stored_kwh": 0,
                        "cumulative_output_kwh": 0,
                        "cumulative_grid_input_kwh": 0,
                    }
                ),
            ],
            "plug_wait_observed_count": 1,
            "charge_start_wait_observed_count": 1,
            "plug_wait_mean_minutes": 15,
            "plug_wait_p90_minutes": 15,
            "charge_start_wait_mean_minutes": 15,
            "charge_start_wait_p90_minutes": 15,
            "plugged_count": 1,
            "charged_count": 1,
            "service_coverage_rate": 0.5,
            "charged_coverage_rate": 0.5,
            "horizon_output_kwh": 5,
            "horizon_energy_cost_vnd": 2800,
        }
    )

    async def run_branch(_snapshot, *, branch_label="baseline", **_kwargs):
        return original.model_copy(update={"outcome_ledger": patched if branch_label == "patched" else baseline})

    monkeypatch.setattr(what_if_module, "run_sandbox_branch", run_branch)
    result = await run_what_if(snap, _actor(rt, a.resident_id, Role.RESIDENT), _target(a, 80))
    assert result.baseline.metrics.plug_wait_mean_minutes == 30
    assert result.patched.metrics.plug_wait_mean_minutes == 15
    assert result.patched.metrics.plug_wait_observed_count == result.patched.metrics.plug_wait_censored_count == 1
    for key in (
        "plug_wait_mean_minutes",
        "plug_wait_p90_minutes",
        "charge_wait_mean_minutes",
        "charge_wait_p90_minutes",
    ):
        assert result.delta[key] is None, f"{key} changed sample from A/B to A, got delta {result.delta[key]}"
        assert result.delta_reasons[key].code == "non_comparable_sample"
    assert result.delta["service_coverage_rate"] == result.delta["charged_coverage_rate"] == -0.5
    assert result.delta["horizon_output_kwh"] == -3
    assert result.delta["horizon_energy_cost_vnd"] == -1200
    assert b.booking_id not in result.model_dump_json()


def _observed_wait(row, minutes):
    observed = row.arrived_at + timedelta(minutes=minutes)
    return row.model_copy(
        update={
            "plug_in_at": observed,
            "first_charge_at": observed,
            "plug_wait_minutes": minutes,
            "charge_start_wait_minutes": minutes,
        }
    )


@pytest.mark.parametrize("same_membership", [False, True], ids=["swapped-bookings", "same-bookings"])
async def test_exact_membership_for_wait_sla_and_coverage_rates(monkeypatch, same_membership):
    rt = _rt()
    for zone in ("AC", "DC"):
        for tag in ("a", "b"):
            _add(rt, f"{zone}-{tag}", zone=zone)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=20)
    branch = await run_sandbox_branch(snap)
    ledger = branch.outcome_ledger

    def branch_ledger(tag, wait, met):
        rows = []
        for row in ledger.vehicles:
            selected = row.booking_id.endswith(f"-{tag}")
            observation = (
                _observed_wait(row, wait)
                if selected
                else row.model_copy(
                    update={
                        "arrived_at": None,
                        "plug_in_at": None,
                        "first_charge_at": None,
                        "plug_wait_minutes": None,
                        "charge_start_wait_minutes": None,
                    }
                )
            )
            rows.append(
                observation.model_copy(
                    update={
                        "sla_evaluable": selected,
                        "met_original_sla": met if selected else None,
                        "censored": not selected,
                        "unserved": selected and not met,
                    }
                )
            )
        zones = {
            zone: metrics.model_copy(
                update={
                    "sla_denominator": 1,
                    "sla_met_count": int(met),
                    "on_time_rate": float(met),
                    "censored_count": 1,
                }
            )
            for zone, metrics in ledger.by_zone.items()
        }
        return ledger.model_copy(
            update={
                "vehicles": rows,
                "by_zone": zones,
                "sla_denominator": 2,
                "sla_met_count": 2 * int(met),
                "on_time_rate": float(met),
                "arrived_count": 2,
                "not_arrived_count": 2,
                "censored_count": 2,
                "unserved_count": 2 * int(not met),
                "service_coverage_denominator": 2,
                "service_coverage_rate": float(met),
                "charged_coverage_rate": float(met),
                "plug_wait_observed_count": 2,
                "charge_start_wait_observed_count": 2,
                "plug_wait_mean_minutes": wait,
                "plug_wait_p90_minutes": wait,
                "charge_start_wait_mean_minutes": wait,
                "charge_start_wait_p90_minutes": wait,
            }
        )

    baseline = branch_ledger("a", 10, True)
    patched = branch_ledger("a" if same_membership else "b", 15, False)

    async def run_branch(_snapshot, *, branch_label="baseline", **_kwargs):
        return branch.model_copy(update={"outcome_ledger": patched if branch_label == "patched" else baseline})

    monkeypatch.setattr(what_if_module, "run_sandbox_branch", run_branch)
    result = await run_what_if(snap, _actor(rt), {"op": "site_limit", "grid_input_kw": 8})
    expected_deltas = {
        "plug_wait_mean_minutes": 5,
        "plug_wait_p90_minutes": 5,
        "charge_wait_mean_minutes": 5,
        "charge_wait_p90_minutes": 5,
        "sla.on_time_rate": -1,
        "sla.AC.on_time_rate": -1,
        "sla.DC.on_time_rate": -1,
        "service_coverage_rate": -1,
        "charged_coverage_rate": -1,
    }
    for key, signed in expected_deltas.items():
        assert result.delta[key] == (signed if same_membership else None), key
        if same_membership:
            assert key not in result.delta_reasons
        else:
            assert result.delta_reasons[key].code == "non_comparable_sample"
    assert result.delta["sla.met_count"] == -2
    assert result.delta["sla.denominator"] == 0
    assert result.delta["unserved_count"] == 2
    assert result.delta["sla.censored_count"] == 0


async def test_safe_unequal_observed_windows_suppress_entire_comparison(monkeypatch):
    rt = _rt()
    b = _add(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=5)
    baseline = await run_sandbox_branch(snap)
    early = baseline.model_copy(update={"observed_until": baseline.observed_until - timedelta(minutes=1)})

    async def run_branch(_snapshot, *, branch_label="baseline", **_kwargs):
        return early if branch_label == "patched" else baseline

    monkeypatch.setattr(what_if_module, "run_sandbox_branch", run_branch)
    result = await run_what_if(snap, _actor(rt), _target(b, 80))
    assert result.baseline.status == result.patched.status == "completed"
    assert result.status == "incomplete"
    assert result.delta is result.delta_reasons is None


def _site_patch(grid_kw, *, upgraded=False):
    return {"op": "site_limit", "grid_input_kw": grid_kw, "hypothetical_infrastructure": upgraded}


def _set_limits(rt, *events, runtime_grid=None):
    if runtime_grid is not None:
        rt.simulator.inject_incident(Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=runtime_grid))
    rt.simulator.kernel.scenario = replace(rt.simulator.scenario, limit_events=events)


def _assert_site_branch(branch, output_profile, *, ac_count, dc_count):
    """Integrate explicit (AC output, DC output, minutes, VND/grid kWh) blocks."""
    metrics = branch.metrics
    output_kw_minutes = sum((ac + dc) * minutes for ac, dc, minutes, _ in output_profile)
    expected_cost = sum((ac + dc) * minutes / 60 / 0.95 * price for ac, dc, minutes, price in output_profile)
    peak_output_kw = max(ac + dc for ac, dc, _, _ in output_profile)
    assert branch.status == "completed"
    assert metrics.horizon_output_kwh == pytest.approx(output_kw_minutes / 60, abs=2e-6)
    assert metrics.horizon_battery_kwh == pytest.approx(output_kw_minutes / 60 * 0.98, abs=2e-6)
    assert metrics.horizon_grid_input_kwh == pytest.approx(output_kw_minutes / 60 / 0.95, abs=2e-6)
    assert metrics.horizon_energy_cost_vnd == pytest.approx(expected_cost, abs=0.01)
    assert metrics.peak_charger_output_kw == pytest.approx(peak_output_kw, abs=2e-6)
    assert metrics.peak_grid_input_kw == pytest.approx(peak_output_kw / 0.95, abs=2e-6)
    for sla, count in (
        (metrics.sla, ac_count + dc_count),
        (metrics.by_zone["AC"], ac_count),
        (metrics.by_zone["DC"], dc_count),
    ):
        assert (sla.denominator, sla.met_count, sla.on_time_rate, sla.censored_count) == (count, 0, 0, 0)
    assert branch.hard_violations == branch.rejected_allocations == branch.sampled_grid_over_limit_minutes == 0
    assert branch.unresolved_safety_count == branch.blocked_commands == branch.pending_approval_commands == 0


async def test_site_increase_at_binding_shared_source_changes_mixed_delivery_and_tou():
    rt = _rt(start=time(19, 56))
    for zone in ("AC", "DC"):
        for i in range(2):
            _add(rt, f"{zone}-{i}", zone=zone, hours=8 / 60)
    _set_limits(rt, runtime_grid=40)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=8)
    result = await run_what_if(snap, _actor(rt), _site_patch(80))
    # Conversion 0.95 and B0 shares 22:78. Four EVs keep both zones supply-bound.
    _assert_site_branch(result.baseline, [(8.36, 29.64, 4, 3500), (8.36, 29.64, 4, 2000)], ac_count=2, dc_count=2)
    _assert_site_branch(result.patched, [(16.72, 59.28, 4, 3500), (16.72, 59.28, 4, 2000)], ac_count=2, dc_count=2)
    assert result.delta["horizon_output_kwh"] == pytest.approx(38 * 8 / 60, abs=2e-6)
    assert result.delta["horizon_energy_cost_vnd"] == pytest.approx(40 * 4 / 60 * (3500 + 2000), abs=0.02)
    for row in result.affected_vehicles:
        ac = row.booking_id.startswith("AC")
        assert row.patched_horizon_battery_kwh == pytest.approx((8.36 if ac else 29.64) * 8 / 60 * 0.98, abs=2e-6)


@pytest.mark.parametrize(
    ("bottleneck", "expected_dc"), [("connector", 60), ("cabinet", 25), ("zone", 25), ("vehicle", 16)]
)
async def test_site_increase_cannot_exceed_equipment_or_vehicle_caps(bottleneck, expected_dc):
    config = catalog.load_station_config().model_dump()
    if bottleneck == "cabinet":
        next(cab for cab in config["cabinets"] if cab["zone"] == "DC")["output_limit_kw"] = 25
    if bottleneck == "zone":
        # A valid fixed-share policy cannot budget above the physical zone cap.
        config["physical_zone_cap_kw"]["DC"] = config["zone_budgets_kw"]["DC"] = 25
    rt = _rt(config=StationConfig.model_validate(config), start=time(19, 56))
    _add(rt, "ac", hours=8 / 60)
    _add(rt, "dc", zone="DC", cap=16 if bottleneck == "vehicle" else 100, hours=8 / 60)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=8)
    result = await run_what_if(snap, _actor(rt), _site_patch(140, upgraded=True))
    profile = [(11, expected_dc, 4, 3500), (11, expected_dc, 4, 2000)]
    for branch in (result.baseline, result.patched):
        _assert_site_branch(branch, profile, ac_count=1, dc_count=1)
    assert result.hypothetical_infrastructure
    assert result.delta["horizon_output_kwh"] == result.delta["horizon_grid_input_kwh"] == 0


async def test_site_patch_replays_future_source_changes_and_cabinet_only_restriction():
    rt = _rt(start=time(19, 56))
    for zone in ("AC", "DC"):
        for i in range(2):
            _add(rt, f"{zone}-{i}", zone=zone, hours=8 / 60)
    _set_limits(
        rt, LimitEvent(2, 0, 30, {}), LimitEvent(4, 0, 100, {}), LimitEvent(6, 0, None, {"DC-01": 12}), runtime_grid=50
    )
    snap = await capture_atomic_snapshot(rt, horizon_minutes=8)
    before = rt.simulator.snapshot_physics_state()
    result = await run_what_if(snap, _actor(rt), _site_patch(80))
    # The decrease binds both branches. The increase exceeds only the patch. The later
    # cabinet restriction limits DC output to 12 kW while the AC budget still uses grid input.
    # Emergency curtailment floors each connector. At 50 -> 30 kW the binary64 expression
    # 18.525 * 0.6 * 1000 falls just below 11115. The 0.01 kW deadband retains 11.114 per DC port.
    baseline = [(10.45, 37.05, 2, 3500), (6.27, 22.228, 2, 3500), (20.9, 74.1, 2, 2000), (20.9, 12, 2, 2000)]
    patched = [(16.72, 59.28, 2, 3500), (6.27, 22.23, 2, 3500), (16.72, 59.28, 2, 2000), (16.72, 12, 2, 2000)]
    _assert_site_branch(result.baseline, baseline, ac_count=2, dc_count=2)
    _assert_site_branch(result.patched, patched, ac_count=2, dc_count=2)
    assert result.known_limit_event_count == 3
    assert rt.simulator.snapshot_physics_state() == before
    assert snap.recompute_digest() == snap.envelope.snapshot_digest


@pytest.mark.parametrize("runtime_grid", [20, 50], ids=["override-binds", "announced-source-binds"])
async def test_site_patch_preserves_announced_grid_event_effective_at_snapshot(runtime_grid, monkeypatch):
    rt = _rt(start=time(19, 56))
    for zone in ("AC", "DC"):
        for i in range(2):
            _add(rt, f"{zone}-{i}", zone=zone, hours=8 / 60)
    _set_limits(rt, LimitEvent(0, 0, 30, {}), LimitEvent(4, 0, 100, {}), runtime_grid=runtime_grid)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=8)
    assert snap.physics_state["grid_input_override_kw"] == runtime_grid
    assert snap.event_manifest.known_limit_events[0].effective_at == snap.envelope.as_of
    delivered_events = {False: [], True: []}
    on_minute = control_loop.on_minute

    async def track_grid_events(runtime, events):
        patched = runtime.simulator.kernel.sandbox_grid_cap_kw is not None
        delivered_events[patched].extend(
            (runtime.simulator.minute, event.new_power_limit_kw)
            for event in events
            if event.type == EventType.POWER_LIMIT_CHANGED
        )
        return await on_minute(runtime, events)

    monkeypatch.setattr(control_loop, "on_minute", track_grid_events)
    result = await run_what_if(snap, _actor(rt), _site_patch(80))
    first_ac_dc = (4.18, 14.82) if runtime_grid == 20 else (6.27, 22.23)
    baseline = [(*first_ac_dc, 4, 3500), (20.9, 74.1, 4, 2000)]
    patched = [(6.27, 22.23, 4, 3500), (16.72, 59.28, 4, 2000)]
    _assert_site_branch(result.baseline, baseline, ac_count=2, dc_count=2)
    _assert_site_branch(result.patched, patched, ac_count=2, dc_count=2)
    assert delivered_events == {False: [(0, min(runtime_grid, 30)), (4, 100)], True: [(0, 30), (4, 80)]}
