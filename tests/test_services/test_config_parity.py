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

# Tham số KHÁC mặc định của registry (rolling_lp: horizon 120'; ac_rolling_lp: block 15').
TUNED = {"optimizer_dc": {"horizon_minutes": 30}}
# §3.4: bộ tham số đổi lịch thật trên kịch bản thử (105 / 240 phút khác so với mặc định) — phép so không tầm thường.
PARITY_POLICY = "M3a"
PARITY_PARAMS = {"optimizer_ac": {"block_minutes": 30}, "optimizer_dc": {"horizon_minutes": 30}}


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


# ---- §3.2 / §3.3 resolved experiment configuration + provenance ---------------------------------------------------------


def test_resolved_experiment_is_explicit_and_stable():
    from src.models.simulation import ResolvedExperiment
    from src.services.experiment import canonical_sha256, resolve_experiment

    config = _config()
    scenario = _scenario()
    tariff, start = catalog.load_tariff(), _start(scenario)
    exp = resolve_experiment(build_sim_runtime(scenario, "M2b", config, tariff, start))
    assert (exp.policy_id, exp.policy_version) == ("M2b", "1")
    assert set(exp.components) == {
        "dispatch.AC",
        "dispatch.DC",
        "optimizers.AC",
        "optimizers.DC",
        "coordinator",
        "physical_guard",
    }
    assert exp.components["dispatch.DC"].name == "llf"
    assert exp.components["optimizers.DC"].name == "rolling_lp"
    assert exp.components["optimizers.DC"].parameters["horizon_minutes"] == 30  # tham số ĐÃ resolve, đủ mặc định
    assert len(exp.components["optimizers.DC"].parameters) > 1
    assert exp.dc_charging_model.name == "synthetic_taper_v1"
    assert exp.parameters == TUNED
    assert exp.time_config == {
        "physics_step_minutes": 1,
        "decision_interval_minutes": 15,
        "planning_horizon_minutes": None,
    }
    # ổn định: dựng lại (seed khác, thời điểm khác) ⇒ cùng fingerprint; băm lại từ JSON ⇒ cùng giá trị
    again = resolve_experiment(build_sim_runtime(_scenario(seed=99), "M2b", config, tariff, NOW))
    assert again.fingerprint == exp.fingerprint
    reloaded = ResolvedExperiment.model_validate_json(exp.model_dump_json())
    assert canonical_sha256(reloaded.model_dump(mode="json", exclude={"fingerprint"})) == exp.fingerprint
    # mỗi thay đổi cấu hình ⇒ fingerprint khác
    default = resolve_experiment(build_sim_runtime(scenario, "M2b", config, tariff, start, parameters={}))
    other = resolve_experiment(build_sim_runtime(scenario, "M3a", config, tariff, start))
    planning = PlanningPolicyConfig(policy_id="M2b", parameters=TUNED, dc_charging_model="vinfast_profiles_v0_1")
    vinfast = config.model_copy(update={"planning": planning})
    dc = resolve_experiment(build_sim_runtime(scenario, "M2b", vinfast, tariff, start))
    assert dc.dc_charging_model.name == "vinfast_profiles_v0_1"
    assert len({exp.fingerprint, default.fingerprint, other.fingerprint, dc.fingerprint}) == 4


def test_benchmark_report_and_manifest_carry_the_experiment(monkeypatch):
    import json

    from eval import run_benchmark
    from src.services import simulation_service

    config = _config()
    monkeypatch.setattr(simulation_service.catalog, "load_station_config", lambda: config)
    scenario = _scenario(duration_hours=2, n_vehicles=3)
    report = simulation_service.run_benchmark([scenario], ["B0", "M2b"], [1, 2])
    by_policy: dict[str, set[str]] = {}
    for run in report.runs:
        assert run.experiment is not None and run.experiment.policy_id == run.policy_id
        by_policy.setdefault(run.policy_id, set()).add(run.experiment.fingerprint)
    assert all(len(prints) == 1 for prints in by_policy.values())  # seed không thuộc cấu hình thí nghiệm
    assert set(report.source.experiments) == {"B0", "M2b"}
    assert report.source.experiments["M2b"].parameters == TUNED
    assert report.source.experiments["B0"].parameters == {}
    manifest = run_benchmark.build_manifest(report, report.model_dump_json(), ["--seeds", "1,2"])
    expected = {pid: exp.fingerprint for pid, exp in report.source.experiments.items()}
    assert manifest["experiment_fingerprints"] == expected
    assert manifest["runs"] == 4 and manifest["command"] == "eval/run_benchmark.py --seeds 1,2"
    json.dumps(manifest)  # ghi được ra file


# ---- §3.4 cùng policy + config (tham số KHÁC mặc định) ⇒ cùng kết quả ở live, benchmark, admission ------------------


def _pending(scenario, config):
    from src.services.simulation_service import generate_bookings

    bookings = generate_bookings(scenario, config, _start(scenario))
    return sorted(bookings, key=lambda b: (b.created_at, b.booking_id))


def _drive(rt, pending, minutes: int) -> list[tuple]:
    """Vòng benchmark (simulation_service._run) — trả công suất từng cổng mỗi phút."""
    from src.services import control_loop
    from src.services.admission import run_sync
    from src.services.runtime import visit_of

    sim, pending = rt.simulator, list(pending)

    async def run() -> list[tuple]:
        trace, carried = [], []
        for _ in range(minutes):
            now, events, carried = sim.now, carried, []
            while pending and pending[0].created_at <= now:
                booking = pending.pop(0)
                rt.store.save_booking(booking)
                events += sim.upsert_vehicle(visit_of(booking, now))
            await control_loop.on_minute(rt, events)
            trace.append((sim.minute, tuple(round(c.power_kw, 9) for c in sim.state().connectors)))
            carried = sim.step(1)
        return trace

    return run_sync(run())


def _live_like(scenario, config, tariff):
    """Runtime dựng ĐÚNG như get_runtime (make_station + live_scheduler), store trong bộ nhớ, cùng kịch bản."""
    from src.services.runtime import _memory_runtime, live_scheduler

    station = make_station(config, _start(scenario))
    station.reset(scenario)
    return _memory_runtime(station, live_scheduler(config, station), config, tariff)


def test_non_default_parameters_give_the_same_results_in_live_benchmark_and_admission():
    from src.services.admission import evaluate, run_sync
    from src.services.experiment import resolve_experiment

    config = _config(PARITY_POLICY, PARITY_PARAMS)
    tariff = catalog.load_tariff()
    scenario = _scenario(duration_hours=8, n_vehicles=8)
    pending = _pending(scenario, config)
    minutes = 4 * 60

    live = _live_like(scenario, config, tariff)
    bench = build_sim_runtime(scenario, PARITY_POLICY, config, tariff, _start(scenario))
    assert live.scheduler.parameters == bench.scheduler.parameters == PARITY_PARAMS
    assert resolve_experiment(live).fingerprint == resolve_experiment(bench).fingerprint
    live_trace, bench_trace = _drive(live, pending, minutes), _drive(bench, pending, minutes)
    assert live_trace == bench_trace
    assert any(any(kw > 0 for kw in powers) for _, powers in bench_trace)
    # tham số mặc định cho lịch khác ⇒ phép so ở trên không tầm thường
    default = build_sim_runtime(scenario, PARITY_POLICY, config, tariff, _start(scenario), parameters={})
    assert _drive(default, pending, minutes) != bench_trace

    # admission (fork của runtime live) = chạy tiếp CHÍNH runtime đó với cùng xe, cùng điều kiện
    model = next(b for b in pending if b.request.zone == "DC")
    now = live.simulator.now
    dwell = model.request.deadline - model.request.arrival_time
    request = model.request.model_copy(update={"arrival_time": now, "deadline": now + dwell})
    candidate = model.model_copy(
        update={"booking_id": "parity-candidate", "resident_id": "parity-res", "request": request, "created_at": now}
    )
    frt_experiment = resolve_experiment(fork_runtime(live, list(live.store.active_bookings())))
    assert frt_experiment.fingerprint == resolve_experiment(live).fingerprint
    admission = run_sync(evaluate(live, candidate))
    assert admission.policy == PARITY_POLICY
    assert admission.delivered_kwh > 0 and admission.charge_start is not None
    executed = _execute_to_deadline(live, candidate)
    assert (admission.connector_id, admission.plugged_at, admission.charge_start, admission.charge_end) == (
        executed["connector"],
        executed["plugged"],
        executed["start"],
        executed["end"],
    )
    assert admission.delivered_kwh == pytest.approx(executed["delivered"], abs=1e-9)
    assert admission.cost_vnd == executed["cost"]


def _execute_to_deadline(rt, candidate) -> dict:
    """Chạy trạm THẬT của `rt` với `candidate` tới deadline — đúng các bước `admission.evaluate` đo trên bản fork."""
    from zoneinfo import ZoneInfo

    from src.models.events import EventType, StationEvent
    from src.services import control_loop
    from src.services.admission import EPS_KWH, run_sync
    from src.services.runtime import visit_of

    sim, cid = rt.simulator, candidate.booking_id
    tz = ZoneInfo(rt.config.timezone)

    async def run() -> dict:
        rt.store.save_booking(candidate)
        events = sim.upsert_vehicle(visit_of(candidate, sim.now))
        events.append(StationEvent(type=EventType.BOOKING_CREATED, occurred_at=sim.now, booking_id=cid))
        deadline = sim.minute_of(candidate.request.deadline)
        out = {"connector": None, "plugged": None, "start": None, "end": None, "cost": 0.0}
        while sim.minute < deadline:
            await control_loop.on_minute(rt, events)
            session = sim.queue.sessions.get(cid)
            if session is None or session.state == "DEPARTED":
                break
            if session.connector is not None and out["connector"] is None:
                out["connector"], out["plugged"] = sim.connector_of(session.connector), sim.now
            at, before = sim.now, sim.kernel.output_kwh.get(cid, 0.0)
            events = sim.step(1)
            delivered = sim.kernel.output_kwh.get(cid, 0.0) - before
            if delivered > EPS_KWH:
                out["start"] = out["start"] or at
                out["end"] = sim.now
                out["cost"] += delivered * rt.tariff.price_at(at.astimezone(tz).time())
            if session.completed_at is not None:
                break
        outcome = next(o for o in sim.outcomes() if o.booking_id == cid)
        out["delivered"] = outcome.delivered_kwh_by_deadline
        out["cost"] = round(out["cost"]) if out["start"] is not None else None
        return out

    return run_sync(run())


def test_old_baseline_without_experiments_still_loads():
    from src.services import simulation_service

    report = simulation_service.latest_benchmark()
    assert report.source.experiments == {}  # baseline 2026-11-24 không có khoá này — evidence cũ không sửa
    assert all(run.experiment is None for run in report.runs)
