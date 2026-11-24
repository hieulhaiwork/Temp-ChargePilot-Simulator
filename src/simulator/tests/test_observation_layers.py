"""Final Review §4.3 — ground truth vs observed / estimated state (chống leakage).

Mô hình quan sát lệch cố định (SOC thật − 0,1, mẫu trễ 5 phút): dispatch và optimizer chỉ thấy SOC ước lượng; vật lý,
hoàn thành phiên và KPI dùng SOC thật của EV2Gym. Mặc định `PerfectObservation` = identity ⇒ kết quả cũ y hệt.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.models.scheduling.observations import (
    EstimatedVehicleObservation,
    ObservationModel,
    PerfectObservation,
    SocEstimate,
    estimated,
)
from src.models.simulation_core import Scenario
from src.optimizer.dispatch.arrival_order import arrival_order
from src.optimizer.dispatch.least_laxity import least_laxity
from src.optimizer.zones.equal_share import zone_equal_share
from src.simulator.core.algorithms import default_algorithms
from src.simulator.hybrid import HybridSimulator

FIXTURE = Path(__file__).resolve().parents[1] / "scenario/mvp1.json"
BIAS = 0.1
DELAY = 5


@pytest.fixture
def scenario():
    return Scenario.parse(json.loads(FIXTURE.read_bytes()))


class BiasedTelemetry:
    """SOC đo lệch −BIAS, mẫu cũ DELAY phút. Không trạng thái (deterministic) — chỉ để kiểm đường dữ liệu."""

    __stateless__ = True

    def observe(self, minute, truth):
        return {
            vid: estimated(row, SocEstimate(max(0.0, row.soc - BIAS), measured_at=minute - DELAY, uncertainty=0.05))
            for vid, row in truth.items()
        }


def _spy_run(scenario, observation_model):
    """Chạy mvp1 với dispatch LLF + equal share được bọc spy; ghi (SOC planner thấy, SOC thật lúc đó)."""
    seen = []
    holder = {}

    def record(kind, vehicles, minute):
        for vid, row in vehicles.items():
            seen.append((kind, minute, vid, row, holder["sim"].adapter.soc(vid)))

    def dispatch(observation):
        record("dispatch", observation.vehicles, observation.minute)
        return (least_laxity if observation.zone == "DC" else arrival_order)(observation)

    def optimizer(observation, zone, budget_kw):
        record("optimizer", observation.vehicles, observation.minute)
        return zone_equal_share(observation, zone, budget_kw)

    algorithms = replace(
        default_algorithms(), dispatch={"AC": dispatch, "DC": dispatch}, optimizers={"AC": optimizer, "DC": optimizer}
    )
    sim = HybridSimulator(scenario, algorithms=algorithms, observation_model=observation_model)
    holder["sim"] = sim
    return sim, sim.run(), seen


def test_planner_receives_only_the_observed_soc(scenario):
    sim, _, seen = _spy_run(scenario, BiasedTelemetry())
    assert {kind for kind, *_ in seen} == {"dispatch", "optimizer"}
    leaked = 0
    for _kind, minute, _vid, row, truth in seen:
        assert isinstance(row, EstimatedVehicleObservation)
        assert row.soc == row.estimate.value == pytest.approx(max(0.0, truth - BIAS), abs=1e-12)
        assert row.estimate.measured_at == minute - DELAY and row.estimate.uncertainty == 0.05
        leaked += abs(row.soc - truth) < 1e-12
    assert leaked == 0, "optimizer / dispatch nhận đúng SOC thật — lớp quan sát bị bỏ qua"


def test_physics_and_kpi_keep_using_ground_truth(scenario):
    sim, result, _ = _spy_run(scenario, BiasedTelemetry())
    rows = {row["id"]: row for row in result["vehicles"]}
    for vid, session in sim.queue.sessions.items():
        truth = sim.adapter.soc(vid)
        assert rows[vid]["soc"] == truth  # báo cáo KPI = SOC thật của EV2Gym
        if session.completed_at is not None:
            # hoàn thành đo bằng SOC thật: lúc đó SOC quan sát (thật − 0,1) vẫn dưới target
            assert truth >= session.vehicle.target - 1e-10
            assert truth - BIAS < session.vehicle.target
    assert result["completed_on_time"] > 0


def test_perfect_observation_is_identity_and_keeps_results(scenario):
    truth = {"x": object()}
    assert PerfectObservation().observe(0, truth) is truth
    assert isinstance(PerfectObservation(), ObservationModel)
    baseline = HybridSimulator(scenario).run()
    assert HybridSimulator(scenario, observation_model=PerfectObservation()).run() == baseline
    sim = HybridSimulator(scenario)
    sim.observe()
    view = sim._view()
    assert all(type(row).__name__ == "VehicleObservation" for row in view.values())


def test_observation_model_may_only_change_the_soc(scenario):
    class MovesVehicles:
        def observe(self, minute, truth):
            return {vid: replace(row, connector="DC-01/P9") for vid, row in truth.items()}

    class DropsVehicles:
        def observe(self, minute, truth):
            return dict(list(truth.items())[1:])

    for model in (MovesVehicles(), DropsVehicles()):
        sim = HybridSimulator(scenario, observation_model=model)
        with pytest.raises(ValueError, match="observation model"):
            sim.step()


def test_soc_estimate_is_validated():
    with pytest.raises(ValueError):
        SocEstimate(1.2, measured_at=0)
    with pytest.raises(ValueError):
        SocEstimate(0.5, measured_at=0, uncertainty=-1)
