"""Earliest-deadline-first selection for waiting vehicles."""

from .base import DispatchObservation


def earliest_deadline(observation: DispatchObservation) -> dict[str, str]:
    ordered = sorted(
        observation.waiting,
        key=lambda vid: (
            observation.vehicles[vid].vehicle.departure,
            observation.vehicles[vid].vehicle.arrival,
            vid,
        ),
    )
    return dict(zip(observation.empty_ports, ordered))
