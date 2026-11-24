"""Final Review 4.2 — HybridStation chọn DC charging model theo tên registry offline (`DC_MODELS`), profile VinFast.

Offline (`HybridSimulator` + `vinfast_profiles_v0_1`) resolve profile từ danh sách xe biết trước; backend
(`HybridStation.with_vinfast_profiles`) resolve khi xe được upsert. Cùng kịch bản ⇒ cùng gán cổng / setpoint /
công suất / SOC từng phút (harness của `test_differential.py`, quyết định mỗi phút ⇒ so từng phút). Xe đến động nhận
đúng profile; bản fork admission không làm đổi bảng profile của trạm live; mặc định vẫn `SyntheticTaperV1()`.
"""

from dataclasses import replace
from datetime import timedelta

import pytest

pytest.importorskip("ev2gym")

from src.models.charging_physics import VehicleBatteryState  # noqa: E402
from src.models.decisions import TimeConfig  # noqa: E402
from src.models.simulation_core import Vehicle  # noqa: E402
from src.models.station_protocols import VehicleVisit  # noqa: E402
from src.services import catalog  # noqa: E402
from src.simulator.core.algorithms import DC_MODELS, resolve_algorithms  # noqa: E402
from src.simulator.core.charging_models.dc_charging_models import resolve_dc_profile  # noqa: E402
from src.simulator.core.charging_models.live_profiles import DynamicVehicleProfilesDCModel  # noqa: E402
from src.simulator.core.charging_models.synthetic_dc import SyntheticTaperV1  # noqa: E402
from src.simulator.core.charging_models.vehicle_profiles import VehicleProfilesDCModel  # noqa: E402
from src.simulator.hybrid_station import HybridStation  # noqa: E402
from tests.factories import NOW  # noqa: E402
from tests.test_refactor.test_differential import Recording, _run, _selection  # noqa: E402

VINFAST = "vinfast_profiles_v0_1"


def _dc(vid, model, battery, cap, arrival=0, departure=110, soc=0.2, target=0.85):
    return Vehicle(vid, "DC", arrival, departure, battery, soc, target, cap, model)


FLEET = [
    Vehicle("ac1", "AC", 0, 150, 60.0, 0.3, 0.8, 11.0),
    _dc("vf3", "VF3", 18.64, 24.0),
    _dc("vf8", "VF8_NEW_2026", 60.13, 100.0, arrival=2, soc=0.1, target=0.9),
    _dc("vf9", "VF9_123", 123.0, 60.0, arrival=5, departure=140, soc=0.35),
    _dc("plain", None, 80.0, 60.0, arrival=20, departure=120),  # không nhãn ⇒ fallback synthetic ở cả hai phía
]


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
        vehicle_model=v.vehicle_model,
    )


def _vinfast_pair(policy: str, timestep: int, horizon: int = 150):
    station = HybridStation.with_vinfast_profiles(catalog.load_station_config(), start=NOW)
    scenario = replace(station.scenario, id="vf-diff", end=horizon, timestep=timestep, vehicles=tuple(FLEET))
    algorithms, metadata = resolve_algorithms(
        {**_selection(policy), "dc_charging_model": VINFAST}, scenario, "differential"
    )
    assert isinstance(algorithms.dc_charging_model, VehicleProfilesDCModel)  # offline: profile từ danh sách xe
    offline = Recording(scenario, algorithms=algorithms, time=TimeConfig(physics_step_minutes=1))
    station.configure(algorithms, policy)
    station.kernel.time = TimeConfig(physics_step_minutes=1, decision_interval_minutes=timestep)
    for v in FLEET:
        station.upsert_vehicle(_visit(v))
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
    vf8 = _dc("vf8", "VF8_NEW_2026", 60.13, 100.0, soc=0.1, target=0.9)
    for station in (vinfast, synthetic):
        station.upsert_vehicle(_visit(vf8))
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
    late = _dc("late-vf8", "VF8_NEW_2026", 60.13, 100.0, arrival=40, departure=160)
    station.upsert_vehicle(_visit(late))
    expected = resolve_dc_profile("VF8_NEW_2026", unknown_battery_kwh=60.13, unknown_reference_max_kw=100.0)
    assert model.profiles["late-vf8"] == expected
    state = VehicleBatteryState("late-vf8", 100.0, 60.13, 0.2 * 60.13, 0.85 * 60.13)
    assert model.acceptance_kw(state) == min(100.0, expected.acceptance_kw(0.2))
    # Xe lạ: profile UNKNOWN tham số hoá như offline; xe sai dung lượng pin: fallback synthetic + ghi lý do.
    station.upsert_vehicle(_visit(_dc("odd", "LAMBO-X", 77.0, 50.0, arrival=40, departure=160)))
    assert model.profiles["odd"].confidence == "low_unknown_ev"
    station.upsert_vehicle(_visit(_dc("wrong-battery", "VF3", 30.0, 24.0, arrival=40, departure=160)))
    assert "wrong-battery" not in model.profiles and "wrong-battery" in model.unresolved
    station.remove_vehicle("late-vf8")  # chưa đến ⇒ quên hẳn xe, kể cả profile
    assert "late-vf8" not in model.profiles


def test_strict_provider_refuses_a_mismatched_profile():
    model = DynamicVehicleProfilesDCModel(strict=True)
    station = HybridStation(catalog.load_station_config(), start=NOW, dc_model=model)
    with pytest.raises(ValueError, match="does not match"):
        station.upsert_vehicle(_visit(_dc("wrong-battery", "VF3", 30.0, 24.0)))


def test_fork_registers_what_if_vehicles_without_touching_live():
    station = HybridStation.with_vinfast_profiles(catalog.load_station_config(), start=NOW)
    station.upsert_vehicle(_visit(_dc("vf3", "VF3", 18.64, 24.0)))
    twin = station.fork()
    twin.upsert_vehicle(_visit(_dc("quote-vf9", "VF9_123", 123.0, 60.0)))
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
