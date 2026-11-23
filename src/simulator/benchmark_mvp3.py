"""Run paired MVP-3 AC/DC coordination benchmarks on HybridSimulator."""

import argparse
import hashlib
import json
import platform
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path
from random import Random
from tempfile import mkdtemp

from src.optimizer.registry import POLICIES  # một nguồn policy (ADR-019); B0/M2b/M3a/M3b đóng băng

from .benchmark import SEEDS, START, workload
from .run import ROOT, write_json
from .src.algorithms import resolve_algorithms
from .src.engine.hybrid import HybridSimulator
from .src.evaluation.extended import ENERGY_TOL_KWH, benchmark_metrics, sample_run
from .src.safety.constraints import TOL
from .src.scenario import Scenario, clock

FAMILIES = ("ac_flexibility_tou", "dc_congestion", "shared_source_scarcity", "site_curtailment", "independent_supply")


def _time(offset: int) -> str:
    return clock(START + offset)


def workload_mvp3(family: str, seed: int) -> dict:
    templates = {
        "ac_flexibility_tou": "no_congestion",
        "dc_congestion": "queue_pressure",
        "shared_source_scarcity": "deadline_scarcity",
        "site_curtailment": "queue_pressure",
        "independent_supply": "queue_pressure",
    }
    config = workload(templates[family], seed)
    rng = Random(seed)
    config.update(
        scenario_id=f"mvp3_{family}_{seed}",
        duration_minutes=180,
        timestep_minutes=5,
        physical_zone_cap_kw={"AC": 22, "DC": 120},
        tou_tariff={
            "currency": "USD",
            "periods": [
                {"start": _time(0), "price_per_kwh": 0.45},
                {"start": _time(60), "price_per_kwh": 0.12},
                {"start": _time(145), "price_per_kwh": 0.32},
            ],
        },
    )
    dc = [vehicle for vehicle in config["vehicles"] if vehicle["zone"] == "DC"]

    def ac(idx, arrival, stay, soc, target):
        return {
            "id": f"AC-{idx:02d}",
            "zone": "AC",
            "arrival": _time(arrival),
            "departure": _time(arrival + stay + rng.randint(-3, 3)),
            "battery_kwh": 60,
            "initial_soc": soc,
            "target_soc": target,
            "max_ac_kw": 11,
        }

    if family == "ac_flexibility_tou":
        config["vehicles"] = [
            *dc,
            ac(0, 0, 142, 0.42, 0.56),
            ac(1, 0, 108, 0.36, 0.67),
            ac(2, 11, 165, 0.71, 0.87),
        ]
    elif family == "dc_congestion":
        config["vehicles"] = [*dc, ac(0, 0, 27, 0.50, 0.54)]
    elif family == "shared_source_scarcity":
        config.update(grid_input_limit_kw=70, dc_power_budget_kw=44)
        config["vehicles"] = [*dc, ac(0, 0, 33, 0.55, 0.64), ac(1, 0, 42, 0.60, 0.71), ac(2, 4, 98, 0.46, 0.62)]
    elif family == "site_curtailment":
        config["limit_events"] = [
            {"effective_at": _time(17), "grid_input_limit_kw": 24},
            {"effective_at": _time(43), "announced_at": _time(34), "grid_input_limit_kw": 0},
            {"effective_at": _time(49), "announced_at": _time(34), "grid_input_limit_kw": 106},
            {"effective_at": _time(66), "cabinet_output_limit_kw": {"DC-01": 25}},
            {"effective_at": _time(83), "cabinet_output_limit_kw": {"DC-01": 120}},
        ]
    elif family == "independent_supply":
        config["independent_grid_input_limit_kw"] = {"AC": 22 / 0.95, "DC": 78 / 0.95}
        config["vehicles"] = [*dc, ac(0, 0, 27, 0.50, 0.54)]
    return config


def _selection(policy: str) -> dict:
    dispatch, ac, dc, coordinator = POLICIES[policy]
    return {"dispatch": {"DC": dispatch}, "optimizers": {"AC": ac, "DC": dc}, "coordinator": coordinator}


def _paired(cases: list[dict], policy: str, baseline: str) -> dict:
    pairs = {}
    for case in cases:
        after, before = (case["policies"][key] for key in (policy, baseline))
        pairs[case["scenario_id"]] = {
            "on_time": {
                zone: after["by_zone"][zone]["on_time"] - before["by_zone"][zone]["on_time"] for zone in ("AC", "DC")
            },
            "unserved": after["overall"]["unserved"] - before["overall"]["unserved"],
            "tou_cost": after["tou_cost"] - before["tou_cost"],
        }
    return pairs


def run_benchmark(output: Path) -> dict:
    cases, latency = [], []
    by_policy, by_family = defaultdict(list), defaultdict(lambda: defaultdict(list))
    metadata = {}
    for family in FAMILIES:
        for seed in SEEDS:
            config = workload_mvp3(family, seed)
            scenario = Scenario.parse(config)
            case = {
                "scenario_id": scenario.id,
                "family": family,
                "seed": seed,
                "scenario": config,
                "scenario_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
                "policies": {},
            }
            for policy in POLICIES:
                algorithms, details = resolve_algorithms(_selection(policy), scenario, "mvp3_benchmark")
                metadata.setdefault(
                    policy, {key: details[key] for key in ("dispatch", "optimizers", "dc_charging_model")}
                )
                result = HybridSimulator(scenario, algorithms=algorithms, record_decisions=True).run()
                sample = sample_run(scenario, result)
                by_policy[policy].append(sample)
                by_family[family][policy].append(sample)
                case["policies"][policy] = benchmark_metrics([sample])
                latency.append({"scenario_id": scenario.id, "policy": policy, "intervals": sample.latency})
                if family in {"site_curtailment", "shared_source_scarcity"} and seed == SEEDS[0]:
                    write_json(output / f"decision_trace_{family}_{policy}.json", result["decision_trace"])
            cases.append(case)

    controls = {}
    for name in ("mvp1", "vinfast_dc_2port_120kw"):
        config = json.loads((ROOT / f"scenario/{name}.json").read_bytes())
        scenario = Scenario.parse(config)
        by_control = {}
        for policy in ("B0", "M2b"):
            selection = config.get("algorithms", {}) | _selection(policy) | {"coordinator": "fixed_budget"}
            algorithms, _ = resolve_algorithms(selection, scenario, "mvp3_legacy_control")
            result = HybridSimulator(scenario, algorithms=algorithms, record_decisions=True).run()
            by_control[policy] = benchmark_metrics([sample_run(scenario, result)])
        controls[name] = by_control

    report = {
        "schema_version": 1,
        "seeds": SEEDS,
        "software": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            **{name: version(name) for name in ("ev2gym", "numpy", "scipy")},
        },
        "absolute_guard_tolerance": TOL,
        "absolute_energy_audit_tolerance_kwh": ENERGY_TOL_KWH,
        "policy_selection": {policy: _selection(policy) for policy in POLICIES},
        "algorithm_metadata": metadata,
        "cases": cases,
        "pooled_by_policy": {key: benchmark_metrics(value) for key, value in by_policy.items()},
        "pooled_by_family": {
            family: {key: benchmark_metrics(value) for key, value in policies.items()}
            for family, policies in by_family.items()
        },
        "paired_deltas": {
            f"{policy}_vs_{baseline}": _paired(cases, policy, baseline)
            for policy, baseline in (("M2b", "B0"), ("M3a", "M2b"), ("M3b", "M3a"), ("M3b", "B0"))
        },
        "golden_regression": {
            "suite": "src/simulator/tests/test_golden_regression.py",
            "references": ["v1_2_outputs.json", "mvp2_outputs.json"],
            "legacy_fixture_metrics": controls,
        },
    }
    write_json(output / "benchmark.json", report)
    write_json(output / "latency_records.json", latency)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = Path(mkdtemp(prefix="mvp3-benchmark-", dir=args.output_dir))
    result = run_benchmark(output)
    for policy, metrics in result["pooled_by_policy"].items():
        ac, dc = (metrics["by_zone"][zone] for zone in ("AC", "DC"))
        print(
            f"{policy} | AC {ac['on_time']}/{ac['requests']} | DC {dc['on_time']}/{dc['requests']} "
            f"| TOU {metrics['tou_cost']:.2f} USD | decision p95 {metrics['decision_latency_ms']['p95']:.3f} ms"
        )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
