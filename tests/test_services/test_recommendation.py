"""Gate 5 oracles on the real station kernel and adversarial search control cases."""

import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest
from pydantic import ValidationError

from src.models.charging import StrategyName
from src.models.control import (
    Approval,
    ApprovalKind,
    Command,
    CommandSource,
    CommandType,
    GuardVerdict,
    Role,
)
from src.models.copilot import ActorContext
from src.models.events import EventType, StationEvent
from src.models.recommendation import Feasibility, SearchStatus
from src.models.simulation_core import LimitEvent
from src.models.station import StationConfig
from src.services import catalog
from src.services.copilot import SnapshotNotReadyError, capture_atomic_snapshot, recommendation, run_recommendation
from src.services.copilot.counterfactual import run_sandbox_branch
from src.services.copilot.what_if import WhatIfForbiddenError
from src.services.runtime import build_sim_runtime, visit_of
from tests.factories import NOW, booking


def _runtime(*, config=None, limit_events=()):
    rt = build_sim_runtime(
        catalog.load_scenario("hybrid_evening"),
        StrategyName.SIM_B0,
        config or catalog.load_station_config(),
        catalog.load_tariff(),
        NOW,
    )
    rt.simulator.kernel.scenario = replace(rt.simulator.scenario, limit_events=limit_events)
    return rt


def _add(rt, name="a", *, target=21.0, minutes=30, arrival=None, zone="AC"):
    start = rt.clock()
    # Catalog fixture VF8 uses 60.13 kWh. An increase of 1 percentage point stores 0.6013 kWh.
    stored = 60.13 * (target - 20) / 100
    record = booking(name, hours=minutes / 60, now=start, arrival=arrival, zone=zone)
    record.request.soc_target = target
    record.energy = record.energy.model_copy(
        update={
            "soc_target": target,
            "battery_energy_kwh": stored,
            "grid_energy_kwh": stored / 0.98,
            "efficiency": 0.98,
        }
    )
    rt.store.save_booking(record)
    rt.simulator.upsert_vehicle(visit_of(record, start))
    return record


def _actor(rt, *, actor_id="res-a", role=Role.RESIDENT):
    return ActorContext(actor_id=actor_id, role=role, station_id=rt.config.station_id)


def _max_at(rt, minute, low=21, high=25, **changes):
    return {
        "goal": "max_soc_by_deadline",
        "booking_id": "a",
        "deadline": rt.clock() + timedelta(minutes=minute),
        "min_target_soc": low,
        "max_target_soc": high,
        "allow_lower_target": False,
        "allow_later_deadline": False,
        "allow_subject_original_sla_regression": False,
        **changes,
    }


def _earliest(rt, low, high, **changes):
    return {
        "goal": "earliest_completion_for_target",
        "booking_id": "a",
        "target_soc": 21,
        "earliest_deadline": rt.clock() + timedelta(minutes=low),
        "latest_deadline": rt.clock() + timedelta(minutes=high),
        "allow_lower_target": False,
        "allow_later_deadline": False,
        "allow_subject_original_sla_regression": False,
        **changes,
    }


def _site(low, high, **changes):
    return {
        "goal": "min_tested_site_limit_for_sla",
        "min_grid_input_kw": low,
        "max_grid_input_kw": high,
        "min_original_on_time_rate": 1,
        "protect_on_time_ac_bookings": True,
        "hypothetical_infrastructure": False,
        **changes,
    }


def _record(result, record_property):
    record_property("result", result.model_dump_json())


async def test_max_soc_deadline_positive_actual_oracle(record_property):
    rt = _runtime()
    _add(rt, target=25, minutes=46)
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=50)
    result = await run_recommendation(
        snapshot,
        _actor(rt),
        _max_at(rt, 16, low=21, high=30, allow_lower_target=True, allow_subject_original_sla_regression=True),
    )
    _record(result, record_property)
    # A 16 minute window supplies at most 2.875 kWh. 25% needs 3.0065 kWh and 30% needs 6.013 kWh.
    # 21% needs .6013 kWh. B0's initial 15-minute setpoint and one extra minute suffice.
    # The original 46-minute booking can reach 25% in its longer window.
    assert result.search_status == SearchStatus.FOUND
    assert result.candidate_set.values == (21, 25, 30)
    assert [o.value for o in result.options] == [21]
    evidence = result.options[0].evidence
    assert evidence.subject_soc_at_deadline_pct == pytest.approx(21, abs=1e-6)
    assert evidence.subject_revised.met_deadline is True
    assert evidence.subject_original.met_deadline is False
    assert result.baseline.subject_original.met_deadline is True
    assert result.baseline.subject_soc_at_deadline_pct < 25
    assert result.candidates[-1].feasibility == Feasibility.INFEASIBLE
    assert result.candidates[-1].evidence.subject_soc_at_deadline_pct < 30
    assert {c.evidence.subject_revised.deadline for c in result.candidates} == {result.goal.deadline}


async def test_max_soc_deadline_negative_actual_oracle(record_property):
    rt = _runtime()
    _add(rt)
    result = await run_recommendation(await capture_atomic_snapshot(rt, horizon_minutes=35), _actor(rt), _max_at(rt, 3))
    _record(result, record_property)
    # Even continuous 11 kW cannot supply one extra point in three minutes.
    ceiling = 20 + 11 * (3 / 60) * 0.98 / 60.13 * 100
    assert result.search_status == SearchStatus.NO_FEASIBLE and not result.options
    assert all(c.evidence.subject_soc_at_deadline_pct <= ceiling + 1e-6 for c in result.candidates)
    assert all(c.feasibility == Feasibility.INFEASIBLE for c in result.candidates)


async def test_earliest_completion_uses_actual_crossing_and_stable_tie(record_property):
    rt = _runtime()
    _add(rt)
    result = await run_recommendation(
        await capture_atomic_snapshot(rt, horizon_minutes=35), _actor(rt), _earliest(rt, 19, 23)
    )
    _record(result, record_property)
    # B0 spreads 0.6013/0.98 kWh across the initial 15-minute slot, rounded down at the command quantum.
    # A further step supplies the remainder at T+16. All five departures tie; T+23 is closest to T+30.
    expected = rt.clock() + timedelta(minutes=16)
    assert {c.evidence.subject_revised.target_reached_at for c in result.candidates} == {expected}
    assert {c.evidence.subject_revised.target_soc for c in result.candidates} == {21}
    assert [c.value for c in result.options] == [rt.clock() + timedelta(minutes=n) for n in (23, 22, 21)]
    assert result.options[0].evidence.subject_release_at == rt.clock() + timedelta(minutes=23)
    assert expected < result.options[0].evidence.subject_release_at


async def test_earliest_completion_negative_actual_oracle(record_property):
    rt = _runtime()
    _add(rt)
    result = await run_recommendation(
        await capture_atomic_snapshot(rt, horizon_minutes=35), _actor(rt), _earliest(rt, 1, 3)
    )
    _record(result, record_property)
    # A three-minute departure can deliver at most 11*.98*3/60 = .539 kWh, below .6013 kWh.
    assert result.search_status == SearchStatus.NO_FEASIBLE and not result.options
    assert all(c.evidence.subject_revised.target_reached_at is None for c in result.candidates)


async def test_site_minimum_actual_oracle_and_budget(monkeypatch, record_property):
    rt = _runtime()
    # Exactly 2.05 kW for 15 minutes, multiplied by .98, adds .50225 kWh.
    _add(rt, target=20 + 0.50225 / 60.13 * 100, minutes=16)
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=19)
    original = rt.simulator.snapshot_physics_state()
    live_bookings = [b.model_dump() for b in rt.store.active_bookings()]
    runs = []

    async def observe(snap, **kwargs):
        assert snap is snapshot
        branch = await run_sandbox_branch(snap, **kwargs)
        runs.append((branch.branch_label, branch.initial_snapshot_digest, branch.event_manifest_sha256))
        return branch

    monkeypatch.setattr(recommendation, "run_sandbox_branch", observe)
    goal = _site(7, 14)
    actor = _actor(rt, role=Role.OPERATOR)
    result = await run_recommendation(snapshot, actor, goal)
    _record(result, record_property)
    # By T+16, even uninterrupted 9 kW × .22 × .95 × .98 × 16/60 = .492 kWh, below the target.
    # 10 kW allows a 2.05 kW charger command within B0's budget plus a minute for quantization.
    assert result.search_status == SearchStatus.FOUND
    assert result.candidate_set.values == tuple(range(7, 15))
    assert result.options[0].value == 10
    assert result.candidates[0].evidence.booking_sla[0].original.met_deadline is False
    assert result.options[0].evidence.booking_sla[0].original.met_deadline is True
    assert result.options[0].evidence.original_sla.denominator == 1
    assert result.baseline_execution_count == 1 and result.branch_execution_count == 9
    assert [run[0] for run in runs] == ["baseline"] + [f"candidate-{n}" for n in range(1, 9)]
    assert {(run[1], run[2]) for run in runs} == {(result.snapshot_sha256, result.event_manifest_sha256)}
    repeated = await run_recommendation(snapshot, actor, goal)
    assert [(c.value, c.feasibility, c.evidence.ref, c.evidence.final_physics_sha256) for c in repeated.candidates] == [
        (c.value, c.feasibility, c.evidence.ref, c.evidence.final_physics_sha256) for c in result.candidates
    ]
    assert result.applied is False
    assert rt.simulator.snapshot_physics_state() == original
    assert [b.model_dump() for b in rt.store.active_bookings()] == live_bookings


async def test_site_extra_supply_cannot_remove_ac_connector_bottleneck(record_property):
    rt = _runtime()
    _add(rt, target=30, minutes=20)
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=22)
    actor = _actor(rt, role=Role.OPERATOR)
    with pytest.raises(ValueError, match="hypothetical_infrastructure"):
        await run_recommendation(snapshot, actor, _site(105, 125))
    result = await run_recommendation(snapshot, actor, _site(105, 125, hypothetical_infrastructure=True))
    _record(result, record_property)
    # 11 kW at the connector for twenty minutes cannot add ten percentage points, even at 100% efficiency.
    assert result.search_status == SearchStatus.NO_FEASIBLE
    assert not result.options and result.candidates[-1].hypothetical_infrastructure
    assert all(c.evidence.booking_sla[0].original.met_deadline is False for c in result.candidates)


async def test_site_unknown_does_not_shrink_denominator(record_property):
    rt = _runtime()
    _add(rt)
    _add(rt, "future-private", arrival=rt.clock() + timedelta(minutes=50))
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=35)
    result = await run_recommendation(snapshot, _actor(rt, role=Role.OPERATOR), _site(12, 12))
    _record(result, record_property)
    sla = result.candidates[0].evidence.original_sla
    assert (sla.cohort_size, sla.denominator, sla.met_count, sla.censored_count) == (2, 1, 1, 1)
    assert result.search_status == SearchStatus.PARTIAL and not result.options
    assert result.candidates[0].reason == "unknown_sla"
    assert result.candidates[0].evidence.booking_sla[1].original.met_deadline is None


async def test_site_ac_protection_is_per_booking_even_at_allowed_rate():
    rt = _runtime()
    _add(rt, target=23, minutes=16)
    _add(rt, "easy", target=20.1)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=35)
    actor = _actor(rt, role=Role.OPERATOR)
    without = await run_recommendation(
        snap, actor, _site(10, 10, min_original_on_time_rate=0.5, protect_on_time_ac_bookings=False)
    )
    with_ac = await run_recommendation(snap, actor, _site(10, 10, min_original_on_time_rate=0.5))
    assert without.search_status == SearchStatus.FOUND
    assert without.baseline.original_sla.met_count == 2
    assert without.options[0].evidence.original_sla.met_count == 1
    assert [(row.booking_id, row.original.met_deadline) for row in without.options[0].evidence.booking_sla] == [
        ("a", False),
        ("easy", True),
    ]
    assert with_ac.search_status == SearchStatus.NO_FEASIBLE
    assert with_ac.candidates[0].reason == "original_sla_regression"


async def test_site_independent_unsupported_has_no_rollouts():
    raw = catalog.load_station_config().model_dump()
    raw.update({"supply_mode": "independent", "independent_grid_input_limit_kw": {"AC": 30, "DC": 90}})
    rt = _runtime(config=StationConfig.model_validate(raw))
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=5)
    result = await run_recommendation(snapshot, _actor(rt, role=Role.OPERATOR), _site(5, 50))
    assert result.search_status == SearchStatus.UNSUPPORTED
    assert result.unsupported_reason == "independent_supply" and result.branch_execution_count == 0


async def test_role_ownership_station_and_explicit_sacrifices():
    rt = _runtime()
    _add(rt)
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=35)
    actor, operator = _actor(rt), _actor(rt, role=Role.OPERATOR)
    goal = _max_at(rt, 20)
    for identity, request in (
        (actor.model_copy(update={"station_id": "another-station"}), goal),
        (actor.model_copy(update={"actor_id": "another-resident"}), goal),
        (actor, {**goal, "booking_id": "missing"}),
        (operator, goal),
        (actor, _site(5, 7)),
    ):
        with pytest.raises(WhatIfForbiddenError, match="^HOW-TO operation not allowed$"):
            await run_recommendation(snapshot, identity, request)
    with pytest.raises(ValidationError):
        await run_recommendation(snapshot, actor, {k: v for k, v in goal.items() if k != "allow_lower_target"})
    with pytest.raises(ValueError, match="simulator minutes"):
        await run_recommendation(snapshot, actor, {**goal, "deadline": goal["deadline"] + timedelta(seconds=1)})
    changed = await run_recommendation(snapshot, actor, _max_at(rt, 31, low=20, high=20))
    assert changed.candidates[0].reason == "sacrifice_not_allowed" and changed.branch_execution_count == 1
    assert changed.options == ()


@pytest.mark.parametrize("mode", ("timeout", "cancelled", "execution_failed"))
async def test_partial_retains_prior_feasible_and_records_failures(mode, monkeypatch, record_property):
    rt = _runtime()
    _add(rt)
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=34)
    cancelled = asyncio.Event()
    runs = []

    async def interfere(snap, **kwargs):
        label = kwargs["branch_label"]
        runs.append(label)
        if label == "candidate-2":
            if mode == "timeout":
                async with asyncio.timeout(0.001):
                    await asyncio.sleep(10)
            if mode == "cancelled":
                cancelled.set()
            if mode == "execution_failed":
                raise RuntimeError("injected failure")
        return await run_sandbox_branch(snap, **kwargs)

    monkeypatch.setattr(recommendation, "run_sandbox_branch", interfere)
    result = await run_recommendation(snapshot, _actor(rt), _earliest(rt, 20, 22), cancel_event=cancelled)
    _record(result, record_property)
    assert result.search_status == SearchStatus.PARTIAL
    assert result.candidates[1].reason == mode and result.candidates[1].status == "failed"
    assert [o.value for o in result.options][-1] == rt.clock() + timedelta(minutes=20)
    if mode == "execution_failed":
        assert runs == ["baseline", "candidate-1", "candidate-2", "candidate-3"]
    else:
        assert runs == ["baseline", "candidate-1", "candidate-2"]
        assert result.candidates[2].status == "skipped" and result.candidates[2].reason == mode
    assert result.branch_execution_count == len(runs)


async def test_external_task_cancellation_propagates(monkeypatch):
    rt = _runtime()
    _add(rt)
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=35)
    started = asyncio.Event()

    async def wait(*args, **kwargs):
        started.set()
        await asyncio.sleep(10)

    monkeypatch.setattr(recommendation, "run_sandbox_branch", wait)
    task = asyncio.create_task(run_recommendation(snapshot, _actor(rt), _max_at(rt, 20)))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_earliest_nonmonotonic_crossing_searches_every_candidate(monkeypatch):
    rt = _runtime()
    _add(rt)
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=35)
    # Synthetic rollout oracle for an arbitrary non-monotonic completion response. It wraps actual
    # branch execution and substitutes only the independent original-target timestamp in the ledger.
    instants = (None, 17, None, 11, 15)
    calls = []

    async def oracle(snap, **kwargs):
        branch = await run_sandbox_branch(snap, **kwargs)
        label = kwargs["branch_label"]
        calls.append(label)
        if label == "baseline":
            return branch
        minute = instants[int(label[-1]) - 1]
        reached_at = None if minute is None else rt.clock() + timedelta(minutes=minute)
        (subject,) = branch.outcome_ledger.vehicles
        row = subject.model_copy(update={"target_reached_at": reached_at})
        return branch.model_copy(
            update={"outcome_ledger": branch.outcome_ledger.model_copy(update={"vehicles": [row]})}
        )

    monkeypatch.setattr(recommendation, "run_sandbox_branch", oracle)
    result = await run_recommendation(snapshot, _actor(rt), _earliest(rt, 20, 24))
    assert calls == ["baseline"] + [f"candidate-{n}" for n in range(1, 6)]
    assert [o.value for o in result.options] == [rt.clock() + timedelta(minutes=m) for m in (23, 24, 21)]


async def test_announced_decrease_replayed_and_unknown_increase_excluded():
    rt = _runtime(limit_events=(LimitEvent(1, 0, 1, {}), LimitEvent(2, 1, 106, {})))
    _add(rt, minutes=20)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=22)
    result = await run_recommendation(snap, _actor(rt, role=Role.OPERATOR), _site(50, 50))
    # Even 1 minute at 11 kW + 19 minutes at 1 kW is below .6013 kWh, before losses.
    assert len(snap.event_manifest.known_limit_events) == 1
    assert result.event_manifest_sha256 == snap.event_manifest.manifest_sha256
    assert result.baseline.booking_sla[0].original.met_deadline is False
    assert result.candidates[0].evidence.booking_sla[0].original.met_deadline is False
    assert result.search_status == SearchStatus.NO_FEASIBLE


async def test_resident_evidence_excludes_other_vehicle_and_protects_commitments():
    rt = _runtime()
    subject = _add(rt, minutes=30)
    # An arrived owner and an unrelated reservation. The projection cannot reveal the latter.
    other = _add(rt, "not-my-vehicle", arrival=rt.clock() + timedelta(minutes=55))
    snap = await capture_atomic_snapshot(rt, horizon_minutes=32)
    result = await run_recommendation(snap, _actor(rt), _max_at(rt, 20, low=21, high=21))
    assert result.search_status == SearchStatus.PARTIAL
    assert result.candidates[0].reason == "unknown_sla" and not result.options
    payload = result.model_dump_json()
    assert subject.booking_id == result.goal.booking_id
    assert other.booking_id not in payload and other.resident_id not in payload


async def test_max_soc_beyond_horizon_is_unknown():
    rt = _runtime()
    _add(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=10)
    result = await run_recommendation(snap, _actor(rt), _max_at(rt, 20))
    assert result.search_status == SearchStatus.PARTIAL
    assert all(candidate.reason == "incomplete_observation" for candidate in result.candidates)
    assert all(candidate.evidence.subject_soc_at_deadline_pct is None for candidate in result.candidates)


@pytest.mark.parametrize("safety", ("safety_hold", "pending_approval", "pending_hard_safety"))
async def test_pending_safety_and_hitl_prevent_recommendation(safety):
    rt = _runtime()
    booking_a = _add(rt)
    now = rt.clock()
    if safety == "safety_hold":
        rt.safety_hold_booking_ids.add(booking_a.booking_id)
    elif safety == "pending_approval":
        command = Command(
            type=CommandType.SET_POWER,
            connector_id="AC-01-1",
            power_kw=5,
            booking_id=booking_a.booking_id,
            source=CommandSource.OPTIMIZER,
            issued_by="optimizer",
            based_on_schedule_version=1,
            based_on_state_at=now,
            created_at=now,
        )
        rt.sinks.save_approval(
            Approval(
                kind=ApprovalKind.RESIDENT_CONSENT,
                command=command,
                verdict=GuardVerdict(command_id=command.command_id, passed=True, checked_at=now),
                requested_from=booking_a.resident_id,
                impact_summary="Fixture",
                created_at=now,
            )
        )
    else:
        rt.queue_events(
            [
                StationEvent(
                    type=EventType.HARD_LIMIT_VIOLATED,
                    occurred_at=now,
                    violation_kinds=["charging_model"],
                )
            ]
        )
        with pytest.raises(SnapshotNotReadyError):
            await capture_atomic_snapshot(rt, horizon_minutes=35)
        return

    snap = await capture_atomic_snapshot(rt, horizon_minutes=35)
    before = rt.simulator.snapshot_physics_state()
    result = await run_recommendation(snap, _actor(rt), _max_at(rt, 20))
    assert result.search_status == SearchStatus.PARTIAL and not result.options
    assert result.baseline_issue == safety
    assert result.branch_execution_count == 1
    assert all(candidate.status == "skipped" for candidate in result.candidates)
    assert rt.simulator.snapshot_physics_state() == before


async def test_unsafe_or_pending_candidate_is_never_ranked(monkeypatch):
    rt = _runtime()
    _add(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=35)

    async def unsafe(snapshot, **kwargs):
        branch = await run_sandbox_branch(snapshot, **kwargs)
        if branch.branch_label == "candidate-2":
            return branch.model_copy(update={"status": "unresolved_safety", "unresolved_safety_count": 1})
        if branch.branch_label == "candidate-3":
            return branch.model_copy(update={"pending_approval_count_end": 1})
        return branch

    monkeypatch.setattr(recommendation, "run_sandbox_branch", unsafe)
    result = await run_recommendation(snap, _actor(rt), _earliest(rt, 20, 22))
    assert result.search_status == SearchStatus.PARTIAL
    assert [o.value for o in result.options] == [rt.clock() + timedelta(minutes=20)]
    assert [c.reason for c in result.candidates[1:]] == ["unsafe", "pending_approval"]


async def test_changed_snapshot_is_rejected_before_rollout():
    rt = _runtime()
    _add(rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=35)
    changed = replace(snap, station_config=snap.station_config.model_copy(update={"grid_input_limit_kw": 5}))
    with pytest.raises(ValueError, match="Snapshot integrity check failed"):
        await run_recommendation(changed, _actor(rt), _max_at(rt, 20))


async def test_actual_search_timeout_stops_baseline_and_skips_candidates():
    rt = _runtime()
    _add(rt)
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=35)
    result = await run_recommendation(
        snapshot, _actor(rt), _earliest(rt, 20, 22), timeout_s=0.02, live_busy_probe=lambda: True
    )
    assert result.search_status == SearchStatus.PARTIAL
    assert result.baseline_issue == "timeout" and result.branch_execution_count == 1
    assert all(c.status == "skipped" and c.reason == "timeout" for c in result.candidates)
    assert not result.options
