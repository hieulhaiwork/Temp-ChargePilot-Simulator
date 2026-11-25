"""Deterministic Gate 3 (AI-4.2A) Counterfactual Foundation & Outcome Ledger evaluation + mutation checks."""

import asyncio
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from src.models.charging import ChargeMode, ChargeRequest, ConsentScope, StrategyName
from src.models.control import Approval, ApprovalKind, Command, CommandSource, CommandType, GuardVerdict
from src.models.copilot import (
    EventManifest,
    KnownLimitEvent,
    OutcomeLedger,
    SnapshotEnvelope,
    SnapshotNotReadyReason,
    VehicleOutcomeStatus,
    VehicleReleaseReason,
)
from src.models.events import EventType, StationEvent
from src.models.simulation import Incident, IncidentType
from src.models.simulation_core import LimitEvent
from src.services import catalog, control_loop, energy, runtime
from src.services.copilot import (
    SnapshotNotReadyError,
    canonical_sha256,
    capture_atomic_snapshot,
    non_timing_branch_signature,
    run_paired_noop,
    run_sandbox_branch,
)
from src.services.runtime import build_sim_runtime, visit_of
from src.simulator.hybrid_station import HybridStation
from tests.factories import VN, booking


def _make_rt(strategy: StrategyName = StrategyName.SIM_M3A, *, vinfast_dc: bool = False):
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=VN)
    if vinfast_dc:
        station = HybridStation(config, start, dc_charging_model="vinfast_profiles_v0_1")
        station.reset(scenario)
        scheduler = runtime.make_scheduler(strategy, lambda: station)
        return runtime._memory_runtime(station, scheduler, config, tariff)
    return build_sim_runtime(scenario, strategy, config, tariff, start)


async def _run_cases(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    case_results: list[dict] = []

    # Case 1: Multi-vehicle AC + VinFast DC paired no-op parity + snapshot immutability
    rt1 = _make_rt(StrategyName.SIM_M3A, vinfast_dc=True)
    t0 = rt1.clock()
    for b in (
        booking("dc-vf8-1", zone="DC", kwh=28, hours=1.5, now=t0),
        booking("dc-vf8-2", zone="DC", kwh=22, hours=2.0, now=t0),
        booking("ac-vf8-1", zone="AC", kwh=18, hours=4.0, now=t0),
    ):
        rt1.store.save_booking(b)
        rt1.simulator.upsert_vehicle(visit_of(b, t0))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t0), rt1)
    live_hash_before = canonical_sha256(rt1.simulator.snapshot_physics_state())
    snap1 = await capture_atomic_snapshot(rt1, horizon_minutes=45)
    paired1 = await run_paired_noop(snap1, interleaved=True)
    ok1 = (
        paired1.applied is False
        and paired1.non_timing_kpis_equal
        and paired1.final_physics_digests_equal
        and snap1.recompute_digest() == snap1.envelope.snapshot_digest
        and canonical_sha256(rt1.simulator.snapshot_physics_state()) == live_hash_before
        and snap1.envelope.snapshot_digest != snap1.envelope.experiment_fingerprint
    )
    case_results.append({"case": "paired_noop_vinfast_interleaved", "passed": ok1})

    (out_dir / "example-snapshot-envelope.json").write_text(
        json.dumps(snap1.envelope.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "example-event-manifest.json").write_text(
        json.dumps(snap1.event_manifest.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "example-paired-noop-result.json").write_text(
        json.dumps(paired1.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Case 2: Independent hand-calculated energy & timestamp oracle (pre-snapshot vs horizon + DC unplug delay)
    rt2 = _make_rt(StrategyName.SIM_B0)
    t2 = rt2.clock()
    b_ac = booking("ac-11kw", zone="AC", kwh=22, hours=4.0, now=t2)
    rt2.store.save_booking(b_ac)
    rt2.simulator.upsert_vehicle(visit_of(b_ac, t2))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t2), rt2)
    for _ in range(12):
        ev = rt2.simulator.step(1)
        await control_loop.on_minute(rt2, ev)
    t_snap2 = rt2.simulator.now
    spec_vf3 = catalog.get_vehicle("VF3")
    est_vf3 = energy.estimate_energy(spec_vf3, soc_now=70, soc_target=80)
    req_vf3 = ChargeRequest(
        vehicle_model="VF3",
        soc_now=70,
        soc_target=80,
        deadline=t_snap2 + timedelta(minutes=90),
        mode=ChargeMode.WALK_IN,
        zone="DC",
    )
    b_vf3 = booking("dc-vf3", zone="DC", kwh=est_vf3.grid_energy_kwh, hours=1.5, now=t_snap2).model_copy(
        update={
            "request": req_vf3,
            "energy": est_vf3,
            "max_charge_power_kw": min(60.0, spec_vf3.max_dc_kw or 60.0),
            "created_at": t_snap2,
        }
    )
    rt2.store.save_booking(b_vf3)
    rt2.simulator.upsert_vehicle(visit_of(b_vf3, t_snap2))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t_snap2), rt2)

    snap2 = await capture_atomic_snapshot(rt2, horizon_minutes=30)
    branch2 = await run_sandbox_branch(snap2)
    led2 = branch2.outcome_ledger
    (out_dir / "example-outcome-ledger.json").write_text(
        json.dumps(led2.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    by2 = {v.booking_id: v for v in led2.vehicles}
    eta_conv = rt2.config.power_conversion_efficiency
    ok2 = (
        abs(by2["ac-11kw"].pre_snapshot_output_kwh - (11.0 * 12 / 60.0)) < 1e-5
        and abs(by2["ac-11kw"].horizon_output_kwh - (11.0 * 30 / 60.0)) < 1e-5
        and abs(by2["ac-11kw"].horizon_grid_input_kwh - (by2["ac-11kw"].horizon_output_kwh / eta_conv)) < 1e-5
        and by2["dc-vf3"].status == VehicleOutcomeStatus.COMPLETED_ON_TIME
        and by2["dc-vf3"].target_reached_at is not None
        and by2["dc-vf3"].release_or_departure_at
        == by2["dc-vf3"].target_reached_at + timedelta(minutes=rt2.config.dc_unplug_delay_minutes)
        and by2["dc-vf3"].release_reason == VehicleReleaseReason.DC_UNPLUG_DELAY
    )
    case_results.append({"case": "oracle_pre_vs_post_energy_and_dc_unplug", "passed": ok2})

    # Case 3: Plug-in vs delayed first-charge separation under pending approval
    rt3 = _make_rt(StrategyName.SIM_B0)
    t3 = rt3.clock()
    b_plug = booking("ac-plug-hold", zone="AC", kwh=15, hours=3.0, now=t3)
    rt3.store.save_booking(b_plug)
    rt3.simulator.upsert_vehicle(visit_of(b_plug, t3))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t3), rt3)
    conn3 = next(c.connector_id for c in rt3.simulator.state().connectors if c.booking_id == "ac-plug-hold")
    with rt3.simulator.lock:
        rt3.simulator.kernel.hold_setpoint("ac-plug-hold", 0.0)
    cmd3 = Command(
        type=CommandType.SET_POWER,
        connector_id=conn3,
        power_kw=7.0,
        booking_id="ac-plug-hold",
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=rt3.plan.version if rt3.plan else 1,
        based_on_state_at=t3,
        created_at=t3,
    )
    rt3.sinks.save_approval(
        Approval(
            kind=ApprovalKind.RESIDENT_CONSENT,
            command=cmd3,
            verdict=GuardVerdict(command_id=cmd3.command_id, passed=True, checked_at=t3),
            requested_from=b_plug.resident_id,
            impact_summary="Hold power",
            created_at=t3,
        )
    )
    snap3 = await capture_atomic_snapshot(rt3, horizon_minutes=20)
    rec3 = (await run_sandbox_branch(snap3)).outcome_ledger.vehicles[0]
    ok3 = rec3.plug_in_at == t3 and rec3.first_charge_at is None and rec3.horizon_output_kwh == 0.0
    case_results.append({"case": "oracle_plug_in_vs_first_charge_separation", "passed": ok3})

    # Case 4: NOT_ARRIVED preservation + censored cohort + empty SLA denominator -> None (never 1.0)
    rt4 = _make_rt()
    t4 = rt4.clock()
    b4_na = booking("res-na", zone="DC", kwh=25, hours=3.0, now=t4, arrival=t4 + timedelta(minutes=60))
    b4_ip = booking("ac-ip", zone="AC", kwh=44, hours=8.0, now=t4)
    for b in (b4_na, b4_ip):
        rt4.store.save_booking(b)
        rt4.simulator.upsert_vehicle(visit_of(b, t4))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t4), rt4)
    led4 = (await run_sandbox_branch(await capture_atomic_snapshot(rt4, horizon_minutes=20))).outcome_ledger
    ok4 = (
        led4.cohort_size == 2
        and led4.not_arrived_count == 1
        and led4.censored_count == 2
        and led4.sla_denominator == 0
        and led4.on_time_rate is None
        and led4.energy_bound_on_time_rate is None
    )
    case_results.append({"case": "oracle_not_arrived_censored_and_empty_sla_none", "passed": ok4})

    # Case 5: Unserved session under faulted DC connectors
    rt5 = _make_rt()
    t5 = rt5.clock()
    for c in rt5.config.connectors:
        if str(c.zone) == "DC":
            rt5.simulator.inject_incident(Incident(type=IncidentType.CONNECTOR_FAULT, connector_id=c.connector_id))
    b5 = booking("dc-unserved", zone="DC", kwh=20, hours=0.5, now=t5)
    rt5.store.save_booking(b5)
    rt5.simulator.upsert_vehicle(visit_of(b5, t5))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t5), rt5)
    led5 = (await run_sandbox_branch(await capture_atomic_snapshot(rt5, horizon_minutes=35))).outcome_ledger
    ok5 = (
        led5.unserved_count == 1
        and led5.sla_denominator == 1
        and led5.on_time_rate == 0.0
        and led5.vehicles[0].status == VehicleOutcomeStatus.UNSERVED_DEPARTED_OR_EXPIRED
    )
    case_results.append({"case": "oracle_unserved_session_zero_sla", "passed": ok5})

    # Case 6: Prospective known_at(T) strips future bookings & unannounced LimitEvents
    rt6 = _make_rt()
    t6 = rt6.clock()
    b6_known = booking("dc-k", zone="DC", kwh=20, hours=2.0, now=t6)
    b6_hidden = booking("dc-h", zone="DC", kwh=20, hours=2.0, now=t6, arrival=t6 + timedelta(minutes=10)).model_copy(
        update={"created_at": t6 + timedelta(minutes=5)}
    )
    for b in (b6_known, b6_hidden):
        rt6.store.save_booking(b)
        rt6.simulator.upsert_vehicle(visit_of(b, t6))
    with rt6.simulator.lock:
        rt6.simulator.kernel.scenario = replace(
            rt6.simulator.kernel.scenario,
            limit_events=(
                LimitEvent(effective_minute=10, announced_minute=0, grid_input_kw=50.0, cabinet_output_kw={}),
                LimitEvent(effective_minute=15, announced_minute=12, grid_input_kw=5.0, cabinet_output_kw={}),
            ),
        )
        rt6.simulator.kernel.grid_input_override_kw = None
    snap6 = await capture_atomic_snapshot(rt6, horizon_minutes=25)
    res6 = await run_sandbox_branch(snap6)
    ok6 = (
        snap6.event_manifest.known_booking_ids == ["dc-k"]
        and snap6.event_manifest.excluded_future_booking_count == 1
        and len(snap6.event_manifest.known_limit_events) == 1
        and snap6.event_manifest.excluded_unannounced_limit_event_count == 1
        and [v.booking_id for v in res6.outcome_ledger.vehicles] == ["dc-k"]
        and res6.outcome_ledger.horizon_sampled_grid_over_limit_minutes == 0
    )
    case_results.append({"case": "known_at_t_excludes_future_arrivals_and_unannounced_limits", "passed": ok6})

    # Case 7: Safety Hold & rejected consent parity
    rt7 = _make_rt()
    t7 = rt7.clock()
    b7_hold = booking("dc-hold", zone="DC", kwh=25, hours=2.0, now=t7)
    b7_rej = booking("ac-rej", zone="AC", kwh=15, hours=3.0, now=t7).model_copy(
        update={"consent": ConsentScope(allow_power_reduction=False)}
    )
    for b in (b7_hold, b7_rej):
        rt7.store.save_booking(b)
        rt7.simulator.upsert_vehicle(visit_of(b, t7))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t7), rt7)
    rt7.safety_hold_booking_ids.add("dc-hold")
    rt7.rejected_booking_ids.add("ac-rej")
    with rt7.simulator.lock:
        rt7.simulator.kernel.hold_setpoint("dc-hold", 0.0)
    paired7 = await run_paired_noop(await capture_atomic_snapshot(rt7, horizon_minutes=25))
    by7 = {v.booking_id: v for v in paired7.baseline.outcome_ledger.vehicles}
    ok7 = (
        paired7.non_timing_kpis_equal
        and by7["dc-hold"].horizon_output_kwh == 0.0
        and paired7.baseline.safety_hold_booking_ids_end == ["dc-hold"]
    )
    case_results.append({"case": "safety_hold_and_rejected_consent_parity", "passed": ok7})

    # Case 8: Unresolved hard safety event blocks snapshot capture without mutating live state
    rt8 = _make_rt()
    t8 = rt8.clock()
    rt8.queue_events(
        [
            StationEvent(event_id="ord-1", type=EventType.TICK, occurred_at=t8),
            StationEvent(
                event_id="hard-1",
                type=EventType.HARD_LIMIT_VIOLATED,
                occurred_at=t8,
                detail="Unresolved",
                violation_kinds=["charging_model"],
            ),
        ]
    )
    blocked8 = False
    try:
        await capture_atomic_snapshot(rt8, horizon_minutes=15)
    except SnapshotNotReadyError as exc:
        blocked8 = (
            exc.reason == SnapshotNotReadyReason.UNRESOLVED_HARD_SAFETY_EVENT
            and rt8.has_pending_safety()
            and [e.event_id for e in rt8.inspect_ordinary_outbox()] == ["ord-1"]
        )
    case_results.append({"case": "unresolved_safety_blocks_capture_cleanly", "passed": blocked8})

    # Contract & Oracle Mutation Detection (5 mutations must be caught)
    mutations_caught = 0
    total_mutations = 5

    # M1: snapshot_digest == experiment_fingerprint must fail SnapshotEnvelope validation
    try:
        SnapshotEnvelope.model_validate(
            {
                **snap1.envelope.model_dump(mode="json"),
                "snapshot_digest": snap1.envelope.experiment_fingerprint,
            }
        )
    except ValidationError:
        mutations_caught += 1

    # M2: on_time_rate = 1.0 when sla_denominator == 0 must fail OutcomeLedger validation
    try:
        OutcomeLedger.model_validate(
            {
                **led4.model_dump(mode="json"),
                "on_time_rate": 1.0,
            }
        )
    except ValidationError:
        mutations_caught += 1

    # M3: service_coverage_rate = 1.0 when service_coverage_denominator == 0 must fail OutcomeLedger validation
    empty_led = (await run_sandbox_branch(await capture_atomic_snapshot(_make_rt(), horizon_minutes=15))).outcome_ledger
    try:
        OutcomeLedger.model_validate(
            {
                **empty_led.model_dump(mode="json"),
                "service_coverage_rate": 1.0,
            }
        )
    except ValidationError:
        mutations_caught += 1

    # M4: censored vehicle claiming sla_evaluable=True must fail VehicleOutcomeRecord validation
    bad_veh = led4.vehicles[0].model_dump(mode="json")
    bad_veh["sla_evaluable"] = True
    bad_veh["met_original_sla"] = True
    try:
        OutcomeLedger.model_validate(
            {
                **led4.model_dump(mode="json"),
                "vehicles": [bad_veh, led4.vehicles[1].model_dump(mode="json")],
            }
        )
    except ValidationError:
        mutations_caught += 1

    # M5: EventManifest containing limit event announced after as_of_minute must fail validation
    try:
        EventManifest.model_validate(
            {
                **snap6.event_manifest.model_dump(mode="json"),
                "known_limit_events": [
                    KnownLimitEvent(
                        announced_minute=snap6.event_manifest.as_of_minute + 5,
                        announced_at=t6 + timedelta(minutes=5),
                        effective_minute=snap6.event_manifest.as_of_minute + 10,
                        effective_at=t6 + timedelta(minutes=10),
                        grid_input_kw=20.0,
                    ).model_dump(mode="json")
                ],
            }
        )
    except ValidationError:
        mutations_caught += 1

    # M6 check: non_timing_branch_signature detects a 1e-4 kWh ledger drift
    mutated_branch = paired1.counterfactual.model_copy(
        update={
            "outcome_ledger": paired1.counterfactual.outcome_ledger.model_copy(
                update={"horizon_output_kwh": paired1.counterfactual.outcome_ledger.horizon_output_kwh + 0.001}
            )
        }
    )
    total_mutations += 1
    if non_timing_branch_signature(paired1.baseline) != non_timing_branch_signature(mutated_branch):
        mutations_caught += 1

    passed_cases = sum(1 for c in case_results if c["passed"])
    summary = {
        "total_cases": len(case_results),
        "passed_cases": passed_cases,
        "mutations_total": total_mutations,
        "mutations_caught": mutations_caught,
        "cases": case_results,
    }
    (out_dir / "g3-eval-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("eval/evidence/2026-11-24-ai4-4-2a/raw/g3-eval")
    summary = asyncio.run(_run_cases(out_dir))
    print(
        f"G3 counterfactual eval: {summary['passed_cases']}/{summary['total_cases']} cases passed; "
        f"mutations caught: {summary['mutations_caught']}/{summary['mutations_total']}"
    )
    for row in summary["cases"]:
        status = "PASS" if row["passed"] else "FAIL"
        print(f"  [{status}] {row['case']}")
    if summary["passed_cases"] != summary["total_cases"] or summary["mutations_caught"] != summary["mutations_total"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
