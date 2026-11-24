"""Gate 2 Final Targeted Fix regression tests (G2-F05a & G2-F05b).

Executed fail-before on mirror 2d15ca1 and pass-after targeted fix in `why.py`/`evidence.py`.
Covers:
- G2-F05a: Post-apply violation temporal leakage (T0 decision, T+12 violation, T+15 close,
  query at T+5 and interval [T0, T+10) vs T+12 and [T+10, T+15)) across booking & station
  POWER / INCIDENT / OVERVIEW.
- G2-F05a: Evicted / untimestamped violation retains whole-trace evidence with PARTIAL +
  missing temporal attribution (never fabricates a timestamp).
- G2-F05a: Post-decision completion fact does NOT use `decision_snapshot` time_scope.
- G2-F05b: Pre-existing Safety Hold on Vehicle A does NOT cause Vehicle B's new post-apply
  violation to be attributed to Vehicle A.
- G2-F05b: True vehicle-specific violation carries event/booking/interval evidence refs;
  Resident accessing a multi-vehicle violation falls back to station-level violation safely.
"""

from datetime import timedelta

import pytest

pytest.importorskip("ev2gym")

from src.models.copilot import (  # noqa: E402
    TemporalBasis,
    TimeWindow,
    WhyQuery,
    WhyStatus,
    WhySubjectScope,
    WhyTopic,
)
from src.services.copilot import explain_why  # noqa: E402
from tests.factories import booking  # noqa: E402
from tests.test_services.test_why_temporal_and_auth import (  # noqa: E402
    STATION_ID,
    T0,
    _operator,
    _resident,
    _synthetic_trace,
)


def _bk(bid: str, rid: str):
    return booking(bid, zone="DC", kwh=35.0, hours=2.0, now=T0).model_copy(update={"resident_id": rid})


def _trace_with_t12_violation(*, vehicle_ids: list[str], held_booking_ids: list[str] | None = None) -> dict:
    tr = _synthetic_trace(
        "t-viol-t12",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=15,
        booking_kw_samples=[(m, {"b-a": 20.0, "b-b": 40.0}) for m in range(15)],
        post_apply="violation",
        hard_violations=["charging_model exceeded at minute 12"],
        held_booking_ids=held_booking_ids or [],
    )
    tr["applied"]["hard_violation_details"] = [
        {
            "minute": 12,
            "kind": "charging_model",
            "vehicle_ids": list(vehicle_ids),
            "message": "charging_model exceeded at minute 12",
        }
    ]
    return tr


# ---- G2-F05a: Post-apply violation temporal leakage ---------------------------------------


@pytest.mark.parametrize("topic", [WhyTopic.POWER, WhyTopic.INCIDENT, WhyTopic.OVERVIEW])
def test_g2_f05a_future_t12_violation_does_not_leak_into_t5_as_of_or_early_window(topic):
    tr = _trace_with_t12_violation(vehicle_ids=["b-a"])
    bookings = {"b-a": _bk("b-a", "res-a"), "b-b": _bk("b-b", "res-b")}

    # 1. Booking-scoped as-of T+5: MUST NOT report POST_APPLY_HARD_VIOLATION or STATION_POST_APPLY_HARD_VIOLATION
    ans_b_t5 = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=topic, at=T0 + timedelta(minutes=5)),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[tr],
        bookings_override=bookings,
    )
    assert not any("VIOLATION" in r.code for r in ans_b_t5.reasons), f"{topic} booking T+5 leaked: {ans_b_t5.reasons}"

    # 2. Station-scoped as-of T+5: MUST NOT report POST_APPLY_HARD_VIOLATION
    ans_s_t5 = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic=topic, at=T0 + timedelta(minutes=5)),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[tr],
        bookings_override=bookings,
    )
    assert not any("VIOLATION" in r.code for r in ans_s_t5.reasons), f"{topic} station T+5 leaked: {ans_s_t5.reasons}"

    # 3. Window [T0, T+10) (strictly before T+12): MUST NOT report violation
    early_win = TimeWindow(start=T0, end=T0 + timedelta(minutes=10))
    ans_s_early = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic=topic, window=early_win),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[tr],
        bookings_override=bookings,
    )
    assert not any("VIOLATION" in r.code for r in ans_s_early.reasons)

    # 4. At T+12 and window [T+10, T+15): MUST report violation WITH event/interval evidence!
    ans_b_t12 = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="b-a", topic=topic, at=T0 + timedelta(minutes=12)),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[tr],
        bookings_override=bookings,
    )
    viol_b = next(r for r in ans_b_t12.reasons if r.code == "POST_APPLY_HARD_VIOLATION")
    assert viol_b.subject == "b-a"
    paths_b = [ref.split("#", 1)[1] for ref in viol_b.evidence_refs]
    assert "/applied/hard_violation_details/0/kind" in paths_b
    assert "/applied/hard_violation_details/0/minute" in paths_b
    assert "/applied/hard_violation_details/0/vehicle_ids/0" in paths_b

    late_win = TimeWindow(start=T0 + timedelta(minutes=10), end=T0 + timedelta(minutes=15))
    ans_s_late = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic=topic, window=late_win),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[tr],
        bookings_override=bookings,
    )
    viol_s = next(r for r in ans_s_late.reasons if r.code == "POST_APPLY_HARD_VIOLATION")
    paths_s = [ref.split("#", 1)[1] for ref in viol_s.evidence_refs]
    assert "/applied/hard_violation_details/0/minute" in paths_s


def test_g2_f05a_evicted_violation_preserves_retrospective_evidence_and_flags_missing_temporal_attribution():
    tr = _synthetic_trace(
        "t-evict-viol",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=15,
        booking_kw_samples=[(14, {"b-a": 20.0})],
        coverage_status="incomplete",
        post_apply="violation",
        hard_violations=["grid limit exceeded"],
    )
    tr["applied"]["coverage"]["dropped_hard_violations"] = 1
    tr["applied"]["hard_violation_details"] = []  # evicted!

    ans = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.STATION,
            topic=WhyTopic.INCIDENT,
            at=T0 + timedelta(minutes=5),
        ),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[tr],
        bookings_override={"b-a": _bk("b-a", "res-a")},
    )
    assert ans.status == WhyStatus.PARTIAL
    assert "post_apply_violation_temporal_attribution_missing" in ans.missing_evidence
    assert "POST_APPLY_HARD_VIOLATION" in {r.code for r in ans.reasons}
    # Must NOT fabricate a violation minute fact
    assert not any(f.name == "incident.hard_violation_minute" for f in ans.facts)


def test_g2_f05a_post_decision_completion_fact_is_not_labeled_decision_snapshot():
    tr = _synthetic_trace(
        "t-comp-scope",
        T0,
        minute=0,
        planned_minutes=15,
        closed=True,
        closed_after_minutes=15,
        booking_kw_samples=[(m, {"b-a": 30.0}) for m in range(12)],
    )
    tr["applied"]["completed"] = ["b-a"]
    tr["applied"]["completed_by_booking"] = {
        "b-a": {"minute": 12, "completed_at": (T0 + timedelta(minutes=12)).isoformat()}
    }
    ans = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="b-a",
            topic=WhyTopic.DEADLINE_RISK,
            at=T0 + timedelta(minutes=12),
        ),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[tr],
        bookings_override={"b-a": _bk("b-a", "res-a")},
    )
    done_fact = next(f for f in ans.facts if f.name == "deadline.observed_completed_at_minute")
    assert done_fact.time_scope != TemporalBasis.DECISION_SNAPSHOT
    assert done_fact.interval_start == T0 + timedelta(minutes=12)
    assert done_fact.interval_end == T0 + timedelta(minutes=12)


# ---- G2-F05b: Vehicle-specific violation attribution --------------------------------------


def test_g2_f05b_prior_safety_hold_on_vehicle_a_never_attributes_vehicle_b_violation_to_a():
    # Vehicle A has a pre-existing Safety Hold from an earlier decision; Vehicle B triggers a NEW violation at T+12.
    tr = _trace_with_t12_violation(vehicle_ids=["b-b"], held_booking_ids=["b-a"])
    bookings = {"b-a": _bk("b-a", "res-a"), "b-b": _bk("b-b", "res-b")}

    for topic in (WhyTopic.POWER, WhyTopic.INCIDENT, WhyTopic.OVERVIEW):
        ans_a = explain_why(
            WhyQuery(
                subject_scope=WhySubjectScope.BOOKING,
                booking_id="b-a",
                topic=topic,
                at=T0 + timedelta(minutes=12),
            ),
            _operator(),
            station_id=STATION_ID,
            raw_traces=[tr],
            bookings_override=bookings,
        )
        # Vehicle A MUST NOT receive a vehicle-specific POST_APPLY_HARD_VIOLATION!
        assert not any(r.code == "POST_APPLY_HARD_VIOLATION" and r.subject == "b-a" for r in ans_a.reasons), (
            f"Vehicle A misattributed violation in {topic}: {ans_a.reasons}"
        )
        # Station-level violation IS allowed (subject="station")
        assert any(r.code == "STATION_POST_APPLY_HARD_VIOLATION" and r.subject == "station" for r in ans_a.reasons)
        # In INCIDENT/OVERVIEW, Vehicle A's own Safety Hold is reported separately as BOOKING_UNDER_SAFETY_HOLD
        if topic in (WhyTopic.INCIDENT, WhyTopic.OVERVIEW):
            assert any(r.code == "BOOKING_UNDER_SAFETY_HOLD" and r.subject == "b-a" for r in ans_a.reasons)


def test_g2_f05b_resident_multi_vehicle_violation_falls_back_to_station_level_without_leaking():
    # Violation involves BOTH b-a and b-b -> Resident A cannot inspect shared detail carrying b-b,
    # so Resident A must receive safe station-level violation without leaking b-b!
    tr = _trace_with_t12_violation(vehicle_ids=["b-a", "b-b"])
    bookings = {"b-a": _bk("b-a", "res-a"), "b-b": _bk("b-b", "res-b")}

    ans_res = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.OWN_BOOKING,
            booking_id="b-a",
            topic=WhyTopic.INCIDENT,
            at=T0 + timedelta(minutes=12),
        ),
        _resident("res-a"),
        station_id=STATION_ID,
        raw_traces=[tr],
        bookings_override=bookings,
    )
    assert any(r.code == "STATION_POST_APPLY_HARD_VIOLATION" and r.subject == "station" for r in ans_res.reasons)
    assert "b-b" not in ans_res.model_dump_json()

    # Single-vehicle violation solely involving b-a -> Resident A MAY receive vehicle-specific violation with full own refs!
    tr_own = _trace_with_t12_violation(vehicle_ids=["b-a"])
    ans_own = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.OWN_BOOKING,
            booking_id="b-a",
            topic=WhyTopic.INCIDENT,
            at=T0 + timedelta(minutes=12),
        ),
        _resident("res-a"),
        station_id=STATION_ID,
        raw_traces=[tr_own],
        bookings_override=bookings,
    )
    viol_own = next(r for r in ans_own.reasons if r.code == "POST_APPLY_HARD_VIOLATION")
    assert viol_own.subject == "b-a"
    paths = [ref.split("#", 1)[1] for ref in viol_own.evidence_refs]
    assert "/applied/hard_violation_details/0/vehicle_ids/0" in paths
    assert "b-b" not in ans_own.model_dump_json()
