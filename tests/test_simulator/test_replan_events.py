"""ADR-019 Phase 3 bước 4: mốc tính lại của backend (sạc xong, boundary TOU / xe rời, sai lệch budget).

Trạm `HybridStation` chạy trên `StationKernel`; mốc quyết định kế tiếp do `kernel.boundary` tính (PHASE3_DESIGN §3).
"""

from dataclasses import replace
from datetime import datetime, time, timedelta

import pytest

pytest.importorskip("ev2gym")

from src.models.charging import StrategyName  # noqa: E402
from src.models.control import Command, CommandSource, CommandType  # noqa: E402
from src.models.events import EventType  # noqa: E402
from src.models.station import Tariff, TariffPeriod  # noqa: E402
from src.models.station_protocols import VehicleVisit  # noqa: E402
from src.services import catalog  # noqa: E402
from src.services.hybrid_planner import SimulatorScheduler  # noqa: E402
from src.simulator.hybrid_station import HybridStation  # noqa: E402
from tests.factories import NOW, VN, booking, context  # noqa: E402


def _cmd(ctype, connector_id, booking_id=None, power=None) -> Command:
    return Command(
        type=ctype,
        connector_id=connector_id,
        booking_id=booking_id,
        power_kw=power,
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=0,
        based_on_state_at=NOW,
        created_at=NOW,
    )


def _visit(bid, zone="AC", hours=10.0, soc=0.4, target=0.8, battery=60.0, cap=11.0, arrival=NOW):
    return VehicleVisit(
        booking_id=bid,
        arrival_time=arrival,
        departure_time=arrival + timedelta(hours=hours),
        required_kwh=(target - soc) * battery / 0.98,
        zone=zone,
        max_power_kw=cap,
        battery_kwh=battery,
        soc_now=soc,
        soc_target=target,
    )


def test_charge_completion_is_its_own_event_once_and_not_a_replan_request():
    """Quyết định 2 (Phase 4): kernel phát CHARGE_COMPLETED, backend nhận đúng loại đó, tách khỏi REPLAN_REQUESTED."""
    sim = HybridStation(catalog.load_station_config(), start=NOW)
    sim.upsert_vehicle(_visit("dc", zone="DC", soc=0.5, target=0.52, cap=60))
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, "DC-01-1", "dc"), _cmd(CommandType.SET_POWER, "DC-01-1", "dc", 60)]
    )
    events = []
    for _ in range(10):
        events += sim.step(1)
    completed = [e for e in events if e.type == EventType.CHARGE_COMPLETED]
    done = sim.queue.sessions["dc"].completed_at
    assert done is not None and len(completed) == 1
    assert completed[0].booking_id == "dc" and completed[0].occurred_at == NOW + timedelta(minutes=done)
    assert not [e for e in events if e.type == EventType.REPLAN_REQUESTED]


async def test_events_of_the_same_minute_trigger_one_replan(clean_db):
    """Sạc xong + xe đến cùng phút → một lần tính lại (không replan trùng cùng timestamp); cả hai được ghi nhận."""
    from src.models.events import StationEvent
    from src.services import control_loop
    from tests.test_services.test_control_and_charging import _sim_runtime

    rt = _sim_runtime()
    recorded: list = []
    rt.store = replace(rt.store, record_event=recorded.append)
    now = rt.clock()
    events = [
        StationEvent(type=EventType.CHARGE_COMPLETED, occurred_at=now, booking_id="x"),
        StationEvent(type=EventType.VEHICLE_ARRIVED, occurred_at=now, booking_id="y"),
    ]
    before = len(rt.recorder.replan_durations_s)
    await control_loop.on_minute(rt, events)
    assert len(rt.recorder.replan_durations_s) == before + 1
    assert [e.type for e in recorded] == [EventType.CHARGE_COMPLETED, EventType.VEHICLE_ARRIVED]


def test_budget_deviation_is_recorded_and_replanned_but_is_not_a_physical_violation():
    sim = HybridStation(catalog.load_station_config(), start=NOW)
    sim.upsert_vehicle(_visit("ac"))
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "ac"), _cmd(CommandType.SET_POWER, "AC-01-1", "ac", 11)]
    )
    sim.kernel.active_budget_kw = {"AC": 5.0, "DC": 78.0}  # budget của quyết định đang hiệu lực < setpoint đang giữ
    events = sim.step(3)
    assert [e.type for e in events] == [EventType.REPLAN_REQUESTED]  # chỉ một lần cho quyết định này
    assert sim.kernel.budget_deviation_count == 3
    assert sim.applied_constraint_violation_count == 0  # 11 kW ≤ trần vật lý 22 kW


def _tariff(boundary: time) -> Tariff:
    return Tariff(
        source="test",
        periods=[
            TariffPeriod(name="cao", start=time(6, 0), end=boundary, price_per_kwh=3000),
            TariffPeriod(name="thấp", start=boundary, end=time(6, 0), price_per_kwh=1000),
        ],
    )


def test_next_decision_is_the_tou_boundary_not_a_fixed_15_minute_tick():
    start = datetime(2026, 11, 23, 21, 50, tzinfo=VN)
    sim = HybridStation(catalog.load_station_config(), start=start)
    scheduler = SimulatorScheduler(StrategyName.SIM_M3A, lambda: sim)
    sim.upsert_vehicle(_visit("ac", arrival=start))
    ctx = replace(
        context([booking("ac", zone="AC", kwh=10, hours=10, now=start)], sim.state()), tariff=_tariff(time(22))
    )
    plan = scheduler.plan(ctx)
    assert sim.next_decision_at == datetime(2026, 11, 23, 22, 0, tzinfo=VN)
    assert plan.step_minutes == 10
    assert scheduler.last_diagnostics["interval_minutes"] == 10


def test_next_decision_is_capped_by_the_planning_step_and_by_departures():
    sim = HybridStation(catalog.load_station_config(), start=NOW)
    scheduler = SimulatorScheduler(StrategyName.SIM_M3A, lambda: sim)
    sim.upsert_vehicle(_visit("short", hours=0.1))  # rời sau 6'
    scheduler.plan(
        replace(context([booking("short", zone="AC", kwh=1, hours=0.1)], sim.state()), tariff=_tariff(time(22)))
    )
    assert sim.next_decision_at == NOW + timedelta(minutes=6)
    sim.step(6)
    sim.upsert_vehicle(_visit("long", arrival=sim.now))
    scheduler.plan(
        replace(context([booking("long", zone="AC", kwh=5, hours=10)], sim.state()), tariff=_tariff(time(22)))
    )
    assert sim.next_decision_at == sim.now + timedelta(minutes=sim.config.optimizer.planning_step_minutes)


def test_command_resolution_matches_the_control_loop_and_is_not_a_budget_deviation():
    from src.services import control_loop
    from src.simulator import hybrid_station

    assert hybrid_station.COMMAND_RESOLUTION_KW == control_loop.POWER_TOL_KW
    sim = HybridStation(catalog.load_station_config(), start=NOW)
    sim.upsert_vehicle(_visit("ac"))
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "ac"), _cmd(CommandType.SET_POWER, "AC-01-1", "ac", 11)]
    )
    sim.kernel.active_budget_kw = {"AC": 10.995, "DC": 78.0}  # lệnh cũ chưa được gửi lại vì chênh < 0,01 kW
    assert sim.step(3) == [] and sim.kernel.budget_deviation_count == 0
    # Quyết định 3 (Phase 4): phần vượt trong deadband được ghi RIÊNG, không lẫn với sai lệch / vi phạm cứng.
    assert sim.kernel.command_deadband_count == 3
    result = sim.kernel.advance(sim.kernel.now + 1)
    assert dict(result.command_deadband_kw) == pytest.approx({"AC": 0.005})
    assert not result.budget_deviation_kw and not result.violations
    assert sim.kernel.deviation_metrics() == {
        "applied_constraint_violation_count": 0,
        "budget_deviation_count": 0,
        "command_deadband_count": 4,
    }


def test_budget_deviation_names_the_stale_held_setpoint():
    """Sai lệch budget > deadband: kernel chỉ ra xe có setpoint đang giữ cao hơn quyết định đã duyệt (lệnh chưa áp)."""
    sim = HybridStation(catalog.load_station_config(), start=NOW)
    sim.upsert_vehicle(_visit("ac"))
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "ac"), _cmd(CommandType.SET_POWER, "AC-01-1", "ac", 9.25)]
    )
    sim.kernel.active_budget_kw = {"AC": 7.279, "DC": 78.0}
    sim.kernel.active_setpoints_kw = {"ac": 7.279}  # quyết định mới; lệnh giảm chưa tới trạm
    result = sim.kernel.advance(sim.kernel.now + 1)
    assert dict(result.budget_deviation_kw) == pytest.approx({"AC": 9.25 - 7.279})
    assert dict(result.stale_setpoint_kw) == pytest.approx({"ac": 9.25 - 7.279})
    assert not result.command_deadband_kw and not result.violations


def test_phase3_ac_budget_deviation_at_minute_560_is_gone(caplog):
    """Tái hiện PHASE3_REPORT §7: `peak_evening` seed 2 M3b từng log AC +1,97 kW ở phút 560 (lệnh giảm AC bị chặn vì
    làm tròn lên). Sau khi lệnh được lượng tử hoá xuống + giảm tải được ưu tiên: không còn budget deviation."""
    import logging

    from src.services import simulation_service

    scenario = catalog.load_scenario("peak_evening").model_copy(update={"seed": 2})
    with caplog.at_level(logging.WARNING, logger="src.simulator.core.kernel"):
        simulation_service.run_scenario(scenario, StrategyName.SIM_M3B)
    assert not [r for r in caplog.records if "budget deviation" in r.getMessage()]
