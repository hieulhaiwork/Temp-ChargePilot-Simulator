"""WP2.6 — Deterministic WHY Engine integration, explainer, policy attribution & mutation tests (Gate 2).

Covers:
- Typed contract validation (naive timestamps, contradictory time selection, invalid scopes, extra fields, NaN/Inf).
- G1-F05 planned evidence on active traces vs measured evidence on closed traces.
- Planned assignment blocked/excluded/pending never conflated with connected vehicle state.
- Read-only invariant (WHY never steps simulator, calls sync_clock, or mutates runtime/bookings).
- All 6 topics (queue, power, deadline_risk, incident, policy, overview) across real HybridStation runs:
  normal/no-conflict, all ports occupied, DC LLF dispatch, site cap drop, connector fault, DC taper,
  PENDING_APPROVAL vs REJECTED_CONSENT vs SAFETY_HOLD, optimizer fallback, unknown policy reason code,
  B0 anti-TOU attribution, M3b Dynamic Slack, independent supply, deadline risk separation.
- Independent oracle mutation tests (subject, time, unit, evidence path, reason code).
"""

import copy
from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError

pytest.importorskip("ev2gym")

from src.models.charging import BookingStatus, StrategyName  # noqa: E402
from src.models.control import Approval, ApprovalKind, Command, CommandSource, CommandType, GuardVerdict, Role  # noqa: E402
from src.models.copilot import (  # noqa: E402
    ActorContext,
    EvidenceCategory,
    FactStage,
    TimeWindow,
    WhyAnswer,
    WhyQuery,
    WhyStatus,
    WhySubjectScope,
    WhyTopic,
)
from src.models.events import EventType, StationEvent  # noqa: E402
from src.models.simulation import Incident, IncidentType  # noqa: E402
from src.services import catalog, control_loop, decision_trace  # noqa: E402
from src.services.copilot import explain_why  # noqa: E402
from src.services.copilot.evidence import resolve_evidence_ref  # noqa: E402
from src.services.runtime import build_sim_runtime, visit_of  # noqa: E402
from tests.factories import VN, booking  # noqa: E402

_CFG = catalog.load_station_config()
_SCENARIO = catalog.load_scenario("hybrid_evening")
STATION_ID = _CFG.station_id
T0 = datetime.combine(date(2026, 11, 24), _SCENARIO.start_time, tzinfo=VN)


def _operator() -> ActorContext:
    return ActorContext(actor_id="op-1", role=Role.OPERATOR, station_id=STATION_ID)


def _resident(actor_id: str) -> ActorContext:
    return ActorContext(actor_id=actor_id, role=Role.RESIDENT, station_id=STATION_ID)


def _make_booking(
    bid: str,
    *,
    resident_id: str | None = None,
    zone: str = "DC",
    kwh: float = 35.0,
    hours: float = 1.5,
    soc_now: float = 20.0,
    soc_target: float = 80.0,
    status: BookingStatus = BookingStatus.CONFIRMED,
):
    b = booking(bid, zone=zone, kwh=kwh, hours=hours, now=T0)
    req = b.request.model_copy(update={"soc_now": soc_now, "soc_target": soc_target})
    return b.model_copy(
        update={
            "resident_id": resident_id or f"res-{bid}",
            "request": req,
            "status": status,
        }
    )


async def _sim_station(strategy: StrategyName, bookings, *, supply_mode: str = "shared"):
    config = catalog.load_station_config()
    if supply_mode == "independent":
        raw_cfg = config.model_dump()
        raw_cfg["supply_mode"] = "independent"
        raw_cfg["independent_grid_input_limit_kw"] = {"AC": 25.0, "DC": 90.0}
        config = type(config).model_validate(raw_cfg)
    tariff = catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    rt = build_sim_runtime(scenario, strategy, config, tariff, T0)
    for b in bookings:
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, T0))
    return rt


# ---- 1. Typed Contract Validation ---------------------------------------------------------


def test_why_query_rejects_invalid_inputs_and_untrusted_actor_fields():
    naive = datetime(2026, 11, 24, 18, 0)
    with pytest.raises(ValidationError):
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic="power", at=naive)
    with pytest.raises(ValidationError):
        WhyQuery(
            subject_scope=WhySubjectScope.STATION,
            topic="power",
            at=T0,
            window=TimeWindow(start=T0, end=T0 + timedelta(minutes=15)),
        )
    with pytest.raises(ValidationError):
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic="power")
    with pytest.raises(ValidationError):
        TimeWindow(start=T0, end=T0)
    with pytest.raises(ValidationError):
        TimeWindow(start=T0, end=T0 + timedelta(days=32))
    with pytest.raises(ValidationError):
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic="power", booking_id="b1", at=T0)
    with pytest.raises(ValidationError):
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, topic="power", at=T0)
    with pytest.raises(ValidationError):
        WhyQuery(subject_scope=WhySubjectScope.OWN_BOOKING, topic="power", at=T0, role="operator")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        WhyQuery(subject_scope=WhySubjectScope.OWN_BOOKING, topic="power", at=T0, actor_id="spoof")  # type: ignore[call-arg]


def test_unknown_topic_returns_unsupported_distinct_from_validation_error():
    ans = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic="tariff_forecast_magic", at=T0),
        _operator(),
        station_id=STATION_ID,
        raw_traces=[],
        bookings_override={},
    )
    assert ans.status == WhyStatus.UNSUPPORTED
    assert "unsupported_topic:tariff_forecast_magic" in ans.missing_evidence


# ---- 2. G1-F05 Planned Evidence, Active vs Closed, and Read-Only Invariant ---------------


async def test_active_trace_provides_planned_evidence_without_fabricating_measured_facts():
    b_dc = _make_booking("dc-1", zone="DC", kwh=30, hours=1.5)
    b_ac = _make_booking("ac-1", zone="AC", kwh=15, hours=3.0)
    rt = await _sim_station(StrategyName.SIM_M3A, [b_dc, b_ac])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)

    active_trace = rt.open_trace["trace"]
    assert active_trace["closed"] is False
    assert active_trace["applied"] is None
    assert active_trace["decision"] is None
    assert isinstance(active_trace["planned"], dict)
    assert active_trace["planned"]["observed"]["vehicles"]["dc-1"]["state"] == "QUEUED"
    assert active_trace["planned"]["observed"]["vehicles"]["dc-1"]["connector_id"] is None
    assert active_trace["planned"]["observed"]["vehicles"]["dc-1"]["planned_assigned_connector"] is not None

    ans = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.OWN_BOOKING, booking_id="dc-1", topic=WhyTopic.POWER, at=T0),
        _resident("res-dc-1"),
        station_id=rt.config.station_id,
        raw_traces=[active_trace],
        live_open_correlation_id=active_trace["correlation_id"],
        live_open_known=True,
        bookings_override={"dc-1": b_dc, "ac-1": b_ac},
    )
    assert ans.status == WhyStatus.PARTIAL
    assert "active_trace_no_measured_data" in ans.missing_evidence
    stages = {f.stage for f in ans.facts}
    assert FactStage.PLANNED in stages and FactStage.APPROVED in stages
    assert FactStage.MEASURED not in stages
    assert not any(f.name.startswith("power.measured") or f.name.startswith("energy.measured") for f in ans.facts)
    for ref in ans.evidence_refs:
        ok, _ = resolve_evidence_ref(ref, active_trace, _resident("res-dc-1"), booking=b_dc)
        assert ok, f"Failed to dereference {ref.source_path}"


async def test_why_engine_is_strictly_read_only_never_steps_or_syncs_clock(monkeypatch):
    b_dc = _make_booking("dc-1", zone="DC", kwh=30, hours=1.5)
    rt = await _sim_station(StrategyName.SIM_M3A, [b_dc])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    rt.simulator.step(2)
    closed = decision_trace.close_open(rt)
    minute_before = rt.simulator.minute
    state_ver_before = rt.simulator.kernel.state_version

    def forbidden_call(*_, **__):
        raise AssertionError("WHY Engine must never call sync_clock or simulator.step")

    monkeypatch.setattr(rt, "sync_clock", forbidden_call)
    monkeypatch.setattr(rt.simulator, "step", forbidden_call)

    ans = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic=WhyTopic.OVERVIEW, at=T0 + timedelta(minutes=1)),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[closed],
        bookings_override={"dc-1": b_dc},
    )
    assert ans.status == WhyStatus.OK
    assert rt.simulator.minute == minute_before
    assert rt.simulator.kernel.state_version == state_ver_before


async def test_planned_assignment_blocked_or_excluded_never_claims_connected():
    b_dc = _make_booking("dc-1", zone="DC", kwh=30, hours=1.5)
    rt = await _sim_station(StrategyName.SIM_M3A, [b_dc])
    rt.safety_hold_booking_ids.add("dc-1")
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    active = rt.open_trace["trace"]

    ans = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.OWN_BOOKING, booking_id="dc-1", topic=WhyTopic.QUEUE, at=T0),
        _resident("res-dc-1"),
        station_id=rt.config.station_id,
        raw_traces=[active],
        live_open_correlation_id=active["correlation_id"],
        live_open_known=True,
        bookings_override={"dc-1": b_dc},
    )
    codes = {r.code for r in ans.reasons}
    assert "PLANNED_ASSIGNMENT_EXCLUDED_SAFETY_HOLD" in codes
    assert "ASSIGNMENT_DISPATCHED" not in codes
    assert "VEHICLE_ALREADY_CONNECTED" not in codes
    obs_conn = next(f for f in ans.facts if f.name == "vehicle.observed_connector")
    assert obs_conn.value is None


# ---- 3. Domain Explainers & Policy Attribution Fixtures -----------------------------------


async def test_b0_policy_never_attributed_to_tou_optimization():
    b_ac = _make_booking("ac-1", zone="AC", kwh=15, hours=3.0)
    rt = await _sim_station(StrategyName.SIM_B0, [b_ac])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    rt.simulator.step(2)
    closed = decision_trace.close_open(rt)

    for topic in (WhyTopic.POWER, WhyTopic.POLICY):
        ans = explain_why(
            WhyQuery(
                subject_scope=WhySubjectScope.BOOKING, booking_id="ac-1", topic=topic, at=T0 + timedelta(minutes=1)
            ),
            _operator(),
            station_id=rt.config.station_id,
            raw_traces=[closed],
            bookings_override={"ac-1": b_ac},
        )
        assert ans.status == WhyStatus.OK
        assert ans.policy_id == "B0"
        codes = {r.code for r in ans.reasons}
        assert "AC_LP_TOU_OPTIMIZED" not in codes
        assert "COORDINATOR_FIXED_SHARE" in codes
        assert not any("TOU" in r.summary for r in ans.reasons)


async def test_m3a_ac_lp_records_tou_and_normal_no_incident():
    b_ac = _make_booking("ac-1", zone="AC", kwh=15, hours=3.0)
    rt = await _sim_station(StrategyName.SIM_M3A, [b_ac])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    rt.simulator.step(2)
    closed = decision_trace.close_open(rt)

    ans_policy = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="ac-1",
            topic=WhyTopic.POLICY,
            at=T0 + timedelta(minutes=1),
        ),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[closed],
        bookings_override={"ac-1": b_ac},
    )
    assert ans_policy.status == WhyStatus.OK
    assert "AC_LP_TOU_OPTIMIZED" in {r.code for r in ans_policy.reasons}

    ans_inc = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic=WhyTopic.INCIDENT, at=T0 + timedelta(minutes=1)),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[closed],
        bookings_override={"ac-1": b_ac},
    )
    assert ans_inc.status == WhyStatus.OK
    assert "NO_INCIDENT_OBSERVED" in {r.code for r in ans_inc.reasons}


async def test_queue_all_ports_occupied_and_dc_llf_waiting_laxity():
    b1 = _make_booking("dc-1", zone="DC", kwh=40, hours=1.5)
    b2 = _make_booking("dc-2", zone="DC", kwh=40, hours=1.5)
    b3 = _make_booking("dc-3", zone="DC", kwh=40, hours=0.5)  # waiting while 2 DC ports occupied
    rt = await _sim_station(StrategyName.SIM_M3A, [b1, b2, b3])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    rt.simulator.step(1)
    # Next tick: dc-1 & dc-2 are plugged, dc-3 is still waiting with 0 empty DC ports
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0 + timedelta(minutes=1)), rt)
    rt.simulator.step(1)
    closed_second = decision_trace.close_open(rt)

    # Identify which DC booking stayed in queue
    queued_vid = next(
        vid for vid, row in closed_second["planned"]["observed"]["vehicles"].items() if row["state"] == "QUEUED"
    )
    ans_q = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.OWN_BOOKING,
            booking_id=queued_vid,
            topic=WhyTopic.QUEUE,
            at=T0 + timedelta(minutes=1),
        ),
        _resident(f"res-{queued_vid}"),
        station_id=rt.config.station_id,
        raw_traces=[closed_second],
        bookings_override={"dc-1": b1, "dc-2": b2, "dc-3": b3},
    )
    assert ans_q.status == WhyStatus.OK
    assert "NO_FREE_COMPATIBLE_PORT" in {r.code for r in ans_q.reasons}
    assert any(f.name == "queue.observed_position" and f.value == 1 for f in ans_q.facts)

    # Deadline risk for waiting DC vehicle reports optimistic_laxity as INFERENCE_BOUND (not observed missed)
    ans_dr = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.OWN_BOOKING,
            booking_id=queued_vid,
            topic=WhyTopic.DEADLINE_RISK,
            at=T0 + timedelta(minutes=1),
        ),
        _resident(f"res-{queued_vid}"),
        station_id=rt.config.station_id,
        raw_traces=[closed_second],
        bookings_override={"dc-1": b1, "dc-2": b2, "dc-3": b3},
    )
    lax_reasons = [r for r in ans_dr.reasons if r.code.startswith("OPTIMISTIC_LAXITY_")]
    assert lax_reasons and all(r.category == EvidenceCategory.INFERENCE_BOUND for r in lax_reasons)
    assert "OBSERVED_DEADLINE_MISSED" not in {r.code for r in ans_dr.reasons}


async def test_site_cap_drop_connector_fault_and_dc_taper():
    b_dc = _make_booking("dc-1", zone="DC", kwh=10, hours=1.5, soc_now=75.0, soc_target=90.0)  # high SOC -> DC taper
    b_ac = _make_booking("ac-1", zone="AC", kwh=10, hours=2.0)
    rt = await _sim_station(StrategyName.SIM_M3A, [b_dc, b_ac])
    # Fault DC-01-2 and drop site power to 30 kW
    rt.simulator.inject_incident(Incident(type=IncidentType.CONNECTOR_FAULT, connector_id="DC-01-2"))
    rt.simulator.inject_incident(Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=30.0))
    await control_loop.on_event(
        StationEvent(type=EventType.POWER_LIMIT_CHANGED, occurred_at=T0, new_power_limit_kw=30.0), rt
    )
    rt.simulator.step(2)
    closed = decision_trace.close_open(rt)

    ans_power = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING, booking_id="dc-1", topic=WhyTopic.POWER, at=T0 + timedelta(minutes=1)
        ),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[closed],
        bookings_override={"dc-1": b_dc, "ac-1": b_ac},
    )
    codes = {r.code for r in ans_power.reasons}
    assert "VEHICLE_ACCEPTANCE_TAPER_LIMIT" in codes
    assert "COORDINATOR_SOURCE_LIMITED" in codes
    assert any(f.name == "limits.site_grid_input_kw" and f.value == 30.0 for f in ans_power.facts)

    ans_inc = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic=WhyTopic.INCIDENT, at=T0 + timedelta(minutes=1)),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[closed],
        bookings_override={"dc-1": b_dc, "ac-1": b_ac},
    )
    assert "CONNECTOR_FAULT_ACTIVE" in {r.code for r in ans_inc.reasons}
    assert any(f.name == "incident.faulted_connectors" and "DC-01-2" in str(f.value) for f in ans_inc.facts)


async def test_independent_supply_and_m3b_dynamic_slack_reason_codes():
    b_dc = _make_booking("dc-1", zone="DC", kwh=35, hours=1.5)
    b_ac = _make_booking("ac-1", zone="AC", kwh=15, hours=3.0)
    rt = await _sim_station(StrategyName.SIM_M3B, [b_dc, b_ac], supply_mode="independent")
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    rt.simulator.step(2)
    closed = decision_trace.close_open(rt)

    ans = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING, booking_id="dc-1", topic=WhyTopic.POWER, at=T0 + timedelta(minutes=1)
        ),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[closed],
        bookings_override={"dc-1": b_dc, "ac-1": b_ac},
    )
    codes = {r.code for r in ans.reasons}
    assert "INDEPENDENT_SUPPLY_MODE" in codes
    assert "COORDINATOR_INDEPENDENT_SUPPLY" in codes


async def test_unknown_coordinator_reason_code_and_optimizer_fallback_never_hallucinated():
    b_dc = _make_booking("dc-1", zone="DC", kwh=35, hours=1.5)
    rt = await _sim_station(StrategyName.SIM_M3B, [b_dc])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    rt.simulator.step(2)
    closed = decision_trace.close_open(rt)

    # Inject an unknown coordinator reason code + optimizer fallback into a synthetic copy of the trace
    mutated = copy.deepcopy(closed)
    mutated["planned"]["coordinator"]["reason_codes"]["DC"].append("mvp35_experimental_quantum_boost")
    mutated["planned"]["optimizers"]["DC"]["fallback_reason"] = "time_limit"

    ans = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING,
            booking_id="dc-1",
            topic=WhyTopic.POLICY,
            at=T0 + timedelta(minutes=1),
        ),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[mutated],
        bookings_override={"dc-1": b_dc},
    )
    codes = {r.code for r in ans.reasons}
    assert "UNKNOWN_POLICY_REASON_CODE" in codes
    assert "OPTIMIZER_FALLBACK_TO_EQUAL_SHARE" in codes
    unknown_reason = next(r for r in ans.reasons if r.code == "UNKNOWN_POLICY_REASON_CODE")
    assert unknown_reason.params["raw_code"] == "mvp35_experimental_quantum_boost"


async def test_command_exclusions_distinguish_pending_rejected_and_safety_hold():
    b_dc = _make_booking("dc-1", zone="DC", kwh=35, hours=1.5)
    rt = await _sim_station(StrategyName.SIM_M3A, [b_dc])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    rt.simulator.step(1)
    # Attach pending approval, safety hold, and rejected consent
    cmd = Command(
        type=CommandType.SET_POWER,
        connector_id="DC-01-1",
        power_kw=20.0,
        booking_id="dc-1",
        source=CommandSource.AGENT,
        issued_by="test",
        based_on_schedule_version=rt.plan.version,
        based_on_state_at=rt.clock(),
        created_at=rt.clock(),
    )
    rt.sinks.save_approval(
        Approval(
            kind=ApprovalKind.OPERATOR_REVIEW,
            command=cmd,
            verdict=GuardVerdict(command_id=cmd.command_id, passed=True, checked_at=rt.clock()),
            requested_from="operator",
            impact_summary="test",
            created_at=rt.clock(),
        )
    )
    rt.safety_hold_booking_ids.add("dc-1")
    rt.rejected_booking_ids.add("dc-1")
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0 + timedelta(minutes=1)), rt)
    active = rt.open_trace["trace"]
    # Simulate an exclusion row carrying all 3 reasons in canonical precedence order
    mutated = copy.deepcopy(active)
    mutated["command_exclusions"] = [
        {
            "command_id": "cmd-test",
            "correlation_id": mutated["correlation_id"],
            "booking_id": "dc-1",
            "connector_id": "DC-01-1",
            "type": "set_power",
            "requested_output_kw": 35.0,
            "primary_reason": "PENDING_APPROVAL",
            "reasons": ["PENDING_APPROVAL", "SAFETY_HOLD", "REJECTED_CONSENT"],
        }
    ]
    ans = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING, booking_id="dc-1", topic=WhyTopic.POWER, at=T0 + timedelta(minutes=1)
        ),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[mutated],
        live_open_correlation_id=mutated["correlation_id"],
        live_open_known=True,
        bookings_override={"dc-1": b_dc},
    )
    ex_reason = next(r for r in ans.reasons if r.code == "EXCLUDED_PENDING_APPROVAL")
    assert ex_reason.params["primary_reason"] == "PENDING_APPROVAL"
    assert "SAFETY_HOLD" in str(ex_reason.params["reasons"])
    assert "REJECTED_CONSENT" in str(ex_reason.params["reasons"])


# ---- 4. Independent Oracle Mutation Tests -------------------------------------------------


def _verify_against_independent_oracle(answer: WhyAnswer, trace: dict, oracle: dict) -> None:
    """Independent verification oracle checking subject, timestamp, unit, evidence path, and reason code."""
    ref_map = {r.ref_id: r for r in answer.evidence_refs}
    # Verify every fact's evidence_ref exists and dereferences cleanly
    for fact in answer.facts:
        assert fact.evidence_ref in ref_map, f"Missing evidence ref {fact.evidence_ref}"
        ref = ref_map[fact.evidence_ref]
        ok, _ = resolve_evidence_ref(ref, trace, _operator())
        assert ok, f"Dangling pointer {ref.source_path}"

    target_fact = next((f for f in answer.facts if f.name == oracle["fact_name"]), None)
    assert target_fact is not None, f"Missing expected fact {oracle['fact_name']}"
    assert target_fact.subject == oracle["subject"]
    assert target_fact.decided_at == oracle["decided_at"]
    assert target_fact.unit == oracle["unit"]
    assert target_fact.source_path == oracle["source_path"]
    assert oracle["reason_code"] in {r.code for r in answer.reasons}


async def test_mutation_tests_fail_on_subject_time_unit_path_and_reason_code():
    b_ac = _make_booking("ac-1", zone="AC", kwh=15, hours=3.0)
    rt = await _sim_station(StrategyName.SIM_M3A, [b_ac])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    rt.simulator.step(2)
    closed = decision_trace.close_open(rt)

    ans = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.BOOKING, booking_id="ac-1", topic=WhyTopic.POWER, at=T0 + timedelta(minutes=1)
        ),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[closed],
        bookings_override={"ac-1": b_ac},
    )
    oracle = {
        "fact_name": "power.approved_output_kw",
        "subject": "ac-1",
        "decided_at": T0,
        "unit": "kW",
        "source_path": "/power/approved/by_booking_kw/ac-1",
        "reason_code": "AC_LP_TOU_OPTIMIZED",
    }
    _verify_against_independent_oracle(ans, closed, oracle)

    idx = next(i for i, f in enumerate(ans.facts) if f.name == oracle["fact_name"])
    # 1. Mutate subject
    mut_subject = ans.model_copy(
        update={
            "facts": [f.model_copy(update={"subject": "ac-wrong"}) if i == idx else f for i, f in enumerate(ans.facts)]
        }
    )
    with pytest.raises(AssertionError):
        _verify_against_independent_oracle(mut_subject, closed, oracle)

    # 2. Mutate timestamp
    mut_time = ans.model_copy(
        update={
            "facts": [
                f.model_copy(update={"decided_at": T0 + timedelta(minutes=5)}) if i == idx else f
                for i, f in enumerate(ans.facts)
            ]
        }
    )
    with pytest.raises(AssertionError):
        _verify_against_independent_oracle(mut_time, closed, oracle)

    # 3. Mutate unit
    mut_unit = ans.model_copy(
        update={"facts": [f.model_copy(update={"unit": "kWh"}) if i == idx else f for i, f in enumerate(ans.facts)]}
    )
    with pytest.raises(AssertionError):
        _verify_against_independent_oracle(mut_unit, closed, oracle)

    # 4. Mutate evidence path
    bad_ref_id = ans.facts[idx].evidence_ref
    mut_path = ans.model_copy(
        update={
            "evidence_refs": [
                r.model_copy(update={"source_path": "/power/approved/by_booking_kw/nonexistent"})
                if r.ref_id == bad_ref_id
                else r
                for r in ans.evidence_refs
            ]
        }
    )
    with pytest.raises(AssertionError):
        _verify_against_independent_oracle(mut_path, closed, oracle)

    # 5. Mutate reason code
    mut_code = ans.model_copy(
        update={
            "reasons": [
                r.model_copy(update={"code": "WRONG_REASON"}) if r.code == oracle["reason_code"] else r
                for r in ans.reasons
            ]
        }
    )
    with pytest.raises(AssertionError):
        _verify_against_independent_oracle(mut_code, closed, oracle)


# ---- 5. Additional Edge Cases (Zero-Sample, Guard Block, Deadline Risk, Build Isolation) --


async def test_zero_sample_closed_trace_never_fabricates_zero_measured_power():
    b_dc = _make_booking("dc-1", zone="DC", kwh=30, hours=1.5)
    rt = await _sim_station(StrategyName.SIM_M3A, [b_dc])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    # Close immediately at 0 stepped minutes -> zero measured samples
    closed = decision_trace.close_open(rt)
    assert closed["validation"]["post_apply"] == "no_samples"

    ans = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="dc-1", topic=WhyTopic.POWER, at=T0),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[closed],
        bookings_override={"dc-1": b_dc},
    )
    assert "no_measured_samples" in ans.missing_evidence
    assert not any(f.name.startswith("power.measured") or f.name.startswith("energy.measured") for f in ans.facts)


async def test_planned_assignment_blocked_by_guard_and_pending_approval_not_connected():
    b_dc = _make_booking("dc-1", zone="DC", kwh=30, hours=1.5)
    rt = await _sim_station(StrategyName.SIM_M3A, [b_dc])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    active = rt.open_trace["trace"]

    # Case A: blocked by Business Guard
    guard_blocked = copy.deepcopy(active)
    guard_blocked["commands"] = [
        {
            "command_id": "cmd-blk",
            "type": "assign_connector",
            "connector_id": "DC-01-1",
            "booking_id": "dc-1",
            "power_kw": None,
            "source": "optimizer",
            "executed": False,
            "guard_passed": False,
            "approval_id": None,
            "note": "",
            "violations": [{"rule": "connector_faulted", "message": "faulted"}],
        }
    ]
    ans_blk = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.OWN_BOOKING, booking_id="dc-1", topic=WhyTopic.QUEUE, at=T0),
        _resident("res-dc-1"),
        station_id=rt.config.station_id,
        raw_traces=[guard_blocked],
        live_open_correlation_id=guard_blocked["correlation_id"],
        live_open_known=True,
        bookings_override={"dc-1": b_dc},
    )
    assert "PLANNED_ASSIGNMENT_BLOCKED_BY_GUARD" in {r.code for r in ans_blk.reasons}
    assert "ASSIGNMENT_DISPATCHED" not in {r.code for r in ans_blk.reasons}
    assert "VEHICLE_ALREADY_CONNECTED" not in {r.code for r in ans_blk.reasons}

    # Case B: pending approval
    pending = copy.deepcopy(active)
    pending["commands"] = [
        {
            "command_id": "cmd-pend",
            "type": "assign_connector",
            "connector_id": "DC-01-1",
            "booking_id": "dc-1",
            "power_kw": None,
            "source": "optimizer",
            "executed": False,
            "guard_passed": True,
            "approval_id": "appr-123",
            "note": "",
            "violations": [],
        }
    ]
    ans_pend = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.OWN_BOOKING, booking_id="dc-1", topic=WhyTopic.QUEUE, at=T0),
        _resident("res-dc-1"),
        station_id=rt.config.station_id,
        raw_traces=[pending],
        live_open_correlation_id=pending["correlation_id"],
        live_open_known=True,
        bookings_override={"dc-1": b_dc},
    )
    assert "PLANNED_ASSIGNMENT_PENDING_APPROVAL" in {r.code for r in ans_pend.reasons}
    assert "ASSIGNMENT_DISPATCHED" not in {r.code for r in ans_pend.reasons}


async def test_deadline_risk_separates_observed_missed_from_hardware_bound_and_projected_shortfall():
    b_dc = _make_booking("dc-1", zone="DC", kwh=50, hours=0.25)  # impossible in 15 min even at 60 kW
    rt = await _sim_station(StrategyName.SIM_M3A, [b_dc])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    rt.simulator.step(2)
    closed = decision_trace.close_open(rt)

    # 1. Before deadline: hardware bound + projected shortfall are INFERENCE_BOUND, never OBSERVED_DEADLINE_MISSED
    ans_bound = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.OWN_BOOKING,
            booking_id="dc-1",
            topic=WhyTopic.DEADLINE_RISK,
            at=T0 + timedelta(minutes=1),
        ),
        _resident("res-dc-1"),
        station_id=rt.config.station_id,
        raw_traces=[closed],
        bookings_override={"dc-1": b_dc},
    )
    codes_bound = {r.code for r in ans_bound.reasons}
    assert "SINGLE_VEHICLE_HARDWARE_BOUND_EXCEEDED" in codes_bound
    assert "PROJECTED_SHORTFALL_UNDER_PERSISTENCE" in codes_bound
    assert "OBSERVED_DEADLINE_MISSED" not in codes_bound
    hw = next(r for r in ans_bound.reasons if r.code == "SINGLE_VEHICLE_HARDWARE_BOUND_EXCEEDED")
    assert hw.category == EvidenceCategory.INFERENCE_BOUND
    proj = next(r for r in ans_bound.reasons if r.code == "PROJECTED_SHORTFALL_UNDER_PERSISTENCE")
    assert proj.category == EvidenceCategory.INFERENCE_BOUND

    # 2. Past deadline with remaining energy: OBSERVED_DEADLINE_MISSED (OBSERVED)
    past = copy.deepcopy(closed)
    past["planned"]["observed"]["vehicles"]["dc-1"]["deadline_minute"] = past["planned"]["minute"]
    past["planned"]["observed"]["vehicles"]["dc-1"]["remaining_kwh"] = 12.5
    ans_missed = explain_why(
        WhyQuery(
            subject_scope=WhySubjectScope.OWN_BOOKING,
            booking_id="dc-1",
            topic=WhyTopic.DEADLINE_RISK,
            at=T0 + timedelta(minutes=1),
        ),
        _resident("res-dc-1"),
        station_id=rt.config.station_id,
        raw_traces=[past],
        bookings_override={"dc-1": b_dc},
    )
    missed = next(r for r in ans_missed.reasons if r.code == "OBSERVED_DEADLINE_MISSED")
    assert missed.category == EvidenceCategory.OBSERVED


async def test_planned_facts_build_failure_is_isolated_from_control_loop(monkeypatch):
    b_dc = _make_booking("dc-1", zone="DC", kwh=30, hours=1.5)
    rt = await _sim_station(StrategyName.SIM_M3A, [b_dc])

    def boom(*_, **__):
        raise RuntimeError("planned facts boom")

    monkeypatch.setattr(rt.simulator, "planned_decision_facts", boom)
    # Control loop must still succeed even if planned_decision_facts raises
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt)
    active = rt.open_trace["trace"]
    assert active["planned"] is None

    ans = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.BOOKING, booking_id="dc-1", topic=WhyTopic.POWER, at=T0),
        _operator(),
        station_id=rt.config.station_id,
        raw_traces=[active],
        live_open_correlation_id=active["correlation_id"],
        live_open_known=True,
        bookings_override={"dc-1": b_dc},
    )
    assert ans.status == WhyStatus.PARTIAL
    assert "planned_diagnostics_unavailable" in ans.missing_evidence
