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
