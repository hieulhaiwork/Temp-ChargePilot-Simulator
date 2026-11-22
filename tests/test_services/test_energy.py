"""FR3 — kWh do CODE tính. AC1: kWh hiển thị cho cư dân phải khớp công thức này."""

import pytest

from src.models.charging import VehicleSpec
from src.services import catalog
from src.services.energy import estimate_energy


def _vehicle(efficiency: float | None = 0.9) -> VehicleSpec:
    return VehicleSpec(
        vehicle_model="T-60",
        display_name="test",
        usable_capacity_kwh=60,
        max_ac_power_kw=11,
        charging_efficiency=efficiency,
        source="test",
    )


def test_formula_battery_and_grid_energy():
    est = estimate_energy(_vehicle(), soc_now=32, soc_target=80)
    assert est.battery_energy_kwh == pytest.approx(60 * 0.48)  # 28.8 kWh vào pin
    assert est.grid_energy_kwh == pytest.approx(28.8 / 0.9)  # 32.0 kWh từ lưới


def test_station_default_efficiency_when_vehicle_has_none():
    default = catalog.load_station_config().default_charging_efficiency
    est = estimate_energy(_vehicle(efficiency=None), soc_now=20, soc_target=70)
    assert est.efficiency == default
    assert est.grid_energy_kwh == pytest.approx(30 / default)


@pytest.mark.parametrize(("soc_now", "soc_target"), [(80, 80), (90, 50), (-1, 50), (10, 101)])
def test_invalid_soc_range_fails_loudly(soc_now, soc_target):
    with pytest.raises(ValueError, match="soc_now"):
        estimate_energy(_vehicle(), soc_now=soc_now, soc_target=soc_target)
