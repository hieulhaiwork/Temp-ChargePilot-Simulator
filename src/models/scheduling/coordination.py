"""Per-interval zone budgets and coordination contract."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from src.models.physical_constraints import ConstraintViolationError
from src.models.scheduling.observations import SchedulingObservation


@dataclass(frozen=True)
class ZoneBudgets:
    minute: int
    interval_minutes: int
    output_kw: Mapping[str, float]
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.output_kw, Mapping):
            raise ConstraintViolationError("Assigned zone budgets must map zone to output kW")
        object.__setattr__(self, "output_kw", MappingProxyType(dict(self.output_kw)))
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))


class GlobalCoordinator(Protocol):
    def __call__(self, observation: SchedulingObservation, demand_kw: Mapping[str, float]) -> ZoneBudgets:
        """Assign output kW for this interval. Demand is aggregate eligible acceptance."""
        ...
