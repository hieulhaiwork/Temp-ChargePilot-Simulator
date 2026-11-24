"""HybridStation — trạm backend dựng trên thành phần của HybridSimulator (src/simulator/hybrid_station.py).

Cần ev2gym (venv `.simulator`): .simulator/Scripts/python.exe -m pytest tests/test_simulator/test_hybrid_station.py
Test cuối phát lại quyết định của HybridSimulator trên fixture mvp1 — "live = research" (ADR-016).
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("ev2gym")

from src.models.control import Command, CommandSource, CommandType  # noqa: E402
from src.models.events import EventType  # noqa: E402
from src.models.simulation import Incident, IncidentType  # noqa: E402
from src.models.simulation_core import Scenario  # noqa: E402
from src.models.station_protocols import VehicleVisit  # noqa: E402
from src.services import catalog  # noqa: E402
from src.simulator.hybrid import HybridSimulator  # noqa: E402
from src.simulator.hybrid_station import HybridStation  # noqa: E402
from tests.factories import NOW  # noqa: E402

MVP1 = Path(__file__).resolve().parents[2] / "src" / "simulator" / "scenario" / "mvp1.json"


def _station(config=None, start=NOW) -> HybridStation:
    return HybridStation(config or catalog.load_station_config(), start=start)


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


def _visit(bid="b1", zone="AC", hours=10, soc=0.4, target=0.8, battery=60.0, cap=11.0, arrival=NOW):
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


def _plug(sim, bid, connector, power):
    sim.apply_commands(
        [_cmd(CommandType.ASSIGN_CONNECTOR, connector, bid), _cmd(CommandType.SET_POWER, connector, bid, power)]
    )


def _progress(sim, bid):
    return next(s for s in sim.state().sessions if s.booking_id == bid)


def test_mapping_and_initial_state():
    sim = _station()
    assert sim.port_of("DC-01-2") == "DC-01/P2" and sim.connector_of("AC-02/P1") == "AC-02-1"
    st = sim.state()
    assert all(c.status == "idle" and c.power_kw == 0 for c in st.connectors)
    assert st.available_power_kw == 106 and st.schedule_version == 0
    assert sim.effective_limits().grid_input_kw == 106


def test_ac_set_power_delivers_expected_energy():
    """(1) AC 11 kW × 60 phút → 11 kWh đầu ra, pin nhận 11 × η_sạc."""
    sim = _station()
    assert [e.type for e in sim.upsert_vehicle(_visit())] == [EventType.VEHICLE_ARRIVED]
    assert sim.state().queue == ["b1"]
    _plug(sim, "b1", "AC-01-1", 11)
    assert sim.schedule_version == 1
    conn = sim.state().connectors[0]
    assert conn.status == "charging" and conn.power_kw == pytest.approx(11)
    sim.step(60)
    assert _progress(sim, "b1").delivered_grid_kwh == pytest.approx(11, abs=1e-6)
    assert sim.queue.sessions["b1"].delivered_battery_kwh == pytest.approx(11 * 0.98, abs=1e-6)
    assert sim.applied_constraint_violation_count == 0


def test_dc_taper_limits_actual_power_below_setpoint():
    """(2) DC: SOC > 0,6 ⇒ synthetic taper, công suất thực < setpoint 60 kW."""
    sim = _station()
    sim.upsert_vehicle(_visit(zone="DC", soc=0.55, target=0.95, cap=60))
    _plug(sim, "b1", "DC-01-1", 60)
    assert sim.state().connectors[2].power_kw == pytest.approx(60)
    sim.step(10)
    assert sim.adapter.soc("b1") > 0.7
    conn = sim.state().connectors[2]
    assert conn.power_kw < 60 - 1 and conn.status == "throttled"
    before = _progress(sim, "b1").delivered_grid_kwh
    sim.step(1)
    assert _progress(sim, "b1").delivered_grid_kwh - before == pytest.approx(conn.power_kw / 60, abs=1e-6)


def test_dc_unplugs_after_delay_ac_holds_until_departure():
    """(3) DC đầy → rút sau dc_unplug_delay_minutes; AC đầy vẫn giữ cổng tới giờ rời."""
    sim = _station()
    sim.upsert_vehicle(_visit("dc", zone="DC", soc=0.5, target=0.55, cap=60))
    sim.upsert_vehicle(_visit("ac", soc=0.5, target=0.52, hours=2))
    _plug(sim, "dc", "DC-01-1", 60)
    _plug(sim, "ac", "AC-01-1", 11)
    events = []
    for _ in range(30):
        events += sim.step(1)
        if sim.queue.sessions["dc"].completed_at is not None:
            break
    done = sim.queue.sessions["dc"].completed_at
    assert done is not None and sim.state().connectors[2].status == "finished"
    events = sim.step(sim.config.dc_unplug_delay_minutes)
    departed = [e for e in events if e.type == EventType.VEHICLE_DEPARTED]
    assert [e.booking_id for e in departed] == ["dc"] and departed[0].connector_id == "DC-01-1"
    assert departed[0].occurred_at == NOW + timedelta(minutes=done + sim.config.dc_unplug_delay_minutes)
    assert sim.state().connectors[0].status == "finished"  # AC đầy vẫn chiếm cổng
    events = sim.step(120 - sim.minute)
    assert [(e.type, e.booking_id) for e in events] == [(EventType.VEHICLE_DEPARTED, "ac")]
    assert sim.state().connectors[0].status == "idle"
    by_id = {o.booking_id: o for o in sim.outcomes()}
    assert by_id["ac"].delivered_kwh_by_deadline >= by_id["ac"].requested_kwh
    assert by_id["dc"].plug_in_time == NOW


def test_vehicle_arriving_mid_run():
    """(4) Xe báo trước đến đúng giờ; xe báo muộn (giờ đến đã qua) vào hàng ngay."""
    sim = _station()
    assert sim.upsert_vehicle(_visit(arrival=NOW + timedelta(minutes=30))) == []
    assert sim.step(29) == []
    assert [e.type for e in sim.step(1)] == [EventType.VEHICLE_ARRIVED]
    late = sim.upsert_vehicle(_visit("b2", arrival=NOW))
    assert [(e.type, e.booking_id) for e in late] == [(EventType.VEHICLE_ARRIVED, "b2")]
    assert _progress(sim, "b2").arrived_at == NOW + timedelta(minutes=30)
    assert sim.state().queue == ["b1", "b2"]
    _plug(sim, "b2", "AC-02-1", 11)
    sim.step(6)
    assert _progress(sim, "b2").delivered_grid_kwh == pytest.approx(1.1, abs=1e-6)


def test_invalid_assignments_are_ignored():
    """(5) Lưới an toàn cuối: sai vùng / xe chưa đến / cổng bận → bỏ qua, không đổi trạng thái."""
    sim = _station()
    sim.upsert_vehicle(_visit("dc", zone="DC", cap=60))
    sim.upsert_vehicle(_visit("ac1"))
    sim.upsert_vehicle(_visit("ac2"))
    sim.upsert_vehicle(_visit("later", arrival=NOW + timedelta(hours=1)))
    sim.apply_commands(
        [
            _cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "dc"),
            _cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "ghost"),
            _cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "later"),
            _cmd(CommandType.ASSIGN_CONNECTOR, "A05", "ac1"),
        ]
    )
    assert all(c.booking_id is None for c in sim.state().connectors)
    sim.apply_commands([_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "ac1")])
    sim.apply_commands([_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "ac2")])  # cổng bận
    assert sim.state().connectors[0].booking_id == "ac1"
    assert sim.state().queue == ["ac2", "dc"]


def test_connector_fault_sends_vehicle_to_queue_head():
    """(6) Cổng lỗi → xe về ĐẦU hàng chờ; khôi phục → idle; gán sang cổng khác được."""
    sim = _station()
    sim.upsert_vehicle(_visit("b1"))
    sim.upsert_vehicle(_visit("b2"))
    _plug(sim, "b1", "AC-01-1", 11)
    sim.step(5)
    events = sim.inject_incident(Incident(type=IncidentType.CONNECTOR_FAULT, connector_id="AC-01-1"))
    st = sim.state()
    assert events[0].type == EventType.CONNECTOR_FAULT and events[0].booking_id == "b1"
    assert st.connectors[0].status == "fault" and st.queue == ["b1", "b2"]
    sim.apply_commands([_cmd(CommandType.ASSIGN_CONNECTOR, "AC-01-1", "b2")])  # cổng lỗi: bỏ qua
    assert sim.state().connectors[0].booking_id is None
    assert "AC-01/P1" not in sim.dispatch_observation("AC").empty_ports
    sim.inject_incident(Incident(type=IncidentType.CONNECTOR_RESTORED, connector_id="AC-01-1"))
    assert sim.state().connectors[0].status == "idle"
    _plug(sim, "b1", "AC-02-1", 11)
    sim.step(5)
    assert _progress(sim, "b1").delivered_grid_kwh == pytest.approx(11 * 10 / 60, abs=1e-6)
    with pytest.raises(ValueError):
        sim.inject_incident(Incident(type=IncidentType.CONNECTOR_FAULT, connector_id="A05"))


def test_power_incident_and_remove_vehicle():
    sim = _station()
    events = sim.inject_incident(Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=20))
    assert events[0].type == EventType.POWER_LIMIT_CHANGED and sim.state().available_power_kw == 20
    assert sim.effective_limits().grid_input_kw == 20
    sim.upsert_vehicle(_visit())
    _plug(sim, "b1", "AC-01-1", 11)
    assert sim.remove_vehicle("b1")[0].type == EventType.VEHICLE_DEPARTED
    assert sim.state().connectors[0].booking_id is None and sim.state().sessions == []


def test_scheduling_observation_matches_simulator_contract():
    sim = _station()
    sim.upsert_vehicle(_visit("dc", zone="DC", soc=0.7, target=0.9, cap=60))
    _plug(sim, "dc", "DC-01-2", 60)
    obs = sim.scheduling_observation()
    assert obs.ports["DC-01/P2"] == "dc" and obs.candidates["dc"].allowed_kw < 60  # taper ở SOC 0,7
    assert obs.effective_limits.grid_input_kw == 106 and obs.dc_charging_model is sim.adapter.dc_model


def test_replay_mvp1_matches_hybrid_simulator():
    """(7) live = research: phát lại quyết định của HybridSimulator (default_algorithms) trên mvp1 → năng lượng khớp."""
    scenario = Scenario.parse(json.loads(MVP1.read_text(encoding="utf-8")))
    research = HybridSimulator(scenario, record_decisions=True)
    research.run()

    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    start = datetime(2026, 11, 18, 0, 0, tzinfo=tz) + timedelta(minutes=scenario.start)
    # mvp1 không khai physical_zone_cap_kw ⇒ trần vùng = ngân sách 22/78 như simulator.
    config = catalog.load_station_config().model_copy(update={"physical_zone_cap_kw": None})
    live = _station(config, start)
    for v in scenario.vehicles:
        live.upsert_vehicle(
            VehicleVisit(
                booking_id=v.id,
                arrival_time=start + timedelta(minutes=v.arrival - scenario.start),
                departure_time=start + timedelta(minutes=v.departure - scenario.start),
                required_kwh=(v.target - v.initial_soc) * v.battery_kwh / scenario.efficiency,
                zone=v.zone,
                max_power_kw=v.max_kw,
                battery_kwh=v.battery_kwh,
                soc_now=v.initial_soc,
                soc_target=v.target,
            )
        )

    for record in research.decision_trace:
        assert record["interval_minutes"] == 1
        assert record["minute"] - scenario.start == live.minute
        commands = [
            _cmd(CommandType.ASSIGN_CONNECTOR, live.connector_of(port), vid)
            for zone in record["dispatch"].values()
            for port, vid in zone["assigned"].items()
        ]
        commands += [
            _cmd(CommandType.SET_POWER, live.connector_of(row["connector"]), vid, row["requested_output_kw"])
            for vid, row in record["vehicles"].items()
            if row["connector"] is not None and row["state"] == "CHARGING"
        ]
        live.apply_commands(commands)
        ports = record["ports_after_dispatch"]
        assert {port: live.queue.occupied.get(port) for port in ports} == ports
        live.step(1)

    assert live.applied_constraint_violation_count == 0
    assert sum(s.delivered_battery_kwh for s in research.queue.sessions.values()) > 100  # không khớp "vì cùng 0"
    for vid, ref in research.queue.sessions.items():
        got = live.queue.sessions[vid]
        assert got.delivered_battery_kwh == pytest.approx(ref.delivered_battery_kwh, abs=1e-6), vid
        assert got.delivered_grid_kwh == pytest.approx(ref.delivered_grid_kwh, abs=1e-6), vid
        assert live.adapter.soc(vid) == pytest.approx(research.adapter.soc(vid), abs=1e-9), vid
        for field in ("charge_started", "completed_at", "departed_at"):
            expected = getattr(ref, field)
            assert getattr(got, field) == (None if expected is None else expected - scenario.start), (vid, field)
        assert got.state == ref.state, vid
