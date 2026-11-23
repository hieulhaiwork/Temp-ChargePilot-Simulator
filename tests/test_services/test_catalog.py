"""config/*.yaml — nạp được, hợp lệ, và KHỚP fixture nền `mvp1` của ADR-010 / danh mục xe ADR-012.

Đổi tham số mô phỏng là quyết định sản phẩm: sửa PRD trước, rồi sửa YAML + test này (thứ tự ADR-003).
Thay 21/11/2026 (T1.10): trước đây khoá 8 × 7 kW / 35 kW / bước 15 phút của PRD v0.2 §1.
"""

from datetime import time

import pytest
from pydantic import ValidationError

from src.models.station import ChargerZone, SupplyMode, Tariff, TariffPeriod
from src.services import catalog

# Ba kịch bản 8 × 7 kW của PRD v0.2, gắn nhãn legacy_ac_only (ADR-012): mã cổng A01–A08 không còn trong
# station.yaml hybrid. Giữ tới khi nhóm quyết bỏ; không dùng cho nghiệm thu.
LEGACY_AC_ONLY_SCENARIOS = {"peak_evening", "connector_failure", "power_drop"}


def test_station_config_matches_mvp1_fixture():
    cfg = catalog.load_station_config()
    assert [(c.connector_id, c.cabinet_id, c.zone, c.max_power_kw) for c in cfg.connectors] == [
        ("AC-01-1", "AC-01", ChargerZone.AC, 11.0),
        ("AC-02-1", "AC-02", ChargerZone.AC, 11.0),
        ("DC-01-1", "DC-01", ChargerZone.DC, 60.0),
        ("DC-01-2", "DC-01", ChargerZone.DC, 60.0),
    ]
    assert [(c.cabinet_id, c.zone, c.output_limit_kw) for c in cfg.cabinets] == [
        ("AC-01", ChargerZone.AC, 11.0),
        ("AC-02", ChargerZone.AC, 11.0),
        ("DC-01", ChargerZone.DC, 120.0),  # cap vật lý của tủ DC, nhỏ hơn 2 × 60
    ]
    assert cfg.grid_input_limit_kw == 106.0
    assert cfg.power_limit_kw == 106.0  # alias một vòng
    assert cfg.zone_budgets_kw == {ChargerZone.AC: 22.0, ChargerZone.DC: 78.0}
    assert cfg.physical_zone_cap_kw == {ChargerZone.AC: 22.0, ChargerZone.DC: 120.0}  # contract simulator §3.1
    assert cfg.power_conversion_efficiency == 0.95
    assert cfg.default_charging_efficiency == 0.98
    assert cfg.supply_mode == SupplyMode.SHARED
    assert cfg.dc_unplug_delay_minutes == 5
    assert (cfg.step_minutes, cfg.horizon_hours) == (1, 24)
    assert cfg.nameplate_power_kw == 142.0
    # 22 + 78 = 100 kW đầu ra ⇒ ≈ 105,263 kW phía lưới, không vượt 106 kW.
    assert sum(cfg.zone_budgets_kw.values()) / cfg.power_conversion_efficiency == pytest.approx(105.263, abs=1e-3)


def test_vehicle_catalog_loads_and_every_vehicle_has_source():
    vehicles = catalog.load_vehicle_catalog()
    assert vehicles, "Danh mục xe rỗng"
    assert all(v.source.strip() for v in vehicles.values())


def test_vinfast_profiles_match_simulator_values():
    """Giá trị chép từ simulator v1.2 (dc_charging_models.resolve_dc_profile) — ADR-012."""
    vehicles = catalog.load_vehicle_catalog()
    got = {
        m: (vehicles[m].usable_capacity_kwh, vehicles[m].max_dc_kw, vehicles[m].dc_curve, vehicles[m].max_ac_power_kw)
        for m in ("VF3", "VF8_NEW_2026", "VF9_123")
    }
    assert got == {
        "VF3": (18.64, 24.0, "vf3_synthetic_v0_1", 11.0),
        "VF8_NEW_2026": (60.13, 100.0, "vf8_shape_proxy_v0_1", 11.0),
        "VF9_123": (123.0, 60.0, "simolin_2025_generic", 11.0),
    }
    assert "UNKNOWN" not in vehicles  # dung lượng do người dùng khai, không nằm trong danh mục chọn


def test_vinfast_provenance_is_per_field_and_honest():
    vehicles = catalog.load_vehicle_catalog()
    status = {m: {k: p.status for k, p in vehicles[m].provenance.items()} for m in ("VF3", "VF8_NEW_2026", "VF9_123")}
    assert status == {
        "VF3": {
            "usable_capacity_kwh": "oem_claim",
            "max_dc_kw": "oem_claim",
            "dc_curve": "synthetic",
            "max_ac_power_kw": "assumed",
        },
        "VF8_NEW_2026": {
            "usable_capacity_kwh": "oem_claim",
            "max_dc_kw": "oem_claim",
            "dc_curve": "proxy",
            "max_ac_power_kw": "assumed",
        },
        "VF9_123": {
            "usable_capacity_kwh": "oem_claim",
            "max_dc_kw": "assumed",
            "dc_curve": "proxy",
            "max_ac_power_kw": "assumed",
        },
    }
    # Không curve nào là số đo OEM; không xe nào được đánh dấu verified.
    assert not any(v.verified for v in vehicles.values())
    assert all(p.status != "verified" for v in vehicles.values() for p in v.provenance.values())


def test_unknown_vehicle_raises_specific_error():
    with pytest.raises(catalog.UnknownVehicleError):
        catalog.get_vehicle("KHONG-CO-XE-NAY")


def test_tariff_covers_day_and_wraps_midnight():
    tariff = catalog.load_tariff()
    off_peak = tariff.price_at(time(23, 0))
    assert tariff.price_at(time(3, 59)) == off_peak  # 22:00 → 04:00 qua nửa đêm
    assert tariff.price_at(time(4, 0)) != off_peak
    assert tariff.price_at(time(18, 0)) > tariff.price_at(time(23, 0))  # cao điểm tối đắt hơn đêm


def test_tariff_with_gap_is_rejected():
    with pytest.raises(ValidationError, match="phủ 0 lần"):
        Tariff(source="test", periods=[TariffPeriod(name="day", start=time(6), end=time(22), price_per_kwh=1)])


def test_all_scenarios_load_with_unique_ids():
    scenarios = catalog.list_scenarios()
    ids = [s.scenario_id for s in scenarios]
    assert {"peak_evening", "connector_failure", "power_drop"} <= set(ids)
    assert len(ids) == len(set(ids))


def test_scenario_connectors_exist_in_station():
    """Kịch bản không legacy phải trỏ tới cổng có trong station.yaml."""
    known = {c.connector_id for c in catalog.load_station_config().connectors}
    for scenario in catalog.list_scenarios():
        if scenario.scenario_id in LEGACY_AC_ONLY_SCENARIOS:
            continue
        for incident in scenario.incidents:
            assert incident.connector_id in (None, *known), f"{scenario.scenario_id}: {incident.connector_id}"


def test_legacy_ac_only_scenarios_are_labelled_and_still_load():
    """Kịch bản legacy vẫn nạp được và mang nhãn trong file — không lặng lẽ trộn với topology hybrid."""
    loaded = {s.scenario_id for s in catalog.list_scenarios()}
    assert LEGACY_AC_ONLY_SCENARIOS <= loaded
    for scenario_id in LEGACY_AC_ONLY_SCENARIOS:
        text = (catalog.SCENARIO_DIR / f"{scenario_id}.yaml").read_text(encoding="utf-8")
        assert text.startswith("# legacy_ac_only"), scenario_id


def test_unknown_scenario_raises_specific_error():
    with pytest.raises(catalog.UnknownScenarioError):
        catalog.load_scenario("khong_co")
