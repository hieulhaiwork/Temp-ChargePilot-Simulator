"""Run the fixed exploratory MVP-2 DC workload matrix on HybridSimulator."""

import argparse
import hashlib
import json
import platform
from collections import defaultdict
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from random import Random
from tempfile import mkdtemp

from .run import ROOT, write_json
from .src.algorithms import resolve_algorithms
from .src.engine.hybrid import HybridSimulator
from .src.evaluation.extended import ENERGY_TOL_KWH, benchmark_metrics, sample_run
from .src.optimizers.rolling_lp import FORECAST, LPConfig
from .src.safety.constraints import TOL
from .src.scenario import Scenario, clock

SEEDS = (11, 23, 37, 51, 71)
START = 18 * 60
# Each row is (arrival offset, stay, capacity, initial SOC, target SOC, vehicle kW).
DC_FAMILIES = {
    "queue_pressure": (
        (0, 80, 80, 0.25, 0.65, 60),
        (0, 75, 70, 0.32, 0.68, 60),
        (0, 65, 60, 0.40, 0.70, 60),
        (0, 88, 70, 0.24, 0.65, 55),
        (4, 47, 55, 0.36, 0.63, 60),
        (6, 58, 60, 0.45, 0.70, 50),
        (12, 95, 70, 0.35, 0.72, 60),
        (15, 35, 60, 0.55, 0.72, 55),
        (20, 66, 70, 0.40, 0.70, 60),
        (28, 82, 60, 0.30, 0.66, 60),
        (35, 55, 55, 0.44, 0.72, 60),
    ),
    "deadline_scarcity": (
        (0, 74, 70, 0.24, 0.67, 60),
        (0, 29, 65, 0.25, 0.65, 60),
        (0, 39, 55, 0.40, 0.65, 60),
        (10, 40, 70, 0.35, 0.60, 60),
        (18, 34, 60, 0.39, 0.64, 55),
        (24, 43, 60, 0.32, 0.69, 60),
    ),
    "high_soc_taper": (
        (0, 45, 70, 0.78, 0.96, 60),
        (0, 31, 55, 0.69, 0.91, 60),
        (0, 66, 65, 0.81, 0.94, 60),
        (5, 69, 70, 0.84, 0.99, 60),
        (8, 48, 60, 0.73, 0.93, 60),
        (15, 55, 65, 0.76, 0.95, 60),
        (24, 82, 55, 0.71, 0.94, 55),
    ),
    "feasible_infeasible_mix": (
        (0, 27, 90, 0.17, 0.77, 45),
        (0, 39, 60, 0.32, 0.60, 60),
        (0, 40, 65, 0.41, 0.69, 60),
        (0, 50, 55, 0.50, 0.66, 60),
        (3, 22, 80, 0.24, 0.75, 30),
        (12, 39, 60, 0.42, 0.67, 60),
        (21, 25, 60, 0.52, 0.71, 60),
        (29, 68, 65, 0.50, 0.82, 55),
    ),
    "no_congestion": (
        (0, 70, 60, 0.40, 0.65, 60),
        (4, 72, 55, 0.50, 0.68, 55),
        (84, 66, 65, 0.38, 0.70, 60),
        (88, 65, 60, 0.45, 0.71, 60),
    ),
}
AC_FLEET = (
    (0, 80, 55, 0.40, 0.63, 11),
    (0, 85, 60, 0.41, 0.63, 11),
    (12, 145, 55, 0.44, 0.64, 11),
)
POLICIES = {
    "B0": ("fcfs", "equal_share"),
    "M2a": ("llf", "equal_share"),
    "M2b": ("llf", "rolling_lp"),
    "M2c": ("edf", "equal_share"),
}
WEIGHT_SENSITIVITY = {
    "M2b_no_sla_weight": {"sla_weight": 0},
    "M2b_no_queue_weight": {"queue_weight": 0},
    "M2b_10x_queue_weight": {"queue_weight": 5},
}


def workload(family: str, seed: int) -> dict:
    rng = Random(seed)

    def vehicle(zone, index, row):
        arrival, stay, capacity, soc, target, cap = row
        if zone == "DC":
            # Preserve the initial simultaneous batch. Perturb later arrivals, stays and initial SOC.
            arrival = max(1, arrival + rng.randint(-2, 2)) if arrival else 0
            stay += rng.randint(-5, 5)
            soc = round(soc + rng.randint(-2, 2) / 100, 2)
        return {
            "id": f"{zone}-{index:02d}",
            "zone": zone,
            "arrival": clock(START + arrival),
            "departure": clock(START + arrival + stay),
            "battery_kwh": capacity,
            "initial_soc": soc,
            "target_soc": target,
            f"max_{zone.lower()}_kw": cap,
        }

    return {
        "scenario_id": f"mvp2_{family}_{seed}",
        "seed": seed,
        "start_time": clock(START),
        "duration_minutes": 165,
        "timestep_minutes": 1,
        "grid_input_limit_kw": 106,
        "ac_power_budget_kw": 22,
        "dc_power_budget_kw": 78,
        "power_conversion_efficiency": 0.95,
        "charging_efficiency": 0.98,
        "ac_unplug_policy": "declared_departure",
        "dc_unplug_delay_minutes": 5,
        "charger_cabinets": [
            {"id": "AC-01", "zone": "AC", "ports": 1, "port_limit_kw": 11, "cabinet_output_limit_kw": 11},
            {"id": "AC-02", "zone": "AC", "ports": 1, "port_limit_kw": 11, "cabinet_output_limit_kw": 11},
            {"id": "DC-01", "zone": "DC", "ports": 2, "port_limit_kw": 60, "cabinet_output_limit_kw": 120},
        ],
        "vehicles": [
            vehicle(zone, index, row)
            for zone, fleet in (("AC", AC_FLEET), ("DC", DC_FAMILIES[family]))
            for index, row in enumerate(fleet)
        ],
    }


def _comparison(cases: list[dict], policy: str, reference: str) -> dict:
    deltas = {}
    for case in cases:
        left = case["policies"][policy]["by_zone"]["DC"]["on_time"]
        right = case["policies"][reference]["by_zone"]["DC"]["on_time"]
        deltas[case["scenario_id"]] = left - right
    return {
        "wins": sum(delta > 0 for delta in deltas.values()),
        "ties": sum(delta == 0 for delta in deltas.values()),
        "losses": sum(delta < 0 for delta in deltas.values()),
        "dc_on_time_delta_by_scenario": deltas,
    }


def run_benchmark(output: Path, vinfast_sensitivity: bool) -> dict:
    cases, latency_records = [], []
    by_policy, by_family = defaultdict(list), defaultdict(lambda: defaultdict(list))

    def run_case(family, config, include_weights):
        scenario = Scenario.parse(config)
        runs = {}
        for policy in (*POLICIES, *(WEIGHT_SENSITIVITY if include_weights else ())):
            dispatch, optimizer = POLICIES.get(policy, POLICIES["M2b"])
            if policy in WEIGHT_SENSITIVITY:
                optimizer = {"name": optimizer, "parameters": WEIGHT_SENSITIVITY[policy]}
            selection = {
                **config.get("algorithms", {}),
                "dispatch": {"DC": dispatch},
                "optimizers": {"DC": optimizer},
            }
            algorithms, _ = resolve_algorithms(selection, scenario, "mvp2_benchmark")
            result = HybridSimulator(scenario, algorithms=algorithms, record_decisions=True).run()
            sample = sample_run(scenario, result)
            runs[policy] = benchmark_metrics([sample])
            latency_records.append(
                {
                    "scenario_id": scenario.id,
                    "policy": policy,
                    "intervals": sample.latency,
                }
            )
            if include_weights:
                by_policy[policy].append(sample)
                by_family[family][policy].append(sample)
        return {
            "scenario_id": scenario.id,
            "family": family,
            "scenario_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
            "scenario": config,
            "policies": runs,
        }

    for family in DC_FAMILIES:
        for seed in SEEDS:
            cases.append(run_case(family, workload(family, seed), include_weights=True))

    vinfast = None
    if vinfast_sensitivity:
        fixture = json.loads((ROOT / "scenario/vinfast_dc_2port_120kw.json").read_bytes())
        vinfast = run_case("vinfast_profile_v0_1", fixture, include_weights=False)

    benchmark = {
        "schema_version": 1,
        "software": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            **{name: version(name) for name in ("ev2gym", "numpy", "scipy")},
        },
        "fixed_seeds": SEEDS,
        "policy_selection": POLICIES,
        "main_dc_charging_model": "synthetic_taper_v1",
        "common_algorithms": {"ac_dispatch": "fifo", "ac_optimizer": "equal_share", "coordinator": "fixed_budget"},
        "lp_defaults": asdict(LPConfig()),
        "lp_forecast": FORECAST,
        "weight_sensitivity_overrides": WEIGHT_SENSITIVITY,
        "absolute_guard_tolerance": TOL,
        "absolute_energy_audit_tolerance_kwh": ENERGY_TOL_KWH,
        "latency_p95_target_ms": 2000,
        "main_cases": cases,
        "pooled_by_policy": {policy: benchmark_metrics(samples) for policy, samples in by_policy.items()},
        "pooled_by_family": {
            family: {policy: benchmark_metrics(samples) for policy, samples in policies.items()}
            for family, policies in by_family.items()
        },
        "dc_sla_paired_comparisons": {
            f"{policy}_vs_{reference}": _comparison(cases, policy, reference)
            for policy, reference in [
                ("M2a", "B0"),
                ("M2b", "B0"),
                ("M2c", "B0"),
                ("M2b", "M2a"),
                *((policy, "M2b") for policy in WEIGHT_SENSITIVITY),
            ]
        },
        "vinfast_sensitivity": vinfast,
    }
    write_json(output / "benchmark.json", benchmark)
    write_json(output / "latency_records.json", latency_records)
    return benchmark


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs", help="Parent directory for the new run")
    parser.add_argument("--vinfast-sensitivity", action="store_true", help="Also compare on the opt-in VinFast fixture")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = Path(mkdtemp(prefix="mvp2-benchmark-", dir=args.output_dir))
    report = run_benchmark(output, args.vinfast_sensitivity)
    for policy, metrics in report["pooled_by_policy"].items():
        dc = metrics["by_zone"]["DC"]
        decision_p95 = metrics["decision_latency_ms"]["p95"]
        print(f"{policy:>24} | DC {dc['on_time']:3}/{dc['requests']} | decision p95 {decision_p95:.3f} ms")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
