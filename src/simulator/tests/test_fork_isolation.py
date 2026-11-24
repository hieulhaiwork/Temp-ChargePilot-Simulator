"""Final Review §4.4 — cô lập bản fork của `StationKernel` (admission / WHAT-IF).

Quy tắc (`src/simulator/core/isolation.py`): chỉ thành phần khai báo stateless được dùng chung; thành phần có trạng
thái được `fork()` (nếu có) hoặc deep copy. Test đột biến: optimizer / DC model / RNG giả có trạng thái bị đổi trong
bản fork không làm đổi bản live. Thành phần hiện có (đã khai báo) vẫn dùng chung như trước.
"""

import json
import random
from dataclasses import replace
from pathlib import Path

import pytest

from src.models.decisions import TimeConfig
from src.models.scheduling.observations import PerfectObservation, SocEstimate, estimated
from src.models.simulation_core import Scenario
from src.optimizer.registry import POLICIES
from src.optimizer.zones.equal_share import zone_equal_share
from src.simulator.core import isolation
from src.simulator.core.algorithms import default_algorithms, resolve_algorithms
from src.simulator.core.charging_models.synthetic_dc import SyntheticTaperV1
from src.simulator.core.ev2gym_adapter import EV2GymAdapter
from src.simulator.core.kernel import StationKernel
from src.simulator.core.queue import QueueController

FIXTURE = Path(__file__).resolve().parents[1] / "scenario/mvp1.json"


@pytest.fixture
def scenario():
    return Scenario.parse(json.loads(FIXTURE.read_bytes()))


class CountingOptimizer:
    """Optimizer có trạng thái (warm-start giả): đếm lần gọi, nhớ quan sát cuối. KHÔNG có fork() ⇒ deep copy."""

    def __init__(self):
        self.calls = 0
        self.memory: list[int] = []

    def __call__(self, observation, zone, budget_kw):
        self.calls += 1
        self.memory.append(observation.minute)
        return zone_equal_share(observation, zone, budget_kw)


class ForkableCoordinator:
    """Thành phần có trạng thái tự định nghĩa snapshot bằng fork()."""

    def __init__(self, inner, generation=0):
        self.inner = inner
        self.generation = generation
        self.calls = 0

    def fork(self):
        return ForkableCoordinator(self.inner, self.generation + 1)

    def __call__(self, observation, demand_kw):
        self.calls += 1
        return self.inner(observation, demand_kw)


class CountingDCModel:
    """DC charging model có trạng thái (đếm lần hỏi acceptance) bọc SyntheticTaperV1."""

    def __init__(self):
        self.inner = SyntheticTaperV1()
        self.queries = 0

    def acceptance_kw(self, state):
        self.queries += 1
        return self.inner.acceptance_kw(state)

    def stored_kwh(self, state, setpoint_kw, interval_minutes, efficiency):
        self.queries += 1
        return self.inner.stored_kwh(state, setpoint_kw, interval_minutes, efficiency)


class NoisyTelemetry:
    """Mô hình quan sát ngẫu nhiên (RNG có trạng thái), nhớ giá trị theo phút để trả lời như nhau trong một phút."""

    def __init__(self, seed=7):
        self.rng = random.Random(seed)
        self.cache: dict = {}

    def observe(self, minute, truth):
        rows = {}
        for vid, row in truth.items():
            key = (minute, vid)
            if key not in self.cache:
                self.cache[key] = min(1.0, max(0.0, row.soc + self.rng.uniform(-0.02, 0.02)))
            rows[vid] = estimated(row, SocEstimate(self.cache[key], measured_at=minute, uncertainty=0.02))
        return rows


def _kernel(scenario, algorithms, dc_model=None, observation_model=None) -> StationKernel:
    adapter = EV2GymAdapter(scenario, dc_model or algorithms.dc_charging_model)
    return StationKernel(
        scenario,
        adapter,
        QueueController(scenario),
        algorithms,
        time=TimeConfig(physics_step_minutes=1, decision_interval_minutes=15),
        strict=False,
        observation_model=observation_model,
    )


def _plan_and_run(kernel: StationKernel, minutes: int = 30) -> None:
    """Vài vòng observe → propose → approve → apply → advance (như admission chạy trên bản fork)."""
    until = kernel.now + minutes
    while kernel.now < until:
        kernel.observe()
        approved = kernel.approve(kernel.propose())
        kernel.apply_approved(approved)
        kernel.advance(min(approved.proposal.interval_end, until))


def test_registered_components_are_declared_and_shared_as_before(scenario):
    for policy in POLICIES:
        dispatch, ac, dc, coordinator = POLICIES[policy]
        algorithms, _ = resolve_algorithms(
            {"dispatch": {"DC": dispatch}, "optimizers": {"AC": ac, "DC": dc}, "coordinator": coordinator},
            scenario,
            "test",
        )
        kernel = _kernel(scenario, algorithms)
        twin = kernel.fork()
        assert twin.algorithms is kernel.algorithms  # cùng object: hành vi cũ, không copy thừa
        assert twin.adapter.dc_model is kernel.adapter.dc_model
        assert twin.observation_model is kernel.observation_model
        assert isinstance(twin.observation_model, PerfectObservation)
    for model in ("synthetic_taper_v1", "vinfast_profiles_v0_1"):
        algorithms, _ = resolve_algorithms({"dc_charging_model": model}, scenario, "test")
        assert isolation.is_shared(algorithms.dc_charging_model)
    assert isolation.is_shared(default_algorithms().coordinator)


def test_stateful_optimizer_in_the_fork_does_not_touch_the_live_one(scenario):
    optimizer = CountingOptimizer()
    algorithms = replace(default_algorithms(), optimizers={"AC": optimizer, "DC": optimizer})
    live = _kernel(scenario, algorithms)
    _plan_and_run(live, 15)
    before = (optimizer.calls, list(optimizer.memory))
    twin = live.fork()
    copy = twin.algorithms.optimizers["AC"]
    assert copy is not optimizer and copy is twin.algorithms.optimizers["DC"]  # một bản cho một object dùng chung
    _plan_and_run(twin, 60)
    assert copy.calls > before[0]
    assert (optimizer.calls, optimizer.memory) == before
    assert live.now == scenario.start + 15 and twin.now == scenario.start + 75


def test_component_with_fork_uses_its_own_snapshot(scenario):
    coordinator = ForkableCoordinator(default_algorithms().coordinator)
    live = _kernel(scenario, replace(default_algorithms(), coordinator=coordinator))
    twin = live.fork()
    assert twin.algorithms.coordinator is not coordinator and twin.algorithms.coordinator.generation == 1
    _plan_and_run(twin, 30)
    assert twin.algorithms.coordinator.calls > 0 and coordinator.calls == 0


def test_stateful_dc_model_is_forked_once_for_adapter_and_algorithms(scenario):
    model = CountingDCModel()
    live = _kernel(scenario, replace(default_algorithms(), dc_charging_model=model), dc_model=model)
    assert live.adapter.dc_model is model
    twin = live.fork()
    assert twin.adapter.dc_model is twin.algorithms.dc_charging_model
    assert twin.adapter.dc_model is not model
    queries = model.queries
    _plan_and_run(twin, 30)
    assert twin.adapter.dc_model.queries > 0
    assert model.queries == queries


def test_stateful_rng_observation_model_is_isolated(scenario):
    telemetry = NoisyTelemetry()
    live = _kernel(scenario, default_algorithms(), observation_model=telemetry)
    live.observe()
    live._view()
    state = telemetry.rng.getstate()
    cache = dict(telemetry.cache)
    twin = live.fork()
    assert twin.observation_model is not telemetry
    _plan_and_run(twin, 45)
    assert telemetry.rng.getstate() == state and telemetry.cache == cache
    assert len(twin.observation_model.cache) > len(cache)
    # Bản fork bắt đầu từ ĐÚNG trạng thái RNG của live: cùng chuỗi số ngẫu nhiên tiếp theo.
    assert random.Random().getstate() != state
    probe = live.fork()
    assert probe.observation_model.rng.random() == telemetry.rng.random()


def test_undeclared_component_is_copied_not_shared():
    class Unknown:
        def __init__(self):
            self.state = []

    item = Unknown()
    memo: dict = {}
    copy = isolation.fork_component(item, memo)
    assert copy is not item and isolation.fork_component(item, memo) is copy
    assert not isolation.is_shared(item)
    assert isolation.is_shared(zone_equal_share) and isolation.is_shared(PerfectObservation())


# ---- Final Acceptance §4.2 — HybridSimulator.fork() có bản ghi riêng ----------------------------------------------------


def _recordings(sim) -> dict:
    import copy as copy_module

    # AppliedResult bất biến (frozen, mapping chỉ đọc) ⇒ chụp list là đủ; bản ghi dict thì chụp sâu.
    return {
        name: list(getattr(sim, name)) if name == "applied_results" else copy_module.deepcopy(getattr(sim, name))
        for name in sim._RECORDINGS
    }


def test_hybrid_simulator_fork_does_not_share_recordings(scenario):
    from src.simulator.hybrid import HybridSimulator

    live = HybridSimulator(scenario, record_decisions=True, time=TimeConfig(1, 15))
    for _ in range(4):
        live.step()
    assert live.events and live.frames and live.trace and live.decision_trace and live.applied_results
    before = _recordings(live)
    twin = live.fork()
    for name in live._RECORDINGS:
        assert getattr(twin, name) is not getattr(live, name), name
        assert getattr(twin, name) == before[name], name  # bản fork bắt đầu từ đúng lịch sử của live
    # mutation sâu trên bản fork không chạm live (frame / trace là dict lồng nhau)
    twin.frames[0]["vehicles"].clear()
    twin.trace[0]["ac_queue"] = -1
    twin.events[0]["event"] = "mutated"
    while not twin.finished:
        twin.step()
    assert len(twin.frames) > len(before["frames"]) and len(twin.events) > len(before["events"])
    assert _recordings(live) == before
    # và ngược lại: live chạy tiếp không đổi bản ghi của một bản fork khác
    probe = live.fork()
    snapshot = _recordings(probe)
    live.step()
    assert _recordings(probe) == snapshot
    assert len(live.trace) == len(before["trace"]) + 1


def test_hybrid_simulator_fork_runs_like_the_original(scenario):
    """Cô lập bản ghi không đổi kết quả: chạy bản fork tới cuối = chạy bản gốc tới cuối."""
    from src.simulator.hybrid import HybridSimulator

    live = HybridSimulator(scenario, time=TimeConfig(1, 15))
    for _ in range(3):
        live.step()
    result = live.fork().run()
    assert result == live.run()


# ---- Final Acceptance §4.3 — fallback DC model có trạng thái; từ chối closure có trạng thái -----------------------------


class StatefulFallback(CountingDCModel):
    """Fallback DC model có trạng thái (không có fork()) ⇒ phải được copy, không dùng chung."""


def test_stateful_fallback_of_the_profile_model_is_isolated(scenario):
    from src.simulator.core.charging_models.vehicle_profiles import VehicleProfilesDCModel

    default = VehicleProfilesDCModel({})
    assert isolation.is_shared(default)  # fallback SyntheticTaperV1 ⇒ như cũ
    fallback = StatefulFallback()
    model = VehicleProfilesDCModel({}, fallback=fallback)
    assert not isolation.is_shared(model)
    live = _kernel(scenario, replace(default_algorithms(), dc_charging_model=model), dc_model=model)
    twin = live.fork()
    assert twin.adapter.dc_model is twin.algorithms.dc_charging_model  # một bản cho adapter + algorithms
    assert twin.adapter.dc_model is not model and twin.adapter.dc_model.fallback is not fallback
    queries = fallback.queries
    _plan_and_run(twin, 30)
    assert twin.adapter.dc_model.fallback.queries > 0
    assert fallback.queries == queries


def test_stateful_fallback_of_the_live_provider_is_isolated():
    from src.simulator.core.charging_models.live_profiles import DynamicVehicleProfilesDCModel

    shared = DynamicVehicleProfilesDCModel()
    assert shared.fork().fallback is shared.fallback  # SyntheticTaperV1 khai báo stateless ⇒ dùng chung như cũ
    fallback = StatefulFallback()
    provider = DynamicVehicleProfilesDCModel(fallback=fallback)
    memo: dict = {}
    twin = isolation.fork_component(provider, memo)
    assert twin is not provider and twin.fallback is not fallback
    assert isinstance(twin.fallback, StatefulFallback)
    import copy as copy_module

    deep = copy_module.deepcopy(provider)
    assert deep.fallback is not fallback


def test_stateful_closure_is_refused_with_a_clear_error(scenario):
    history: list[int] = []

    def remembering(observation, zone, budget_kw):  # closure có trạng thái (history)
        history.append(observation.minute)
        return zone_equal_share(observation, zone, budget_kw)

    with pytest.raises(isolation.StatefulComponentError, match="closure over history"):
        isolation.fork_component(remembering, {})
    live = _kernel(scenario, replace(default_algorithms(), optimizers={"AC": remembering, "DC": zone_equal_share}))
    with pytest.raises(isolation.StatefulComponentError, match="remembering"):
        live.fork()

    def mutable_default(observation, zone, budget_kw, seen=[]):  # noqa: B006 — chính là thứ cần từ chối
        return zone_equal_share(observation, zone, budget_kw)

    with pytest.raises(isolation.StatefulComponentError, match="mutable default"):
        isolation.fork_component(mutable_default, {})

    def tagged(observation, zone, budget_kw):
        return zone_equal_share(observation, zone, budget_kw)

    tagged.calls = 0
    with pytest.raises(isolation.StatefulComponentError, match="attributes"):
        isolation.fork_component(tagged, {})


def test_declared_or_plain_functions_are_still_shared():
    def plain(observation, zone, budget_kw):
        return zone_equal_share(observation, zone, budget_kw)

    assert isolation.fork_component(plain, {}) is plain  # không có trạng thái thấy được ⇒ như cũ

    counter = {"n": 0}

    def declared(observation, zone, budget_kw):
        counter["n"] += 1
        return zone_equal_share(observation, zone, budget_kw)

    declared.__stateless__ = True  # người viết tự khai báo (chịu trách nhiệm)
    assert isolation.is_shared(declared) and isolation.fork_component(declared, {}) is declared
