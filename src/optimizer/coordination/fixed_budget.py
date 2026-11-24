"""Fixed output budgets bounded by scenario limits."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from src.models.physical_constraints import ConstraintViolationError, valid_kw
from src.models.scheduling.coordination import ZoneBudgets
from src.models.scheduling.observations import SchedulingObservation


@dataclass(frozen=True)
class FixedBudgetCoordinator:
    output_kw: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if self.output_kw is not None:
            object.__setattr__(self, "output_kw", MappingProxyType(dict(self.output_kw)))

    def __call__(self, observation: SchedulingObservation, demand_kw: Mapping[str, float]) -> ZoneBudgets:
        requested = observation.scenario.default_zone_budget_kw if self.output_kw is None else self.output_kw
        if not observation.scenario.coordinated_limits and type(self) is FixedBudgetCoordinator:
            return ZoneBudgets(observation.minute, observation.interval_minutes, requested)

        limits = observation.limits()
        if requested.keys() != limits.zone_output_kw.keys() or any(
            not valid_kw(kw, limits.zone_output_kw[zone]) for zone, kw in requested.items()
        ):
            raise ConstraintViolationError("Invalid fixed zone budget before curtailment")
        clipped = {zone: min(kw, limits.zone_capacity_kw(zone)) for zone, kw in requested.items()}
        # Derate the original shares together when the shared source shrinks.
        total = sum(requested.values())
        fraction = min(1.0, limits.site_output_kw / total) if limits.shared_supply and total else 1.0
        assigned = {zone: min(clipped[zone], fraction * kw) for zone, kw in requested.items()}
        reasons = {
            zone: ["fixed_share", *(["source_limited"] if assigned[zone] < kw else [])]
            for zone, kw in requested.items()
        }
        return ZoneBudgets(
            observation.minute,
            observation.interval_minutes,
            assigned,
            {
                "requested_output_kw": dict(requested),
                "reason_codes": reasons,
                "shared_derating_factor": fraction,
            },
        )


class FixedShareCoordinator(FixedBudgetCoordinator):
    """Explicit interval-aware fixed share, including when no extension fields are configured."""

    uses_online_interval = True
