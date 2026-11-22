"""Validator topology hybrid của StationConfig (ADR-010) và provenance của VehicleSpec (ADR-012)."""

import pytest
from pydantic import ValidationError

from src.models.charging import VehicleSpec
from src.models.station import ChargerZone, StationConfig, SupplyMode

GUARD = {"max_state_age_seconds": 60, "flap_window_minutes": 10, "flap_max_toggles": 3}
OPTIMIZER = {"unmet_penalty_factor": 100, "early_charge_factor": 0.001, "smoothing_factor": 0.001}


def _config(**overrides) -> dict:
    base = {
        "station_id": "T",
        "name": "test",
        "power_limit_kw": 106.0,
        "step_minutes": 1,
        "horizon_hours": 24,
        "default_charging_efficiency": 0.98,
        "guard": GUARD,
        "optimizer": OPTIMIZER,
        "zone_budgets_kw": {"AC": 22.0, "DC": 78.0},
        "power_conversion_efficiency": 0.95,
        "cabinets": [
            {"cabinet_id": "AC-01", "zone": "AC", "output_limit_kw": 11.0},
            {"cabinet_id": "DC-01", "zone": "DC", "output_limit_kw": 120.0},
        ],
        "connectors": [
            {"connector_id": "AC-01-1", "cabinet_id": "AC-01", "zone": "AC", "max_power_kw": 11.0},
            {"connector_id": "DC-01-1", "cabinet_id": "DC-01", "zone": "DC", "max_power_kw": 60.0},
        ],
    }
    base.update(overrides)
    return base


def test_valid_hybrid_config_and_grid_defaults_to_power_limit():
    cfg = StationConfig.model_validate(_config())
    assert cfg.grid_input_limit_kw == 106.0  # None ⇒ bằng power_limit_kw
    assert cfg.supply_mode == SupplyMode.SHARED
    assert cfg.zone_budgets_kw == {ChargerZone.AC: 22.0, ChargerZone.DC: 78.0}


def test_legacy_ac_only_config_still_loads_with_defaults():
    """Client / config cũ không khai tủ, vùng, η vẫn nạp được (chỉ thêm field, có default)."""
    cfg = StationConfig.model_validate(
        _config(
            power_limit_kw=35.0,
            zone_budgets_kw=None,
            power_conversion_efficiency=1.0,
            cabinets=[],
            connectors=[{"connector_id": "A01", "max_power_kw": 7.0}],
        )
    )
    assert cfg.connectors[0].zone == ChargerZone.AC and cfg.connectors[0].cabinet_id is None
    assert cfg.grid_input_limit_kw == 35.0 and cfg.dc_unplug_delay_minutes == 5


def test_connector_with_unknown_cabinet_is_rejected():
    connectors = [{"connector_id": "AC-09-1", "cabinet_id": "AC-09", "zone": "AC", "max_power_kw": 11.0}]
    with pytest.raises(ValidationError, match="không có trong cabinets"):
        StationConfig.model_validate(_config(connectors=connectors))


def test_connector_zone_must_match_cabinet_zone():
    connectors = [{"connector_id": "DC-01-1", "cabinet_id": "DC-01", "zone": "AC", "max_power_kw": 60.0}]
    with pytest.raises(ValidationError, match="khác zone"):
        StationConfig.model_validate(_config(connectors=connectors))


def test_duplicate_cabinet_id_is_rejected():
    cabinets = [
        {"cabinet_id": "DC-01", "zone": "DC", "output_limit_kw": 120.0},
        {"cabinet_id": "DC-01", "zone": "DC", "output_limit_kw": 60.0},
    ]
    with pytest.raises(ValidationError, match="cabinet_id bị trùng"):
        StationConfig.model_validate(_config(cabinets=cabinets, connectors=[_config()["connectors"][1]]))


def test_zone_budgets_over_grid_rejected_when_shared():
    # 22 + 80 = 102 kW đầu ra / 0,95 ≈ 107,37 kW > 106 kW lưới.
    with pytest.raises(ValidationError, match="vượt grid_input_limit_kw"):
        StationConfig.model_validate(_config(zone_budgets_kw={"AC": 22.0, "DC": 80.0}))


def test_zone_budgets_over_grid_allowed_when_independent():
    """independent: mỗi vùng có nguồn riêng, không cộng ngân sách vào một lưới chung."""
    cfg = StationConfig.model_validate(_config(zone_budgets_kw={"AC": 22.0, "DC": 80.0}, supply_mode="independent"))
    assert cfg.supply_mode == SupplyMode.INDEPENDENT


def test_grid_alias_mismatch_is_rejected():
    with pytest.raises(ValidationError, match="alias"):
        StationConfig.model_validate(_config(grid_input_limit_kw=150.0))


@pytest.mark.parametrize("eta", [0.0, 1.01])
def test_conversion_efficiency_bounds(eta):
    with pytest.raises(ValidationError):
        StationConfig.model_validate(_config(power_conversion_efficiency=eta))


def test_vehicle_provenance_rejects_unknown_status_and_field():
    base = {"vehicle_model": "X", "display_name": "x", "usable_capacity_kwh": 10, "max_ac_power_kw": 7, "source": "t"}
    with pytest.raises(ValidationError):
        VehicleSpec.model_validate(
            {**base, "provenance": {"usable_capacity_kwh": {"source": "t", "status": "measured"}}}
        )
    with pytest.raises(ValidationError, match="không phải field"):
        VehicleSpec.model_validate({**base, "provenance": {"battery_kwh": {"source": "t", "status": "assumed"}}})
    ok = VehicleSpec.model_validate({**base, "provenance": {"max_dc_kw": {"source": "t", "status": "assumed"}}})
    assert ok.provenance["max_dc_kw"].status == "assumed" and ok.max_dc_kw is None
