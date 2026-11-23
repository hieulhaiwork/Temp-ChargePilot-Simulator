"""Hợp đồng của trạm giả lập (FR10, FR11), KPI (AC7) và bộ sinh phiên (FR18) — docs/plan/30-ai.md §4, §7.

Backend chạy trên `LiveStation` (src/simulator/live.py) sau bề mặt công khai `src/simulator/base.py`.
HybridSimulator (src/simulator/src/) là công cụ R&D offline, có bộ test riêng ở src/simulator/tests/.
"""

import inspect
from datetime import UTC, datetime, timedelta
from typing import get_type_hints

import pytest

from src.models.control import Command, CommandSource, CommandType
from src.models.events import EventType, StationEvent
from src.models.simulation import Incident, IncidentType, KpiReport, SessionOutcome
from src.models.station_protocols import StationActuator, StationReader, VehicleVisit
from src.services import catalog, simulation_service
from src.simulator.live import LiveStation
from tests.factories import NOW

READER_METHODS = [name for name, _ in inspect.getmembers(StationReader, inspect.isfunction) if not name.startswith("_")]


def test_reader_protocol_has_no_write_path():
    """ADR-002: phần ĐỌC không được có apply_commands — chỉ StationActuator có."""
    assert "apply_commands" not in READER_METHODS
    assert hasattr(StationActuator, "apply_commands")


def test_inject_incident_is_part_of_the_reader_contract():
    hints = get_type_hints(StationReader.inject_incident)
    assert hints["incident"] is Incident
    assert hints["return"] == list[StationEvent]


def test_kpi_report_covers_every_prd_metric():
    """AC7: thời gian chờ, tỷ lệ đúng hạn, điện thiếu, tỷ lệ phục vụ, chi phí (+ MT4, MT5, MT6)."""
    required = {
        "on_time_rate",
        "wait_mean_minutes",
        "wait_p90_minutes",
        "unmet_energy_kwh",
        "delivered_energy_kwh",
        "service_rate",
        "energy_cost_vnd",
        "peak_load_kw",
        "power_limit_violations",
        "replan_p95_seconds",
        "blocked_commands",
    }
    assert required <= set(KpiReport.model_fields)


# ---- T1.4: LiveStation -------------------------------------------------------------------


def _station() -> LiveStation:
    return LiveStation(catalog.load_station_config(), start=NOW)


def _cmd(ctype, connector_id, booking_id=None, power=None, version=0) -> Command:
    return Command(
        type=ctype,
        connector_id=connector_id,
        booking_id=booking_id,
        power_kw=power,
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=version,
        based_on_state_at=NOW,
        created_at=NOW,
    )


def _visit(bid="b1", hours=10, kwh=20, zone="AC", arrival=NOW, cap=11) -> VehicleVisit:
    return VehicleVisit(
        booking_id=bid,
        arrival_time=arrival,
        departure_time=arrival + timedelta(hours=hours),
        required_kwh=kwh,
        zone=zone,
        max_power_kw=cap,
    )


def test_adapter_contract_reset_gives_idle_connectors():
    st = _station().reset(catalog.load_scenario("hybrid_evening"))
    assert {c.connector_id for c in st.connectors} == {"AC-01-1", "AC-02-1", "DC-01-1", "DC-01-2"}
    assert all(c.status == "idle" and c.power_kw == 0 for c in st.connectors)
    assert st.available_power_kw == 106 and st.schedule_version == 0


def test_adapter_contract_energy_is_conserved():
    """Xe cắm AC-01-1, lệnh SET_POWER 6 kW, 15 phút → giao đúng 1,5 kWh (±1e-6)."""
    sim = _station()
    events = sim.upsert_vehicle(_visit())
    assert [e.type for e in events] == [EventType.VEHICLE_ARRIVED]
    assert sim.state().queue == ["b1"]
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "b1"), _cmd(CommandType.SET_POWER, "AC-01-1", "b1", 6)]
    )
    assert sim.state().schedule_version == 1
    sim.step(15)
    progress = next(s for s in sim.state().sessions if s.booking_id == "b1")
    assert progress.delivered_grid_kwh == pytest.approx(1.5, abs=1e-6)


def test_vehicle_power_is_capped_and_finishes():
    sim = _station()
    sim.upsert_vehicle(_visit(kwh=1, cap=3.7))
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "b1"), _cmd(CommandType.SET_POWER, "AC-01-1", "b1", 11)]
    )
    assert sim.state().connectors[0].power_kw == 3.7
    sim.step(30)
    conn = sim.state().connectors[0]
    assert conn.status == "finished" and conn.power_kw == 0  # đầy rồi vẫn chiếm cổng (F14)


def test_adapter_contract_departure_emits_event():
    sim = _station()
    sim.upsert_vehicle(_visit(hours=1))
    sim.apply_commands([_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "b1")])
    events = sim.step(61)
    assert [e.type for e in events] == [EventType.VEHICLE_DEPARTED]
    assert sim.state().connectors[0].status == "idle"
    assert sim.outcomes()[0].plug_in_time == NOW


def test_dc_vehicle_unplugs_after_delay_when_full():
    sim = _station()
    sim.upsert_vehicle(_visit(zone="DC", kwh=5, hours=3, cap=60))
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, "DC-01-1", "b1"), _cmd(CommandType.SET_POWER, "DC-01-1", "b1", 60)]
    )
    events = sim.step(5 + sim.config.dc_unplug_delay_minutes + 1)
    assert EventType.VEHICLE_DEPARTED in [e.type for e in events]


def test_wrong_zone_and_unknown_assignments_are_ignored():
    """Lưới an toàn cuối (Guard đã phải chặn trước): gán xe DC vào cổng AC / xe chưa đến → không đổi trạng thái."""
    sim = _station()
    sim.upsert_vehicle(_visit(zone="DC", cap=60))
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "b1"), _cmd(CommandType.ASSIGN_CONNECTOR, "AC-02-1", "ghost")]
    )
    assert all(c.booking_id is None for c in sim.state().connectors)


def test_adapter_contract_power_incident_changes_limit():
    """AC5. inject_incident(power_limit_change 20) → available_power_kw == 20 + POWER_LIMIT_CHANGED."""
    sim = _station()
    events = sim.inject_incident(Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=20))
    assert sim.state().available_power_kw == 20
    assert events[0].type == EventType.POWER_LIMIT_CHANGED and events[0].new_power_limit_kw == 20


def test_connector_fault_sends_car_back_to_queue():
    sim = _station()
    sim.upsert_vehicle(_visit())
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "b1"), _cmd(CommandType.SET_POWER, "AC-01-1", "b1", 11)]
    )
    events = sim.inject_incident(Incident(type=IncidentType.CONNECTOR_FAULT, connector_id="AC-01-1"))
    st = sim.state()
    assert events[0].type == EventType.CONNECTOR_FAULT
    assert st.connectors[0].status == "fault" and st.queue == ["b1"]
    sim.inject_incident(Incident(type=IncidentType.CONNECTOR_RESTORED, connector_id="AC-01-1"))
    assert sim.state().connectors[0].status == "idle"
    with pytest.raises(ValueError):
        sim.inject_incident(Incident(type=IncidentType.CONNECTOR_FAULT, connector_id="A05"))


def test_future_reservation_arrives_on_time():
    sim = _station()
    assert sim.upsert_vehicle(_visit(arrival=NOW + timedelta(minutes=30))) == []
    events = sim.step(30)
    assert [e.type for e in events] == [EventType.VEHICLE_ARRIVED]


def test_remove_vehicle_frees_connector():
    sim = _station()
    sim.upsert_vehicle(_visit())
    sim.apply_commands([_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "b1")])
    assert sim.remove_vehicle("b1")[0].type == EventType.VEHICLE_DEPARTED
    assert sim.state().connectors[0].booking_id is None


# ---- T1.5: sinh phiên --------------------------------------------------------------------


def _bookings(seed: int = 42):
    scenario = catalog.load_scenario("hybrid_evening").model_copy(update={"seed": seed})
    start = datetime.combine(simulation_service.SIM_DATE, scenario.start_time, tzinfo=NOW.tzinfo)
    return scenario, simulation_service.generate_bookings(scenario, catalog.load_station_config(), start)


def test_same_seed_same_bookings():
    """FR18. Cùng scenario + seed → cùng danh sách; seed khác → khác."""
    assert _bookings(42)[1] == _bookings(42)[1]
    assert _bookings(42)[1] != _bookings(7)[1]


def test_generated_bookings_are_valid_and_capped():
    scenario, bookings = _bookings()
    assert len(bookings) == scenario.n_vehicles
    horizon_end = bookings[0].created_at + timedelta(hours=scenario.duration_hours + 12)
    for b in bookings:
        cap = 60 if b.request.zone == "DC" else 11
        assert b.max_charge_power_kw <= cap
        assert b.request.deadline <= horizon_end
        assert b.request.vehicle_model != "DEMO-60"


# ---- T3.4: KPI ---------------------------------------------------------------------------


def _outcome(bid, requested, delivered, feasible=True, plugged=True) -> SessionOutcome:
    return SessionOutcome(
        booking_id=bid,
        accepted=True,
        feasible=feasible,
        arrival_time=NOW,
        plug_in_time=NOW + timedelta(minutes=10) if plugged else None,
        deadline=NOW + timedelta(hours=8),
        requested_kwh=requested,
        delivered_kwh_by_deadline=delivered,
    )


def _kpis(outcomes, load=()):
    return simulation_service.compute_kpis(
        outcomes, list(load), catalog.load_tariff(), catalog.load_station_config(), [0.1, 0.2], 3
    )


def test_on_time_rate_ignores_infeasible_requests():
    """MT1. 10 yêu cầu, 2 bất khả thi về vật lý, 8 đủ điện đúng hạn → on_time_rate == 1.0."""
    outcomes = [_outcome(f"ok{i}", 10, 10) for i in range(8)] + [
        _outcome(f"x{i}", 99, 20, feasible=False) for i in range(2)
    ]
    k = _kpis(outcomes)
    assert k.on_time_rate == 1.0
    assert k.unmet_energy_kwh == pytest.approx(158)
    assert k.blocked_commands == 3 and k.replan_p95_seconds == 0.2


def test_power_limit_violations_follow_the_limit_of_each_step():
    """MT4. Giới hạn rớt 35 → 20 kW ở giữa, tải 30 kW (đầu ra) suốt → vi phạm đúng số bước ở đoạn 20 kW."""
    t0 = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
    load = [(t0 + timedelta(minutes=m), 30.0, 35.0 if m < 10 or m >= 20 else 20.0) for m in range(30)]
    assert _kpis([], load).power_limit_violations == 10


def test_cost_uses_station_local_time_for_tariff():
    """MT3. 7 kWh nạp lúc 23:00 giờ trạm (16:00 UTC) → giá off_peak, không phải giá của 16:00."""
    eta = catalog.load_station_config().power_conversion_efficiency
    at = datetime(2026, 11, 23, 16, 0, tzinfo=UTC)
    load = [(at + timedelta(minutes=m), 7.0 * eta, 106.0) for m in range(60)]
    assert _kpis([], load).energy_cost_vnd == pytest.approx(7 * 1200, abs=1)


def test_wait_counts_unplugged_cars_until_departure():
    k = _kpis([_outcome("a", 1, 1), _outcome("b", 1, 0, plugged=False)])
    assert k.wait_mean_minutes == pytest.approx((10 + 480) / 2)
    assert k.service_rate == 0.5
