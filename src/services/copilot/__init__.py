"""Deterministic AI-4 Decision Copilot services (Phase AI-4.1 WHY Engine & Phase AI-4.2A Counterfactual Foundation).

Invariants:
- Live runtime is never stepped, drained, or mutated (`sync_clock` / live `simulator.step` forbidden).
- No live `StationActuator` calls, DB mutations, or WebSocket notifications from Copilot services.
- No LLM calls in deterministic WHY or Counterfactual Foundation services.
"""

from src.services.copilot.counterfactual import (
    SandboxCancelledError,
    non_timing_branch_signature,
    run_paired_noop,
    run_sandbox_branch,
)
from src.services.copilot.outcome_ledger import OutcomeTracker
from src.services.copilot.snapshot import (
    CapturedSnapshot,
    SnapshotNotReadyError,
    build_known_at_manifest,
    build_sandbox_runtime,
    canonical_sha256,
    capture_atomic_snapshot,
)
from src.services.copilot.why import explain_why

__all__ = [
    "CapturedSnapshot",
    "OutcomeTracker",
    "SandboxCancelledError",
    "SnapshotNotReadyError",
    "build_known_at_manifest",
    "build_sandbox_runtime",
    "canonical_sha256",
    "capture_atomic_snapshot",
    "explain_why",
    "non_timing_branch_signature",
    "run_paired_noop",
    "run_sandbox_branch",
]
