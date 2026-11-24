"""MVP-2 comparative metrics and independent energy/physical reconciliation."""

from collections import defaultdict
from dataclasses import dataclass
from math import ceil, fsum, isfinite
from statistics import mean

from src.models.physical_constraints import TOL
from src.models.physical_limits import effective_limits
from src.models.simulation_core import Scenario

ENERGY_TOL_KWH = 1e-6


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[ceil(fraction * len(ordered)) - 1] if ordered else None


def latency_summary(values) -> dict:
    return {
        "samples": len(values),
        "p50": percentile(values, 0.5),
        "p95": percentile(values, 0.95),
        "max": max(values, default=None),
    }


def _within_limit(value: float, cap: float) -> None:
    if not isfinite(value) or not 0 <= value <= cap + TOL:
        raise ValueError(f"Benchmark physical audit failed for {value} kW against {cap} kW")


def audit(scenario: Scenario, result: dict) -> dict:
    by_id = {v.id: v for v in scenario.vehicles}
    connector_caps = {f"{cab.id}/P{index + 1}": cab for cab in scenario.cabinets for index in range(cab.ports)}
    trace = result["power_trace"]
    track = {
        "grid": fsum(row["grid_input_kw"] * row["duration_minutes"] / 60 for row in trace),
        "output": fsum((row["ac_output_kw"] + row["dc_output_kw"]) * row["duration_minutes"] / 60 for row in trace),
    }
    battery_per_vehicle = defaultdict(float)
    grid_per_vehicle = defaultdict(float)
    decisions = result["decision_trace"]
    if len(decisions) != len(trace):
        raise ValueError("Decision and power intervals differ")
    for decision, power in zip(decisions, trace):
        if (decision["minute"], decision["interval_minutes"]) != (power["minute"], power["duration_minutes"]):
            raise ValueError("Decision interval and power interval timestamps differ")
        if decision["guard"]["status"] != "pass":
            raise ValueError("Benchmark decision did not pass the Guard")
        limits = effective_limits(scenario, power["minute"])
        end = power["minute"] + power["duration_minutes"]
        if any(power["minute"] < event.effective_minute < end for event in scenario.limit_events):
            raise ValueError("Power interval crosses a physical limit change")
        if scenario.tariff and any(power["minute"] < start < end for start in scenario.tariff.starts):
            raise ValueError("Power interval crosses a published tariff boundary")
        recorded = decision["physical_limits"]
        if (
            recorded["grid_input_kw"] != limits.grid_input_kw
            or recorded["zone_output_kw"] != limits.zone_output_kw
            or recorded["cabinet_output_kw"] != limits.cabinet_output_kw
            or recorded["independent_grid_input_kw"] != limits.independent_grid_input_kw
        ):
            raise ValueError("Decision and physical schedule disagree")
        for stage in ("requested", "actual"):
            zone_totals, cabinet_totals = defaultdict(float), defaultdict(float)
            for vid, row in decision["vehicles"].items():
                kw = row[f"{stage}_output_kw"]
                if kw:
                    cab = connector_caps[row["connector"]]
                    if cab.zone != by_id[vid].zone:
                        raise ValueError("Benchmark port is incompatible with vehicle zone")
                    _within_limit(kw, min(by_id[vid].max_kw, cab.port_kw, row["allowed_output_kw"]))
                    zone_totals[cab.zone] += kw
                    cabinet_totals[cab.id] += kw
                if stage == "actual":
                    _within_limit(kw, row["requested_output_kw"])
                    output_kwh = kw * power["duration_minutes"] / 60
                    battery_per_vehicle[vid] += output_kwh * scenario.efficiency
                    grid_per_vehicle[vid] += output_kwh / scenario.conversion
            for cabinet, cap in limits.cabinet_output_kw.items():
                _within_limit(cabinet_totals[cabinet], cap)
            for zone, cap in limits.zone_output_kw.items():
                _within_limit(zone_totals[zone], min(cap, decision["budget_output_kw"][zone]))
                if not limits.shared_supply:
                    _within_limit(zone_totals[zone] / scenario.conversion, limits.independent_grid_input_kw[zone])
                if stage == "actual" and abs(zone_totals[zone] - power[f"{zone.lower()}_output_kw"]) > TOL:
                    raise ValueError("Decision and power trace zone totals differ")
            _within_limit(sum(zone_totals.values()) / scenario.conversion, limits.grid_input_kw)

    errors = {
        "grid_to_output_kwh": abs(track["grid"] * scenario.conversion - track["output"]),
        "output_to_soc_kwh": 0.0,
        "grid_to_vehicle_ledger_kwh": 0.0,
        "max_vehicle_battery_kwh": 0.0,
        "max_vehicle_grid_kwh": 0.0,
    }
    soc_deltas, ledger_grid = [], []
    for row in result["vehicles"]:
        vid = row["id"]
        v = by_id[vid]
        battery = (row["soc"] - v.initial_soc) * v.battery_kwh
        soc_deltas.append(battery)
        ledger_grid.append(row["delivered_grid_kwh"])
        errors["max_vehicle_battery_kwh"] = max(
            errors["max_vehicle_battery_kwh"],
            abs(battery - battery_per_vehicle[vid]),
            abs(battery - row["delivered_battery_kwh"]),
        )
        errors["max_vehicle_grid_kwh"] = max(
            errors["max_vehicle_grid_kwh"],
            abs(grid_per_vehicle[vid] - row["delivered_grid_kwh"]),
        )
    errors["output_to_soc_kwh"] = abs(track["output"] * scenario.efficiency - fsum(soc_deltas))
    errors["grid_to_vehicle_ledger_kwh"] = abs(track["grid"] - fsum(ledger_grid))
    if max(errors.values()) > ENERGY_TOL_KWH:
        raise ValueError(f"Benchmark energy audit failed: {errors}")
    return errors


@dataclass(frozen=True)
class RunSample:
    sessions: list[dict]
    latency: list[dict]
    audited_errors: dict
    charger_output_kwh: float
    fallbacks: int
    solver_rejections: int
    guard_rejections: int
    applied_violations: int
    prediction_errors: dict
    cost_by_zone: dict[str, float]
    currency: str | None


def sample_run(scenario: Scenario, result: dict) -> RunSample:
    by_id = {v.id: v for v in scenario.vehicles}
    sessions = []
    for row in result["vehicles"]:
        vehicle = by_id[row["id"]]
        required = (vehicle.target - vehicle.initial_soc) * vehicle.battery_kwh
        sessions.append(
            {
                "zone": vehicle.zone,
                "on_time": row["completed_at"] is not None and row["completed_at"] <= vehicle.departure,
                "waiting_minutes": row["waiting_minutes"],
                "censored": row["wait_censored"],
                "unserved": row["delivered_battery_kwh"] <= TOL,
                "abandoned": row["charge_started"] is None and row["departed_at"] is not None,
                "shortfall_kwh": max(0.0, vehicle.target - row["soc"]) * vehicle.battery_kwh,
                "battery_kwh": row["delivered_battery_kwh"],
                "grid_kwh": row["delivered_grid_kwh"],
                "fulfillment": min(1.0, row["delivered_battery_kwh"] / required),
            }
        )
    decisions = result["decision_trace"]
    diagnostics = [item for decision in decisions for item in decision["optimizers"].values()]
    predictions = [
        row for decision in decisions for row in decision["vehicles"].values() if "predicted_battery_kwh" in row
    ]
    costs = {}
    tariff = scenario.tariff
    if tariff is not None:
        costs = {
            zone: fsum(
                row[f"{zone.lower()}_output_kw"]
                / scenario.conversion
                * row["duration_minutes"]
                / 60
                * tariff.price_at(row["minute"])
                for row in result["power_trace"]
            )
            for zone in scenario.zone_kw
        }
    return RunSample(
        sessions,
        result["decision_latency_ms"],
        audit(scenario, result),
        fsum(
            (row["ac_output_kw"] + row["dc_output_kw"]) * row["duration_minutes"] / 60 for row in result["power_trace"]
        ),
        sum(d["fallback_reason"] is not None for d in diagnostics),
        sum(d.get("solver_plan_rejected", False) for d in diagnostics),
        result["rejected_allocation_count"],
        result["applied_constraint_violation_count"],
        {
            "samples": len(predictions),
            "max_abs_output_kw": max((abs(row["actual_minus_predicted_output_kw"]) for row in predictions), default=0),
            "max_abs_battery_kwh": max(
                (abs(row["actual_minus_predicted_battery_kwh"]) for row in predictions), default=0
            ),
        },
        costs,
        tariff.currency if tariff else None,
    )


def _session_metrics(sessions: list[dict]) -> dict:
    count = len(sessions)
    waits = [r["waiting_minutes"] for r in sessions if r["waiting_minutes"] is not None]
    done = sum(r["on_time"] for r in sessions)
    unserved = sum(r["unserved"] for r in sessions)
    abandoned = sum(r["abandoned"] for r in sessions)
    shares = [r["fulfillment"] for r in sessions]
    return {
        "requests": count,
        "on_time": done,
        "sla_rate": done / count if count else None,
        "mean_wait_all_arrivals_minutes": mean(waits) if waits else None,
        "p95_wait_all_arrivals_minutes": percentile(waits, 0.95),
        "censored_waits": sum(r["censored"] for r in sessions),
        "unserved": unserved,
        "unserved_rate": unserved / count if count else None,
        "abandoned": abandoned,
        "abandoned_rate": abandoned / count if count else None,
        "shortfall_kwh": fsum(r["shortfall_kwh"] for r in sessions),
        "battery_kwh": fsum(r["battery_kwh"] for r in sessions),
        "grid_kwh": fsum(r["grid_kwh"] for r in sessions),
        "jain_fulfillment": fsum(shares) ** 2 / (count * fsum(x * x for x in shares)) if any(shares) else None,
    }


def benchmark_metrics(samples: list[RunSample]) -> dict:
    sessions = [row for sample in samples for row in sample.sessions]
    latency = [row for sample in samples for row in sample.latency]
    currencies = {sample.currency for sample in samples if sample.currency is not None}
    costs = None
    if currencies:
        if len(currencies) != 1 or any(sample.currency is None for sample in samples):
            raise ValueError("Cannot pool runs with different tariff currencies or availability")
        costs = {zone: fsum(sample.cost_by_zone[zone] for sample in samples) for zone in ("AC", "DC")}
    return {
        "runs": len(samples),
        "overall": _session_metrics(sessions),
        "by_zone": {zone: _session_metrics([r for r in sessions if r["zone"] == zone]) for zone in ("AC", "DC")},
        "charger_output_kwh": fsum(run.charger_output_kwh for run in samples),
        "decision_latency_ms": latency_summary([row["decision_ms"] for row in latency]),
        "solver_latency_ms": latency_summary([ms for row in latency for ms in row["solver_ms"].values()]),
        "solver_latency_by_zone_ms": {
            zone: latency_summary([row["solver_ms"][zone] for row in latency if zone in row["solver_ms"]])
            for zone in ("AC", "DC")
        },
        "tou_cost": fsum(costs.values()) if costs else None,
        "tou_cost_by_zone": costs,
        "tou_currency": next(iter(currencies)) if currencies else None,
        "fallback_count": sum(run.fallbacks for run in samples),
        "rejected_solver_plan_count": sum(run.solver_rejections for run in samples),
        "guard_rejected_allocation_count": sum(run.guard_rejections for run in samples),
        "applied_constraint_violation_count": sum(run.applied_violations for run in samples),
        "max_energy_errors_kwh": {
            key: max(run.audited_errors[key] for run in samples) for key in samples[0].audited_errors
        },
        "lp_execution_prediction_errors": {
            "samples": sum(run.prediction_errors["samples"] for run in samples),
            "max_abs_output_kw": max(run.prediction_errors["max_abs_output_kw"] for run in samples),
            "max_abs_battery_kwh": max(run.prediction_errors["max_abs_battery_kwh"] for run in samples),
        },
    }
