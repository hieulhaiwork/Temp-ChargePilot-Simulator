"""Deterministic AI-4 Decision Copilot services (Phase AI-4.1: WHY Engine).

Strictly read-only over DecisionTrace / repository data:
- No simulator stepping or clock advancement (`sync_clock` / `simulator.step` forbidden).
- No Command construction or actuator calls.
- No LLM calls in deterministic services.
"""

from src.services.copilot.why import explain_why

__all__ = ["explain_why"]
