"""Per-vehicle DC profiles on the simulator's battery-only charging contract."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType

from ..scenario import Scenario, Vehicle
from .base import VehicleBatteryState
from .dc_charging_models import DCProfile, charge_dc_step, resolve_dc_profile
from .synthetic_dc import SyntheticTaperV1

PROFILE_VERSION = "0.1.0"
INTEGRATION_SECONDS = 10.0
GENERIC_CURVE = "https://doi.org/10.1016/j.treng.2025.100350"
VF8_SHAPE = "https://evkx.net/models/vinfast/vf8/vf8_plus/chargingcurve/"
OEM_SOURCES = {
    "VF3": "https://vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3",
    "VF8_NEW_2026": "https://vinfastauto.com/vn_vi/dat-coc-xe-vf8-the-all-new-2026",
    "VF9_123": "https://stg-cms-v2.vinfastauto.com/vn_vi/car-pdp-v2/vf9",
}
CURVE_SOURCES = {
    "VF3": "ChargePilot synthetic SOC knots using the OEM charge-time claim as a reference",
    "VF8_NEW_2026": f"Cross-generation shape proxy normalized from the older VF8 Plus table: {VF8_SHAPE}",
    "VF9_123": f"Simolin et al. 2025 Eq. 13, heterogeneous fit adapted for simulation: {GENERIC_CURVE}",
    "UNKNOWN": f"Simolin et al. 2025 Eq. 13, heterogeneous fit adapted for simulation: {GENERIC_CURVE}",
}


@dataclass(frozen=True)
class VehicleProfilesDCModel:
    profiles: Mapping[str, DCProfile]
    fallback: SyntheticTaperV1 = SyntheticTaperV1()

    def __post_init__(self) -> None:
        object.__setattr__(self, "profiles", MappingProxyType(dict(self.profiles)))

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> "VehicleProfilesDCModel":
        profiles = {}
        for vehicle in scenario.vehicles:
            if vehicle.zone != "DC" or vehicle.vehicle_model is None:
                continue
            try:
                profile = resolve_dc_profile(
                    vehicle.vehicle_model,
                    unknown_battery_kwh=vehicle.battery_kwh,
                    # Zero is a valid disabled vehicle limit, not a reference power.
                    unknown_reference_max_kw=vehicle.max_kw or 60.0,
                )
            except ValueError as exc:
                raise ValueError(f"{vehicle.id}: {exc}") from exc
            if vehicle.battery_kwh != profile.usable_battery_kwh:
                raise ValueError(
                    f"{vehicle.id}: battery_kwh={vehicle.battery_kwh:g} does not match "
                    f"{profile.model} usable capacity {profile.usable_battery_kwh:g} kWh"
                )
            profiles[vehicle.id] = profile
        return cls(profiles)

    def _profile(self, state: VehicleBatteryState) -> DCProfile | None:
        profile = self.profiles.get(state.vehicle_id)
        if profile is not None and state.battery_kwh != profile.usable_battery_kwh:
            raise ValueError(f"{state.vehicle_id}: battery state capacity does not match selected DC profile")
        return profile

    def acceptance_kw(self, state: VehicleBatteryState) -> float:
        profile = self._profile(state)
        if profile is None:
            return self.fallback.acceptance_kw(state)
        return min(state.max_output_kw, profile.acceptance_kw(state.soc))

    def stored_kwh(
        self, state: VehicleBatteryState, setpoint_kw: float, interval_minutes: int, efficiency: float
    ) -> float:
        if isinstance(setpoint_kw, bool) or not isfinite(setpoint_kw) or setpoint_kw < 0:
            raise ValueError("DC setpoint must be finite and nonnegative")
        profile = self._profile(state)
        if profile is None:
            return self.fallback.stored_kwh(state, setpoint_kw, interval_minutes, efficiency)
        output_kw = min(setpoint_kw, state.max_output_kw)
        # The Guard already reserved this setpoint for this car. The adapter
        # needs only stored kWh; the engine accounts for conversion at the grid.
        step = charge_dc_step(
            profile,
            soc=state.soc,
            target_soc=state.target_kwh / state.battery_kwh,
            requested_kw=output_kw,
            minutes=interval_minutes,
            port_limit_kw=output_kw,
            cabinet_available_kw=output_kw,
            battery_efficiency=efficiency,
            charger_conversion_efficiency=1.0,
            integration_seconds=INTEGRATION_SECONDS,
        )
        return step.battery_added_kwh

    def metadata_for(self, vehicle: Vehicle) -> dict:
        profile = self.profiles.get(vehicle.id)
        key = (
            "synthetic_taper_v1"
            if profile is None
            else "UNKNOWN"
            if profile.confidence == "low_unknown_ev"
            else profile.model
        )
        return {
            "vehicle_model": vehicle.vehicle_model,
            "model_key": key,
            "curve_model_version": "1" if profile is None else PROFILE_VERSION,
            "curve_kind": "synthetic_taper" if profile is None else profile.curve_kind,
            "curve_source": "ChargePilot synthetic SOC taper" if profile is None else CURVE_SOURCES[key],
            "provenance": "ChargePilot baseline fallback" if profile is None else profile.provenance,
            "confidence": "synthetic_assumption" if profile is None else profile.confidence,
            "battery_capacity_source": OEM_SOURCES.get(key, "scenario vehicle.battery_kwh"),
            "battery_kwh": vehicle.battery_kwh,
            "reference_max_dc_kw": vehicle.max_kw if profile is None else profile.reference_max_dc_kw,
            "scenario_max_dc_kw": vehicle.max_kw,
            "oem_cap_verified": profile is not None and profile.reference_max_is_oem_spec,
            "vehicle_curve_measured": False,
        }
