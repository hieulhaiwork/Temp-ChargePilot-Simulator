"""Chạy kịch bản mô phỏng (màn S8, F7) và benchmark A–D (AC7).

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

Owner: TV1. Task: T1.5 (baseline A), T3.4 (B/C/D), T3.5 (sự cố).
"""

import asyncio
import json
import math
import random
import statistics
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.models.api import ErrorCode
from src.models.charging import Booking, BookingStatus, ChargeMode, ChargeRequest, ConsentScope, StrategyName
from src.models.events import EventType, StationEvent
from src.models.simulation import (
    BenchmarkReport,
    Incident,
    KpiReport,
    Scenario,
    SessionOutcome,
    SimulationRunResult,
)
from src.models.station import StationConfig, Tariff
from src.services import catalog, control_loop, event_bus
from src.services.charging_service import vehicle_power_cap
from src.services.energy import estimate_energy
from src.services.errors import DomainError
from src.services.runtime import StationRuntime, build_sim_runtime, get_runtime, visit_of

BENCHMARK_FILE = Path(__file__).resolve().parents[2] / "eval" / "results" / "benchmark.json"
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


def _run_sync(coro):
    """Chạy coroutine từ code đồng bộ — kể cả khi đang ở trong event loop (chạy ở thread riêng)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict = {}

    def target() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 — chuyển lỗi về thread gọi
            box["error"] = exc

    worker = threading.Thread(target=target)
    worker.start()
    worker.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def _is_feasible(outcome: SessionOutcome, booking: Booking) -> bool:
    hours = (booking.request.deadline - outcome.arrival_time).total_seconds() / 3600
    return booking.max_charge_power_kw * hours >= outcome.requested_kwh - ON_TIME_TOL_KWH


async def _run(scenario: Scenario, strategy: StrategyName) -> SimulationRunResult:
    started_at = datetime.now(UTC)
    config = catalog.load_station_config()
    tariff = catalog.load_tariff()
    tz = ZoneInfo(config.timezone)
    start = datetime.combine(SIM_DATE, scenario.start_time, tzinfo=tz)
    bookings = generate_bookings(scenario, config, start)
    rt: StationRuntime = build_sim_runtime(
        scenario, strategy, config, tariff, start, tuple(bookings) if strategy == StrategyName.ORACLE else ()
    )
    sim = rt.simulator
    pending = sorted(bookings, key=lambda b: (b.created_at, b.booking_id))
    incidents = {i.at_minute: [] for i in scenario.incidents}
    for inc in scenario.incidents:
        incidents[inc.at_minute].append(inc)
    step = config.optimizer.planning_step_minutes
    minute_load: list[tuple[datetime, float, float]] = []
    skipped: list[str] = []  # sự cố trỏ tới cổng không có trong topology hiện hành (kịch bản legacy_ac_only)
    for minute in range(scenario.duration_hours * 60):
        now = sim.now
        events: list[StationEvent] = []
        while pending and pending[0].created_at <= now:
            booking = pending.pop(0)
            rt.store.save_booking(booking)
            events += sim.upsert_vehicle(visit_of(booking, now))
            events.append(StationEvent(type=EventType.BOOKING_CREATED, occurred_at=now, booking_id=booking.booking_id))
        for inc in incidents.get(minute, []):
            try:
                events += sim.inject_incident(Incident.model_validate(inc.model_dump(exclude={"at_minute"})))
            except ValueError:
                skipped.append(f"{inc.type.value}@{inc.at_minute}' ({inc.connector_id})")
        if not events and minute % step == 0:
            events.append(StationEvent(type=EventType.TICK, occurred_at=now))
        # Sự cố nguồn phải đi trước để bảo vệ khẩn cấp chạy ngay (AC5); các sự kiện khác gộp vào một lần tính lại.
        urgent = [e for e in events if e.type == EventType.POWER_LIMIT_CHANGED]
        for event in urgent:
            await control_loop.on_event(event, rt)
        rest = [e for e in events if e.type != EventType.POWER_LIMIT_CHANGED]
        if rest:
            await control_loop.on_event(rest[-1], rt)
        state = sim.state()
        minute_load.append((now, state.total_power_kw, state.available_power_kw))
        for event in sim.step(1):
            if event.type in (EventType.VEHICLE_ARRIVED, EventType.VEHICLE_DEPARTED):
                await control_loop.on_event(event, rt)
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
        f"{scenario.power_limit_kw:g} kW; LiveStation (không mô phỏng taper DC)."
    )
    if skipped:
        notes += f" Bỏ qua sự cố không khớp topology: {', '.join(skipped)}."
    if strategy == StrategyName.OPT_ML:
        notes += " C = B vì F6 hoãn (ADR-015): không có dự báo — KHÔNG tuyên bố AI cải thiện."
    return SimulationRunResult(
        run_id=uuid4().hex[:12],
        scenario_id=scenario.scenario_id,
        strategy=strategy,
        kpis=kpis,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        notes=notes,
    )


def run_scenario(scenario: Scenario, strategy: StrategyName) -> SimulationRunResult:
    """Chạy trọn một kịch bản với một chiến lược, trả KPI (compute_kpis)."""
    return _run_sync(_run(scenario, strategy))


def run_benchmark(
    scenarios: list[Scenario], strategies: list[StrategyName], seeds: list[int] | None = None
) -> BenchmarkReport:
    """Mọi chiến lược chạy trên CÙNG tập kịch bản (cùng seed → cùng tập phiên, cùng biểu giá).

    seeds=None → dùng seed ghi trong từng kịch bản. Có seeds → mỗi (kịch bản, chiến lược) chạy một lần cho
    mỗi seed (PRD §8 "chạy nhiều ngày mô phỏng"); báo cáo ghi trung bình ± độ lệch chuẩn ở `notes`.
    """
    runs: list[SimulationRunResult] = []
    for scenario in scenarios:
        for seed in seeds or [scenario.seed]:
            seeded = scenario.model_copy(update={"seed": seed})
            for strategy in strategies:
                runs.append(run_scenario(seeded, strategy))
    notes = [
        "Simulator: LiveStation của backend (src/simulator/live.py) — số KHÔNG so trực tiếp với HybridSimulator R&D.",
        "Phiên sạc tổng hợp; tham số phân bố là [GIẢ ĐỊNH] (src/services/simulation_service.py).",
    ]
    if seeds:
        for scenario in scenarios:
            for strategy in strategies:
                sample = [r.kpis for r in runs if r.scenario_id == scenario.scenario_id and r.strategy == strategy]
                if len(sample) > 1:
                    on_time = [k.on_time_rate for k in sample]
                    cost = [k.energy_cost_vnd for k in sample]
                    notes.append(
                        f"{scenario.scenario_id} / {strategy.value}: đúng hạn {statistics.fmean(on_time):.1%} ± "
                        f"{statistics.stdev(on_time):.1%}, chi phí {statistics.fmean(cost):,.0f} ± "
                        f"{statistics.stdev(cost):,.0f} VND ({len(sample)} seed)"
                    )
    return BenchmarkReport(generated_at=datetime.now(UTC), runs=runs, notes=notes)


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
    """US8 — bảng so sánh gần nhất (eval/results/benchmark.json do eval/run_benchmark.py ghi)."""
    if not BENCHMARK_FILE.exists():
        raise DomainError(ErrorCode.NOT_FOUND, "Chưa có kết quả benchmark — chạy `python eval/run_benchmark.py`")
    return BenchmarkReport.model_validate(json.loads(BENCHMARK_FILE.read_text(encoding="utf-8")))
