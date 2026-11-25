"""Additive Outcome Ledger for AI-4 counterfactual rollouts (Phase AI-4.2A: WP3.5).

Leaves frozen `HybridStation.outcomes()` and `simulation_service.compute_kpis()` completely untouched.
Fixes the evaluation cohort at snapshot time `T`, preserves original commitments (`target_soc`, `deadline`,
`arrival`), tracks post-snapshot energy deltas without double-counting pre-snapshot energy, separates
plug-in time from first-charging time and target-reached time from connector release/departure time,
preserves `NOT_ARRIVED` and censored vehicles explicitly, and returns `None` (never `1.0`) on empty
denominators.
"""

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.models.charging import Booking
from src.models.control import DecisionLogEntry
from src.models.copilot import (
    OUTCOME_LEDGER_SCHEMA_VERSION,
    OutcomeLedger,
    VehicleOutcomeRecord,
    VehicleOutcomeStatus,
    VehicleReleaseReason,
    ZoneSlaSummary,
)
from src.models.events import EventType, StationEvent
from src.models.station import StationConfig, Tariff
from src.simulator.hybrid_station import HybridStation

ENERGY_EPS_KWH = 1e-9
POWER_OVER_LIMIT_EPS_KW = 1e-6
FEASIBILITY_TOL_KWH = 0.05

LEDGER_ASSUMPTIONS: tuple[str, ...] = (
    "Pre-snapshot energies (delivered_battery_kwh, output_kwh, delivered_grid_kwh) are recorded separately and excluded from horizon_*_kwh and horizon_energy_cost_vnd.",
    "horizon_grid_input_kwh divides step charger-output kWh by station conversion efficiency once per physics step via StationKernel.",
    "Original Booking.energy.grid_energy_kwh retains its frozen FR3 charger-output meaning (battery_kwh / charging_efficiency); R10 billing changes remain out of AI-4.2A scope.",
    "The optimistic energy bound assumes continuous charging at the vehicle cap. It excludes contention, taper and hardware availability.",
    "Wait statistics include observed timestamps only. Historical charging starts are unknown when earlier energy has already accrued.",
    "Empty SLA or service coverage denominators evaluate to None rather than 1.0.",
    "Censored vehicles (original_deadline > observed_until and not yet completed) remain in the cohort and are excluded from sla_denominator.",
)


def _percentile_90(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(math.ceil(0.9 * len(ordered)) - 1, 0)
    return round(ordered[idx], 4)


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.fmean(values), 4)


@dataclass
class _VehicleRolloutState:
    booking: Booking
    usable_capacity_kwh: float
    original_arrival_at: datetime
    within_energy_bound: bool

    initial_session_state: str
    initial_soc_pct: float
    already_plugged_at_snapshot: bool
    already_completed_at_snapshot: bool
    pre_battery_kwh: float
    pre_output_kwh: float
    pre_grid_kwh: float

    prev_battery_kwh: float
    prev_output_kwh: float
    prev_grid_kwh: float
    prev_connector_id: str | None

    arrived_at: datetime | None = None
    assigned_connector_id: str | None = None
    plug_in_at: datetime | None = None
    first_charge_at: datetime | None = None
    first_rollout_charge_at: datetime | None = None
    historical_plug_unknown: bool = False
    target_reached_at: datetime | None = None
    release_or_departure_at: datetime | None = None
    release_reason: VehicleReleaseReason | None = None
    fault_unplug_count: int = 0

    horizon_battery_kwh: float = 0.0
    horizon_output_kwh: float = 0.0
    horizon_grid_kwh: float = 0.0


class OutcomeTracker:
    """Minute-by-minute observer attached to a single isolated sandbox `HybridStation` fork."""

    def __init__(
        self,
        *,
        station_config: StationConfig,
        tariff: Tariff,
        as_of: datetime,
        horizon_minutes: int,
        known_bookings: tuple[Booking, ...],
        station: HybridStation,
        revised_booking_id: str | None = None,
    ) -> None:
        self._config = station_config
        self._tariff = tariff
        self._tz = ZoneInfo(station_config.timezone)
        self._as_of = as_of
        self._horizon_minutes = horizon_minutes
        self._horizon_end = as_of + timedelta(minutes=horizon_minutes)
        self._revised_booking_id = revised_booking_id

        initial_phys = station.snapshot_physics_state()
        self._initial_applied_violations = int(
            initial_phys["constraint_counters"]["applied_constraint_violation_count"]
        )
        self._initial_rejected_allocations = int(initial_phys["constraint_counters"]["rejected_allocation_count"])

        sessions: dict[str, dict[str, Any]] = initial_phys["sessions"]
        self._vehicles: dict[str, _VehicleRolloutState] = {}

        for b in sorted(known_bookings, key=lambda item: item.booking_id):
            vid = b.booking_id
            s = sessions.get(vid)
            if s is not None:
                usable_cap = float(s["battery_capacity_kwh"])
                orig_arrival = datetime.fromisoformat(s["arrival_at"])
                init_state = str(s["state"])
                init_soc_pct = round(float(s["current_soc"]) * 100.0, 6)
                already_plugged = s["connector_id"] is not None
                already_completed = init_state != "NOT_ARRIVED" and (
                    float(s["current_capacity_kwh"]) >= usable_cap * b.request.soc_target / 100 - ENERGY_EPS_KWH
                    or s["completed_at"] is not None
                )
                pre_bat = float(s["delivered_battery_kwh"])
                pre_out = float(s["output_kwh"])
                pre_grid = float(s["delivered_grid_kwh"])
                arrived_at = orig_arrival if init_state != "NOT_ARRIVED" else None
                conn_id = s["connector_id"]
                had_plug = already_plugged or s["last_connector_id"] is not None or pre_out > ENERGY_EPS_KWH
                plug_at = orig_arrival if had_plug and s["charge_started_minute"] == s["arrival_minute"] else None
                historical_plug_unknown = had_plug and plug_at is None
                target_at = datetime.fromisoformat(s["completed_at"]) if s["completed_at"] is not None else None
                dep_at = datetime.fromisoformat(s["departed_at"]) if s["departed_at"] is not None else None
                rel_reason = None
                if dep_at is not None and s["departed_at_minute"] is not None:
                    rel_reason = (
                        VehicleReleaseReason.DC_UNPLUG_DELAY
                        if int(s["departed_at_minute"]) < int(s["departure_minute"])
                        else VehicleReleaseReason.DECLARED_DEPARTURE
                    )
            else:
                usable_cap = (
                    b.energy.battery_energy_kwh / ((b.request.soc_target - b.request.soc_now) / 100.0)
                    if b.request.soc_target > b.request.soc_now
                    else 0.0
                )
                orig_arrival = b.request.arrival_time or b.created_at
                init_state = "NOT_IN_SIMULATOR"
                init_soc_pct = float(b.request.soc_now)
                already_plugged = False
                already_completed = False
                pre_bat = 0.0
                pre_out = 0.0
                pre_grid = 0.0
                arrived_at = None
                conn_id = None
                plug_at = None
                historical_plug_unknown = False
                target_at = None
                dep_at = None
                rel_reason = None

            hours_avail = max(0.0, (b.request.deadline - orig_arrival).total_seconds() / 3600.0)
            feasible = b.max_charge_power_kw * hours_avail >= b.energy.grid_energy_kwh - FEASIBILITY_TOL_KWH

            self._vehicles[vid] = _VehicleRolloutState(
                booking=b,
                usable_capacity_kwh=usable_cap,
                original_arrival_at=orig_arrival,
                within_energy_bound=feasible,
                initial_session_state=init_state,
                initial_soc_pct=init_soc_pct,
                already_plugged_at_snapshot=already_plugged,
                already_completed_at_snapshot=already_completed,
                pre_battery_kwh=pre_bat,
                pre_output_kwh=pre_out,
                pre_grid_kwh=pre_grid,
                prev_battery_kwh=pre_bat,
                prev_output_kwh=pre_out,
                prev_grid_kwh=pre_grid,
                prev_connector_id=conn_id,
                arrived_at=arrived_at,
                assigned_connector_id=conn_id,
                plug_in_at=plug_at,
                historical_plug_unknown=historical_plug_unknown,
                target_reached_at=target_at,
                release_or_departure_at=dep_at,
                release_reason=rel_reason,
            )

        self._horizon_energy_cost_vnd = 0.0
        self._peak_output_kw = 0.0
        self._peak_grid_kw = 0.0
        self._sampled_over_limit_minutes = 0
        self._hard_safety_event_count = 0
        self._guard_blocked_commands = 0
        self._pending_approval_commands = 0

    def observe_after_dispatch(self, station: HybridStation, entries: list[DecisionLogEntry]) -> None:
        """Record dispatch outcomes and connector assignments at minute `m` BEFORE physics step `[m, m+1)`."""
        for entry in entries:
            if entry.approval_id is not None and not entry.executed:
                self._pending_approval_commands += 1
            elif not entry.executed:
                self._guard_blocked_commands += 1

        phys = station.snapshot_physics_state()
        at_dt = datetime.fromisoformat(phys["now_iso"])
        sessions = phys["sessions"]
        for vid, rec in self._vehicles.items():
            s = sessions.get(vid)
            if s is None:
                continue
            if rec.arrived_at is None and s["state"] != "NOT_ARRIVED":
                rec.arrived_at = datetime.fromisoformat(s["arrival_at"])
            conn_id = s["connector_id"]
            if conn_id is not None:
                if rec.plug_in_at is None and not rec.historical_plug_unknown:
                    rec.plug_in_at = at_dt
                if rec.assigned_connector_id is None:
                    rec.assigned_connector_id = conn_id
            elif rec.prev_connector_id is not None and s["state"] != "DEPARTED":
                rec.fault_unplug_count += 1
            rec.prev_connector_id = conn_id

    def observe_after_physics_step(
        self,
        station: HybridStation,
        *,
        step_start_minute: int,
        step_start_dt: datetime,
        emitted_events: list[StationEvent],
    ) -> None:
        """Record `[m, m+1)` energy deltas, charging start, completion, unplug/departure, TOU cost, and caps."""
        for ev in emitted_events:
            if ev.type == EventType.HARD_LIMIT_VIOLATED:
                self._hard_safety_event_count += 1

        phys = station.snapshot_physics_state()
        sessions = phys["sessions"]
        step_total_output_kwh = 0.0
        step_total_grid_kwh = 0.0

        for vid, rec in self._vehicles.items():
            s = sessions.get(vid)
            if s is None:
                continue
            if rec.arrived_at is None and s["state"] != "NOT_ARRIVED":
                rec.arrived_at = datetime.fromisoformat(s["arrival_at"])

            cur_bat = float(s["delivered_battery_kwh"])
            cur_out = float(s["output_kwh"])
            cur_grid = float(s["delivered_grid_kwh"])

            d_bat = max(0.0, cur_bat - rec.prev_battery_kwh)
            d_out = max(0.0, cur_out - rec.prev_output_kwh)
            d_grid = max(0.0, cur_grid - rec.prev_grid_kwh)

            rec.prev_battery_kwh = cur_bat
            rec.prev_output_kwh = cur_out
            rec.prev_grid_kwh = cur_grid

            rec.horizon_battery_kwh += d_bat
            rec.horizon_output_kwh += d_out
            rec.horizon_grid_kwh += d_grid

            step_total_output_kwh += d_out
            step_total_grid_kwh += d_grid

            if d_out > ENERGY_EPS_KWH and rec.first_rollout_charge_at is None:
                rec.first_rollout_charge_at = step_start_dt
                if rec.pre_output_kwh <= ENERGY_EPS_KWH:
                    rec.first_charge_at = step_start_dt

            if rec.target_reached_at is None and not rec.already_completed_at_snapshot:
                if vid == self._revised_booking_id:
                    target_kwh = rec.usable_capacity_kwh * rec.booking.request.soc_target / 100
                    if rec.arrived_at is not None and float(s["current_capacity_kwh"]) >= target_kwh - ENERGY_EPS_KWH:
                        rec.target_reached_at = station.now
                elif s["completed_at"] is not None:
                    rec.target_reached_at = datetime.fromisoformat(s["completed_at"])

            if s["departed_at"] is not None and rec.release_or_departure_at is None:
                rec.release_or_departure_at = datetime.fromisoformat(s["departed_at"])
                dep_min = int(s["departed_at_minute"])
                rec.release_reason = (
                    VehicleReleaseReason.DC_UNPLUG_DELAY
                    if dep_min < int(s["departure_minute"])
                    else VehicleReleaseReason.DECLARED_DEPARTURE
                )

            conn_id = s["connector_id"]
            if conn_id is None and rec.prev_connector_id is not None and s["state"] != "DEPARTED":
                rec.fault_unplug_count += 1
            rec.prev_connector_id = conn_id

        step_output_kw = step_total_output_kwh * 60.0
        step_grid_kw = step_total_grid_kwh * 60.0
        self._peak_output_kw = max(self._peak_output_kw, step_output_kw)
        self._peak_grid_kw = max(self._peak_grid_kw, step_grid_kw)

        price_vnd = self._tariff.price_at(step_start_dt.astimezone(self._tz).time())
        self._horizon_energy_cost_vnd += step_total_grid_kwh * price_vnd

        grid_cap_kw = station.effective_grid_limit_kw(minute=step_start_minute)
        if math.isfinite(grid_cap_kw) and step_grid_kw > grid_cap_kw + POWER_OVER_LIMIT_EPS_KW:
            self._sampled_over_limit_minutes += 1

    def finalize(self, station: HybridStation) -> OutcomeLedger:
        """Build immutable `OutcomeLedger` at `horizon_end` with explicit censoring and denominators."""
        final_phys = station.snapshot_physics_state()
        observed_until = station.now
        sessions = final_phys["sessions"]

        records: list[VehicleOutcomeRecord] = []
        plug_waits: list[float] = []
        charge_waits: list[float] = []

        for vid in sorted(self._vehicles):
            rec = self._vehicles[vid]
            b = rec.booking
            s = sessions.get(vid)

            if s is not None:
                final_state = str(s["state"])
                final_soc_pct = round(float(s["current_soc"]) * 100.0, 6)
                final_cap_kwh = float(s["current_capacity_kwh"])
                if rec.arrived_at is None and final_state != "NOT_ARRIVED":
                    rec.arrived_at = datetime.fromisoformat(s["arrival_at"])
                if vid != self._revised_booking_id and s["completed_at"] is not None and rec.target_reached_at is None:
                    rec.target_reached_at = datetime.fromisoformat(s["completed_at"])
                if s["departed_at"] is not None and rec.release_or_departure_at is None:
                    rec.release_or_departure_at = datetime.fromisoformat(s["departed_at"])
                    rec.release_reason = (
                        VehicleReleaseReason.DC_UNPLUG_DELAY
                        if int(s["departed_at_minute"]) < int(s["departure_minute"])
                        else VehicleReleaseReason.DECLARED_DEPARTURE
                    )
            else:
                final_state = rec.initial_session_state
                final_soc_pct = rec.initial_soc_pct
                final_cap_kwh = rec.usable_capacity_kwh * (final_soc_pct / 100.0)

            cum_bat = rec.pre_battery_kwh + rec.horizon_battery_kwh
            cum_out = rec.pre_output_kwh + rec.horizon_output_kwh
            cum_grid = rec.pre_grid_kwh + rec.horizon_grid_kwh
            desired_cap = rec.usable_capacity_kwh * (b.request.soc_target / 100.0)
            remaining_bat = max(0.0, desired_cap - final_cap_kwh)

            plug_wait: float | None = None
            censored_plug_wait: float | None = None
            if rec.arrived_at is not None:
                if rec.plug_in_at is not None:
                    plug_wait = round(max(0.0, (rec.plug_in_at - rec.arrived_at).total_seconds() / 60.0), 4)
                    plug_waits.append(plug_wait)
                elif not rec.historical_plug_unknown:
                    end_wait_ref = min(
                        b.request.deadline, observed_until, rec.release_or_departure_at or observed_until
                    )
                    if end_wait_ref >= rec.arrived_at:
                        censored_plug_wait = round((end_wait_ref - rec.arrived_at).total_seconds() / 60.0, 4)

            charge_wait: float | None = None
            censored_charge_wait: float | None = None
            if rec.arrived_at is not None and rec.first_charge_at is not None:
                charge_wait = round(max(0.0, (rec.first_charge_at - rec.arrived_at).total_seconds() / 60.0), 4)
                charge_waits.append(charge_wait)
            elif rec.arrived_at is not None and rec.pre_output_kwh <= ENERGY_EPS_KWH:
                end_wait_ref = min(b.request.deadline, observed_until, rec.release_or_departure_at or observed_until)
                if end_wait_ref >= rec.arrived_at:
                    censored_charge_wait = round((end_wait_ref - rec.arrived_at).total_seconds() / 60.0, 4)

            if rec.already_completed_at_snapshot and rec.target_reached_at is None:
                status = VehicleOutcomeStatus.ALREADY_COMPLETED_AT_SNAPSHOT
                met_sla = True if self._as_of <= b.request.deadline else None
                sla_evaluable = met_sla is not None
                censored = not sla_evaluable
                unserved = False
            elif rec.target_reached_at is not None:
                on_time = rec.target_reached_at <= b.request.deadline
                if rec.already_completed_at_snapshot:
                    status = VehicleOutcomeStatus.ALREADY_COMPLETED_AT_SNAPSHOT
                elif on_time:
                    status = VehicleOutcomeStatus.COMPLETED_ON_TIME
                else:
                    status = VehicleOutcomeStatus.COMPLETED_LATE
                sla_evaluable = True
                censored = False
                unserved = False
                met_sla: bool | None = on_time
            elif final_state in ("NOT_ARRIVED", "NOT_IN_SIMULATOR"):
                if b.request.deadline > observed_until:
                    status = VehicleOutcomeStatus.CENSORED_NOT_ARRIVED
                    sla_evaluable = False
                    censored = True
                    unserved = False
                    met_sla = None
                else:
                    status = VehicleOutcomeStatus.MISSED_DEADLINE_NOT_ARRIVED
                    sla_evaluable = True
                    censored = False
                    unserved = True
                    met_sla = False
            else:
                if final_state != "DEPARTED" and b.request.deadline > observed_until:
                    status = VehicleOutcomeStatus.CENSORED_IN_PROGRESS
                    sla_evaluable = False
                    censored = True
                    unserved = False
                    met_sla = None
                elif cum_bat <= ENERGY_EPS_KWH and cum_out <= ENERGY_EPS_KWH:
                    status = VehicleOutcomeStatus.UNSERVED_DEPARTED_OR_EXPIRED
                    sla_evaluable = True
                    censored = False
                    unserved = True
                    met_sla = False
                else:
                    status = VehicleOutcomeStatus.PARTIAL_MISSED_DEADLINE
                    sla_evaluable = True
                    censored = False
                    unserved = False
                    met_sla = False

            records.append(
                VehicleOutcomeRecord(
                    booking_id=vid,
                    zone=b.request.zone,
                    vehicle_model=b.request.vehicle_model,
                    within_optimistic_energy_bound=rec.within_energy_bound,
                    original_arrival_at=rec.original_arrival_at,
                    original_deadline=b.request.deadline,
                    original_soc_now_pct=round(float(b.request.soc_now), 6),
                    original_target_soc_pct=round(float(b.request.soc_target), 6),
                    original_required_battery_kwh=round(float(b.energy.battery_energy_kwh), 6),
                    original_required_output_kwh=round(float(b.energy.grid_energy_kwh), 6),
                    initial_session_state=rec.initial_session_state,
                    initial_soc_pct=rec.initial_soc_pct,
                    already_plugged_at_snapshot=rec.already_plugged_at_snapshot,
                    already_completed_at_snapshot=rec.already_completed_at_snapshot,
                    pre_snapshot_battery_stored_kwh=round(rec.pre_battery_kwh, 6),
                    pre_snapshot_output_kwh=round(rec.pre_output_kwh, 6),
                    pre_snapshot_grid_input_kwh=round(rec.pre_grid_kwh, 6),
                    arrived_at=rec.arrived_at,
                    assigned_connector_id=rec.assigned_connector_id,
                    plug_in_at=rec.plug_in_at,
                    first_charge_at=rec.first_charge_at,
                    first_rollout_charge_at=rec.first_rollout_charge_at,
                    historical_plug_time_unknown=rec.historical_plug_unknown,
                    target_reached_at=rec.target_reached_at,
                    release_or_departure_at=rec.release_or_departure_at,
                    release_reason=rec.release_reason,
                    plug_wait_minutes=plug_wait,
                    censored_plug_wait_minutes=censored_plug_wait,
                    charge_start_wait_minutes=charge_wait,
                    censored_charge_start_wait_minutes=censored_charge_wait,
                    fault_unplug_count=rec.fault_unplug_count,
                    horizon_battery_stored_kwh=round(rec.horizon_battery_kwh, 6),
                    horizon_output_kwh=round(rec.horizon_output_kwh, 6),
                    horizon_grid_input_kwh=round(rec.horizon_grid_kwh, 6),
                    final_session_state=final_state,
                    final_soc_pct=min(100.0, max(0.0, final_soc_pct)),
                    cumulative_battery_stored_kwh=round(cum_bat, 6),
                    cumulative_output_kwh=round(cum_out, 6),
                    cumulative_grid_input_kwh=round(cum_grid, 6),
                    remaining_to_original_target_battery_kwh=round(remaining_bat, 6),
                    status=status,
                    sla_evaluable=sla_evaluable,
                    censored=censored,
                    unserved=unserved,
                    met_original_sla=met_sla,
                )
            )

        by_zone: dict[str, ZoneSlaSummary] = {}
        for zone in ("AC", "DC"):
            z_rows = [r for r in records if r.zone == zone]
            by_zone[zone] = _build_zone_summary(zone, z_rows)

        cohort_size = len(records)
        arrived_rows = [r for r in records if r.arrived_at is not None]
        arrived_count = len(arrived_rows)
        not_arrived_count = cohort_size - arrived_count
        plugged_arrived = sum(1 for r in arrived_rows if r.plug_in_at is not None or r.historical_plug_time_unknown)
        charged_arrived = sum(
            1 for r in arrived_rows if r.first_charge_at is not None or r.cumulative_output_kwh > ENERGY_EPS_KWH
        )
        plugged_total = sum(1 for r in records if r.plug_in_at is not None or r.historical_plug_time_unknown)
        charged_total = sum(
            1 for r in records if r.first_charge_at is not None or r.cumulative_output_kwh > ENERGY_EPS_KWH
        )

        evaluable = [r for r in records if r.sla_evaluable]
        sla_denom = len(evaluable)
        sla_met = sum(1 for r in evaluable if r.met_original_sla is True)
        on_time_rate = round(sla_met / sla_denom, 6) if sla_denom > 0 else None

        feasible_eval = [r for r in evaluable if r.within_optimistic_energy_bound]
        feas_denom = len(feasible_eval)
        feas_met = sum(1 for r in feasible_eval if r.met_original_sla is True)
        feas_rate = round(feas_met / feas_denom, 6) if feas_denom > 0 else None

        svc_cov = round(plugged_arrived / arrived_count, 6) if arrived_count > 0 else None
        chg_cov = round(charged_arrived / arrived_count, 6) if arrived_count > 0 else None

        final_applied_viol = int(final_phys["constraint_counters"]["applied_constraint_violation_count"])
        final_rejected_alloc = int(final_phys["constraint_counters"]["rejected_allocation_count"])

        return OutcomeLedger(
            schema_version=OUTCOME_LEDGER_SCHEMA_VERSION,
            station_id=self._config.station_id,
            as_of=self._as_of,
            horizon_end=self._horizon_end,
            horizon_minutes=self._horizon_minutes,
            observed_until=observed_until,
            cohort_size=cohort_size,
            arrived_count=arrived_count,
            not_arrived_count=not_arrived_count,
            plugged_count=plugged_total,
            charged_count=charged_total,
            completed_on_time_count=sum(1 for r in records if r.status == VehicleOutcomeStatus.COMPLETED_ON_TIME),
            completed_late_count=sum(1 for r in records if r.status == VehicleOutcomeStatus.COMPLETED_LATE),
            already_completed_at_snapshot_count=sum(
                1 for r in records if r.status == VehicleOutcomeStatus.ALREADY_COMPLETED_AT_SNAPSHOT
            ),
            unserved_count=sum(1 for r in records if r.unserved),
            partial_missed_deadline_count=sum(
                1 for r in records if r.status == VehicleOutcomeStatus.PARTIAL_MISSED_DEADLINE
            ),
            censored_count=sum(1 for r in records if r.censored),
            censored_not_arrived_count=sum(1 for r in records if r.status == VehicleOutcomeStatus.CENSORED_NOT_ARRIVED),
            censored_in_progress_count=sum(1 for r in records if r.status == VehicleOutcomeStatus.CENSORED_IN_PROGRESS),
            sla_denominator=sla_denom,
            sla_met_count=sla_met,
            on_time_rate=on_time_rate,
            energy_bound_sla_denominator=feas_denom,
            energy_bound_sla_met_count=feas_met,
            energy_bound_on_time_rate=feas_rate,
            service_coverage_denominator=arrived_count,
            service_coverage_rate=svc_cov,
            charged_coverage_rate=chg_cov,
            plug_wait_observed_count=len(plug_waits),
            charge_start_wait_observed_count=len(charge_waits),
            plug_wait_mean_minutes=_mean_or_none(plug_waits),
            plug_wait_p90_minutes=_percentile_90(plug_waits),
            charge_start_wait_mean_minutes=_mean_or_none(charge_waits),
            charge_start_wait_p90_minutes=_percentile_90(charge_waits),
            pre_snapshot_battery_stored_kwh=round(sum(r.pre_snapshot_battery_stored_kwh for r in records), 6),
            pre_snapshot_output_kwh=round(sum(r.pre_snapshot_output_kwh for r in records), 6),
            pre_snapshot_grid_input_kwh=round(sum(r.pre_snapshot_grid_input_kwh for r in records), 6),
            horizon_battery_stored_kwh=round(sum(r.horizon_battery_stored_kwh for r in records), 6),
            horizon_output_kwh=round(sum(r.horizon_output_kwh for r in records), 6),
            horizon_grid_input_kwh=round(sum(r.horizon_grid_input_kwh for r in records), 6),
            horizon_energy_cost_vnd=round(self._horizon_energy_cost_vnd, 2),
            remaining_to_original_target_battery_kwh=round(
                sum(r.remaining_to_original_target_battery_kwh for r in records), 6
            ),
            peak_charger_output_kw=round(self._peak_output_kw, 6),
            peak_grid_input_kw=round(self._peak_grid_kw, 6),
            pre_snapshot_applied_constraint_violation_count=self._initial_applied_violations,
            horizon_applied_constraint_violation_count=max(0, final_applied_viol - self._initial_applied_violations),
            horizon_rejected_allocation_count=max(0, final_rejected_alloc - self._initial_rejected_allocations),
            horizon_sampled_grid_over_limit_minutes=self._sampled_over_limit_minutes,
            horizon_hard_safety_event_count=self._hard_safety_event_count,
            horizon_guard_blocked_command_count=self._guard_blocked_commands,
            horizon_pending_approval_command_count=self._pending_approval_commands,
            by_zone=by_zone,
            vehicles=records,
            assumptions=list(LEDGER_ASSUMPTIONS),
        )


def _build_zone_summary(zone: str, rows: list[VehicleOutcomeRecord]) -> ZoneSlaSummary:
    cohort_count = len(rows)
    arrived = [r for r in rows if r.arrived_at is not None]
    arrived_count = len(arrived)
    not_arrived_count = cohort_count - arrived_count
    plugged_arrived = sum(1 for r in arrived if r.plug_in_at is not None or r.historical_plug_time_unknown)
    plugged_count = sum(1 for r in rows if r.plug_in_at is not None or r.historical_plug_time_unknown)
    charged_count = sum(1 for r in rows if r.first_charge_at is not None or r.cumulative_output_kwh > ENERGY_EPS_KWH)
    unserved_count = sum(1 for r in rows if r.unserved)
    censored_count = sum(1 for r in rows if r.censored)

    evaluable = [r for r in rows if r.sla_evaluable]
    sla_denom = len(evaluable)
    sla_met = sum(1 for r in evaluable if r.met_original_sla is True)
    on_time = round(sla_met / sla_denom, 6) if sla_denom > 0 else None

    feas_eval = [r for r in evaluable if r.within_optimistic_energy_bound]
    feas_denom = len(feas_eval)
    feas_met = sum(1 for r in feas_eval if r.met_original_sla is True)
    feas_rate = round(feas_met / feas_denom, 6) if feas_denom > 0 else None

    svc_rate = round(plugged_arrived / arrived_count, 6) if arrived_count > 0 else None

    return ZoneSlaSummary(
        zone=zone,  # type: ignore[arg-type]
        cohort_count=cohort_count,
        arrived_count=arrived_count,
        not_arrived_count=not_arrived_count,
        plugged_count=plugged_count,
        charged_count=charged_count,
        unserved_count=unserved_count,
        censored_count=censored_count,
        sla_denominator=sla_denom,
        sla_met_count=sla_met,
        on_time_rate=on_time,
        energy_bound_sla_denominator=feas_denom,
        energy_bound_sla_met_count=feas_met,
        energy_bound_on_time_rate=feas_rate,
        service_coverage_rate=svc_rate,
    )
