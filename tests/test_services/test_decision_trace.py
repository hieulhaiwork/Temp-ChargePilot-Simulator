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


def test_foundation_full_trace_is_retrievable_with_default_config(clean_db, monkeypatch, run):
    from src.config import get_settings
    from src.services import repository

    monkeypatch.setattr(get_settings(), "decision_trace_dir", "")
    trace = json.loads(json.dumps(run.recorder.decision_traces[-1]))
    cid = trace["correlation_id"]
    decision_trace.persist(trace, True)
    repository.dispose()
    stored = repository.get_full_decision_trace(cid)
    assert stored == trace
    assert repository.get_decision_trace(cid).artifact is None


def test_foundation_trace_lifecycle_index_and_old_summary(clean_db, run):
    from src.models.decision_trace import TRACE_SCHEMA
    from src.services import repository

    trace = next(t for t in run.recorder.decision_traces if t["booking_ids"] and t["closed"])
    cid, booking_id = trace["correlation_id"], trace["booking_ids"][0]
    decided_at = datetime.fromisoformat(trace["decided_at"])
    end = decided_at + timedelta(minutes=1)
    active = {**trace, "closed": False, "decision": None, "applied": None}
    decision_trace.persist(active, False)
    assert repository.get_full_decision_trace(cid)["trace_schema"] == TRACE_SCHEMA
    assert repository.list_full_decision_traces(decided_at, end, booking_id=booking_id, closed=False) == [active]
    decision_trace.persist(trace, True)
    decision_trace.persist(active, False)
    decision_trace.persist(trace, True)
    repository.dispose()
    assert repository.get_full_decision_trace(cid) == trace
    assert repository.list_full_decision_traces(decided_at, end, booking_id=booking_id, closed=True) == [trace]
    assert repository.list_full_decision_traces(decided_at - timedelta(minutes=1), decided_at) == []
    assert repository.list_full_decision_traces(decided_at, end, booking_id="unknown") == []
    with pytest.raises(ValueError, match="limit"):
        repository.list_full_decision_traces(decided_at, end, limit=101)

    legacy = decision_trace.summary(trace).model_copy(update={"correlation_id": "legacy"})
    repository.save_decision_trace(legacy)
    assert repository.get_decision_trace("legacy") == legacy
    assert repository.get_full_decision_trace("legacy") is None
    assert repository.get_full_decision_trace("missing") is None
    assert repository.list_full_decision_traces(decided_at, end) == [trace]


def test_foundation_trace_write_and_export_errors_are_isolated(clean_db, monkeypatch, tmp_path, caplog, run):
    from src.config import get_settings
    from src.services import repository

    trace = run.recorder.decision_traces[-1]
    invalid = {**trace, "correlation_id": "invalid", "applied": {**trace["applied"], "extra": float("nan")}}
    decision_trace.persist(invalid, True)
    assert repository.get_full_decision_trace("invalid") is None
    assert "decision_trace_write_failed correlation_id=invalid" in caplog.text

    not_a_dir = tmp_path / "regular-file"
    not_a_dir.touch()
    monkeypatch.setattr(get_settings(), "decision_trace_dir", str(not_a_dir))
    decision_trace.persist(trace, True)
    assert "decision_trace_export_failed" in caplog.text
    assert repository.get_full_decision_trace(trace["correlation_id"]) == trace

    def fail(*_):
        raise RuntimeError("synthetic write failure")

    with monkeypatch.context() as patch:
        patch.setattr(repository, "save_decision_trace", fail)
        decision_trace.persist({**trace, "correlation_id": "db-failure"}, True)
    assert "decision_trace_write_failed correlation_id=db-failure" in caplog.text
    assert repository.get_full_decision_trace("db-failure") is None


def test_foundation_power_stages_and_energy_use_measured_intervals(run):
    traces = [t for t in run.recorder.decision_traces if t["power"]["actual_output"]]
    assert traces
    for trace in traces:
        power = trace["power"]
        assert power["proposed"]["by_booking_kw"] == trace["proposed_setpoints_kw"]
        assert power["approved"]["by_booking_kw"] == trace["approved_setpoints_kw"]
        assert power["dispatched"]["command_ids"] == [
            c["command_id"] for c in trace["emergency_commands"] + trace["commands"] if c["executed"]
        ]
        assert power["effective_setpoint"]["source"] == "kernel.held_setpoints"
        measured = power["actual_output"]
        assert measured["source"] == "physics.applied_result.actual_kw"
        combined = {}
        for sample in measured["samples"]:
            duration = sample["end_minute"] - sample["start_minute"]
            for vid, kw in sample["by_booking_kw"].items():
                combined[vid] = combined.get(vid, 0.0) + kw * duration / 60
        assert combined == pytest.approx(trace["applied"]["output_kwh"])
        assert set(measured["average_by_booking_kw"]) == combined.keys()
        for vid, output in combined.items():
            assert measured["average_by_booking_kw"][vid] == pytest.approx(
                output * 60 / measured["sample_minutes_by_booking"][vid]
            )
            assert trace["applied"]["grid_input_kwh"][vid] == pytest.approx(
                output / run.config.power_conversion_efficiency
            )
        assert trace["experiment"]["fingerprint"]
        assert trace["evidence_refs"]["/power/actual_output"].endswith("#/power/actual_output")


async def test_foundation_trace_keeps_decision_time_policy_after_reconfiguration():
    from src.models.events import EventType, StationEvent
    from src.services.experiment import resolve_experiment
    from src.services.runtime import make_scheduler

    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(NOW.date(), scenario.start_time, tzinfo=NOW.tzinfo)
    rt = build_sim_runtime(scenario, StrategyName.SIM_M3A, config, tariff, start)
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=start), rt)
    held = rt.open_trace
    assert held["trace"]["validation"]["post_apply"] == "not_evaluated"
    assert held["trace"]["power"]["actual_output"] is None
    assert held["trace"]["experiment"]["fingerprint"] == resolve_experiment(rt).fingerprint
    rt.scheduler = make_scheduler(StrategyName.SIM_B0, lambda: rt.simulator)
    closed = decision_trace.close_open(rt)
    assert closed["policy"] == {"id": "M3a", "version": "1"}
    assert closed["decision"]["algorithms"] == held["labels"]
    assert closed["experiment"]["fingerprint"] != resolve_experiment(rt).fingerprint
    assert closed["validation"]["post_apply"] == "no_samples"
    assert closed["power"]["actual_output"] is None


async def test_foundation_trace_with_independent_supply_and_no_readings_is_json_safe():
    from src.models.events import EventType, StationEvent

    config = catalog.load_station_config().model_dump()
    config["supply_mode"] = "independent"
    config["independent_grid_input_limit_kw"] = {"AC": 25, "DC": 90}
    config = type(catalog.load_station_config()).model_validate(config)
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(NOW.date(), scenario.start_time, tzinfo=NOW.tzinfo)
    rt = build_sim_runtime(scenario, StrategyName.SIM_M3A, config, catalog.load_tariff(), start)
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=start), rt)
    rt.simulator.step(1)
    closed = decision_trace.close_open(rt)
    assert closed["applied"]["minutes"] == 1
    assert closed["decision"]["physical_limits"]["supply_mode"] == "independent"
    assert closed["validation"]["post_apply"] == "no_samples"
    assert closed["power"]["actual_output"] is None
    json.dumps(closed, allow_nan=False)
