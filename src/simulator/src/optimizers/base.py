"""Optimizer contracts for combined and per-zone power proposals."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from ..observations import SchedulingObservation


class SchedulingPolicy(Protocol):
    def __call__(self, observation: SchedulingObservation) -> Mapping[str, float]:
        """Propose charger-output kW by stable ID. Omitted IDs request zero."""
        ...


@dataclass(frozen=True)
class PowerProposal:
    """Setpoints and structured planning evidence. Solver timing is recorded separately."""

    output_kw: Mapping[str, float]
    diagnostics: dict
    solver_ms: float | None = None


class ZonePowerOptimizer(Protocol):
    def __call__(
        self, observation: SchedulingObservation, zone: str, budget_kw: float
    ) -> Mapping[str, float] | PowerProposal:
        """Propose output kW for connected, eligible vehicles in this zone."""
        ...
