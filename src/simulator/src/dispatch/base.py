"""Compatibility re-export (ADR-019 Phase 1): dispatch contract moved to `src.models.scheduling.dispatch`."""

from src.models.scheduling.dispatch import DispatchObservation, DispatchPolicy

__all__ = ["DispatchObservation", "DispatchPolicy"]
