"""Regression checks for the EV2Gym boundary and optimizer-facing contract."""

import json
from dataclasses import FrozenInstanceError, replace
from math import fsum
from pathlib import Path

import pytest

from src.simulator import run
from src.simulator.src.engine.ev2gym_adapter import Delivered, EV2GymAdapter
from src.simulator.src.engine.hybrid import HybridSimulator
from src.simulator.src.optimizers.equal_share import equal_share_policy
from src.simulator.src.safety.constraints import ConstraintViolationError
from src.simulator.src.scenario import Scenario, minute

FIXTURE = Path(__file__).resolve().parents[1] / "scenario/mvp1.json"


@pytest.fixture
def config():
    return json.loads(FIXTURE.read_bytes())


@pytest.mark.parametrize(
    "cabinet,port,first,second",
    [("AC-01", 0, "AC-A", "AC-C"), ("DC-01", 1, "DC-B", "DC-C")],
)
def test_adapter_local_id_and_port_reuse(config, cabinet, port, first, second):
    adapter = EV2GymAdapter(Scenario.parse(config))
    station = adapter.stations[cabinet]
    if cabinet == "DC-01":
        adapter.connect("DC-A", cabinet, 0)
    adapter.connect(first, cabinet, port)
    ev = adapter.models[first]
    assert (ev.id, ev.location) == (port, station.id)
    assert station.evs_connected[port] is ev
    assert station.n_evs_connected == port + 1
    with pytest.raises(RuntimeError, match="already connected"):
        adapter.connect(first, "AC-02", 0)
    with pytest.raises(RuntimeError, match="before disconnect"):
        adapter.disconnect(second, cabinet, port)
    adapter.disconnect(first, cabinet, port)
    assert ev.id is None and ev.location is None and station.n_evs_connected == port
    assert station.evs_connected[port] is None
    with pytest.raises(RuntimeError, match="not connected"):
        adapter.step(first, cabinet, 1, 1)
    adapter.connect(second, cabinet, port)
    assert adapter.models[first] is ev
    assert station.evs_connected[port] is adapter.models[second]
    assert adapter.models[second].id == port and station.n_evs_connected == port + 1


def test_adapter_detects_foreign_occupancy_drift(config):
    adapter = EV2GymAdapter(Scenario.parse(config))
    with pytest.raises(RuntimeError, match="Incompatible charger type"):
        adapter.connect("DC-A", "AC-01", 0)
    adapter.connect("AC-A", "AC-01", 0)
    adapter.stations["AC-01"].n_evs_connected = 0
    with pytest.raises(RuntimeError, match="occupancy diverged"):
        adapter.step("AC-A", "AC-01", 11, 1)


def test_dc_energy_state_only(config):
    adapter = EV2GymAdapter(Scenario.parse(config))
    ev = adapter.models["DC-A"]
    adapter.connect("DC-A", "DC-01", 0)
    before = ev.current_capacity
    response = adapter.step("DC-A", "DC-01", 30, 2)
    assert ev.prev_capacity == before
    assert ev.current_capacity - before == pytest.approx(0.98)
    assert ev.current_energy == ev.total_energy_exchanged == ev.abs_total_energy_exchanged == response.battery_kwh
    assert response.actual_output_kw == pytest.approx(30)
    assert ev.required_energy == pytest.approx(ev.battery_capacity - ev.current_capacity)
    adapter.step("DC-A", "DC-01", 0, 1)
    assert ev.current_energy == 0 and ev.total_energy_exchanged == response.battery_kwh
    with pytest.raises(NotImplementedError, match="degradation"):
        ev.get_battery_degradation()


@pytest.mark.parametrize("arrival", ["17:59", "18:01", "18:02"])
def test_arrival_must_be_in_half_open_horizon(config, arrival):
    config["duration_minutes"] = 1
    config["vehicles"] = [dict(config["vehicles"][0], arrival=arrival)]
    with pytest.raises(ValueError, match="within scenario horizon"):
        Scenario.parse(config)


@pytest.mark.parametrize("step", [0, -1, True, 1.0, 5])
def test_invalid_or_conflicting_timestep_alias(config, step):
    config["timestep_minutes"] = step
    with pytest.raises(ValueError, match="timestep_minutes"):
        Scenario.parse(config)


def test_observation_read_only_with_queue_and_forecast(config):
    config["vehicles"][-1]["arrival"] = "18:02"
    scenario = Scenario.parse(config)
    budgets = dict(scenario.zone_kw)
    scenario = replace(scenario, zone_kw=budgets)
    budgets["AC"] = 99
    config["ac_power_budget_kw"] = 99
    observations = []

    def policy(observation):
        observations.append(observation)
        return equal_share_policy(observation)

    simulator = HybridSimulator(scenario, policy=policy)
    simulator.step()
    simulator.step()
    first = observations[0]
    assert first.scenario.zone_kw["AC"] == 22
    assert first.minute == minute("18:00") and first.interval_minutes == 1
    assert first.queues["AC"] == ("AC-C", "AC-D")
    assert first.vehicles["AC-C"].vehicle.departure == minute("23:15")
    assert first.vehicles["DC-E"].state == "NOT_ARRIVED"
    assert first.vehicles["DC-E"].vehicle.arrival == minute("18:02")
    assert first.candidates["AC-A"].allowed_kw == 11
    assert "AC-C" not in first.candidates
    assert first.ports["AC-01/P1"] == "AC-A"
    assert first.vehicles["AC-A"].soc < observations[1].vehicles["AC-A"].soc
    for mapping in (first.queues, first.ports, first.candidates, first.vehicles, first.scenario.zone_kw):
        with pytest.raises(TypeError):
            mapping["AC"] = 60
    with pytest.raises(FrozenInstanceError):
        first.candidates["AC-A"].cabinet.port_kw = 100


def test_applied_violation_count_and_fail_closed(config):
    class BrokenResponse(EV2GymAdapter):
        def step(self, vehicle_id, cabinet, output_kw, minutes):
            delivery = super().step(vehicle_id, cabinet, output_kw, minutes)
            return Delivered(delivery.actual_output_kw + 1, delivery.battery_kwh)

    simulator = HybridSimulator(Scenario.parse(config), adapter_factory=BrokenResponse)
    with pytest.raises(ConstraintViolationError, match="Invalid battery response"):
        simulator.run()
    assert simulator.constraint_metrics() == {"rejected_allocation_count": 0, "applied_constraint_violation_count": 1}
    assert not simulator.trace and not simulator.frames
    with pytest.raises(RuntimeError, match="start a new run"):
        simulator.step()


def test_cli_guard_failure_prints_counters_and_skips_export(tmp_path, monkeypatch, capsys):
    def simulator_with_invalid_policy(scenario, **kwargs):
        return HybridSimulator(scenario, policy=lambda _: {"AC-C": 1}, **kwargs)

    monkeypatch.setattr(run, "HybridSimulator", simulator_with_invalid_policy)
    with pytest.raises(SystemExit) as exc:
        run.main(["--output-dir", str(tmp_path)])
    assert exc.value.code == 2
    failure = json.loads(capsys.readouterr().err)
    assert failure["status"] == "constraint_failure"
    assert failure["rejected_allocation_count"] == 1
    assert failure["applied_constraint_violation_count"] == 0
    assert not list(tmp_path.iterdir())


def test_split_steps_ac_dc_and_midnight(config):
    config.update(start_time="23:58", duration_minutes=7, timestep_minutes=3, step_minutes=3)
    config["vehicles"] = [
        dict(config["vehicles"][0], arrival="23:59", departure="24:02"),
        dict(config["vehicles"][4], arrival="24:00", departure="24:03"),
    ]
    scenario = Scenario.parse(config)
    simulator = HybridSimulator(scenario)
    result = simulator.run()
    assert [f["time"] for f in result["frames"]] == ["23:58", "23:59", "24:00", "24:02", "24:03", "24:05"]
    hours_ac, hours_dc = 3 / 60, 3 / 60
    assert result["vehicles"][0]["delivered_battery_kwh"] == pytest.approx(11 * hours_ac * scenario.efficiency)
    assert result["vehicles"][1]["delivered_battery_kwh"] == pytest.approx(60 * hours_dc * scenario.efficiency)
    assert simulator.adapter.models["AC-A"].time_of_departure == 4
    assert simulator.adapter.models["DC-A"].time_of_arrival == 2
    assert all(v["state"] == "DEPARTED" for v in result["vehicles"])


def test_zero_vehicles(config):
    config["vehicles"] = []
    result = HybridSimulator(Scenario.parse(config)).run()
    assert result["requests"] == 0 and result["satisfied_demand_rate"] is None
    assert result["total_grid_energy_kwh"] == 0 and not result["events"]
    assert result["rejected_allocation_count"] == result["applied_constraint_violation_count"] == 0


def test_energy_independently_reconciles_trace_and_soc(config):
    scenario = Scenario.parse(config)
    result = HybridSimulator(scenario).run()
    trace = result["power_trace"]
    grid_kwh = fsum(row["grid_input_kw"] * row["duration_minutes"] / 60 for row in trace)
    output_kwh = fsum((row["ac_output_kw"] + row["dc_output_kw"]) * row["duration_minutes"] / 60 for row in trace)
    battery_kwh_by_id = {v.id: v.battery_kwh for v in scenario.vehicles}
    soc_kwh = fsum((v["soc"] - v["initial_soc"]) * battery_kwh_by_id[v["id"]] for v in result["vehicles"])
    stored_kwh = fsum(v["delivered_battery_kwh"] for v in result["vehicles"])
    assert grid_kwh * scenario.conversion == pytest.approx(output_kwh, abs=1e-7)
    assert output_kwh * scenario.efficiency == pytest.approx(soc_kwh, abs=1e-7)
    assert stored_kwh == pytest.approx(soc_kwh, abs=1e-7)
    assert result["total_grid_energy_kwh"] == round(grid_kwh, 3)


def dc_earliest_deadline_first(observation):
    """Comparison policy ranks power requests from already connected DC EVs."""
    proposal = equal_share_policy(observation)
    remaining = observation.scenario.zone_kw["DC"]
    cabinet_left = {cab.id: cab.output_kw for cab in observation.scenario.cabinets}
    dc_candidates = sorted(
        (vid for vid, c in observation.candidates.items() if c.cabinet.zone == "DC"),
        key=lambda vid: (observation.vehicles[vid].vehicle.departure, vid),
    )
    for vid in dc_candidates:
        candidate = observation.candidates[vid]
        cid = candidate.cabinet.id
        kw = min(candidate.allowed_kw, remaining, cabinet_left[cid])
        proposal[vid] = kw
        remaining -= kw
        cabinet_left[cid] -= kw
    return proposal


@pytest.mark.parametrize("scarce", [False, True], ids=["mvp1", "scarce"])
def test_policy_comparison_same_fixture(config, scarce):
    if scarce:
        config.update(duration_minutes=2, grid_input_limit_kw=32, ac_power_budget_kw=0, dc_power_budget_kw=30)
        config["vehicles"] = [
            dict(config["vehicles"][4], battery_kwh=50, initial_soc=0.4, target_soc=0.41, departure="18:02"),
            dict(config["vehicles"][5], battery_kwh=50, initial_soc=0.4, target_soc=0.41, departure="18:02"),
        ]
    scenario = Scenario.parse(config)
    equal = HybridSimulator(scenario).run()
    earliest = HybridSimulator(scenario, policy=dc_earliest_deadline_first).run()
    assert equal["frames"][0]["ports"] == earliest["frames"][0]["ports"]
    for result in (equal, earliest):
        assert result["rejected_allocation_count"] == result["applied_constraint_violation_count"] == 0
        assert result["peak_grid_input_kw"] <= scenario.grid_kw
    if scarce:
        # The site supplies at most 0.98 kWh to the batteries, below the joint 1 kWh target.
        assert (equal["completed_on_time"], earliest["completed_on_time"]) == (0, 1)
        assert earliest["missed_deadline_sessions"] == 1
    else:
        assert equal["completed_on_time"] == 9
    for name, result in (("equal-share", equal), ("dc-earliest-deadline", earliest)):
        print(
            f"{name}: on-time={result['completed_on_time']}/{result['requests']}; "
            f"wait={result['mean_wait_minutes_started_only']}; "
            f"grid_kWh={result['total_grid_energy_kwh']}; peak_kW={result['peak_grid_input_kw']}"
        )
