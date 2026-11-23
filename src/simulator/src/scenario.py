"""Compatibility re-export (ADR-019 Phase 1).

The scenario contract (`Scenario`, `Cabinet`, `Vehicle`, `LimitEvent`, `Tariff` and the parsing helpers) moved
verbatim to `src.models.simulation_core` so optimizer, guard and simulator can share it without import cycles.
This module re-exports the same objects; existing imports keep working and identity is preserved.
"""

from src.models.simulation_core import (
    Cabinet,
    LimitEvent,
    Scenario,
    Tariff,
    Vehicle,
    clock,
    identifier,
    integer,
    minute,
    number,
)

__all__ = [
    "Cabinet",
    "LimitEvent",
    "Scenario",
    "Tariff",
    "Vehicle",
    "clock",
    "identifier",
    "integer",
    "minute",
    "number",
]
