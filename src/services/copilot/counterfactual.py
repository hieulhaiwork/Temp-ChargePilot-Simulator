"""Independent sandbox runner and paired no-op validator (Phase AI-4.2A: WP3.4).

Invariants:
- Reuses Unified Core (`HybridStation`), Business & Physical Guard, `dispatcher.submit`,
  `control_loop.on_minute`, and the existing single-thread `solver.run_async` executor.
- Never creates a second solver thread pool.
- Serializes sandbox minute decisions through `_SANDBOX_MINUTE_GATE` (`asyncio.Semaphore(1)`)
  and yields to the event loop every simulated minute (`await asyncio.sleep(0)`), ensuring at most
  one short LP solve is ever queued ahead of live `control_loop.on_event` or safety handlers.
- Never mutates `CapturedSnapshot`, live runtime, database, WebSocket clients, or filesystem.
- In Gate 3 (AI-4.2A), neither branch applies business patches (`baseline` and `counterfactual`
  are two independent no-op forks from the same `CapturedSnapshot` and `EventManifest`).
"""

import asyncio
import time
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import replace

from src.models.control import DecisionLogEntry
from src.models.copilot import PairedNoOpResult, SandboxBranchResult
from src.models.events import StationEvent
from src.services import control_loop
from src.services.copilot.outcome_ledger import OutcomeTracker
from src.services.copilot.snapshot import CapturedSnapshot, build_sandbox_runtime, canonical_sha256

# Per-event-loop Semaphore(1) so multiple sandbox rollouts never flood the single-worker HiGHS
# solver executor ahead of live replans, without binding one Semaphore across closed event loops.
_LOOP_MINUTE_GATES: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


def _minute_gate() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    gate = _LOOP_MINUTE_GATES.get(loop)
    if gate is None:
        gate = asyncio.Semaphore(1)
        _LOOP_MINUTE_GATES[loop] = gate
    return gate


class SandboxCancelledError(asyncio.CancelledError):
    """Raised when a sandbox rollout is explicitly cancelled via `cancel_event`."""


StepHook = Callable[[str, int], Awaitable[None] | None]
LiveBusyProbe = Callable[[], bool]


def _check_cancel(cancel_event: asyncio.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise SandboxCancelledError("Counterfactual sandbox rollout cancelled")


async def _cooperative_yield(
    cancel_event: asyncio.Event | None,
    live_busy_probe: LiveBusyProbe | None,
) -> None:
    """Yield to the event loop every minute and defer if a live replan/safety pass is active."""
    _check_cancel(cancel_event)
    await asyncio.sleep(0)
    if live_busy_probe is not None:
        # Bounded cooperative yield (at most a few event-loop turns) so live replan claims solver first.
        for _ in range(5):
            if not live_busy_probe():
                break
            _check_cancel(cancel_event)
            await asyncio.sleep(0.001)
    _check_cancel(cancel_event)


async def _execute_branch(
    snapshot: CapturedSnapshot,
    *,
    branch_label: str,
    cancel_event: asyncio.Event | None,
    step_hook: StepHook | None,
    live_busy_probe: LiveBusyProbe | None,
) -> SandboxBranchResult:
    started = time.perf_counter()
    _check_cancel(cancel_event)

    frt = build_sandbox_runtime(snapshot)
    minute_entries: list[DecisionLogEntry] = []
    base_log = frt.sinks.log_decision

    def _capture_entry(entry: DecisionLogEntry) -> None:
        base_log(entry)
        minute_entries.append(entry)

    frt.sinks = replace(frt.sinks, log_decision=_capture_entry)
    sim = frt.simulator
    end_minute = snapshot.event_manifest.horizon_end_minute

    tracker = OutcomeTracker(
        station_config=frt.config,
        tariff=frt.tariff,
        as_of=snapshot.envelope.as_of,
        horizon_minutes=snapshot.envelope.horizon_minutes,
        known_bookings=snapshot.known_bookings,
        station=sim,
    )

    events: list[StationEvent] = list(frt.take_events())
    executed_count = 0
    blocked_count = 0

    while sim.minute < end_minute:
        await _cooperative_yield(cancel_event, live_busy_probe)
        current_minute = sim.minute
        current_dt = sim.now

        async with _minute_gate():
            _check_cancel(cancel_event)
            minute_entries.clear()
            await control_loop.on_minute(frt, events)
            entries = list(minute_entries)
            for entry in entries:
                if entry.executed:
                    executed_count += 1
                elif entry.approval_id is None:
                    blocked_count += 1
            tracker.observe_after_dispatch(sim, entries)
            events = sim.step(1)
            tracker.observe_after_physics_step(
                sim,
                step_start_minute=current_minute,
                step_start_dt=current_dt,
                emitted_events=events,
            )

        if step_hook is not None:
            maybe_coro = step_hook(branch_label, sim.minute)
            if maybe_coro is not None:
                await maybe_coro

    _check_cancel(cancel_event)
    ledger = tracker.finalize(sim)
    final_physics = sim.snapshot_physics_state()
    final_physics_digest = canonical_sha256(final_physics)
    wall_ms = round((time.perf_counter() - started) * 1000.0, 3)

    return SandboxBranchResult(
        branch_label=branch_label,
        applied=False,
        snapshot_id=snapshot.envelope.snapshot_id,
        initial_snapshot_digest=snapshot.envelope.snapshot_digest,
        experiment_fingerprint=snapshot.envelope.experiment_fingerprint,
        event_manifest_sha256=snapshot.event_manifest.manifest_sha256,
        policy_id=snapshot.envelope.policy_id,
        policy_version=snapshot.envelope.policy_version,
        as_of=snapshot.envelope.as_of,
        horizon_end=snapshot.event_manifest.horizon_end,
        horizon_minutes=snapshot.envelope.horizon_minutes,
        decisions_count=len(frt.recorder.replan_durations_s),
        executed_command_count=executed_count,
        blocked_command_count=blocked_count,
        pending_approval_count_end=len(frt.store.pending_approvals()),
        safety_hold_booking_ids_end=sorted(frt.safety_hold_booking_ids),
        final_physics_digest=final_physics_digest,
        wall_time_ms=wall_ms,
        outcome_ledger=ledger,
    )


async def run_sandbox_branch(
    snapshot: CapturedSnapshot,
    *,
    branch_label: str = "baseline",
    timeout_s: float | None = None,
    cancel_event: asyncio.Event | None = None,
    step_hook: StepHook | None = None,
    live_busy_probe: LiveBusyProbe | None = None,
) -> SandboxBranchResult:
    """Run one isolated counterfactual branch from `snapshot` with optional timeout and cancellation."""
    if timeout_s is not None and timeout_s <= 0:
        raise ValueError("timeout_s must be positive when provided")
    coro = _execute_branch(
        snapshot,
        branch_label=branch_label,
        cancel_event=cancel_event,
        step_hook=step_hook,
        live_busy_probe=live_busy_probe,
    )
    if timeout_s is not None:
        async with asyncio.timeout(timeout_s):
            return await coro
    return await coro


def non_timing_branch_signature(result: SandboxBranchResult) -> dict:
    """Extract all deterministic non-timing metrics and per-vehicle outcomes for parity comparison."""
    return {
        "applied": result.applied,
        "initial_snapshot_digest": result.initial_snapshot_digest,
        "experiment_fingerprint": result.experiment_fingerprint,
        "event_manifest_sha256": result.event_manifest_sha256,
        "policy_id": result.policy_id,
        "policy_version": result.policy_version,
        "as_of": result.as_of.isoformat(),
        "horizon_end": result.horizon_end.isoformat(),
        "horizon_minutes": result.horizon_minutes,
        "decisions_count": result.decisions_count,
        "executed_command_count": result.executed_command_count,
        "blocked_command_count": result.blocked_command_count,
        "pending_approval_count_end": result.pending_approval_count_end,
        "safety_hold_booking_ids_end": result.safety_hold_booking_ids_end,
        "final_physics_digest": result.final_physics_digest,
        "outcome_ledger": result.outcome_ledger.model_dump(mode="json"),
    }


async def run_paired_noop(
    snapshot: CapturedSnapshot,
    *,
    timeout_s: float | None = None,
    cancel_event: asyncio.Event | None = None,
    interleaved: bool = False,
    live_busy_probe: LiveBusyProbe | None = None,
) -> PairedNoOpResult:
    """Run two independent no-op sandbox forks (`baseline` and `counterfactual`) from `snapshot`.

    In Gate 3 (AI-4.2A), neither branch applies business patches; both share the exact same
    `snapshot_digest`, `experiment_fingerprint`, `event_manifest`, and fixed booking cohort.
    When `interleaved=True`, both branches run concurrently on the event loop, alternating steps.
    """
    if timeout_s is not None and timeout_s <= 0:
        raise ValueError("timeout_s must be positive when provided")

    async def _run_both() -> tuple[SandboxBranchResult, SandboxBranchResult]:
        if interleaved:
            return await asyncio.gather(
                run_sandbox_branch(
                    snapshot,
                    branch_label="baseline",
                    cancel_event=cancel_event,
                    live_busy_probe=live_busy_probe,
                ),
                run_sandbox_branch(
                    snapshot,
                    branch_label="counterfactual",
                    cancel_event=cancel_event,
                    live_busy_probe=live_busy_probe,
                ),
            )
        base = await run_sandbox_branch(
            snapshot,
            branch_label="baseline",
            cancel_event=cancel_event,
            live_busy_probe=live_busy_probe,
        )
        cf = await run_sandbox_branch(
            snapshot,
            branch_label="counterfactual",
            cancel_event=cancel_event,
            live_busy_probe=live_busy_probe,
        )
        return base, cf

    if timeout_s is not None:
        async with asyncio.timeout(timeout_s):
            baseline, counterfactual = await _run_both()
    else:
        baseline, counterfactual = await _run_both()

    kpis_equal = non_timing_branch_signature(baseline) == non_timing_branch_signature(counterfactual)
    phys_equal = baseline.final_physics_digest == counterfactual.final_physics_digest

    return PairedNoOpResult(
        applied=False,
        snapshot_id=snapshot.envelope.snapshot_id,
        snapshot_digest=snapshot.envelope.snapshot_digest,
        experiment_fingerprint=snapshot.envelope.experiment_fingerprint,
        event_manifest_sha256=snapshot.event_manifest.manifest_sha256,
        horizon_minutes=snapshot.envelope.horizon_minutes,
        known_booking_ids=list(snapshot.event_manifest.known_booking_ids),
        baseline=baseline,
        counterfactual=counterfactual,
        non_timing_kpis_equal=kpis_equal,
        final_physics_digests_equal=phys_equal,
    )
