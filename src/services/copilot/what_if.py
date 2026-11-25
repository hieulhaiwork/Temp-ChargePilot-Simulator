"""Authorized, paired WHAT-IF experiments on the shared counterfactual runner."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pydantic import Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

from src.models.charging import Booking, ChargeMode, ChargeRequest, EnergyEstimate
from src.models.control import Role
from src.models.copilot import ActorContext, OutcomeLedger, SandboxBranchResult, VehicleOutcomeRecord
from src.models.events import EventType, StationEvent
from src.models.station import SupplyMode
from src.models.what_if import (
    PATCH_ADAPTER,
    CommitmentOutcome,
    DeltaUnavailableReason,
    Outage,
    ReviseVehicle,
    SiteLimit,
    SlaMetrics,
    StationMetrics,
    WhatIfBranch,
    WhatIfPatch,
    WhatIfResult,
    WhatIfVehicleOutcome,
)
from src.services.copilot.counterfactual import LiveBusyProbe, run_sandbox_branch
from src.services.copilot.snapshot import CapturedSnapshot, canonical_sha256, verify_snapshot_integrity
from src.services.runtime import StationRuntime

SOC_EPS_PCT = 1e-8
DEFAULT_WHAT_IF_TIMEOUT_S = 60.0


class WhatIfForbiddenError(PermissionError):
    """The actor may not run this operation for the requested subject."""


class _HypotheticalChargeRequest(ChargeRequest):
    """A revised commitment can require zero additional charging at capture."""

    soc_target: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _check_consistency(self) -> "_HypotheticalChargeRequest":
        if self.mode == ChargeMode.RESERVATION and self.arrival_time is None:
            raise ValueError("Reservation requires arrival_time")
        if self.arrival_time is not None and self.deadline <= self.arrival_time:
            raise ValueError("Deadline must follow arrival_time")
        return self


class _HypotheticalBooking(Booking):
    request: _HypotheticalChargeRequest


@dataclass(frozen=True)
class PreparedWhatIf:
    patch: WhatIfPatch
    as_of_minute: int
    original_booking: Booking | None = None
    revised_booking: Booking | None = None
    target_changed: bool = False
    already_satisfied: bool = False
    outage_start: int | None = None
    outage_end: int | None = None
    hypothetical_infrastructure: bool = False


def _prepare_patch(
    snapshot: CapturedSnapshot, actor: ActorContext, patch: WhatIfPatch | dict[str, Any]
) -> PreparedWhatIf:
    if actor.station_id != snapshot.envelope.station_id:
        raise WhatIfForbiddenError("WHAT-IF operation not allowed")
    verify_snapshot_integrity(snapshot)
    data = patch if isinstance(patch, dict) else patch.model_dump(mode="python")
    patch = PATCH_ADAPTER.validate_python(data)
    minute = snapshot.envelope.sim_minute
    now = snapshot.envelope.as_of

    if isinstance(patch, ReviseVehicle):
        original = next((b for b in snapshot.known_bookings if b.booking_id == patch.booking_id), None)
        if original is None or (actor.role == Role.RESIDENT and original.resident_id != actor.actor_id):
            raise WhatIfForbiddenError("WHAT-IF operation not allowed")
        session = snapshot.physics_state["sessions"].get(original.booking_id)
        if session is None or session["state"] == "DEPARTED":
            raise ValueError("Booking must have an active or prospective physical session")
        deadline = original.request.deadline if patch.deadline is None else patch.deadline.astimezone(UTC)
        if patch.deadline is not None and (deadline - now.astimezone(UTC)) % timedelta(minutes=1):
            raise ValidationError.from_exception_data(
                "ReviseVehicle",
                [
                    {
                        "type": PydanticCustomError(
                            "deadline_not_on_simulator_minute",
                            "Revised deadline must align with a simulator minute relative to snapshot time",
                        ),
                        "loc": ("deadline",),
                        "input": patch.deadline,
                    }
                ],
            )
        arrival_at = datetime.fromisoformat(session["arrival_at"])
        if deadline <= max(now, arrival_at):
            raise ValueError("Revised deadline must follow snapshot time and vehicle arrival")

        target = original.request.soc_target if patch.target_soc is None else patch.target_soc
        target_changed = target != original.request.soc_target
        soc = float(session["current_soc"]) * 100
        arrived = session["state"] != "NOT_ARRIVED"
        attained = arrived and soc >= target - SOC_EPS_PCT
        if target_changed and not arrived and soc >= target - SOC_EPS_PCT:
            raise ValueError("A reservation below or at its assumed arrival SOC has no observed SOC at capture")

        request = {**original.request.model_dump(), "soc_target": target, "deadline": deadline}
        energy = original.energy
        if target_changed:
            needed = float(session["battery_capacity_kwh"]) * max(target - soc, 0.0) / 100
            request["soc_now"] = soc
            energy = EnergyEstimate(
                vehicle_model=energy.vehicle_model,
                soc_now=soc,
                soc_target=target,
                battery_energy_kwh=needed,
                grid_energy_kwh=needed / energy.efficiency,
                efficiency=energy.efficiency,
            )
        revised = _HypotheticalBooking.model_validate({**original.model_dump(), "request": request, "energy": energy})
        return PreparedWhatIf(
            patch=ReviseVehicle.model_validate({**data, "deadline": deadline if patch.deadline is not None else None}),
            as_of_minute=minute,
            original_booking=original.model_copy(deep=True),
            revised_booking=revised,
            target_changed=target_changed,
            already_satisfied=attained,
        )

    if actor.role != Role.OPERATOR:
        raise WhatIfForbiddenError("WHAT-IF operation not allowed")
    config = snapshot.station_config
    if isinstance(patch, SiteLimit):
        if config.supply_mode != SupplyMode.SHARED:
            raise ValueError("site_limit requires shared supply")
        installed = config.grid_input_limit_kw or config.power_limit_kw
        above_installed = patch.grid_input_kw > installed
        if above_installed and not patch.hypothetical_infrastructure:
            raise ValueError("Above-installed grid input requires hypothetical_infrastructure")
        supported_max = max(installed, config.nameplate_power_kw / config.power_conversion_efficiency)
        if patch.grid_input_kw > supported_max:
            raise ValueError("Grid input exceeds the supported station power envelope")
        return PreparedWhatIf(patch, minute, hypothetical_infrastructure=above_installed)

    if not any(port.connector_id == patch.connector_id for port in config.connectors):
        raise ValueError("Unknown connector")
    starts_at = (patch.starts_at or now).astimezone(UTC)
    seconds = (starts_at - now.astimezone(UTC)).total_seconds()
    if seconds < 0 or seconds % 60 != 0 or starts_at >= snapshot.event_manifest.horizon_end:
        raise ValueError("Outage must start on a simulator minute within the planned horizon")
    start = minute + int(seconds // 60)
    return PreparedWhatIf(
        Outage.model_validate({**data, "starts_at": starts_at}),
        minute,
        outage_start=start,
        outage_end=start + patch.duration_minutes,
    )


class _WhatIfIntervention:
    """One branch's private application state and observed revised target crossing."""

    def __init__(
        self,
        prepared: PreparedWhatIf | None,
        announced_grid: dict[int, float] | None = None,
        *,
        capture_minute: int,
    ):
        self.prepared = prepared
        self._announced_grid = announced_grid or {}
        self._capture_minute = capture_minute
        original = prepared.original_booking if prepared is not None and prepared.target_changed else None
        self.revised_booking_id = original.booking_id if original is not None else None
        self.revised_reached_at: datetime | None = None
        self._owns_outage = False
        self._skipped_fault = False
        self._applied_outage = False
        self._restored_outage = False

    def at_minute(self, runtime: StationRuntime, *, terminal: bool = False) -> list[StationEvent]:
        station = runtime.simulator
        if runtime.live or not station.is_fork:
            raise ValueError("WHAT-IF patches require an isolated sandbox")
        announced = None
        if not terminal and station.minute in self._announced_grid:
            announced = station.replay_sandbox_grid_limit(at_capture=station.minute == self._capture_minute)
        events = self._patch_at_minute(runtime, self.prepared, terminal=terminal) if self.prepared else []
        if announced is not None and not any(event.type == EventType.POWER_LIMIT_CHANGED for event in events):
            events.insert(0, announced)
        return events

    def _patch_at_minute(
        self, runtime: StationRuntime, prepared: PreparedWhatIf, *, terminal: bool
    ) -> list[StationEvent]:
        station = runtime.simulator
        patch = prepared.patch
        minute = station.minute
        at_start = minute == prepared.as_of_minute

        if isinstance(patch, Outage):
            if minute == prepared.outage_end and self._owns_outage:
                events = station.set_sandbox_connector_fault(patch.connector_id, faulted=False)
                self._owns_outage = False
                self._restored_outage = True
                return events
            if not terminal and minute == prepared.outage_start:
                if patch.connector_id in station.snapshot_physics_state()["faulted_connectors"]:
                    self._skipped_fault = True
                    return []
                events = station.set_sandbox_connector_fault(patch.connector_id, faulted=True)
                self._owns_outage = True
                self._applied_outage = True
                return events
            return []

        if terminal:
            return []
        if isinstance(patch, SiteLimit):
            if not at_start:
                return []
            future_increase = any(
                at > minute and limit > patch.grid_input_kw for at, limit in self._announced_grid.items()
            )
            if patch.grid_input_kw == station.effective_grid_limit_kw() and not future_increase:
                return []
            station.set_sandbox_grid_limit(patch.grid_input_kw)
            return [
                StationEvent(
                    type=EventType.POWER_LIMIT_CHANGED,
                    occurred_at=station.now,
                    new_power_limit_kw=station.effective_grid_limit_kw(),
                    detail="WHAT-IF grid input limit",
                )
            ]

        original, revised = prepared.original_booking, prepared.revised_booking
        if not at_start or original is None or revised is None or original.request == revised.request:
            return []
        event = station.revise_sandbox_vehicle(
            revised.booking_id,
            target=revised.request.soc_target / 100,
            deadline=revised.request.deadline,
            required_output_kwh=revised.energy.grid_energy_kwh,
        )
        runtime.store.save_booking(revised)
        return [event]

    def after_step(self, runtime: StationRuntime) -> None:
        if self.revised_booking_id is None or self.revised_reached_at is not None:
            return
        assert self.prepared is not None and self.prepared.revised_booking is not None
        if self.prepared.already_satisfied:
            return
        revised = self.prepared.revised_booking
        station = runtime.simulator
        with station.lock:
            session = station.queue.sessions[self.revised_booking_id]
            reached = station.adapter.soc(self.revised_booking_id) * 100 >= revised.request.soc_target - SOC_EPS_PCT
            if session.state != "NOT_ARRIVED" and reached:
                self.revised_reached_at = station.now

    def assumptions(self) -> tuple[str, ...]:
        assert self.prepared is not None
        if isinstance(self.prepared.patch, SiteLimit):
            return (
                "The site patch replaces the captured runtime supply setting and caps later regimes. "
                "Announced grid and cabinet limits and existing equipment caps still apply.",
            )
        if not isinstance(self.prepared.patch, Outage):
            return ()
        if self._skipped_fault:
            return ("Connector was already faulted at outage start. Its pre-existing fault was preserved.",)
        if self._restored_outage:
            return ("The patch-owned fault was restored at the end of its declared interval.",)
        if self._applied_outage:
            return ("Outage restoration falls after the observed rollout cutoff.",)
        return ("Outage start falls after the observed rollout cutoff.",)


def _station_metrics(branch: SandboxBranchResult, efficiencies: dict[str, float]) -> StationMetrics:
    ledger = branch.outcome_ledger
    plug_censored = sum(row.censored_plug_wait_minutes is not None for row in ledger.vehicles)
    charge_censored = sum(row.censored_charge_start_wait_minutes is not None for row in ledger.vehicles)
    return StationMetrics(
        cohort_size=ledger.cohort_size,
        sla=SlaMetrics(
            cohort_size=ledger.cohort_size,
            denominator=ledger.sla_denominator,
            met_count=ledger.sla_met_count,
            on_time_rate=ledger.on_time_rate,
            censored_count=ledger.censored_count,
        ),
        by_zone={
            name: SlaMetrics(
                cohort_size=zone.cohort_count,
                denominator=zone.sla_denominator,
                met_count=zone.sla_met_count,
                on_time_rate=zone.on_time_rate,
                censored_count=zone.censored_count,
            )
            for name, zone in ledger.by_zone.items()
        },
        service_coverage_denominator=ledger.service_coverage_denominator,
        service_coverage_rate=ledger.service_coverage_rate,
        charged_coverage_rate=ledger.charged_coverage_rate,
        unserved_count=ledger.unserved_count,
        plug_wait_observed_count=ledger.plug_wait_observed_count,
        plug_wait_censored_count=plug_censored,
        plug_wait_unknown_count=ledger.arrived_count - ledger.plug_wait_observed_count - plug_censored,
        plug_wait_mean_minutes=ledger.plug_wait_mean_minutes,
        plug_wait_p90_minutes=ledger.plug_wait_p90_minutes,
        charge_wait_observed_count=ledger.charge_start_wait_observed_count,
        charge_wait_censored_count=charge_censored,
        charge_wait_unknown_count=ledger.arrived_count - ledger.charge_start_wait_observed_count - charge_censored,
        charge_wait_mean_minutes=ledger.charge_start_wait_mean_minutes,
        charge_wait_p90_minutes=ledger.charge_start_wait_p90_minutes,
        horizon_battery_kwh=ledger.horizon_battery_stored_kwh,
        horizon_output_kwh=ledger.horizon_output_kwh,
        horizon_grid_input_kwh=ledger.horizon_grid_input_kwh,
        horizon_energy_cost_vnd=ledger.horizon_energy_cost_vnd,
        unmet_original_battery_kwh=ledger.remaining_to_original_target_battery_kwh,
        unmet_original_output_kwh=round(
            sum(row.remaining_to_original_target_battery_kwh / efficiencies[row.booking_id] for row in ledger.vehicles),
            6,
        ),
        peak_charger_output_kw=ledger.peak_charger_output_kw,
        peak_grid_input_kw=ledger.peak_grid_input_kw,
    )


def _summary(
    branch: SandboxBranchResult, config_hash: str, input_hash: str, efficiencies: dict[str, float]
) -> WhatIfBranch:
    ledger = branch.outcome_ledger
    return WhatIfBranch(
        run_id=uuid4().hex,
        input_sha256=input_hash,
        config_sha256=config_hash,
        final_physics_sha256=branch.final_physics_digest,
        status=branch.status,
        observed_until=branch.observed_until,
        metrics=_station_metrics(branch, efficiencies),
        hard_violations=ledger.horizon_applied_constraint_violation_count,
        rejected_allocations=ledger.horizon_rejected_allocation_count,
        sampled_grid_over_limit_minutes=ledger.horizon_sampled_grid_over_limit_minutes,
        unresolved_safety_count=branch.unresolved_safety_count,
        blocked_commands=branch.blocked_command_count,
        pending_approvals=branch.pending_approval_count_end,
        pending_approval_commands=ledger.horizon_pending_approval_command_count,
    )


def _original_outcome(row: VehicleOutcomeRecord, efficiency: float) -> CommitmentOutcome:
    return CommitmentOutcome(
        target_soc=row.original_target_soc_pct,
        deadline=row.original_deadline,
        target_reached_at=row.target_reached_at,
        already_satisfied_at_snapshot=row.already_completed_at_snapshot,
        met_deadline=row.met_original_sla,
        remaining_battery_kwh=row.remaining_to_original_target_battery_kwh,
        remaining_output_kwh=round(row.remaining_to_original_target_battery_kwh / efficiency, 6),
    )


def _revised_outcome(
    row: VehicleOutcomeRecord, patched: SandboxBranchResult, intervention: _WhatIfIntervention
) -> CommitmentOutcome:
    prepared = intervention.prepared
    assert prepared is not None and prepared.revised_booking is not None
    revised = prepared.revised_booking
    deadline = revised.request.deadline
    target = revised.request.soc_target
    attained = prepared.already_satisfied
    reached = intervention.revised_reached_at if prepared.target_changed else row.target_reached_at
    if reached is not None:
        met = reached <= deadline
    elif attained and patched.as_of <= deadline:
        met = True
    elif attained:
        met = None
    elif patched.observed_until >= deadline or row.final_session_state == "DEPARTED":
        met = False
    else:
        met = None
    remaining = row.remaining_to_original_target_battery_kwh
    if prepared.target_changed:
        battery_kwh = revised.energy.battery_energy_kwh
        remaining = 0.0 if attained or reached is not None else max(battery_kwh - row.horizon_battery_stored_kwh, 0)
    return CommitmentOutcome(
        target_soc=target,
        deadline=deadline,
        target_reached_at=reached,
        already_satisfied_at_snapshot=attained,
        met_deadline=met,
        remaining_battery_kwh=round(remaining, 6),
        remaining_output_kwh=round(remaining / revised.energy.efficiency, 6),
    )


def _metric_sample_ids(ledger: OutcomeLedger) -> dict[str, set[str]]:
    """Select the same wait observations and rate denominators as the Outcome Ledger."""
    rows = ledger.vehicles
    plug = {row.booking_id for row in rows if row.plug_wait_minutes is not None}
    charge = {row.booking_id for row in rows if row.charge_start_wait_minutes is not None}
    arrived = {row.booking_id for row in rows if row.arrived_at is not None}
    return {
        "plug_wait_mean_minutes": plug,
        "plug_wait_p90_minutes": plug,
        "charge_wait_mean_minutes": charge,
        "charge_wait_p90_minutes": charge,
        "service_coverage_rate": arrived,
        "charged_coverage_rate": arrived,
        "sla.on_time_rate": {row.booking_id for row in rows if row.sla_evaluable},
        **{
            f"sla.{zone}.on_time_rate": {row.booking_id for row in rows if row.sla_evaluable and row.zone == zone}
            for zone in ledger.by_zone
        },
    }


def _metric_values(metrics: StationMetrics) -> dict[str, float | None]:
    values = metrics.model_dump(exclude={"sla", "by_zone"})
    for prefix, sla in (("sla", metrics.sla), *((f"sla.{zone}", sla) for zone, sla in metrics.by_zone.items())):
        values.update({f"{prefix}.{key}": value for key, value in sla.model_dump().items()})
    return values


def _metrics_delta(
    baseline: StationMetrics, patched: StationMetrics, baseline_ledger: OutcomeLedger, patched_ledger: OutcomeLedger
) -> tuple[dict[str, float | None], dict[str, DeltaUnavailableReason]]:
    baseline_values, patched_values = _metric_values(baseline), _metric_values(patched)
    baseline_samples, patched_samples = _metric_sample_ids(baseline_ledger), _metric_sample_ids(patched_ledger)
    delta: dict[str, float | None] = {}
    reasons: dict[str, DeltaUnavailableReason] = {}
    for key in sorted(baseline_values):
        first, second = baseline_values[key], patched_values[key]
        if baseline_samples.get(key) != patched_samples.get(key):
            delta[key] = None
            reasons[key] = DeltaUnavailableReason(code="non_comparable_sample")
        elif first is None or second is None:
            delta[key] = None
            reasons[key] = DeltaUnavailableReason(code="missing_data")
        else:
            delta[key] = round(second - first, 6)
    return delta, reasons


async def run_what_if(
    snapshot: CapturedSnapshot,
    actor: ActorContext,
    patch: WhatIfPatch | dict[str, Any],
    *,
    timeout_s: float = DEFAULT_WHAT_IF_TIMEOUT_S,
    cancel_event: asyncio.Event | None = None,
    live_busy_probe: LiveBusyProbe | None = None,
) -> WhatIfResult:
    """Run a validated pair and return only the caller's authorized projections."""
    if not 0 < timeout_s <= 600:
        raise ValueError("WHAT-IF timeout must be in (0, 600] seconds")
    prepared = _prepare_patch(snapshot, actor, patch)
    capture_minute = snapshot.envelope.sim_minute
    announced_grid = {
        max(capture_minute, event.effective_minute): event.grid_input_kw
        for event in snapshot.event_manifest.known_limit_events
        if event.grid_input_kw is not None and event.effective_minute < snapshot.event_manifest.horizon_end_minute
    }
    intervention = _WhatIfIntervention(prepared, announced_grid, capture_minute=capture_minute)
    async with asyncio.timeout(timeout_s):
        baseline = await run_sandbox_branch(
            snapshot,
            cancel_event=cancel_event,
            live_busy_probe=live_busy_probe,
            intervention=(
                _WhatIfIntervention(None, announced_grid, capture_minute=capture_minute) if announced_grid else None
            ),
        )
        patched = await run_sandbox_branch(
            snapshot,
            branch_label="patched",
            cancel_event=cancel_event,
            live_busy_probe=live_busy_probe,
            intervention=intervention,
        )
    verify_snapshot_integrity(snapshot)

    safe = baseline.status == patched.status == "completed"
    full_window = baseline.observed_until == patched.observed_until == snapshot.event_manifest.horizon_end
    consistent = safe and full_window
    status = "completed" if consistent else "unsafe" if not safe else "incomplete"
    snap_hash = snapshot.envelope.snapshot_digest
    config_hash = snapshot.envelope.station_config_sha256
    patch_hash = canonical_sha256(prepared.patch.model_dump(mode="json"))
    patched_input_hash = canonical_sha256({"snapshot_sha256": snap_hash, "patch_sha256": patch_hash})
    patched_config_hash = (
        canonical_sha256({"station_config_sha256": config_hash, "site_grid_input_kw": prepared.patch.grid_input_kw})
        if isinstance(prepared.patch, SiteLimit)
        else config_hash
    )
    efficiencies = {b.booking_id: b.energy.efficiency for b in snapshot.known_bookings}
    base_summary = _summary(baseline, config_hash, snap_hash, efficiencies)
    patched_summary = _summary(patched, patched_config_hash, patched_input_hash, efficiencies)
    delta, delta_reasons = (
        _metrics_delta(base_summary.metrics, patched_summary.metrics, baseline.outcome_ledger, patched.outcome_ledger)
        if consistent
        else (None, None)
    )

    originals = {row.booking_id: row for row in baseline.outcome_ledger.vehicles}
    visible = {
        b.booking_id for b in snapshot.known_bookings if actor.role == Role.OPERATOR or b.resident_id == actor.actor_id
    }
    affected: list[WhatIfVehicleOutcome] = []
    feasible: bool | None = None if consistent else False
    for row in patched.outcome_ledger.vehicles:
        if row.booking_id not in visible:
            continue
        original = originals[row.booking_id]
        is_revised = prepared.revised_booking is not None and row.booking_id == prepared.revised_booking.booking_id
        if original == row and not is_revised:
            continue
        revised = _revised_outcome(row, patched, intervention) if is_revised else None
        if revised is not None and consistent:
            feasible = revised.met_deadline
        eff = efficiencies[row.booking_id]
        affected.append(
            WhatIfVehicleOutcome(
                booking_id=row.booking_id,
                baseline_original=_original_outcome(original, eff),
                patched_original=_original_outcome(row, eff),
                patched_revised=revised,
                baseline_plug_in_at=original.plug_in_at,
                patched_plug_in_at=row.plug_in_at,
                baseline_first_charge_at=original.first_charge_at,
                patched_first_charge_at=row.first_charge_at,
                baseline_release_at=original.release_or_departure_at,
                patched_release_at=row.release_or_departure_at,
                initial_soc_pct=row.initial_soc_pct,
                baseline_final_soc_pct=original.final_soc_pct,
                patched_final_soc_pct=row.final_soc_pct,
                baseline_horizon_battery_kwh=original.horizon_battery_stored_kwh,
                patched_horizon_battery_kwh=row.horizon_battery_stored_kwh,
            )
        )
    return WhatIfResult(
        status=status,
        snapshot_id=snapshot.envelope.snapshot_id,
        snapshot_digest=snap_hash,
        snapshot_time=snapshot.envelope.as_of,
        state_version=snapshot.envelope.state_version,
        experiment_fingerprint=snapshot.envelope.experiment_fingerprint,
        event_manifest_sha256=snapshot.event_manifest.manifest_sha256,
        horizon_end=snapshot.event_manifest.horizon_end,
        horizon_minutes=snapshot.envelope.horizon_minutes,
        known_booking_count=snapshot.envelope.known_booking_count,
        known_limit_event_count=len(snapshot.event_manifest.known_limit_events),
        patch=prepared.patch,
        patch_sha256=patch_hash,
        hypothetical_infrastructure=prepared.hypothetical_infrastructure,
        baseline=base_summary,
        patched=patched_summary,
        delta=delta,
        delta_reasons=delta_reasons,
        feasible=feasible,
        affected_vehicles=tuple(affected),
        assumptions=(
            *snapshot.event_manifest.assumptions,
            "Delta is patched minus baseline on a shared full safe observation window and matching metric samples.",
            "Station unmet energy is remaining energy to original targets at the observation cutoff.",
            "Station SLA uses original commitments. Revised SLA is reported separately.",
            "Remaining output equivalents use booking charging efficiency. Grid input denotes sampled station energy.",
            *intervention.assumptions(),
        ),
    )
