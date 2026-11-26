"""Typed service contracts for a bounded, advisory HOW-TO search."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from src.models.what_if import CommitmentOutcome, PatchDatetime, SlaMetrics

MAX_RECOMMENDATION_CANDIDATES = 8
Soc = Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)]
GridInput = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
CandidateValue = float | AwareDatetime


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _ResidentGoal(_Contract):
    booking_id: str = Field(strict=True, min_length=1, max_length=64)
    allow_lower_target: bool = Field(strict=True)
    allow_later_deadline: bool = Field(strict=True)
    allow_subject_original_sla_regression: bool = Field(strict=True)


class MaxSocByDeadline(_ResidentGoal):
    goal: Literal["max_soc_by_deadline"]
    deadline: PatchDatetime
    min_target_soc: Soc
    max_target_soc: Soc

    @model_validator(mode="after")
    def _ordered(self) -> "MaxSocByDeadline":
        if self.min_target_soc > self.max_target_soc:
            raise ValueError("SOC bounds must be ordered")
        return self


class EarliestCompletionForTarget(_ResidentGoal):
    goal: Literal["earliest_completion_for_target"]
    target_soc: Soc
    earliest_deadline: PatchDatetime
    latest_deadline: PatchDatetime

    @model_validator(mode="after")
    def _ordered(self) -> "EarliestCompletionForTarget":
        if self.earliest_deadline > self.latest_deadline:
            raise ValueError("Deadline bounds must be ordered")
        return self


class MinTestedSiteLimitForSla(_Contract):
    goal: Literal["min_tested_site_limit_for_sla"]
    min_grid_input_kw: GridInput
    max_grid_input_kw: GridInput
    min_original_on_time_rate: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)
    protect_on_time_ac_bookings: bool = Field(strict=True)
    hypothetical_infrastructure: bool = Field(strict=True)

    @model_validator(mode="after")
    def _ordered(self) -> "MinTestedSiteLimitForSla":
        if self.min_grid_input_kw > self.max_grid_input_kw:
            raise ValueError("Grid input bounds must be ordered")
        return self


RecommendationGoal = Annotated[
    MaxSocByDeadline | EarliestCompletionForTarget | MinTestedSiteLimitForSla, Field(discriminator="goal")
]
RECOMMENDATION_GOAL_ADAPTER: TypeAdapter[RecommendationGoal] = TypeAdapter(RecommendationGoal)


class CandidateSet(_Contract):
    version: Literal["chargepilot.how_to_candidates/1"] = "chargepilot.how_to_candidates/1"
    search_variable: Literal["target_soc_pct", "deadline", "grid_input_kw"]
    values: tuple[CandidateValue, ...] = Field(max_length=MAX_RECOMMENDATION_CANDIDATES)


class SearchStatus(StrEnum):
    FOUND = "found"
    NO_FEASIBLE = "no_feasible_in_tested_set"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


class Feasibility(StrEnum):
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"


class CandidateReason(StrEnum):
    TARGET_NOT_MET = "target_not_met_by_deadline"
    SITE_SLA_NOT_MET = "site_sla_not_met"
    ORIGINAL_SLA_REGRESSION = "original_sla_regression"
    SACRIFICE_NOT_ALLOWED = "sacrifice_not_allowed"
    UNKNOWN_SLA = "unknown_sla"
    EMPTY_COHORT = "empty_cohort"
    INCOMPLETE_OBSERVATION = "incomplete_observation"
    UNSAFE = "unsafe"
    SAFETY_HOLD = "safety_hold"
    PENDING_APPROVAL = "pending_approval"
    BLOCKED_COMMAND = "blocked_command"
    REJECTED_ALLOCATION = "rejected_allocation"
    INVALID_CANDIDATE = "invalid_candidate_for_snapshot"
    BASELINE_UNAVAILABLE = "baseline_unavailable"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    EXECUTION_FAILED = "execution_failed"


class BookingSla(_Contract):
    booking_id: str
    zone: Literal["AC", "DC"]
    original: CommitmentOutcome


class TargetAttainment(_Contract):
    target_soc: Soc
    target_reached_at: AwareDatetime | None
    already_satisfied_at_snapshot: bool


class RecommendationEvidence(_Contract):
    ref: str = Field(description="Identity of the authorized evidence projection. Append a JSON Pointer for a field.")
    input_sha256: str
    config_sha256: str
    final_physics_sha256: str
    observed_until: AwareDatetime
    branch_status: Literal["completed", "unsafe", "unresolved_safety"]
    hard_violations: int
    rejected_allocations: int
    safety_holds: int
    unresolved_safety_count: int
    blocked_commands: int
    pending_approvals: int
    pending_approval_commands: int
    elapsed_ms: float
    original_sla: SlaMetrics | None = None
    booking_sla: tuple[BookingSla, ...] = ()
    subject_original: CommitmentOutcome | None = None
    subject_revised: CommitmentOutcome | None = None
    subject_goal_target: TargetAttainment | None = None
    subject_soc_at_deadline_pct: Soc | None = None
    subject_soc_observed_at: AwareDatetime | None = None
    subject_release_at: AwareDatetime | None = None


class RecommendationCandidate(_Contract):
    value: CandidateValue
    status: Literal["completed", "skipped", "failed"]
    feasibility: Feasibility
    reason: CandidateReason | None = None
    hypothetical_infrastructure: bool = False
    evidence: RecommendationEvidence | None = None


class RecommendationResult(_Contract):
    applied: Literal[False] = False
    goal: RecommendationGoal
    search_status: SearchStatus
    unsupported_reason: Literal["independent_supply"] | None = None
    baseline_issue: CandidateReason | None = None
    snapshot_id: str
    snapshot_sha256: str
    known_at: AwareDatetime
    horizon_end: AwareDatetime
    event_manifest_sha256: str
    experiment_fingerprint: str
    policy_id: str
    policy_version: str
    candidate_set: CandidateSet
    baseline: RecommendationEvidence | None
    candidates: tuple[RecommendationCandidate, ...]
    options: tuple[RecommendationCandidate, ...] = Field(max_length=3)
    ranking: tuple[str, ...]
    assumptions: tuple[str, ...]
    baseline_execution_count: int
    branch_execution_count: int
    elapsed_ms: float
