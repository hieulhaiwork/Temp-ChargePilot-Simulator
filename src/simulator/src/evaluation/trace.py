"""Deterministic decision facts, built after the Guard verifies the applied interval."""

from src.optimizer.dispatch.least_laxity import optimistic_laxity

from ..safety.constraints import TOL
from ..scenario import clock

SCHEMA_VERSION = 2


def _binding_constraints(observation, budgets, power_by_vehicle) -> list[dict]:
    cfg = observation.scenario
    limits = observation.limits()
    bindings = []
    for stage in ("requested", "actual"):
        cabinet_power = {}
        zone_power = {}
        for vid, candidate in observation.candidates.items():
            kw = power_by_vehicle[vid][f"{stage}_output_kw"]
            cab = candidate.cabinet
            cabinet_power[cab.id] = cabinet_power.get(cab.id, 0.0) + kw
            zone_power[cab.zone] = zone_power.get(cab.zone, 0.0) + kw
            if abs(kw - candidate.allowed_kw) <= TOL:
                bindings.append(
                    {
                        "stage": stage,
                        "limit": "individual_allowed_output",
                        "id": vid,
                        "kw": candidate.allowed_kw,
                    }
                )
            if abs(kw - cab.port_kw) <= TOL:
                bindings.append(
                    {
                        "stage": stage,
                        "limit": "port_output",
                        "id": observation.vehicles[vid].connector,
                        "kw": cab.port_kw,
                    }
                )
        for cab in cfg.cabinets:
            cap = limits.cabinet_output_kw[cab.id]
            if cab.id in cabinet_power and abs(cabinet_power[cab.id] - cap) <= TOL:
                bindings.append({"stage": stage, "limit": "cabinet_output", "id": cab.id, "kw": cap})
        for zone, total in zone_power.items():
            for label, cap in (("zone_budget", budgets.output_kw[zone]), ("zone_limit", limits.zone_output_kw[zone])):
                if abs(total - cap) <= TOL:
                    bindings.append({"stage": stage, "limit": label, "id": zone, "kw": cap})
            if not limits.shared_supply:
                cap = limits.independent_grid_input_kw[zone]
                if abs(total / cfg.conversion - cap) <= TOL:
                    bindings.append({"stage": stage, "limit": "independent_grid_input", "id": zone, "kw": cap})
        if (
            limits.shared_supply
            and zone_power
            and abs(sum(zone_power.values()) / cfg.conversion - limits.grid_input_kw) <= TOL
        ):
            bindings.append({"stage": stage, "limit": "site_grid_input", "id": "site", "kw": limits.grid_input_kw})
    return bindings


def decision_record(
    observation,
    dispatch,
    assignments,
    demand,
    budgets,
    labels,
    power_by_vehicle,
    stored_by_vehicle,
    diagnostics,
) -> dict:
    cfg = observation.scenario
    limits = observation.limits()
    now = observation.minute
    hours = observation.interval_minutes / 60
    vehicles = {}
    waiting_laxity = {}
    for zone, item in dispatch.items():
        if zone != "DC":
            continue
        ports = item.empty_ports or tuple(item.port_output_kw)
        cap = max((item.port_output_kw[port] for port in ports), default=0.0)
        for vid in item.waiting:
            laxity = optimistic_laxity(item.vehicles[vid], now, cap, cfg.efficiency)
            waiting_laxity[vid] = {
                "optimistic_laxity_minutes": laxity,
                "at_risk_under_optimistic_bound": laxity is None or laxity < 0,
                "estimate_max_output_kw": min(item.vehicles[vid].vehicle.max_kw, cap),
                "estimate_basis": "free_ports" if item.empty_ports else "installed_ports",
            }

    for vid, item in observation.vehicles.items():
        if vid not in dispatch[item.vehicle.zone].waiting and item.connector is None:
            continue
        v = item.vehicle
        power = power_by_vehicle.get(vid, {})
        requested = power.get("requested_output_kw", 0.0)
        actual = power.get("actual_output_kw", 0.0)
        stored = stored_by_vehicle.get(vid, 0.0)
        row = {
            "zone": v.zone,
            "state": item.state,
            "connector": item.connector,
            "soc": item.soc,
            "target_soc": v.target,
            "deadline_minute": v.departure,
            "remaining_kwh": item.remaining_kwh,
            "vehicle_max_output_kw": v.max_kw,
            "requested_output_kw": requested,
            "allowed_output_kw": power.get("allowed_output_kw", 0.0),
            "actual_output_kw": actual,
            "battery_kwh": stored,
            "grid_input_kw": actual / cfg.conversion,
            "grid_kwh": actual * hours / cfg.conversion,
        }
        if vid in (diagnostics.get(v.zone, {}).get("projected_shortfall_kwh") or {}):
            prediction = requested * hours * cfg.efficiency
            row.update(
                predicted_output_kw=requested,
                predicted_battery_kwh=prediction,
                actual_minus_predicted_output_kw=actual - requested,
                actual_minus_predicted_battery_kwh=stored - prediction,
            )
        vehicles[vid] = row

    return {
        "schema_version": SCHEMA_VERSION,
        "minute": now,
        "time": clock(now),
        "interval_minutes": observation.interval_minutes,
        "planning_interval_minutes": budgets.interval_minutes,
        "algorithms": labels,
        "dispatch": {
            zone: {
                "waiting": list(item.waiting),
                "empty_ports": list(item.empty_ports),
                "assigned": {port: assignments[port] for port in item.empty_ports if port in assignments},
            }
            for zone, item in dispatch.items()
        },
        "queues_after_dispatch": {zone: list(waiting) for zone, waiting in observation.queues.items()},
        "ports_after_dispatch": dict(observation.ports),
        "vehicles": vehicles,
        "dc_waiting_laxity": waiting_laxity,
        "demand_output_kw": dict(demand),
        "budget_output_kw": dict(budgets.output_kw),
        "coordinator": {
            "policy": labels["coordinator"],
            "assigned_output_kw": dict(budgets.output_kw),
            "default_zone_budget_kw": dict(cfg.default_zone_budget_kw),
            "requested_output_kw": dict(demand),
            "reason_codes": {},
            "fallback_reason": None,
            **budgets.diagnostics,
        },
        "physical_limits": {
            "grid_input_kw": limits.grid_input_kw,
            "supply_mode": "shared" if limits.shared_supply else "independent",
            "independent_grid_input_kw": None if limits.shared_supply else dict(limits.independent_grid_input_kw),
            "zone_output_kw": dict(limits.zone_output_kw),
            "cabinet_output_kw": dict(limits.cabinet_output_kw),
            "port_output_kw": {
                f"{cab.id}/P{index + 1}": cab.port_kw for cab in cfg.cabinets for index in range(cab.ports)
            },
            "conversion_efficiency": cfg.conversion,
            "charging_efficiency": cfg.efficiency,
        },
        "published_limit_events": [
            {
                "effective_minute": event.effective_minute,
                "announced_minute": event.announced_minute,
                "grid_input_kw": event.grid_input_kw,
                "cabinet_output_kw": dict(event.cabinet_output_kw),
            }
            for event in cfg.limit_events
        ],
        "tariff": {
            "currency": cfg.tariff.currency,
            "price_per_grid_kwh": cfg.tariff.price_at(now),
            "published_periods": [
                {"minute": minute, "price_per_grid_kwh": price}
                for minute, price in zip(cfg.tariff.starts, cfg.tariff.prices)
            ],
        }
        if cfg.tariff
        else None,
        "optimizers": {
            zone: diagnostics.get(zone, {"solver_status": "not_applicable", "fallback_reason": None})
            for zone in cfg.zone_kw
        },
        "guard": {
            "status": "pass",
            "checks": ["dispatch", "budgets", "requested", "vehicle_response", "actual"],
            "absolute_tolerance": TOL,
            "binding_constraints": _binding_constraints(observation, budgets, power_by_vehicle),
        },
    }
