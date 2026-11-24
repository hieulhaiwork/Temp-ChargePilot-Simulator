"""Final Review §4.5b — fail-safe khi trạm phát hiện vi phạm trần cứng SAU khi áp (backend, non-strict).

Gây vi phạm: nguồn tụt "im lặng" (không có sự kiện POWER_LIMIT_CHANGED nên bảo vệ AC5 không chạy) trong khi setpoint
cũ vẫn giữ ⇒ Physical Guard sau thực thi của kernel bắt vi phạm. Bật `guard.after_apply_failsafe` ⇒ trạm phát
HARD_LIMIT_VIOLATED ⇒ control_loop sinh lệnh giảm tải EMERGENCY qua guard/dispatcher.py, ghi nhật ký + DecisionTrace,
rồi tính lại; phút sau không còn vi phạm. Tắt (mặc định) ⇒ hành vi cũ: chỉ đếm + log.
"""

import logging
from datetime import datetime

import pytest

pytest.importorskip("ev2gym")

from src.models.charging import StrategyName  # noqa: E402
from src.models.control import CommandSource  # noqa: E402
from src.models.events import EventType, StationEvent  # noqa: E402
from src.services import catalog, control_loop  # noqa: E402
from src.services.runtime import build_sim_runtime, visit_of  # noqa: E402
from tests.factories import VN, booking  # noqa: E402

SILENT_LIMIT_KW = 30.0


async def _charging_runtime(failsafe: bool):
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    config = config.model_copy(update={"guard": config.guard.model_copy(update={"after_apply_failsafe": failsafe})})
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=VN)
    rt = build_sim_runtime(scenario, StrategyName.SIM_M3A, config, tariff, start)
    for b in (
        booking("dc-a", zone="DC", kwh=40, hours=1.5, now=rt.clock()),
        booking("dc-b", zone="DC", kwh=40, hours=1.5, now=rt.clock()),
        booking("ac-a", zone="AC", kwh=20, hours=3, now=rt.clock()),
    ):
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    events = rt.simulator.step(1)
    await control_loop.on_minute(rt, events)
    assert rt.simulator.state().total_power_kw / config.power_conversion_efficiency > SILENT_LIMIT_KW
    return rt


async def test_violation_after_apply_triggers_load_reduction_through_the_dispatcher(caplog):
    rt = await _charging_runtime(failsafe=True)
    sim = rt.simulator
    decisions: list = []
    original = rt.sinks.log_decision
    rt.sinks = rt.sinks.__class__(
        log_decision=lambda e: (decisions.append(e), original(e)),
        save_approval=rt.sinks.save_approval,
        notify=rt.sinks.notify,
    )
    sim.available_power_kw = SILENT_LIMIT_KW  # tụt nguồn không qua incident ⇒ không có POWER_LIMIT_CHANGED
    before = sim.applied_constraint_violation_count
    with caplog.at_level(logging.WARNING):
        events = sim.step(1)
    assert sim.applied_constraint_violation_count > before
    violated = [e for e in events if e.type == EventType.HARD_LIMIT_VIOLATED]
    assert len(violated) == 1 and "trần cứng" in violated[0].detail

    with caplog.at_level(logging.WARNING):
        await control_loop.on_minute(rt, events)
    emergency = [e for e in decisions if e.command.source == CommandSource.EMERGENCY]
    assert emergency and all(e.executed for e in emergency)
    assert all(e.command.correlation_id for e in emergency)
    assert any("fail-safe sau khi áp" in r.getMessage() for r in caplog.records)
    trace = rt.open_trace["trace"]
    assert trace["trigger"]["type"] == EventType.HARD_LIMIT_VIOLATED.value or any(
        b["type"] == EventType.HARD_LIMIT_VIOLATED.value for b in trace["trigger"]["batched"]
    )
    assert {row["command_id"] for row in trace["emergency_commands"]} == {e.command.command_id for e in emergency}

    after = sim.applied_constraint_violation_count
    events = sim.step(1)
    assert sim.applied_constraint_violation_count == after  # đã về trong trần
    assert not [e for e in events if e.type == EventType.HARD_LIMIT_VIOLATED]
    assert sim.state().total_power_kw / rt.config.power_conversion_efficiency <= SILENT_LIMIT_KW + 1e-6


async def test_failsafe_is_opt_in_default_keeps_count_and_log_only(caplog):
    assert catalog.load_station_config().guard.after_apply_failsafe is False
    rt = await _charging_runtime(failsafe=False)
    sim = rt.simulator
    sim.available_power_kw = SILENT_LIMIT_KW
    before = sim.applied_constraint_violation_count
    with caplog.at_level(logging.ERROR):
        events = sim.step(1)
    assert sim.applied_constraint_violation_count > before
    assert not [e for e in events if e.type == EventType.HARD_LIMIT_VIOLATED]
    assert any("physical constraint violated after apply" in r.getMessage() for r in caplog.records)
