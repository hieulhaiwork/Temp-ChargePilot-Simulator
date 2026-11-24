"""Differential tests (ADR-019 Phase 3, PLAN.md Phase 3 mục 8): simulator standalone ↔ backend dùng CÙNG kernel.

Mỗi ca dựng hai phía từ cùng topology / policy / xe:
  - offline: `HybridSimulator` (CLI / benchmark) với `TimeConfig(physics_step_minutes=1)`;
  - backend: `HybridStation` (trạm sau Guard) với cùng trần quyết định.
Trước mỗi quyết định offline, kernel của trạm phải đề xuất ĐÚNG cùng gán cổng / setpoint / budget (cùng policy +
config + state ⇒ cùng plan). Sau đó trạm nhận ĐÚNG setpoint đã duyệt và chạy cùng số phút; năng lượng / SOC / mốc
hoàn thành của từng xe phải trùng (cùng setpoint + physics config ⇒ cùng kết quả thực thi). Số thứ tự khác biệt
tham chiếu PHASE0_FINDINGS §2.
"""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("ev2gym")

from src.models.decisions import TimeConfig  # noqa: E402
from src.models.events import EventType  # noqa: E402
from src.models.simulation import Incident, IncidentType  # noqa: E402
from src.models.simulation_core import Vehicle  # noqa: E402
from src.models.station_protocols import VehicleVisit  # noqa: E402
from src.optimizer.registry import POLICIES  # noqa: E402
from src.optimizer.zones import rolling_lp  # noqa: E402
from src.services import catalog  # noqa: E402
from src.simulator.core.algorithms import default_algorithms, resolve_algorithms  # noqa: E402
from src.simulator.hybrid import HybridSimulator  # noqa: E402
from src.simulator.hybrid_station import HybridStation  # noqa: E402
from tests.factories import NOW  # noqa: E402

TOL = 1e-9


class Recording(HybridSimulator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.approved = []

    def approve(self, proposal, *args, **kwargs):
        result = super().approve(proposal, *args, **kwargs)
        self.approved.append(result)
        return result


def _selection(policy: str) -> dict:
    dispatch, ac, dc, coordinator = POLICIES[policy]
    return {"dispatch": {"DC": dispatch}, "optimizers": {"AC": ac, "DC": dc}, "coordinator": coordinator}


def _visit(v: Vehicle) -> VehicleVisit:
    return VehicleVisit(
        booking_id=v.id,
        arrival_time=NOW + timedelta(minutes=v.arrival),
        departure_time=NOW + timedelta(minutes=v.departure),
        required_kwh=(v.target - v.initial_soc) * v.battery_kwh / 0.98,
        zone=v.zone,
        max_power_kw=v.max_kw,
        battery_kwh=v.battery_kwh,
        soc_now=v.initial_soc,
        soc_target=v.target,
    )


def _pair(vehicles, policy, *, timestep=5, horizon=180, config=None, limit_events=()):
    station = HybridStation(config or catalog.load_station_config(), start=NOW)
    scenario = replace(
        station.scenario, id="diff", end=horizon, timestep=timestep, vehicles=tuple(vehicles), limit_events=limit_events
    )
    if policy is None:
        algorithms = replace(default_algorithms(), dc_charging_model=station.adapter.dc_model)
    else:
        algorithms, _ = resolve_algorithms(_selection(policy), scenario, "differential")
    offline = Recording(scenario, algorithms=algorithms, time=TimeConfig(physics_step_minutes=1))
    station.configure(algorithms, policy or "default")
    station.kernel.time = TimeConfig(physics_step_minutes=1, decision_interval_minutes=timestep)
    for v in vehicles:
        station.upsert_vehicle(_visit(v))
    return offline, station, replace(station.scenario, end=horizon, limit_events=limit_events)


def _same(a, b) -> bool:
    return a.keys() == b.keys() and all(abs(a[k] - b[k]) <= TOL for k in a)


def _run(offline, station, scenario, *, hooks=None):
    """Chạy song song tới hết horizon. hooks: phút → hàm(offline, station) chạy trước quyết định tại phút đó."""
    decisions = 0
    hooks = dict(hooks or {})
    while not offline.finished:
        minute = offline.now
        assert station.minute == minute
        if minute in hooks:
            hooks.pop(minute)(offline, station)
        offline.observe()
        backend = station.kernel.propose(scenario=scenario)
        offline.step()
        ref = offline.approved[-1].proposal
        assert dict(backend.assignments) == dict(ref.assignments), minute
        assert _same(backend.setpoints_kw, ref.setpoints_kw), (minute, backend.setpoints_kw, ref.setpoints_kw)
        assert _same(backend.budgets.output_kw, ref.budgets.output_kw), minute
        assert backend.interval_end == ref.interval_end and backend.planning_interval_minutes == (
            ref.planning_interval_minutes
        ), minute
        station.kernel.apply_approved(station.kernel.approve(backend))
        station.step(offline.applied_results[-1].end - minute)
        decisions += 1
        _assert_same_execution(offline, station)
    assert not hooks, "hook chưa chạy"
    assert station.applied_constraint_violation_count == offline.applied_constraint_violation_count == 0
    return decisions


def _assert_same_execution(offline, station):
    offline.observe()  # trạm xử lý xe đến / rời ngay sau mỗi phút; offline làm ở đầu bước sau (idempotent)
    for vid, ref in offline.queue.sessions.items():
        got = station.queue.sessions[vid]
        assert abs(got.delivered_battery_kwh - ref.delivered_battery_kwh) <= TOL, vid
        assert abs(got.delivered_grid_kwh - ref.delivered_grid_kwh) <= TOL, vid
        assert abs(station.adapter.soc(vid) - offline.adapter.soc(vid)) <= TOL, vid
        for field in ("state", "connector", "charge_started", "completed_at", "departed_at"):
            assert getattr(got, field) == getattr(ref, field), (vid, field)


def _ac(vid, arrival=0, departure=150, soc=0.3, target=0.8, battery=60.0):
    return Vehicle(vid, "AC", arrival, departure, battery, soc, target, 11.0)


def _dc(vid, arrival=0, departure=90, soc=0.3, target=0.8, battery=80.0, cap=60.0):
    return Vehicle(vid, "DC", arrival, departure, battery, soc, target, cap)


CONGESTED = [
    _ac("ac1"),
    _ac("ac2", arrival=3, soc=0.75),  # đầy giữa interval (#2, #4)
    _ac("ac3", arrival=10, departure=60),  # chờ cổng rồi rời khi chưa sạc (#3)
    _dc("dc1", soc=0.55, target=0.95),  # vùng taper (#1)
    _dc("dc2", arrival=2),
    _dc("dc3", arrival=7, departure=40, soc=0.1, target=0.95),  # deadline bất khả thi
    _dc("dc4", arrival=20, departure=120),
]


@pytest.mark.parametrize("policy", [None, "B0", "M2b", "M3a", "M3b"])
def test_same_state_gives_the_same_proposal_and_the_same_execution(policy):
    offline, station, scenario = _pair(CONGESTED, policy)
    assert _run(offline, station, scenario) > 10
    assert any(s.completed_at is not None for s in offline.queue.sessions.values())
    assert offline.queue.sessions["dc3"].completed_at is None  # deadline bất khả thi vẫn đi cùng một đường


def test_independent_supply_is_planned_and_executed_identically():
    config = catalog.load_station_config().model_copy(
        update={"supply_mode": "independent", "independent_grid_input_limit_kw": {"AC": 22 / 0.95, "DC": 60 / 0.95}}
    )
    offline, station, scenario = _pair(CONGESTED, "M3b", config=config)
    assert not station.effective_limits().shared_supply
    _run(offline, station, scenario)


def test_site_curtailment_reaches_both_sides_through_the_same_effective_limits():
    """#6: offline = LimitEvent đã công bố; backend = sự cố POWER_LIMIT_CHANGE. Công bố = hiệu lực ⇒ cùng kết quả."""
    from src.models.simulation_core import LimitEvent

    event = LimitEvent(30, 30, 40.0, {})
    offline, station, scenario = _pair(CONGESTED, "M3a", limit_events=(event,))
    scenario = replace(scenario, limit_events=())

    def curtail(offline, station):
        station.inject_incident(Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=40))

    _run(offline, station, scenario, hooks={30: curtail})
    assert station.effective_limits().grid_input_kw == offline.effective_limits().grid_input_kw == 40


def test_connector_fault_uses_the_same_kernel_primitive_on_both_sides():
    """#17: cổng lỗi giữa chừng — xe về đầu hàng, cổng không được dispatch tới khi khôi phục."""
    offline, station, scenario = _pair(CONGESTED, "M3a")

    def fault(offline, station):
        offline.fault_port("DC-01/P1")
        events = station.inject_incident(Incident(type=IncidentType.CONNECTOR_FAULT, connector_id="DC-01-1"))
        assert events[0].type == EventType.CONNECTOR_FAULT

    def restore(offline, station):
        offline.restore_port("DC-01/P1")
        station.inject_incident(Incident(type=IncidentType.CONNECTOR_RESTORED, connector_id="DC-01-1"))

    _run(offline, station, scenario, hooks={15: fault, 45: restore})
    assert offline.queue.sessions["dc1"].last_connector is not None


def test_solver_fallback_follows_the_same_path(monkeypatch):
    """Rolling LP không tối ưu → cùng fallback equal share ở cả hai phía."""
    monkeypatch.setattr(rolling_lp, "linprog", lambda *a, **k: SimpleNamespace(status=1, x=None))
    offline, station, scenario = _pair(CONGESTED, "M2b")
    _run(offline, station, scenario)
    reasons = [a.proposal.diagnostics.get("DC", {}).get("fallback_reason") for a in offline.approved]
    assert any(reasons)  # fallback thật sự xảy ra (không phải "khớp vì cả hai cùng không chạy LP")


def test_compatibility_mode_differs_from_one_minute_physics_only_by_time_configuration():
    """P1: cùng code, hai cấu hình thời gian → số khác nhau (không so benchmark chéo); ZOH giữ golden."""
    vehicles = [_dc("dc1", soc=0.7, target=0.95)]  # vùng taper: ZOH 5' giữ acceptance đầu interval (#1)
    station = HybridStation(catalog.load_station_config(), start=NOW)
    scenario = replace(station.scenario, id="p1", end=10, timestep=5, vehicles=tuple(vehicles))
    zoh = HybridSimulator(scenario).run()
    one = HybridSimulator(scenario, time=TimeConfig(physics_step_minutes=1)).run()
    assert zoh["vehicles"][0]["delivered_battery_kwh"] != pytest.approx(one["vehicles"][0]["delivered_battery_kwh"])


# ---- Final Review 4.2: DC charging model theo tên registry offline (`DC_MODELS`), profile VinFast ------------------
# Offline (`HybridSimulator` + `vinfast_profiles_v0_1`) resolve profile từ danh sách xe biết trước; backend
# (`HybridStation.with_vinfast_profiles`) resolve khi xe được upsert. Cùng kịch bản ⇒ cùng gán cổng / setpoint /
# công suất / SOC từng phút (harness ở trên, quyết định mỗi phút ⇒ so từng phút). Xe đến động nhận đúng profile; bản
# fork admission không làm đổi bảng profile của trạm live; mặc định vẫn `SyntheticTaperV1()`.

from src.models.charging_physics import VehicleBatteryState  # noqa: E402
from src.simulator.core.algorithms import DC_MODELS  # noqa: E402
from src.simulator.core.charging_models.dc_charging_models import resolve_dc_profile  # noqa: E402
from src.simulator.core.charging_models.live_profiles import DynamicVehicleProfilesDCModel  # noqa: E402
from src.simulator.core.charging_models.synthetic_dc import SyntheticTaperV1  # noqa: E402
from src.simulator.core.charging_models.vehicle_profiles import VehicleProfilesDCModel  # noqa: E402

VINFAST = "vinfast_profiles_v0_1"


def _vf_dc(vid, model, battery, cap, arrival=0, departure=110, soc=0.2, target=0.85):
    return Vehicle(vid, "DC", arrival, departure, battery, soc, target, cap, model)


VF_FLEET = [
    Vehicle("ac1", "AC", 0, 150, 60.0, 0.3, 0.8, 11.0),
    _vf_dc("vf3", "VF3", 18.64, 24.0),
    _vf_dc("vf8", "VF8_NEW_2026", 60.13, 100.0, arrival=2, soc=0.1, target=0.9),
    _vf_dc("vf9", "VF9_123", 123.0, 60.0, arrival=5, departure=140, soc=0.35),
    _vf_dc("plain", None, 80.0, 60.0, arrival=20, departure=120),  # không nhãn ⇒ fallback synthetic ở cả hai phía
]


def _vf_visit(v: Vehicle) -> VehicleVisit:
    return VehicleVisit(
        booking_id=v.id,
        arrival_time=NOW + timedelta(minutes=v.arrival),
        departure_time=NOW + timedelta(minutes=v.departure),
        required_kwh=(v.target - v.initial_soc) * v.battery_kwh / 0.98,
        zone=v.zone,
        max_power_kw=v.max_kw,
        battery_kwh=v.battery_kwh,
        soc_now=v.initial_soc,
        soc_target=v.target,
        vehicle_model=v.vehicle_model,
    )


def _vinfast_pair(policy: str, timestep: int, horizon: int = 150):
    station = HybridStation.with_vinfast_profiles(catalog.load_station_config(), start=NOW)
    scenario = replace(station.scenario, id="vf-diff", end=horizon, timestep=timestep, vehicles=tuple(VF_FLEET))
    algorithms, metadata = resolve_algorithms(
        {**_selection(policy), "dc_charging_model": VINFAST}, scenario, "differential"
    )
    assert isinstance(algorithms.dc_charging_model, VehicleProfilesDCModel)  # offline: profile từ danh sách xe
    offline = Recording(scenario, algorithms=algorithms, time=TimeConfig(physics_step_minutes=1))
    station.configure(algorithms, policy)
    station.kernel.time = TimeConfig(physics_step_minutes=1, decision_interval_minutes=timestep)
    for v in VF_FLEET:
        station.upsert_vehicle(_vf_visit(v))
    return offline, station, replace(station.scenario, end=horizon), metadata


@pytest.mark.parametrize(("policy", "timestep"), [("B0", 1), ("M2b", 5)])
def test_backend_vinfast_profiles_match_offline_minute_by_minute(policy, timestep):
    """timestep 1 ⇒ mỗi quyết định = 1 phút: _run so gán cổng / setpoint / budget, rồi năng lượng + SOC từng xe."""
    offline, station, scenario, metadata = _vinfast_pair(policy, timestep)
    live = station.adapter.dc_model
    assert isinstance(live, DynamicVehicleProfilesDCModel)
    assert set(live.profiles) == {"vf3", "vf8", "vf9"} == set(offline.adapter.dc_model.profiles)
    assert dict(live.profiles) == dict(offline.adapter.dc_model.profiles)  # cùng profile (dataclass frozen)
    assert metadata["dc_charging_model"]["name"] == VINFAST
    decisions = _run(offline, station, scenario)
    assert decisions >= (100 if timestep == 1 else 20)
    if timestep == 1:
        # Công suất thực từng phút: AppliedResult của offline (mỗi bước = 1 phút) = các phút của trạm.
        applied = station.drain_applied()
        assert len(applied) == len(offline.applied_results)
        for ref, got in zip(offline.applied_results, applied, strict=True):
            assert (got.minute, got.end) == (ref.minute, ref.end)
            assert got.actual_kw.keys() == ref.actual_kw.keys(), ref.minute
            assert all(abs(got.actual_kw[v] - ref.actual_kw[v]) <= 1e-9 for v in ref.actual_kw), ref.minute
    assert any(s.completed_at is not None for vid, s in offline.queue.sessions.items() if vid.startswith("vf"))


def test_profiles_change_the_physics_compared_to_synthetic():
    """Đối chứng: test parity trên không vô nghĩa — profile VinFast cho kết quả khác SyntheticTaperV1."""
    vinfast = HybridStation.with_vinfast_profiles(catalog.load_station_config(), start=NOW)
    synthetic = HybridStation(catalog.load_station_config(), start=NOW)
    vf8 = _vf_dc("vf8", "VF8_NEW_2026", 60.13, 100.0, soc=0.1, target=0.9)
    for station in (vinfast, synthetic):
        station.upsert_vehicle(_vf_visit(vf8))
    state = VehicleBatteryState("vf8", 100.0, 60.13, 0.1 * 60.13, 0.9 * 60.13)
    assert vinfast.adapter.dc_model.acceptance_kw(state) != synthetic.adapter.dc_model.acceptance_kw(state)


def test_default_station_keeps_synthetic_taper():
    station = HybridStation(catalog.load_station_config(), start=NOW)
    assert station.dc_model_name is None
    assert type(station.adapter.dc_model) is SyntheticTaperV1
    assert station.kernel.algorithms.dc_charging_model is station.adapter.dc_model


def test_vehicle_arriving_later_gets_its_profile_on_upsert():
    station = HybridStation.with_vinfast_profiles(catalog.load_station_config(), start=NOW)
    model = station.adapter.dc_model
    assert dict(model.profiles) == {}  # trạm live không biết xe nào trước
    station.step(30)
    late = _vf_dc("late-vf8", "VF8_NEW_2026", 60.13, 100.0, arrival=40, departure=160)
    station.upsert_vehicle(_vf_visit(late))
    expected = resolve_dc_profile("VF8_NEW_2026", unknown_battery_kwh=60.13, unknown_reference_max_kw=100.0)
    assert model.profiles["late-vf8"] == expected
    state = VehicleBatteryState("late-vf8", 100.0, 60.13, 0.2 * 60.13, 0.85 * 60.13)
    assert model.acceptance_kw(state) == min(100.0, expected.acceptance_kw(0.2))
    # Xe lạ: profile UNKNOWN tham số hoá như offline; xe sai dung lượng pin: fallback synthetic + ghi lý do.
    station.upsert_vehicle(_vf_visit(_vf_dc("odd", "LAMBO-X", 77.0, 50.0, arrival=40, departure=160)))
    assert model.profiles["odd"].confidence == "low_unknown_ev"
    station.upsert_vehicle(_vf_visit(_vf_dc("wrong-battery", "VF3", 30.0, 24.0, arrival=40, departure=160)))
    assert "wrong-battery" not in model.profiles and "wrong-battery" in model.unresolved
    station.remove_vehicle("late-vf8")  # chưa đến ⇒ quên hẳn xe, kể cả profile
    assert "late-vf8" not in model.profiles


def test_strict_provider_refuses_a_mismatched_profile():
    model = DynamicVehicleProfilesDCModel(strict=True)
    station = HybridStation(catalog.load_station_config(), start=NOW, dc_model=model)
    with pytest.raises(ValueError, match="does not match"):
        station.upsert_vehicle(_vf_visit(_vf_dc("wrong-battery", "VF3", 30.0, 24.0)))


def test_fork_registers_what_if_vehicles_without_touching_live():
    station = HybridStation.with_vinfast_profiles(catalog.load_station_config(), start=NOW)
    station.upsert_vehicle(_vf_visit(_vf_dc("vf3", "VF3", 18.64, 24.0)))
    twin = station.fork()
    twin.upsert_vehicle(_vf_visit(_vf_dc("quote-vf9", "VF9_123", 123.0, 60.0)))
    assert "quote-vf9" in twin.adapter.dc_model.profiles
    assert set(station.adapter.dc_model.profiles) == {"vf3"}
    assert twin.adapter.dc_model is not station.adapter.dc_model
    assert twin.kernel.adapter.dc_model is twin.adapter.dc_model


def test_unknown_model_name_and_double_choice_are_refused():
    config = catalog.load_station_config()
    with pytest.raises(ValueError, match="Unknown dc_charging_model"):
        HybridStation(config, start=NOW, dc_charging_model="khong_co")
    with pytest.raises(ValueError, match="không cả hai"):
        HybridStation(config, start=NOW, dc_model=SyntheticTaperV1(), dc_charging_model=VINFAST)
    assert set(DC_MODELS) >= {"synthetic_taper_v1", VINFAST}


def test_config_planning_block_selects_the_dc_model_for_backend_runs():
    """station.yaml `planning.dc_charging_model` ⇒ make_station / build_sim_runtime dùng profile; booking thật
    (`visit_of` lấy dung lượng pin từ danh mục xe) nhận đúng profile."""
    from src.models.station import PlanningPolicyConfig
    from src.services import simulation_service
    from src.services.runtime import build_sim_runtime, make_station, visit_of

    base = catalog.load_station_config()
    config = base.model_copy(update={"planning": PlanningPolicyConfig(dc_charging_model=VINFAST)})
    assert type(make_station(base, NOW).adapter.dc_model) is SyntheticTaperV1
    scenario = catalog.load_scenario("hybrid_evening")
    rt = build_sim_runtime(scenario, "M3a", config, catalog.load_tariff(), NOW)
    assert isinstance(rt.simulator.adapter.dc_model, DynamicVehicleProfilesDCModel)
    assert rt.scheduler.metadata["dc_charging_model"]["name"] == VINFAST
    assert rt.scheduler.algorithms().dc_charging_model is rt.simulator.adapter.dc_model
    bookings = [b for b in simulation_service.generate_bookings(scenario, config, NOW) if b.request.zone == "DC"]
    assert bookings
    for booking in bookings:
        rt.simulator.upsert_vehicle(visit_of(booking, NOW))
    profiles = rt.simulator.adapter.dc_model.profiles
    assert {profiles[b.booking_id].model for b in bookings} <= {"VF3", "VF8_NEW_2026", "VF9_123"}
    assert not rt.simulator.adapter.dc_model.unresolved
