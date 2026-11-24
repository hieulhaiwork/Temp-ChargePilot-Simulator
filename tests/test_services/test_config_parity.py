"""Final Acceptance §3 — config parity + experiment provenance.

Cùng policy + cùng config ⇒ runtime live, benchmark (`build_sim_runtime`) và admission (`fork_runtime`) dựng CÙNG thuật
toán với CÙNG tham số optimizer (`planning.parameters` của station.yaml), và cho cùng kết quả trong cùng điều kiện.
"""

from datetime import datetime

import pytest

pytest.importorskip("ev2gym")

from src.models.station import PlanningPolicyConfig  # noqa: E402
from src.services import catalog  # noqa: E402
from src.services.runtime import (  # noqa: E402
    build_sim_runtime,
    fork_runtime,
    live_policy,
    make_scheduler,
    make_station,
    policy_parameters,
)
from tests.factories import NOW  # noqa: E402

# Tham số KHÁC mặc định (rolling_lp: horizon 120', AC LP mặc định của registry) — đủ để đổi lịch.
TUNED = {"optimizer_dc": {"horizon_minutes": 30}}


def _config(policy_id: str | None = "M2b", parameters: dict | None = None):
    planning = PlanningPolicyConfig(policy_id=policy_id, parameters=TUNED if parameters is None else parameters)
    return catalog.load_station_config().model_copy(update={"planning": planning})


def _scenario(**update):
    return catalog.load_scenario("hybrid_evening").model_copy(update={"duration_hours": 6, "n_vehicles": 6, **update})


def _start(scenario) -> datetime:
    return datetime.combine(NOW.date(), scenario.start_time, tzinfo=NOW.tzinfo)


# ---- §3.1 build_sim_runtime truyền tham số như runtime live -------------------------------------------------------------


def test_benchmark_runtime_gets_the_live_parameters():
    config = _config()
    scenario = _scenario()
    live_id, live_params = live_policy(config)
    assert (live_id, live_params) == ("M2b", TUNED)
    rt = build_sim_runtime(scenario, "M2b", config, catalog.load_tariff(), _start(scenario))
    assert rt.scheduler.parameters == live_params
    assert rt.scheduler.algorithms().optimizers["DC"].config.horizon_minutes == 30
    # live dựng scheduler bằng đúng live_policy (get_runtime) ⇒ cùng tham số
    live = make_scheduler(live_id, lambda: make_station(config, NOW), parameters=live_params or None)
    assert live.parameters == rt.scheduler.parameters
    assert live.metadata["optimizers"] == rt.scheduler.metadata["optimizers"]


def test_other_policies_keep_registry_defaults_and_explicit_parameters_win():
    config = _config()
    scenario = _scenario()
    tariff, start = catalog.load_tariff(), _start(scenario)
    assert policy_parameters(config, "B0") == {}  # tham số của M2b không áp lên equal_share của B0
    b0 = build_sim_runtime(scenario, "B0", config, tariff, start)
    assert b0.scheduler.parameters == {}
    default = build_sim_runtime(scenario, "M2b", config, tariff, start, parameters={})
    assert default.scheduler.algorithms().optimizers["DC"].config.horizon_minutes == 120
    # không có khối planning ⇒ như cũ
    plain = catalog.load_station_config()
    assert policy_parameters(plain, "M3a") == {}
    assert build_sim_runtime(scenario, "M3a", plain, tariff, start).scheduler.parameters == {}


def test_admission_fork_keeps_the_parameters():
    config = _config()
    scenario = _scenario()
    rt = build_sim_runtime(scenario, "M2b", config, catalog.load_tariff(), _start(scenario))
    frt = fork_runtime(rt, [])
    assert frt.scheduler.parameters == rt.scheduler.parameters == TUNED
    assert frt.scheduler.algorithms().optimizers["DC"].config.horizon_minutes == 30
