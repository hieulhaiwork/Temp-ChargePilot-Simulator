"""Shared immutable observations for scheduling and coordination.

State layers (Final Review §4.3, MVP-3.5 readiness). Only the last one may reach dispatch / coordinator / optimizer:

    ground truth   physics state of the kernel (EV2Gym SOC, queue sessions, delivered energy) — physics, Physical
                   Guard after apply, KPI. Never handed to the planner directly.
    declared       what the resident declared (`Vehicle`: arrival, departure, battery, initial SOC, target).
    observation    `ObservationModel.observe(minute, truth)` — the plug-in point for noise / delay / missing / stale
                   telemetry. Default `PerfectObservation` is the identity (same mapping object back ⇒ old results).
    estimated      what the planner sees: `VehicleObservation.soc`; a non-perfect model returns
                   `EstimatedVehicleObservation` carrying `SocEstimate` (value, measurement minute, uncertainty).

Definitions above `SocEstimate` are preserved byte-for-byte (AST gate, ADR-019); the layer contract is additive.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from src.models.charging_physics import DCChargingModel
from src.models.physical_limits import EffectiveLimits, effective_limits
from src.models.simulation_core import Cabinet, Scenario, Vehicle


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


# ---- observation / estimated layers (additive, opt-in) -----------------------------------------


@dataclass(frozen=True)
class SocEstimate:
    """Estimated SOC handed to the planner, with where it came from.

    `measured_at` < observation minute ⇒ stale / delayed telemetry; a missing sample keeps the last value with a larger
    `uncertainty`. `source`: "telemetry" | "declared" | "model" (free text, recorded for traces).
    """

    value: float
    measured_at: int
    uncertainty: float = 0.0
    source: str = "telemetry"

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"estimated SOC must be in [0, 1], got {self.value}")
        if self.uncertainty < 0:
            raise ValueError("SOC uncertainty must be non-negative")


@dataclass(frozen=True)
class EstimatedVehicleObservation(VehicleObservation):
    """A `VehicleObservation` whose `soc` is an ESTIMATE (`estimate.value`), never the physics ground truth."""

    estimate: SocEstimate | None = None

    def __post_init__(self) -> None:
        if self.estimate is not None and self.estimate.value != self.soc:
            raise ValueError("EstimatedVehicleObservation.soc must equal estimate.value")


def estimated(row: VehicleObservation, estimate: SocEstimate) -> EstimatedVehicleObservation:
    """Same vehicle / state / connector as `row`, SOC replaced by the estimate (the only field a model may change)."""
    return EstimatedVehicleObservation(
        row.vehicle, row.state, estimate.value, row.connector, row.charge_started, row.completed_at, estimate
    )


@runtime_checkable
class ObservationModel(Protocol):
    """Telemetry / estimation layer between ground truth and the planner (plug-in of `StationKernel`).

    `observe` receives the ground-truth rows of the vehicles the planner is allowed to know about and returns the rows
    it will actually see, keyed exactly like `truth`. It may only change the SOC (use `estimated`); vehicle, state and
    connector are physical facts of the queue. It can be called several times for the same minute (once per zone
    dispatch and once for planning) and must answer the same each time. A model with state (RNG, delay buffers, filter
    memory) must also implement `fork()` returning an independent copy (`StationKernel.fork`, Final Review §4.4).
    """

    def observe(self, minute: int, truth: Mapping[str, VehicleObservation]) -> Mapping[str, VehicleObservation]: ...


class PerfectObservation:
    """Identity: the planner sees the ground truth (MVP-1/2/3 behaviour). Returns the very same mapping object."""

    __stateless__ = True

    def observe(self, minute: int, truth: Mapping[str, VehicleObservation]) -> Mapping[str, VehicleObservation]:
        return truth
