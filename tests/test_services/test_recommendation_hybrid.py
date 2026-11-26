"""Optimized-policy HOW-TO oracles using minute physics from the isolated station."""

import json
from datetime import timedelta

import pytest

from src.models.control import Role
from src.models.recommendation import Feasibility, SearchStatus
from src.services import catalog
from src.services.copilot import capture_atomic_snapshot, recommendation, run_recommendation
from src.services.copilot.counterfactual import run_sandbox_branch
from src.services.runtime import build_sim_runtime, visit_of
from tests.factories import NOW, booking
from tests.test_services.test_recommendation import _actor, _earliest, _max_at, _site

CAPACITY_KWH = 60.13
CONVERSION = 0.95
EFFICIENCY = 0.98


def _hybrid_runtime(policy, vehicles):
    config = catalog.load_station_config()
    scenario = catalog.load_scenario("hybrid_evening")
    assert config.grid_input_limit_kw == scenario.power_limit_kw == 106
    rt = build_sim_runtime(scenario, policy, config, catalog.load_tariff(), NOW)
    for name, zone, soc, target, deadline in vehicles:
        record = booking(name, now=rt.clock(), hours=deadline / 60, zone=zone)
        record.request.soc_now = soc
        record.request.soc_target = target
        stored = CAPACITY_KWH * (target - soc) / 100
        record.energy = record.energy.model_copy(
            update={
                "soc_now": soc,
                "soc_target": target,
                "battery_energy_kwh": stored,
                "grid_energy_kwh": stored / EFFICIENCY,
                "efficiency": EFFICIENCY,
            }
        )
        rt.store.save_booking(record)
        rt.simulator.upsert_vehicle(visit_of(record, rt.clock()))
    assert rt.scheduler.metadata["dc_charging_model"]["name"] == "synthetic_taper_v1"
    return rt


_TAPER_LOAD = (
    ("a", "DC", 66, 83, 38),
    ("dc-rival", "DC", 60, 90, 34),
    ("ac-a", "AC", 30, 35, 36),
    ("ac-b", "AC", 40, 42, 28),
)


@pytest.fixture
def minute_samples(monkeypatch):
    frames = {}

    async def capture(snapshot, **kwargs):
        assert snapshot.envelope.dc_charging_model_name == "synthetic_taper_v1"
        label = kwargs["branch_label"]
        observer = kwargs["intervention"]
        observe = observer.after_step
        frames[label] = [snapshot.physics_state]

        def read_physics(runtime):
            observe(runtime)
            assert runtime.simulator.is_fork
            state = runtime.simulator.snapshot_physics_state()
            assert (
                state["stateful_components"]["dc_charging_model"]
                == snapshot.physics_state["stateful_components"]["dc_charging_model"]
            )
            frames[label].append(state)

        monkeypatch.setattr(observer, "after_step", read_physics)
        return await run_sandbox_branch(snapshot, **kwargs)

    monkeypatch.setattr(recommendation, "run_sandbox_branch", capture)
    return frames


def _crossing(frames, name, target):
    """Derive crossing from stored kWh, independently of ledger and target events."""
    initial = frames[0]["sessions"][name]
    threshold = (target / 100 - initial["current_soc"]) * CAPACITY_KWH
    start_energy = initial["delivered_battery_kwh"]
    for frame in frames[1:]:
        stored = frame["sessions"][name]["delivered_battery_kwh"] - start_energy
        if stored >= threshold - 1e-8:
            return frame["minute"] - frames[0]["minute"]
    return None


def _soc_at(frames, name, minute):
    initial = frames[0]["sessions"][name]
    end = frames[minute]["sessions"][name]
    stored = end["delivered_battery_kwh"] - initial["delivered_battery_kwh"]
    return (initial["current_soc"] + stored / CAPACITY_KWH) * 100


def _physics_oracle(samples, branches):
    """Integrate actual meter deltas and independently check installed limits and taper."""
    port_caps = {"AC-01-1": 11, "AC-02-1": 11, "DC-01-1": 60, "DC-01-2": 60}
    assert set(samples) == set(branches)
    summaries = {}
    for label, frames in samples.items():
        site_cap = branches[label]
        peak_grid = peak_ac = peak_dc = 0.0
        mixed_minutes = 0
        dc_taper_minutes = 0
        for before, after in zip(frames, frames[1:], strict=False):
            assert after["minute"] - before["minute"] == 1
            assert len(after["occupied_connectors"]) == len(set(after["occupied_connectors"].values()))
            zones = {"AC": 0.0, "DC": 0.0}
            for name, session in after["sessions"].items():
                previous = before["sessions"][name]
                output = (session["output_kwh"] - previous["output_kwh"]) * 60
                grid = (session["delivered_grid_kwh"] - previous["delivered_grid_kwh"]) * 60
                stored = session["delivered_battery_kwh"] - previous["delivered_battery_kwh"]
                assert output >= -2e-6
                assert grid == pytest.approx(output / CONVERSION, abs=2e-6)
                assert stored == pytest.approx(output * EFFICIENCY / 60, abs=2e-8)
                if output <= 2e-6:
                    continue
                connector = session["connector_id"] or session["last_connector_id"]
                zone = connector[:2]
                zones[zone] += output
                assert output <= port_caps[connector] + 2e-6
                if zone == "DC":
                    # Configured synthetic acceptance starts tapering above 60% SOC.
                    soc = previous["current_soc"]
                    taper = max(0.05, 1 - 2.25 * max(0, soc - 0.60))
                    assert output <= 60 * taper + 2e-6
                    dc_taper_minutes += soc > 0.60
            assert zones["AC"] <= 22 + 2e-6 and zones["DC"] <= 120 + 2e-6
            total_grid = sum(zones.values()) / CONVERSION
            assert total_grid <= site_cap + 2e-6
            peak_grid = max(peak_grid, total_grid)
            peak_ac = max(peak_ac, zones["AC"])
            peak_dc = max(peak_dc, zones["DC"])
            mixed_minutes += min(zones.values()) > 2e-6
        summaries[label] = {
            "site_cap_grid_kw": site_cap,
            "peak_grid_kw": peak_grid,
            "peak_ac_output_kw": peak_ac,
            "peak_dc_output_kw": peak_dc,
            "minutes_with_both_zones_charging": mixed_minutes,
            "dc_vehicle_minutes_in_taper": dc_taper_minutes,
        }
    return summaries


def _record_oracle(record_property, result, **observations):
    record_property("result", result.model_dump_json())
    record_property("numerical_oracle", json.dumps({"dc_model": "synthetic_taper_v1", **observations}))
    assert not result.applied
    assert result.baseline_execution_count == 1
    assert result.branch_execution_count == len(result.candidate_set.values) + 1 <= 9


def _assert_safe(evidence):
    assert evidence.branch_status == "completed"
    assert not any(
        (
            evidence.hard_violations,
            evidence.rejected_allocations,
            evidence.safety_holds,
            evidence.unresolved_safety_count,
            evidence.blocked_commands,
            evidence.pending_approvals,
            evidence.pending_approval_commands,
        )
    )


async def test_m3a_dc_max_soc_uses_deadline_taper_and_keeps_original_sla(minute_samples, record_property):
    rt = _hybrid_runtime("M3a", _TAPER_LOAD)
    t = rt.clock()
    snap = await capture_atomic_snapshot(rt, horizon_minutes=60)
    goal = _max_at(rt, 18, low=70, high=90, allow_lower_target=True, allow_subject_original_sla_regression=True)
    res = await run_recommendation(snap, _actor(rt), goal)
    assert res.policy_id == "M3a"
    physics = _physics_oracle(minute_samples, dict.fromkeys(minute_samples, 106))
    assert physics["baseline"]["dc_vehicle_minutes_in_taper"]
    assert physics["baseline"]["minutes_with_both_zones_charging"]

    # Integrate the optimistic minute envelope at full connector acceptance with no contention.
    soc_bound = 0.66
    for _ in range(18):
        soc_bound += (1 - 2.25 * (soc_bound - 0.60)) * EFFICIENCY / CAPACITY_KWH
    assert soc_bound < 0.90
    reached = []
    for i, candidate in enumerate(res.candidates, start=1):
        evidence = candidate.evidence
        _assert_safe(evidence)
        measured_soc = _soc_at(minute_samples[f"candidate-{i}"], "a", 18)
        assert evidence.subject_soc_at_deadline_pct == pytest.approx(measured_soc, abs=2e-7)
        assert evidence.subject_soc_observed_at == t + timedelta(minutes=18)
        assert evidence.subject_revised.met_deadline == (measured_soc >= candidate.value - 1e-8)
        if measured_soc >= candidate.value - 1e-8:
            reached.append(candidate.value)
    assert res.candidate_set.values == (70, 75, 80, 83, 85, 90)
    assert reached == [70] and [option.value for option in res.options] == [max(reached)]
    assert res.baseline.subject_original.met_deadline
    assert res.baseline.subject_original.target_reached_at == t + timedelta(minutes=29)
    assert res.options[0].evidence.subject_original.met_deadline is False
    assert res.options[0].evidence.subject_revised.met_deadline is True
    assert res.goal.allow_lower_target and res.goal.allow_subject_original_sla_regression
    _record_oracle(record_property, res, hardware_soc_ceiling_pct=100 * soc_bound, physics=physics)


async def test_m3a_dc_deadline_changes_actual_completion_under_contention(minute_samples, record_property):
    load = (
        ("a", "DC", 30, 59, 55),
        ("dc-rival", "DC", 30, 65, 30),
        ("ac-a", "AC", 30, 35, 36),
        ("ac-b", "AC", 40, 42, 28),
    )
    rt = _hybrid_runtime("M3a", load)
    t = rt.clock()
    snap = await capture_atomic_snapshot(rt, horizon_minutes=60)
    res = await run_recommendation(
        snap, _actor(rt), _earliest(rt, 18, 42, target_soc=59, allow_subject_original_sla_regression=True)
    )
    assert res.policy_id == "M3a" and res.search_status == SearchStatus.FOUND
    physics = _physics_oracle(minute_samples, dict.fromkeys(minute_samples, 106))
    assert physics["baseline"]["minutes_with_both_zones_charging"]
    crossings = {label: _crossing(frames, "a", 59) for label, frames in minute_samples.items()}
    assert crossings["baseline"] == 37
    assert res.baseline.subject_goal_target.target_reached_at == t + timedelta(minutes=37)
    assert res.baseline.subject_release_at == t + timedelta(minutes=42)
    for i, candidate in enumerate(res.candidates, start=1):
        _assert_safe(candidate.evidence)
        minute = crossings[f"candidate-{i}"]
        attained_at = None if minute is None else t + timedelta(minutes=minute)
        assert candidate.evidence.subject_goal_target.target_reached_at == attained_at
        assert candidate.evidence.subject_revised.target_reached_at == attained_at
    winner = res.options[0]
    assert winner.value == t + timedelta(minutes=31)
    assert winner.evidence.subject_goal_target.target_reached_at == t + timedelta(minutes=31)
    assert (
        res.baseline.subject_goal_target.target_reached_at - winner.evidence.subject_goal_target.target_reached_at
    ) == timedelta(minutes=6)
    assert 31 == min(minute for label, minute in crossings.items() if label != "baseline" and minute is not None)
    assert res.candidates[-1].evidence.subject_release_at == t + timedelta(minutes=42)
    _record_oracle(record_property, res, crossings_from_stored_energy=crossings, physics=physics)


async def test_m3a_baseline_already_meets_goal_and_feasible_deadlines_do_not_improve_completion(
    minute_samples, record_property
):
    rt = _hybrid_runtime("M3a", _TAPER_LOAD)
    t = rt.clock()
    snap = await capture_atomic_snapshot(rt, horizon_minutes=60)
    res = await run_recommendation(snap, _actor(rt), _earliest(rt, 34, 38, target_soc=83))
    assert res.search_status == SearchStatus.FOUND and res.baseline.subject_original.met_deadline
    assert _crossing(minute_samples["baseline"], "a", 83) == 29
    base_attainment = res.baseline.subject_goal_target
    assert base_attainment.target_reached_at == t + timedelta(minutes=29)
    assert res.baseline.subject_release_at == t + timedelta(minutes=34)
    assert len(res.options) == 3
    for i, candidate in enumerate(res.candidates, start=1):
        _assert_safe(candidate.evidence)
        assert candidate.feasibility == Feasibility.FEASIBLE
        assert candidate.evidence.subject_revised.met_deadline
        assert candidate.evidence.subject_goal_target == base_attainment
        assert candidate.evidence.subject_release_at == res.baseline.subject_release_at
        assert _crossing(minute_samples[f"candidate-{i}"], "a", 83) == 29
    unchanged = res.options[0]
    assert unchanged.value == res.baseline.subject_original.deadline
    assert unchanged.evidence.subject_revised.target_soc == res.baseline.subject_original.target_soc
    assert unchanged.evidence.subject_original.met_deadline == res.baseline.subject_original.met_deadline
    assert unchanged.evidence.subject_release_at == res.baseline.subject_release_at
    _record_oracle(record_property, res, goal_reached_minute=29, original_release_minute=34)


async def test_m3b_shared_source_increase_and_per_booking_ac_protection(minute_samples, record_property):
    load = (
        ("a", "DC", 30, 50, 27),
        ("dc-rival", "DC", 35, 54, 27),
        ("ac-a", "AC", 30, 31, 22),
        ("ac-b", "AC", 40, 41, 22),
    )
    rt = _hybrid_runtime("M3b", load)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=45)
    actor = _actor(rt, role=Role.OPERATOR)
    goal = _site(22, 106, min_original_on_time_rate=0.75)
    res = await run_recommendation(snap, actor, goal)
    assert res.policy_id == "M3b" and res.policy_version == "1"
    caps = {f"candidate-{i}": cap for i, cap in enumerate(res.candidate_set.values, start=1)}
    physics = _physics_oracle(minute_samples, {"baseline": 106, **caps})
    required_kwh = sum(target - initial for _, _, initial, target, _ in load) * CAPACITY_KWH / 100
    low_source_ceiling = 22 * CONVERSION * EFFICIENCY * 27 / 60
    assert low_source_ceiling < required_kwh
    assert physics["candidate-1"]["peak_grid_kw"] == pytest.approx(22, abs=0.01)
    assert physics["candidate-1"]["minutes_with_both_zones_charging"]
    assert physics["candidate-7"]["minutes_with_both_zones_charging"]
    assert res.baseline.original_sla.met_count == res.baseline.original_sla.denominator == 4
    assert res.search_status == SearchStatus.PARTIAL  # Lower branches with blocked commands cannot qualify.
    assert res.candidates[0].reason == "blocked_command"
    assert res.candidate_set.values == (22, 34, 46, 58, 70, 82, 94, 106)
    rejected = res.candidates[5]
    assert rejected.evidence.original_sla.met_count == 3 and rejected.evidence.original_sla.denominator == 4
    assert rejected.reason == "original_sla_regression"
    _assert_safe(rejected.evidence)
    assert {row.booking_id: row.original.met_deadline for row in rejected.evidence.booking_sla} == {
        "a": True,
        "ac-a": False,
        "ac-b": True,
        "dc-rival": True,
    }
    assert [c.value for c in res.options] == [94, 106]
    for option in res.options:
        _assert_safe(option.evidence)
        assert not option.hypothetical_infrastructure
        assert option.evidence.original_sla.met_count == option.evidence.original_sla.denominator == 4
        for outcome in option.evidence.booking_sla:
            _, _, _, target, deadline = next(row for row in load if row[0] == outcome.booking_id)
            frames = minute_samples[f"candidate-{res.candidate_set.values.index(option.value) + 1}"]
            crossing = _crossing(frames, outcome.booking_id, target)
            assert crossing is not None and crossing <= deadline
            assert outcome.original.target_reached_at == rt.clock() + timedelta(minutes=crossing)
    _record_oracle(
        record_property,
        res,
        total_commitment_kwh=required_kwh,
        low_source_ceiling_kwh=low_source_ceiling,
        physics=physics,
    )


async def test_earliest_baseline_observes_requested_target_separately_from_original(minute_samples, record_property):
    rt = _hybrid_runtime("M3a", _TAPER_LOAD)
    t = rt.clock()
    snap = await capture_atomic_snapshot(rt, horizon_minutes=60)
    res = await run_recommendation(
        snap,
        _actor(rt),
        _earliest(rt, 38, 38, target_soc=75, allow_lower_target=True, allow_subject_original_sla_regression=True),
    )
    baseline = res.baseline
    at_75 = _crossing(minute_samples["baseline"], "a", 75)
    at_83 = _crossing(minute_samples["baseline"], "a", 83)
    assert at_75 is not None and at_83 is not None and at_75 < at_83
    assert baseline.subject_goal_target.target_soc == 75
    assert baseline.subject_goal_target.target_reached_at == t + timedelta(minutes=at_75)
    assert not baseline.subject_goal_target.already_satisfied_at_snapshot
    assert baseline.subject_original.target_soc == 83
    assert baseline.subject_original.target_reached_at == t + timedelta(minutes=at_83)
    assert baseline.subject_revised is None
    _record_oracle(record_property, res, baseline_goal_crossing=at_75, baseline_original_crossing=at_83)


async def test_evidence_identity_distinguishes_subject_goal_and_observation_time():
    rt = _hybrid_runtime("M3a", _TAPER_LOAD)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=60)
    goal = _max_at(rt, 18, low=70, high=70, allow_lower_target=True, allow_subject_original_sla_regression=True)
    actor = _actor(rt)
    first = await run_recommendation(snap, actor, goal)
    later = await run_recommendation(snap, actor, {**goal, "deadline": goal["deadline"] + timedelta(minutes=1)})
    other = await run_recommendation(snap, _actor(rt, actor_id="res-dc-rival"), {**goal, "booking_id": "dc-rival"})
    different_goal = await run_recommendation(
        snap,
        actor,
        _earliest(rt, 18, 18, target_soc=70, allow_lower_target=True, allow_subject_original_sla_regression=True),
    )
    projections = [result.baseline for result in (first, later, other, different_goal)]
    assert {evidence.input_sha256 for evidence in projections} == {snap.envelope.snapshot_digest}
    assert len({evidence.final_physics_sha256 for evidence in projections}) == 1
    assert len({evidence.ref for evidence in projections}) == 4
    first_branch, other_view = first.candidates[0].evidence, different_goal.candidates[0].evidence
    assert first_branch.input_sha256 == other_view.input_sha256
    assert first_branch.ref != other_view.ref
    repeated = await run_recommendation(snap, actor, goal)
    assert repeated.baseline.ref == first.baseline.ref
    assert repeated.candidates[0].evidence.ref == first_branch.ref
    assert "dc-rival" not in first.model_dump_json()
    assert "res-dc-rival" not in first.model_dump_json()
