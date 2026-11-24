"""Feasibility-aware, non-preemptive least-laxity dispatch for DC."""

from math import isfinite

from src.models.scheduling.dispatch import DispatchObservation
from src.models.scheduling.observations import VehicleObservation


def optimistic_laxity(
    observation: VehicleObservation, minute: int, output_cap_kw: float, efficiency: float
) -> float | None:
    vehicle = observation.vehicle
    remaining_kwh = observation.remaining_kwh
    rate = min(vehicle.max_kw, output_cap_kw) * efficiency
    if remaining_kwh and not rate:
        return None  # No positive charging rate; JSON has no finite laxity here.
    minutes_needed = remaining_kwh / rate * 60 if remaining_kwh else 0.0
    laxity = vehicle.departure - minute - minutes_needed
    return laxity if isfinite(laxity) else None


def least_laxity(observation: DispatchObservation) -> dict[str, str]:
    """Place feasible EVs first, then the least late infeasible EVs, ignoring taper."""
    if not observation.empty_ports:
        return {}
    ports = sorted(observation.empty_ports, key=lambda port: -observation.port_output_kw[port])
    best_cap = observation.port_output_kw[ports[0]]

    def key(vid: str) -> tuple:
        item = observation.vehicles[vid]
        laxity = optimistic_laxity(item, observation.minute, best_cap, observation.efficiency)
        risk = laxity is None or laxity < 0
        magnitude = abs(laxity) if laxity is not None else float("inf")
        return risk, magnitude, item.vehicle.arrival, vid

    return dict(zip(ports, sorted(observation.waiting, key=key)))
