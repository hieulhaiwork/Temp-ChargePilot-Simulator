"""Shared progressive filling for AC and DC."""

from collections import defaultdict
from collections.abc import Mapping

from src.models.physical_constraints import TOL
from src.models.scheduling.observations import Candidate, SchedulingObservation
from src.models.simulation_core import Scenario


def equal_share_policy(observation: SchedulingObservation) -> dict[str, float]:
    return equal_share(observation.scenario, observation.candidates)


def equal_share(scenario: Scenario, candidates: Mapping[str, Candidate]) -> dict[str, float]:
    """Compatibility helper for existing combined power policies."""
    return {
        vid: kw
        for zone, budget in scenario.zone_kw.items()
        for vid, kw in _equal_share_zone(scenario, candidates, zone, budget).items()
    }


def zone_equal_share(observation: SchedulingObservation, zone: str, budget_kw: float) -> dict[str, float]:
    return _equal_share_zone(observation.scenario, observation.candidates, zone, budget_kw)


def _equal_share_zone(scenario, candidates, zone, budget):
    """Progressive filling within one zone, redistributing unused shares."""
    remaining = [vid for vid, item in candidates.items() if item.cabinet.zone == zone]
    allocation = dict.fromkeys(remaining, 0.0)
    cabinet_left = {cab.id: cab.output_kw for cab in scenario.cabinets if cab.zone == zone}
    while remaining and budget > TOL:
        counts = defaultdict(int)
        for vid in remaining:
            counts[candidates[vid].cabinet.id] += 1
        increment = min(
            budget / len(remaining),
            min(candidates[vid].allowed_kw - allocation[vid] for vid in remaining),
            min(cabinet_left[cab] / count for cab, count in counts.items()),
        )
        for vid in remaining:
            allocation[vid] += increment
        for cab, count in counts.items():
            cabinet_left[cab] -= increment * count
        budget -= increment * len(remaining)
        remaining = [
            vid
            for vid in remaining
            if candidates[vid].allowed_kw - allocation[vid] > TOL and cabinet_left[candidates[vid].cabinet.id] > TOL
        ]
    return allocation
