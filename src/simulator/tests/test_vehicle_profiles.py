"""Acceptance, safety and export tests for opt-in DC vehicle profiles."""

import json
from dataclasses import replace
from math import fsum
from pathlib import Path

import pytest

from src.models.charging_physics import VehicleBatteryState
from src.models.physical_constraints import TOL, ConstraintViolationError
from src.models.simulation_core import Scenario
from src.simulator.core.algorithms import resolve_algorithms
from src.simulator.core.charging_models.dc_charging_models import resolve_dc_profile
from src.simulator.core.charging_models.synthetic_dc import SyntheticTaperV1
from src.simulator.hybrid import HybridSimulator
from src.simulator.run import main

FIXTURE = Path(__file__).resolve().parents[1] / "scenario/vinfast_dc_2port_120kw.json"


@pytest.fixture
def config():
    return json.loads(FIXTURE.read_bytes())


def build(config):
    scenario = Scenario.parse(config)
    algorithms, metadata = resolve_algorithms(config["algorithms"], scenario, "test")
    return scenario, algorithms, metadata["dc_charging_model"]


def battery(vehicle, soc):
    return VehicleBatteryState(
        vehicle.id, vehicle.max_kw, vehicle.battery_kwh, vehicle.battery_kwh * soc, vehicle.battery_kwh * vehicle.target
    )


@pytest.mark.parametrize(
    "model,capacity,max_kw",
    [("VF 3", 18.64, 24), ("VF8_NEW_2026", 60.13, 100), ("VF8", 60.13, 100), ("VF 9 123", 123, 60)],
)
def test_known_profile_aliases(model, capacity, max_kw):
    profile = resolve_dc_profile(model)
    assert profile.usable_battery_kwh == capacity
    assert profile.reference_max_dc_kw == max_kw


@pytest.mark.parametrize("index", [4, 6, 7], ids=["VF8", "VF3", "VF9"])
def test_known_capacity_mismatch_rejected(config, index):
    config["vehicles"][index]["battery_kwh"] += 1
    with pytest.raises(ValueError, match="does not match .* usable capacity"):
        build(config)


def test_unknown_requires_usable_capacity_and_uses_declared_power(config):
    with pytest.raises(ValueError, match="provide unknown_battery_kwh"):
        resolve_dc_profile("Other model")
    unknown = config["vehicles"][-1]
    unknown.update(vehicle_model="Other model", max_dc_kw=45)
    scenario, algorithms, metadata = build(config)
    assert metadata["vehicle_profiles"]["DC-E"]["model_key"] == "UNKNOWN"
    assert metadata["vehicle_profiles"]["DC-E"]["battery_capacity_source"] == "scenario vehicle.battery_kwh"
    assert metadata["vehicle_profiles"]["DC-E"]["confidence"] == "low_unknown_ev"
    assert metadata["vehicle_profiles"]["DC-E"]["vehicle_model"] == "Other model"
    assert algorithms.dc_charging_model.acceptance_kw(battery(scenario.vehicles[-1], 0)) == pytest.approx(45 * 0.87)
    del unknown["battery_kwh"]
    with pytest.raises(ValueError, match="DC-E battery_kwh"):
        build(config)


def test_vf2_does_not_resolve_to_vf3(config):
    config["vehicles"][6]["vehicle_model"] = "VF 2"
    with pytest.raises(ValueError, match="DC-C: VF2"):
        build(config)


def test_profiles_are_opt_in_and_unlabelled_ev_uses_synthetic(config):
    del config["vehicles"][-1]["vehicle_model"]
    scenario, algorithms, metadata = build(config)
    state = battery(scenario.vehicles[-1], 0.72)
    assert metadata["vehicle_profiles"]["DC-E"]["model_key"] == "synthetic_taper_v1"
    assert algorithms.dc_charging_model.acceptance_kw(state) == SyntheticTaperV1().acceptance_kw(state)
    assert algorithms.dc_charging_model.stored_kwh(state, 12, 1, 0.98) == SyntheticTaperV1().stored_kwh(
        state, 12, 1, 0.98
    )
    default, _ = resolve_algorithms({}, scenario, "test")
    assert isinstance(default.dc_charging_model, SyntheticTaperV1)


@pytest.mark.parametrize("soc", [-0.1, 1.01, float("nan"), float("inf")])
def test_profile_soc_validation(config, soc):
    scenario, algorithms, _ = build(config)
    with pytest.raises(ValueError, match="soc"):
        algorithms.dc_charging_model.acceptance_kw(battery(scenario.vehicles[4], soc))


@pytest.mark.parametrize("power", [float("nan"), float("inf"), -1, True])
def test_invalid_setpoint_rejected(config, power):
    scenario, algorithms, _ = build(config)
    with pytest.raises(ValueError, match="finite and nonnegative"):
        algorithms.dc_charging_model.stored_kwh(battery(scenario.vehicles[4], 0.4), power, 1, 0.98)


def test_wrapper_caps_vehicle_and_target_and_integrates_taper(config):
    scenario, algorithms, _ = build(config)
    model = algorithms.dc_charging_model
    vf3 = scenario.vehicles[6]
    state = battery(vf3, 0.05)
    assert model.acceptance_kw(state) == 24
    assert 0 < model.stored_kwh(state, 60, 1, 0.98) <= 24 / 60 * 0.98
    almost_done = replace(state, target_kwh=state.current_kwh + 0.001)
    assert model.stored_kwh(almost_done, 20, 1, 0.98) == pytest.approx(0.001)
    high_soc = battery(replace(scenario.vehicles[4], target=1), 0.80)
    setpoint = model.acceptance_kw(high_soc)
    assert 0 < model.stored_kwh(high_soc, setpoint, 1, 0.98) < setpoint / 60 * 0.98
    with pytest.raises(ValueError, match="battery state capacity"):
        model.acceptance_kw(replace(state, battery_kwh=20))


def test_wrapper_applies_battery_efficiency_to_a_flat_interval_once(config):
    scenario, algorithms, _ = build(config)
    state = battery(scenario.vehicles[4], 0.35)
    assert algorithms.dc_charging_model.stored_kwh(state, 60, 1, 0.8) == pytest.approx(0.8)


def test_guard_rejects_port_and_cabinet_overload(config):
    scenario, algorithms, _ = build(config)
    sim = HybridSimulator(scenario, algorithms=algorithms, policy=lambda _: {"DC-A": 61})
    with pytest.raises(ConstraintViolationError, match="invalid power"):
        sim.step()
    assert sim.rejected_allocation_count == 1
    assert sim.adapter.soc("DC-A") == 0.2

    config["charger_cabinets"][2]["cabinet_output_limit_kw"] = 100
    scenario, algorithms, _ = build(config)
    sim = HybridSimulator(scenario, algorithms=algorithms, policy=lambda _: {"DC-A": 60, "DC-B": 60})
    with pytest.raises(ConstraintViolationError, match="Cabinet limit exceeded"):
        sim.step()


def test_config_site_limit_accounts_for_both_zone_budgets(config):
    config["grid_input_limit_kw"] = 149
    with pytest.raises(ValueError, match="grid input"):
        Scenario.parse(config)


def test_mixed_fleet_run_preserves_occupancy_caps_and_energy(config):
    scenario, algorithms, _ = build(config)
    sim = HybridSimulator(scenario, algorithms=algorithms)
    result = sim.run()
    assert result["completed_on_time"] == 8
    assert result["missed_deadline_sessions"] == 1
    assert result["constraint_violation_count"] == 0
    assert result["frames"][0]["queues"]["DC"] == ["DC-C", "DC-D", "DC-E"]
    assert result["power_trace"][0]["dc_output_kw"] == pytest.approx(120)
    assert result["power_trace"][0]["grid_input_kw"] == pytest.approx(142 / 0.95)
    assert any(
        row["vehicles"]["DC-C"]["actual_output_kw"] > 0 and row["vehicles"]["DC-D"]["actual_output_kw"] > 0
        for row in result["power_trace"]
    )
    assert any(row["vehicles"]["DC-E"]["actual_output_kw"] > 0 for row in result["power_trace"])

    for start, end, row in zip(result["frames"][:-1], result["frames"][1:], result["power_trace"], strict=True):
        dt_hours = row["duration_minutes"] / 60
        connected = [vid for vid in start["ports"].values() if vid is not None]
        assert len(connected) == len(set(connected))
        assert not set(connected).intersection(start["queues"]["DC"])
        assert row["dc_output_kw"] <= 120 + TOL
        assert row["grid_input_kw"] <= scenario.grid_kw + TOL
        assert row["grid_input_kw"] * scenario.conversion == pytest.approx(
            row["ac_output_kw"] + row["dc_output_kw"], abs=TOL
        )
        for v in scenario.vehicles:
            vid = v.id
            actual = row["vehicles"][vid]["actual_output_kw"]
            assert 0 <= actual <= row["vehicles"][vid]["requested_output_kw"] + TOL
            assert actual <= v.max_kw + TOL
            if v.zone == "DC":
                assert actual <= 60 + TOL
            if vid not in connected:
                assert actual == 0
            a, b = start["vehicles"][vid]["soc"], end["vehicles"][vid]["soc"]
            assert 0 <= a <= b <= v.target + TOL
            assert actual * dt_hours * scenario.efficiency == pytest.approx((b - a) * v.battery_kwh, abs=TOL)

    grid_kwh = fsum(row["grid_input_kw"] * row["duration_minutes"] / 60 for row in result["power_trace"])
    battery_kwh = fsum(
        (row["soc"] - v.initial_soc) * v.battery_kwh
        for row, v in zip(result["vehicles"], scenario.vehicles, strict=True)
    )
    assert grid_kwh * scenario.conversion * scenario.efficiency == pytest.approx(battery_kwh, abs=TOL)
    assert result["total_grid_energy_kwh"] == round(grid_kwh, 3)
    assert result["total_battery_energy_kwh"] == round(battery_kwh, 3)
    assert all(station.n_evs_connected == 0 for station in sim.adapter.stations.values())


def test_profile_metadata_and_viewer_replay_export(tmp_path):
    assert main(["--scenario", str(FIXTURE), "--output-dir", str(tmp_path)]) == 0
    run = next(tmp_path.iterdir())
    report = json.loads((run / "report.json").read_bytes())
    replay = json.loads((run / "replay.json").read_bytes())
    model = report["metadata"]["algorithms"]["dc_charging_model"]
    assert model == replay["metadata"]["algorithms"]["dc_charging_model"]
    assert model["name"] == "vinfast_profiles_v0_1"
    assert model["version"] == "0.1.0"
    profiles = model["vehicle_profiles"]
    assert {p["model_key"] for p in profiles.values()} == {"VF3", "VF8_NEW_2026", "VF9_123", "UNKNOWN"}
    assert all(p["curve_source"] and p["confidence"] and p["battery_capacity_source"] for p in profiles.values())
    assert all(p["curve_model_version"] == "0.1.0" and not p["vehicle_curve_measured"] for p in profiles.values())
    assert profiles["DC-C"]["oem_cap_verified"] and profiles["DC-A"]["oem_cap_verified"]
    assert not profiles["DC-D"]["oem_cap_verified"] and not profiles["DC-E"]["oem_cap_verified"]
    html = (run / "viewer.html").read_text(encoding="utf-8")
    assert json.loads(html.split('id="embedded-replay">', 1)[1].split("</script>", 1)[0]) == replay
