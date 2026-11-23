"""Example deadline-priority power allocation."""

from src.models.scheduling.observations import SchedulingObservation


def deadline_first(observation: SchedulingObservation, zone: str, budget_kw: float) -> dict[str, float]:
    """Example greedy allocation, for experiments with the optimizer interface."""
    remaining = budget_kw
    cabinet_left = {cab.id: cab.output_kw for cab in observation.scenario.cabinets if cab.zone == zone}
    plan = {}
    for vid in sorted(observation.candidates, key=lambda vid: (observation.vehicles[vid].vehicle.departure, vid)):
        candidate = observation.candidates[vid]
        cid = candidate.cabinet.id
        kw = min(candidate.allowed_kw, remaining, cabinet_left[cid])
        plan[vid] = kw
        remaining -= kw
        cabinet_left[cid] -= kw
    return plan
