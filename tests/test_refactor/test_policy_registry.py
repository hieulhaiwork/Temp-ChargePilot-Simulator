"""Final Review 4.1 — policy lấy từ registry: một policy HOÀN TOÀN MỚI chạy được trên backend không sửa orchestration.

Khác `test_registry_extension.py` (thay optimizer bằng cách tạm trỏ M2b sang implementation mới): ở đây đăng ký một id
policy mới ghép từ thành phần có sẵn (EDF + deadline_first DC), không đụng B0 / M2b / M3a / M3b, rồi chạy qua
`HybridStation` + `SimulatorScheduler` + control loop + Guard, qua `simulation_service` và qua API. Policy cũ giữ id,
version và thành phần.
"""

from datetime import datetime

import pytest

from src.models.charging import SchedulePlan, StrategyName
from src.models.control import Role
from src.optimizer import registry

NEW_ID = "T41-edf"
NEW_VERSION = "test-2"
NEW = registry.PolicySpec(NEW_ID, NEW_VERSION, "edf", "equal_share", "deadline_first", "fixed_share", "test 4.1")
FROZEN = {
    "B0": ("fcfs", "equal_share", "equal_share", "fixed_share"),
    "M2b": ("llf", "equal_share", "rolling_lp", "fixed_share"),
    "M3a": ("llf", "ac_rolling_lp", "rolling_lp", "fixed_share"),
    "M3b": ("llf", "ac_rolling_lp", "rolling_lp", "dynamic_slack"),
}


@pytest.fixture
def new_policy():
    spec = registry.register_policy(NEW)
    yield spec
    registry.unregister_policy(NEW_ID)


def _frozen_untouched() -> None:
    assert {pid: registry.POLICIES[pid] for pid in FROZEN} == FROZEN
    assert all(registry.policy_spec(pid).version == "1" for pid in FROZEN)


def _short(scenario_id: str, **update):
    from src.services import catalog

    return catalog.load_scenario(scenario_id).model_copy(update=update)


# ---- registry -------------------------------------------------------------------------------------------------------


def test_frozen_policies_keep_id_version_and_components():
    _frozen_untouched()
    assert [s.id for s in registry.policy_specs()][:4] == ["B0", "M2b", "M3a", "M3b"]
    assert all(registry.policy_spec(pid).frozen for pid in FROZEN)


@pytest.mark.parametrize("policy_id", list(FROZEN))
def test_registering_an_existing_id_is_refused(policy_id):
    """Không ghi đè M2b / M3a để thử optimizer mới — phá nghĩa baseline (Final Review 4.1)."""
    with pytest.raises(ValueError, match="đã đăng ký"):
        registry.register_policy(
            registry.PolicySpec(policy_id, "2", "edf", "equal_share", "equal_share", "fixed_share")
        )
    with pytest.raises(ValueError, match="đóng băng"):
        registry.unregister_policy(policy_id)
    _frozen_untouched()


def test_registering_unknown_components_is_refused():
    with pytest.raises(ValueError, match="chưa đăng ký"):
        registry.register_policy(registry.PolicySpec("T41-bad", "1", "edf", "equal_share", "khong_co", "fixed_share"))
    assert "T41-bad" not in registry.POLICIES


def test_new_policy_is_listed_with_its_own_version(new_policy):
    assert registry.policy_spec(NEW_ID) == NEW
    assert not new_policy.frozen
    _frozen_untouched()


# ---- HybridStation + planner (không sửa orchestration) ---------------------------------------------------------------


def test_planner_and_station_run_a_new_policy_end_to_end(new_policy):
    from src.services import catalog, control_loop
    from src.services.admission import run_sync
    from src.services.runtime import build_sim_runtime, make_scheduler, visit_of
    from src.services.simulation_service import generate_bookings
    from tests.factories import NOW

    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = _short("hybrid_evening")
    start = datetime.combine(NOW.date(), scenario.start_time, tzinfo=NOW.tzinfo)
    pending = sorted(generate_bookings(scenario, config, start), key=lambda b: (b.created_at, b.booking_id))
    rt = build_sim_runtime(scenario, NEW_ID, config, tariff, start)
    sim = rt.simulator
    assert (rt.scheduler.policy_id, rt.scheduler.policy_version) == (NEW_ID, NEW_VERSION)
    assert rt.scheduler.name == NEW_ID and not isinstance(rt.scheduler.name, StrategyName)
    assert (sim.kernel.policy_id, sim.kernel.policy_version) == (NEW_ID, NEW_VERSION)
    implementation = rt.scheduler.metadata["optimizers"]["DC"]["implementation"]
    assert implementation.endswith("deadline_first"), implementation
    assert rt.scheduler.metadata["dispatch"]["DC"]["name"] == "edf"

    async def drive() -> list[SchedulePlan]:
        plans, carried = [], []
        for _ in range(9 * 60):
            now, events, carried = sim.now, carried, []
            while pending and pending[0].created_at <= now:
                booking = pending.pop(0)
                rt.store.save_booking(booking)
                events += sim.upsert_vehicle(visit_of(booking, now))
            await control_loop.on_minute(rt, events)
            if rt.plan is not None and (not plans or plans[-1].version != rt.plan.version):
                plans.append(rt.plan)
            carried = sim.step(1)
        return plans

    plans = run_sync(drive())
    assert plans, "policy mới phải sinh lịch"
    assert all(p.policy_id == NEW_ID and p.policy_version == NEW_VERSION and p.strategy is None for p in plans)
    assert max(c.power_kw for c in sim.state().connectors) >= 0
    assert sum(sim.kernel.output_kwh.values()) > 0, "policy mới phải cấp điện thật qua dispatcher"
    assert sim.applied_constraint_violation_count == 0
    assert rt.recorder.decision_traces or rt.open_trace is not None
    # Không có danh sách cứng: make_scheduler nhận id mới, từ chối id lạ bằng lỗi nghiệp vụ.
    assert make_scheduler(NEW_ID, lambda: sim).policy_id == NEW_ID
    from src.services.errors import DomainError

    with pytest.raises(DomainError):
        make_scheduler("khong-co", lambda: sim)
    _frozen_untouched()


def test_simulation_service_runs_new_and_old_policy_side_by_side(new_policy):
    """Đăng ký policy mới không đổi kết quả policy cũ (cùng kịch bản, cùng seed)."""
    from src.services import simulation_service

    scenario = _short("hybrid_evening", duration_hours=10, n_vehicles=6)
    reference = simulation_service.run_scenario(scenario, StrategyName.SIM_M3A)
    new = simulation_service.run_scenario(scenario, NEW_ID)
    again = simulation_service.run_scenario(scenario, StrategyName.SIM_M3A)
    assert (new.policy_id, new.policy_version, new.strategy) == (NEW_ID, NEW_VERSION, None)
    assert (reference.policy_id, reference.policy_version, reference.strategy) == ("M3a", "1", StrategyName.SIM_M3A)
    timing = {"replan_p95_seconds"}
    assert again.kpis.model_dump(exclude=timing) == reference.kpis.model_dump(exclude=timing)
    assert again.notes == reference.notes
    assert new.kpis.power_limit_violations == 0


# ---- config (station.yaml `planning:` tuỳ chọn) ------------------------------------------------------------------------


def test_missing_planning_block_keeps_live_strategy(monkeypatch):
    from src.services import catalog
    from src.services.runtime import live_policy

    config = catalog.load_station_config()
    assert config.planning is None  # station.yaml hiện hành không khai khối này
    assert live_policy(config) == ("M3a", {})


def test_planning_block_selects_policy_version_and_parameters(new_policy):
    from src.models.station import PlanningPolicyConfig
    from src.services import catalog
    from src.services.hybrid_planner import selection
    from src.services.runtime import live_policy

    base = catalog.load_station_config()
    config = base.model_copy(update={"planning": PlanningPolicyConfig(policy_id=NEW_ID, version=NEW_VERSION)})
    assert live_policy(config) == (NEW_ID, {})
    wrong = base.model_copy(update={"planning": PlanningPolicyConfig(policy_id="M3a", version="2")})
    with pytest.raises(ValueError, match="không khớp version"):
        live_policy(wrong)
    tuned = PlanningPolicyConfig(policy_id="M2b", parameters={"optimizer_dc": {"horizon_minutes": 60}})
    policy_id, parameters = live_policy(base.model_copy(update={"planning": tuned}))
    assert selection(policy_id, parameters)["optimizers"]["DC"] == {
        "name": "rolling_lp",
        "parameters": {"horizon_minutes": 60},
    }
    assert selection("M2b") == {
        "dispatch": {"DC": "llf"},
        "optimizers": {"AC": "equal_share", "DC": "rolling_lp"},
        "coordinator": "fixed_share",
    }
    with pytest.raises(ValueError, match="planning.parameters"):
        PlanningPolicyConfig(parameters={"khong_co": {}})


def test_planning_parameters_reach_the_optimizer():
    from src.services import catalog
    from src.services.runtime import make_scheduler, make_station
    from tests.factories import NOW

    station = make_station(catalog.load_station_config(), NOW)
    tuned = make_scheduler("M2b", lambda: station, parameters={"optimizer_dc": {"horizon_minutes": 60}})
    assert tuned.metadata["optimizers"]["DC"]["parameters"]["horizon_minutes"] == 60
    assert tuned.algorithms().optimizers["DC"].config.horizon_minutes == 60
    default = make_scheduler("M2b", lambda: make_station(catalog.load_station_config(), NOW))
    assert default.metadata["optimizers"]["DC"]["parameters"]["horizon_minutes"] == 120


# ---- hợp đồng (tương thích ngược) ---------------------------------------------------------------------------------------


def test_policy_fields_are_backward_compatible():
    from src.db.mappers import plan_to_row
    from src.models.api import SimulationRunRequest
    from tests.factories import NOW

    old = SchedulePlan(version=1, strategy=StrategyName.SIM_M3A, created_at=NOW, horizon_start=NOW, step_minutes=15)
    assert old.policy_id == "M3a" and old.strategy is StrategyName.SIM_M3A
    assert SchedulePlan.model_validate(old.model_dump(mode="json")) == old
    legacy_payload = {"version": 1, "strategy": "B0", "created_at": NOW, "horizon_start": NOW, "step_minutes": 15}
    assert SchedulePlan.model_validate(legacy_payload).policy_id == "B0"
    by_id = SchedulePlan(version=1, policy_id="M2b", created_at=NOW, horizon_start=NOW, step_minutes=15)
    assert by_id.strategy is StrategyName.SIM_M2B
    new = SchedulePlan(version=1, policy_id="T41-very-long-id", created_at=NOW, horizon_start=NOW, step_minutes=15)
    assert new.strategy is None
    assert plan_to_row(old).strategy == "M3a" and plan_to_row(new).strategy == "custom"
    assert plan_to_row(new).payload["policy_id"] == "T41-very-long-id"
    with pytest.raises(ValueError):
        SchedulePlan(version=1, strategy="M3a", policy_id="B0", created_at=NOW, horizon_start=NOW, step_minutes=15)
    with pytest.raises(ValueError):
        SchedulePlan(version=1, created_at=NOW, horizon_start=NOW, step_minutes=15)
    request = SimulationRunRequest.model_validate({"scenario_id": "peak_evening", "strategy": "M3a"})
    assert (request.strategy, request.policy_id, request.strict_incidents) == (StrategyName.SIM_M3A, "M3a", None)
    assert SimulationRunRequest(scenario_id="x", policy_id=NEW_ID).strategy is None
    with pytest.raises(ValueError):
        SimulationRunRequest(scenario_id="x")


# ---- API ---------------------------------------------------------------------------------------------------------------


async def test_policies_endpoint_reads_the_registry(client, as_role, new_policy):
    as_role(Role.OPERATOR)
    response = await client.get("/api/v1/simulation/policies")
    assert response.status_code == 200
    rows = {row["policy_id"]: row for row in response.json()}
    assert list(rows) == list(registry.POLICIES)
    assert rows["M3a"] == {
        "policy_id": "M3a",
        "version": "1",
        "dispatch_dc": "llf",
        "optimizer_ac": "ac_rolling_lp",
        "optimizer_dc": "rolling_lp",
        "coordinator": "fixed_share",
        "description": "LLF + AC/DC LP + Fixed Share",
        "frozen": True,
        "legacy_strategy": "M3a",
    }
    assert rows[NEW_ID]["version"] == NEW_VERSION
    assert rows[NEW_ID]["frozen"] is False and rows[NEW_ID]["legacy_strategy"] is None


async def test_policies_endpoint_needs_operator(client, as_role):
    as_role(Role.RESIDENT)
    response = await client.get("/api/v1/simulation/policies")
    assert response.status_code == 403


async def test_run_endpoint_accepts_a_new_policy_id(client, as_role, new_policy):
    as_role(Role.OPERATOR)
    body = {"scenario_id": "hybrid_evening", "policy_id": NEW_ID, "n_vehicles": 3}
    response = await client.post("/api/v1/simulation/runs", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["policy_id"], data["policy_version"], data["strategy"]) == (NEW_ID, NEW_VERSION, None)
    assert data["kpis"]["power_limit_violations"] == 0
    unknown = await client.post("/api/v1/simulation/runs", json={"scenario_id": "hybrid_evening", "policy_id": "zz"})
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "not_found"
