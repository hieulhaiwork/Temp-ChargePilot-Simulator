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
