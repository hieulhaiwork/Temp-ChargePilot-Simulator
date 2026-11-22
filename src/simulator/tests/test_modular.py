"""Swap control modules independently while exercising the real adapter and guard."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.simulator.run import main
from src.simulator.src.algorithms import default_algorithms, resolve_algorithms
from src.simulator.src.charging_models.base import VehicleBatteryState, energy_to_target
from src.simulator.src.charging_models.synthetic_dc import SyntheticTaperV1
from src.simulator.src.coordination.base import ZoneBudgets
from src.simulator.src.engine.hybrid import HybridSimulator
from src.simulator.src.safety.constraints import ConstraintViolationError
from src.simulator.src.scenario import Scenario

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return json.loads((ROOT / "scenario/mvp1.json").read_bytes())


def test_fifo_and_edf_differ_with_one_empty_port(config):
    config["charger_cabinets"] = [dict(config["charger_cabinets"][0])]
    config["duration_minutes"] = 3
    config["vehicles"] = [
        dict(config["vehicles"][0], departure="18:01"),
        dict(config["vehicles"][1], departure="18:03"),
        dict(config["vehicles"][2], departure="18:02"),
    ]
    scenario = Scenario.parse(config)
    baseline = HybridSimulator(scenario).run()
    plugins, _ = resolve_algorithms({"dispatch": {"AC": "edf"}}, scenario, "test")
    edf = HybridSimulator(scenario, algorithms=plugins).run()
    port = "AC-01/P1"
    assert [frame["ports"][port] for frame in baseline["frames"]] == ["AC-A", "AC-B", "AC-B", None]
    assert [frame["ports"][port] for frame in edf["frames"]] == ["AC-A", "AC-C", "AC-B", None]


def test_dispatch_can_choose_second_native_slot_and_leave_first_free(config):
    scenario = Scenario.parse(config)
    defaults = default_algorithms()

    def second_slot(observation):
        return {"DC-01/P2": observation.waiting[0]} if observation.minute == scenario.start else {}

    simulator = HybridSimulator(
        scenario, algorithms=replace(defaults, dispatch={**defaults.dispatch, "DC": second_slot})
    )
    simulator.step()
    station = simulator.adapter.stations["DC-01"]
    assert station.evs_connected == [None, simulator.adapter.models["DC-A"]]
    assert station.n_evs_connected == 1 and station.evs_connected[1].id == 1
    assert simulator.frames[0]["ports"]["DC-01/P2"] == "DC-A"
    assert simulator.frames[0]["queues"]["DC"] == ["DC-B", "DC-C", "DC-D", "DC-E"]


@pytest.mark.parametrize(
    "assignment",
    [
        {"DC-01/P1": "AC-A"},
        {"AC-01/P1": "DC-A"},
        {"AC-01/P9": "AC-A"},
        {"AC-01/P1": "AC-A", "AC-02/P1": "AC-A"},
        {"AC-01/P1": ["AC-A"]},
        [],
    ],
)
def test_guard_validates_both_dispatch_plans_before_plugging(config, assignment):
    defaults = default_algorithms()
    plugins = replace(defaults, dispatch={**defaults.dispatch, "AC": lambda _: assignment})
    simulator = HybridSimulator(Scenario.parse(config), algorithms=plugins)
    with pytest.raises(ConstraintViolationError, match="[Dd]ispatch"):
        simulator.step()
    assert not simulator.queue.occupied
    assert simulator.rejected_allocation_count == 1
    assert all(station.n_evs_connected == 0 for station in simulator.adapter.stations.values())


def test_dispatch_cannot_replace_connected_ev_in_full_station(config):
    scenario = Scenario.parse(config)
    defaults = default_algorithms()

    def invalid_second_step(observation):
        if observation.minute == scenario.start:
            return defaults.dispatch["AC"](observation)
        return {"AC-01/P1": "AC-C"}

    simulator = HybridSimulator(
        scenario, algorithms=replace(defaults, dispatch={**defaults.dispatch, "AC": invalid_second_step})
    )
    simulator.step()
    with pytest.raises(ConstraintViolationError, match="Invalid AC dispatch"):
        simulator.step()
    assert simulator.queue.occupied["AC-01/P1"] == "AC-A"


@pytest.mark.parametrize("zone,other", [("DC", "AC"), ("AC", "DC")])
def test_swapping_one_optimizer_keeps_other_zone_policy_and_trace(config, zone, other):
    scenario = Scenario.parse(config)
    defaults = default_algorithms()
    baseline = HybridSimulator(scenario).run()
    calls = []

    def zero(observation, assigned_zone, budget):
        assert assigned_zone == zone
        assert budget == scenario.zone_kw[zone]
        assert all(candidate.cabinet.zone == zone for candidate in observation.candidates.values())
        for values in (observation.candidates, observation.scenario.zone_kw, observation.ports):
            with pytest.raises(TypeError):
                values["AC"] = 99
        calls.append(observation.minute)
        return {}

    algorithms = replace(defaults, optimizers={**defaults.optimizers, zone: zero})
    assert algorithms.optimizers[other] is defaults.optimizers[other]
    result = HybridSimulator(scenario, algorithms=algorithms).run()
    assert len(calls) == len(result["power_trace"])
    assert all(r[f"{zone.lower()}_output_kw"] == 0 for r in result["power_trace"])
    assert [r[f"{other.lower()}_output_kw"] for r in baseline["power_trace"]] == [
        r[f"{other.lower()}_output_kw"] for r in result["power_trace"]
    ]


@pytest.mark.parametrize(
    "proposal,reason",
    [
        ({"AC-A": 0}, "cross-zone"),
        ({"DC-C": 0}, "ineligible"),
        ({"DC-A": float("inf")}, "invalid power"),
        ({"DC-A": -1}, "invalid power"),
        ({"DC-A": float("nan")}, "invalid power"),
        (None, "must map"),
    ],
)
def test_zone_optimizer_cannot_bypass_guard(config, proposal, reason):
    defaults = default_algorithms()
    algorithms = replace(defaults, optimizers={**defaults.optimizers, "DC": lambda *_: proposal})
    simulator = HybridSimulator(Scenario.parse(config), algorithms=algorithms)
    with pytest.raises(ConstraintViolationError, match=reason):
        simulator.step()
    assert simulator.rejected_allocation_count == 1
    assert all(ev.current_capacity == ev.battery_capacity_at_arrival for ev in simulator.adapter.models.values())


def test_custom_coordinator_fresh_budget_then_stale_budget(config):
    defaults = default_algorithms()
    seen = []

    def coordinator(observation, demand):
        with pytest.raises(TypeError):
            demand["DC"] = 100
        assert demand["DC"] > 10
        if not seen:
            seen.append(ZoneBudgets(observation.minute, observation.interval_minutes, {"AC": 22, "DC": 10}))
        return seen[0]

    simulator = HybridSimulator(Scenario.parse(config), algorithms=replace(defaults, coordinator=coordinator))
    simulator.step()
    assert simulator.trace[0]["dc_output_kw"] == pytest.approx(10)
    assert simulator.scenario.zone_kw["DC"] == 78
    with pytest.raises(ConstraintViolationError, match="stale"):
        simulator.step()


def test_optimizer_cannot_exceed_lower_assigned_budget(config):
    scenario = Scenario.parse(config)
    configured, _ = resolve_algorithms(
        {"coordinator": {"name": "fixed_budget", "parameters": {"output_kw": {"AC": 22, "DC": 5}}}},
        scenario,
        "test",
    )
    algorithms = replace(configured, optimizers={**configured.optimizers, "DC": lambda *_: {"DC-A": 12}})
    with pytest.raises(ConstraintViolationError, match="Zone limit exceeded: DC"):
        HybridSimulator(scenario, algorithms=algorithms).step()


@pytest.mark.parametrize("assigned", [{"AC": 22, "DC": 100}, {"AC": 22}, {"AC": 22, "DC": -1}])
def test_invalid_assigned_budgets_fail_before_optimizer(config, assigned):
    def coordinator(observation, _):
        return ZoneBudgets(observation.minute, observation.interval_minutes, assigned)

    def optimizer(*_):
        pytest.fail("Optimizer called before budget was validated")

    default = default_algorithms()
    algorithms = replace(default, coordinator=coordinator, optimizers={"AC": optimizer, "DC": optimizer})
    with pytest.raises(ConstraintViolationError, match="budget"):
        HybridSimulator(Scenario.parse(config), algorithms=algorithms).step()


def test_guard_independently_caps_site_even_if_zones_have_room(config):
    scenario = replace(Scenario.parse(config), grid_kw=100)
    with pytest.raises(ConstraintViolationError, match="site grid"):
        HybridSimulator(scenario).step()


class EstimatedCurve:
    """Test-only generic estimated profile. No OEM data or measured coefficients."""

    def acceptance_kw(self, state):
        if not 0 <= state.soc <= 1:
            raise ValueError("SOC out of range")
        return 40 if state.soc < 0.8 else 15

    def stored_kwh(self, state, setpoint_kw, interval_minutes, efficiency):
        return energy_to_target(state, min(setpoint_kw, self.acceptance_kw(state)), interval_minutes, efficiency)


def test_synthetic_model_nonnegative_monotone_and_explicit_soc_range():
    model = SyntheticTaperV1()
    values = [model.acceptance_kw(VehicleBatteryState("example", 60, 100, i, 100)) for i in range(101)]
    assert values == sorted(values, reverse=True)
    assert values[0] == 60 and 0 <= values[-1] <= 60
    with pytest.raises(ValueError, match="SOC"):
        model.acceptance_kw(VehicleBatteryState("example", 60, 100, 101, 100))


def test_dc_model_replacement_respects_vehicle_port_cabinet_and_target(config):
    config["duration_minutes"] = 2
    config["charger_cabinets"][2].update(port_limit_kw=35, cabinet_output_limit_kw=55)
    config["vehicles"] = [
        dict(config["vehicles"][4], max_dc_kw=24, target_soc=0.258),
        dict(config["vehicles"][5], target_soc=0.85),
    ]
    scenario = Scenario.parse(config)
    defaults = default_algorithms()
    simulator = HybridSimulator(scenario, algorithms=replace(defaults, dc_charging_model=EstimatedCurve()))
    result = simulator.run()
    first = result["power_trace"][0]
    assert first["dc_output_kw"] == pytest.approx(55)
    assert first["vehicles"]["DC-A"]["allowed_output_kw"] == 24  # Hypothetical vehicle config.
    assert first["vehicles"]["DC-B"]["allowed_output_kw"] == 35
    assert result["vehicles"][0]["soc"] == pytest.approx(0.258)
    assert result["vehicles"][0]["delivered_battery_kwh"] == pytest.approx((0.258 - 0.25) * 94)


@pytest.mark.parametrize("bad_acceptance", [float("nan"), -1])
def test_invalid_dc_acceptance_rejected_before_power_plan(config, bad_acceptance):
    class BrokenModel(EstimatedCurve):
        def acceptance_kw(self, state):
            return bad_acceptance

    algorithms = replace(default_algorithms(), dc_charging_model=BrokenModel())
    simulator = HybridSimulator(Scenario.parse(config), algorithms=algorithms)
    with pytest.raises(ConstraintViolationError, match="Invalid DC acceptance"):
        simulator.step()
    assert simulator.rejected_allocation_count == 1


def test_invalid_dc_response_is_applied_constraint_fault(config):
    class BrokenModel(EstimatedCurve):
        def stored_kwh(self, *args):
            return 10

    algorithms = replace(default_algorithms(), dc_charging_model=BrokenModel())
    simulator = HybridSimulator(Scenario.parse(config), algorithms=algorithms)
    with pytest.raises(ConstraintViolationError, match="Invalid battery response"):
        simulator.step()
    assert simulator.applied_constraint_violation_count == 1 and not simulator.frames
    with pytest.raises(RuntimeError, match="start a new run"):
        simulator.step()


@pytest.mark.parametrize(
    "field,name", [("coordinator", "dynamic"), ("physical_guard", "off"), ("dc_charging_model", "unknown")]
)
def test_cli_rejects_unknown_algorithms_without_successful_export(tmp_path, field, name, capsys):
    config = tmp_path / "algorithms.json"
    config.write_text(json.dumps({field: name}))
    output = tmp_path / "output"
    with pytest.raises(SystemExit) as exc:
        main(["--algorithms", str(config), "--output-dir", str(output)])
    assert exc.value.code == 2 and f"Unknown {field}" in capsys.readouterr().err
    assert not output.exists()


def test_cli_alternate_exports_actual_algorithm_metadata(tmp_path):
    selection = ROOT / "config/algorithms_edf_demo.json"
    assert main(["--algorithms", str(selection), "--output-dir", str(tmp_path)]) == 0
    output = next(tmp_path.iterdir())
    report = json.loads((output / "report.json").read_bytes())
    replay = json.loads((output / "replay.json").read_bytes())
    metadata = report["metadata"]["algorithms"]
    assert metadata == replay["metadata"]["algorithms"]
    assert metadata["dispatch"]["DC"]["name"] == "edf"
    assert metadata["optimizers"]["AC"]["name"] == "equal_share"
    assert metadata["optimizers"]["DC"]["name"] == "deadline_first"
    assert metadata["coordinator"]["parameters"]["output_kw"] == {"AC": 22, "DC": 60}
    assert metadata["dc_charging_model"]["observed_vs_estimated"] == "synthetic_assumption"
    assert metadata["dispatch"]["DC"]["config_source"] == str(selection)
    assert all(frame["dc_output_kw"] <= 60 + 1e-7 for frame in replay["frames"])
    payload = (
        (output / "viewer.html")
        .read_text(encoding="utf-8")
        .split('id="embedded-replay">', 1)[1]
        .split("</script>", 1)[0]
    )
    assert json.loads(payload) == replay


def test_scenario_embedded_config_sets_only_specified_zone(config, tmp_path):
    config["algorithms"] = {"optimizers": {"AC": "deadline_first"}}
    scenario = tmp_path / "scenario.json"
    scenario.write_text(json.dumps(config))
    output = tmp_path / "output"
    assert main(["--scenario", str(scenario), "--output-dir", str(output)]) == 0
    report = json.loads(next(output.glob("*/report.json")).read_bytes())
    algorithms = report["metadata"]["algorithms"]
    assert algorithms["optimizers"]["AC"]["config_source"] == f"{scenario}#algorithms"
    assert algorithms["optimizers"]["DC"]["config_source"] == "default"


def test_registry_can_configure_new_coordinator_and_dc_model(config, monkeypatch):
    from src.simulator.src.algorithms import COORDINATORS, DC_MODELS, Registration
    from src.simulator.src.coordination.fixed_budget import FixedBudgetCoordinator

    def configured_coordinator(params, scenario):
        budget = {**scenario.zone_kw, "DC": params["dc_kw"]}
        return FixedBudgetCoordinator(budget), {"parameters": budget}

    def configured_model(params, scenario):
        return EstimatedCurve(), {
            "parameters": {},
            "provenance": "test-only generic estimate",
            "observed_vs_estimated": "estimated",
            "validity": {"soc_fraction": [0, 1]},
        }

    monkeypatch.setitem(
        COORDINATORS,
        "test_coordinator",
        Registration(FixedBudgetCoordinator, "test-2", ("dc_kw",), configured_coordinator),
    )
    monkeypatch.setitem(
        DC_MODELS, "estimated_test_curve", Registration(EstimatedCurve, "test-3", configure=configured_model)
    )
    scenario = Scenario.parse(config)
    algorithms, metadata = resolve_algorithms(
        {
            "coordinator": {"name": "test_coordinator", "parameters": {"dc_kw": 65}},
            "dc_charging_model": "estimated_test_curve",
        },
        scenario,
        "test.json",
    )
    sim = HybridSimulator(scenario, algorithms=algorithms)
    sim.step()
    assert sim.trace[0]["dc_output_kw"] == pytest.approx(65)
    assert sim.trace[0]["vehicles"]["DC-A"]["allowed_output_kw"] == 40
    assert metadata["coordinator"]["version"] == "test-2"
    assert metadata["dc_charging_model"]["version"] == "test-3"
    assert metadata["dc_charging_model"]["provenance"] == "test-only generic estimate"
