"""Gate 2 Remediation regression tests (G2-F01 through G2-F07).

Executed fail-before on the reviewed Gate 2 tree (mirror 6ba13b8) and pass-after remediation
to classify every static review finding as a confirmed bug with concrete regression evidence.
"""

import copy
from datetime import timedelta

import pytest

pytest.importorskip("ev2gym")

from src.models.copilot import (  # noqa: E402
    EvidenceRef,
    FactStage,
    TimeWindow,
    WhyQuery,
    WhyStatus,
    WhySubjectScope,
    WhyTopic,
)
from src.models.decision_trace import TRACE_SCHEMA  # noqa: E402
from src.services import decision_trace, runtime  # noqa: E402
from src.services.copilot import explain_why  # noqa: E402
from src.services.copilot.evidence import EvidenceCollector, resolve_evidence_ref  # noqa: E402
from src.services.copilot.trace_reader import extract_measured_slice, resolve_traces_from_records  # noqa: E402
from tests.test_services.test_why_temporal_and_auth import (  # noqa: E402
    STATION_ID,
    T0,
    _operator,
    _resident,
    _seed_user_and_booking,
    _synthetic_trace,
)

# ---- G2-F01: Numerical integration (exact overlap, as-of power vs energy, no double-count) ---


def test_g2_f01_fractional_window_uses_exact_overlap_not_full_sample_duration():
    # Minute 0 [18:00, 18:01): 60 kW; Minute 1 [18:01, 18:02): 30 kW
    trace = _synthetic_trace(
        "t-frac",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=2,
        booking_kw_samples=[(0, {"b-a": 60.0}), (1, {"b-a": 30.0})],
    )
    win = TimeWindow(start=T0 + timedelta(seconds=30), end=T0 + timedelta(seconds=90))
    ans = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=WhyTopic.POWER, window=win),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    # Exact overlap: 0.5 min * 60 kW + 0.5 min * 30 kW = 0.75 kWh, avg = 45.0 kW
    kwh = next(f for f in ans.facts if f.name == "energy.measured_output_kwh")
    avg = next(f for f in ans.facts if f.name == "power.measured_actual_output_avg_kw")
    assert kwh.value == pytest.approx(0.75, abs=1e-5)
    assert avg.value == pytest.approx(45.0, abs=1e-5)
    assert any("piecewise-constant" in a for a in ans.assumptions)


def test_g2_f01_as_of_query_exposes_power_never_accumulated_sample_energy():
    trace = _synthetic_trace(
        "t-asof-e",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=2,
        booking_kw_samples=[(0, {"b-a": 60.0}), (1, {"b-a": 30.0})],
    )
    ans = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            at=T0 + timedelta(seconds=30),
        ),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    # Point-in-time query must NEVER report full-sample energy as accumulated energy at an instant
    assert not any(f.name.startswith("energy.measured") for f in ans.facts)
    power_fact = next(
        f for f in ans.facts if f.name in ("power.measured_actual_output_kw", "power.measured_actual_output_avg_kw")
    )
    assert power_fact.value == pytest.approx(60.0, abs=1e-5)


def test_g2_f01_overlapping_duplicate_samples_never_double_counted():
    trace = _synthetic_trace(
        "t-dup-sample",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=2,
        booking_kw_samples=[(0, {"b-a": 60.0}), (1, {"b-a": 30.0})],
    )
    # Duplicate sample 0 inside actual_output.samples
    dup = copy.deepcopy(trace["power"]["actual_output"]["samples"][0])
    trace["power"]["actual_output"]["samples"].insert(1, dup)
    res = resolve_traces_from_records([trace], window=TimeWindow(start=T0, end=T0 + timedelta(minutes=2)))
    sl = extract_measured_slice(res.traces[0], window=TimeWindow(start=T0, end=T0 + timedelta(minutes=2)))
    # Total energy over [18:00, 18:02) must be 60*(1/60) + 30*(1/60) = 1.5 kWh, NOT 2.5 kWh
    assert sl.output_kwh_by_booking["b-a"] == pytest.approx(1.5, abs=1e-5)


# ---- G2-F02: Evidence grounding (direct vs derived facts & multi-sample input refs) ----------


def test_g2_f02_subwindow_derived_facts_list_all_contributing_samples_and_efficiency():
    trace = _synthetic_trace(
        "t-ground",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=5,
        booking_kw_samples=[(m, {"b-a": 10.0 * (m + 1)}) for m in range(5)],
    )
    win = TimeWindow(start=T0 + timedelta(minutes=1), end=T0 + timedelta(minutes=4))
    ans = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=WhyTopic.POWER, window=win),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    avg_fact = next(f for f in ans.facts if f.name == "power.measured_actual_output_avg_kw")
    kwh_fact = next(f for f in ans.facts if f.name == "energy.measured_output_kwh")
    grid_fact = next(f for f in ans.facts if f.name == "energy.measured_grid_input_kwh")
    appr_fact = next(f for f in ans.facts if f.name == "power.approved_output_kw")

    assert getattr(appr_fact, "derivation_kind", None) == "direct"
    assert getattr(avg_fact, "derivation_kind", None) == "derived"
    assert getattr(avg_fact, "derivation_op", None) == "average"
    assert getattr(kwh_fact, "derivation_op", None) == "time_integration"
    assert getattr(grid_fact, "derivation_op", None) == "efficiency_conversion"

    # Must cite ALL 3 contributing samples (indices 1, 2, 3), NEVER only sample 1!
    for fact in (avg_fact, kwh_fact):
        paths = [r.split("#", 1)[1] for r in getattr(fact, "input_evidence_refs", [])]
        assert "/power/actual_output/samples/1/by_booking_kw/b-a" in paths
        assert "/power/actual_output/samples/2/by_booking_kw/b-a" in paths
        assert "/power/actual_output/samples/3/by_booking_kw/b-a" in paths

    grid_paths = [r.split("#", 1)[1] for r in getattr(grid_fact, "input_evidence_refs", [])]
    assert "/planned/physical_limits/conversion_efficiency" in grid_paths


def test_g2_f02_direct_fact_rejects_value_mismatch_against_canonical_trace_field():
    trace = _synthetic_trace(
        "t-direct", T0, minute=0, closed=True, closed_after_minutes=1, booking_kw_samples=[(0, {"b-a": 20.0})]
    )
    resolved = resolve_traces_from_records([trace], at=T0).traces[0]
    collector = EvidenceCollector(_operator())
    # Trace has approved power = 30.0 kW; passing wrong value 999.0 for a direct fact MUST fail!
    with pytest.raises(ValueError):
        collector.add_fact(
            resolved,
            name="power.approved_output_kw",
            subject="b-a",
            stage=FactStage.APPROVED,
            value=999.0,
            unit="kW",
            source_path="/power/approved/by_booking_kw/b-a",
        )


# ---- G2-F03: Temporal fact metadata (sub-window interval & observation snapshot) -------------


def test_g2_f03_subwindow_measured_facts_carry_derivation_interval_and_observed_has_no_planned_span():
    trace = _synthetic_trace(
        "t-meta",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=5,
        booking_kw_samples=[(m, {"b-a": 20.0}) for m in range(5)],
    )
    sub_start = T0 + timedelta(minutes=1)
    sub_end = T0 + timedelta(minutes=3)
    win = TimeWindow(start=sub_start, end=sub_end)

    # Booking-scoped power
    ans_b = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=WhyTopic.POWER, window=win),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    avg_b = next(f for f in ans_b.facts if f.name == "power.measured_actual_output_avg_kw")
    assert avg_b.interval_start == sub_start
    assert avg_b.interval_end == sub_end
    obs_allow = next(f for f in ans_b.facts if f.name == "vehicle.allowed_output_kw")
    assert obs_allow.interval_start is None and obs_allow.interval_end is None

    # Station-scoped power
    ans_s = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic=WhyTopic.POWER, window=win),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    st_kwh = next(f for f in ans_s.facts if f.name == "energy.station_measured_output_kwh")
    assert st_kwh.interval_start == sub_start
    assert st_kwh.interval_end == sub_end

    # Queue observation snapshot must NOT claim planned 15-min interval
    ans_q = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=WhyTopic.QUEUE, window=win),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    obs_state = next(f for f in ans_q.facts if f.name == "vehicle.observed_state")
    assert obs_state.interval_start is None and obs_state.interval_end is None


# ---- G2-F04: Temporal resolution (default restart path, station supersede, live clock, limit) -


def test_g2_f04_default_path_detects_stale_active_trace_when_runtime_uninitialized(clean_db, monkeypatch):
    _seed_user_and_booking("b-a", "res-a")
    stale = _synthetic_trace("t-uninit-stale", T0, minute=0, planned_minutes=15, closed=False, schedule_version=1)
    decision_trace.persist(stale, False)
    # Simulate fresh process restart where runtime._live has NOT been initialized yet
    monkeypatch.setattr(runtime, "_live", None)

    # Call explain_why via DEFAULT path (NO injected live_open_known!)
    ans = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            at=T0 + timedelta(minutes=3),
        ),
        _operator(),
        station_id=STATION_ID,
    )
    assert ans.status == WhyStatus.PARTIAL
    assert ans.traces[0].stale_after_restart is True
    assert "stale_active_trace_unclosed_after_restart" in ans.missing_evidence


def test_g2_f04_booking_query_respects_station_level_superseding_trace(clean_db, monkeypatch):
    _seed_user_and_booking("b-a", "res-a")
    _seed_user_and_booking("b-other", "res-other")
    # Trace 1 at T0 includes b-a (unclosed active)
    t1 = _synthetic_trace(
        "t-sup-1", T0, minute=0, planned_minutes=15, closed=False, schedule_version=1, booking_kw_samples=[]
    )
    # Trace 2 at T0+4m is a station-level decision that does NOT include b-a!
    t2 = _synthetic_trace(
        "t-sup-2",
        T0 + timedelta(minutes=4),
        minute=4,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=10,
        schedule_version=2,
        booking_kw_samples=[(m, {"b-other": 30.0}) for m in range(10)],
    )
    decision_trace.persist(t1, False)
    decision_trace.persist(t2, True)
    monkeypatch.setattr(runtime, "_live", None)

    # Query b-a at T0+6m: t1 was superseded at T0+4m by station-level t2 -> MUST NOT match t1!
    ans = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            at=T0 + timedelta(minutes=6),
        ),
        _operator(),
        station_id=STATION_ID,
    )
    assert ans.status == WhyStatus.NO_DATA
    assert not ans.traces


def test_g2_f04_as_of_beyond_live_physics_clock_flagged_and_candidate_limit_not_starved(clean_db, monkeypatch):
    _seed_user_and_booking("b-a", "res-a")
    # 25 non-overlapping 1-min closed traces BEFORE window [T0, T0+10m)
    for i in range(25):
        ts = T0 - timedelta(minutes=60 - i)
        tr = _synthetic_trace(
            f"t-old-{i:02d}",
            ts,
            minute=i,
            planned_minutes=1,
            closed=True,
            closed_after_minutes=1,
            schedule_version=i + 1,
            booking_kw_samples=[(0, {"b-a": 10.0})],
        )
        decision_trace.persist(tr, True)
    # 3 overlapping traces INSIDE [T0, T0+9m)
    for j in range(3):
        ts = T0 + timedelta(minutes=j * 3)
        tr = _synthetic_trace(
            f"t-win-{j}",
            ts,
            minute=100 + j * 3,
            planned_minutes=3,
            closed=True,
            closed_after_minutes=3,
            schedule_version=100 + j,
            booking_kw_samples=[(m, {"b-a": 20.0}) for m in range(3)],
        )
        decision_trace.persist(tr, True)

    win = TimeWindow(start=T0, end=T0 + timedelta(minutes=9))
    page1 = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=WhyTopic.POWER, window=win, limit=2),
        _operator(),
        station_id=STATION_ID,
    )
    assert [t.correlation_id for t in page1.traces] == ["t-win-0", "t-win-1"]
    assert page1.truncated is True
    next_cursor = getattr(page1, "next_cursor", None)
    assert next_cursor is not None

    page2 = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            window=win,
            limit=2,
            cursor=next_cursor,
        ),
        _operator(),
        station_id=STATION_ID,
    )
    assert [t.correlation_id for t in page2.traces] == ["t-win-2"]
    assert page2.truncated is False

    # Also test live active trace with physics clock at T0+2m queried at T0+10m (inside planned [T0, T0+15m))
    live_trace = _synthetic_trace("t-live-clk", T0, minute=0, planned_minutes=15, closed=False, schedule_version=200)

    class _FakeSim:
        now = T0 + timedelta(minutes=2)

    class _FakeLive:
        open_trace = {"trace": live_trace}
        simulator = _FakeSim()

    monkeypatch.setattr(runtime, "_live", _FakeLive())
    ans_future = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            at=T0 + timedelta(minutes=10),
        ),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[live_trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    assert ans_future.status == WhyStatus.PARTIAL
    assert "query_exceeds_live_physics_clock" in ans_future.missing_evidence


# ---- G2-F05: Causal and subject attribution --------------------------------------------------


def test_g2_f05_no_future_completion_leakage_and_completion_ref_not_pre_decision_state():
    # Trace [18:00, 18:15): vehicle was CHARGING at 18:00 and completed at 18:12 (minute 12)
    trace = _synthetic_trace(
        "t-comp",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=15,
        booking_kw_samples=[(m, {"b-a": 30.0}) for m in range(12)],
    )
    trace["applied"]["completed"] = ["b-a"]
    trace["applied"]["completed_by_booking"] = {
        "b-a": {"minute": 12, "completed_at": (T0 + timedelta(minutes=12)).isoformat()}
    }

    # Query at T+5 (BEFORE completion at T+12) -> MUST NOT claim completed!
    ans_t5 = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.DEADLINE_RISK,
            at=T0 + timedelta(minutes=5),
        ),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    assert "OBSERVED_CHARGE_COMPLETED" not in {r.code for r in ans_t5.reasons}

    # Query at T+12 (AT/AFTER completion) -> MAY claim completed, and evidence ref MUST NOT point to pre-decision state!
    ans_t12 = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.DEADLINE_RISK,
            at=T0 + timedelta(minutes=12),
        ),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    comp = next(r for r in ans_t12.reasons if r.code == "OBSERVED_CHARGE_COMPLETED")
    assert all(not ref.endswith("/planned/observed/vehicles/b-a/state") for ref in comp.evidence_refs)


def test_g2_f05_station_violation_not_misattributed_and_no_incident_abstains_when_incomplete():
    # Station post-apply violation caused by b-other, NOT b-a
    trace_v = _synthetic_trace(
        "t-sviol",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=5,
        booking_kw_samples=[(m, {"b-a": 20.0, "b-other": 60.0}) for m in range(5)],
        post_apply="violation",
        hard_violations=["charging_model violation on b-other"],
    )
    trace_v["applied"]["hard_violation_details"] = [
        {"minute": 1, "kind": "charging_model", "vehicle_ids": ["b-other"], "message": "exceeded"}
    ]
    ans_v = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.INCIDENT,
            at=T0 + timedelta(minutes=1),
        ),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace_v],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    viol_reasons = [r for r in ans_v.reasons if "VIOLATION" in r.code]
    assert viol_reasons
    assert all(r.subject != "b-a" for r in viol_reasons)

    # Active (not_evaluated) and incomplete traces MUST NOT assert NO_INCIDENT_OBSERVED
    trace_active = _synthetic_trace("t-act-inc", T0, minute=0, planned_minutes=15, closed=False)
    ans_act = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic=WhyTopic.INCIDENT, at=T0),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace_active],
        live_open_correlation_id="t-act-inc",
        live_open_known=True,
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    assert "NO_INCIDENT_OBSERVED" not in {r.code for r in ans_act.reasons}

    trace_incomp = _synthetic_trace(
        "t-incomp-inc",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=5,
        booking_kw_samples=[(0, {"b-a": 20.0})],
        coverage_status="incomplete",
        post_apply="incomplete",
    )
    ans_inc = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic=WhyTopic.INCIDENT, at=T0 + timedelta(minutes=1)),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace_incomp],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    assert "NO_INCIDENT_OBSERVED" not in {r.code for r in ans_inc.reasons}


def test_g2_f05_guard_block_pending_approval_and_hardware_bound_complete_evidence():
    trace = _synthetic_trace(
        "t-ev-full",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=2,
        booking_kw_samples=[(0, {"b-a": 30.0}), (1, {"b-a": 30.0})],
    )
    trace["commands"] = [
        {
            "command_id": "cmd-guard",
            "recorded_at": T0.isoformat(),
            "type": "set_power",
            "source": "optimizer",
            "connector_id": "DC-01-1",
            "booking_id": "b-a",
            "power_kw": 30.0,
            "guard_passed": False,
            "violations": [{"rule": "site_limit_exceeded", "message": "too high"}],
            "approval_id": None,
            "executed": False,
            "note": "",
        },
        {
            "command_id": "cmd-pend",
            "recorded_at": T0.isoformat(),
            "type": "set_power",
            "source": "optimizer",
            "connector_id": "DC-01-1",
            "booking_id": "b-a",
            "power_kw": 25.0,
            "guard_passed": True,
            "violations": [],
            "approval_id": "appr-42",
            "executed": False,
            "note": "",
        },
    ]
    ans_p = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=WhyTopic.POWER, at=T0),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    blk = next(r for r in ans_p.reasons if r.code == "BUSINESS_GUARD_BLOCKED")
    blk_paths = [ref.split("#", 1)[1] for ref in blk.evidence_refs]
    assert "/commands/0/guard_passed" in blk_paths
    assert "/commands/0/violations/0/rule" in blk_paths

    pend = next(r for r in ans_p.reasons if r.code == "COMMAND_PENDING_APPROVAL")
    pend_paths = [ref.split("#", 1)[1] for ref in pend.evidence_refs]
    assert "/commands/1/approval_id" in pend_paths
    assert pend.params.get("decision_time_only") is True

    # Hardware infeasibility bound must cite remaining_kwh, deadline_minute, vehicle_max_output_kw, port_limit_kw, charging_efficiency
    trace["planned"]["observed"]["vehicles"]["b-a"]["remaining_kwh"] = 50.0
    trace["planned"]["observed"]["vehicles"]["b-a"]["deadline_minute"] = 10
    ans_dr = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=WhyTopic.DEADLINE_RISK, at=T0),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    hw = next(r for r in ans_dr.reasons if r.code == "SINGLE_VEHICLE_HARDWARE_BOUND_EXCEEDED")
    hw_paths = [ref.split("#", 1)[1] for ref in hw.evidence_refs]
    assert "/planned/observed/vehicles/b-a/remaining_kwh" in hw_paths
    assert "/planned/observed/vehicles/b-a/deadline_minute" in hw_paths
    assert "/planned/observed/vehicles/b-a/vehicle_max_output_kw" in hw_paths
    assert "/planned/physical_limits/charging_efficiency" in hw_paths
    assert any("port_output_kw" in p or "port_limit_kw" in p for p in hw_paths)


# ---- G2-F06: Energy conversion provenance (no silent 0.95 / 0.98 fallbacks) ------------------


def test_g2_f06_missing_efficiencies_report_missing_evidence_instead_of_silent_defaults():
    trace = _synthetic_trace(
        "t-no-eff",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=2,
        booking_kw_samples=[(0, {"b-a": 30.0}), (1, {"b-a": 30.0})],
    )
    trace["planned"]["physical_limits"]["conversion_efficiency"] = None
    trace["planned"]["physical_limits"]["charging_efficiency"] = None
    trace["planned"]["observed"]["vehicles"]["b-a"]["remaining_kwh"] = 50.0
    trace["planned"]["observed"]["vehicles"]["b-a"]["deadline_minute"] = 10

    # Sub-window power must NOT fabricate grid_input_kwh with 0.95
    ans_p = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.POWER,
            window=TimeWindow(start=T0, end=T0 + timedelta(minutes=1)),
        ),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    assert ans_p.status == WhyStatus.PARTIAL
    assert "missing_conversion_efficiency_evidence" in ans_p.missing_evidence
    assert not any(f.name == "energy.measured_grid_input_kwh" for f in ans_p.facts)

    # Deadline risk must NOT fabricate hardware bound with 0.98
    ans_d = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=WhyTopic.DEADLINE_RISK, at=T0),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[trace],
        bookings_override={"b-a": _make_dummy_booking("b-a", "res-a")},
    )
    assert ans_d.status == WhyStatus.PARTIAL
    assert "missing_charging_efficiency_evidence" in ans_d.missing_evidence
    assert "SINGLE_VEHICLE_HARDWARE_BOUND_EXCEEDED" not in {r.code for r in ans_d.reasons}


# ---- G2-F07: EvidenceRef authorization & adversarial consistency checks ----------------------


def test_g2_f07_adversarial_evidence_ref_mismatches_rejected():
    trace = _synthetic_trace(
        "t-adv",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=2,
        booking_kw_samples=[(0, {"b-a": 20.0, "b-b": 40.0})],
    )
    op = _operator()

    # 1. Valid pointer, mismatched ref_id vs source_path
    bad_ref_id = EvidenceRef(
        ref_id=f"t-adv:{TRACE_SCHEMA}#/policy/version",
        correlation_id="t-adv",
        trace_schema=TRACE_SCHEMA,
        source_path="/policy/id",
        subject="station",
        decided_at=T0,
        policy_id="M3a",
        policy_version="1",
    )
    assert resolve_evidence_ref(bad_ref_id, trace, op)[0] is False

    # 2. Valid pointer to b-b, wrong subject "b-a"
    bad_subject = EvidenceRef(
        ref_id=f"t-adv:{TRACE_SCHEMA}#/power/approved/by_booking_kw/b-b",
        correlation_id="t-adv",
        trace_schema=TRACE_SCHEMA,
        source_path="/power/approved/by_booking_kw/b-b",
        subject="b-a",
        decided_at=T0,
        policy_id="M3a",
        policy_version="1",
    )
    assert resolve_evidence_ref(bad_subject, trace, op)[0] is False

    # 3. Valid pointer, wrong time interval (outside trace/sample bounds or inverted)
    bad_interval = EvidenceRef(
        ref_id=f"t-adv:{TRACE_SCHEMA}#/power/actual_output/samples/0/by_booking_kw/b-a",
        correlation_id="t-adv",
        trace_schema=TRACE_SCHEMA,
        source_path="/power/actual_output/samples/0/by_booking_kw/b-a",
        subject="b-a",
        decided_at=T0,
        policy_id="M3a",
        policy_version="1",
        interval_start=T0 + timedelta(minutes=10),
        interval_end=T0 + timedelta(minutes=12),
    )
    assert resolve_evidence_ref(bad_interval, trace, op)[0] is False

    # 4. Valid pointer, wrong policy_id
    bad_policy = EvidenceRef(
        ref_id=f"t-adv:{TRACE_SCHEMA}#/policy/id",
        correlation_id="t-adv",
        trace_schema=TRACE_SCHEMA,
        source_path="/policy/id",
        subject="station",
        decided_at=T0,
        policy_id="B0",
        policy_version="1",
    )
    assert resolve_evidence_ref(bad_policy, trace, op)[0] is False

    # 5. Resident A trying to dereference Resident B's ref even by passing spoofed own_booking_id string
    # (must require verified booking ownership, not blind trust in arbitrary string)
    b_b = _make_dummy_booking("b-b", "res-b")
    ref_b = EvidenceRef(
        ref_id=f"t-adv:{TRACE_SCHEMA}#/power/approved/by_booking_kw/b-b",
        correlation_id="t-adv",
        trace_schema=TRACE_SCHEMA,
        source_path="/power/approved/by_booking_kw/b-b",
        subject="b-b",
        decided_at=T0,
        policy_id="M3a",
        policy_version="1",
    )
    # Passing Resident A with Resident B's booking or unverified string must fail!
    assert resolve_evidence_ref(ref_b, trace, _resident("res-a"), booking=b_b)[0] is False

    # 6. Resident cannot dereference container/object prefix pointers that could carry cross-resident metadata
    b_a = _make_dummy_booking("b-a", "res-a")
    for container_path in ("/applied/coverage", "/planned/physical_limits", "/planned/observed/zone_summary/DC"):
        cref = EvidenceRef(
            ref_id=f"t-adv:{TRACE_SCHEMA}#{container_path}",
            correlation_id="t-adv",
            trace_schema=TRACE_SCHEMA,
            source_path=container_path,
            subject="station",
            decided_at=T0,
            policy_id="M3a",
            policy_version="1",
        )
        assert resolve_evidence_ref(cref, trace, _resident("res-a"), booking=b_a)[0] is False

    # 7. verify_privacy_projection rejects reason params or summary leaking foreign booking IDs
    from src.models.copilot import EvidenceCategory, WhyAnswer, WhyReason
    from src.services.copilot.evidence import AuthorizedSubject, verify_privacy_projection

    resolved = resolve_traces_from_records([trace], at=T0).traces[0]
    auth_a = AuthorizedSubject(actor=_resident("res-a"), station_id=STATION_ID, own_booking_id="b-a")
    leaked_ans = WhyAnswer(
        status=WhyStatus.OK,
        topic="power",
        subject_scope=WhySubjectScope.OWN_BOOKING,
        subject_id="b-a",
        query_at=T0,
        reasons=[
            WhyReason(
                code="TEST_LEAK",
                category=EvidenceCategory.OBSERVED,
                subject="b-a",
                correlation_id="t-adv",
                policy_id="M3a",
                policy_version="1",
                decided_at=T0,
                template_key="test.leak",
                params={"other": "b-b"},
                summary="Blocked by b-b",
            )
        ],
    )
    with pytest.raises(PermissionError):
        verify_privacy_projection(leaked_ans, _resident("res-a"), [resolved], authorized_subject=auth_a)


def _make_dummy_booking(bid: str, resident_id: str):
    from tests.factories import booking

    return booking(bid, zone="DC", kwh=35.0, hours=2.0, now=T0).model_copy(update={"resident_id": resident_id})
