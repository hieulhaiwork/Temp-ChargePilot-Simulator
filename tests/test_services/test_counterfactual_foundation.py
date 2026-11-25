"""Comprehensive Gate 3 (AI-4.2A) validation suite for Counterfactual Foundation (WP3.1–WP3.6)."""

import asyncio
import gc
import random
import threading
import types
from collections import deque
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

pytest.importorskip("ev2gym")

from src.db import session as db_session  # noqa: E402
from src.db.base import Base  # noqa: E402
from src.models.charging import (  # noqa: E402
    ChargeMode,
    ChargeRequest,
    ConsentScope,
    StrategyName,
)
from src.models.control import (  # noqa: E402
    Approval,
    ApprovalKind,
    Command,
    CommandSource,
    CommandType,
    GuardVerdict,
    Role,
)
from src.models.copilot import (  # noqa: E402
    ActorContext,
    SnapshotNotReadyReason,
    SnapshotStatus,
    VehicleOutcomeStatus,
    VehicleReleaseReason,
    WhyQuery,
    WhySubjectScope,
)
from src.models.events import EventType, StationEvent  # noqa: E402
from src.models.identity import UserRecord  # noqa: E402
from src.models.scheduling.observations import SocEstimate, estimated  # noqa: E402
from src.models.simulation import Incident, IncidentType  # noqa: E402
from src.models.simulation_core import LimitEvent  # noqa: E402
from src.services import catalog, charging_service, control_loop, realtime, repository, runtime  # noqa: E402
from src.services.copilot import (  # noqa: E402
    SandboxCancelledError,
    SnapshotNotReadyError,
    canonical_sha256,
    capture_atomic_snapshot,
    explain_why,
    non_timing_branch_signature,
    run_paired_noop,
    run_sandbox_branch,
)
from src.services.runtime import StationRuntime, build_sim_runtime, visit_of  # noqa: E402
from src.simulator.hybrid_station import HybridStation  # noqa: E402
from tests.factories import VN, booking  # noqa: E402


def _sim_runtime(
    strategy: StrategyName = StrategyName.SIM_M3A,
    *,
    dc_charging_model: str | None = None,
) -> StationRuntime:
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=VN)
    if dc_charging_model is not None:
        station = HybridStation(config, start, dc_charging_model=dc_charging_model)
        station.reset(scenario)
        scheduler = runtime.make_scheduler(strategy, lambda: station)
        return runtime._memory_runtime(station, scheduler, config, tariff)
    return build_sim_runtime(scenario, strategy, config, tariff, start)


class _WarmStartOptimizer:
    """Stateful optimizer wrapper recording visited minutes."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.history: list[int] = []

    def __call__(self, observation, zone, budget_kw):
        self.history.append(observation.minute)
        return self.inner(observation, zone, budget_kw)


class _CountingDCModel:
    """Stateful DC charging model wrapper counting queries."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.calls = 0

    def acceptance_kw(self, state):
        self.calls += 1
        return self.inner.acceptance_kw(state)

    def stored_kwh(self, state, setpoint_kw, interval_minutes, efficiency):
        self.calls += 1
        return self.inner.stored_kwh(state, setpoint_kw, interval_minutes, efficiency)


class _NoisyRngObservation:
    """Stateful RNG observation model."""

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)
        self.cache: dict[tuple[int, str], float] = {}

    def observe(self, minute: int, truth):
        rows = {}
        for vid, row in truth.items():
            key = (minute, vid)
            if key not in self.cache:
                self.cache[key] = min(1.0, max(0.0, row.soc + self.rng.uniform(-0.015, 0.015)))
            rows[vid] = estimated(row, SocEstimate(self.cache[key], measured_at=minute, uncertainty=0.015))
        return rows


# ---- 1. Atomic snapshot capture & barrier concurrency (WP3.1 / WP3.2) ------------------------


async def test_atomic_snapshot_capture_has_no_mixed_version_state_under_barriers():
    rt = _sim_runtime()
    b1 = booking("dc-1", zone="DC", kwh=25, hours=2.0, now=rt.clock())
    rt.store.save_booking(b1)
    rt.simulator.upsert_vehicle(visit_of(b1, rt.clock()))
    rt.booking_version = 1
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)

    writer_holding_booking_lock = asyncio.Event()
    capture_started = asyncio.Event()
    thread_barrier = threading.Barrier(2)

    async def writer_mutation() -> None:
        async with rt.booking_lock:
            writer_holding_booking_lock.set()
            await capture_started.wait()
            b2 = booking("ac-2", zone="AC", kwh=18, hours=4.0, now=rt.clock())
            rt.store.save_booking(b2)
            rt.simulator.upsert_vehicle(visit_of(b2, rt.clock()))
            rt.booking_version = 2
            await control_loop.on_event(
                StationEvent(type=EventType.BOOKING_CREATED, occurred_at=rt.clock(), booking_id=b2.booking_id),
                rt,
            )

    def off_thread_reader() -> None:
        thread_barrier.wait(timeout=5.0)
        rt.sync_clock()

    writer_task = asyncio.create_task(writer_mutation())
    await writer_holding_booking_lock.wait()

    reader_thread = threading.Thread(target=off_thread_reader, daemon=True)
    reader_thread.start()

    async def capture_coro():
        capture_started.set()
        thread_barrier.wait(timeout=5.0)
        return await capture_atomic_snapshot(rt, horizon_minutes=30)

    snap, _ = await asyncio.gather(capture_coro(), writer_task)
    reader_thread.join(timeout=5.0)

    # Writer held booking_lock first, so snapshot must observe complete post-commit state (never mixed v1/v2).
    assert snap.envelope.booking_version == 2
    assert snap.envelope.known_booking_count == 2
    assert sorted(b.booking_id for b in snap.known_bookings) == ["ac-2", "dc-1"]
    assert snap.plan is not None and snap.envelope.plan_version == snap.plan.version
    assert {s.booking_id for s in snap.plan.sessions} >= {"ac-2", "dc-1"}

    # Digest distinctions: snapshot_digest != experiment_fingerprint and sensitive to 1-minute physics step.
    assert snap.envelope.snapshot_digest != snap.envelope.experiment_fingerprint
    assert snap.recompute_digest() == snap.envelope.snapshot_digest
    adm_fp_before = rt.admission_fingerprint()
    rt.simulator.step(1)
    snap_after_step = await capture_atomic_snapshot(rt, horizon_minutes=30)
    assert rt.admission_fingerprint() == adm_fp_before  # admission_fingerprint ignores normal minute step
    assert snap_after_step.envelope.experiment_fingerprint == snap.envelope.experiment_fingerprint
    assert snap_after_step.envelope.snapshot_digest != snap.envelope.snapshot_digest


def test_snapshot_object_graph_contains_no_live_locks_db_loops_ws_or_actuators():
    async def _capture():
        rt = _sim_runtime(dc_charging_model="vinfast_profiles_v0_1")
        b = booking("dc-vf8", zone="DC", kwh=30, hours=2.0, now=rt.clock())
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
        await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
        return await capture_atomic_snapshot(rt, horizon_minutes=30)

    snap = asyncio.run(_capture())
    lock_types = (type(threading.Lock()), type(threading.RLock()), asyncio.Lock, asyncio.Semaphore)

    visited: set[int] = set()
    queue_objs: deque[object] = deque([snap])
    forbidden_hits: list[str] = []

    while queue_objs:
        cur = queue_objs.popleft()
        obj_id = id(cur)
        if obj_id in visited or isinstance(cur, (str, bytes, int, float, bool, type, type(None))):
            continue
        visited.add(obj_id)

        cls_mod = type(cur).__module__
        cls_name = f"{cls_mod}.{type(cur).__qualname__}"
        if isinstance(cur, lock_types):
            forbidden_hits.append(f"lock:{cls_name}")
        if isinstance(cur, asyncio.AbstractEventLoop):
            forbidden_hits.append(f"event_loop:{cls_name}")
        if isinstance(cur, HybridStation) or callable(getattr(cur, "apply_commands", None)):
            forbidden_hits.append(f"actuator:{cls_name}")
        if cls_mod.startswith(("sqlalchemy", "sqlite3", "psycopg", "asyncpg", "fastapi.websockets")):
            forbidden_hits.append(f"db_or_ws:{cls_name}")
        if cls_name.endswith(("DispatchSinks", "RuntimeStore", "ConnectionManager")):
            forbidden_hits.append(f"runtime_handle:{cls_name}")

        for ref in gc.get_referents(cur):
            if isinstance(ref, (type, types.ModuleType, types.FunctionType, types.MethodType)):
                continue
            queue_objs.append(ref)

    assert forbidden_hits == []


# ---- 2 & 3. Paired no-op parity, interleaved & stateful component isolation (WP3.4) -----------


async def test_paired_noop_branches_produce_identical_non_timing_kpis_and_ledgers():
    rt = _sim_runtime(dc_charging_model="vinfast_profiles_v0_1")
    for item in (
        booking("dc-1", zone="DC", kwh=28, hours=1.5, now=rt.clock()),
        booking("dc-2", zone="DC", kwh=22, hours=2.0, now=rt.clock()),
        booking("ac-1", zone="AC", kwh=16, hours=3.0, now=rt.clock()),
    ):
        rt.store.save_booking(item)
        rt.simulator.upsert_vehicle(visit_of(item, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)

    snap = await capture_atomic_snapshot(rt, horizon_minutes=45)
    paired = await run_paired_noop(snap)

    assert paired.applied is False
    assert paired.non_timing_kpis_equal is True
    assert paired.final_physics_digests_equal is True
    assert paired.baseline.initial_snapshot_digest == snap.envelope.snapshot_digest
    assert paired.counterfactual.initial_snapshot_digest == snap.envelope.snapshot_digest
    assert paired.baseline.event_manifest_sha256 == snap.event_manifest.manifest_sha256
    assert paired.counterfactual.event_manifest_sha256 == snap.event_manifest.manifest_sha256
    assert paired.baseline.experiment_fingerprint == snap.envelope.experiment_fingerprint
    assert paired.baseline.outcome_ledger.model_dump(mode="json") == (
        paired.counterfactual.outcome_ledger.model_dump(mode="json")
    )


async def test_sandbox_forks_are_independent_under_interleaved_and_repeated_stateful_runs():
    rt = _sim_runtime()
    base_alg = rt.scheduler.algorithms()
    warm_opt = _WarmStartOptimizer(base_alg.optimizers["DC"])
    counting_dc = _CountingDCModel(rt.simulator.adapter.dc_model)
    noisy_obs = _NoisyRngObservation(seed=99)

    rt.simulator.adapter.dc_model = counting_dc
    rt.simulator._dc_model = counting_dc
    rt.simulator.kernel.observation_model = noisy_obs
    rt.simulator._observation_model = noisy_obs
    custom_alg = replace(
        base_alg,
        optimizers={"AC": base_alg.optimizers["AC"], "DC": warm_opt},
        dc_charging_model=counting_dc,
    )
    rt.scheduler._algorithms = custom_alg
    rt.scheduler.configure(rt.simulator)

    for item in (
        booking("dc-s1", zone="DC", kwh=24, hours=1.5, now=rt.clock()),
        booking("ac-s1", zone="AC", kwh=12, hours=2.5, now=rt.clock()),
    ):
        rt.store.save_booking(item)
        rt.simulator.upsert_vehicle(visit_of(item, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)

    live_opt_history = list(warm_opt.history)
    live_dc_calls = counting_dc.calls
    live_rng_state = noisy_obs.rng.getstate()
    live_rng_cache = dict(noisy_obs.cache)

    snap = await capture_atomic_snapshot(rt, horizon_minutes=30)

    # Interleaved concurrent paired execution + third repeated run from the exact same snapshot.
    step_trace: list[tuple[str, int]] = []

    async def record_step(label: str, minute: int) -> None:
        step_trace.append((label, minute))
        await asyncio.sleep(0)

    b1, b2 = await asyncio.gather(
        run_sandbox_branch(snap, branch_label="baseline", step_hook=record_step),
        run_sandbox_branch(snap, branch_label="counterfactual", step_hook=record_step),
    )
    b3 = await run_sandbox_branch(snap, branch_label="repeat")

    # Verify interleaving actually occurred (not all baseline before counterfactual).
    labels_seen = [lbl for lbl, _ in step_trace]
    first_cf = labels_seen.index("counterfactual")
    last_base = len(labels_seen) - 1 - labels_seen[::-1].index("baseline")
    assert first_cf < last_base

    assert non_timing_branch_signature(b1) == non_timing_branch_signature(b2)
    assert non_timing_branch_signature(b1) == non_timing_branch_signature(b3)

    # Live stateful components remained 100% untouched!
    assert warm_opt.history == live_opt_history
    assert counting_dc.calls == live_dc_calls
    assert noisy_obs.rng.getstate() == live_rng_state
    assert noisy_obs.cache == live_rng_cache


# ---- 4, 5 & 6. Immutability of snapshot & live state + zero DB/WS/FS side effects -----------


async def test_rollout_never_mutates_snapshot_digest_or_paused_live_runtime_state():
    rt = _sim_runtime()
    b = booking("dc-live", zone="DC", kwh=25, hours=2.0, now=rt.clock())
    rt.store.save_booking(b)
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    rt.simulator.step(5)

    live_phys_before = canonical_sha256(rt.simulator.snapshot_physics_state())
    live_plan_before = rt.plan.model_dump(mode="json") if rt.plan else None
    live_traces_before = len(rt.recorder.decision_traces)

    snap = await capture_atomic_snapshot(rt, horizon_minutes=60)
    snap_digest_before = snap.envelope.snapshot_digest
    assert snap.recompute_digest() == snap_digest_before

    paired = await run_paired_noop(snap, interleaved=True)
    assert paired.non_timing_kpis_equal is True

    assert snap.envelope.snapshot_digest == snap_digest_before
    assert snap.recompute_digest() == snap_digest_before
    assert canonical_sha256(rt.simulator.snapshot_physics_state()) == live_phys_before
    assert (rt.plan.model_dump(mode="json") if rt.plan else None) == live_plan_before
    assert len(rt.recorder.decision_traces) == live_traces_before


async def test_sandbox_rollout_has_zero_db_ws_actuator_or_filesystem_side_effects(monkeypatch, clean_db, tmp_path):
    t0 = datetime(2026, 11, 23, 18, 0, tzinfo=VN)
    monkeypatch.setattr(runtime, "_live_clock", lambda config: lambda: t0)
    runtime.reset_runtime()
    repository.upsert_user(
        UserRecord(
            user_id="res-db",
            email="res-db@example.invalid",
            role=Role.RESIDENT,
            display_name="Resident DB",
            created_at=t0,
        )
    )
    live = runtime.get_runtime()
    await charging_service.book(
        ChargeRequest(
            vehicle_model="VF8_NEW_2026",
            soc_now=25,
            soc_target=80,
            deadline=t0 + timedelta(hours=3),
            mode=ChargeMode.WALK_IN,
            zone="DC",
        ),
        "res-db",
    )

    def _table_counts() -> dict[str, int]:
        with db_session.session_scope() as s:
            return {
                tbl.name: int(s.execute(select(func.count()).select_from(tbl)).scalar_one())
                for tbl in Base.metadata.sorted_tables
            }

    ws_calls: list = []
    live_apply_calls: list = []

    async def _spy_broadcast(*args, **kwargs):
        ws_calls.append((args, kwargs))

    orig_apply = getattr(live.simulator, "apply_commands")

    def _spy_apply(commands):
        live_apply_calls.append(commands)
        return orig_apply(commands)

    conn_id_op = realtime.register(_spy_broadcast, Role.OPERATOR, "op-ws")
    conn_id_res = realtime.register(_spy_broadcast, Role.RESIDENT, "res-db")
    monkeypatch.setattr(realtime, "broadcast", _spy_broadcast)
    monkeypatch.setattr(live.simulator, "apply_commands", _spy_apply)

    counts_before = _table_counts()
    live_phys_before = canonical_sha256(live.simulator.snapshot_physics_state())

    snap = await capture_atomic_snapshot(live, horizon_minutes=45)

    import builtins

    real_open = builtins.open
    fs_opens: list[tuple[str, str]] = []

    def _spy_open(file, mode="r", *args, **kwargs):
        if any(flag in str(mode) for flag in ("w", "a", "x", "+")):
            fs_opens.append((str(file), str(mode)))
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _spy_open)
    try:
        paired = await run_paired_noop(snap)
    finally:
        realtime.unregister(conn_id_op)
        realtime.unregister(conn_id_res)

    assert paired.non_timing_kpis_equal is True
    assert _table_counts() == counts_before
    assert ws_calls == []
    assert live_apply_calls == []
    assert fs_opens == []
    assert canonical_sha256(live.simulator.snapshot_physics_state()) == live_phys_before


# ---- 7 & 8. Safety Hold / approval / consent parity & not_ready safety guard -----------------


async def test_safety_hold_pending_approval_and_rejected_consent_parity_in_forks():
    rt = _sim_runtime()
    b_hold = booking("dc-hold", zone="DC", kwh=30, hours=2.0, now=rt.clock())
    b_ok = booking("dc-ok", zone="DC", kwh=25, hours=2.0, now=rt.clock())
    b_pend = booking(
        "ac-pend",
        zone="AC",
        kwh=15,
        hours=4.0,
        now=rt.clock(),
    ).model_copy(update={"consent": ConsentScope(allow_power_reduction=False)})
    b_rej = booking(
        "ac-rej",
        zone="AC",
        kwh=15,
        hours=4.0,
        now=rt.clock(),
    ).model_copy(update={"consent": ConsentScope(allow_power_reduction=False)})

    for b in (b_hold, b_ok, b_pend, b_rej):
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))

    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)

    # Put dc-hold under Safety Hold with safe 0 kW held setpoint (resolved emergency state).
    rt.safety_hold_booking_ids.add("dc-hold")
    with rt.simulator.lock:
        rt.simulator.kernel.hold_setpoint("dc-hold", 0.0)

    # Open a pending approval for ac-pend and mark ac-rej as rejected consent.
    now = rt.clock()
    cmd = Command(
        type=CommandType.SET_POWER,
        connector_id="AC-01-1",
        power_kw=5.0,
        booking_id="ac-pend",
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=rt.plan.version if rt.plan else 1,
        based_on_state_at=now,
        created_at=now,
    )
    pending = Approval(
        kind=ApprovalKind.RESIDENT_CONSENT,
        command=cmd,
        verdict=GuardVerdict(command_id=cmd.command_id, passed=True, checked_at=now),
        requested_from=b_pend.resident_id,
        impact_summary="Reduce power",
        created_at=now,
    )
    rt.sinks.save_approval(pending)
    rt.rejected_booking_ids.add("ac-rej")

    snap = await capture_atomic_snapshot(rt, horizon_minutes=30)
    assert snap.envelope.status == SnapshotStatus.READY
    assert snap.envelope.safety_hold_booking_ids == ["dc-hold"]
    assert snap.envelope.rejected_booking_ids == ["ac-rej"]
    assert snap.envelope.pending_approval_ids == [pending.approval_id]

    paired = await run_paired_noop(snap)
    assert paired.non_timing_kpis_equal is True
    assert paired.baseline.safety_hold_booking_ids_end == ["dc-hold"]
    assert paired.counterfactual.safety_hold_booking_ids_end == ["dc-hold"]

    by_id = {v.booking_id: v for v in paired.baseline.outcome_ledger.vehicles}
    assert by_id["dc-hold"].horizon_output_kwh == 0.0
    assert by_id["dc-ok"].horizon_output_kwh > 0.0


async def test_unresolved_hard_safety_or_unsafe_allocation_blocks_snapshot_without_mutating_live():
    rt = _sim_runtime()
    b = booking("dc-1", zone="DC", kwh=25, hours=2.0, now=rt.clock())
    rt.store.save_booking(b)
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)

    # Case A: Unresolved HARD_LIMIT_VIOLATED + ordinary event in outbox + existing Safety Hold.
    rt.safety_hold_booking_ids.add("existing-hold")
    tick_ev = StationEvent(event_id="ord-tick", type=EventType.TICK, occurred_at=rt.clock())
    hard_ev = StationEvent(
        event_id="hard-unres",
        type=EventType.HARD_LIMIT_VIOLATED,
        occurred_at=rt.clock(),
        detail="Grid overload",
        violation_kinds=["aggregate_power"],
    )
    rt.queue_events([tick_ev, hard_ev])
    min_before = rt.simulator.minute

    with pytest.raises(SnapshotNotReadyError) as exc_info:
        await capture_atomic_snapshot(rt, horizon_minutes=30)
    assert exc_info.value.status == SnapshotStatus.NOT_READY
    assert exc_info.value.reason == SnapshotNotReadyReason.UNRESOLVED_HARD_SAFETY_EVENT

    # Live state was NOT stepped, Safety Hold NOT released, and outbox events NOT dropped!
    assert rt.simulator.minute == min_before
    assert rt.has_pending_safety() is True
    assert [e.event_id for e in rt.inspect_ordinary_outbox()] == ["ord-tick"]
    assert "existing-hold" in rt.safety_hold_booking_ids

    # Case B: Clear pending safety, but force an unsafe physical state (setpoint > lowered grid cap).
    rt.acknowledge_safety([hard_ev])
    rt.safety_hold_booking_ids.clear()
    with rt.simulator.lock:
        rt.simulator.available_power_kw = 5.0  # dc-1 is holding > 5 kW setpoint before curtailment!

    with pytest.raises(SnapshotNotReadyError) as exc_unsafe:
        await capture_atomic_snapshot(rt, horizon_minutes=30)
    assert exc_unsafe.value.reason == SnapshotNotReadyReason.UNSAFE_PHYSICAL_STATE
    assert rt.simulator.minute == min_before
    assert [e.event_id for e in rt.inspect_ordinary_outbox()] == ["ord-tick"]


# ---- 9. Prospective known_at(T) manifest vs hidden future ground truth (WP3.3) ----------------


async def test_known_at_t_manifest_excludes_hidden_future_arrivals_and_unannounced_limit_events():
    rt = _sim_runtime()
    t0 = rt.clock()

    b_now = booking("dc-now", zone="DC", kwh=30, hours=2.0, now=t0).model_copy(
        update={"created_at": t0 - timedelta(minutes=10)}
    )
    b_res_known = booking(
        "dc-res-known",
        zone="DC",
        kwh=20,
        hours=2.0,
        now=t0,
        arrival=t0 + timedelta(minutes=10),
    ).model_copy(update={"created_at": t0 - timedelta(minutes=5)})
    b_future_hidden = booking(
        "dc-future-hidden",
        zone="DC",
        kwh=20,
        hours=2.0,
        now=t0,
        arrival=t0 + timedelta(minutes=15),
    ).model_copy(update={"created_at": t0 + timedelta(minutes=12)})

    for b in (b_now, b_res_known, b_future_hidden):
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, t0))

    # Also inject an unbooked NOT_ARRIVED scenario vehicle directly into simulator queue
    unbooked_b = booking(
        "ac-unbooked-hidden",
        zone="AC",
        kwh=15,
        hours=2.0,
        now=t0,
        arrival=t0 + timedelta(minutes=8),
    )
    rt.simulator.upsert_vehicle(visit_of(unbooked_b, t0))

    # Inject one announced LimitEvent (announced at minute 0 -> 45 kW at minute 10)
    # and one unannounced future LimitEvent (announced at minute 15 -> 8 kW at minute 20).
    with rt.simulator.lock:
        ev_known = LimitEvent(effective_minute=10, announced_minute=0, grid_input_kw=45.0, cabinet_output_kw={})
        ev_hidden = LimitEvent(effective_minute=20, announced_minute=15, grid_input_kw=8.0, cabinet_output_kw={})
        rt.simulator.kernel.scenario = replace(
            rt.simulator.kernel.scenario,
            limit_events=(ev_known, ev_hidden),
        )
        # Clear override so scenario limit_events govern grid_input_kw
        rt.simulator.kernel.grid_input_override_kw = None

    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t0), rt)

    snap = await capture_atomic_snapshot(rt, horizon_minutes=30)
    manifest = snap.event_manifest
    assert manifest.known_booking_ids == ["dc-now", "dc-res-known"]
    assert manifest.already_present_booking_ids == ["dc-now"]
    assert manifest.known_future_arrival_booking_ids == ["dc-res-known"]
    assert manifest.excluded_future_booking_count == 1
    assert manifest.excluded_unbooked_not_arrived_count == 1
    assert len(manifest.known_limit_events) == 1
    assert manifest.known_limit_events[0].grid_input_kw == 45.0
    assert manifest.excluded_unannounced_limit_event_count == 1

    branch = await run_sandbox_branch(snap, branch_label="baseline")
    ledger_ids = [v.booking_id for v in branch.outcome_ledger.vehicles]
    assert ledger_ids == ["dc-now", "dc-res-known"]
    by_id = {v.booking_id: v for v in branch.outcome_ledger.vehicles}
    assert by_id["dc-res-known"].arrived_at == t0 + timedelta(minutes=10)
    assert by_id["dc-res-known"].horizon_output_kwh > 0.0
    # Unannounced 8 kW drop at minute 20 was excluded, so peak/actual grid power stayed governed by 45 kW (not 8 kW),
    # and zero sampled over-limit violations occurred.
    assert branch.outcome_ledger.horizon_sampled_grid_over_limit_minutes == 0


# ---- 10 & 11. Timeout, cancellation & live replan non-starvation (WP3.4 / WP3.6) -------------


async def test_timeout_and_cancellation_leave_zero_live_or_snapshot_mutation():
    rt = _sim_runtime()
    b = booking("dc-cancel", zone="DC", kwh=30, hours=2.0, now=rt.clock())
    rt.store.save_booking(b)
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)

    live_digest_before = canonical_sha256(rt.simulator.snapshot_physics_state())
    snap = await capture_atomic_snapshot(rt, horizon_minutes=60)
    snap_digest_before = snap.envelope.snapshot_digest

    # 1. Explicit cancel_event mid-rollout at minute 5
    cancel_ev = asyncio.Event()

    def trigger_cancel(_label: str, minute: int) -> None:
        if minute >= 5:
            cancel_ev.set()

    with pytest.raises(SandboxCancelledError):
        await run_sandbox_branch(snap, cancel_event=cancel_ev, step_hook=trigger_cancel)

    # 2. Strict timeout via slow step_hook
    async def slow_step(_label: str, _minute: int) -> None:
        await asyncio.sleep(0.05)

    with pytest.raises(TimeoutError):
        await run_sandbox_branch(snap, timeout_s=0.01, step_hook=slow_step)

    # 3. Task cancellation (`asyncio.CancelledError`)
    entered = asyncio.Event()

    async def pause_at_step(_label: str, minute: int) -> None:
        if minute >= 3:
            entered.set()
            await asyncio.sleep(10.0)

    task = asyncio.create_task(run_sandbox_branch(snap, step_hook=pause_at_step))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert canonical_sha256(rt.simulator.snapshot_physics_state()) == live_digest_before
    assert snap.recompute_digest() == snap_digest_before


@pytest.mark.parametrize("enable_busy_probe", [False, True])
async def test_live_replan_is_not_starved_by_concurrent_sandbox_workload(enable_busy_probe):
    live_rt = _sim_runtime()
    for b in (
        booking("dc-a", zone="DC", kwh=30, hours=2.0, now=live_rt.clock()),
        booking("ac-a", zone="AC", kwh=20, hours=4.0, now=live_rt.clock()),
    ):
        live_rt.store.save_booking(b)
        live_rt.simulator.upsert_vehicle(visit_of(b, live_rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=live_rt.clock()), live_rt)
    plan_v_before = live_rt.plan.version if live_rt.plan else 0

    snap = await capture_atomic_snapshot(live_rt, horizon_minutes=120)
    sandbox_in_flight = asyncio.Event()

    def notify_in_flight(_label: str, minute: int) -> None:
        if minute >= 5:
            sandbox_in_flight.set()

    def is_live_busy():
        return live_rt.lock.locked() or live_rt.has_pending_safety()

    live_busy = is_live_busy if enable_busy_probe else None
    sb_a = asyncio.create_task(
        run_sandbox_branch(snap, branch_label="baseline", step_hook=notify_in_flight, live_busy_probe=live_busy)
    )
    sb_b = asyncio.create_task(run_sandbox_branch(snap, branch_label="counterfactual", live_busy_probe=live_busy))

    await sandbox_in_flight.wait()
    t_start = asyncio.get_running_loop().time()
    new_plan = await control_loop.on_event(
        StationEvent(type=EventType.TICK, occurred_at=live_rt.clock()),
        live_rt,
    )
    live_latency_s = asyncio.get_running_loop().time() - t_start

    res_a, res_b = await asyncio.gather(sb_a, sb_b)
    assert new_plan.version > plan_v_before
    assert live_latency_s < 1.5  # MT5 p95 budget <= 2.0 s
    assert non_timing_branch_signature(res_a) == non_timing_branch_signature(res_b)


# ---- 12. Hand-calculable Outcome Ledger oracle fixtures (WP3.5 / WP3.6) -----------------------


async def test_outcome_ledger_hand_calculated_oracle_energy_and_timestamps():
    """Verify exact pre- vs post-snapshot kWh, plug-in vs first-charge, and completion vs DC unplug."""
    rt = _sim_runtime(StrategyName.SIM_B0)
    t0 = rt.clock()

    # 1) ac-pre arrives at T0 and charges for 10 minutes BEFORE snapshot capture at T0+10m.
    b_ac = booking("ac-pre", zone="AC", kwh=22, hours=4.0, now=t0)
    rt.store.save_booking(b_ac)
    rt.simulator.upsert_vehicle(visit_of(b_ac, t0))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t0), rt)
    for _ in range(10):
        ev = rt.simulator.step(1)
        await control_loop.on_minute(rt, ev)

    t_snap = rt.simulator.now
    assert t_snap == t0 + timedelta(minutes=10)
    pre_phys = rt.simulator.snapshot_physics_state()["sessions"]["ac-pre"]
    expected_pre_out = pre_phys["output_kwh"]
    expected_pre_bat = pre_phys["delivered_battery_kwh"]
    expected_pre_grid = pre_phys["delivered_grid_kwh"]
    assert expected_pre_out > 0.0

    # 2) At T_snap, add:
    #    - dc-quick: needs small energy (~5 kWh) with deadline T_snap + 90m -> finishes early and unplugs after
    #      dc_unplug_delay_minutes (5 minutes in station.yaml), strictly BEFORE declared deadline!
    #    - ac-delayed-charge: assigned connector at T_snap, but we place a pending approval holding SET_POWER so
    #      it plugs in at T_snap with 0 kW, demonstrating plug_in_at != first_charge_at (first_charge_at is None)!
    b_dc_quick = ChargeRequest(
        vehicle_model="VF3",
        soc_now=70,
        soc_target=80,
        deadline=t_snap + timedelta(minutes=90),
        mode=ChargeMode.WALK_IN,
        zone="DC",
    )
    from src.services import energy as energy_svc

    spec_vf3 = catalog.get_vehicle("VF3")
    dc_est = energy_svc.estimate_energy(spec_vf3, soc_now=70, soc_target=80)
    bk_dc = booking("dc-quick", zone="DC", kwh=dc_est.grid_energy_kwh, hours=1.5, now=t_snap).model_copy(
        update={
            "request": b_dc_quick,
            "energy": dc_est,
            "max_charge_power_kw": min(60.0, spec_vf3.max_dc_kw or 60.0),
            "created_at": t_snap,
        }
    )

    bk_ac_zero = booking("ac-plug-only", zone="AC", kwh=15, hours=3.0, now=t_snap).model_copy(
        update={"created_at": t_snap}
    )
    for b in (bk_dc, bk_ac_zero):
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, t_snap))

    # Assign ac-plug-only a connector with 0 kW held and put a pending approval on it so SET_POWER > 0 is held!
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t_snap), rt)
    ac_conn = next(c.connector_id for c in rt.simulator.state().connectors if c.booking_id == "ac-plug-only")
    with rt.simulator.lock:
        rt.simulator.kernel.hold_setpoint("ac-plug-only", 0.0)
    hold_cmd = Command(
        type=CommandType.SET_POWER,
        connector_id=ac_conn,
        power_kw=7.0,
        booking_id="ac-plug-only",
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=rt.plan.version if rt.plan else 1,
        based_on_state_at=t_snap,
        created_at=t_snap,
    )
    rt.sinks.save_approval(
        Approval(
            kind=ApprovalKind.RESIDENT_CONSENT,
            command=hold_cmd,
            verdict=GuardVerdict(command_id=hold_cmd.command_id, passed=True, checked_at=t_snap),
            requested_from=bk_ac_zero.resident_id,
            impact_summary="Hold power",
            created_at=t_snap,
        )
    )

    snap = await capture_atomic_snapshot(rt, horizon_minutes=40)
    res = await run_sandbox_branch(snap)
    ledger = res.outcome_ledger
    by_id = {v.booking_id: v for v in ledger.vehicles}

    # Verify no pre-snapshot double counting on ac-pre (11 kW for 10 min pre-snapshot, 40 min post-snapshot):
    rec_ac = by_id["ac-pre"]
    assert rec_ac.pre_snapshot_output_kwh == pytest.approx(11.0 * 10 / 60.0, abs=1e-5)
    assert rec_ac.horizon_output_kwh == pytest.approx(11.0 * 40 / 60.0, abs=1e-5)
    assert rec_ac.cumulative_output_kwh == pytest.approx(11.0 * 50 / 60.0, abs=1e-5)
    assert rec_ac.pre_snapshot_output_kwh == pytest.approx(expected_pre_out, abs=1e-6)
    assert rec_ac.pre_snapshot_battery_stored_kwh == pytest.approx(expected_pre_bat, abs=1e-6)
    assert rec_ac.pre_snapshot_grid_input_kwh == pytest.approx(expected_pre_grid, abs=1e-6)
    assert rec_ac.cumulative_output_kwh == pytest.approx(
        rec_ac.pre_snapshot_output_kwh + rec_ac.horizon_output_kwh, abs=2e-6
    )
    assert rec_ac.horizon_grid_input_kwh == pytest.approx(
        rec_ac.horizon_output_kwh / rt.config.power_conversion_efficiency, abs=1e-5
    )

    # Verify plug_in_at vs first_charge_at separation on ac-plug-only:
    rec_plug_only = by_id["ac-plug-only"]
    assert rec_plug_only.plug_in_at is not None
    assert rec_plug_only.first_charge_at is None
    assert rec_plug_only.horizon_output_kwh == 0.0

    # Verify target_reached_at vs release_or_departure_at (DC unplug delay) on dc-quick:
    rec_dc = by_id["dc-quick"]
    assert rec_dc.status == VehicleOutcomeStatus.COMPLETED_ON_TIME
    assert rec_dc.target_reached_at is not None
    assert rec_dc.release_or_departure_at is not None
    expected_delay = timedelta(minutes=rt.config.dc_unplug_delay_minutes)
    assert rec_dc.release_or_departure_at == rec_dc.target_reached_at + expected_delay
    assert rec_dc.release_or_departure_at < rec_dc.original_deadline
    assert rec_dc.release_reason == VehicleReleaseReason.DC_UNPLUG_DELAY


async def test_outcome_ledger_censoring_not_arrived_unserved_and_empty_sla_denominator():
    """Verify NOT_ARRIVED preservation, censoring, unserved sessions, and None (never 1.0) on empty denominators."""
    # Case 1: Empty cohort (0 bookings) -> on_time_rate and service_coverage_rate MUST be None (not 1.0!)
    rt_empty = _sim_runtime()
    snap_empty = await capture_atomic_snapshot(rt_empty, horizon_minutes=15)
    res_empty = await run_sandbox_branch(snap_empty)
    led_empty = res_empty.outcome_ledger
    assert led_empty.cohort_size == 0
    assert led_empty.sla_denominator == 0
    assert led_empty.on_time_rate is None
    assert led_empty.energy_bound_on_time_rate is None
    assert led_empty.service_coverage_rate is None
    assert led_empty.by_zone["AC"].on_time_rate is None
    assert led_empty.by_zone["DC"].on_time_rate is None

    # Case 2: 2-vehicle cohort where BOTH have deadline > horizon_end (one NOT_ARRIVED, one CHARGING) ->
    # sla_denominator == 0 -> on_time_rate is None, NOT_ARRIVED preserved in cohort!
    rt_cens = _sim_runtime()
    t0 = rt_cens.clock()
    b_not_arrived = booking(
        "res-later",
        zone="DC",
        kwh=25,
        hours=3.0,
        now=t0,
        arrival=t0 + timedelta(minutes=60),
    )
    b_in_prog = booking("ac-long", zone="AC", kwh=45, hours=8.0, now=t0)
    for b in (b_not_arrived, b_in_prog):
        rt_cens.store.save_booking(b)
        rt_cens.simulator.upsert_vehicle(visit_of(b, t0))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t0), rt_cens)

    snap_cens = await capture_atomic_snapshot(rt_cens, horizon_minutes=20)
    led_cens = (await run_sandbox_branch(snap_cens)).outcome_ledger
    assert led_cens.cohort_size == 2
    assert led_cens.arrived_count == 1
    assert led_cens.not_arrived_count == 1
    assert led_cens.censored_count == 2
    assert led_cens.censored_not_arrived_count == 1
    assert led_cens.censored_in_progress_count == 1
    assert led_cens.sla_denominator == 0
    assert led_cens.on_time_rate is None
    assert led_cens.energy_bound_on_time_rate is None

    # Case 3: Unserved session (all DC connectors faulted before arrival, deadline within horizon) ->
    # UNSERVED_DEPARTED_OR_EXPIRED, sla_denominator == 1, on_time_rate == 0.0!
    rt_unserved = _sim_runtime()
    t_u = rt_unserved.clock()
    for conn in rt_unserved.config.connectors:
        if str(conn.zone) == "DC":
            rt_unserved.simulator.inject_incident(
                Incident(type=IncidentType.CONNECTOR_FAULT, connector_id=conn.connector_id)
            )
    b_unserved = booking("dc-unserved", zone="DC", kwh=20, hours=0.5, now=t_u)
    rt_unserved.store.save_booking(b_unserved)
    rt_unserved.simulator.upsert_vehicle(visit_of(b_unserved, t_u))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t_u), rt_unserved)

    snap_unserved = await capture_atomic_snapshot(rt_unserved, horizon_minutes=35)
    led_unserved = (await run_sandbox_branch(snap_unserved)).outcome_ledger
    assert led_unserved.cohort_size == 1
    assert led_unserved.unserved_count == 1
    assert led_unserved.sla_denominator == 1
    assert led_unserved.sla_met_count == 0
    assert led_unserved.on_time_rate == 0.0
    assert led_unserved.vehicles[0].status == VehicleOutcomeStatus.UNSERVED_DEPARTED_OR_EXPIRED
    assert led_unserved.vehicles[0].unserved is True
    assert led_unserved.vehicles[0].met_original_sla is False
    # Verify retrospective WHY Engine still works cleanly alongside Counterfactual Foundation
    why_ans = explain_why(
        WhyQuery(subject_scope=WhySubjectScope.STATION, topic="overview", at=t_u),
        ActorContext(actor_id="op-1", role=Role.OPERATOR, station_id=rt_unserved.config.station_id),
        raw_traces=rt_unserved.recorder.decision_traces,
    )
    assert why_ans.topic == "overview"


async def test_undelivered_ordinary_outbox_events_are_replayed_in_both_forks_without_draining_live():
    """Ordinary outbox events pending at T are captured atomically, kept on live, and replayed on both forks."""
    rt = _sim_runtime()
    t0 = rt.clock()
    b1 = booking("dc-1", zone="DC", kwh=30, hours=2.0, now=t0)
    rt.store.save_booking(b1)
    rt.simulator.upsert_vehicle(visit_of(b1, t0))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t0), rt)

    # Advance 3 minutes (not a 15-min boundary), then arrive a walk-in whose event sits in ordinary outbox.
    rt.simulator.step(3)
    t3 = rt.simulator.now
    b2 = booking("dc-2", zone="DC", kwh=20, hours=2.0, now=t3)
    rt.store.save_booking(b2)
    arr_events = rt.simulator.upsert_vehicle(visit_of(b2, t3))
    arr_events.append(
        StationEvent(event_id="ord-b2-created", type=EventType.BOOKING_CREATED, occurred_at=t3, booking_id="dc-2")
    )
    rt.queue_events(arr_events)

    live_outbox_ids = [e.event_id for e in rt.inspect_ordinary_outbox()]
    assert "ord-b2-created" in live_outbox_ids

    snap = await capture_atomic_snapshot(rt, horizon_minutes=20)
    assert snap.envelope.undelivered_ordinary_outbox_count == len(live_outbox_ids)
    # Live outbox was NOT drained!
    assert [e.event_id for e in rt.inspect_ordinary_outbox()] == live_outbox_ids

    paired = await run_paired_noop(snap)
    assert paired.non_timing_kpis_equal is True
    by_id = {v.booking_id: v for v in paired.baseline.outcome_ledger.vehicles}
    # Because ordinary outbox was replayed at minute 0 (t3), dc-2 got assigned immediately at t3 (0 min wait)
    # instead of waiting 12 minutes until the next 15-min periodic boundary!
    assert by_id["dc-2"].plug_in_at == t3
    assert by_id["dc-2"].plug_wait_minutes == 0.0


@pytest.mark.parametrize("horizon, blocked", [(1, True), (3, True), (3, False)])
async def test_rollout_handles_hard_safety_before_advancing_or_returning(monkeypatch, horizon, blocked):
    rt = _sim_runtime()
    snap = await capture_atomic_snapshot(rt, horizon_minutes=horizon)
    initial_minute = rt.simulator.minute
    hard_id = "g3-injected-hard"
    original_step = HybridStation.step
    steps = []

    def step(station, minutes):
        events = original_step(station, minutes)
        steps.append(station.minute)
        if station.minute == initial_minute + 1:
            events.append(
                StationEvent(
                    event_id=hard_id,
                    type=EventType.HARD_LIMIT_VIOLATED,
                    occurred_at=station.now,
                    violation_kinds=[] if blocked else ["aggregate_power"],
                )
            )
        return events

    monkeypatch.setattr(HybridStation, "step", step)
    result = await run_sandbox_branch(snap)
    assert len(steps) == (1 if blocked else horizon)
    assert result.status == ("unresolved_safety" if blocked else "completed")
    assert result.unresolved_safety_count == int(blocked)
    assert result.outcome_ledger.horizon_hard_safety_event_count == 1


@pytest.mark.parametrize("field", ["manifest", "booking", "config", "plan", "scheduler", "physics"])
async def test_snapshot_rejects_altered_branch_inputs(field):
    from src.services.copilot.snapshot import build_sandbox_runtime

    rt = _sim_runtime()
    b = booking("integrity-vehicle", zone="AC", kwh=5, now=rt.clock())
    rt.store.save_booking(b)
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    snap = await capture_atomic_snapshot(rt, horizon_minutes=1)
    if field == "manifest":
        snap.event_manifest.known_booking_ids.append("hidden")
    elif field == "booking":
        snap.known_bookings[0].request.soc_target -= 1
    elif field == "config":
        snap.station_config.guard.approval_ttl_minutes += 1
    elif field == "plan":
        object.__setattr__(snap.plan, "version", snap.plan.version + 1)
    elif field == "scheduler":
        snap = replace(snap, scheduler_metadata={"other": True})
    elif field == "physics":
        snap._physics_seed.detached_kernel.command_resolution_kw += 0.5
    with pytest.raises(ValueError, match="integrity"):
        build_sandbox_runtime(snap)


async def test_snapshot_rejects_untracked_present_vehicle():
    rt = _sim_runtime()
    b = booking("physical-only", zone="AC", kwh=5, now=rt.clock())
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    with pytest.raises(SnapshotNotReadyError):
        await capture_atomic_snapshot(rt, horizon_minutes=1)


async def test_historical_charge_start_stays_unknown_after_reassignment():
    rt = _sim_runtime(StrategyName.SIM_B0)
    sim = rt.simulator
    t0 = sim.now
    b = booking("dc-delayed", zone="DC", kwh=25, hours=2.0, now=t0)
    rt.store.save_booking(b)
    sim.upsert_vehicle(visit_of(b, t0))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=t0), rt)
    session = sim.queue.sessions[b.booking_id]
    assert session.charge_started == sim.minute
    power = sim.kernel.setpoints[b.booking_id]
    sim.kernel.hold_setpoint(b.booking_id, 0)
    sim.step(2)
    assert sim.kernel.output_kwh.get(b.booking_id, 0.0) == 0
    sim.kernel.hold_setpoint(b.booking_id, power)
    sim.step(1)
    pre_output = sim.kernel.output_kwh[b.booking_id]
    assert pre_output > 0

    events = sim.inject_incident(
        Incident(type=IncidentType.CONNECTOR_FAULT, connector_id=sim.connector_of(session.connector))
    )
    assert session.charge_started is None
    await control_loop.on_minute(rt, events)
    assert session.charge_started == sim.minute

    snap = await capture_atomic_snapshot(rt, horizon_minutes=2)
    row = (await run_sandbox_branch(snap)).outcome_ledger.vehicles[0]
    assert row.pre_snapshot_output_kwh == pytest.approx(pre_output, abs=1e-6)
    assert row.historical_plug_time_unknown
    assert row.plug_in_at is None
    assert row.first_charge_at is None
    assert row.first_rollout_charge_at == sim.now


async def test_interleaved_pair_reaps_peer_on_branch_exception(monkeypatch):
    from src.services.copilot import counterfactual

    peer_started = asyncio.Event()
    peer_cleaned = asyncio.Event()

    async def branch(_snapshot, *, branch_label, **_kwargs):
        if branch_label == "baseline":
            await peer_started.wait()
            raise ValueError("injected branch failure")
        peer_started.set()
        try:
            await asyncio.Future()
        finally:
            peer_cleaned.set()

    monkeypatch.setattr(counterfactual, "run_sandbox_branch", branch)
    with pytest.raises(ValueError, match="injected branch failure"):
        await counterfactual.run_paired_noop(None, interleaved=True)
    cleaned_at_return = peer_cleaned.is_set()
    for task in asyncio.all_tasks() - {asyncio.current_task()}:
        if task.get_coro().__qualname__.endswith(".<locals>.branch"):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert cleaned_at_return


async def test_pending_safety_retained_when_rollout_is_cancelled_during_delivery(monkeypatch):
    from src.services.copilot import counterfactual

    snapshot = await capture_atomic_snapshot(_sim_runtime(), horizon_minutes=3)
    fork = counterfactual.build_sandbox_runtime(snapshot)
    original_step = fork.simulator.step
    start_minute = fork.simulator.minute
    delivering = asyncio.Event()

    def step(minutes):
        events = original_step(minutes)
        return [
            *events,
            StationEvent(
                event_id="cancel-hard",
                type=EventType.HARD_LIMIT_VIOLATED,
                occurred_at=fork.simulator.now,
                violation_kinds=["charging_model"],
                violation_booking_ids=["unknown-vehicle"],
            ),
        ]

    async def failsafe(*_args):
        delivering.set()
        await asyncio.Future()

    monkeypatch.setattr(fork.simulator, "step", step)
    monkeypatch.setattr(control_loop, "_failsafe", failsafe)
    monkeypatch.setattr(counterfactual, "build_sandbox_runtime", lambda _: fork)
    job = asyncio.create_task(run_sandbox_branch(snapshot))
    await asyncio.wait_for(delivering.wait(), timeout=3)
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job
    assert fork.simulator.minute == start_minute + 1
    assert [e.event_id for e in fork.inspect_pending_safety()] == ["cancel-hard"]
    assert not fork.lock.locked()


async def test_missing_physical_update_reports_not_ready():
    rt = _sim_runtime()
    book_only = booking("persisted-only", zone="AC", kwh=5, now=rt.clock())
    rt.store.save_booking(book_only)
    with pytest.raises(SnapshotNotReadyError) as err:
        await capture_atomic_snapshot(rt, horizon_minutes=1)
    assert err.value.reason.value == "inconsistent_cohort"
    assert book_only.booking_id not in rt.simulator.queue.sessions


@pytest.mark.parametrize("block_stop", [True, False])
async def test_rollout_vehicle_safety_readback_requires_executed_stop(monkeypatch, block_stop):
    from src.guard import dispatcher
    from src.services.runtime import SAFETY_ATTEMPT_LIMIT

    rt = _sim_runtime(StrategyName.SIM_B0)
    b = booking("safety-active", zone="DC", kwh=25, now=rt.clock())
    rt.store.save_booking(b)
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    initial_minute = rt.simulator.minute
    assert rt.simulator.kernel.setpoints[b.booking_id] > 0
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=3)
    original_step = HybridStation.step
    original_submit = dispatcher.submit
    attempts = 0

    def step(station, minutes):
        events = original_step(station, minutes)
        if station.minute == initial_minute + 1:
            events.append(
                StationEvent(
                    event_id="active-vehicle-hard",
                    type=EventType.HARD_LIMIT_VIOLATED,
                    occurred_at=station.now,
                    violation_kinds=["charging_model"],
                    violation_booking_ids=[b.booking_id],
                )
            )
        return events

    async def submit(commands, *args, **kwargs):
        nonlocal attempts
        if any(cmd.source == CommandSource.EMERGENCY for cmd in commands):
            attempts += 1
            if block_stop:
                return []
        return await original_submit(commands, *args, **kwargs)

    monkeypatch.setattr(HybridStation, "step", step)
    monkeypatch.setattr(dispatcher, "submit", submit)
    branch = await run_sandbox_branch(snapshot)
    assert attempts == (SAFETY_ATTEMPT_LIMIT if block_stop else 1)
    observed_minutes = 1 if block_stop else 3
    assert branch.observed_until == snapshot.envelope.as_of + timedelta(minutes=observed_minutes)
    assert branch.unresolved_safety_count == int(block_stop)
    assert branch.safety_hold_booking_ids_end == [b.booking_id]
    assert branch.outcome_ledger.vehicles[0].horizon_output_kwh > 0
    assert branch.outcome_ledger.vehicles[0].status == VehicleOutcomeStatus.CENSORED_IN_PROGRESS


async def test_native_solver_timeout_cancels_coroutine_and_allows_next_branch(monkeypatch):
    from src.services.hybrid_planner import SimulatorScheduler

    rt = _sim_runtime()
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=3)
    original_plan = SimulatorScheduler.plan
    worker_started = threading.Event()
    release_worker = threading.Event()
    worker_finished = threading.Event()
    minutes = []

    def plan(scheduler, context):
        if not worker_started.is_set():
            worker_started.set()
            try:
                assert release_worker.wait(timeout=3)
            finally:
                worker_finished.set()
        return original_plan(scheduler, context)

    monkeypatch.setattr(SimulatorScheduler, "plan", plan)
    job = asyncio.create_task(
        run_sandbox_branch(snapshot, timeout_s=0.2, step_hook=lambda _, minute: minutes.append(minute))
    )
    try:
        assert await asyncio.to_thread(worker_started.wait, 1)
        with pytest.raises(TimeoutError):
            await job
        assert not worker_finished.is_set()
        assert minutes == []
    finally:
        release_worker.set()
    assert await asyncio.to_thread(worker_finished.wait, 1)
    assert (await run_sandbox_branch(snapshot, timeout_s=2)).status == "completed"


async def test_live_store_clock_and_staged_booking_event(monkeypatch, clean_db):
    from src.services import event_bus
    from src.services.copilot.snapshot import build_sandbox_runtime

    live = runtime.get_runtime()
    live.clock = lambda: live.simulator.now
    start = live.simulator.now
    repository.upsert_user(
        UserRecord(
            user_id="g3-clock-resident",
            email="g3-clock@example.invalid",
            role=Role.RESIDENT,
            display_name="G3 resident",
            created_at=start,
        )
    )
    fixture = booking("unused", zone="AC", kwh=5, hours=5, now=start, arrival=start + timedelta(minutes=30))

    # Wall-clock registration can be later than a paused simulator minute.
    class FutureWallTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return (start + timedelta(days=1)).astimezone(tz)

    monkeypatch.setattr(charging_service, "datetime", FutureWallTime)
    publish_original = event_bus.publish
    captured = []

    async def publish(event):
        if event.type == EventType.BOOKING_CREATED:
            snap = await capture_atomic_snapshot(live, horizon_minutes=2)
            captured.append(snap)
            await control_loop.deliver_pending(live)
            version = live.plan.version
            await publish_original(event)
            assert live.plan.version == version
        else:
            await publish_original(event)

    monkeypatch.setattr(event_bus, "publish", publish)
    result = await charging_service.book(fixture.request, "g3-clock-resident")
    assert result.created_at > start
    (snap,) = captured
    assert snap.event_manifest.known_booking_ids == [result.booking_id]
    assert [e.type for e in snap.ordinary_outbox_events] == [EventType.BOOKING_CREATED]
    assert build_sandbox_runtime(snap).simulator.queue.sessions[result.booking_id].state == "NOT_ARRIVED"
