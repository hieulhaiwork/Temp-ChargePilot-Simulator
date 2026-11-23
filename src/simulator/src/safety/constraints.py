"""Compatibility re-export (ADR-019 Phase 1): tolerance and error moved to `src.models.physical_constraints`.

`valid_kw` (formerly defined in `safety/guard.py`) lives there too; it is re-exported here for `safety.guard`.
"""

from src.models.physical_constraints import TOL, ConstraintViolationError, valid_kw

__all__ = ["TOL", "ConstraintViolationError", "valid_kw"]
