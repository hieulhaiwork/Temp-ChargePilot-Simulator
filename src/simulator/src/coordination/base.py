"""Compatibility re-export (ADR-019 Phase 1): coordination contract moved to `src.models.scheduling.coordination`."""

from src.models.scheduling.coordination import GlobalCoordinator, ZoneBudgets

__all__ = ["GlobalCoordinator", "ZoneBudgets"]
