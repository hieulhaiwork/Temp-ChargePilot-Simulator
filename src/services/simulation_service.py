"""Chạy kịch bản mô phỏng (màn S8, F7) và benchmark B0 / M2b / M3a / M3b (AC7).

Vì sao dùng CHUNG pipeline với vận hành thật: benchmark phải đo đúng đường code
production (optimizer → Guard → simulator), nếu không "0 lần vượt giới hạn" (MT4) chỉ
đúng trên giấy. Khác biệt duy nhất là đồng hồ mô phỏng thay cho đồng hồ thật.

Đây cũng là composition root của chế độ mô phỏng: tạo runtime mô phỏng (runtime.build_sim_runtime)
và CHỈ đưa phần StationActuator cho guard.dispatcher — không tự gọi apply_commands.

Phiên sạc tổng hợp (FR18) — generate_bookings, xác định theo seed. MỌI tham số phân bố dưới đây là
[GIẢ ĐỊNH] của bộ sinh, không phải số đo tại trạm thật:
  - 65% xe AC (qua đêm, ở lại 9–13 giờ), 35% xe DC (sạc nhanh, ở lại 1–2,5 giờ), xe DC chọn trong mẫu có max_dc_kw.
  - Giờ đến ~ chuẩn quanh 19:00 (σ = 2 giờ); AC 60% đặt trước 1–3 giờ, còn lại đến trực tiếp.
  - Cư dân mô phỏng đồng ý trước cho lùi giờ bắt đầu tới sát hạn (không có người trả lời S4 trong benchmark).
Kịch bản trong config/scenarios/ mang nhãn legacy_ac_only (ADR-012): chỉ dùng n_vehicles, seed, giờ bắt đầu,
thời lượng, giới hạn nguồn và sự cố; topology lấy từ config/station.yaml hiện hành (ADR-010).

Owner: TV1. Task: T3.4 (benchmark B0 / M2b / M3a / M3b, baseline có version — Phase 4), T3.5 (sự cố).
"""

import json
import math
import platform
import random
import statistics
from datetime import UTC, date, datetime, time, timedelta
from importlib import metadata
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.models.api import ErrorCode
from src.models.charging import Booking, BookingStatus, ChargeMode, ChargeRequest, ConsentScope, StrategyName
from src.models.events import EventType, StationEvent
from src.models.simulation import (
    BenchmarkReport,
    BenchmarkSource,
    BenchmarkSourceKind,
    Incident,
    IncidentCounts,
    IncidentType,
    KpiReport,
    PolicyInfo,
    ResolvedExperiment,
    Scenario,
    SessionOutcome,
    SimulationRunResult,
    ViolationCounts,
)
from src.models.station import StationConfig, Tariff
from src.services import catalog, control_loop, event_bus
from src.services.admission import run_sync
from src.services.charging_service import vehicle_power_cap
from src.services.energy import estimate_energy
from src.services.errors import DomainError
from src.services.experiment import try_resolve_experiment
from src.services.hybrid_planner import as_policy_ref, policy_key
from src.services.runtime import StationRuntime, build_sim_runtime, get_runtime, make_station, visit_of

REPO_ROOT = Path(__file__).resolve().parents[2]
# Baseline có version mà S8 hiển thị (Phase 4 quyết định 8). Baseline nghiệm thu cuối = thư mục mới + đổi hằng này.
BENCHMARK_BASELINE_DIR = REPO_ROOT / "eval" / "evidence" / "2026-11-24-unified-core-frozen-baseline"
SIM_DATE = date(2026, 11, 23)  # ngày tham chiếu cố định → cùng seed cùng kết quả (giá chỉ phụ thuộc giờ trong ngày)
ON_TIME_TOL_KWH = 0.05
DEMO_ONLY_VEHICLES = {"DEMO-60"}  # fixture test, không dùng cho mô phỏng


# ---- sinh phiên (FR18) -------------------------------------------------------------------


def generate_bookings(scenario: Scenario, config: StationConfig, start: datetime) -> list[Booking]:
    """Danh sách booking tổng hợp của một kịch bản — cùng scenario + seed → cùng danh sách."""
    rng = random.Random(scenario.seed)
    vehicles = [v for m, v in sorted(catalog.load_vehicle_catalog().items()) if m not in DEMO_ONLY_VEHICLES]
    dc_vehicles = [v for v in vehicles if v.max_dc_kw]
    horizon = scenario.duration_hours * 60
    peak = (19 * 60 - (start.hour * 60 + start.minute)) % (24 * 60)
    bookings: list[Booking] = []
    for i in range(scenario.n_vehicles):
        dc = bool(dc_vehicles) and rng.random() < 0.35
        vehicle = rng.choice(dc_vehicles if dc else vehicles)
        dwell = rng.uniform(60, 150) if dc else rng.uniform(9 * 60, 13 * 60)
        latest = max(horizon - dwell - 1, 0)
        arrival_min = min(max(int(rng.gauss(peak, 120)), 0), int(latest))
        arrival = start + timedelta(minutes=arrival_min)
        deadline = arrival + timedelta(minutes=int(dwell))
        soc_now = round(rng.uniform(10, 40) if dc else rng.uniform(15, 50))
        soc_target = 80 if dc else rng.choice([80, 90, 100])
        reservation = not dc and rng.random() < 0.6
        created = arrival - timedelta(minutes=rng.randint(60, 180)) if reservation else arrival
        request = ChargeRequest(
            vehicle_model=vehicle.vehicle_model,
            soc_now=soc_now,
            soc_target=soc_target,
            arrival_time=arrival,
            deadline=deadline,
            mode=ChargeMode.RESERVATION if reservation else ChargeMode.WALK_IN,
            zone="DC" if dc else "AC",
        )
        bookings.append(
            Booking(
                booking_id=f"sim-{scenario.seed}-{i:03d}",
                resident_id=f"sim-res-{i:03d}",
                request=request,
                status=BookingStatus.CONFIRMED,
                energy=estimate_energy(vehicle, soc_now, soc_target),
                max_charge_power_kw=vehicle_power_cap(config, request, vehicle),
                consent=ConsentScope(max_start_delay_minutes=int(dwell)),
                planned_start=arrival,
                schedule_version=0,
                created_at=max(created, start),
            )
        )
    return bookings


# ---- KPI (AC7, MT1–MT6) ------------------------------------------------------------------


def compute_kpis(
    outcomes: list[SessionOutcome],
    minute_load: list[tuple[datetime, float, float]],
    tariff: Tariff,
    config: StationConfig,
    replan_s: list[float],
    blocked: int,
) -> KpiReport:
    """minute_load = (thời điểm, công suất đầu ra tổng kW, giới hạn lưới kW) mỗi phút mô phỏng."""
    tz = ZoneInfo(config.timezone)
    feasible = [o for o in outcomes if o.feasible]
    on_time = sum(1 for o in feasible if o.delivered_kwh_by_deadline >= o.requested_kwh - ON_TIME_TOL_KWH)
    waits = [
        ((o.plug_in_time or o.deadline) - o.arrival_time).total_seconds() / 60 for o in outcomes
    ]  # chưa cắm = chờ tới giờ rời (censored)
    waits_sorted = sorted(waits)
    p90 = waits_sorted[max(math.ceil(0.9 * len(waits_sorted)) - 1, 0)] if waits_sorted else 0.0
    eta = config.power_conversion_efficiency
    cost = sum(kw / eta / 60 * tariff.price_at(t.astimezone(tz).time()) for t, kw, _ in minute_load)
    violations = sum(1 for _, kw, limit in minute_load if kw / eta > limit + 1e-6)
    p95 = None
    if replan_s:
        ordered = sorted(replan_s)
        p95 = ordered[max(math.ceil(0.95 * len(ordered)) - 1, 0)]
    return KpiReport(
        on_time_rate=on_time / len(feasible) if feasible else 1.0,
        wait_mean_minutes=round(statistics.fmean(waits), 2) if waits else 0.0,
        wait_p90_minutes=round(p90, 2),
        unmet_energy_kwh=round(sum(max(o.requested_kwh - o.delivered_kwh_by_deadline, 0) for o in outcomes), 3),
        delivered_energy_kwh=round(sum(o.delivered_kwh_by_deadline for o in outcomes), 3),
        service_rate=sum(1 for o in outcomes if o.plug_in_time) / len(outcomes) if outcomes else 1.0,
        energy_cost_vnd=round(cost),
        peak_load_kw=round(max((kw for _, kw, _ in minute_load), default=0.0), 3),
        power_limit_violations=violations,
        replan_p95_seconds=round(p95, 4) if p95 is not None else None,
        blocked_commands=blocked,
    )


# ---- chạy kịch bản -----------------------------------------------------------------------


def _is_feasible(outcome: SessionOutcome, booking: Booking) -> bool:
    hours = (booking.request.deadline - outcome.arrival_time).total_seconds() / 3600
    return booking.max_charge_power_kw * hours >= outcome.requested_kwh - ON_TIME_TOL_KWH


class InvalidIncidentError(DomainError):
    """Chế độ nghiên cứu (`strict_incidents`): sự cố của kịch bản không áp được vào topology hiện hành (Final Review 4.7)."""

    def __init__(self, detail: str) -> None:
        super().__init__(ErrorCode.NOT_FOUND, detail)


async def _run(
    scenario: Scenario, strategy: StrategyName | str, *, strict_incidents: bool = False
) -> SimulationRunResult:
    started_at = datetime.now(UTC)
    config = catalog.load_station_config()
    tariff = catalog.load_tariff()
    tz = ZoneInfo(config.timezone)
    start = datetime.combine(SIM_DATE, scenario.start_time, tzinfo=tz)
    if strict_incidents:
        # Fail-fast TRƯỚC khi dựng trạm: kịch bản nghiên cứu mà sự cố không diễn ra thì kết quả sai nghĩa.
        known = {c.connector_id for c in config.connectors}
        invalid = [
            _incident_label(inc)
            for inc in scenario.incidents
            if inc.type != IncidentType.POWER_LIMIT_CHANGE and inc.connector_id not in known
        ]
        if invalid:
            raise InvalidIncidentError(
                f"Kịch bản {scenario.scenario_id}: sự cố trỏ đầu nối không có trong topology hiện hành: "
                f"{', '.join(invalid)} (strict_incidents)"
            )
    bookings = generate_bookings(scenario, config, start)
    rt: StationRuntime = build_sim_runtime(scenario, strategy, config, tariff, start)
    sim = rt.simulator
    pending = sorted(bookings, key=lambda b: (b.created_at, b.booking_id))
    incidents = {i.at_minute: [] for i in scenario.incidents}
    for inc in scenario.incidents:
        incidents[inc.at_minute].append(inc)
    minute_load: list[tuple[datetime, float, float]] = []
    skipped: list[str] = []  # sự cố trỏ tới cổng không có trong topology hiện hành (kịch bản legacy_ac_only)
    applied = 0
    carried: list[StationEvent] = []  # sự kiện trạm phát ra ở cuối phút trước (xe đến / rời, sạc xong)
    for minute in range(scenario.duration_hours * 60):
        now = sim.now
        events, carried = carried, []
        while pending and pending[0].created_at <= now:
            booking = pending.pop(0)
            rt.store.save_booking(booking)
            events += sim.upsert_vehicle(visit_of(booking, now))
            events.append(StationEvent(type=EventType.BOOKING_CREATED, occurred_at=now, booking_id=booking.booking_id))
        for inc in incidents.get(minute, []):
            try:
                events += sim.inject_incident(Incident.model_validate(inc.model_dump(exclude={"at_minute"})))
            except ValueError as exc:
                if strict_incidents:
                    raise InvalidIncidentError(
                        f"Kịch bản {scenario.scenario_id}: sự cố {_incident_label(inc)} không áp được: {exc}"
                    ) from exc
                skipped.append(_incident_label(inc))
            else:
                applied += 1
        await control_loop.on_minute(rt, events)
        state = sim.state()
        minute_load.append((now, state.total_power_kw, state.available_power_kw))
        carried = sim.step(1)
    by_id = {b.booking_id: b for b in bookings}
    outcomes = [o.model_copy(update={"feasible": _is_feasible(o, by_id[o.booking_id])}) for o in sim.outcomes()]
    arrived = {o.booking_id for o in outcomes}
    kpis = compute_kpis(
        outcomes,
        minute_load,
        tariff,
        config,
        rt.recorder.replan_durations_s,
        rt.recorder.blocked_commands,
    )
    notes = (
        f"{len(bookings)} phiên tổng hợp (seed {scenario.seed}), {len(arrived)} xe đã đến; giới hạn nguồn "
        f"{scenario.power_limit_kw:g} kW; {_engine_label(rt.simulator)}."
    )
    if skipped:
        notes += f" Bỏ qua sự cố không khớp topology: {', '.join(skipped)}."
    policy_id = getattr(rt.scheduler, "policy_id", None) or policy_key(strategy)
    return SimulationRunResult(
        run_id=uuid4().hex[:12],
        scenario_id=scenario.scenario_id,
        policy_id=policy_id,  # strategy (enum cũ) tự điền khi id là B0 / M2b / M3a / M3b
        policy_version=getattr(rt.scheduler, "policy_version", None),
        kpis=kpis,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        notes=notes,
        incidents=IncidentCounts(
            planned=len(scenario.incidents),
            applied=applied,
            skipped=len(skipped),
            skipped_details=skipped,
            strict=strict_incidents,
        ),
        experiment=try_resolve_experiment(rt),
        violations=violation_counts(kpis, sim),
    )


def violation_counts(kpis: KpiReport, station) -> ViolationCounts:
    """KPI lấy mẫu (MT4) và vi phạm cứng của kernel — hai nguồn, hai trường (Final Acceptance §3.5)."""
    kernel = getattr(station, "kernel", None)
    return ViolationCounts(
        sampled_power_over_limit_minutes=kpis.power_limit_violations,
        applied_constraint_violation_count=getattr(station, "applied_constraint_violation_count", 0),
        rejected_allocation_count=getattr(kernel, "rejected_allocation_count", 0),
    )


def _incident_label(inc) -> str:
    return f"{inc.type.value}@{inc.at_minute}' ({inc.connector_id})"


def run_scenario(
    scenario: Scenario, strategy: StrategyName | str, *, strict_incidents: bool = False
) -> SimulationRunResult:
    """Chạy trọn một kịch bản với một policy (StrategyName hoặc id registry), trả KPI (compute_kpis).

    `strict_incidents=True` (benchmark nghiên cứu): sự cố không áp được ⇒ `InvalidIncidentError` ngay; mặc định giữ
    hành vi cũ (bỏ qua + ghi note). Mọi chế độ ghi số sự cố dự kiến / thực thi / bỏ qua ở `incidents`.
    """
    return run_sync(_run(scenario, strategy, strict_incidents=strict_incidents))


def list_policies() -> list[PolicyInfo]:
    """Policy hợp lệ cho backend — đọc từ registry (`src/optimizer/registry.py`), cùng nguồn với runtime."""
    from src.optimizer import registry

    infos = []
    for spec in registry.policy_specs():
        legacy = as_policy_ref(spec.id)
        infos.append(
            PolicyInfo(
                policy_id=spec.id,
                version=spec.version,
                dispatch_dc=spec.dispatch_dc,
                optimizer_ac=spec.optimizer_ac,
                optimizer_dc=spec.optimizer_dc,
                coordinator=spec.coordinator,
                description=spec.description,
                frozen=spec.frozen,
                legacy_strategy=legacy if isinstance(legacy, StrategyName) else None,
            )
        )
    return infos


def run_benchmark(
    scenarios: list[Scenario],
    strategies: list[StrategyName | str],
    seeds: list[int] | None = None,
    *,
    strict_incidents: bool = False,
) -> BenchmarkReport:
    """Mọi chiến lược chạy trên CÙNG tập kịch bản (cùng seed → cùng tập phiên, cùng biểu giá).

    seeds=None → dùng seed ghi trong từng kịch bản. Có seeds → mỗi (kịch bản, chiến lược) chạy một lần cho
    mỗi seed (PRD §8 "chạy nhiều ngày mô phỏng"); báo cáo ghi trung bình ± độ lệch chuẩn ở `notes`.
    `strict_incidents`: như `run_scenario` — benchmark nghiên cứu dừng ngay ở kịch bản có sự cố không hợp lệ.
    """
    runs: list[SimulationRunResult] = []
    for scenario in scenarios:
        for seed in seeds or [scenario.seed]:
            seeded = scenario.model_copy(update={"seed": seed})
            for strategy in strategies:
                runs.append(run_scenario(seeded, strategy, strict_incidents=strict_incidents))
    notes = [
        f"Trạm: {_engine_label(None)} — kịch bản và KPI của backend; so với số MVP-2/3 R&D phải cùng fixture (ADR-018).",
        "Phiên sạc tổng hợp; tham số phân bố là [GIẢ ĐỊNH] (src/services/simulation_service.py).",
    ]
    if seeds:
        for scenario in scenarios:
            for strategy in strategies:
                key = policy_key(strategy)
                sample = [r.kpis for r in runs if r.scenario_id == scenario.scenario_id and r.policy_id == key]
                if len(sample) > 1:
                    on_time = [k.on_time_rate for k in sample]
                    cost = [k.energy_cost_vnd for k in sample]
                    notes.append(
                        f"{scenario.scenario_id} / {key}: đúng hạn {statistics.fmean(on_time):.1%} ± "
                        f"{statistics.stdev(on_time):.1%}, chi phí {statistics.fmean(cost):,.0f} ± "
                        f"{statistics.stdev(cost):,.0f} VND ({len(sample)} seed)"
                    )
    experiments, conflicts = run_experiments(runs)
    notes += [f"Cấu hình đã resolve KHÁC NHAU giữa các run của {pid} (fingerprint lệch)." for pid in conflicts]
    source = benchmark_source(scenarios, strategies, seeds or sorted({s.seed for s in scenarios}))
    source.experiments = experiments
    return BenchmarkReport(generated_at=datetime.now(UTC), runs=runs, notes=notes, source=source)


def run_experiments(runs: list[SimulationRunResult]) -> tuple[dict[str, ResolvedExperiment], list[str]]:
    """policy_id → cấu hình đã resolve (run đầu tiên) + danh sách policy có run lệch fingerprint (Final Acceptance §3.3).

    Seed / kịch bản không thuộc cấu hình thí nghiệm ⇒ mọi run của một policy phải cùng fingerprint.
    """
    experiments: dict[str, ResolvedExperiment] = {}
    conflicts: list[str] = []
    for run in runs:
        if run.experiment is None or run.policy_id is None:
            continue
        first = experiments.setdefault(run.policy_id, run.experiment)
        if first.fingerprint != run.experiment.fingerprint and run.policy_id not in conflicts:
            conflicts.append(run.policy_id)
    return experiments, conflicts


async def inject_incident(incident: Incident) -> None:
    """US6 / FR18 — bơm sự cố vào simulator đang chạy (demo trực tiếp).

    rt.simulator.inject_incident → event_bus.publish(sự kiện) → control_loop.on_event xử lý ngay
    (AC5: bảo vệ khẩn cấp chạy trước khi tính lại lịch).
    """
    rt = get_runtime()
    async with rt.lock:
        rt.sync_clock()
        try:
            events = rt.simulator.inject_incident(incident)
        except ValueError as exc:
            raise DomainError(ErrorCode.NOT_FOUND, str(exc)) from None
    for event in events:
        await event_bus.publish(event)


def latest_benchmark() -> BenchmarkReport:
    """US8 — bảng đối chứng của S8 = baseline CÓ VERSION hiện hành (Phase 4 quyết định 8).

    Đọc `BENCHMARK_BASELINE_DIR/{manifest,benchmark}.json`, gắn `source` (baseline, version, commit, kịch bản, policy,
    seed, TimeConfig, thư viện). Không đọc `eval/results/benchmark.json`: số vừa sinh chưa phải baseline cho tới khi
    được chép thành một thư mục baseline mới có manifest. Bảng A–D cũ nằm ở `eval/results/archive/` (deprecated).
    """
    manifest_file = BENCHMARK_BASELINE_DIR / "manifest.json"
    data_file = BENCHMARK_BASELINE_DIR / "benchmark.json"
    if not (manifest_file.exists() and data_file.exists()):
        raise DomainError(ErrorCode.NOT_FOUND, f"Chưa có baseline benchmark có version ở {_repo_path(data_file)}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    report = BenchmarkReport.model_validate(json.loads(data_file.read_text(encoding="utf-8")))
    source = BenchmarkSource(
        kind=BenchmarkSourceKind.VERSIONED_BASELINE,
        baseline_id=manifest["baseline_id"],
        version=manifest["version"],
        status=manifest.get("status"),
        code_commit=manifest.get("code_commit"),
        path=_repo_path(data_file),
        scenarios=manifest.get("scenarios", []),
        policies=manifest.get("policies", []),
        seeds=manifest.get("seeds", []),
        time_config=manifest.get("time_config", {}),
        libraries=manifest.get("libraries", {}),
        note=manifest.get("status_note", ""),
        experiments=manifest.get("experiments", {}),  # baseline cũ không có khoá này ⇒ rỗng
    )
    head = (
        f"Nguồn: baseline {source.baseline_id} version {source.version} ({source.status or 'không rõ trạng thái'}), "
        f"code {(source.code_commit or '?')[:7]}, seed {', '.join(map(str, source.seeds))} — {source.path}."
    )
    return report.model_copy(update={"source": source, "notes": [head, *report.notes]})


def benchmark_source(
    scenarios: list[Scenario], strategies: list[StrategyName | str], seeds: list[int]
) -> BenchmarkSource:
    """`source` cho bảng VỪA SINH (eval/run_benchmark.py): điều kiện đo để sau này chép thành baseline có version."""
    config = catalog.load_station_config()
    station = make_station(config, datetime.combine(SIM_DATE, time(0), tzinfo=ZoneInfo(config.timezone)))
    libraries = {"python": platform.python_version(), "os": f"{platform.system()} {platform.release()}"}
    for package in ("ev2gym", "numpy", "scipy"):
        try:
            libraries[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            libraries[package] = "không cài"
    return BenchmarkSource(
        kind=BenchmarkSourceKind.GENERATED,
        scenarios=[s.scenario_id for s in scenarios],
        policies=[policy_key(s) for s in strategies],
        seeds=seeds,
        time_config=station.time.as_dict(),
        libraries=libraries,
        note="Số vừa sinh, chưa phải baseline có version — không trộn với baseline / bảng A–D đã lưu trữ.",
    )


def _repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def _engine_label(station) -> str:
    """Ghi rõ engine và cấu hình thời gian (P1) trong mọi báo cáo: không so số giữa hai cấu hình khác nhau."""
    time = getattr(station, "time", None)
    detail = f"; vật lý {time.physics_step_minutes}', trần quyết định {time.decision_interval_minutes}'" if time else ""
    return f"HybridStation (kernel dùng chung với simulator: EV2Gym AC, đường sạc DC{detail})"
