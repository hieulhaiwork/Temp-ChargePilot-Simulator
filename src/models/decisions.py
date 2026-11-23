"""Decision contracts of the unified station kernel (ADR-019 Phase 3, docs/refactor/PHASE3_DESIGN.md §1).

Pure stdlib so the standalone simulator imports them. One decision flows through three immutable objects:

    ProposedDecision  Planning Core output, already checked by the Physical Guard (before apply)
    ApprovedDecision  after business steps (consent); a changed plan is re-checked by the SAME Physical Guard
    AppliedResult     Physical Core output for one advance, checked again by the Physical Guard (after apply)

A plan that fails the Guard before apply raises `ConstraintViolationError` and nothing is applied
(REJECTED_BEFORE_APPLY). A failure after integration is VIOLATION_AFTER_APPLY.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from src.models.physical_limits import EffectiveLimits
from src.models.scheduling.coordination import ZoneBudgets
from src.models.scheduling.dispatch import DispatchObservation
from src.models.scheduling.observations import Candidate, SchedulingObservation


def _freeze(instance, *names: str) -> None:
    for name in names:
        object.__setattr__(instance, name, MappingProxyType(dict(getattr(instance, name))))


@dataclass(frozen=True)
class TimeConfig:
    """Three independent time parameters (P1). `None` keeps the historical (golden) behaviour.

    - physics_step_minutes: length of one integration with constant power. None = one zero-order hold over the whole
      decision interval (compatibility mode of HybridSimulator; golden MVP-1/2/3).
    - decision_interval_minutes: upper bound of the decision interval. None = scenario.timestep.
    - planning_horizon_minutes: upper bound of the interval the optimizer sees. None = the decision interval.
    """

    physics_step_minutes: int | None = None
    decision_interval_minutes: int | None = None
    planning_horizon_minutes: int | None = None

    def __post_init__(self) -> None:
        for name in ("physics_step_minutes", "decision_interval_minutes", "planning_horizon_minutes"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f"{name} must be a positive integer or None")

    @property
    def compatibility(self) -> bool:
        return self.physics_step_minutes is None

    def as_dict(self) -> dict:
        return {
            "physics_step_minutes": self.physics_step_minutes,
            "decision_interval_minutes": self.decision_interval_minutes,
            "planning_horizon_minutes": self.planning_horizon_minutes,
        }


class ReasonCode:
    PLANNED = "PLANNED"
    OPTIMIZER_FALLBACK = "OPTIMIZER_FALLBACK"
    CONSENT_ADJUSTED = "CONSENT_ADJUSTED"
    REJECTED_BEFORE_APPLY = "REJECTED_BEFORE_APPLY"
    STALE_STATE = "STALE_STATE"
    VIOLATION_AFTER_APPLY = "VIOLATION_AFTER_APPLY"
    BUDGET_DEVIATION = "BUDGET_DEVIATION"
    CHARGE_COMPLETED = "CHARGE_COMPLETED"


@dataclass(frozen=True)
class ProposedDecision:
    policy_id: str
    policy_version: str
    state_version: int
    minute: int
    interval_end: int
    planning_interval_minutes: int
    assignments: Mapping[str, str]
    setpoints_kw: Mapping[str, float]
    budgets: ZoneBudgets
    effective_limits: EffectiveLimits
    candidates: Mapping[str, Candidate]
    observation: SchedulingObservation
    planning: SchedulingObservation
    dispatch: Mapping[str, DispatchObservation]
    demand: Mapping[str, float]
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    solver_ms: Mapping[str, float] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = (ReasonCode.PLANNED,)

    def __post_init__(self) -> None:
        _freeze(self, "assignments", "setpoints_kw", "candidates", "dispatch", "demand", "diagnostics", "solver_ms")
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))

    @property
    def interval_minutes(self) -> int:
        return self.interval_end - self.minute


@dataclass(frozen=True)
class ApprovedDecision:
    proposal: ProposedDecision
    setpoints_kw: Mapping[str, float]
    adjustments_kw: Mapping[str, float] = field(default_factory=dict)
    rechecked: bool = False
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _freeze(self, "setpoints_kw", "adjustments_kw")
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))


@dataclass(frozen=True)
class AppliedResult:
    minute: int
    end: int
    physics_step_minutes: int
    requested_kw: Mapping[str, float]
    allowed_kw: Mapping[str, float]
    actual_kw: Mapping[str, float]
    stored_kwh: Mapping[str, float]
    completed: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    budget_deviation_kw: Mapping[str, float] = field(default_factory=dict)
    state_version: int = 0

    def __post_init__(self) -> None:
        _freeze(self, "requested_kw", "allowed_kw", "actual_kw", "stored_kwh", "budget_deviation_kw")
        object.__setattr__(self, "completed", tuple(self.completed))
        object.__setattr__(self, "violations", tuple(self.violations))
