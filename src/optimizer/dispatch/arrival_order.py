"""Shared FIFO/FCFS arrival-order selection."""

from src.models.scheduling.dispatch import DispatchObservation


def arrival_order(observation: DispatchObservation) -> dict[str, str]:
    """FIFO/FCFS: arrival order, stable vehicle ID for simultaneous arrivals."""
    return dict(zip(observation.empty_ports, observation.waiting))
