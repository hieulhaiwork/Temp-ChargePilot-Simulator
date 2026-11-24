"""Final Review §4.4 ở tầng backend: admission (quote / booking) chạy trên bản fork không đổi thành phần của trạm live.

Optimizer giả có trạng thái được gắn vào policy M3a của runtime; admission chạy policy đó tới deadline trên bản fork.
Bản live phải giữ nguyên số lần gọi / bộ nhớ của optimizer; bản fork dùng bản copy riêng.
"""

from dataclasses import replace
from datetime import datetime

import pytest

pytest.importorskip("ev2gym")

from src.models.charging import StrategyName  # noqa: E402
from src.models.events import EventType, StationEvent  # noqa: E402
from src.services import admission, catalog, control_loop  # noqa: E402
from src.services.runtime import build_sim_runtime, fork_runtime, visit_of  # noqa: E402
from tests.factories import VN, booking  # noqa: E402


class WarmStartMemory:
    """Bọc optimizer thật, giữ "warm start" (lịch sử phút đã giải) — kiểu optimizer có trạng thái của MVP-3.5."""

    def __init__(self, inner):
        self.inner = inner
        self.history: list[int] = []

    def __call__(self, observation, zone, budget_kw):
        self.history.append(observation.minute)
        return self.inner(observation, zone, budget_kw)


async def _runtime_with_stateful_optimizer():
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=VN)
    rt = build_sim_runtime(scenario, StrategyName.SIM_M3A, config, tariff, start)
    base = rt.scheduler.algorithms()
    memory = WarmStartMemory(base.optimizers["DC"])
    stateful = replace(base, optimizers={"AC": base.optimizers["AC"], "DC": memory})
    rt.scheduler._algorithms = stateful
    rt.scheduler.configure(rt.simulator)
    for b in (booking("dc-a", zone="DC", kwh=35, hours=1.5, now=rt.clock()),):
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    return rt, memory


async def test_admission_fork_does_not_mutate_live_stateful_optimizer():
    rt, memory = await _runtime_with_stateful_optimizer()
    assert rt.simulator.kernel.algorithms.optimizers["DC"] is memory and memory.history
    live_history = list(memory.history)
    frt = fork_runtime(rt, list(rt.store.active_bookings()))
    forked = frt.simulator.kernel.algorithms.optimizers["DC"]
    assert forked is not memory and forked.history == live_history  # snapshot, không dùng chung
    assert frt.scheduler.algorithms() is frt.simulator.kernel.algorithms  # scheduler fork không gắn lại bản live

    candidate = booking("cand", zone="DC", kwh=25, hours=2, now=rt.clock())
    result = await admission.evaluate(rt, candidate)
    assert result.decisions > 0
    assert memory.history == live_history  # WHAT-IF không đổi trạng thái optimizer của trạm live
    assert rt.simulator.kernel.algorithms.optimizers["DC"] is memory


async def test_stateless_policy_is_still_shared_by_the_fork():
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=VN)
    rt = build_sim_runtime(scenario, StrategyName.SIM_M3A, config, tariff, start)
    frt = fork_runtime(rt, [])
    assert frt.simulator.kernel.algorithms is rt.simulator.kernel.algorithms
    assert frt.simulator.adapter.dc_model is rt.simulator.adapter.dc_model


async def test_foundation_fork_copies_nested_runtime_dtos_and_keeps_sinks_isolated():
    from src.models.control import Approval, ApprovalKind, Command, CommandSource, CommandType, GuardVerdict

    rt, _ = await _runtime_with_stateful_optimizer()
    (live_booking,) = rt.store.active_bookings()
    now = rt.clock()
    cmd = Command(
        type=CommandType.SET_POWER,
        connector_id="DC-01-1",
        power_kw=10,
        booking_id=live_booking.booking_id,
        source=CommandSource.OPTIMIZER,
        issued_by="test",
        based_on_schedule_version=rt.plan.version,
        based_on_state_at=now,
        created_at=now,
    )
    pending = Approval(
        kind=ApprovalKind.RESIDENT_CONSENT,
        command=cmd,
        verdict=GuardVerdict(command_id=cmd.command_id, passed=True, checked_at=now),
        requested_from=live_booking.resident_id,
        impact_summary="Synthetic approval",
        created_at=now,
    )
    rt.sinks.save_approval(pending)
    rt.recent_commands.append(cmd)
    rt.rejected_booking_ids.add("rejected")
    live_trace_count = len(rt.recorder.decision_traces)
    live_bookings = [b.model_dump() for b in rt.store.active_bookings()]
    live_plan = rt.plan.model_dump()
    live_config = rt.config.model_dump()
    live_tariff = rt.tariff.model_dump()

    fork = fork_runtime(rt, rt.store.active_bookings())
    assert fork.config is fork.simulator.config
    assert fork.config.model_dump() == live_config and fork.plan.model_dump() == live_plan
    assert fork.tariff.model_dump() == live_tariff and fork.rejected_booking_ids == rt.rejected_booking_ids
    assert fork.store.pending_approvals()[0].model_dump() == pending.model_dump()
    assert fork.sinks is not rt.sinks and fork.store is not rt.store
    assert fork.lock is not rt.lock and fork.booking_lock is not rt.booking_lock and fork.loop is None
    assert fork.open_trace is None and not fork.recorder.decision_traces and not fork.outbox

    fork.store.get_booking(live_booking.booking_id).request.soc_target = 50
    fork.store.pending_approvals()[0].command.power_kw = 7
    fork.recent_commands[-1].power_kw = 4
    fork.plan.sessions[0].slots[0].power_kw = 2
    fork.config.connectors[0].max_power_kw = 3
    fork.tariff.periods[0].price_per_kwh = 123
    fork.rejected_booking_ids.clear()
    fork.scheduler.metadata["dispatch"]["AC"]["name"] = "fixture-override"
    assert [b.model_dump() for b in rt.store.active_bookings()] == live_bookings
    assert rt.store.pending_approvals()[0].command.power_kw == 10 and rt.recent_commands[-1].power_kw == 10
    assert rt.plan.model_dump() == live_plan and rt.config.model_dump() == live_config
    assert rt.tariff.model_dump() == live_tariff and rt.rejected_booking_ids == {"rejected"}
    assert rt.scheduler.metadata["dispatch"]["AC"]["name"] != "fixture-override"
    assert len(rt.recorder.decision_traces) == live_trace_count


class StatefulDC:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = 0

    def acceptance_kw(self, *args):
        self.calls += 1
        return self.delegate.acceptance_kw(*args)

    def stored_kwh(self, *args):
        self.calls += 1
        return self.delegate.stored_kwh(*args)


async def test_foundation_runtime_fork_keeps_one_independent_dc_model():
    rt, _ = await _runtime_with_stateful_optimizer()
    dc = StatefulDC(rt.simulator.adapter.dc_model)
    rt.simulator.adapter.dc_model = dc
    rt.scheduler._algorithms = replace(rt.scheduler.algorithms(), dc_charging_model=dc)
    rt.scheduler.configure(rt.simulator)
    fork = fork_runtime(rt, rt.store.active_bookings())
    copied = fork.simulator.adapter.dc_model
    assert copied is fork.scheduler.algorithms().dc_charging_model and copied is not dc
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=fork.clock()), fork)
    fork.simulator.step(1)
    assert copied.calls > 0 and dc.calls == 0
