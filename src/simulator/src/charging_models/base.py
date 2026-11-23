"""Compatibility re-export (ADR-019 Phase 1): the DC charging model contract moved to `src.models.charging_physics`."""

from src.models.charging_physics import DCChargingModel, VehicleBatteryState, energy_to_target

__all__ = ["DCChargingModel", "VehicleBatteryState", "energy_to_target"]
