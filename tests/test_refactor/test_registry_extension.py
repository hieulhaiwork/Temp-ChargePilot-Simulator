"""Definition of Done (ADR-019, TECHLEAD_PHASE4_DECISIONS): thay / thêm optimizer CHỈ qua registry + config.

Đăng ký một optimizer DC thử nghiệm vào `src/optimizer/registry.py` (OPTIMIZERS), trỏ policy sang nó (POLICIES), nạp lại
cấu hình như lúc khởi động tiến trình — rồi chạy đúng runtime backend (HybridStation + Planning Core + control loop +
Guard). Không sửa một dòng nào của `src/services` / `src/simulator`: backend phải dùng optimizer mới và lệnh vẫn qua
Physical Guard.
"""

import importlib
from datetime import datetime

import pytest

from src.models.charging import StrategyName
from src.optimizer import registry
from src.optimizer.zones.equal_share import zone_equal_share

CAP_KW = 5.0
MINUTES = 520  # xe DC đầu tiên của hybrid_evening đến phút 350, cụm DC ở phút 469–485


class CappedDCForTest:
    """Optimizer DC CHỈ để kiểm đường đăng ký: equal share rồi kẹp mỗi xe ≤ 5 kW (không phải policy thật)."""

    def __call__(self, observation, zone, budget_kw):
        return {vid: min(kw, CAP_KW) for vid, kw in zone_equal_share(observation, zone, budget_kw).items()}


def _configure(params, scenario):
    return CappedDCForTest(), {"parameters": {"cap_kw": CAP_KW}}


async def _run_backend(strategy: StrategyName) -> tuple[float, dict]:
    from src.models.events import EventType, StationEvent
    from src.services import catalog, control_loop, simulation_service
    from src.services.runtime import build_sim_runtime, visit_of
    from tests.factories import NOW

    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(NOW.date(), scenario.start_time, tzinfo=NOW.tzinfo)
    pending = sorted(
        simulation_service.generate_bookings(scenario, config, start), key=lambda b: (b.created_at, b.booking_id)
    )
    rt = build_sim_runtime(scenario, strategy, config, tariff, start)
    sim, carried, dc_peak = rt.simulator, [], 0.0
    for _ in range(MINUTES):
        now, events, carried = sim.now, carried, []
        while pending and pending[0].created_at <= now:
            booking = pending.pop(0)
            rt.store.save_booking(booking)
            events += sim.upsert_vehicle(visit_of(booking, now))
            events.append(StationEvent(type=EventType.BOOKING_CREATED, occurred_at=now, booking_id=booking.booking_id))
        await control_loop.on_minute(rt, events)
        carried = sim.step(1)
        dc_peak = max([dc_peak] + [c.power_kw for c in sim.state().connectors if c.connector_id.startswith("DC")])
    assert getattr(sim, "applied_constraint_violation_count", 0) == 0
    return dc_peak, rt.scheduler.metadata


@pytest.fixture
def capped_dc_policy(monkeypatch):
    """Cấu hình: optimizer mới trong registry + policy M2b trỏ sang nó; nạp lại như khởi động tiến trình."""
    from src.services import hybrid_planner

    monkeypatch.setitem(
        registry.OPTIMIZERS,
        "test_capped_dc",
        registry.Registration(CappedDCForTest, version="test-1", configure=_configure),
    )
    monkeypatch.setitem(registry.POLICIES, "M2b", ("llf", "equal_share", "test_capped_dc", "fixed_share"))
    importlib.reload(hybrid_planner)
    yield
    monkeypatch.undo()
    importlib.reload(hybrid_planner)


def test_backend_runs_a_newly_registered_optimizer_without_code_changes(capped_dc_policy):
    from src.services.admission import run_sync

    dc_peak, metadata = run_sync(_run_backend(StrategyName.SIM_M2B))
    implementation = metadata["optimizers"]["DC"]["implementation"]
    assert implementation.endswith("CappedDCForTest"), implementation
    assert 0 < dc_peak <= CAP_KW + 1e-6, dc_peak


def test_reference_policy_is_untouched_after_the_override():
    """Sau khi bỏ cấu hình thử nghiệm, M2b trở lại đúng bản đóng băng của registry (DC rolling LP, công suất > 5 kW)."""
    from src.services import hybrid_planner
    from src.services.admission import run_sync

    assert registry.POLICIES["M2b"] == ("llf", "equal_share", "rolling_lp", "fixed_share")
    assert hybrid_planner.POLICIES[StrategyName.SIM_M2B] is registry.POLICIES["M2b"]
    dc_peak, metadata = run_sync(_run_backend(StrategyName.SIM_M2B))
    assert metadata["optimizers"]["DC"]["implementation"].endswith("RollingHorizonLP")
    assert dc_peak > CAP_KW
