"""Acceptance checks on actual EV2Gym components, with the unchanged MVP1 fixture."""

import csv
import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.simulator.run import main
from src.simulator.src.engine.ev2gym_adapter import DCEV, PrecisionEV
from src.simulator.src.engine.hybrid import HybridSimulator
from src.simulator.src.safety.constraints import ConstraintViolationError
from src.simulator.src.scenario import Scenario, minute

FIXTURE = Path(__file__).resolve().parents[1] / "scenario/mvp1.json"


@pytest.fixture
def config():
    return json.loads(FIXTURE.read_bytes())


def simulate(config):
    return HybridSimulator(Scenario.parse(config)).run()


def test_9ev_queue_occupancy_order_and_unplug(config):
    reverse = deepcopy(config)
    reverse["vehicles"].reverse()
    result = simulate(config)
    assert simulate(reverse) == result
    assert simulate(config) == result
    assert sum(e["event"] == "ARRIVED" and e["time"] == "18:00" for e in result["events"]) == 9
    assert result["frames"][0]["ports"] == {
        "AC-01/P1": "AC-A",
        "AC-02/P1": "AC-B",
        "DC-01/P1": "DC-A",
        "DC-01/P2": "DC-B",
    }
    assert result["frames"][0]["queues"] == {"AC": ["AC-C", "AC-D"], "DC": ["DC-C", "DC-D", "DC-E"]}
    for frame in result["frames"]:
        queued = frame["queues"]["AC"] + frame["queues"]["DC"]
        connected = [vid for vid in frame["ports"].values() if vid is not None]
        assert len(set(queued + connected)) == len(queued + connected)
        assert set(queued) == {v["id"] for v in frame["vehicles"].values() if v["state"] == "QUEUED"}
        for port, vid in frame["ports"].items():
            if vid is not None:
                assert frame["vehicles"][vid]["connector"] == port
                assert frame["vehicles"][vid]["state"] in ("CHARGING", "FINISHED")
    for zone in ("AC", "DC"):
        plugs = [e["car_id"] for e in result["events"] if e["zone"] == zone and e["event"] == "PLUGGED_IN"]
        assert plugs == sorted(v["id"] for v in result["vehicles"] if v["zone"] == zone)
    rows = {v["id"]: v for v in result["vehicles"]}
    assert rows["AC-A"]["departed_at"] == rows["AC-A"]["departure"] == rows["AC-C"]["charge_started"]
    assert rows["AC-A"]["completed_at"] < rows["AC-A"]["departed_at"]
    assert rows["DC-B"]["departed_at"] == rows["DC-B"]["completed_at"] + 5 == rows["DC-C"]["charge_started"]
    assert result["completed_on_time"] == 9
    assert result["frames"][-1]["completed"] == 9
    assert all(v["state"] == "DEPARTED" for v in result["frames"][-1]["vehicles"].values())


def test_power_caps_soc_and_energy_accounting(config):
    config["charger_cabinets"][2]["cabinet_output_limit_kw"] = 70
    scenario = Scenario.parse(config)
    sim = HybridSimulator(scenario)
    assert type(sim.adapter.models["AC-A"]) is PrecisionEV
    assert isinstance(sim.adapter.models["DC-A"], DCEV)
    result = sim.run()
    battery = {v.id: v for v in scenario.vehicles}
    delivered = {v.id: 0.0 for v in scenario.vehicles}
    assert result["power_trace"][0]["dc_output_kw"] == pytest.approx(70)
    for frame, following, interval in zip(
        result["frames"][:-1], result["frames"][1:], result["power_trace"], strict=True
    ):
        hours = interval["duration_minutes"] / 60
        assert interval["grid_input_kw"] <= scenario.grid_kw + 1e-7
        for zone, budget in scenario.zone_kw.items():
            assert interval[f"{zone.lower()}_output_kw"] <= budget + 1e-7
        for vid, row in interval["vehicles"].items():
            v = battery[vid]
            start, end = frame["vehicles"][vid], following["vehicles"][vid]
            kw = row["actual_output_kw"]
            assert 0 <= kw <= row["requested_output_kw"] + 1e-7
            assert row["requested_output_kw"] <= row["allowed_output_kw"] + 1e-7
            assert kw <= v.max_kw + 1e-7
            assert 0 <= start["soc"] <= end["soc"] <= v.target + 1e-8
            if start["state"] != "CHARGING":
                assert kw == 0
            if v.zone == "DC" and start["soc"] > 0.60:
                assert kw <= v.max_kw * max(0.05, 1 - 2.25 * (start["soc"] - 0.60)) + 1e-7
            assert (end["soc"] - start["soc"]) * v.battery_kwh == pytest.approx(
                kw * hours * scenario.efficiency, abs=1e-7
            )
            delivered[vid] += kw * hours / scenario.conversion
        for cab in scenario.cabinets:
            readings = [
                interval["vehicles"][vid]["actual_output_kw"]
                for port, vid in frame["ports"].items()
                if vid is not None and port.startswith(cab.id + "/")
            ]
            assert all(power <= cab.port_kw + 1e-7 for power in readings)
            assert sum(readings) <= cab.output_kw + 1e-7
    for row in result["vehicles"]:
        spec = battery[row["id"]]
        assert row["delivered_grid_kwh"] == pytest.approx(delivered[row["id"]])
        assert row["delivered_battery_kwh"] == pytest.approx((row["soc"] - spec.initial_soc) * spec.battery_kwh)
    assert result["constraint_violation_count"] == 0


def test_left_queue_and_censored_wait_preserved(config):
    config["duration_minutes"] = 3
    config["vehicles"][2]["departure"] = "18:02"
    result = simulate(config)
    assert result["waited_then_left_without_charging"] == 1
    assert result["missed_deadline_sessions"] == 1
    assert result["pending_target_sessions"] == 8
    waits = {r["vehicle_id"]: r for r in result["queue_wait_for_all_arrivals"]}
    assert waits["AC-C"] == {"vehicle_id": "AC-C", "minutes": 2, "censored": False}
    assert waits["AC-D"] == {"vehicle_id": "AC-D", "minutes": 3, "censored": True}
    assert any(e["event"] == "LEFT_QUEUE" and e["car_id"] == "AC-C" for e in result["events"])
    assert next(v for v in result["vehicles"] if v["id"] == "AC-C")["delivered_battery_kwh"] == 0


def test_timestep_splits_on_arrival_departure_and_horizon(config):
    config["step_minutes"] = 5
    config["duration_minutes"] = 8
    config["vehicles"] = [dict(config["vehicles"][0], arrival="18:02", departure="18:07")]
    result = simulate(config)
    assert [row["time"] for row in result["frames"]] == ["18:00", "18:02", "18:07", "18:08"]
    assert [row["duration_minutes"] for row in result["power_trace"]] == [2, 5, 1]
    v = result["vehicles"][0]
    assert v["departed_at"] == minute("18:07") and v["delivered_battery_kwh"] == pytest.approx(11 * 5 / 60 * 0.98)


def test_ac_uses_native_taper_and_reports_response_below_setpoint(config):
    config["duration_minutes"] = 1
    config["vehicles"] = [dict(config["vehicles"][0], initial_soc=0.96, target_soc=1)]
    result = simulate(config)
    frame = result["frames"][0]["vehicles"]["AC-A"]
    assert 0 < frame["actual_output_kw"] < frame["requested_output_kw"] == 11
    assert result["vehicles"][0]["delivered_battery_kwh"] == pytest.approx(frame["actual_output_kw"] / 60 * 0.98)


@pytest.mark.parametrize("initial_soc,kw", [(0.60, 50), (0.80, 27.5)])
def test_dc_taper_applies_without_other_power_limits(config, initial_soc, kw):
    config["vehicles"] = [dict(config["vehicles"][4], initial_soc=initial_soc, target_soc=0.90, max_dc_kw=50)]
    config["duration_minutes"] = 1
    result = simulate(config)
    assert result["power_trace"][0]["dc_output_kw"] == pytest.approx(kw)


@pytest.mark.parametrize(
    "allocation",
    [
        {"AC-C": 1},
        {"AC-A": -1},
        {"DC-A": 61},
        {"AC-A": float("nan")},
        {"AC-A": True},
        {"AC-A": "1"},
        {"DC-A": 45, "DC-B": 45},
        [],
        None,
    ],
)
def test_guard_rejects_before_charging(config, allocation):
    sim = HybridSimulator(Scenario.parse(config), policy=lambda _: allocation)
    with pytest.raises(ConstraintViolationError):
        sim.step()
    assert all(model.current_capacity == model.battery_capacity_at_arrival for model in sim.adapter.models.values())
    assert sim.constraint_metrics() == {"rejected_allocation_count": 1, "applied_constraint_violation_count": 0}
    assert not sim.trace
    with pytest.raises(RuntimeError, match="start a new run"):
        sim.run()


def test_invalid_site_config_is_rejected(config):
    config["grid_input_limit_kw"] = 90
    with pytest.raises(ValueError, match="grid input"):
        Scenario.parse(config)


@pytest.mark.parametrize(
    "key,value",
    [
        ("charging_efficiency", 0),
        ("power_conversion_efficiency", float("nan")),
        ("dc_power_budget_kw", -1),
        ("duration_minutes", 0),
        ("dc_unplug_delay_minutes", -1),
        ("ac_unplug_policy", "immediate"),
    ],
)
def test_invalid_configuration_rejected(config, key, value):
    config[key] = value
    with pytest.raises(ValueError):
        Scenario.parse(config)


def test_duplicate_cabinet_rejected(config):
    config["charger_cabinets"].append(deepcopy(config["charger_cabinets"][0]))
    with pytest.raises(ValueError, match="Duplicate cabinet"):
        Scenario.parse(config)


def test_departures_at_horizon_release_ports_and_queue(config):
    config["duration_minutes"] = 2
    config["vehicles"] = [dict(v, departure="18:02") for v in config["vehicles"][:3]]
    simulator = HybridSimulator(Scenario.parse(config))
    result = simulator.run()
    final = result["frames"][-1]
    assert all(occupant is None for occupant in final["ports"].values())
    assert final["queues"] == {"AC": [], "DC": []}
    assert all(row["departed_at"] == minute("18:02") for row in result["vehicles"])
    assert result["missed_deadline_sessions"] == 3
    assert result["waited_then_left_without_charging"] == 1
    assert result["vehicles"][2]["delivered_battery_kwh"] == 0
    with pytest.raises(RuntimeError, match="horizon"):
        simulator.step()


def test_cabinet_bottleneck_recycles_unused_zone_budget(config):
    config["vehicles"] = config["vehicles"][:2]
    config["ac_power_budget_kw"] = 16
    config["charger_cabinets"][0]["cabinet_output_limit_kw"] = 5
    simulator = HybridSimulator(Scenario.parse(config))
    simulator.step()
    powers = simulator.trace[0]["vehicles"]
    assert powers["AC-A"]["actual_output_kw"] == pytest.approx(5)
    assert powers["AC-B"]["actual_output_kw"] == pytest.approx(11)


def test_guard_rejects_aggregate_cabinet_overload(config):
    config["charger_cabinets"][2]["cabinet_output_limit_kw"] = 30
    simulator = HybridSimulator(Scenario.parse(config), policy=lambda _: {"DC-A": 16, "DC-B": 16})
    with pytest.raises(ConstraintViolationError, match="Cabinet limit exceeded"):
        simulator.step()
    assert simulator.adapter.soc("DC-A") == config["vehicles"][4]["initial_soc"]
    assert simulator.rejected_allocation_count == 1


def test_zero_budget_reports_unmet_deadlines(config):
    config.update(ac_power_budget_kw=0, dc_power_budget_kw=0)
    result = simulate(config)
    assert result["completed_on_time"] == 0
    assert result["missed_deadline_sessions"] == 9
    assert result["total_grid_energy_kwh"] == 0
    assert result["remaining_demand_kwh"] == 223


@pytest.mark.parametrize("index", [0, 4], ids=["AC", "DC"])
def test_final_interval_caps_energy_to_target(config, index):
    vehicle = config["vehicles"][index]
    vehicle["target_soc"] = vehicle["initial_soc"] + 0.00001
    config.update(vehicles=[vehicle], duration_minutes=1)
    result = simulate(config)
    row = result["vehicles"][0]
    assert row["soc"] == pytest.approx(vehicle["target_soc"], abs=1e-12)
    assert row["delivered_battery_kwh"] == pytest.approx(0.00001 * vehicle["battery_kwh"])
    assert row["completed_at"] == minute("18:01")


def test_cli_exports_distinct_complete_replays(tmp_path):
    args = ["--scenario", "mvp1", "--output-dir", str(tmp_path)]
    assert main(args) == main(args) == 0
    runs = sorted(tmp_path.iterdir())
    assert len(runs) == 2
    a, b = runs
    report = json.loads((a / "report.json").read_bytes())
    replay = json.loads((a / "replay.json").read_bytes())
    replay_again = json.loads((b / "replay.json").read_bytes())
    assert replay["frames"] == replay_again["frames"]
    assert replay["events"] == replay_again["events"] == json.loads((a / "events.json").read_bytes())
    assert report["completed_on_time"] == 9
    assert report["metadata"]["native_dc"] is False
    assert report["metadata"]["ev2gym_version"] == "2.0.0"
    assert report["metadata"]["config"] == json.loads(FIXTURE.read_bytes())
    with (a / "power_trace.csv").open() as stream:
        assert len(list(csv.DictReader(stream))) == 360
    with (a / "vehicles.csv").open() as stream:
        assert len(list(csv.DictReader(stream))) == 9
    html = (a / "viewer.html").read_text(encoding="utf-8")
    payload = html.split('id="embedded-replay">', 1)[1].split("</script>", 1)[0]
    assert json.loads(payload) == replay
