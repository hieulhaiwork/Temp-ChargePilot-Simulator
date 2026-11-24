"""Shared tolerance and error for physical validation."""

from math import isfinite
from numbers import Real

TOL = 1e-7


class ConstraintViolationError(ValueError):
    pass


# Moved verbatim from src/simulator/src/safety/guard.py (ADR-019 Phase 1) so optimizers and the Guard share one
# numeric validity predicate without optimizer -> guard imports. `src.guard.physical.validator` imports it.
def valid_kw(value, upper: float) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and 0 <= value <= upper + TOL and isfinite(value)
