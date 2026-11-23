"""Chiến lược của runtime (F2/F3): B0 / M2b / M3a / M3b trên Planning Core của kernel + nghiệm thu trên HybridStation.

LP backend A–D đã xoá ở ADR-019 Phase 3 (docs/refactor/DELETION_MANIFEST.md); test của nó được thay bằng các test dưới
đây (cùng tiêu chí AC3 / AC5 / MT4 / MT5, chạy trên policy thực thi).
"""

import pytest

from src.models.charging import StrategyName
from src.services import catalog, simulation_service
from src.services.hybrid_planner import SIMULATOR_STRATEGIES
from src.services.runtime import make_scheduler, make_station
from tests.factories import NOW

pytest.importorskip("ev2gym")

REMOVED = ["A_fcfs", "A_edf", "B", "C", "D"]  # LP backend cũ — bỏ hẳn ở Phase 4 (quyết định 1)


@pytest.mark.parametrize("name", sorted(SIMULATOR_STRATEGIES))
def test_every_runtime_strategy_is_a_planning_core_policy(name):
    station = make_station(catalog.load_station_config(), NOW)
    scheduler = make_scheduler(name, lambda: station)
    assert scheduler.name == name and callable(scheduler.plan)
    assert station.kernel.policy_id == name.value


def test_strategy_enum_is_exactly_the_registry_policies():
    """Không còn giá trị nào của StrategyName mà Planning Core không chạy được (S8 / OpenAPI dùng enum này)."""
    assert set(StrategyName) == set(SIMULATOR_STRATEGIES)
    assert [s.value for s in StrategyName] == ["B0", "M2b", "M3a", "M3b"]


@pytest.mark.parametrize("name", REMOVED)
def test_removed_lp_strategies_fail_loudly(name):
    """Thay cho `make_scheduler(A–D) → DomainError` của Phase 3: giá trị cũ giờ bị từ chối ngay ở hợp đồng."""
    with pytest.raises(ValueError):
        StrategyName(name)


@pytest.mark.parametrize("name", REMOVED)
def test_removed_lp_strategies_are_rejected_by_settings(name, monkeypatch):
    from pydantic import ValidationError

    from src.config import Settings

    monkeypatch.setenv("LIVE_STRATEGY", name)
    with pytest.raises(ValidationError):
        Settings()


@pytest.fixture(scope="module")
def power_drop_runs():
    scenario = catalog.load_scenario("hybrid_power_drop")
    return {s: simulation_service.run_scenario(scenario, s) for s in (StrategyName.SIM_B0, StrategyName.SIM_M3A)}


def test_power_limit_is_never_exceeded_even_when_supply_drops(power_drop_runs):
    """AC3 / AC5 / MT4: 24 h, nguồn rớt 106 → 40 kW và một cổng DC lỗi giữa chừng — 0 lần vượt giới hạn.

    Phần "≥ 95% đúng hạn" của AC3 KHÔNG được khẳng định ở đây: bãi `mvp1` chỉ có 2 cổng AC giữ xe qua đêm nên
    kịch bản tổng hợp cố ý quá tải; tỉ lệ đúng hạn thật được báo trong evidence benchmark.
    """
    for run in power_drop_runs.values():
        assert run.kpis.power_limit_violations == 0
        assert run.kpis.peak_load_kw <= 100 + 1e-6  # Σ ngân sách vùng 22 + 78 kW


def test_replan_p95_under_two_seconds(power_drop_runs):
    """MT5: p95 thời gian tính lại ≤ 2 s — đo trên cùng đường on_event của production."""
    p95 = power_drop_runs[StrategyName.SIM_M3A].kpis.replan_p95_seconds
    assert p95 is not None
    assert p95 <= 2.0
