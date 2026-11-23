"""Compatibility re-export (ADR-019 Phase 1): interval limits moved to `src.models.physical_limits`."""

from src.models.physical_limits import EffectiveLimits, effective_limits, environment_boundary

__all__ = ["EffectiveLimits", "effective_limits", "environment_boundary"]
