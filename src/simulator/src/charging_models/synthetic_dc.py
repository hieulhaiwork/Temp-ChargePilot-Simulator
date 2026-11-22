"""Synthetic MVP-1 SOC taper."""

from dataclasses import dataclass
from math import isfinite

from .base import VehicleBatteryState, energy_to_target


@dataclass(frozen=True)
class SyntheticTaperV1:
    taper_start_soc: float = 0.60
    slope_per_soc: float = 2.25
    minimum_fraction: float = 0.05

    def acceptance_kw(self, state: VehicleBatteryState) -> float:
        soc = state.soc
        if not isfinite(soc) or not 0 <= soc <= 1:
            raise ValueError("synthetic_taper_v1 requires fractional SOC in [0, 1]")
        if soc <= self.taper_start_soc:
            return state.max_output_kw
        return state.max_output_kw * max(self.minimum_fraction, 1 - self.slope_per_soc * (soc - self.taper_start_soc))

    def stored_kwh(
        self, state: VehicleBatteryState, setpoint_kw: float, interval_minutes: int, efficiency: float
    ) -> float:
        return energy_to_target(state, min(setpoint_kw, self.acceptance_kw(state)), interval_minutes, efficiency)
