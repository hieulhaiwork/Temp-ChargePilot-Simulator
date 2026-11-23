"""Bộ tối ưu (F2/F3): registry chiến lược A–D + nghiệm thu trên simulator (LiveStation) chạy thật."""

from datetime import timedelta

import pytest

from src.models.charging import StrategyName
from src.optimizer import get_scheduler
from src.services import catalog, simulation_service
from tests.factories import NOW, booking, context, energy_of, state

BACKEND_STRATEGIES = [s for s in StrategyName if not s.value.startswith(("B0", "M2", "M3"))]


@pytest.mark.parametrize("name", BACKEND_STRATEGIES)
def test_every_benchmark_strategy_is_registered(name):
    """PRD §8: mỗi mã A–D có đúng một chiến lược, cùng interface Scheduler.

    B0 / M2b / M3a / M3b là thuật toán simulator, dựng ở src/services/runtime.make_scheduler (ADR-018).
    """
    scheduler = get_scheduler(name)
    assert scheduler.name == name
    assert callable(scheduler.plan)


@pytest.fixture(scope="module")
def power_drop_runs():
    scenario = catalog.load_scenario("hybrid_power_drop")
    return {s: simulation_service.run_scenario(scenario, s) for s in (StrategyName.FCFS, StrategyName.OPT_NO_ML)}


def test_power_limit_is_never_exceeded_even_when_supply_drops(power_drop_runs):
    """AC3 / AC5 / MT4: 24 h, nguồn rớt 106 → 40 kW và một cổng DC lỗi giữa chừng — 0 lần vượt giới hạn.

    Phần "≥ 95% đúng hạn" của AC3 KHÔNG được khẳng định ở đây: bãi `mvp1` chỉ có 2 cổng AC giữ xe qua đêm nên
    kịch bản tổng hợp cố ý quá tải; tỉ lệ đúng hạn thật được báo trong eval/results/benchmark.md.
    """
    for run in power_drop_runs.values():
        assert run.kpis.power_limit_violations == 0
        assert run.kpis.peak_load_kw <= 100 + 1e-6  # Σ ngân sách vùng 22 + 78 kW


def test_forecast_never_relaxes_declared_deadline():
    """FR9: chiến lược C với departure_forecast MUỘN hơn deadline vẫn giao đủ kWh trước deadline khai báo."""
    b = booking("a1", kwh=20, hours=3)
    ctx = context([b], state({"AC-01-1": "a1"}), departure_forecast={"a1": NOW + timedelta(hours=10)})
    plan = get_scheduler(StrategyName.OPT_ML).plan(ctx)
    deadline = b.request.deadline
    session = next(s for s in plan.sessions if s.booking_id == "a1")
    assert all(slot.start < deadline for slot in session.slots)
    assert energy_of(plan, "a1") == pytest.approx(20, abs=0.01)


def test_replan_p95_under_two_seconds(power_drop_runs):
    """MT5: p95 thời gian tính lại ≤ 2 s (đặt lịch, walk-in, sự cố) — đo trên cùng đường on_event của production."""
    p95 = power_drop_runs[StrategyName.OPT_NO_ML].kpis.replan_p95_seconds
    assert p95 is not None
    assert p95 <= 2.0
