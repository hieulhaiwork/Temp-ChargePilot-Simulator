"""MVP-3 TOU, interval limits, coordination and compatible execution."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.models.physical_constraints import TOL, ConstraintViolationError
from src.models.scheduling.coordination import ZoneBudgets
from src.models.simulation_core import Scenario, clock
from src.optimizer.zones import ac_lp
from src.simulator.benchmark_mvp3 import POLICIES, _selection, workload_mvp3
from src.simulator.core import kernel as hybrid
from src.simulator.core.algorithms import resolve_algorithms
from src.simulator.evaluation.extended import audit, sample_run
from src.simulator.hybrid import HybridSimulator

START = 18 * 60
ROOT = Path(__file__).resolve().parents[1]


def at(offset):
    return clock(START + offset)


def ac(vid, departure, kwh, *, soc=0.4, arrival=0):
    return {
        "id": vid,
        "zone": "AC",
        "arrival": at(arrival),
        "departure": at(departure),
        "battery_kwh": 60,
        "initial_soc": soc,
        "target_soc": soc + kwh / 60,
        "max_ac_kw": 11,
    }


def ac_config(*vehicles):
    config = json.loads((ROOT / "scenario/mvp1.json").read_bytes())
    config.update(
        step_minutes=5,
        duration_minutes=125,
        vehicles=list(vehicles),
        physical_zone_cap_kw={"AC": 22, "DC": 120},
        tou_tariff={
            "currency": "USD",
            "periods": [
                {"start": at(0), "price_per_kwh": 0.42},
                {"start": at(60), "price_per_kwh": 0.1},
            ],
        },
    )
    return config


def simulate(config, policy):
    scenario = Scenario.parse(config)
    algorithms, _ = resolve_algorithms(_selection(policy), scenario, "mvp3_test")
    return HybridSimulator(scenario, algorithms=algorithms, record_decisions=True)


def test_ac_lp_protects_tight_deadline_and_moves_flexible_energy_to_cheap_period():
    fixture = ac_config(ac("tight", 40, 6), ac("flexible", 120, 8))
    equal = simulate(fixture, "M2b")
    lp = simulate(fixture, "M3a")
    baseline, result = equal.run(), lp.run()
    assert baseline["completed_on_time"] == result["completed_on_time"] == 2
    assert all(
        d["vehicles"]["flexible"]["actual_output_kw"] == 0 for d in result["decision_trace"] if d["minute"] < START + 60
    )
    assert result["decision_trace"][0]["optimizers"]["AC"]["stage_status"] == {"sla": "optimal", "tou": "optimal"}
    assert result["decision_trace"][0]["optimizers"]["AC"]["primary_minimum_shortfall_kwh"] == pytest.approx(0)
    assert sample_run(lp.scenario, result).cost_by_zone["AC"] == pytest.approx((6 * 0.42 + 8 * 0.1) / 0.98 / 0.95)
    assert sample_run(lp.scenario, result).cost_by_zone["AC"] < sample_run(equal.scenario, baseline).cost_by_zone["AC"]


def test_ac_lp_high_soc_keeps_native_adapter_response_within_projected_pilot():
    fixture = ac_config(ac("high-soc", 120, 4.8, soc=0.87))
    sim = simulate(fixture, "M3a")
    result = sim.run()
    assert result["completed_on_time"] == 1
    assert result["applied_constraint_violation_count"] == 0
    assert max(audit(sim.scenario, result).values()) < 1e-6
    actual = [d["vehicles"]["high-soc"] for d in result["decision_trace"] if "high-soc" in d["vehicles"]]
    assert all(row["actual_output_kw"] <= row["requested_output_kw"] + TOL for row in actual)


@pytest.mark.parametrize("policy", POLICIES)
def test_source_drop_blackout_and_cabinet_derating_with_real_guard(policy):
    sim = simulate(workload_mvp3("site_curtailment", 11), policy)
    result = sim.run()
    assert result["applied_constraint_violation_count"] == result["rejected_allocation_count"] == 0
    for offset, grid_kw in ((17, 24), (43, 0), (49, 106)):
        trace = next(d for d in result["decision_trace"] if d["minute"] == START + offset)
        assert trace["physical_limits"]["grid_input_kw"] == grid_kw
        assert sum(trace["budget_output_kw"].values()) <= grid_kw * sim.scenario.conversion + TOL
    assert any(d["minute"] == START + 34 for d in result["decision_trace"])
    during_drop = next(d for d in result["decision_trace"] if d["minute"] == START + 66)
    assert during_drop["physical_limits"]["cabinet_output_kw"]["DC-01"] == 25
    assert max(audit(sim.scenario, result).values()) < 1e-6


def test_coordinator_and_guards_share_the_same_snapshot_before_and_after(monkeypatch):
    sim = simulate(workload_mvp3("site_curtailment", 11), "M3b")
    original = sim.algorithms.coordinator
    guard = hybrid.guard
    coordinator_limits = []
    guard_limits = []

    def with_limits(observation, demand):
        coordinator_limits.append(observation.effective_limits)
        return original(observation, demand)

    def record_guard(*args, **kwargs):
        guard_limits.append(kwargs["limits"])
        return guard(*args, **kwargs)

    sim.algorithms = replace(sim.algorithms, coordinator=with_limits)
    monkeypatch.setattr(hybrid, "guard", record_guard)
    sim.run()
    assert len(guard_limits) == 2 * len(coordinator_limits)
    assert all(limits is guard_limits[i * 2] is guard_limits[i * 2 + 1] for i, limits in enumerate(coordinator_limits))


def test_lends_unused_ac_share_only_on_shared_supply():
    config = workload_mvp3("dc_congestion", 11)
    config["vehicles"] = [v for v in config["vehicles"] if v["zone"] == "DC"]
    for policy, expected in (("M3a", 78), ("M3b", 100.7)):
        sim = simulate(config, policy)
        sim.step()
        row = sim.decision_trace[0]
        assert row["budget_output_kw"]["DC"] == pytest.approx(expected)
        if policy == "M3b":
            assert "shared_slack" in row["coordinator"]["reason_codes"]["DC"]
    config["independent_grid_input_limit_kw"] = {"AC": 22 / 0.95, "DC": 78 / 0.95}
    sim = simulate(config, "M3b")
    sim.step()
    row = sim.decision_trace[0]
    assert row["budget_output_kw"] == pytest.approx({"AC": 0, "DC": 78})
    assert row["physical_limits"]["supply_mode"] == "independent"
    assert "shared_slack" not in row["coordinator"]["reason_codes"]["DC"]


def test_guard_blocks_independent_supply_cross_lending_even_below_total_limit():
    sim = simulate(workload_mvp3("independent_supply", 11), "M3b")
    sim.algorithms = replace(
        sim.algorithms, coordinator=lambda obs, _: ZoneBudgets(obs.minute, obs.interval_minutes, {"AC": 0, "DC": 90})
    )
    with pytest.raises(ConstraintViolationError, match="independent grid input limit: DC"):
        sim.step()
    assert sim.rejected_allocation_count == 1
    assert sim.applied_constraint_violation_count == 0


def test_guard_rejects_custom_optimizer_exceeding_runtime_cabinet_derating():
    config = ac_config(ac("active", 60, 8))
    config["limit_events"] = [{"effective_at": at(0), "cabinet_output_limit_kw": {"AC-01": 3}}]
    sim = simulate(config, "M3a")
    sim.algorithms = replace(sim.algorithms, optimizers={**sim.algorithms.optimizers, "AC": lambda *_: {"active": 5}})
    with pytest.raises(ConstraintViolationError, match="Cabinet limit exceeded"):
        sim.step()
    assert sim.adapter.soc("active") == 0.4


@pytest.mark.parametrize("policy", ("B0", "M3b"))
def test_unannounced_events_and_vehicles_cannot_change_first_setpoint(policy):
    results = []
    for offset in (2, 4):
        config = ac_config(ac("visible", 40, 0.38), ac(f"unseen-{offset}", 80, 5, arrival=offset + 5))
        config["limit_events"] = [{"effective_at": at(offset), "grid_input_limit_kw": 0}]
        sim = simulate(config, policy)
        sim.step()
        decision = sim.decision_trace[0]
        assert decision["interval_minutes"] == offset
        assert decision["planning_interval_minutes"] == 5
        assert decision["published_limit_events"] == []
        assert set(decision["vehicles"]) == {"visible"}
        results.append(decision)
    assert (
        results[0]["vehicles"]["visible"]["requested_output_kw"]
        == results[1]["vehicles"]["visible"]["requested_output_kw"]
    )
    assert results[0]["optimizers"] == results[1]["optimizers"]
    assert results[0]["coordinator"] == results[1]["coordinator"]


def test_published_curtailment_changes_ac_plan_before_it_takes_effect():
    initial = ac_config(ac("flexible", 100, 5))
    curtailed = initial | {
        "limit_events": [
            {"effective_at": at(60), "announced_at": at(0), "grid_input_limit_kw": 0},
        ]
    }
    control = simulate(initial, "M3a")
    published = simulate(curtailed, "M3a")
    normal = control.run()
    result = published.run()
    assert result["completed_on_time"] == normal["completed_on_time"] == 1
    assert sum(d["vehicles"]["flexible"]["grid_kwh"] for d in result["decision_trace"] if d["minute"] < START + 60) > 0
    assert sum(d["vehicles"]["flexible"]["grid_kwh"] for d in normal["decision_trace"] if d["minute"] < START + 60) == 0


@pytest.mark.parametrize("stage", ("sla", "tou"))
def test_ac_lp_safe_fallback_and_logging_at_both_stages(monkeypatch, caplog, stage):
    original = ac_lp.linprog
    fixture = ac_config(ac("active", 40, 6))
    calls = 0

    def timeout(*args, **kwargs):
        nonlocal calls
        calls += 1
        if stage == "sla" or calls == 2:
            return SimpleNamespace(status=1, x=None)
        return original(*args, **kwargs)

    monkeypatch.setattr(ac_lp, "linprog", timeout)
    sim = simulate(fixture, "M3a")
    expected = simulate(fixture, "M2b")
    sim.step()
    expected.step()
    decision = sim.decision_trace[0]
    assert decision["optimizers"]["AC"]["fallback_stage"] == stage
    assert decision["optimizers"]["AC"]["fallback_reason"] == "time_limit"
    assert decision["guard"]["status"] == "pass"
    assert sim.trace == expected.trace
    assert "zone=AC power optimizer fallback=time_limit" in caplog.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"physical_zone_cap_kw": {"AC": 15, "DC": 120}},
        {"default_zone_budget_kw": {"AC": 20, "DC": 78}},
        {"independent_grid_input_limit_kw": {"AC": 5, "DC": 85}},
        {"limit_events": [{"effective_at": at(10), "announced_at": at(15), "grid_input_limit_kw": 20}]},
        {"limit_events": [{"effective_at": at(10), "cabinet_output_limit_kw": {"UNKNOWN": 0}}]},
        {
            "limit_events": [
                {"effective_at": at(10), "grid_input_limit_kw": 20},
                {"effective_at": at(10), "grid_input_limit_kw": 40},
            ]
        },
        {"tou_tariff": {"currency": "USD", "periods": [{"start": at(0), "price_per_kwh": -1}]}},
    ],
)
def test_invalid_physical_or_tariff_configuration_is_rejected(overrides):
    with pytest.raises(ValueError):
        Scenario.parse(ac_config() | overrides)


def test_trace_is_deterministic_and_latency_stays_separate():
    config = workload_mvp3("site_curtailment", 11)
    first, second = (simulate(config, "M3b").run() for _ in range(2))
    assert first["decision_trace"] == second["decision_trace"]
    assert json.loads(json.dumps(first["decision_trace"], allow_nan=False))[0]["schema_version"] == 2
    assert "solver_ms" not in json.dumps(first["decision_trace"])
    assert any(row["solver_ms"].keys() == {"AC", "DC"} for row in first["decision_latency_ms"])
