"""Evaluate a finite HOW-TO search using shared WHAT-IF interventions and sandbox execution."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter

from src.models.control import Role
from src.models.copilot import ActorContext, SandboxBranchResult, VehicleOutcomeRecord
from src.models.recommendation import (
    MAX_RECOMMENDATION_CANDIDATES,
    RECOMMENDATION_GOAL_ADAPTER,
    BookingSla,
    CandidateReason,
    CandidateSet,
    CandidateValue,
    EarliestCompletionForTarget,
    Feasibility,
    MaxSocByDeadline,
    MinTestedSiteLimitForSla,
    RecommendationCandidate,
    RecommendationEvidence,
    RecommendationGoal,
    RecommendationResult,
    SearchStatus,
)
from src.models.station import SupplyMode
from src.models.what_if import ReviseVehicle, SiteLimit, SlaMetrics, WhatIfPatch
from src.services.copilot.counterfactual import LiveBusyProbe, SandboxCancelledError, run_sandbox_branch
from src.services.copilot.snapshot import CapturedSnapshot, canonical_sha256, verify_snapshot_integrity
from src.services.copilot.what_if import (
    DEFAULT_WHAT_IF_TIMEOUT_S,
    SOC_EPS_PCT,
    PreparedWhatIf,
    WhatIfForbiddenError,
    _announced_grid_limits,
    _original_outcome,
    _prepare_patch,
    _revised_outcome,
    _WhatIfIntervention,
)
from src.services.runtime import StationRuntime

logger = logging.getLogger(__name__)

_MINUTE = timedelta(minutes=1)
_RANKING = {
    "max_soc_by_deadline": ("highest_tested_target_soc",),
    "earliest_completion_for_target": (
        "earliest_observed_target_attainment",
        "smallest_change_from_original_deadline",
        "earliest_requested_deadline",
    ),
    "min_tested_site_limit_for_sla": ("lowest_tested_grid_input_kw",),
}


class _DeadlineObservation(_WhatIfIntervention):
    def __init__(
        self, snapshot: CapturedSnapshot, prepared: PreparedWhatIf | None, goal: RecommendationGoal | None
    ) -> None:
        super().__init__(prepared, _announced_grid_limits(snapshot), capture_minute=snapshot.envelope.sim_minute)
        self.goal = goal
        self.deadline_soc_pct: float | None = None

    def after_step(self, runtime: StationRuntime) -> None:
        super().after_step(runtime)
        goal = self.goal
        if isinstance(goal, MaxSocByDeadline) and runtime.simulator.now == goal.deadline:
            station = runtime.simulator
            with station.lock:
                session = station.queue.sessions[goal.booking_id]
                if session.state != "NOT_ARRIVED":
                    self.deadline_soc_pct = station.adapter.soc(goal.booking_id) * 100


def _even_indices(size: int, limit: int) -> tuple[int, ...]:
    count = min(size, limit)
    if count == 1:
        return (0,)
    return tuple(i * (size - 1) // (count - 1) for i in range(count))


def _candidate_set(snapshot: CapturedSnapshot, goal: RecommendationGoal) -> CandidateSet:
    if isinstance(goal, MinTestedSiteLimitForSla):
        config = snapshot.station_config
        low, high = goal.min_grid_input_kw, goal.max_grid_input_kw
        if config.supply_mode != SupplyMode.SHARED:
            return CandidateSet(search_variable="grid_input_kw", values=())
        installed = config.grid_input_limit_kw or config.power_limit_kw
        if high > installed and not goal.hypothetical_infrastructure:
            raise ValueError("Above-installed grid input requires hypothetical_infrastructure")
        if high > max(installed, config.nameplate_power_kw / config.power_conversion_efficiency):
            raise ValueError("Grid input exceeds the supported station power envelope")
        count = MAX_RECOMMENDATION_CANDIDATES
        values = sorted({low, high, *(low + (high - low) * (i / (count - 1)) for i in range(1, count - 1))})
        return CandidateSet(search_variable="grid_input_kw", values=tuple(values))

    session = snapshot.physics_state["sessions"].get(goal.booking_id)
    if session is None or session["state"] == "DEPARTED":
        raise ValueError("Booking must have an active or prospective physical session")

    as_of = snapshot.envelope.as_of.astimezone(UTC)
    arrival = datetime.fromisoformat(session["arrival_at"])
    deadlines = (
        (goal.deadline,) if isinstance(goal, MaxSocByDeadline) else (goal.earliest_deadline, goal.latest_deadline)
    )
    for deadline in deadlines:
        if deadline <= max(as_of, arrival) or (deadline.astimezone(UTC) - as_of) % _MINUTE:
            raise ValueError("Deadlines must follow snapshot time and arrival and align with simulator minutes")

    if isinstance(goal, EarliestCompletionForTarget):
        start = goal.earliest_deadline.astimezone(UTC)
        size = (goal.latest_deadline.astimezone(UTC) - start) // _MINUTE + 1
        indices = _even_indices(size, MAX_RECOMMENDATION_CANDIDATES)
        return CandidateSet(search_variable="deadline", values=tuple(start + index * _MINUTE for index in indices))

    original = next(b for b in snapshot.known_bookings if b.booking_id == goal.booking_id)
    low, high = goal.min_target_soc, goal.max_target_soc
    current_soc = session["current_soc"] * 100
    anchors = {low, high, *(v for v in (original.request.soc_target, current_soc) if low <= v <= high)}
    grid = sorted({float(v) for v in range(0, 101, 5) if low < v < high} - anchors)
    if grid:
        indices = _even_indices(len(grid), MAX_RECOMMENDATION_CANDIDATES - len(anchors))
        anchors.update(grid[i] for i in indices)
    return CandidateSet(search_variable="target_soc_pct", values=tuple(sorted(anchors)))


def _patch(goal: RecommendationGoal, value: CandidateValue) -> WhatIfPatch:
    if isinstance(goal, MinTestedSiteLimitForSla):
        return SiteLimit(
            op="site_limit", grid_input_kw=value, hypothetical_infrastructure=goal.hypothetical_infrastructure
        )
    if isinstance(goal, MaxSocByDeadline):
        return ReviseVehicle(op="revise_vehicle", booking_id=goal.booking_id, target_soc=value, deadline=goal.deadline)
    return ReviseVehicle(op="revise_vehicle", booking_id=goal.booking_id, target_soc=goal.target_soc, deadline=value)


def _unsafe_reason(snapshot: CapturedSnapshot, branch: SandboxBranchResult) -> CandidateReason | None:
    ledger = branch.outcome_ledger
    if (
        branch.status != "completed"
        or branch.unresolved_safety_count
        or ledger.horizon_applied_constraint_violation_count
    ):
        return CandidateReason.UNSAFE
    if snapshot.safety_hold_booking_ids or branch.safety_hold_booking_ids_end:
        return CandidateReason.SAFETY_HOLD
    if snapshot.pending_approvals or branch.pending_approval_count_end or ledger.horizon_pending_approval_command_count:
        return CandidateReason.PENDING_APPROVAL
    if ledger.horizon_rejected_allocation_count:
        return CandidateReason.REJECTED_ALLOCATION
    if branch.blocked_command_count:
        return CandidateReason.BLOCKED_COMMAND
    if branch.observed_until != branch.horizon_end:
        return CandidateReason.INCOMPLETE_OBSERVATION
    return None


def _evidence(
    snapshot: CapturedSnapshot,
    goal: RecommendationGoal,
    branch: SandboxBranchResult,
    intervention: _DeadlineObservation,
) -> RecommendationEvidence:
    prepared = intervention.prepared
    snapshot_sha = snapshot.envelope.snapshot_digest
    config_sha = snapshot.envelope.station_config_sha256
    input_sha = snapshot_sha
    if prepared is not None:
        patch = prepared.patch
        input_sha = canonical_sha256({"snapshot_sha256": snapshot_sha, "patch": patch.model_dump(mode="json")})
        if isinstance(patch, SiteLimit):
            config_sha = canonical_sha256(
                {"station_config_sha256": config_sha, "site_grid_input_kw": patch.grid_input_kw}
            )
    ledger = branch.outcome_ledger
    common = dict(
        ref=f"how-to:branch:{input_sha}",
        input_sha256=input_sha,
        config_sha256=config_sha,
        final_physics_sha256=branch.final_physics_digest,
        observed_until=branch.observed_until,
        branch_status=branch.status,
        hard_violations=ledger.horizon_applied_constraint_violation_count,
        rejected_allocations=ledger.horizon_rejected_allocation_count,
        safety_holds=len(set(branch.safety_hold_booking_ids_end) | snapshot.safety_hold_booking_ids),
        unresolved_safety_count=branch.unresolved_safety_count,
        blocked_commands=branch.blocked_command_count,
        pending_approvals=branch.pending_approval_count_end,
        pending_approval_commands=ledger.horizon_pending_approval_command_count,
        elapsed_ms=branch.wall_time_ms,
    )
    if isinstance(goal, MinTestedSiteLimitForSla):
        efficiencies = {b.booking_id: b.energy.efficiency for b in snapshot.known_bookings}
        return RecommendationEvidence(
            **common,
            original_sla=SlaMetrics(
                cohort_size=ledger.cohort_size,
                denominator=ledger.sla_denominator,
                met_count=ledger.sla_met_count,
                on_time_rate=ledger.on_time_rate,
                censored_count=ledger.censored_count,
            ),
            booking_sla=tuple(
                BookingSla(
                    booking_id=row.booking_id,
                    zone=row.zone,
                    original=_original_outcome(row, efficiencies[row.booking_id]),
                )
                for row in ledger.vehicles
            ),
        )

    row = next(row for row in ledger.vehicles if row.booking_id == goal.booking_id)
    eff = next(b.energy.efficiency for b in snapshot.known_bookings if b.booking_id == goal.booking_id)
    return RecommendationEvidence(
        **common,
        subject_original=_original_outcome(row, eff),
        subject_revised=_revised_outcome(row, branch, intervention) if prepared else None,
        subject_soc_at_deadline_pct=intervention.deadline_soc_pct,
        subject_release_at=row.release_or_departure_at,
    )


def _preservation_issue(
    baseline: dict[str, VehicleOutcomeRecord],
    branch: SandboxBranchResult,
    goal: RecommendationGoal,
) -> CandidateReason | None:
    unknown = False
    for row in branch.outcome_ledger.vehicles:
        if isinstance(goal, MinTestedSiteLimitForSla):
            if not goal.protect_on_time_ac_bookings or row.zone != "AC":
                continue
        elif row.booking_id == goal.booking_id and goal.allow_subject_original_sla_regression:
            continue
        original, new = baseline[row.booking_id].met_original_sla, row.met_original_sla
        if original is True and new is False:
            return CandidateReason.ORIGINAL_SLA_REGRESSION
        unknown |= original is not False and new is not True
    return CandidateReason.UNKNOWN_SLA if unknown else None


def _assess(
    goal: RecommendationGoal,
    baseline: dict[str, VehicleOutcomeRecord],
    branch: SandboxBranchResult,
    evidence: RecommendationEvidence,
) -> tuple[Feasibility, CandidateReason | None]:
    protection = _preservation_issue(baseline, branch, goal)
    if protection == CandidateReason.ORIGINAL_SLA_REGRESSION:
        return Feasibility.INFEASIBLE, protection
    if isinstance(goal, MinTestedSiteLimitForSla):
        sla = evidence.original_sla
        assert sla is not None
        if not sla.cohort_size:
            return Feasibility.UNKNOWN, CandidateReason.EMPTY_COHORT
        if sla.denominator != sla.cohort_size or sla.censored_count:
            return Feasibility.UNKNOWN, CandidateReason.UNKNOWN_SLA
        if sla.met_count / sla.cohort_size < goal.min_original_on_time_rate:
            return Feasibility.INFEASIBLE, CandidateReason.SITE_SLA_NOT_MET
    else:
        revised = evidence.subject_revised
        assert revised is not None
        if isinstance(goal, MaxSocByDeadline):
            soc_at_deadline = evidence.subject_soc_at_deadline_pct
            if soc_at_deadline is None:
                return Feasibility.UNKNOWN, CandidateReason.INCOMPLETE_OBSERVATION
            attained = soc_at_deadline >= revised.target_soc - SOC_EPS_PCT and revised.met_deadline is True
        else:
            attained = revised.met_deadline
            if attained is None:
                return Feasibility.UNKNOWN, CandidateReason.INCOMPLETE_OBSERVATION
        if not attained:
            return Feasibility.INFEASIBLE, CandidateReason.TARGET_NOT_MET
    if protection is not None:
        return Feasibility.UNKNOWN, protection
    return Feasibility.FEASIBLE, None


def _rank(
    candidates: list[RecommendationCandidate],
    goal: RecommendationGoal,
    baseline: RecommendationEvidence | None,
    as_of: datetime,
) -> tuple[RecommendationCandidate, ...]:
    eligible = [candidate for candidate in candidates if candidate.feasibility == Feasibility.FEASIBLE]
    if isinstance(goal, MaxSocByDeadline):
        eligible.sort(key=lambda candidate: candidate.value, reverse=True)
    elif isinstance(goal, MinTestedSiteLimitForSla):
        eligible.sort(key=lambda candidate: candidate.value)
    else:

        def completion_key(candidate: RecommendationCandidate) -> tuple[datetime, timedelta, datetime]:
            assert baseline and baseline.subject_original and candidate.evidence and candidate.evidence.subject_revised
            revised = candidate.evidence.subject_revised
            reached = max(as_of, revised.target_reached_at or as_of)
            return reached, abs(revised.deadline - baseline.subject_original.deadline), revised.deadline

        eligible.sort(key=completion_key)
    return tuple(eligible[:3])


async def run_recommendation(
    snapshot: CapturedSnapshot,
    actor: ActorContext,
    goal: RecommendationGoal | dict,
    *,
    timeout_s: float = DEFAULT_WHAT_IF_TIMEOUT_S,
    cancel_event: asyncio.Event | None = None,
    live_busy_probe: LiveBusyProbe | None = None,
) -> RecommendationResult:
    """Run one bounded search on a detached snapshot. Actor identity comes from the trusted caller."""
    if not 0 < timeout_s <= 600:
        raise ValueError("HOW-TO timeout must be in (0, 600] seconds")
    goal = RECOMMENDATION_GOAL_ADAPTER.validate_python(goal if isinstance(goal, dict) else goal.model_dump())
    is_site = isinstance(goal, MinTestedSiteLimitForSla)
    if actor.station_id != snapshot.envelope.station_id or actor.role != (Role.OPERATOR if is_site else Role.RESIDENT):
        raise WhatIfForbiddenError("HOW-TO operation not allowed")
    if not is_site and not any(
        b.booking_id == goal.booking_id and b.resident_id == actor.actor_id for b in snapshot.known_bookings
    ):
        raise WhatIfForbiddenError("HOW-TO operation not allowed")

    started = perf_counter()
    loop = asyncio.get_running_loop()
    expires = loop.time() + timeout_s
    verify_snapshot_integrity(snapshot)
    envelope = snapshot.envelope
    planned = _candidate_set(snapshot, goal)
    baseline = None
    baseline_rows: dict[str, VehicleOutcomeRecord] = {}
    baseline_issue = None
    candidates: list[RecommendationCandidate] = []
    baseline_count = branch_count = 0
    stopped = None

    async def execute(
        intervention: _DeadlineObservation, label: str
    ) -> tuple[SandboxBranchResult | None, CandidateReason | None]:
        nonlocal branch_count
        if cancel_event is not None and cancel_event.is_set():
            return None, CandidateReason.CANCELLED
        remaining = expires - loop.time()
        if remaining <= 0:
            return None, CandidateReason.TIMEOUT
        branch_count += 1
        try:
            branch = await run_sandbox_branch(
                snapshot,
                branch_label=label,
                intervention=intervention,
                timeout_s=remaining,
                cancel_event=cancel_event,
                live_busy_probe=live_busy_probe,
            )
        except SandboxCancelledError:
            return None, CandidateReason.CANCELLED
        except TimeoutError:
            return None, CandidateReason.TIMEOUT
        except Exception as error:
            logger.error("how_to_branch_failed branch=%s error_type=%s", label, type(error).__name__)
            return None, CandidateReason.EXECUTION_FAILED
        return branch, None

    unsupported = is_site and snapshot.station_config.supply_mode != SupplyMode.SHARED
    if not unsupported:
        observer = _DeadlineObservation(snapshot, None, goal)
        branch, baseline_issue = await execute(observer, "baseline")
        if branch is not None:
            baseline = _evidence(snapshot, goal, branch, observer)
            baseline_rows = {row.booking_id: row for row in branch.outcome_ledger.vehicles}
            baseline_issue = _unsafe_reason(snapshot, branch)
        baseline_count = branch_count

    for index, value in enumerate(planned.values, start=1):
        if baseline_issue or stopped:
            reason = stopped or (
                baseline_issue
                if baseline_issue in (CandidateReason.CANCELLED, CandidateReason.TIMEOUT)
                else CandidateReason.BASELINE_UNAVAILABLE
            )
            candidates.append(
                RecommendationCandidate(value=value, status="skipped", feasibility=Feasibility.UNKNOWN, reason=reason)
            )
            continue

        patch = _patch(goal, value)
        try:
            prepared = _prepare_patch(snapshot, actor, patch)
        except ValueError:
            # Reject modified snapshots globally. Invalid candidate parameters are local to this branch.
            verify_snapshot_integrity(snapshot)
            candidates.append(
                RecommendationCandidate(
                    value=value,
                    status="skipped",
                    feasibility=Feasibility.UNKNOWN,
                    reason=CandidateReason.INVALID_CANDIDATE,
                )
            )
            continue
        if not is_site:
            original, revised = prepared.original_booking, prepared.revised_booking
            assert original is not None and revised is not None
            if (
                revised.request.soc_target < original.request.soc_target
                and not goal.allow_lower_target
                or revised.request.deadline > original.request.deadline
                and not goal.allow_later_deadline
            ):
                candidates.append(
                    RecommendationCandidate(
                        value=value,
                        status="skipped",
                        feasibility=Feasibility.INFEASIBLE,
                        reason=CandidateReason.SACRIFICE_NOT_ALLOWED,
                    )
                )
                continue
        observer = _DeadlineObservation(snapshot, prepared, goal)
        evidence = None
        previous_count = branch_count
        branch, reason = await execute(observer, f"candidate-{index}")
        if branch is None:
            if reason in (CandidateReason.TIMEOUT, CandidateReason.CANCELLED):
                stopped = reason
            status = "failed" if branch_count > previous_count else "skipped"
            feasibility = Feasibility.UNKNOWN
        else:
            evidence = _evidence(snapshot, goal, branch, observer)
            reason = _unsafe_reason(snapshot, branch)
            feasibility, reason = (
                (Feasibility.UNKNOWN, reason) if reason else _assess(goal, baseline_rows, branch, evidence)
            )
            status = "completed"
        candidates.append(
            RecommendationCandidate(
                value=value,
                status=status,
                feasibility=feasibility,
                reason=reason,
                hypothetical_infrastructure=prepared.hypothetical_infrastructure,
                evidence=evidence,
            )
        )

    verify_snapshot_integrity(snapshot)
    options = _rank(candidates, goal, baseline, envelope.as_of)
    if unsupported:
        search_status = SearchStatus.UNSUPPORTED
    elif baseline_issue or any(candidate.feasibility == Feasibility.UNKNOWN for candidate in candidates):
        search_status = SearchStatus.PARTIAL
    else:
        search_status = SearchStatus.FOUND if options else SearchStatus.NO_FEASIBLE

    assumptions = (
        *snapshot.event_manifest.assumptions,
        "Recommendations are simulated and advisory. Ranking applies only to the finite tested set.",
        "SLA uses original commitments unless explicitly labeled revised.",
    )
    if is_site:
        assumptions += (
            "The SLA threshold applies to the full known booking cohort. Unknown outcomes prevent verification.",
            "A site patch caps later regimes. Announced grid and cabinet limits and existing equipment caps still apply.",
            "Above-installed candidates are conditional on hypothetical infrastructure.",
        )
    else:
        assumptions += (
            "Other bookings' original on-time outcomes are protected. Unknown preservation prevents verification.",
            "Target attainment and connector release are separate. Already-satisfied targets need no further charging.",
        )
    return RecommendationResult(
        goal=goal,
        search_status=search_status,
        unsupported_reason="independent_supply" if unsupported else None,
        baseline_issue=baseline_issue,
        snapshot_id=envelope.snapshot_id,
        snapshot_sha256=envelope.snapshot_digest,
        known_at=envelope.as_of,
        horizon_end=snapshot.event_manifest.horizon_end,
        event_manifest_sha256=snapshot.event_manifest.manifest_sha256,
        experiment_fingerprint=envelope.experiment_fingerprint,
        policy_id=envelope.policy_id,
        policy_version=envelope.policy_version,
        candidate_set=planned,
        baseline=baseline,
        candidates=tuple(candidates),
        options=options,
        ranking=_RANKING[goal.goal],
        assumptions=assumptions,
        baseline_execution_count=baseline_count,
        branch_execution_count=branch_count,
        elapsed_ms=round((perf_counter() - started) * 1000, 3),
    )
