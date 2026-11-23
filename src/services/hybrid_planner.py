"""Bộ lập lịch backend: Planning Core của `StationKernel` + bước nghiệp vụ consent (ADR-019 Phase 3).

Không còn bản chép của `HybridSimulator.step`: `decide()` gọi `kernel.propose` (dispatch → coordinator → optimizer →
Physical Guard, cùng code với simulator standalone) trên trạm đang chạy, rồi áp consent cư dân và `kernel.approve`
(plan bị consent chỉnh phải qua lại CÙNG Physical Guard). Kết quả thành `SchedulePlan`; lệnh vẫn đi `diff_commands` →
`guard/dispatcher.py` (7 luật Business Guard + HITL, ADR-002) trước khi tới trạm. Admission (quote / booking) gọi
CÙNG `decide()` trên bản fork của trạm (`services/admission.py`).

Chọn thuật toán: bảng `POLICIES` của `src/optimizer/registry.py`, dựng bằng `resolve_algorithms`, gắn vào kernel của
trạm qua `HybridStation.configure` (một policy cho mỗi runtime).

[GIẢ ĐỊNH] / khác biệt đã biết so với HybridSimulator.run() (docs/refactor/PHASE3_DESIGN.md §2–§3):
  - Interval quyết định = tới mốc boundary kế tiếp (xe đến / rời, rút DC, đổi giá TOU), trần
    `optimizer.planning_step_minutes`; vật lý 1'. Simulator standalone (tương thích) dùng trần `timestep`, vật lý = interval.
  - Biểu giá TOU của backend (`config/tariff.yaml`) đổi sang `Tariff` của simulator cho 48 giờ tới.
  - Lệnh vượt consent vẫn bị `guard/approval.py` giữ lại chờ duyệt như mọi chiến lược.
"""

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from src.models.charging import PowerSlot, SchedulePlan, SessionPlan, StrategyName
from src.models.decisions import ApprovedDecision, ReasonCode
from src.models.physical_constraints import TOL, ConstraintViolationError
from src.models.planning import PlanningContext
from src.models.scheduling.observations import Candidate
from src.models.simulation_core import Tariff as SimTariff
from src.models.station import Tariff
from src.optimizer.registry import POLICIES as REGISTRY_POLICIES
from src.simulator.core.algorithms import Algorithms, resolve_algorithms

logger = logging.getLogger(__name__)

# Một nguồn policy: src/optimizer/registry.py POLICIES (ADR-019) — (dispatch DC, optimizer AC, optimizer DC, coordinator).
# Backend chỉ ánh xạ mã chiến lược sang khoá registry; không chép bảng.
POLICIES: Mapping[StrategyName, tuple[str, str, str, str]] = {
    strategy: REGISTRY_POLICIES[strategy.value]
    for strategy in (StrategyName.SIM_B0, StrategyName.SIM_M2B, StrategyName.SIM_M3A, StrategyName.SIM_M3B)
}
SIMULATOR_STRATEGIES = frozenset(POLICIES)
POLICY_VERSION = "1"  # B0 / M2b / M3a / M3b đóng băng (registry.POLICIES)
TARIFF_HORIZON_HOURS = 48


def selection(strategy: StrategyName) -> dict:
    dispatch, ac, dc, coordinator = POLICIES[strategy]
    return {"dispatch": {"DC": dispatch}, "optimizers": {"AC": ac, "DC": dc}, "coordinator": coordinator}


class SimulatorScheduler:
    """Scheduler (`src/models/planning.py`) cho B0 / M2b / M3a / M3b. `station` trả HybridStation đang chạy."""

    def __init__(self, name: StrategyName, station: Callable[[], object], algorithms: Algorithms | None = None) -> None:
        if name not in POLICIES:
            raise ValueError(f"Không phải chiến lược simulator: {name!r}")
        self.name = name
        self._station = station
        self._algorithms: Algorithms | None = algorithms
        self.metadata: dict = {}
        self.last_diagnostics: dict = {}
        self.configure(station())

    def algorithms(self, station=None) -> Algorithms:
        if self._algorithms is None:
            scenario = (station or self._station()).scenario
            self._algorithms, self.metadata = resolve_algorithms(
                selection(self.name), scenario, f"backend:{self.name.value}"
            )
        return self._algorithms

    def configure(self, station) -> None:
        """Gắn policy vào kernel của trạm (giữ qua reset). Fork của admission mang theo cấu hình này."""
        station.configure(self.algorithms(station), self.name.value, POLICY_VERSION)

    def decide(self, station, ctx: PlanningContext) -> ApprovedDecision:
        """propose (Planning Core) → consent (nghiệp vụ) → approve (Physical Guard lại nếu bị chỉnh). Gọi dưới khoá trạm."""
        kernel = station.kernel
        if kernel.algorithms is not self.algorithms(station):
            self.configure(station)
        scenario = replace(kernel.scenario, tariff=_sim_tariff(ctx.tariff, ctx.now, kernel.now))
        proposal = kernel.propose(scenario=scenario)
        forced = _start_minimums(ctx, proposal.observation, proposal.interval_minutes)
        fitted = _fit_with_minimums(
            proposal.setpoints_kw, forced, proposal.candidates, proposal.budgets.output_kw, proposal.effective_limits
        )
        approved = kernel.approve(proposal, fitted, adjustments=forced)
        self.last_diagnostics = {
            "policy": {"id": proposal.policy_id, "version": proposal.policy_version},
            "state_version": proposal.state_version,
            "interval_minutes": proposal.interval_minutes,
            "planning_interval_minutes": proposal.planning_interval_minutes,
            "budgets_kw": dict(proposal.budgets.output_kw),
            "consent_forced_start_kw": forced,
            "reason_codes": list(approved.reason_codes),
            **{zone: proposal.diagnostics[zone] for zone in proposal.diagnostics},
        }
        return approved

    def plan(self, ctx: PlanningContext) -> SchedulePlan:
        started = time.perf_counter()
        station = self._station()
        fallback = ctx.config.optimizer.planning_step_minutes
        # Giữ khoá trạm suốt lúc đọc: plan() chạy trên thread solver, request khác có thể step() trạm cùng lúc.
        with station.lock:
            try:
                approved = self.decide(station, ctx)
                assignments = dict(approved.proposal.assignments)
                setpoints = dict(approved.setpoints_kw)
                interval = approved.proposal.interval_minutes
            except ConstraintViolationError:
                # REJECTED_BEFORE_APPLY: không cấp điện mới, giữ gán cổng hiện tại (lịch an toàn 0 kW).
                logger.exception("%s: Physical Guard từ chối đề xuất — lịch an toàn (0 kW)", self.name.value)
                self.last_diagnostics = {"reason_codes": [ReasonCode.REJECTED_BEFORE_APPLY]}
                assignments, setpoints, interval = {}, {}, fallback
                station.kernel.next_decision_minute = station.kernel.now + fallback
            queue = [b for b in ctx.state.queue if b not in assignments.values()]
            return _to_plan(self.name, ctx, station, assignments, setpoints, queue, interval, started)


def _start_minimums(ctx: PlanningContext, observation, interval: int) -> dict[str, float]:
    """Xe nào phải bắt đầu sạc trong khoảng này theo consent.max_start_delay_minutes, và công suất tối thiểu.

    Cùng quy tắc với LP backend (`optimizer/horizon.py:_start_requirement`): mốc là lúc xe cắm (`plugged_in_at`; xe vừa
    được gán = now); hạn = mốc + max_start_delay; khoảng nào kết thúc sau hạn mà xe chưa nhận điện thì phải sạc, mức
    = min(cho phép, đủ để giao phần còn thiếu trong khoảng). Đã bắt đầu rồi thì không ép (tạm dừng sau đó thuộc
    consent allow_power_reduction — chờ nhóm chốt, HANDOFF).
    """
    bookings = {b.booking_id: b for b in ctx.bookings}
    progress = {p.booking_id: p for p in ctx.state.sessions}
    interval_end = ctx.now + timedelta(minutes=interval)
    hours = interval / 60
    efficiency = observation.scenario.efficiency
    minimums: dict[str, float] = {}
    for vid, candidate in observation.candidates.items():
        booking, item = bookings.get(vid), observation.vehicles[vid]
        state = progress.get(vid)
        if booking is None or item.remaining_kwh <= TOL:
            continue
        if state is not None and state.delivered_grid_kwh > TOL:
            continue
        anchor = state.plugged_in_at if state is not None and state.plugged_in_at else ctx.now
        if interval_end <= anchor + timedelta(minutes=booking.consent.max_start_delay_minutes):
            continue
        need_kw = item.remaining_kwh / efficiency / hours
        minimums[vid] = round(min(candidate.allowed_kw, need_kw), 6)
    return minimums


def _fit_with_minimums(
    setpoints: Mapping[str, float],
    minimums: Mapping[str, float],
    candidates: Mapping[str, Candidate],
    budgets: Mapping[str, float],
    limits,
) -> dict[str, float]:
    """Nâng xe bắt buộc lên mức tối thiểu, rồi co xe khác (trước) và xe bắt buộc (sau) cho vừa tủ → vùng → lưới.

    Chỉ hạ công suất nên tầng đã vừa không bị vỡ lại. Guard simulator kiểm lại kết quả ngay sau đó.
    """
    result = {vid: float(kw) for vid, kw in setpoints.items()}
    for vid, kw in minimums.items():
        result[vid] = max(result.get(vid, 0.0), kw)
    if not minimums:
        return result

    def shrink(members: list[str], cap: float) -> None:
        total = sum(result.get(v, 0.0) for v in members)
        excess = total - cap
        for group in ([v for v in members if v not in minimums], [v for v in members if v in minimums]):
            if excess <= TOL:
                return
            group_total = sum(result.get(v, 0.0) for v in group)
            if group_total <= TOL:
                continue
            factor = max(0.0, (group_total - excess) / group_total)
            for v in group:
                result[v] = result.get(v, 0.0) * factor
            excess -= group_total * (1 - factor)

    vids = list(result)
    for cabinet, cap in limits.cabinet_output_kw.items():
        shrink([v for v in vids if candidates[v].cabinet.id == cabinet], cap)
    for zone, cap in limits.zone_output_kw.items():
        shrink([v for v in vids if candidates[v].cabinet.zone == zone], min(cap, budgets.get(zone, cap)))
    if limits.shared_supply:
        shrink(vids, limits.grid_input_kw * limits.conversion)
    else:
        for zone, cap in limits.independent_grid_input_kw.items():
            shrink([v for v in vids if candidates[v].cabinet.zone == zone], cap * limits.conversion)
    return result


def _to_plan(name, ctx, station, assignments, setpoints, queue, interval, started) -> SchedulePlan:
    """Bước đầu của lịch = setpoint của khoảng quyết định này (receding horizon, như MPC của backend)."""
    connector_of = {vid: station.connector_of(port) for port, vid in assignments.items()}
    etas = _queue_etas(station, ctx, assignments, setpoints)
    sessions = []
    for progress in ctx.state.sessions:
        bid = progress.booking_id
        connector = connector_of.get(bid, progress.connector_id)
        if connector:
            slots = [PowerSlot(start=ctx.now, power_kw=round(max(setpoints.get(bid, 0.0), 0.0), 3))]
        elif bid in etas:
            slots = [PowerSlot(start=etas[bid], power_kw=0.0)]  # ước tính lúc có cổng — cho ETA hàng chờ (AC2)
        else:
            slots = []
        sessions.append(SessionPlan(booking_id=bid, connector_id=connector, slots=slots))
    return SchedulePlan(
        version=ctx.state.schedule_version + 1,
        strategy=name,
        created_at=datetime.now(UTC),
        horizon_start=ctx.now,
        step_minutes=interval,
        sessions=sessions,
        queue=queue,
        solve_time_s=round(time.perf_counter() - started, 4),
    )


def _queue_etas(station, ctx: PlanningContext, assignments: dict, setpoints: dict) -> dict[str, datetime]:
    """Ước tính lúc xe đang chờ có cổng (AC2): xe thứ k của vùng nhận cổng rảnh sớm thứ k.

    Cổng AC rảnh khi xe rời theo giờ khai báo (F14); cổng DC rảnh khi xe sạc xong theo setpoint hiện tại + thời gian
    rút, không muộn hơn giờ rời. Cổng trống rảnh ngay. [GIẢ ĐỊNH] — không tính đường sạc DC trong ước tính.
    """
    observation = station.scheduling_observation(1)
    now_minute = observation.minute
    delay = station.scenario.delay
    occupied = dict(observation.ports) | dict(assignments)
    free_at: dict[str, list[float]] = {}
    for port, (cabinet, _) in station.queue.connectors.items():
        vid = occupied.get(port)
        if vid is None:
            release = float(now_minute)
        else:
            vehicle = observation.vehicles[vid]
            release = float(vehicle.vehicle.departure)
            if cabinet.zone == "DC":
                power = setpoints.get(vid, 0.0)
                if vehicle.completed_at is not None:
                    release = min(release, vehicle.completed_at + delay)
                elif power > TOL:
                    hours = vehicle.remaining_kwh / (power * station.scenario.efficiency)
                    release = min(release, now_minute + hours * 60 + delay)
        free_at.setdefault(cabinet.zone, []).append(max(release, now_minute))
    etas: dict[str, datetime] = {}
    for zone, queue in observation.queues.items():
        waiting = [vid for vid in queue if vid not in assignments.values()]
        for vid, release in zip(waiting, sorted(free_at.get(zone, [])), strict=False):
            etas[vid] = ctx.now + timedelta(minutes=release - now_minute)
    return etas


def _sim_tariff(tariff: Tariff | None, now: datetime, now_minute: int) -> SimTariff | None:
    """Biểu giá backend (khung giờ trong ngày) → `Tariff` simulator (phút của trạm) cho 48 giờ tới."""
    if tariff is None:
        return None
    local = now.astimezone(now.tzinfo)
    day0 = local.replace(hour=0, minute=0, second=0, microsecond=0)
    boundaries = []
    for day in range(-1, TARIFF_HORIZON_HOURS // 24 + 1):
        for period in tariff.periods:
            at = day0 + timedelta(days=day, hours=period.start.hour, minutes=period.start.minute)
            boundaries.append((at, period.price_per_kwh))
    boundaries.sort(key=lambda item: item[0])
    current = max((b for b in boundaries if b[0] <= local), key=lambda item: item[0])
    starts, prices = [now_minute], [current[1]]
    for at, price in boundaries:
        minute = now_minute + int((at - local).total_seconds() // 60)
        if minute > now_minute and at <= local + timedelta(hours=TARIFF_HORIZON_HOURS):
            starts.append(minute)
            prices.append(price)
    return SimTariff(tariff.currency, tuple(starts), tuple(prices))


__all__ = ["POLICIES", "SIMULATOR_STRATEGIES", "TOL", "SimulatorScheduler", "selection"]
