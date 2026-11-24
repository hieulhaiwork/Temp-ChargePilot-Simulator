"""Deterministic WHY Engine evaluation suite (Phase AI-4.1 — Gate 2).

Zero LLM judge. Runs deterministic real-simulation and temporal/auth/privacy fixtures
through `explain_why` and evaluates all 5 Tech Lead Gate 2 metrics independently:
  1. fact_correctness
  2. causal_correctness
  3. evidence_ref_validity
  4. answer_coverage_and_abstention
  5. authorization_and_privacy_violations

Also writes concrete deterministic Resident and Operator WhyAnswer JSON examples.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zoneinfo import ZoneInfo  # noqa: E402

from src.models.charging import (  # noqa: E402
    Booking,
    BookingStatus,
    ChargeMode,
    ChargeRequest,
    EnergyEstimate,
    StrategyName,
)
from src.models.control import Role  # noqa: E402
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

VN = ZoneInfo("Asia/Ho_Chi_Minh")
CFG = catalog.load_station_config()
SCENARIO = catalog.load_scenario("hybrid_evening")
STATION_ID = CFG.station_id
T0 = datetime.combine(date(2026, 11, 24), SCENARIO.start_time, tzinfo=VN)


def _op() -> ActorContext:
    return ActorContext(actor_id="op-eval", role=Role.OPERATOR, station_id=STATION_ID)


def _res(actor_id: str) -> ActorContext:
    return ActorContext(actor_id=actor_id, role=Role.RESIDENT, station_id=STATION_ID)


def _booking(
    bid: str,
    *,
    resident_id: str | None = None,
    zone: str = "DC",
    kwh: float = 30.0,
    hours: float = 1.5,
    soc_now: float = 20.0,
    soc_target: float = 80.0,
) -> Booking:
    return Booking(
        booking_id=bid,
        resident_id=resident_id or f"res-{bid}",
        request=ChargeRequest(
            zone=zone,
            vehicle_model="VF8_NEW_2026",
            soc_now=soc_now,
            soc_target=soc_target,
            deadline=T0 + timedelta(hours=hours),
            arrival_time=None,
            mode=ChargeMode.WALK_IN,
        ),
        energy=EnergyEstimate(
            vehicle_model="VF8_NEW_2026",
            soc_now=soc_now,
            soc_target=soc_target,
            battery_energy_kwh=kwh,
            grid_energy_kwh=kwh,
            efficiency=1.0,
        ),
        status=BookingStatus.CONFIRMED,
        max_charge_power_kw=60.0 if zone == "DC" else 11.0,
        schedule_version=0,
        created_at=T0,
    )


async def _sim(strategy: StrategyName, bookings: list[Booking], *, supply_mode: str = "shared"):
    config = catalog.load_station_config()
    if supply_mode == "independent":
        raw = config.model_dump()
        raw["supply_mode"] = "independent"
        raw["independent_grid_input_limit_kw"] = {"AC": 25.0, "DC": 90.0}
        config = type(config).model_validate(raw)
    tariff = catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    rt = build_sim_runtime(scenario, strategy, config, tariff, T0)
    for b in bookings:
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, T0))
    return rt


def _check_refs(
    answer: WhyAnswer,
    traces_by_cid: dict[str, dict],
    actor: ActorContext,
    own_booking_id: str | None,
) -> tuple[int, int, list[str]]:
    total = 0
    valid = 0
    errors: list[str] = []
    ref_map = {r.ref_id: r for r in answer.evidence_refs}
    for ref in answer.evidence_refs:
        total += 1
        trace = traces_by_cid.get(ref.correlation_id)
        if trace is None:
            errors.append(f"unknown_correlation_id:{ref.correlation_id}")
            continue
        ok, _ = resolve_evidence_ref(ref, trace, actor, own_booking_id=own_booking_id)
        if ok:
            valid += 1
        else:
            errors.append(f"failed_deref:{ref.source_path}")
    for fact in answer.facts:
        if fact.evidence_ref not in ref_map:
            total += 1
            errors.append(f"missing_fact_ref:{fact.evidence_ref}")
    for reason in answer.reasons:
        for rid in reason.evidence_refs:
            if rid not in ref_map:
                total += 1
                errors.append(f"missing_reason_ref:{rid}")
    return valid, total, errors


async def run_evaluation(out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    examples: dict[str, dict[str, Any]] = {}

    # ---- Build real simulation fixtures ---------------------------------------------------
    # Fixture 1: M3a normal closed trace (DC + AC)
    b_dc1 = _booking("dc-1", zone="DC", kwh=30, hours=1.5)
    b_ac1 = _booking("ac-1", zone="AC", kwh=15, hours=3.0)
    rt1 = await _sim(StrategyName.SIM_M3A, [b_dc1, b_ac1])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt1)
    active_m3a = copy.deepcopy(rt1.open_trace["trace"])
    rt1.simulator.step(2)
    closed_m3a = decision_trace.close_open(rt1)

    # Fixture 2: B0 closed trace (must NEVER attribute TOU)
    rt_b0 = await _sim(StrategyName.SIM_B0, [b_ac1])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt_b0)
    rt_b0.simulator.step(2)
    closed_b0 = decision_trace.close_open(rt_b0)

    # Fixture 3: 3 DC vehicles -> queue occupied + waiting laxity
    b_q1 = _booking("dc-q1", zone="DC", kwh=40, hours=1.5)
    b_q2 = _booking("dc-q2", zone="DC", kwh=40, hours=1.5)
    b_q3 = _booking("dc-q3", zone="DC", kwh=40, hours=0.5)
    rt_q = await _sim(StrategyName.SIM_M3A, [b_q1, b_q2, b_q3])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt_q)
    rt_q.simulator.step(1)
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0 + timedelta(minutes=1)), rt_q)
    rt_q.simulator.step(1)
    closed_q = decision_trace.close_open(rt_q)
    queued_vid = next(
        vid for vid, row in closed_q["planned"]["observed"]["vehicles"].items() if row["state"] == "QUEUED"
    )

    # Fixture 4: Site cap drop + connector fault + DC taper
    b_taper = _booking("dc-taper", zone="DC", kwh=10, hours=1.5, soc_now=75.0, soc_target=90.0)
    rt_inc = await _sim(StrategyName.SIM_M3A, [b_taper, b_ac1])
    rt_inc.simulator.inject_incident(Incident(type=IncidentType.CONNECTOR_FAULT, connector_id="DC-01-2"))
    rt_inc.simulator.inject_incident(Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=30.0))
    await control_loop.on_event(
        StationEvent(type=EventType.POWER_LIMIT_CHANGED, occurred_at=T0, new_power_limit_kw=30.0), rt_inc
    )
    rt_inc.simulator.step(2)
    closed_inc = decision_trace.close_open(rt_inc)

    # Fixture 5: Independent supply + M3b dynamic slack
    rt_ind = await _sim(StrategyName.SIM_M3B, [b_dc1, b_ac1], supply_mode="independent")
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt_ind)
    rt_ind.simulator.step(2)
    closed_ind = decision_trace.close_open(rt_ind)

    # Fixture 6: Impossible hardware deadline bound
    b_tight = _booking("dc-tight", zone="DC", kwh=50, hours=0.25)
    rt_tight = await _sim(StrategyName.SIM_M3A, [b_tight])
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt_tight)
    rt_tight.simulator.step(2)
    closed_tight = decision_trace.close_open(rt_tight)

    # Fixture 7: Unknown coordinator reason code + violation with incomplete coverage
    tr_unknown = copy.deepcopy(closed_ind)
    tr_unknown["planned"]["coordinator"]["reason_codes"]["DC"].append("experimental_unverified_code")
    tr_viol_incomp = copy.deepcopy(closed_m3a)
    tr_viol_incomp["validation"]["post_apply"] = "violation"
    tr_viol_incomp["applied"]["guard_status"] = "violation"
    tr_viol_incomp["applied"]["coverage"]["status"] = "incomplete"
    tr_viol_incomp["applied"]["coverage"]["evicted_minutes"] = 5
    tr_viol_incomp["applied"]["hard_violation_count"] = 2
    tr_viol_incomp["applied"]["violation_reasons"] = ["site_grid_input_limit"]

    # Fixture 8: Safety hold blocking planned assignment
    rt_hold = await _sim(StrategyName.SIM_M3A, [b_dc1])
    rt_hold.safety_hold_booking_ids.add("dc-1")
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=T0), rt_hold)
    active_hold = copy.deepcopy(rt_hold.open_trace["trace"])

    # ---- Evaluation Spec ------------------------------------------------------------------
    # Each case specifies independent oracle checks for all 5 metrics
    specs = [
        {
            "id": "res_power_closed_m3a",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.OWN_BOOKING,
                booking_id="dc-1",
                topic=WhyTopic.POWER,
                at=T0 + timedelta(minutes=1),
            ),
            "actor": _res("res-dc-1"),
            "traces": [closed_m3a],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "expected_status": WhyStatus.OK,
            "oracle_facts": [
                (
                    "power.approved_output_kw",
                    "dc-1",
                    FactStage.APPROVED,
                    "kW",
                    closed_m3a["power"]["approved"]["by_booking_kw"]["dc-1"],
                ),
            ],
            "required_reasons": [("COORDINATOR_FIXED_SHARE", EvidenceCategory.POLICY_REASON)],
            "forbidden_reasons": ["AC_LP_TOU_OPTIMIZED", "OBSERVED_DEADLINE_MISSED"],
            "forbidden_leaks": ["ac-1", "res-ac-1", "AC-01-1", "AC-01-2"],
            "save_example": "resident_power",
        },
        {
            "id": "res_power_active_no_measured_fabrication",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.OWN_BOOKING,
                booking_id="dc-1",
                topic=WhyTopic.POWER,
                at=T0,
            ),
            "actor": _res("res-dc-1"),
            "traces": [active_m3a],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "live_cid": active_m3a["correlation_id"],
            "live_known": True,
            "expected_status": WhyStatus.PARTIAL,
            "required_missing": ["active_trace_no_measured_data"],
            "forbidden_fact_stages": [FactStage.MEASURED],
            "forbidden_leaks": ["ac-1", "res-ac-1"],
        },
        {
            "id": "op_b0_no_tou_attribution",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.BOOKING,
                booking_id="ac-1",
                topic=WhyTopic.POLICY,
                at=T0 + timedelta(minutes=1),
            ),
            "actor": _op(),
            "traces": [closed_b0],
            "bookings": {"ac-1": b_ac1},
            "expected_status": WhyStatus.OK,
            "oracle_facts": [("policy.id", "station", FactStage.CONFIG, None, "B0")],
            "required_reasons": [("COORDINATOR_FIXED_SHARE", EvidenceCategory.POLICY_REASON)],
            "forbidden_reasons": ["AC_LP_TOU_OPTIMIZED"],
        },
        {
            "id": "op_m3a_ac_lp_tou_policy",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.BOOKING,
                booking_id="ac-1",
                topic=WhyTopic.POLICY,
                at=T0 + timedelta(minutes=1),
            ),
            "actor": _op(),
            "traces": [closed_m3a],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "expected_status": WhyStatus.OK,
            "oracle_facts": [("policy.id", "station", FactStage.CONFIG, None, "M3a")],
            "required_reasons": [("AC_LP_TOU_OPTIMIZED", EvidenceCategory.POLICY_REASON)],
            "forbidden_reasons": [],
        },
        {
            "id": "res_queue_all_ports_occupied",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.OWN_BOOKING,
                booking_id=queued_vid,
                topic=WhyTopic.QUEUE,
                at=T0 + timedelta(minutes=1),
            ),
            "actor": _res(f"res-{queued_vid}"),
            "traces": [closed_q],
            "bookings": {"dc-q1": b_q1, "dc-q2": b_q2, "dc-q3": b_q3},
            "expected_status": WhyStatus.OK,
            "oracle_facts": [
                ("vehicle.observed_state", queued_vid, FactStage.OBSERVED, None, "QUEUED"),
                ("queue.observed_position", queued_vid, FactStage.OBSERVED, "rank", 1),
            ],
            "required_reasons": [("NO_FREE_COMPATIBLE_PORT", EvidenceCategory.OBSERVED)],
            "forbidden_reasons": ["VEHICLE_ALREADY_CONNECTED", "ASSIGNMENT_DISPATCHED"],
            "forbidden_leaks": [bid for bid in ("dc-q1", "dc-q2", "dc-q3") if bid != queued_vid],
            "save_example": "resident_queue",
        },
        {
            "id": "op_incident_fault_and_site_cap_taper",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.STATION,
                topic=WhyTopic.OVERVIEW,
                at=T0 + timedelta(minutes=1),
            ),
            "actor": _op(),
            "traces": [closed_inc],
            "bookings": {"dc-taper": b_taper, "ac-1": b_ac1},
            "expected_status": WhyStatus.OK,
            "oracle_facts": [
                ("limits.site_grid_input_kw", STATION_ID, FactStage.CONFIG, "kW", 30.0),
            ],
            "required_reasons": [("CONNECTOR_FAULT_ACTIVE", EvidenceCategory.OBSERVED)],
            "forbidden_reasons": ["NO_INCIDENT_OBSERVED"],
            "save_example": "operator_overview",
        },
        {
            "id": "op_power_dc_taper_and_source_limited",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.BOOKING,
                booking_id="dc-taper",
                topic=WhyTopic.POWER,
                at=T0 + timedelta(minutes=1),
            ),
            "actor": _op(),
            "traces": [closed_inc],
            "bookings": {"dc-taper": b_taper, "ac-1": b_ac1},
            "expected_status": WhyStatus.OK,
            "oracle_facts": [("limits.site_grid_input_kw", "station", FactStage.CONFIG, "kW", 30.0)],
            "required_reasons": [
                ("VEHICLE_ACCEPTANCE_TAPER_LIMIT", EvidenceCategory.BINDING_CONSTRAINT),
                ("COORDINATOR_SOURCE_LIMITED", EvidenceCategory.POLICY_REASON),
            ],
            "forbidden_reasons": [],
        },
        {
            "id": "op_independent_supply_m3b",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.BOOKING,
                booking_id="dc-1",
                topic=WhyTopic.POWER,
                at=T0 + timedelta(minutes=1),
            ),
            "actor": _op(),
            "traces": [closed_ind],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "expected_status": WhyStatus.OK,
            "oracle_facts": [],
            "required_reasons": [
                ("INDEPENDENT_SUPPLY_MODE", EvidenceCategory.OBSERVED),
                ("COORDINATOR_INDEPENDENT_SUPPLY", EvidenceCategory.POLICY_REASON),
            ],
            "forbidden_reasons": ["COORDINATOR_SHARED_SUPPLY_SCARCITY"],
        },
        {
            "id": "res_deadline_risk_hardware_bound_inference",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.OWN_BOOKING,
                booking_id="dc-tight",
                topic=WhyTopic.DEADLINE_RISK,
                at=T0 + timedelta(minutes=1),
            ),
            "actor": _res("res-dc-tight"),
            "traces": [closed_tight],
            "bookings": {"dc-tight": b_tight},
            "expected_status": WhyStatus.OK,
            "oracle_facts": [],
            "required_reasons": [
                ("SINGLE_VEHICLE_HARDWARE_BOUND_EXCEEDED", EvidenceCategory.INFERENCE_BOUND),
                ("PROJECTED_SHORTFALL_UNDER_PERSISTENCE", EvidenceCategory.INFERENCE_BOUND),
            ],
            "forbidden_reasons": ["OBSERVED_DEADLINE_MISSED"],
        },
        {
            "id": "op_unknown_coordinator_code_no_hallucination",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.BOOKING,
                booking_id="dc-1",
                topic=WhyTopic.POLICY,
                at=T0 + timedelta(minutes=1),
            ),
            "actor": _op(),
            "traces": [tr_unknown],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "expected_status": WhyStatus.OK,
            "oracle_facts": [],
            "required_reasons": [("UNKNOWN_POLICY_REASON_CODE", EvidenceCategory.POLICY_REASON)],
            "forbidden_reasons": [],
        },
        {
            "id": "op_violation_with_incomplete_coverage",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.STATION,
                topic=WhyTopic.INCIDENT,
                at=T0 + timedelta(minutes=1),
            ),
            "actor": _op(),
            "traces": [tr_viol_incomp],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "expected_status": WhyStatus.PARTIAL,
            "required_missing": ["incomplete_measured_coverage"],
            "oracle_facts": [
                ("validation.post_apply_status", "station", FactStage.MEASURED, None, "violation"),
            ],
            "required_reasons": [("POST_APPLY_HARD_VIOLATION", EvidenceCategory.OBSERVED)],
            "forbidden_reasons": ["NO_INCIDENT_OBSERVED"],
        },
        {
            "id": "op_stale_active_trace_after_restart_bounded",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.STATION,
                topic=WhyTopic.POWER,
                at=T0 + timedelta(minutes=20),
            ),
            "actor": _op(),
            "traces": [active_m3a],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "live_cid": None,
            "live_known": True,
            "expected_status": WhyStatus.NO_DATA,
            "required_missing": ["no_matching_decision_trace", "query_exceeds_available_evidence"],
            "oracle_facts": [],
            "required_reasons": [],
            "forbidden_reasons": [],
        },
        {
            "id": "op_stale_active_trace_within_planned_window_partial",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.STATION,
                topic=WhyTopic.POWER,
                at=T0 + timedelta(minutes=5),
            ),
            "actor": _op(),
            "traces": [active_m3a],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "live_cid": None,
            "live_known": True,
            "expected_status": WhyStatus.PARTIAL,
            "required_missing": ["active_trace_no_measured_data", "stale_active_trace_unclosed_after_restart"],
            "forbidden_fact_stages": [FactStage.MEASURED],
            "oracle_facts": [],
            "required_reasons": [],
            "forbidden_reasons": [],
        },
        {
            "id": "res_safety_hold_not_connected",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.OWN_BOOKING,
                booking_id="dc-1",
                topic=WhyTopic.QUEUE,
                at=T0,
            ),
            "actor": _res("res-dc-1"),
            "traces": [active_hold],
            "bookings": {"dc-1": b_dc1},
            "live_cid": active_hold["correlation_id"],
            "live_known": True,
            "expected_status": WhyStatus.PARTIAL,
            "required_missing": ["active_trace_no_measured_data"],
            "oracle_facts": [
                ("vehicle.observed_connector", "dc-1", FactStage.OBSERVED, None, None),
            ],
            "required_reasons": [("PLANNED_ASSIGNMENT_EXCLUDED_SAFETY_HOLD", EvidenceCategory.OBSERVED)],
            "forbidden_reasons": ["ASSIGNMENT_DISPATCHED", "VEHICLE_ALREADY_CONNECTED"],
        },
        {
            "id": "op_unsupported_topic_abstention",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.STATION,
                topic="future_what_if_scenario",
                at=T0,
            ),
            "actor": _op(),
            "traces": [closed_m3a],
            "bookings": {"dc-1": b_dc1},
            "expected_status": WhyStatus.UNSUPPORTED,
            "required_missing": ["unsupported_topic:future_what_if_scenario"],
            "oracle_facts": [],
            "required_reasons": [],
            "forbidden_reasons": [],
        },
        {
            "id": "op_no_data_beyond_trace_window",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.STATION,
                topic=WhyTopic.POWER,
                window=TimeWindow(start=T0 + timedelta(hours=3), end=T0 + timedelta(hours=4)),
            ),
            "actor": _op(),
            "traces": [closed_m3a],
            "bookings": {"dc-1": b_dc1},
            "expected_status": WhyStatus.NO_DATA,
            "required_missing": ["no_matching_decision_trace", "query_exceeds_available_evidence"],
            "oracle_facts": [],
            "required_reasons": [],
            "forbidden_reasons": [],
        },
        {
            "id": "auth_res_forbidden_station_scope",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.STATION,
                topic=WhyTopic.OVERVIEW,
                at=T0,
            ),
            "actor": _res("res-dc-1"),
            "traces": [closed_m3a],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "expected_status": WhyStatus.FORBIDDEN,
            "is_auth_deny": True,
            "oracle_facts": [],
            "required_reasons": [],
            "forbidden_reasons": [],
        },
        {
            "id": "auth_res_forbidden_other_booking",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.OWN_BOOKING,
                booking_id="ac-1",
                topic=WhyTopic.POWER,
                at=T0,
            ),
            "actor": _res("res-dc-1"),
            "traces": [closed_m3a],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "expected_status": WhyStatus.FORBIDDEN,
            "is_auth_deny": True,
            "oracle_facts": [],
            "required_reasons": [],
            "forbidden_reasons": [],
        },
        {
            "id": "auth_res_forbidden_nonexistent_non_enumerating",
            "query": WhyQuery(
                subject_scope=WhySubjectScope.OWN_BOOKING,
                booking_id="does-not-exist-999",
                topic=WhyTopic.POWER,
                at=T0,
            ),
            "actor": _res("res-dc-1"),
            "traces": [closed_m3a],
            "bookings": {"dc-1": b_dc1, "ac-1": b_ac1},
            "expected_status": WhyStatus.FORBIDDEN,
            "is_auth_deny": True,
            "oracle_facts": [],
            "required_reasons": [],
            "forbidden_reasons": [],
        },
    ]

    # Metrics accumulators
    facts_passed = 0
    facts_total = 0
    causal_passed = 0
    causal_total = 0
    refs_valid = 0
    refs_total = 0
    coverage_passed = 0
    coverage_total = 0
    auth_privacy_violations = 0

    auth_other_dump = None
    auth_missing_dump = None

    for spec in specs:
        actor: ActorContext = spec["actor"]
        query: WhyQuery = spec["query"]
        traces = spec["traces"]
        ans = explain_why(
            query,
            actor,
            station_id=STATION_ID,
            raw_traces=traces,
            bookings_override=spec["bookings"],
            live_open_correlation_id=spec.get("live_cid"),
            live_open_known=spec.get("live_known"),
        )
        if spec["id"] == "auth_res_forbidden_other_booking":
            auth_other_dump = (ans.status, ans.missing_evidence, ans.subject_id, ans.facts, ans.reasons)
        if spec["id"] == "auth_res_forbidden_nonexistent_non_enumerating":
            auth_missing_dump = (ans.status, ans.missing_evidence, ans.subject_id, ans.facts, ans.reasons)

        if "save_example" in spec:
            examples[spec["save_example"]] = ans.model_dump(mode="json")

        case_issues: list[str] = []

        # 1. Fact correctness
        for fname, fsubj, fstage, funit, fval in spec.get("oracle_facts", []):
            facts_total += 1
            match = next(
                (
                    f
                    for f in ans.facts
                    if f.name == fname
                    and f.subject == fsubj
                    and f.stage == fstage
                    and f.unit == funit
                    and f.value == fval
                ),
                None,
            )
            if match is not None:
                facts_passed += 1
            else:
                case_issues.append(f"fact_mismatch:{fname}")
        for bad_stage in spec.get("forbidden_fact_stages", []):
            facts_total += 1
            if not any(f.stage == bad_stage for f in ans.facts):
                facts_passed += 1
            else:
                case_issues.append(f"forbidden_stage:{bad_stage}")

        # 2. Causal correctness
        if spec.get("required_reasons") or spec.get("forbidden_reasons"):
            causal_total += 1
            reason_map = {r.code: r for r in ans.reasons}
            ok_req = all(
                code in reason_map and reason_map[code].category == cat
                for code, cat in spec.get("required_reasons", [])
            )
            ok_forb = all(code not in reason_map for code in spec.get("forbidden_reasons", []))
            if ok_req and ok_forb:
                causal_passed += 1
            else:
                case_issues.append(f"causal_mismatch:got={sorted(reason_map)}")

        # 3. Evidence reference validity
        traces_by_cid = {t["correlation_id"]: t for t in traces}
        own_bid = ans.subject_id if actor.role == Role.RESIDENT else None
        rv, rt_cnt, ref_errs = _check_refs(ans, traces_by_cid, actor, own_bid)
        refs_valid += rv
        refs_total += rt_cnt
        case_issues.extend(ref_errs)

        # 4. Answer coverage & abstention
        coverage_total += 1
        ok_status = ans.status == spec["expected_status"]
        ok_missing = all(m in ans.missing_evidence for m in spec.get("required_missing", []))
        if ok_status and ok_missing:
            coverage_passed += 1
        else:
            case_issues.append(f"coverage_mismatch:status={ans.status},missing={ans.missing_evidence}")

        # 5. Authorization & privacy violations
        if spec.get("is_auth_deny"):
            if ans.status != WhyStatus.FORBIDDEN or ans.facts or ans.reasons or ans.evidence_refs:
                auth_privacy_violations += 1
                case_issues.append("auth_deny_bypassed")
        if spec.get("forbidden_leaks"):
            blob = json.dumps(ans.model_dump(mode="json"))
            for token in spec["forbidden_leaks"]:
                if token in blob:
                    auth_privacy_violations += 1
                    case_issues.append(f"privacy_leak:{token}")

        cases.append(
            {
                "id": spec["id"],
                "status": ans.status.value,
                "facts_count": len(ans.facts),
                "reasons": [r.code for r in ans.reasons],
                "evidence_refs_count": len(ans.evidence_refs),
                "missing_evidence": ans.missing_evidence,
                "passed": not case_issues,
                "issues": case_issues,
            }
        )

    # Non-enumeration invariant check (unauthorized vs nonexistent booking_id must be identical)
    if auth_other_dump != auth_missing_dump:
        auth_privacy_violations += 1
        cases.append(
            {
                "id": "auth_non_enumeration_equivalence",
                "passed": False,
                "issues": [f"enumeration_diff:{auth_other_dump} != {auth_missing_dump}"],
            }
        )
    else:
        cases.append({"id": "auth_non_enumeration_equivalence", "passed": True, "issues": []})

    summary = {
        "suite": "ai4_4_1_deterministic_why_eval",
        "llm_judge_used": False,
        "cases_total": len(cases),
        "cases_passed": sum(1 for c in cases if c["passed"]),
        "metrics": {
            "fact_correctness": {
                "passed": facts_passed,
                "total": facts_total,
                "rate": round(facts_passed / facts_total, 4) if facts_total else 1.0,
            },
            "causal_correctness": {
                "passed": causal_passed,
                "total": causal_total,
                "rate": round(causal_passed / causal_total, 4) if causal_total else 1.0,
            },
            "evidence_ref_validity": {
                "valid": refs_valid,
                "total": refs_total,
                "rate": round(refs_valid / refs_total, 4) if refs_total else 1.0,
            },
            "answer_coverage_and_abstention": {
                "passed": coverage_passed,
                "total": coverage_total,
                "rate": round(coverage_passed / coverage_total, 4) if coverage_total else 1.0,
            },
            "authorization_and_privacy_violations": auth_privacy_violations,
        },
        "cases": cases,
    }

    (out_dir / "why-eval-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    for name, payload in examples.items():
        (out_dir / f"example-{name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return summary


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "raw" / "why-eval"
    summary = asyncio.run(run_evaluation(out_dir))
    m = summary["metrics"]
    print(f"Deterministic WHY Eval (LLM judge = {summary['llm_judge_used']})")
    print(f"Cases: {summary['cases_passed']}/{summary['cases_total']} passed")
    print(
        f"1. Fact correctness:               {m['fact_correctness']['passed']}/{m['fact_correctness']['total']} "
        f"({m['fact_correctness']['rate'] * 100:.1f}%)"
    )
    print(
        f"2. Causal correctness:             {m['causal_correctness']['passed']}/{m['causal_correctness']['total']} "
        f"({m['causal_correctness']['rate'] * 100:.1f}%)"
    )
    print(
        f"3. Evidence ref validity:          {m['evidence_ref_validity']['valid']}/{m['evidence_ref_validity']['total']} "
        f"({m['evidence_ref_validity']['rate'] * 100:.1f}%)"
    )
    print(
        f"4. Answer coverage & abstention:   {m['answer_coverage_and_abstention']['passed']}/{m['answer_coverage_and_abstention']['total']} "
        f"({m['answer_coverage_and_abstention']['rate'] * 100:.1f}%)"
    )
    print(f"5. Auth & privacy violations:      {m['authorization_and_privacy_violations']}")
    failed = [c for c in summary["cases"] if not c["passed"]]
    for c in failed:
        print(f"FAILED {c['id']}: {c['issues']}")
    return 0 if not failed and m["authorization_and_privacy_violations"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
