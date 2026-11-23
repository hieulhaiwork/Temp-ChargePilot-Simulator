"""MVP-2 entry points, online boundaries, solver fallback and deterministic trace."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.models.simulation_core import Scenario, clock
from src.optimizer.zones import rolling_lp
from src.simulator.core.algorithms import resolve_algorithms
from src.simulator.hybrid import HybridSimulator
from src.simulator.run import main
from src.simulator.tests.golden_util import canonical_parts

ROOT = Path(__file__).resolve().parents[1]
START = 18 * 60


def dc(vid, arrival, departure, kwh, *, soc=0.3, max_kw=60):
    return {
        "id": vid,
        "zone": "DC",
        "arrival": clock(START + arrival),
        "departure": clock(START + departure),
        "initial_soc": soc,
        "target_soc": soc + kwh / 60,
        "battery_kwh": 60,
        "max_dc_kw": max_kw,
    }


def config(*vehicles, ports=2, timestep=1, duration=30, cabinet_kw=120, budget_kw=78):
    fixture = json.loads((ROOT / "scenario/mvp1.json").read_bytes())
    fixture.update(
        vehicles=list(vehicles),
        charger_cabinets=[
            dict(fixture["charger_cabinets"][-1], ports=ports, cabinet_output_limit_kw=cabinet_kw),
        ],
        step_minutes=timestep,
        duration_minutes=duration,
        dc_power_budget_kw=budget_kw,
    )
    return fixture


def simulator(conf, dispatch="llf", optimizer="rolling_lp", **selection):
    scenario = Scenario.parse(conf)
    algorithms, _ = resolve_algorithms(
        {"dispatch": {"DC": dispatch}, "optimizers": {"DC": optimizer}, **selection}, scenario, "test"
    )
    return HybridSimulator(scenario, algorithms=algorithms, record_decisions=True)


@pytest.mark.parametrize("dispatch,expected", [("fcfs", "A"), ("edf", "B"), ("llf", "C")])
def test_overloaded_dispatch_through_queue_with_simultaneous_arrivals(dispatch, expected):
    fixture = config(
        dc("D", 1, 8, 4.5),
        dc("C", 1, 8, 4.5),
        dc("A", 1, 10, 20),
        dc("B", 1, 7, 1),
        dc("incumbent", 0, 3, 30),
        ports=1,
        duration=12,
    )
    result = simulator(fixture, dispatch, "equal_share").run()
    decisions = result["decision_trace"]
    assert decisions[1]["ports_after_dispatch"]["DC-01/P1"] == "incumbent"
    assert decisions[1]["dispatch"]["DC"]["assigned"] == {}
    assert decisions[3]["dispatch"]["DC"]["waiting"] == ["A", "B", "C", "D"]
    assert decisions[3]["dispatch"]["DC"]["assigned"] == {"DC-01/P1": expected}
    laxity = decisions[3]["dc_waiting_laxity"]
    assert laxity["A"]["at_risk_under_optimistic_bound"]
    assert 0 < laxity["C"]["optimistic_laxity_minutes"] < laxity["B"]["optimistic_laxity_minutes"]
    assert laxity["C"] == laxity["D"]


def test_zero_rate_laxity_is_structured_and_infeasible_goes_last():
    sim = simulator(config(dc("A", 0, 10, 2, max_kw=0), dc("B", 0, 10, 2), ports=1))
    sim.step()
    decision = sim.decision_trace[0]
    assert decision["dispatch"]["DC"]["assigned"] == {"DC-01/P1": "B"}
    assert decision["dc_waiting_laxity"]["A"]["optimistic_laxity_minutes"] is None
    assert decision["dc_waiting_laxity"]["A"]["at_risk_under_optimistic_bound"]
    json.dumps(decision, allow_nan=False)


def test_lp_uses_validated_budget_before_solving_and_serves_tight_deadline():
    fixture = config(dc("A", 0, 1, 0.7), dc("B", 0, 10, 6), cabinet_kw=49, budget_kw=60)
    coordinator = {"name": "fixed_budget", "parameters": {"output_kw": {"AC": 22, "DC": 46}}}
    baseline = simulator(fixture, "llf", "equal_share", coordinator=coordinator).run()
    lp = simulator(fixture, coordinator=coordinator).run()
    assert baseline["vehicles"][0]["completed_at"] is None
    assert lp["vehicles"][0]["completed_at"] == START + 1
    first = lp["decision_trace"][0]
    assert first["budget_output_kw"]["DC"] == 46
    assert first["optimizers"]["DC"]["projected_shortfall_kwh"]["A"] == pytest.approx(0)
    assert sum(v["requested_output_kw"] for v in first["vehicles"].values()) == pytest.approx(46)
    assert lp["rejected_allocation_count"] == lp["applied_constraint_violation_count"] == 0


def test_lp_limits_shared_cabinet_and_remaining_target():
    sim = simulator(config(dc("A", 0, 20, 12), dc("B", 0, 20, 12), cabinet_kw=30))
    sim.step()
    decision = sim.decision_trace[0]
    assert sum(v["requested_output_kw"] for v in decision["vehicles"].values()) == pytest.approx(30)
    assert {"stage": "requested", "limit": "cabinet_output", "id": "DC-01", "kw": 30} in (
        decision["guard"]["binding_constraints"]
    )
    for v in decision["vehicles"].values():
        assert 0 <= v["actual_output_kw"] <= v["allowed_output_kw"] <= v["vehicle_max_output_kw"]
        assert v["predicted_battery_kwh"] == pytest.approx(v["battery_kwh"])


def test_future_arrival_roster_and_off_grid_timing_cannot_change_lp_first_plan():
    arrived = dc("arrived", 0, 20, 2)
    starts = []
    for arrival in (2, 8):
        sim = simulator(config(arrived, dc(f"unseen-{arrival}", arrival, 19, 12), timestep=10))
        original = sim.algorithms.optimizers["DC"]
        fixed_budget = sim.algorithms.coordinator

        def coordinator(observation, demand):
            assert set(observation.vehicles) == {"arrived"}
            assert observation.interval_minutes == 10
            assert demand["DC"] == pytest.approx(2 * 60 / 10 / 0.98)
            return fixed_budget(observation, demand)

        def inspect(observation, zone, budget):
            assert set(observation.vehicles) == {"arrived"}
            assert [v.id for v in observation.scenario.vehicles] == ["arrived"]
            assert observation.interval_minutes == 10
            assert observation.candidates["arrived"].allowed_kw == pytest.approx(2 * 60 / 10 / 0.98)
            return original(observation, zone, budget)

        inspect.uses_online_interval = True
        sim.algorithms = replace(
            sim.algorithms,
            optimizers={**sim.algorithms.optimizers, "DC": inspect},
            coordinator=coordinator,
        )
        sim.step()
        starts.append(sim.decision_trace[0])
    early, late = starts
    assert (early["interval_minutes"], late["interval_minutes"]) == (2, 8)
    assert early["dispatch"] == late["dispatch"]
    assert early["optimizers"] == late["optimizers"]
    assert early["vehicles"]["arrived"]["requested_output_kw"] == late["vehicles"]["arrived"]["requested_output_kw"]
    assert early["vehicles"]["arrived"]["battery_kwh"] < late["vehicles"]["arrived"]["battery_kwh"]
    assert all("unseen-" not in json.dumps(trace) for trace in starts)


@pytest.mark.parametrize(
    "case,reason,rejected",
    [
        ("exception", "solver_error", False),
        ("timeout", "time_or_iteration_limit", False),
        ("timeout_feasible", "time_or_iteration_limit", False),
        ("infeasible", "infeasible", False),
        ("invalid_status", "invalid_solver_status", True),
        ("invalid_shape", "invalid_primal", True),
        ("nonfinite", "invalid_primal", True),
        ("negative_power", "invalid_primal", True),
        ("over_budget", "invalid_primal", True),
    ],
)
def test_lp_falls_back_through_guard_on_nonoptimal_or_invalid_primal(monkeypatch, case, reason, rejected):
    fixture = config(dc("A", 0, 15, 10), dc("B", 0, 18, 15))
    expected = simulator(fixture, "llf", "equal_share")
    expected.step()
    linprog = rolling_lp.linprog

    def broken(*args, **kwargs):
        if case == "exception":
            raise RuntimeError("injected failure")
        if case == "timeout":
            return SimpleNamespace(status=1, x=None)
        if case == "infeasible":
            return SimpleNamespace(status=2, x=None)
        if case == "invalid_status":
            return SimpleNamespace(status=None, x=None)
        if case == "invalid_shape":
            return SimpleNamespace(status=0, x=[0])
        answer = linprog(*args, **kwargs)
        assert answer.status == 0
        if case == "timeout_feasible":
            answer.status = 1
        elif case == "nonfinite":
            answer.x[0] = float("nan")
        elif case == "negative_power":
            answer.x[0] = -1
        elif case == "over_budget":
            block_count = answer.x.size // 2 - 1  # Two vehicles with one shortfall variable each.
            answer.x[[0, block_count]] = 60
        return answer

    monkeypatch.setattr(rolling_lp, "linprog", broken)
    sim = simulator(fixture)
    sim.step()
    decision = sim.decision_trace[0]
    assert decision["optimizers"]["DC"]["fallback_reason"] == reason
    assert decision["optimizers"]["DC"]["solver_plan_rejected"] is rejected
    assert decision["guard"]["status"] == "pass"
    assert sim.trace == expected.trace
    assert sim.decision_latency_ms[0]["solver_ms"]["DC"] >= 0
    assert sim.constraint_metrics() == {"rejected_allocation_count": 0, "applied_constraint_violation_count": 0}


@pytest.mark.parametrize(
    "selection",
    [
        {"optimizers": {"DC": {"name": "rolling_lp", "parameters": {"time_limit_s": -0.1}}}},
        {"optimizers": {"DC": {"name": "rolling_lp", "parameters": {"horizon_minutes": -1}}}},
        {"optimizers": {"DC": {"name": "rolling_lp", "parameters": {"sla_weight": float("nan")}}}},
        {"optimizers": {"AC": "rolling_lp"}},
        {"dispatch": {"AC": "llf"}},
    ],
)
def test_registry_rejects_negative_or_invalid_inputs(selection):
    with pytest.raises(ValueError):
        resolve_algorithms(selection, Scenario.parse(config()), "test")


def test_tracing_preserves_legacy_outputs_and_runs_deterministically():
    fixture = config(dc("A", 0, 4, 3), dc("B", 0, 7, 5), dc("C", 2, 10, 4))
    sim = simulator(fixture)
    result = sim.run()
    other = simulator(fixture).run()
    again = HybridSimulator(sim.scenario, algorithms=sim.algorithms).run()
    assert canonical_parts(result) == canonical_parts(again)
    assert result["decision_trace"] == other["decision_trace"]
    assert [d["minute"] for d in result["decision_trace"]] == [d["minute"] for d in result["decision_latency_ms"]]
    assert "solver_ms" not in json.dumps(result["decision_trace"], allow_nan=False)


def test_cli_exports_separate_trace_and_profile_prediction_error(tmp_path):
    algorithms = tmp_path / "selection.json"
    algorithms.write_text(
        json.dumps(
            {
                "dispatch": {"DC": "llf"},
                "optimizers": {"DC": "rolling_lp"},
                "dc_charging_model": "vinfast_profiles_v0_1",
            }
        )
    )
    assert (
        main(
            [
                "--scenario",
                "vinfast_dc_2port_120kw",
                "--algorithms",
                str(algorithms),
                "--decision-trace",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    trace_file = next(tmp_path.glob("*/decision_trace.json"))
    trace = json.loads(trace_file.read_bytes())
    latency = json.loads(trace_file.with_name("decision_latency_ms.json").read_bytes())
    assert len(trace) == len(latency) == 360
    errors = [
        v["actual_minus_predicted_output_kw"]
        for row in trace
        for v in row["vehicles"].values()
        if "actual_minus_predicted_output_kw" in v
    ]
    assert min(errors) < -0.01 and max(errors) < 1e-7
    report = json.loads(trace_file.with_name("report.json").read_bytes())
    assert report["metadata"]["algorithms"]["optimizers"]["DC"]["forecast"]["future_arrivals"] == "unknown"
    assert report["applied_constraint_violation_count"] == 0
