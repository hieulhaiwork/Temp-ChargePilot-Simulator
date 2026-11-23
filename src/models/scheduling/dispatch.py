"""Dispatch observation and policy contract."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from src.models.scheduling.observations import VehicleObservation


@dataclass(frozen=True)
class DispatchObservation:
    minute: int
    zone: str
    empty_ports: tuple[str, ...]
    waiting: tuple[str, ...]
    vehicles: Mapping[str, VehicleObservation]
    port_output_kw: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))
    efficiency: float = 1.0


class DispatchPolicy(Protocol):
    def __call__(self, observation: DispatchObservation) -> Mapping[str, str]:
        """Propose empty port -> waiting ChargePilot vehicle ID."""
        ...
