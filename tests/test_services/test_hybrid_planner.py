"""ADR-018: backend chạy thuật toán + engine của simulator R&D (simulator là gốc)."""

from datetime import datetime, time, timedelta, timezone

import pytest

pytest.importorskip("ev2gym")

from src.models.charging import StrategyName  # noqa: E402
from src.models.station import Tariff, TariffPeriod  # noqa: E402
from src.services import catalog, simulation_service  # noqa: E402
from src.services.hybrid_planner import POLICIES, _sim_tariff  # noqa: E402
from src.simulator import benchmark_mvp3  # noqa: E402

VN = timezone(timedelta(hours=7))


def test_policies_are_exactly_the_simulator_benchmark_policies():
    """Không tự định nghĩa lại M2b / M3a / M3b: đọc đúng bảng của simulator."""
    assert {name.value: combo for name, combo in POLICIES.items()} == dict(benchmark_mvp3.POLICIES)


def test_tariff_is_translated_to_simulator_minutes():
    tariff = Tariff(
        source="test",
        periods=[
            TariffPeriod(name="thấp", start=time(22, 0), end=time(6, 0), price_per_kwh=1000),
            TariffPeriod(name="cao", start=time(6, 0), end=time(22, 0), price_per_kwh=3000),
        ],
    )
    now = datetime(2026, 11, 23, 20, 30, tzinfo=VN)
    sim = _sim_tariff(tariff, now, 100)
    assert sim.price_at(100) == 3000  # 20:30 là giờ cao
    assert sim.price_at(100 + 90) == 1000  # 22:00
    assert sim.price_at(100 + 90 + 8 * 60) == 3000  # 06:00 hôm sau


@pytest.mark.parametrize("strategy", [StrategyName.SIM_M3A, StrategyName.SIM_M3B, StrategyName.SIM_M2B])
def test_simulator_strategies_run_end_to_end_behind_the_guard(strategy):
    """Optimizer simulator → Guard backend → HybridStation: 0 vượt giới hạn, 0 lệnh bị chặn, có xe được sạc."""
    scenario = catalog.load_scenario("hybrid_evening")
    result = simulation_service.run_scenario(scenario, strategy)
    assert result.kpis.power_limit_violations == 0
    assert result.kpis.blocked_commands == 0
    assert result.kpis.delivered_energy_kwh > 0
    assert "HybridStation" in result.notes


async def _plugged_ac_power(strategy: StrategyName, max_start_delay_minutes: int) -> float:
    """Xe AC hạn xa vào lúc giờ cao điểm (18:00): thuật toán AC của simulator muốn dời tới giờ thấp điểm."""
    from src.models.charging import ConsentScope
    from src.models.events import EventType, StationEvent
    from src.services import control_loop
    from src.services.runtime import build_sim_runtime, visit_of
    from tests.factories import booking

    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=VN)
    rt = build_sim_runtime(scenario, strategy, config, tariff, start)
    b = booking("ac1", zone="AC", kwh=10, hours=10, now=rt.clock()).model_copy(
        update={"consent": ConsentScope(max_start_delay_minutes=max_start_delay_minutes)}
    )
    rt.store.save_booking(b)
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    conn = next(c for c in rt.simulator.state().connectors if c.booking_id == "ac1")
    return conn.power_kw


async def test_m3a_starts_charging_when_resident_did_not_allow_delay():
    """Lỗi "đang sạc 0 kW": consent max_start_delay = 0 ⇒ xe đã cắm phải được cấp điện ngay (như LP backend)."""
    assert await _plugged_ac_power(StrategyName.SIM_M3A, 0) > 0


async def test_m3a_may_wait_for_cheap_hours_when_delay_is_allowed():
    """Consent cho lùi 10 giờ ⇒ thuật toán simulator được tự quyết (không ép); chỉ cần không vượt trần."""
    assert 0 <= await _plugged_ac_power(StrategyName.SIM_M3A, 600) <= 11 + 1e-6


def test_station_reads_and_writes_are_serialised_by_one_lock():
    """Bot review: plan() đọc trạm trên thread solver — mọi thao tác trạm phải dưới cùng một RLock."""
    import threading

    from src.simulator.hybrid_station import HybridStation

    station = HybridStation(catalog.load_station_config(), datetime(2026, 11, 23, 18, tzinfo=VN))
    assert isinstance(station.lock, type(threading.RLock()))
    entered = threading.Event()
    done = []

    def stepper():
        entered.set()
        station.step(1)
        done.append(True)

    with station.lock:
        worker = threading.Thread(target=stepper)
        worker.start()
        entered.wait(1)
        worker.join(0.2)
        assert not done  # step() phải chờ khoá
    worker.join(2)
    assert done


async def _at_risk_after_tick(strategy: StrategyName, bookings) -> list[str]:
    from src.models.events import EventType, StationEvent
    from src.services import control_loop, station_service
    from src.services.runtime import build_sim_runtime, visit_of

    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=VN)
    rt = build_sim_runtime(scenario, strategy, config, tariff, start, engine="hybrid")
    for make in bookings:
        b = make(rt.clock())
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    return station_service.build_overview(rt).at_risk_booking_ids


EASY_AND_TIGHT = [
    ("dc-de", "DC", 20, 4),  # dễ kịp
    ("ac-de", "AC", 10, 10),  # dễ kịp (M3a để 0 kW chờ giờ thấp điểm — vẫn không phải nguy cơ)
    ("dc-sat", "DC", 50, 50 / 60),  # 50 kWh trong 50' ở 60 kW → laxity 0
]


def _makers():
    from tests.factories import booking

    return [
        (lambda now, bid=bid, zone=zone, kwh=kwh, hours=hours: booking(bid, zone=zone, kwh=kwh, hours=hours, now=now))
        for bid, zone, kwh, hours in EASY_AND_TIGHT
    ]


async def test_at_risk_simulator_strategy_flags_only_tight_sessions():
    """US5. Lỗi PR #15 (đã chạy thử 23/11): M3a chỉ có lịch 1 bước → MỌI xe bị gắn "nguy cơ trễ".
    Sau sửa (laxity < 30'): xe dễ kịp không gắn, xe sát hạn vẫn gắn."""
    flagged = await _at_risk_after_tick(StrategyName.SIM_M3A, _makers())
    assert set(flagged) == {"dc-sat"}


async def test_at_risk_backend_lp_keeps_planned_shortfall_definition():
    """A–D giữ định nghĩa cũ: nguy cơ = lịch dự kiến giao thiếu. Xe sát hạn nhưng lịch vẫn đủ → không gắn.
    Hai định nghĩa khác nghĩa — ghi rõ, chưa hợp nhất (ADR-018)."""
    assert await _at_risk_after_tick(StrategyName.OPT_NO_ML, _makers()) == []
