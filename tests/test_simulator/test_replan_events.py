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


def test_charge_completion_requests_a_replan_once():
    sim = HybridStation(catalog.load_station_config(), start=NOW)
    sim.upsert_vehicle(_visit("dc", zone="DC", soc=0.5, target=0.52, cap=60))
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, "DC-01-1", "dc"), _cmd(CommandType.SET_POWER, "DC-01-1", "dc", 60)]
    )
    events = []
    for _ in range(10):
        events += sim.step(1)
    replans = [e for e in events if e.type == EventType.REPLAN_REQUESTED]
    done = sim.queue.sessions["dc"].completed_at
    assert done is not None and len(replans) == 1
    assert replans[0].booking_id == "dc" and replans[0].occurred_at == NOW + timedelta(minutes=done)


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
