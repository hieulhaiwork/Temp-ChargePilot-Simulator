"""Deterministic budget allocation from current connected demand and deadline slack."""

from collections import defaultdict
from collections.abc import Mapping

from src.models.physical_constraints import TOL
from src.models.scheduling.coordination import ZoneBudgets
from src.models.scheduling.observations import SchedulingObservation


class DynamicSlackCoordinator:
    uses_online_interval = True

    def __call__(self, observation: SchedulingObservation, demand_kw: Mapping[str, float]) -> ZoneBudgets:
        limits = observation.limits()
        scenario = observation.scenario
        zones = tuple(limits.zone_output_kw)
        budget = dict.fromkeys(zones, 0.0)
        reasons = {zone: [] for zone in zones}

        by_cabinet = defaultdict(float)
        urgency = dict.fromkeys(zones, 0.0)
        hours = observation.interval_minutes / 60
        for vid, candidate in observation.candidates.items():
            cab = candidate.cabinet
            by_cabinet[cab.id] += candidate.allowed_kw
            item = observation.vehicles[vid]
            time_left = min(scenario.end, item.vehicle.departure) - observation.minute
            future_hours = max(0.0, time_left / 60 - hours)
            future_cap = min(item.vehicle.max_kw, cab.port_kw, cab.output_kw, limits.zone_output_kw[cab.zone])
            required_now = max(0.0, item.remaining_kwh / scenario.efficiency - future_cap * future_hours)
            urgency[cab.zone] += min(candidate.allowed_kw, required_now / hours)

        feasible = dict.fromkeys(zones, 0.0)
        for cab in scenario.cabinets:
            feasible[cab.zone] += min(by_cabinet[cab.id], limits.cabinet_output_kw[cab.id])
        feasible = {zone: min(kw, limits.zone_capacity_kw(zone)) for zone, kw in feasible.items()}
        reserve = {zone: min(feasible[zone], scenario.default_zone_budget_kw[zone]) for zone in zones}
        if limits.shared_supply:
            for targets, reason in (
                ({zone: min(feasible[zone], urgency[zone]) for zone in zones}, "deadline_headroom"),
                (reserve, "fixed_reservation"),
                (feasible, "shared_slack"),
            ):
                increments = {zone: max(0.0, targets[zone] - budget[zone]) for zone in zones}
                total = sum(increments.values())
                if total <= TOL:
                    continue
                free = max(0.0, limits.site_output_kw - sum(budget.values()))
                factor = min(1.0, free / total)
                for zone, kw in increments.items():
                    allocated = kw * factor
                    budget[zone] += allocated
                    if allocated > TOL:
                        reasons[zone].append(reason)
        else:
            budget = feasible.copy()
            for zone in zones:
                reasons[zone].append("independent_supply")

        for zone in zones:
            if demand_kw[zone] <= TOL:
                reasons[zone].append("no_connected_demand")
            elif budget[zone] + TOL < feasible[zone]:
                reasons[zone].append("shared_supply_scarcity")
            if feasible[zone] + TOL < demand_kw[zone]:
                reasons[zone].append("effective_capacity_bound")
        return ZoneBudgets(
            observation.minute,
            observation.interval_minutes,
            budget,
            {
                "requested_output_kw": dict(demand_kw),
                "eligible_demand_kw": feasible,
                "fixed_reservation_kw": reserve,
                "optimistic_deadline_headroom_kw": urgency,
                "reason_codes": reasons,
            },
        )
