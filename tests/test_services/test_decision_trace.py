"""DecisionTrace backend (ADR-019 Phase 4, quyết định 6): cùng schema / facts với simulator, correlation ID, replay.

Chạy runtime mô phỏng (đúng đường control_loop → Guard → HybridStation của benchmark) trên `hybrid_evening`, rồi:
  - facts `decision` có ĐÚNG schema của `evaluation/trace.decision_record` (so với DecisionTrace của HybridSimulator);
  - mọi Command mang correlation_id của trace sinh ra nó;
  - replay Physical Guard từ trace (không cần trạm) cho cùng phán quyết; trace bị sửa vượt giới hạn thì bị từ chối;
  - năng lượng của các trace cộng lại = năng lượng trạm đo được (không mất / không đếm trùng bước vật lý);
  - trace là JSON thuần, không chứa resident_id / token.
"""

import json
from datetime import datetime, timedelta

import pytest

pytest.importorskip("ev2gym")

from src.models.charging import StrategyName  # noqa: E402
from src.services import catalog, control_loop, decision_trace, simulation_service  # noqa: E402
from src.services.runtime import build_sim_runtime, visit_of  # noqa: E402
from tests.factories import NOW  # noqa: E402

MINUTES = 240


async def _run(minutes: int = MINUTES):
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(NOW.date(), scenario.start_time, tzinfo=NOW.tzinfo)
    bookings = simulation_service.generate_bookings(scenario, config, start)
    rt = build_sim_runtime(scenario, StrategyName.SIM_M3A, config, tariff, start)
    sim = rt.simulator
    pending = sorted(bookings, key=lambda b: (b.created_at, b.booking_id))
    carried = []
    from src.models.events import EventType, StationEvent

    for _ in range(minutes):
        now = sim.now
        events, carried = carried, []
        while pending and pending[0].created_at <= now:
            booking = pending.pop(0)
            rt.store.save_booking(booking)
            events += sim.upsert_vehicle(visit_of(booking, now))
            events.append(StationEvent(type=EventType.BOOKING_CREATED, occurred_at=now, booking_id=booking.booking_id))
        await control_loop.on_minute(rt, events)
        carried = sim.step(1)
    decision_trace.close_open(rt)
    return rt


@pytest.fixture(scope="module")
def run():
    from src.services.admission import run_sync

    return run_sync(_run())


def test_every_replan_leaves_one_closed_trace_with_a_correlation_id(run):
    traces = run.recorder.decision_traces
    assert len(traces) == len(run.recorder.replan_durations_s) > 10
    ids = [t["correlation_id"] for t in traces]
    assert len(set(ids)) == len(ids) and all(t["closed"] for t in traces)
    assert all(t["policy"] == {"id": "M3a", "version": "1"} for t in traces if t["decision"] is not None)
    assert all(t["time_config"]["physics_step_minutes"] == 1 for t in traces)


def test_commands_carry_the_correlation_id_of_their_trace(run):
    by_command = {c["command_id"]: t["correlation_id"] for t in run.recorder.decision_traces for c in t["commands"]}
    executed = list(run.recent_commands)
    assert executed
    for cmd in executed:
        assert cmd.correlation_id == by_command[cmd.command_id]


def test_decision_facts_use_the_simulator_decision_trace_schema(run):
    from src.models.simulation_core import Scenario
    from src.simulator.core.algorithms import resolve_algorithms
    from src.simulator.hybrid import HybridSimulator
    from src.simulator.run import SCENARIOS

    config = json.loads((SCENARIOS / "mvp1.json").read_text(encoding="utf-8"))
    scenario = Scenario.parse(config)
    algorithms, _ = resolve_algorithms(config.get("algorithms", {}), scenario, "test")
    offline = HybridSimulator(scenario, algorithms=algorithms, record_decisions=True).run()["decision_trace"][0]
    backend = next(t["decision"] for t in run.recorder.decision_traces if t["decision"] and t["decision"]["vehicles"])
    assert backend["schema_version"] == offline["schema_version"]
    assert backend.keys() == offline.keys()
    assert backend["guard"].keys() == offline["guard"].keys()
    assert next(iter(backend["vehicles"].values())).keys() >= next(iter(offline["vehicles"].values())).keys()


def test_physical_guard_replays_from_the_trace_alone(run):
    traces = [t for t in run.recorder.decision_traces if t["guard_inputs"] and t["approved_setpoints_kw"]]
    assert traces
    for trace in traces:
        assert decision_trace.replay_physical_guard(trace) is None, trace["correlation_id"]
        assert decision_trace.replay_commands(trace) == []
    # WHAT-IF / debug: vượt giới hạn cho phép của một xe ⇒ Guard từ chối, nêu lý do.
    trace = traces[-1]
    vid, row = next(iter(trace["guard_inputs"]["candidates"].items()))
    bad = {**trace["approved_setpoints_kw"], vid: row["allowed_kw"] + 1.0}
    assert "invalid power" in decision_trace.replay_physical_guard(trace, bad)


def test_applied_energy_of_all_traces_equals_the_measured_station_energy(run):
    traced = sum(kwh for t in run.recorder.decision_traces for kwh in t["applied"]["output_kwh"].values())
    measured = sum(run.simulator.kernel.output_kwh.values())
    assert traced == pytest.approx(measured, abs=1e-6) and measured > 0
    assert sum(t["applied"]["minutes"] for t in run.recorder.decision_traces) == MINUTES


def test_trace_separates_deviation_deadband_and_hard_violations(run):
    for trace in run.recorder.decision_traces:
        applied = trace["applied"]
        assert set(applied) >= {"budget_deviation_kw", "command_deadband_kw", "hard_violations", "stale_setpoint_kw"}
        assert applied["hard_violations"] == []
    summaries = [decision_trace.summary(t) for t in run.recorder.decision_traces]
    assert all(s.hard_violations == 0 and s.closed for s in summaries)


def test_trace_is_plain_json_without_personal_data(run):
    blob = json.dumps(run.recorder.decision_traces, ensure_ascii=False, allow_nan=False)
    assert "resident" not in blob and "token" not in blob.lower()


async def test_live_persist_writes_db_summary_and_jsonl_artifact(clean_db, tmp_path, monkeypatch, run):
    from src.config import get_settings
    from src.services import repository

    monkeypatch.setattr(get_settings(), "decision_trace_dir", str(tmp_path))
    trace = json.loads(json.dumps(run.recorder.decision_traces[-1]))
    decision_trace.persist({**trace, "closed": False}, False)
    stored = repository.get_decision_trace(trace["correlation_id"])
    assert stored is not None and not stored.closed and stored.artifact is None
    decision_trace.persist(trace, True)
    stored = repository.get_decision_trace(trace["correlation_id"])
    assert stored.closed and stored.artifact and (tmp_path / stored.artifact).exists()
    line = (tmp_path / stored.artifact).read_text(encoding="utf-8").splitlines()[-1]
    assert json.loads(line)["correlation_id"] == trace["correlation_id"]
    assert repository.list_decision_traces()[0].correlation_id == trace["correlation_id"]
    assert stored.decided_at - datetime.fromisoformat(trace["decided_at"]) == timedelta(0)
