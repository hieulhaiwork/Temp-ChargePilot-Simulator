"""Online, DC-only rolling-horizon power allocation using SciPy HiGHS."""

from collections import defaultdict
from dataclasses import dataclass
from numbers import Integral
from time import perf_counter
from typing import ClassVar

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix

from ..charging_models.base import DCChargingModel, VehicleBatteryState
from ..observations import SchedulingObservation, VehicleObservation
from ..safety.constraints import TOL
from ..safety.guard import valid_kw
from ..scenario import integer, number
from .base import PowerProposal
from .equal_share import zone_equal_share

SAMPLE_COUNT = 9
FORECAST = {
    "budget_and_physical_caps": "persistence",
    "future_arrivals": "unknown",
    "acceptance": "sampled_affine_lower_envelope_at_block_start",
}


@dataclass(frozen=True)
class LPConfig:
    horizon_minutes: int = 120
    block_minutes: int = 5
    sla_weight: float = 4.0
    shortfall_weight: float = 1.0
    early_weight: float = 0.02
    queue_weight: float = 0.5
    time_limit_s: float = 0.2

    def __post_init__(self) -> None:
        for name in ("horizon_minutes", "block_minutes"):
            integer(getattr(self, name), name)
        for name in ("sla_weight", "shortfall_weight", "early_weight", "queue_weight", "time_limit_s"):
            number(getattr(self, name), name)
        if not self.time_limit_s or not self.shortfall_weight:
            raise ValueError("time_limit_s and shortfall_weight must be positive")


def _acceptance_line(model: DCChargingModel, item: VehicleObservation, cap_kw: float) -> tuple[float, float]:
    """Bound future block-start acceptance by a sampled affine function of stored energy."""
    v = item.vehicle
    room = item.remaining_kwh
    if not room:
        return 0.0, 0.0
    initial = item.soc * v.battery_kwh
    target = v.target * v.battery_kwh
    fractions = np.linspace(0.0, 1.0, SAMPLE_COUNT)
    acceptance = []
    for fraction in fractions:
        current = min(target, initial + float(fraction) * room)
        kw = model.acceptance_kw(VehicleBatteryState(v.id, v.max_kw, v.battery_kwh, current, target))
        if not valid_kw(kw, float("inf")):
            raise ValueError("Invalid DC acceptance forecast")
        acceptance.append(min(cap_kw, kw))
    floor = min(acceptance)
    drop = min((kw - floor) / (1 - fraction) for kw, fraction in zip(acceptance[:-1], fractions[:-1]))
    return float(floor + drop), float(drop / room)


def _blocks(observation: SchedulingObservation, config: LPConfig) -> list[tuple[int, int]]:
    now = observation.minute
    first_end = now + observation.interval_minutes
    deadlines = {observation.vehicles[vid].vehicle.departure for vid in observation.candidates}
    end = max(first_end, min(now + config.horizon_minutes, observation.scenario.end, max(deadlines)))
    boundaries = sorted(
        {now, first_end, end, *range(first_end, end, config.block_minutes)}
        | {deadline for deadline in deadlines if first_end < deadline < end}
    )
    return list(zip(boundaries, boundaries[1:]))


def _valid_primal(solution, objective, matrix, limits, upper) -> np.ndarray | None:
    try:
        x = np.asarray(solution)
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        x.shape != objective.shape
        or x.dtype.kind not in "fiu"
        or not np.all(np.isfinite(x))
        or np.any(x < -TOL)
        or np.any(x > upper + TOL)
        or np.any(matrix @ x > limits + TOL)
        or not np.isfinite(objective @ x)
    ):
        return None
    x = np.clip(x, 0, upper)
    return x if np.all(matrix @ x <= limits + TOL) else None


@dataclass(frozen=True)
class RollingHorizonLP:
    config: LPConfig = LPConfig()
    uses_online_interval: ClassVar[bool] = True

    def __call__(self, observation: SchedulingObservation, zone: str, budget_kw: float) -> PowerProposal:
        if zone != "DC":
            raise ValueError("rolling_lp only supports DC")
        if not observation.candidates:
            return PowerProposal(
                {},
                {
                    "solver_status": "not_needed",
                    "fallback_reason": None,
                    "projected_shortfall_kwh": None,
                },
            )

        def fallback(reason: str, solver_ms=None, *, status=None, rejected=False) -> PowerProposal:
            return PowerProposal(
                zone_equal_share(observation, zone, budget_kw),
                {
                    "solver_status": reason,
                    "solver_status_code": status,
                    "fallback_reason": reason,
                    "fallback_optimizer": "equal_share",
                    "solver_plan_rejected": rejected,
                    "projected_shortfall_kwh": None,
                    "planning_interval_minutes": observation.interval_minutes,
                },
                solver_ms,
            )

        model = observation.dc_charging_model
        if model is None:
            return fallback("missing_dc_model")
        cfg = self.config
        scenario = observation.scenario
        vehicle_ids = sorted(observation.candidates)
        blocks = _blocks(observation, cfg)
        count = len(blocks)
        power_count = len(vehicle_ids) * count
        size = power_count + len(vehicle_ids)
        objective, upper = np.zeros(size), np.zeros(size)
        row_indices, column_indices, values, limits = [], [], [], []

        def constrain(columns, coefficients, limit):
            column_indices.extend(columns)
            row_indices.extend([len(limits)] * len(columns))
            values.extend(np.broadcast_to(coefficients, (len(columns),)))
            limits.append(limit)

        by_cabinet = defaultdict(list)
        waiting = bool(observation.queues[zone])
        horizon_end = blocks[-1][1]
        horizon_length = horizon_end - observation.minute
        early = np.array([(horizon_end - start) / horizon_length for start, _ in blocks])
        for index, vid in enumerate(vehicle_ids):
            candidate = observation.candidates[vid]
            item = observation.vehicles[vid]
            v = item.vehicle
            cab = candidate.cabinet
            room = item.remaining_kwh
            cap = min(v.max_kw, cab.port_kw)
            charges = np.arange(index * count, (index + 1) * count)
            slack = power_count + index
            by_cabinet[cab.id].append(index)
            stored_per_kw = np.array(
                [scenario.efficiency * (end - start) / 60 if end <= v.departure else 0.0 for start, end in blocks]
            )
            upper[charges] = np.where(stored_per_kw > 0, cap, 0.0)
            upper[charges[0]] = min(upper[charges[0]], candidate.allowed_kw)
            upper[slack] = room
            deadline_in_horizon = v.departure <= horizon_end
            objective[slack] = cfg.shortfall_weight + (cfg.sla_weight / max(room, 1.0) if deadline_in_horizon else 0)
            reward = cfg.early_weight + (cfg.queue_weight / max(room, 1.0) if waiting else 0)
            objective[charges] = -reward * early * stored_per_kw
            constrain(charges, stored_per_kw, room)
            constrain(np.append(charges, slack), np.append(-stored_per_kw, -1), -room)
            if count > 1:
                try:
                    intercept, slope = _acceptance_line(model, item, cap)
                except (ValueError, ArithmeticError):
                    return fallback("invalid_acceptance_forecast")
                for block in range(1, count):
                    if stored_per_kw[block] > 0:
                        constrain(charges[: block + 1], np.append(slope * stored_per_kw[:block], 1), intercept)

        for block in range(count):
            constrain(range(block, power_count, count), 1, min(budget_kw, scenario.zone_kw[zone]))
            for cab in scenario.cabinets:
                members = by_cabinet.get(cab.id)
                if members:
                    constrain([index * count + block for index in members], 1, cab.output_kw)

        matrix = csr_matrix((values, (row_indices, column_indices)), shape=(len(limits), size))
        rhs = np.array(limits)
        started = perf_counter()
        try:
            result = linprog(
                objective,
                A_ub=matrix,
                b_ub=rhs,
                bounds=np.column_stack((np.zeros(size), upper)),
                method="highs",
                options={"time_limit": cfg.time_limit_s},
            )
        except (RuntimeError, ValueError, TypeError, ArithmeticError):
            return fallback("solver_error", (perf_counter() - started) * 1000)
        solver_ms = (perf_counter() - started) * 1000
        status = getattr(result, "status", None)
        if not isinstance(status, Integral) or isinstance(status, bool):
            return fallback("invalid_solver_status", solver_ms, rejected=True)
        status = int(status)
        if status != 0:
            reason = {1: "time_or_iteration_limit", 2: "infeasible", 3: "unbounded"}.get(status, "solver_error")
            return fallback(reason, solver_ms, status=status)
        x = _valid_primal(getattr(result, "x", None), objective, matrix, rhs, upper)
        if x is None:
            return fallback("invalid_primal", solver_ms, status=status, rejected=True)
        return PowerProposal(
            {vid: float(x[index * count]) for index, vid in enumerate(vehicle_ids)},
            {
                "solver_status": "optimal",
                "solver_status_code": status,
                "fallback_reason": None,
                "solver_plan_rejected": False,
                "forecast": dict(FORECAST),
                "blocks": count,
                "planning_interval_minutes": observation.interval_minutes,
                "horizon_end_minute": horizon_end,
                "projected_shortfall_kwh": {
                    vid: float(x[power_count + index]) for index, vid in enumerate(vehicle_ids)
                },
                "projection_cutoff_minute": {
                    vid: min(horizon_end, observation.vehicles[vid].vehicle.departure) for vid in vehicle_ids
                },
            },
            solver_ms,
        )
