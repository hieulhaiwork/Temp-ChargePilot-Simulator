"""Shared immutable observations for scheduling and coordination."""

from collections.abc import Mapping
from dataclasses import dataclass

from .charging_models.base import DCChargingModel
from .safety.limits import EffectiveLimits, effective_limits
from .scenario import Cabinet, Scenario, Vehicle


@dataclass(frozen=True)
class Candidate:
    cabinet: Cabinet
    allowed_kw: float


@dataclass(frozen=True)
class VehicleObservation:
    vehicle: Vehicle
    state: str
    soc: float
    connector: str | None
    charge_started: int | None
    completed_at: int | None

    @property
    def remaining_kwh(self) -> float:
        return max(0.0, self.vehicle.target - self.soc) * self.vehicle.battery_kwh


@dataclass(frozen=True)
class SchedulingObservation:
    """Immutable snapshot at the interval start, after dispatch."""

    scenario: Scenario
    minute: int
    interval_minutes: int
    vehicles: Mapping[str, VehicleObservation]
    queues: Mapping[str, tuple[str, ...]]
    ports: Mapping[str, str | None]
    candidates: Mapping[str, Candidate]
    dc_charging_model: DCChargingModel | None = None
    effective_limits: EffectiveLimits | None = None

    def limits(self) -> EffectiveLimits:
        return (
            self.effective_limits if self.effective_limits is not None else effective_limits(self.scenario, self.minute)
        )
