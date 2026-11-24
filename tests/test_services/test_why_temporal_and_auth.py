"""WP2.6 — Temporal resolution (G1-F06), restart stale traces, authorization & privacy projection tests (Gate 2).

Covers every required temporal and security case:
- Trace starting before query window and overlapping into it + exact sub-window measured calculation.
- Trace closed early by replan (effective_end < planned_end).
- Multiple decisions at the exact same timestamp.
- Multi-trace window with different policies (per-fact provenance preserved, no misattribution).
- Stale active trace left in DB after process restart (never treated as infinitely active).
- Temporal gap between traces, zero-sample trace, incomplete measured coverage (with and without violation).
- Legacy summary-only DB record (`full_payload=None`).
- Query beyond available data & pagination truncation.
- Resident ownership (active + historical), non-enumerating FORBIDDEN (unauthorized vs nonexistent ID),
  cross-resident privacy projection across all 6 topics, and EvidenceRef dereference auth bypass block.
"""

import json
from datetime import datetime, timedelta

import pytest

pytest.importorskip("ev2gym")

from src.models.charging import BookingStatus  # noqa: E402
from src.models.control import Role  # noqa: E402
from src.models.copilot import (  # noqa: E402
    ActorContext,
    EvidenceRef,
    TimeWindow,
    WhyQuery,
    WhyStatus,
    WhySubjectScope,
    WhyTopic,
)
from src.models.decision_trace import TRACE_SCHEMA  # noqa: E402
from src.models.identity import UserRecord  # noqa: E402
from src.services import decision_trace, repository  # noqa: E402
from src.services.copilot import explain_why  # noqa: E402
from src.services.copilot.evidence import resolve_evidence_ref  # noqa: E402
from tests.factories import VN, booking  # noqa: E402

T0 = datetime(2026, 11, 24, 18, 0, tzinfo=VN)
STATION_ID = "CHARGEPILOT-MVP1"


def _operator(station_id: str = STATION_ID) -> ActorContext:
    return ActorContext(actor_id="op-1", role=Role.OPERATOR, station_id=station_id)


def _resident(actor_id: str, station_id: str = STATION_ID) -> ActorContext:
    return ActorContext(actor_id=actor_id, role=Role.RESIDENT, station_id=station_id)


def _seed_user_and_booking(bid: str, resident_id: str, *, status: BookingStatus = BookingStatus.CONFIRMED):
    repository.upsert_user(
        UserRecord(
            user_id=resident_id,
            email=f"{resident_id}@example.invalid",
            role=Role.RESIDENT,
            display_name=resident_id,
            created_at=T0,
        )
    )
    b = booking(bid, zone="DC", kwh=35.0, hours=2.0, now=T0).model_copy(
        update={"resident_id": resident_id, "status": status}
    )
    repository.save_booking(b)
    return b


def _synthetic_trace(
    cid: str,
    decided_at: datetime,
    *,
    minute: int = 0,
    planned_minutes: int = 15,
    closed: bool = True,
    closed_after_minutes: int | None = None,
    policy_id: str = "M3a",
    policy_version: str = "1",
    schedule_version: int = 1,
    booking_kw_samples: list[tuple[int, dict[str, float]]] | None = None,
    coverage_status: str | None = None,
    post_apply: str | None = None,
    hard_violations: list[str] | None = None,
    held_booking_ids: list[str] | None = None,
    waiting_dc: list[str] | None = None,
) -> dict:
    """Build a valid `chargepilot.backend_decision_trace/2` payload with explicit temporal metadata."""
    start_at = decided_at
    planned_end_at = decided_at + timedelta(minutes=planned_minutes)
    samples_spec = booking_kw_samples if booking_kw_samples is not None else []
    eff_dur = (
        closed_after_minutes if closed_after_minutes is not None else (len(samples_spec) if closed else planned_minutes)
    )
    closed_at = decided_at + timedelta(minutes=eff_dur) if closed else None

    all_vids = set(waiting_dc or ()) | set(held_booking_ids or ())
    for _, kw_map in samples_spec:
        all_vids.update(kw_map.keys())
    if not all_vids:
        all_vids = {"b-a"}

    proposed_map = {vid: 30.0 for vid in sorted(all_vids) if vid not in (waiting_dc or ())}
    actual_samples = []
    held_samples = []
    output_kwh: dict[str, float] = {}
    sample_mins: dict[str, int] = {}
    for offset, kw_map in samples_spec:
        sm = minute + offset
        em = sm + 1
        s_at = (decided_at + timedelta(minutes=offset)).isoformat()
        e_at = (decided_at + timedelta(minutes=offset + 1)).isoformat()
        actual_samples.append(
            {"start_minute": sm, "end_minute": em, "start_at": s_at, "end_at": e_at, "by_booking_kw": dict(kw_map)}
        )
        held_samples.append(
            {"start_minute": sm, "end_minute": em, "start_at": s_at, "end_at": e_at, "by_booking_kw": dict(kw_map)}
        )
        for vid, kw in kw_map.items():
            output_kwh[vid] = output_kwh.get(vid, 0.0) + kw / 60.0
            sample_mins[vid] = sample_mins.get(vid, 0) + 1

    avg_kw = {vid: output_kwh[vid] * 60.0 / sample_mins[vid] for vid in sample_mins}
    grid_kwh = {vid: kwh / 0.95 for vid, kwh in output_kwh.items()}
    retained_mins = len(samples_spec)
    cov = coverage_status or (
        "not_evaluated"
        if not closed
        else (
            "complete"
            if retained_mins == eff_dur and retained_mins > 0
            else ("no_samples" if retained_mins == 0 else "incomplete")
        )
    )
    post = post_apply or (
        "not_evaluated"
        if not closed
        else (
            "violation"
            if hard_violations
            else ("incomplete" if cov == "incomplete" else ("pass" if avg_kw else "no_samples"))
        )
    )

    vehicles_obs = {}
    for vid in sorted(all_vids):
        is_wait = vid in (waiting_dc or ())
        vehicles_obs[vid] = {
            "zone": "DC",
            "state": "QUEUED" if is_wait else "CHARGING",
            "connector_id": None if is_wait else "DC-01-1",
            "queue_position": (waiting_dc.index(vid) + 1) if is_wait and waiting_dc else None,
            "planned_assigned_connector": None,
            "soc": 0.35,
            "target_soc": 0.80,
            "deadline_minute": minute + 90,
            "deadline_at": (decided_at + timedelta(minutes=90)).isoformat(),
            "remaining_kwh": 27.0,
            "vehicle_max_output_kw": 60.0,
            "allowed_output_kw": 60.0,
            "completed_at_minute": None,
            "completed_at": None,
        }

    trace = {
        "trace_schema": TRACE_SCHEMA,
        "correlation_id": cid,
        "station_id": STATION_ID,
        "decided_at": decided_at.isoformat(),
        "minute": minute,
        "trigger": {"type": "tick", "event_id": f"ev-{cid}", "booking_id": None, "batched": []},
        "policy": {"id": policy_id, "version": policy_version},
        "state_version": schedule_version,
        "experiment": {
            "policy_id": policy_id,
            "policy_version": policy_version,
            "dc_charging_model": {"name": "synthetic_taper_v1", "version": "1"},
            "fingerprint": f"fp-{policy_id}",
        },
        "schedule_version": schedule_version,
        "time_config": {"physics_step_minutes": 1, "decision_interval_minutes": 15, "planning_horizon_minutes": None},
        "interval": {
            "start_minute": minute,
            "end_minute": minute + planned_minutes,
            "planning_interval_minutes": planned_minutes,
            "start_at": start_at.isoformat(),
            "end_at": planned_end_at.isoformat(),
        },
        "reason_codes": ["PLANNED"],
        "budgets_kw": {"AC": 22.0, "DC": 78.0},
        "proposed_setpoints_kw": proposed_map,
        "approved_setpoints_kw": proposed_map,
        "consent": {"adjustments_kw": {}, "rechecked_by_physical_guard": False},
        "guard_inputs": None,
        "commands": [
            {
                "command_id": f"cmd-{cid}-{vid}",
                "recorded_at": decided_at.isoformat(),
                "type": "set_power",
                "source": "optimizer",
                "connector_id": "DC-01-1",
                "booking_id": vid,
                "power_kw": kw,
                "guard_passed": True,
                "violations": [],
                "approval_id": None,
                "executed": True,
                "note": "",
            }
            for vid, kw in proposed_map.items()
        ],
        "emergency_commands": [],
        "held_for_pending_approval": [],
        "command_exclusions": [],
        "validation": {
            "pre_apply_physical": "pass",
            "business_guard": {"status": "evaluated", "source": "commands, emergency_commands"},
            "post_apply": post,
            "fail_safe": {"status": "not_triggered", "command_ids": [], "outcomes": []},
        },
        "safety": {
            "hard_limit_violations": [],
            "held_booking_ids": list(held_booking_ids or ()),
            "by_booking": {vid: {"safety_hold": True} for vid in (held_booking_ids or ())},
        },
        "planned": {
            "minute": minute,
            "end_minute": minute + planned_minutes,
            "interval_minutes": planned_minutes,
            "planning_interval_minutes": planned_minutes,
            "interval_start_at": start_at.isoformat(),
            "interval_end_at": planned_end_at.isoformat(),
            "algorithms": {
                "dispatch": {"AC": "fifo", "DC": "llf" if policy_id != "B0" else "fcfs"},
                "optimizers": {
                    "AC": "equal_share" if policy_id == "B0" else "ac_rolling_lp",
                    "DC": "equal_share" if policy_id == "B0" else "rolling_lp",
                },
                "coordinator": "fixed_share",
            },
            "observed": {
                "ports": {
                    "DC-01-1": {
                        "port": "DC-01/P1",
                        "cabinet_id": "DC-01",
                        "zone": "DC",
                        "port_limit_kw": 60.0,
                        "faulted": False,
                        "occupied_booking_id": "b-a",
                    }
                },
                "zone_summary": {
                    "DC": {
                        "total_ports": 2,
                        "occupied_ports": 2 if waiting_dc else 1,
                        "empty_ports": 0 if waiting_dc else 1,
                        "faulted_ports": 0,
                        "waiting_count": len(waiting_dc or ()),
                    }
                },
                "queues_by_zone": {"DC": list(waiting_dc or ())},
                "empty_connectors_by_zone": {"DC": [] if waiting_dc else ["DC-01-2"]},
                "faulted_connectors": [],
                "vehicles": vehicles_obs,
            },
            "dispatch": {
                "DC": {
                    "policy": "fcfs" if policy_id == "B0" else "llf",
                    "waiting_before": list(waiting_dc or ()),
                    "empty_connectors_before": [] if waiting_dc else ["DC-01-2"],
                    "planned_assignments": {},
                    "waiting_after_plan": list(waiting_dc or ()),
                }
            },
            "dc_waiting_laxity": {},
            "demand_output_kw": {"DC": 60.0},
            "physical_limits": {
                "grid_input_kw": 106.0,
                "grid_input_unbounded": False,
                "supply_mode": "shared",
                "independent_grid_input_kw": None,
                "zone_output_kw": {"AC": 22.0, "DC": 120.0},
                "cabinet_output_kw": {"DC-01": 120.0},
                "port_output_kw": {"DC-01-1": 60.0, "DC-01-2": 60.0},
                "conversion_efficiency": 0.95,
                "charging_efficiency": 0.98,
            },
            "coordinator": {
                "policy": "fixed_share",
                "assigned_output_kw": {"AC": 22.0, "DC": 78.0},
                "default_zone_budget_kw": {"AC": 22.0, "DC": 78.0},
                "requested_output_kw": {"DC": 60.0},
                "reason_codes": {"DC": ["fixed_share"]},
                "fallback_reason": None,
                "diagnostics": {},
            },
            "optimizers": {
                "DC": {
                    "policy": "equal_share" if policy_id == "B0" else "rolling_lp",
                    "solver_status": "not_applicable" if policy_id == "B0" else "optimal",
                    "fallback_reason": None,
                    "projected_shortfall_kwh": None if policy_id == "B0" else {vid: 0.0 for vid in proposed_map},
                }
            },
            "binding_constraints": [],
            "tariff": None,
        },
        "power": {
            "proposed": {"unit": "kW", "source": "kernel.proposal", "by_booking_kw": proposed_map},
            "approved": {"unit": "kW", "source": "kernel.approval", "by_booking_kw": proposed_map},
            "dispatched": {
                "unit": "kW",
                "source": "dispatcher",
                "command_ids": [f"cmd-{cid}-{vid}" for vid in proposed_map],
            },
            "effective_setpoint": (
                {"unit": "kW", "source": "kernel.held_setpoints", "samples": held_samples}
                if closed and held_samples
                else None
            ),
            "actual_output": (
                {
                    "unit": "kW",
                    "source": "physics.applied_result.actual_kw",
                    "samples": actual_samples,
                    "sample_minutes_by_booking": sample_mins,
                    "average_by_booking_kw": avg_kw,
                }
                if closed and actual_samples
                else None
            ),
        },
        "decision": None,
        "applied": (
            {
                "from_minute": actual_samples[0]["start_minute"] if actual_samples else None,
                "to_minute": actual_samples[-1]["end_minute"] if actual_samples else None,
                "from_at": actual_samples[0]["start_at"] if actual_samples else None,
                "to_at": actual_samples[-1]["end_at"] if actual_samples else None,
                "closed_at": closed_at.isoformat() if closed_at else None,
                "minutes": retained_mins,
                "output_kwh": output_kwh,
                "battery_stored_kwh": {vid: kwh * 0.98 for vid, kwh in output_kwh.items()},
                "grid_input_kwh": grid_kwh,
                "completed": [],
                "hard_violations": list(hard_violations or ()),
                "hard_violation_details": [],
                "budget_deviation_kw": {},
                "budget_deviation_minutes": 0,
                "command_deadband_kw": {},
                "command_deadband_minutes": 0,
                "stale_setpoint_kw": {},
                "coverage": {
                    "status": cov,
                    "expected_from_minute": minute,
                    "expected_to_minute": minute + eff_dur,
                    "expected_from_at": decided_at.isoformat(),
                    "expected_to_at": closed_at.isoformat() if closed_at else None,
                    "expected_minutes": eff_dur,
                    "retained_minutes": retained_mins,
                    "dropped_minutes": max(0, eff_dur - retained_mins) if cov == "incomplete" else 0,
                    "dropped_hard_violations": 0,
                },
            }
            if closed
            else None
        ),
        "booking_ids": sorted(all_vids),
        "closed": closed,
        "evidence_refs": {},
    }
    return trace


# ---- 1. G1-F06 Temporal Resolution Tests (DB-backed SQLite) -------------------------------


def test_temporal_overlap_pre_window_trace_and_exact_subwindow_average(clean_db):
    _seed_user_and_booking("b-a", "res-a")
    # Trace decided at 18:00 covers [18:00, 18:10): first 5 min = 10 kW, next 5 min = 20 kW (full-trace avg = 15 kW)
    samples = [(m, {"b-a": 10.0 if m < 5 else 20.0}) for m in range(10)]
    t1 = _synthetic_trace(
        "t-pre", T0, minute=0, planned_minutes=15, closed=True, closed_after_minutes=10, booking_kw_samples=samples
    )
    decision_trace.persist(t1, True)

    # Query sub-window [18:05, 18:10) -> must overlap t-pre AND compute 20.0 kW (NOT full-trace avg 15.0 kW!)
    ans = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            window=TimeWindow(start=T0 + timedelta(minutes=5), end=T0 + timedelta(minutes=10)),
        ),
        _operator(),
        station_id=STATION_ID,
    )
    assert ans.status == WhyStatus.OK
    assert [t.correlation_id for t in ans.traces] == ["t-pre"]
    avg_fact = next(f for f in ans.facts if f.name == "power.measured_actual_output_avg_kw")
    assert avg_fact.value == pytest.approx(20.0, abs=1e-4)
    kwh_fact = next(f for f in ans.facts if f.name == "energy.measured_output_kwh")
    assert kwh_fact.value == pytest.approx(20.0 * 5 / 60, abs=1e-4)


def test_early_replan_truncates_effective_interval_and_same_timestamp_returns_both(clean_db):
    _seed_user_and_booking("b-a", "res-a")
    # Two decisions at exact T0: t0a (point decision v1) and t0b (planned 15m, closed early at +4m)
    t0a = _synthetic_trace(
        "t-0a",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=0,
        schedule_version=1,
        booking_kw_samples=[],
    )
    t0b = _synthetic_trace(
        "t-0b",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=4,
        schedule_version=2,
        policy_id="B0",
        booking_kw_samples=[(m, {"b-a": 12.0}) for m in range(4)],
    )
    t1 = _synthetic_trace(
        "t-1",
        T0 + timedelta(minutes=4),
        minute=4,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=6,
        schedule_version=3,
        policy_id="M3a",
        booking_kw_samples=[(m, {"b-a": 30.0}) for m in range(6)],
    )
    for t in (t0a, t0b, t1):
        decision_trace.persist(t, True)

    # As-of exact T0: returns BOTH t-0a and t-0b in chronological/version order
    ans_t0 = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=WhyTopic.POLICY, at=T0),
        _operator(),
        station_id=STATION_ID,
    )
    assert [t.correlation_id for t in ans_t0.traces] == ["t-0a", "t-0b"]
    # Different policies -> top-level policy_id is None, per-fact provenance carries exact policy!
    assert ans_t0.policy_id is None
    assert ans_t0.decision_time is None
    assert {(f.correlation_id, f.policy_id) for f in ans_t0.facts if f.name == "policy.id"} == {
        ("t-0a", "M3a"),
        ("t-0b", "B0"),
    }

    # As-of T0+6m: t-0b closed early at +4m, so ONLY t-1 matches (NOT t-0b even though planned_end was +15m!)
    ans_t6 = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            at=T0 + timedelta(minutes=6),
        ),
        _operator(),
        station_id=STATION_ID,
    )
    assert [t.correlation_id for t in ans_t6.traces] == ["t-1"]
    assert ans_t6.policy_id == "M3a"


def test_stale_active_trace_after_restart_is_never_infinitely_active(clean_db):
    _seed_user_and_booking("b-a", "res-a")
    # Old active trace saved before crash/restart (planned 15m, never closed)
    stale_active = _synthetic_trace("t-stale", T0, minute=0, planned_minutes=15, closed=False, schedule_version=1)
    decision_trace.persist(stale_active, False)

    # Query 2 hours later after restart (no live open trace) -> MUST NOT match stale_active!
    ans_later = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            at=T0 + timedelta(hours=2),
        ),
        _operator(),
        station_id=STATION_ID,
        live_open_correlation_id=None,
        live_open_known=True,
    )
    assert ans_later.status == WhyStatus.NO_DATA
    assert "stale_active_trace_unclosed_after_restart" in ans_later.missing_evidence
    assert "query_exceeds_available_evidence" in ans_later.missing_evidence

    # Query within [T0, T0+15m) after restart with live_open_known=True (different/None open trace) -> flagged stale_after_restart
    ans_during = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            at=T0 + timedelta(minutes=3),
        ),
        _operator(),
        station_id=STATION_ID,
        live_open_correlation_id=None,
        live_open_known=True,
    )
    assert ans_during.status == WhyStatus.PARTIAL
    assert ans_during.traces[0].stale_after_restart is True
    assert "stale_active_trace_unclosed_after_restart" in ans_during.missing_evidence


def test_temporal_gap_zero_sample_incomplete_with_violation_legacy_and_truncation(clean_db):
    _seed_user_and_booking("b-a", "res-a")
    # Trace 1: [18:00, 18:05) normal; Gap [18:05, 18:10); Trace 2: [18:10, 18:15) incomplete + hard violation
    t1 = _synthetic_trace(
        "t-gap-1",
        T0,
        minute=0,
        planned_minutes=5,
        closed=True,
        closed_after_minutes=5,
        schedule_version=1,
        booking_kw_samples=[(m, {"b-a": 25.0}) for m in range(5)],
    )
    t2 = _synthetic_trace(
        "t-gap-2",
        T0 + timedelta(minutes=10),
        minute=10,
        planned_minutes=5,
        closed=True,
        closed_after_minutes=5,
        schedule_version=2,
        booking_kw_samples=[(3, {"b-a": 25.0}), (4, {"b-a": 25.0})],  # 3 minutes evicted!
        coverage_status="incomplete",
        post_apply="violation",
        hard_violations=["grid limit exceeded"],
    )
    decision_trace.persist(t1, True)
    decision_trace.persist(t2, True)

    # Window covering [18:00, 18:15) detects BOTH gap AND incomplete coverage AND preserves violation!
    ans_gap = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            window=TimeWindow(start=T0, end=T0 + timedelta(minutes=15)),
        ),
        _operator(),
        station_id=STATION_ID,
    )
    assert ans_gap.status == WhyStatus.PARTIAL
    assert "temporal_gap_in_window" in ans_gap.missing_evidence
    assert "incomplete_measured_coverage" in ans_gap.missing_evidence
    assert "POST_APPLY_HARD_VIOLATION" in {r.code for r in ans_gap.reasons}

    # Truncation when limit=1 over 2 overlapping traces
    ans_trunc = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            window=TimeWindow(start=T0, end=T0 + timedelta(minutes=15)),
            limit=1,
        ),
        _operator(),
        station_id=STATION_ID,
    )
    assert ans_trunc.truncated is True
    assert ans_trunc.status == WhyStatus.PARTIAL
    assert "trace_window_truncated" in ans_trunc.missing_evidence

    # Legacy summary-only record at T0 + 1h
    legacy_time = T0 + timedelta(hours=1)
    legacy_t = _synthetic_trace("t-legacy", legacy_time, minute=60, closed=True)
    repository.save_decision_trace(decision_trace.summary(legacy_t), None)
    ans_legacy = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic=WhyTopic.POWER, at=legacy_time),
        _operator(),
        station_id=STATION_ID,
    )
    assert ans_legacy.status == WhyStatus.NO_DATA
    assert "legacy_summary_only_trace" in ans_legacy.missing_evidence


# ---- 2. Authorization & Privacy Projection Tests ------------------------------------------


def test_resident_authorization_non_enumerating_and_historical_booking_access(clean_db):
    _seed_user_and_booking("b-a", "res-a", status=BookingStatus.COMPLETED)  # historical booking!
    _seed_user_and_booking("b-b", "res-b", status=BookingStatus.CHARGING)
    t = _synthetic_trace(
        "t-auth",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=5,
        booking_kw_samples=[(m, {"b-a": 20.0, "b-b": 40.0}) for m in range(5)],
        held_booking_ids=["b-b"],
        waiting_dc=["b-c"],
    )
    decision_trace.persist(t, True)

    # Resident A asking about Resident B's booking vs nonexistent booking -> IDENTICAL FORBIDDEN (no oracle!)
    ans_other = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING, booking_id="b-b", topic=WhyTopic.POWER, at=T0 + timedelta(minutes=1)
        ),
        _resident("res-a"),
        station_id=STATION_ID,
    )
    ans_missing = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="does-not-exist",
            topic=WhyTopic.POWER,
            at=T0 + timedelta(minutes=1),
        ),
        _resident("res-a"),
        station_id=STATION_ID,
    )
    assert ans_other.status == WhyStatus.FORBIDDEN
    assert ans_other.model_dump() == ans_missing.model_dump()

    # Resident cannot query station scope; Operator cannot query own_booking or another site
    assert (
        explain_why(
            WhyQuery(subject_scope=WhySubjectScope.STATION, topic=WhyTopic.OVERVIEW, at=T0),
            _resident("res-a"),
            station_id=STATION_ID,
        ).status
        == WhyStatus.FORBIDDEN
    )
    assert (
        explain_why(
            WhyQuery(subject_scope=WhySubjectScope.OWN_BOOKING, topic=WhyTopic.OVERVIEW, at=T0),
            _operator(),
            station_id=STATION_ID,
        ).status
        == WhyStatus.FORBIDDEN
    )
    assert (
        explain_why(
            WhyQuery(subject_scope=WhySubjectScope.STATION, topic=WhyTopic.OVERVIEW, at=T0),
            _operator(station_id="OTHER-SITE"),
            station_id=STATION_ID,
        ).status
        == WhyStatus.FORBIDDEN
    )

    # Resident A CAN query their own historical completed booking across ALL 6 topics with ZERO leakage of b-b or b-c!
    for topic in WhyTopic:
        ans_own = explain_why(
            WhyQuery(
                subject_scope=WhySubjectScope.OWN_BOOKING,
                booking_id="b-a",
                topic=topic,
                at=T0 + timedelta(minutes=1),
            ),
            _resident("res-a"),
            station_id=STATION_ID,
        )
        assert ans_own.status == WhyStatus.OK, f"Topic {topic} failed: {ans_own.missing_evidence}"
        blob = json.dumps(ans_own.model_dump(mode="json"), ensure_ascii=False)
        assert "b-b" not in blob, f"Leaked b-b in {topic}: {blob}"
        assert "b-c" not in blob, f"Leaked b-c in {topic}: {blob}"
        assert "res-b" not in blob, f"Leaked res-b in {topic}: {blob}"


def test_syntactically_valid_evidence_ref_cannot_bypass_resident_authorization():
    t = _synthetic_trace(
        "t-bypass",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=5,
        booking_kw_samples=[(m, {"b-a": 20.0, "b-b": 40.0}) for m in range(5)],
        held_booking_ids=["b-b"],
        waiting_dc=["b-c"],
    )
    res_a = _resident("res-a")

    forbidden_paths = [
        "/planned/observed/vehicles/b-b/soc",
        "/planned/observed/queues_by_zone/DC",
        "/safety/held_booking_ids",
        "/safety/by_booking/b-b/safety_hold",
        "/power/approved/by_booking_kw/b-b",
        "/commands/1/power_kw",  # b-b's command row
        "/booking_ids",
        "/planned/observed/vehicles",
    ]
    for path in forbidden_paths:
        ref = EvidenceRef(
            ref_id=f"t-bypass:{TRACE_SCHEMA}#{path}",
            correlation_id="t-bypass",
            trace_schema=TRACE_SCHEMA,
            source_path=path,
            subject="b-a",
            decided_at=T0,
            policy_id="M3a",
            policy_version="1",
        )
        ok, _ = resolve_evidence_ref(ref, t, res_a, own_booking_id="b-a")
        assert not ok, f"Resident A must NOT dereference {path}"
        # Operator in same station CAN dereference the exact same valid pointer
        op_ok, _ = resolve_evidence_ref(ref, t, _operator())
        assert op_ok, f"Operator should dereference valid pointer {path}"
