"""Mandatory physical checks independent of dispatch, optimization and coordination."""

from collections import defaultdict
from collections.abc import Mapping
from math import isclose, isfinite
from numbers import Real

from ..coordination.base import ZoneBudgets
from ..dispatch.base import DispatchObservation
from ..observations import Candidate, SchedulingObservation
from ..scenario import Scenario, Vehicle
from .constraints import TOL, ConstraintViolationError
from .limits import EffectiveLimits, effective_limits


def valid_kw(value, upper: float) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and 0 <= value <= upper + TOL and isfinite(value)


def validate_dispatch(observation: DispatchObservation, plan: Mapping[str, str]) -> None:
    if not isinstance(plan, Mapping):
        raise ConstraintViolationError("Dispatch must map empty ports to waiting vehicle IDs")
    assigned = set()
    for port, vid in plan.items():
        if (
            port not in observation.empty_ports
            or not isinstance(vid, str)
            or vid not in observation.waiting
            or vid in assigned
        ):
            raise ConstraintViolationError(f"Invalid {observation.zone} dispatch: {port} -> {vid}")
        vehicle = observation.vehicles[vid]
        if vehicle.state != "QUEUED" or vehicle.connector is not None or vehicle.vehicle.zone != observation.zone:
            raise ConstraintViolationError(f"Ineligible vehicle for dispatch: {vid}")
        assigned.add(vid)


def validate_budgets(observation: SchedulingObservation, budgets: ZoneBudgets) -> None:
    if (
        not isinstance(budgets, ZoneBudgets)
        or type(budgets.minute) is not int
        or type(budgets.interval_minutes) is not int
        or budgets.minute != observation.minute
        or budgets.interval_minutes != observation.interval_minutes
    ):
        raise ConstraintViolationError("Missing or stale zone budgets for this interval")
    limits = observation.limits()
    if limits.minute != observation.minute:
        raise ConstraintViolationError("Stale effective physical limits for this interval")
    if budgets.output_kw.keys() != limits.zone_output_kw.keys():
        raise ConstraintViolationError("Assigned budget must include exactly the configured zones")
    for zone, cap in limits.zone_output_kw.items():
        if not valid_kw(budgets.output_kw[zone], cap):
            raise ConstraintViolationError(f"Invalid assigned zone budget: {zone}")
    _validate_supply(limits, budgets.output_kw, "Assigned zone budgets exceed")


def _validate_supply(limits: EffectiveLimits, output_kw: Mapping[str, float], message: str) -> None:
    if limits.shared_supply:
        if sum(output_kw.values()) / limits.conversion > limits.grid_input_kw + TOL:
            raise ConstraintViolationError(f"{message} site grid input limit")
    else:
        for zone, cap in limits.independent_grid_input_kw.items():
            if output_kw.get(zone, 0.0) / limits.conversion > cap + TOL:
                raise ConstraintViolationError(f"{message} independent grid input limit: {zone}")


def guard(
    scenario: Scenario,
    candidates: Mapping[str, Candidate],
    plan: Mapping[str, float],
    assigned_kw: Mapping[str, float],
    *,
    limits: EffectiveLimits | None = None,
) -> None:
    limits = effective_limits(scenario, scenario.start) if limits is None else limits
    if not isinstance(plan, Mapping):
        raise ConstraintViolationError("Allocation must map vehicle IDs to charger-output kW")
    zone_totals = defaultdict(float)
    cabinet_totals = defaultdict(float)
    for vid, kw in plan.items():
        item = candidates.get(vid)
        if item is None or not valid_kw(kw, min(item.allowed_kw, item.cabinet.port_kw)):
            raise ConstraintViolationError(f"Ineligible vehicle or invalid power: {vid} = {kw} kW")
        cabinet_totals[item.cabinet.id] += kw
        zone_totals[item.cabinet.zone] += kw
    for cabinet, cap in limits.cabinet_output_kw.items():
        if cabinet_totals[cabinet] > cap + TOL:
            raise ConstraintViolationError(f"Cabinet limit exceeded: {cabinet}")
    for zone, cap in limits.zone_output_kw.items():
        if zone_totals[zone] > min(cap, assigned_kw[zone]) + TOL:
            raise ConstraintViolationError(f"Zone limit exceeded: {zone}")
    _validate_supply(limits, zone_totals, "Allocation exceeds")


def validate_response(
    scenario: Scenario,
    vehicle: Vehicle,
    minutes: int,
    setpoint: float,
    before: float,
    soc: float,
    kw: float,
    energy: float,
) -> None:
    if (
        not 0 <= soc <= vehicle.target + TOL
        or not -TOL <= kw <= setpoint + TOL
        or energy < -TOL
        or not isclose(energy, (soc - before) * vehicle.battery_kwh, rel_tol=0, abs_tol=TOL)
        or not isclose(energy, kw * minutes / 60 * scenario.efficiency, rel_tol=0, abs_tol=TOL)
    ):
        raise ConstraintViolationError(f"Invalid battery response for {vehicle.id}")
