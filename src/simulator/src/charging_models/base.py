"""Shared DC charging model contract and battery state."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VehicleBatteryState:
    vehicle_id: str
    max_output_kw: float
    battery_kwh: float
    current_kwh: float
    target_kwh: float

    @property
    def soc(self) -> float:
        return self.current_kwh / self.battery_kwh


class DCChargingModel(Protocol):
    def acceptance_kw(self, state: VehicleBatteryState) -> float:
        """Return finite, nonnegative charger-output acceptance for this SOC."""
        ...

    def stored_kwh(
        self, state: VehicleBatteryState, setpoint_kw: float, interval_minutes: int, efficiency: float
    ) -> float:
        """Return battery energy gained in the interval using this same model."""
        ...


def energy_to_target(state: VehicleBatteryState, output_kw: float, minutes: int, efficiency: float) -> float:
    return min(max(0.0, state.target_kwh - state.current_kwh), output_kw * minutes / 60 * efficiency)
