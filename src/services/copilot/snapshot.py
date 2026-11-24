"""Atomic snapshot capture and prospective `known_at(T)` manifest (Phase AI-4.2A: WP3.2 & WP3.3).

Lock acquisition order matches the repository's canonical hierarchy:
    `rt.booking_lock` (async)
      -> `rt.decision_lock()` / `rt.lock` (async; pauses `sync_clock` read-driven steps)
        -> `rt._clock_lock` (thread RLock; guards outbox & pending safety registry)
          -> `rt.simulator.lock` (thread RLock; guards `HybridStation` & `StationKernel`)

Locks are held ONLY during in-memory state cloning and SHA-256 digest computation (never during
sandbox rollout or LP solving). `CapturedSnapshot` contains pure data and a detached, lock-free,
actuator-free `PhysicsSnapshotSeed` — zero live DB connections, event loops, locks, WebSocket
clients, or `StationActuator` instances.
"""

import hashlib
import json
from collections import deque
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from src.guard.physical import adapter as physical_guard_adapter
from src.models.charging import Booking, SchedulePlan, StrategyName
from src.models.control import Approval, Command
from src.models.copilot import (
    EVENT_MANIFEST_SCHEMA_VERSION,
    MAX_COUNTERFACTUAL_HORIZON_MINUTES,
    SNAPSHOT_SCHEMA_VERSION,
    EventManifest,
    KnownLimitEvent,
    SnapshotEnvelope,
    SnapshotNotReadyReason,
    SnapshotStatus,
)
from src.models.events import EventType, StationEvent
from src.models.physical_constraints import TOL
from src.models.simulation import ResolvedExperiment
from src.models.station import StationConfig, Tariff
from src.services.experiment import resolve_experiment
from src.services.runtime import ACTIVE, OUTBOX_MAX, StationRuntime, _memory_runtime, make_scheduler, visit_of
from src.simulator.hybrid_station import HybridStation, PhysicsSnapshotSeed

PROSPECTIVE_ASSUMPTIONS: tuple[str, ...] = (
    "Prospective known_at(T) boundary: only bookings registered at or before T (created_at <= T) and vehicles physically present at T are included.",
    "Prospective known_at(T) boundary: only supply/cabinet limit events announced at or before T (announced_minute <= as_of_minute) are visible to optimizer and sandbox physics.",
    "Current backend Incident payloads carry no announcement timestamp; only incidents already effective in station state at T are included (no unannounced future benchmark incidents).",
    "Pending HITL/resident approvals remain undecided during non-interactive sandbox rollout unless explicitly resolved in future phases.",
    "Live runtime is never stepped, drained, or mutated during snapshot capture or sandbox rollout.",
)


class SnapshotNotReadyError(RuntimeError):
    """Raised when live station state cannot safely or consistently be captured for counterfactual rollout."""

    def __init__(self, reason: SnapshotNotReadyReason, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.status = SnapshotStatus.NOT_READY
        self.reason = reason
        self.detail = detail


def canonical_sha256(payload: Any) -> str:
    """Stable SHA-256 hex digest of canonical sorted-key JSON with strict finite-number check."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _freeze_json_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(k): _freeze_json_tree(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json_tree(item) for item in value)
    return value


def _thaw_json_tree(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw_json_tree(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json_tree(item) for item in value]
    return value


@dataclass(frozen=True)
class CapturedSnapshot:
    """Immutable, self-contained counterfactual snapshot at `envelope.as_of`.

    Contains NO locks, NO event loops, NO DB sessions/engines, NO WebSocket clients,
    and NO `StationActuator` / `HybridStation` instances.
    """

    envelope: SnapshotEnvelope
    event_manifest: EventManifest
    experiment: ResolvedExperiment
    station_config: StationConfig
    tariff: Tariff
    plan: SchedulePlan | None
    known_bookings: tuple[Booking, ...]
    pending_approvals: tuple[Approval, ...]
    recent_commands: tuple[Command, ...]
    safety_hold_booking_ids: frozenset[str]
    rejected_booking_ids: frozenset[str]
    ordinary_outbox_events: tuple[StationEvent, ...]
    pending_safety_events: tuple[StationEvent, ...]
    acknowledged_safety_ids: tuple[str, ...]
    safety_attempts: int
    scheduler_name: StrategyName | str
    scheduler_parameters: Mapping[str, Any]
    scheduler_metadata: Mapping[str, Any]
    physics_state: Mapping[str, Any]
    _physics_seed: PhysicsSnapshotSeed

    def recompute_digest(self) -> str:
        """Recompute canonical content digest from stored snapshot fields (verifies immutability)."""
        seed_probe = HybridStation.from_physics_seed(self.station_config, self._physics_seed)
        known_ids = frozenset(self.event_manifest.known_booking_ids)
        seed_probe.enforce_known_at_on_fork(self.envelope.sim_minute, known_ids)
        live_seed_physics = seed_probe.snapshot_physics_state()
        return _build_snapshot_digest_payload(
            station_id=self.envelope.station_id,
            as_of=self.envelope.as_of,
            sim_minute=self.envelope.sim_minute,
            booking_version=self.envelope.booking_version,
            plan_version=self.envelope.plan_version,
            state_version=self.envelope.state_version,
            schedule_version=self.envelope.schedule_version,
            experiment=self.experiment,
            station_config=self.station_config,
            tariff=self.tariff,
            plan=self.plan,
            known_bookings=self.known_bookings,
            pending_approvals=self.pending_approvals,
            recent_commands=self.recent_commands,
            safety_hold_booking_ids=self.safety_hold_booking_ids,
            rejected_booking_ids=self.rejected_booking_ids,
            ordinary_outbox_events=self.ordinary_outbox_events,
            event_manifest=self.event_manifest,
            physics_state=live_seed_physics,
        )


def _build_snapshot_digest_payload(
    *,
    station_id: str,
    as_of: datetime,
    sim_minute: int,
    booking_version: int,
    plan_version: int | None,
    state_version: int,
    schedule_version: int,
    experiment: ResolvedExperiment,
    station_config: StationConfig,
    tariff: Tariff,
    plan: SchedulePlan | None,
    known_bookings: tuple[Booking, ...],
    pending_approvals: tuple[Approval, ...],
    recent_commands: tuple[Command, ...],
    safety_hold_booking_ids: frozenset[str],
    rejected_booking_ids: frozenset[str],
    ordinary_outbox_events: tuple[StationEvent, ...],
    event_manifest: EventManifest,
    physics_state: dict[str, Any],
) -> str:
    canonical = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "station_id": station_id,
        "as_of": as_of.isoformat(),
        "sim_minute": sim_minute,
        "versions": {
            "booking_version": booking_version,
            "plan_version": plan_version,
            "state_version": state_version,
            "schedule_version": schedule_version,
        },
        "experiment_fingerprint": experiment.fingerprint,
        "experiment": experiment.model_dump(mode="json"),
        "station_config": station_config.model_dump(mode="json"),
        "tariff": tariff.model_dump(mode="json"),
        "plan": None if plan is None else plan.model_dump(mode="json"),
        "known_bookings": [b.model_dump(mode="json") for b in known_bookings],
        "pending_approvals": [a.model_dump(mode="json") for a in pending_approvals],
        "recent_commands": [c.model_dump(mode="json") for c in recent_commands],
        "safety_hold_booking_ids": sorted(safety_hold_booking_ids),
        "rejected_booking_ids": sorted(rejected_booking_ids),
        "ordinary_outbox_events": [e.model_dump(mode="json") for e in ordinary_outbox_events],
        "event_manifest_sha256": event_manifest.manifest_sha256,
        "physics_state": physics_state,
    }
    return canonical_sha256(canonical)


def _check_capture_readiness(
    *,
    station_config: StationConfig,
    safety_hold_booking_ids: frozenset[str],
    pending_safety: tuple[StationEvent, ...],
    ordinary_outbox: tuple[StationEvent, ...],
    probe_station: HybridStation,
) -> None:
    """Verify station is safe & consistent on an isolated fork probe without calling live stateful models."""
    if pending_safety:
        ids = ", ".join(ev.event_id for ev in pending_safety)
        raise SnapshotNotReadyError(
            SnapshotNotReadyReason.UNRESOLVED_HARD_SAFETY_EVENT,
            f"Pending hard safety event(s) unresolved: {ids}",
        )
    hard_in_outbox = [ev.event_id for ev in ordinary_outbox if ev.type == EventType.HARD_LIMIT_VIOLATED]
    if hard_in_outbox:
        raise SnapshotNotReadyError(
            SnapshotNotReadyReason.UNRESOLVED_HARD_SAFETY_EVENT,
            f"Undelivered hard safety event(s) in outbox: {', '.join(hard_in_outbox)}",
        )
    safety_state = probe_station.safety_state()
    for conn in safety_state.connectors:
        if conn.booking_id in safety_hold_booking_ids and conn.power_kw > 0:
            raise SnapshotNotReadyError(
                SnapshotNotReadyReason.UNSAFE_PHYSICAL_STATE,
                f"Booking {conn.booking_id} under Safety Hold still draws {conn.power_kw:g} kW on {conn.connector_id}",
            )
        if conn.power_kw > conn.max_power_kw + TOL:
            raise SnapshotNotReadyError(
                SnapshotNotReadyReason.UNSAFE_PHYSICAL_STATE,
                f"Connector {conn.connector_id} exceeds port limit ({conn.power_kw:g} > {conn.max_power_kw:g} kW)",
            )
    power = {c.connector_id: c.power_kw for c in safety_state.connectors}
    occupants = {c.connector_id: c.booking_id for c in safety_state.connectors}
    site_violation = physical_guard_adapter.check_site_allocation(station_config, safety_state, power, occupants)
    if site_violation is not None:
        detail = getattr(site_violation, "detail", str(site_violation))
        raise SnapshotNotReadyError(
            SnapshotNotReadyReason.UNSAFE_PHYSICAL_STATE,
            f"Current station allocation violates physical limits: {detail}",
        )


def build_known_at_manifest(
    *,
    station_id: str,
    as_of: datetime,
    as_of_minute: int,
    horizon_minutes: int,
    active_bookings: list[Booking],
    raw_physics_state: dict[str, Any],
) -> tuple[EventManifest, tuple[Booking, ...]]:
    """Materialize `known_at(T)` cohort & exogenous events once, excluding future hidden ground truth."""
    if horizon_minutes <= 0 or horizon_minutes > MAX_COUNTERFACTUAL_HORIZON_MINUTES:
        raise ValueError(f"horizon_minutes must be in 1..{MAX_COUNTERFACTUAL_HORIZON_MINUTES}")
    sessions: dict[str, dict[str, Any]] = raw_physics_state["sessions"]
    present_ids = sorted(vid for vid, s in sessions.items() if s["state"] not in ("NOT_ARRIVED", "DEPARTED"))
    present_set = set(present_ids)

    kept_bookings: list[Booking] = []
    excluded_future_bookings = 0
    for b in sorted(active_bookings, key=lambda item: item.booking_id):
        # Bookings created at/before T (or already physically present at T) belong to known_at(T).
        if b.created_at <= as_of or b.booking_id in present_set:
            kept_bookings.append(b.model_copy(deep=True))
        else:
            excluded_future_bookings += 1

    all_booking_ids = {b.booking_id for b in active_bookings}
    known_booking_ids = sorted(b.booking_id for b in kept_bookings)
    known_set = set(known_booking_ids)
    known_future_arrivals = sorted(
        vid
        for vid in known_booking_ids
        if vid not in present_set and sessions.get(vid, {}).get("state", "NOT_ARRIVED") == "NOT_ARRIVED"
    )
    excluded_unbooked_not_arrived = sum(
        1 for vid, s in sessions.items() if s["state"] == "NOT_ARRIVED" and vid not in all_booking_ids
    )

    known_limit_events = [
        KnownLimitEvent(
            announced_minute=row["announced_minute"],
            announced_at=datetime.fromisoformat(row["announced_at"]),
            effective_minute=row["effective_minute"],
            effective_at=datetime.fromisoformat(row["effective_at"]),
            grid_input_kw=row["grid_input_kw"],
            cabinet_output_kw=dict(row["cabinet_output_kw"]),
        )
        for row in raw_physics_state["known_limit_events"]
    ]
    horizon_end = as_of + timedelta(minutes=horizon_minutes)
    horizon_end_minute = as_of_minute + horizon_minutes
    effective_grid_kw = raw_physics_state["effective_grid_limit_kw"]
    if effective_grid_kw is None:
        effective_grid_kw = float(raw_physics_state["available_power_kw"])

    manifest_body = {
        "schema_version": EVENT_MANIFEST_SCHEMA_VERSION,
        "station_id": station_id,
        "as_of": as_of.isoformat(),
        "as_of_minute": as_of_minute,
        "horizon_minutes": horizon_minutes,
        "horizon_end": horizon_end.isoformat(),
        "horizon_end_minute": horizon_end_minute,
        "known_booking_ids": known_booking_ids,
        "already_present_booking_ids": [vid for vid in present_ids if vid in known_set],
        "known_future_arrival_booking_ids": known_future_arrivals,
        "excluded_future_booking_count": excluded_future_bookings,
        "excluded_unbooked_not_arrived_count": excluded_unbooked_not_arrived,
        "known_limit_events": [ev.model_dump(mode="json") for ev in known_limit_events],
        "excluded_unannounced_limit_event_count": int(raw_physics_state["hidden_unannounced_limit_event_count"]),
        "active_faulted_connectors": list(raw_physics_state["faulted_connectors"]),
        "effective_grid_limit_kw_at_capture": float(effective_grid_kw),
        "assumptions": list(PROSPECTIVE_ASSUMPTIONS),
    }
    manifest_sha = canonical_sha256(manifest_body)
    manifest = EventManifest(
        schema_version=EVENT_MANIFEST_SCHEMA_VERSION,
        station_id=station_id,
        as_of=as_of,
        as_of_minute=as_of_minute,
        horizon_minutes=horizon_minutes,
        horizon_end=horizon_end,
        horizon_end_minute=horizon_end_minute,
        known_booking_ids=known_booking_ids,
        already_present_booking_ids=[vid for vid in present_ids if vid in known_set],
        known_future_arrival_booking_ids=known_future_arrivals,
        excluded_future_booking_count=excluded_future_bookings,
        excluded_unbooked_not_arrived_count=excluded_unbooked_not_arrived,
        known_limit_events=known_limit_events,
        excluded_unannounced_limit_event_count=int(raw_physics_state["hidden_unannounced_limit_event_count"]),
        active_faulted_connectors=list(raw_physics_state["faulted_connectors"]),
        effective_grid_limit_kw_at_capture=float(effective_grid_kw),
        assumptions=list(PROSPECTIVE_ASSUMPTIONS),
        manifest_sha256=manifest_sha,
    )
    return manifest, tuple(kept_bookings)


async def capture_atomic_snapshot(
    rt: StationRuntime,
    *,
    horizon_minutes: int = 120,
) -> CapturedSnapshot:
    """Capture an atomic, lock-free `CapturedSnapshot` at `rt.simulator.now` without mutating live state.

    Acquires `rt.booking_lock` -> `rt.decision_lock()` -> `rt._clock_lock` -> `rt.simulator.lock`
    only for the in-memory copy & digest calculation, then releases all locks before returning.
    """
    if horizon_minutes <= 0 or horizon_minutes > MAX_COUNTERFACTUAL_HORIZON_MINUTES:
        raise ValueError(f"horizon_minutes must be in 1..{MAX_COUNTERFACTUAL_HORIZON_MINUTES}")

    async with rt.booking_lock:
        async with rt.decision_lock():
            with rt._clock_lock:
                with rt.simulator.lock:
                    ordinary_outbox = rt.inspect_ordinary_outbox()
                    pending_safety = rt.inspect_pending_safety()
                    safety_holds = frozenset(rt.safety_hold_booking_ids)
                    rejected_ids = frozenset(rt.rejected_booking_ids)

                    booking_version = int(rt.booking_version)
                    plan_copy = rt.plan.model_copy(deep=True) if rt.plan is not None else None
                    plan_version = None if plan_copy is None else int(plan_copy.version)
                    station_config = rt.config.model_copy(deep=True)
                    tariff_copy = rt.tariff.model_copy(deep=True)
                    experiment = resolve_experiment(rt).model_copy(deep=True)

                    as_of = rt.simulator.now
                    sim_minute = int(rt.simulator.minute)
                    seed = rt.simulator.export_physics_seed()

                    active_bookings = [b.model_copy(deep=True) for b in rt.store.active_bookings()]
                    pending_approvals = tuple(
                        sorted(
                            (a.model_copy(deep=True) for a in rt.store.pending_approvals()),
                            key=lambda item: item.approval_id,
                        )
                    )
                    recent_commands = tuple(c.model_copy(deep=True) for c in rt.recent_commands)
                    acked_safety = tuple(rt._acknowledged_safety)
                    safety_attempts = int(rt._safety_attempts)

                    scheduler_name = rt.scheduler.name
                    scheduler_params = deepcopy(getattr(rt.scheduler, "parameters", None) or {})
                    scheduler_meta = deepcopy(getattr(rt.scheduler, "metadata", None) or {})

    # Outside all live locks: validate physical readiness and materialize known_at(T) on isolated probe.
    probe_station = HybridStation.from_physics_seed(station_config, seed)
    _check_capture_readiness(
        station_config=station_config,
        safety_hold_booking_ids=safety_holds,
        pending_safety=pending_safety,
        ordinary_outbox=ordinary_outbox,
        probe_station=probe_station,
    )
    raw_physics = probe_station.snapshot_physics_state()
    manifest, known_bookings = build_known_at_manifest(
        station_id=station_config.station_id,
        as_of=as_of,
        as_of_minute=sim_minute,
        horizon_minutes=horizon_minutes,
        active_bookings=active_bookings,
        raw_physics_state=raw_physics,
    )
    known_ids = frozenset(manifest.known_booking_ids)
    kept_ordinary_outbox = tuple(
        ev.model_copy(deep=True) for ev in ordinary_outbox if ev.booking_id is None or ev.booking_id in known_ids
    )
    clean_fork = HybridStation.from_physics_seed(station_config, seed)
    for b in known_bookings:
        if b.status in ACTIVE and b.booking_id not in clean_fork.queue.sessions:
            clean_fork.upsert_vehicle(visit_of(b, as_of))
    clean_fork._events.clear()
    clean_fork.enforce_known_at_on_fork(sim_minute, known_ids)
    clean_seed = clean_fork.export_physics_seed()
    clean_physics = clean_fork.snapshot_physics_state()

    snapshot_digest = _build_snapshot_digest_payload(
        station_id=station_config.station_id,
        as_of=as_of,
        sim_minute=sim_minute,
        booking_version=booking_version,
        plan_version=plan_version,
        state_version=int(clean_physics["state_version"]),
        schedule_version=int(clean_physics["schedule_version"]),
        experiment=experiment,
        station_config=station_config,
        tariff=tariff_copy,
        plan=plan_copy,
        known_bookings=known_bookings,
        pending_approvals=pending_approvals,
        recent_commands=recent_commands,
        safety_hold_booking_ids=safety_holds,
        rejected_booking_ids=rejected_ids,
        ordinary_outbox_events=kept_ordinary_outbox,
        event_manifest=manifest,
        physics_state=clean_physics,
    )

    envelope = SnapshotEnvelope(
        snapshot_id=f"snap-{uuid4().hex[:16]}",
        status=SnapshotStatus.READY,
        station_id=station_config.station_id,
        as_of=as_of,
        sim_minute=sim_minute,
        horizon_minutes=horizon_minutes,
        booking_version=booking_version,
        plan_version=plan_version,
        state_version=int(clean_physics["state_version"]),
        schedule_version=int(clean_physics["schedule_version"]),
        policy_id=experiment.policy_id,
        policy_version=experiment.policy_version,
        dc_charging_model_name=experiment.dc_charging_model.name,
        time_config=dict(experiment.time_config),
        station_config_sha256=experiment.station_config_sha256,
        tariff_sha256=experiment.tariff_sha256,
        experiment_fingerprint=experiment.fingerprint,
        event_manifest_sha256=manifest.manifest_sha256,
        stateful_components_sha256=str(clean_physics["stateful_components_sha256"]),
        snapshot_digest=snapshot_digest,
        known_booking_count=len(known_bookings),
        safety_hold_booking_ids=sorted(safety_holds),
        rejected_booking_ids=sorted(rejected_ids),
        pending_approval_ids=[a.approval_id for a in pending_approvals],
        recent_command_count=len(recent_commands),
        undelivered_ordinary_outbox_count=len(kept_ordinary_outbox),
    )

    return CapturedSnapshot(
        envelope=envelope,
        event_manifest=manifest,
        experiment=experiment,
        station_config=station_config,
        tariff=tariff_copy,
        plan=plan_copy,
        known_bookings=known_bookings,
        pending_approvals=pending_approvals,
        recent_commands=recent_commands,
        safety_hold_booking_ids=safety_holds,
        rejected_booking_ids=rejected_ids,
        ordinary_outbox_events=kept_ordinary_outbox,
        pending_safety_events=pending_safety,
        acknowledged_safety_ids=acked_safety,
        safety_attempts=safety_attempts,
        scheduler_name=scheduler_name,
        scheduler_parameters=_freeze_json_tree(scheduler_params),
        scheduler_metadata=_freeze_json_tree(scheduler_meta),
        physics_state=_freeze_json_tree(clean_physics),
        _physics_seed=clean_seed,
    )


def build_sandbox_runtime(snapshot: CapturedSnapshot) -> StationRuntime:
    """Materialize a completely isolated in-memory `StationRuntime` fork from `snapshot`.

    Uses no-op `DispatchSinks` and an in-memory `RuntimeStore` (`live=False`, zero DB/WS/file I/O).
    """
    fork_station = HybridStation.from_physics_seed(snapshot.station_config, snapshot._physics_seed)
    known_ids = frozenset(snapshot.event_manifest.known_booking_ids)
    fork_station.enforce_known_at_on_fork(snapshot.envelope.sim_minute, known_ids)

    params = _thaw_json_tree(snapshot.scheduler_parameters) or None
    scheduler = make_scheduler(
        snapshot.scheduler_name,
        lambda: fork_station,
        fork_station.kernel.algorithms,
        parameters=deepcopy(params),
    )
    scheduler.metadata = deepcopy(_thaw_json_tree(snapshot.scheduler_metadata))

    frt = _memory_runtime(
        fork_station,
        scheduler,
        fork_station.config,
        snapshot.tariff.model_copy(deep=True),
        bookings=[b.model_copy(deep=True) for b in snapshot.known_bookings],
        approvals=[a.model_copy(deep=True) for a in snapshot.pending_approvals],
    )
    frt.booking_version = snapshot.envelope.booking_version
    frt.plan = snapshot.plan.model_copy(deep=True) if snapshot.plan is not None else None
    frt.recent_commands.extend(c.model_copy(deep=True) for c in snapshot.recent_commands)
    frt.rejected_booking_ids.update(snapshot.rejected_booking_ids)
    frt.safety_hold_booking_ids.update(snapshot.safety_hold_booking_ids)
    with frt._clock_lock:
        frt._outbox.extend(ev.model_copy(deep=True) for ev in snapshot.ordinary_outbox_events)
        frt._pending_safety = {ev.event_id: ev.model_copy(deep=True) for ev in snapshot.pending_safety_events}
        frt._acknowledged_safety = deque(snapshot.acknowledged_safety_ids, maxlen=OUTBOX_MAX)
        frt._safety_attempts = snapshot.safety_attempts
    return frt
