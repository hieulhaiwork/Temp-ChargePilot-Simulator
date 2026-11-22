"""AC deadline-first, then TOU, rolling-horizon linear allocation."""

from collections import defaultdict
from dataclasses import dataclass, replace
from numbers import Integral
from time import perf_counter
from typing import ClassVar

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, vstack

from ..observations import SchedulingObservation
from ..safety.constraints import TOL
from ..safety.limits import effective_limits
from ..scenario import integer, number
from .base import PowerProposal
from .equal_share import zone_equal_share

AC_TRANSITION_SOC = 0.8  # EV2Gym 2.0.0's default pilot taper transition at vehicle max kW.
FORECAST = {
    "deadline_window": "connected_deadlines_or_simulation_end",
    "zone_budget": "persistence_with_published_physical_caps",
    "tariff": "published_at_start",
    "acceptance": "conservative_end_of_block_pilot_taper",
}


@dataclass(frozen=True)
class ACConfig:
    block_minutes: int = 15
    time_limit_s: float = 0.2

    def __post_init__(self) -> None:
        integer(self.block_minutes, "AC block_minutes")
        if not number(self.time_limit_s, "AC time_limit_s"):
            raise ValueError("AC time_limit_s must be positive")


def _boundaries(observation: SchedulingObservation, block_minutes: int) -> list[int]:
    scenario = observation.scenario
    start = observation.minute
    first_end = start + observation.interval_minutes
    deadlines = {min(scenario.end, observation.vehicles[vid].vehicle.departure) for vid in observation.candidates}
    end = max(first_end, max(deadlines))
    extras = {event.effective_minute for event in scenario.limit_events if event.announced_minute <= start}
    if scenario.tariff:
        extras.update(scenario.tariff.starts)
    return sorted(
        {start, first_end, end, *range(first_end, end, block_minutes)}
        | {value for value in deadlines | extras if first_end < value < end}
    )


def _solve(objective, matrix, rhs, upper, timeout) -> tuple[np.ndarray | None, str, float]:
    if timeout <= 0:
        return None, "time_limit", 0.0
    started = perf_counter()
    try:
        answer = linprog(
            objective,
            A_ub=matrix,
            b_ub=rhs,
            bounds=np.column_stack((np.zeros(len(upper)), upper)),
            method="highs",
            options={"time_limit": timeout, "primal_feasibility_tolerance": 1e-9},
        )
    except (ValueError, RuntimeError, TypeError, ArithmeticError):
        return None, "solver_error", (perf_counter() - started) * 1000
    solver_ms = (perf_counter() - started) * 1000
    status = getattr(answer, "status", None)
    if not isinstance(status, Integral) or isinstance(status, bool):
        return None, "invalid_status", solver_ms
    if status != 0:
        reason = {1: "time_limit", 2: "infeasible", 3: "unbounded", 4: "solver_error"}.get(status, "invalid_status")
        return None, reason, solver_ms
    try:
        x = np.asarray(getattr(answer, "x", None))
    except (ValueError, TypeError):
        return None, "invalid_primal", solver_ms
    if (
        x.shape != upper.shape
        or x.dtype.kind not in "fiu"
        or not np.isfinite(x).all()
        or np.any(x < -TOL)
        or np.any(x > upper + TOL)
        or np.any(matrix @ x > rhs + TOL)
        or not np.isfinite(objective @ x)
    ):
        return None, "invalid_primal", solver_ms
    clipped = np.clip(x, 0.0, upper)
    if np.any(matrix @ clipped > rhs + TOL):
        return None, "invalid_primal", solver_ms
    return clipped, "optimal", solver_ms


@dataclass(frozen=True)
class ACRollingLP:
    config: ACConfig = ACConfig()
    uses_online_interval: ClassVar[bool] = True
    uses_published_limits: ClassVar[bool] = True

    def __call__(self, observation: SchedulingObservation, zone: str, budget_kw: float) -> PowerProposal:
        if zone != "AC":
            raise ValueError("ac_rolling_lp only supports AC")
        if not observation.candidates:
            return PowerProposal({}, {"solver_status": "not_needed", "fallback_reason": None})

        def fallback(stage, reason, solver_ms, statuses) -> PowerProposal:
            projected = observation.limits().as_optimizer_scenario(observation.scenario)
            safe = zone_equal_share(replace(observation, scenario=projected), zone, budget_kw)
            return PowerProposal(
                safe,
                {
                    "solver_status": reason,
                    "fallback_reason": reason,
                    "fallback_optimizer": "equal_share",
                    "fallback_stage": stage,
                    "stage_status": statuses,
                    "solver_plan_rejected": reason in {"invalid_primal", "invalid_status"},
                    "projected_shortfall_kwh": None,
                },
                solver_ms,
            )

        scenario = observation.scenario
        ids = sorted(observation.candidates)
        boundaries = _boundaries(observation, self.config.block_minutes)
        start = np.array(boundaries[:-1])
        end = np.array(boundaries[1:])
        block_count, vehicle_count = len(start), len(ids)
        power_count = block_count * vehicle_count
        size = power_count + vehicle_count
        hours = (end - start) / 60
        stored_per_kw = hours * scenario.efficiency
        prices = np.array([scenario.tariff.price_at(int(at)) if scenario.tariff else 0.0 for at in start])
        grid_cost_per_kw = hours * prices / scenario.conversion
        upper = np.zeros(size)
        rows, columns, data, rhs = [], [], [], []

        def constrain(index, coefficients, bound):
            rows.extend([len(rhs)] * len(index))
            columns.extend(index)
            data.extend(np.broadcast_to(coefficients, (len(index),)))
            rhs.append(bound)

        by_cabinet = defaultdict(list)
        for i, vid in enumerate(ids):
            item = observation.vehicles[vid]
            vehicle = item.vehicle
            cab = observation.candidates[vid].cabinet
            by_cabinet[cab.id].append(i)
            power = np.arange(i * block_count, (i + 1) * block_count)
            slack = power_count + i
            usable = end <= vehicle.departure
            upper[power] = np.where(usable, min(vehicle.max_kw, cab.port_kw), 0)
            upper[power[0]] = min(upper[power[0]], observation.candidates[vid].allowed_kw)
            upper[slack] = item.remaining_kwh
            constrain(power, stored_per_kw, item.remaining_kwh)
            constrain(np.append(power, slack), np.append(-stored_per_kw, -1.0), -item.remaining_kwh)
            # At the end of each block keep SOC below the native pilot crossover
            # 1 - (1 - transition_soc) * pilot_kw / max_vehicle_kw.
            taper = vehicle.max_kw / (1 - AC_TRANSITION_SOC)
            if item.vehicle.target > AC_TRANSITION_SOC and taper:
                for k in np.flatnonzero(usable):
                    coefficients = stored_per_kw[: k + 1] * taper / vehicle.battery_kwh
                    coefficients[-1] += 1.0
                    constrain(power[: k + 1], coefficients, taper * (1 - item.soc))

        for k, time in enumerate(start):
            limits = observation.limits() if k == 0 else effective_limits(scenario, int(time))
            constrain(range(k, power_count, block_count), 1, min(budget_kw, limits.zone_capacity_kw(zone)))
            for cid, indices in by_cabinet.items():
                constrain([i * block_count + k for i in indices], 1, limits.cabinet_output_kw[cid])

        matrix = csr_matrix((data, (rows, columns)), shape=(len(rhs), size))
        rhs = np.array(rhs)
        sla = np.zeros(size)
        sla[power_count:] = 1
        primary, status, solver_ms = _solve(sla, matrix, rhs, upper, self.config.time_limit_s)
        statuses = {"sla": status}
        if primary is None:
            return fallback("sla", status, solver_ms, statuses)
        best_shortfall = float(sla @ primary)

        # With constant prices, every feasible plan on the primary face has the
        # same cost. Break the tie in favor of early charging.
        secondary = np.zeros(size)
        if np.all(prices == prices[0]):
            secondary[:power_count] = np.tile(hours * (start - start[0]) / (end[-1] - start[0]), vehicle_count)
        else:
            secondary[:power_count] = np.tile(grid_cost_per_kw, vehicle_count)
        plan, status, next_ms = _solve(
            secondary,
            vstack((matrix, csr_matrix(sla.reshape(1, -1))), format="csr"),
            np.append(rhs, best_shortfall),
            upper,
            self.config.time_limit_s - solver_ms / 1000,
        )
        solver_ms += next_ms
        statuses["tou"] = status
        if plan is None:
            return fallback("tou", status, solver_ms, statuses)
        return PowerProposal(
            {vid: float(plan[i * block_count]) for i, vid in enumerate(ids)},
            {
                "solver_status": "optimal",
                "fallback_reason": None,
                "stage_status": statuses,
                "forecast": FORECAST,
                "primary_minimum_shortfall_kwh": best_shortfall,
                "projected_shortfall_kwh": {vid: float(plan[power_count + i]) for i, vid in enumerate(ids)},
                "projection_cutoff_minute": {
                    vid: min(scenario.end, observation.vehicles[vid].vehicle.departure) for vid in ids
                },
                "projected_tou_cost": float(plan[:power_count] @ np.tile(grid_cost_per_kw, vehicle_count))
                if scenario.tariff
                else None,
                "horizon_end_minute": int(end[-1]),
                "blocks": block_count,
            },
            solver_ms,
        )
