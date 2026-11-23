"""Bộ lập lịch backend dùng NGUYÊN thuật toán của simulator R&D (M2b / M3a / M3b) — simulator là gốc.

Vì sao ở `src/services/` chứ không ở `src/optimizer/`: test kiến trúc cấm optimizer import `src.simulator`. Ở đây chỉ
ghép lại đúng các bước của `src/simulator/src/engine/hybrid.py:HybridSimulator.step` — dispatch theo vùng →
coordinator chia ngân sách → optimizer theo vùng → Guard vật lý của simulator — trên trạng thái thật của
`HybridStation`, rồi trả `SchedulePlan` như mọi `Scheduler`. Lệnh vẫn đi `diff_commands` → `guard/dispatcher.py`
(ADR-002): bộ lập lịch không chạm trạm.

Chọn thuật toán: bảng `POLICIES` của `src/optimizer/registry.py` (nguồn của số MVP-2 / MVP-3), dựng bằng
`resolve_algorithms` của simulator. Không sửa code simulator.

[GIẢ ĐỊNH] / khác biệt đã biết so với HybridSimulator.run():
  - Khoảng quyết định = `optimizer.planning_step_minutes` (15') hoặc tới lần tính lại kế tiếp do sự kiện; simulator chạy
    tới mốc kế tiếp của kịch bản. Setpoint giữ nguyên giữa hai lần tính; trạm tự cắt theo đường sạc DC mỗi phút.
  - Biểu giá TOU của backend (`config/tariff.yaml`) đổi sang `Tariff` của simulator cho 48 giờ tới.
  - Consent của cư dân (lùi giờ / giảm công suất) chưa là ràng buộc của thuật toán simulator — lệnh vượt consent vẫn bị
    `guard/approval.py` giữ lại chờ duyệt như mọi chiến lược.
"""

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType

from src.guard.physical.validator import guard, validate_budgets, validate_dispatch
from src.models.charging import PowerSlot, SchedulePlan, SessionPlan, StrategyName
from src.models.physical_constraints import TOL, ConstraintViolationError
from src.models.scheduling.observations import Candidate, VehicleObservation
from src.models.scheduling.optimization import PowerProposal
from src.models.simulation_core import Tariff as SimTariff
from src.models.station import Tariff
from src.optimizer.base import PlanningContext
from src.optimizer.registry import POLICIES as REGISTRY_POLICIES
from src.simulator.src.algorithms import Algorithms, resolve_algorithms

logger = logging.getLogger(__name__)

# Một nguồn policy: src/optimizer/registry.py POLICIES (ADR-019) — (dispatch DC, optimizer AC, optimizer DC, coordinator).
# Backend chỉ ánh xạ mã chiến lược sang khoá registry; không chép bảng.
POLICIES: Mapping[StrategyName, tuple[str, str, str, str]] = {
    strategy: REGISTRY_POLICIES[strategy.value]
    for strategy in (StrategyName.SIM_B0, StrategyName.SIM_M2B, StrategyName.SIM_M3A, StrategyName.SIM_M3B)
}
SIMULATOR_STRATEGIES = frozenset(POLICIES)
TARIFF_HORIZON_HOURS = 48


def selection(strategy: StrategyName) -> dict:
    dispatch, ac, dc, coordinator = POLICIES[strategy]
    return {"dispatch": {"DC": dispatch}, "optimizers": {"AC": ac, "DC": dc}, "coordinator": coordinator}


class SimulatorScheduler:
    """`Scheduler` (src/optimizer/base.py) cho M2b / M3a / M3b. `station` trả HybridStation đang chạy."""

    def __init__(self, name: StrategyName, station: Callable[[], object]) -> None:
        if name not in POLICIES:
            raise ValueError(f"Không phải chiến lược simulator: {name!r}")
        self.name = name
        self._station = station
        self._algorithms: Algorithms | None = None
        self.metadata: dict = {}
        self.last_diagnostics: dict = {}

    def algorithms(self) -> Algorithms:
        if self._algorithms is None:
            self._algorithms, self.metadata = resolve_algorithms(
                selection(self.name), self._station().scenario, f"backend:{self.name.value}"
            )
        return self._algorithms

    def plan(self, ctx: PlanningContext) -> SchedulePlan:
        started = time.perf_counter()
        station = self._station()
        interval = ctx.config.optimizer.planning_step_minutes
        # Giữ khoá trạm suốt lúc đọc: plan() chạy trên thread solver, request khác có thể step() trạm cùng lúc.
        with station.lock:
            try:
                assignments, setpoints, queue = self._decide(station, ctx, interval)
            except ConstraintViolationError:
                # Guard simulator từ chối đề xuất: không cấp điện mới, giữ gán cổng hiện tại.
                logger.exception("%s: Guard simulator từ chối đề xuất — lịch an toàn (0 kW)", self.name.value)
                assignments, setpoints, queue = {}, {}, list(ctx.state.queue)
            return _to_plan(self.name, ctx, station, assignments, setpoints, queue, interval, started)

    # ---- các bước của HybridSimulator.step ---------------------------------------------------

    def _decide(self, station, ctx: PlanningContext, interval: int) -> tuple[dict, dict, list[str]]:
        algorithms = self.algorithms()
        base = station.scheduling_observation(interval)
        scenario = replace(base.scenario, tariff=_sim_tariff(ctx.tariff, ctx.now, base.minute))
        limits = base.limits()

        # 1. dispatch theo vùng (xe đang chờ → cổng trống), kiểm bằng validate_dispatch của simulator
        assignments: dict[str, str] = {}
        for zone, policy in algorithms.dispatch.items():
            observation = station.dispatch_observation(zone)
            plan = policy(observation)
            validate_dispatch(observation, plan)
            assignments.update(plan)

        # 2. quan sát SAU dispatch (như hybrid.py: candidates gồm cả xe vừa được gán)
        vehicles = dict(base.vehicles)
        ports = dict(base.ports)
        candidates = dict(base.candidates)
        for port, vid in assignments.items():
            cabinet, _ = station.queue.connectors[port]
            item = vehicles[vid]
            vehicles[vid] = VehicleObservation(item.vehicle, "CHARGING", item.soc, port, base.minute, item.completed_at)
            ports[port] = vid
            allowed = min(cabinet.port_kw, station.adapter.acceptance_kw(item.vehicle, interval))
            candidates[vid] = Candidate(cabinet, allowed)
        queues = {zone: tuple(v for v in q if v not in assignments.values()) for zone, q in base.queues.items()}
        observation = replace(
            base,
            scenario=scenario,
            vehicles=MappingProxyType(vehicles),
            ports=MappingProxyType(ports),
            queues=MappingProxyType(queues),
            candidates=MappingProxyType(candidates),
        )

        # 3. coordinator chia ngân sách vùng, kiểm bằng validate_budgets
        demand = MappingProxyType(
            {
                zone: sum(c.allowed_kw for c in candidates.values() if c.cabinet.zone == zone)
                for zone in scenario.zone_kw
            }
        )
        budgets = algorithms.coordinator(observation, demand)
        validate_budgets(observation, budgets)

        # 4. optimizer theo vùng (như HybridSimulator._power_plan)
        setpoints: dict[str, float] = {}
        diagnostics: dict = {"budgets_kw": dict(budgets.output_kw)}
        for zone, optimizer in algorithms.optimizers.items():
            eligible = {vid: c for vid, c in candidates.items() if c.cabinet.zone == zone}
            zone_scenario = scenario
            if not getattr(optimizer, "uses_published_limits", False):
                zone_scenario = limits.as_optimizer_scenario(scenario)
            zone_obs = replace(observation, scenario=zone_scenario, candidates=MappingProxyType(eligible))
            proposal = optimizer(zone_obs, zone, budgets.output_kw[zone])
            if isinstance(proposal, PowerProposal):
                diagnostics[zone] = proposal.diagnostics
                proposal = proposal.output_kw
            if not isinstance(proposal, Mapping) or proposal.keys() - eligible.keys():
                raise ConstraintViolationError(f"{zone} optimizer đề xuất xe không hợp lệ")
            setpoints.update({vid: float(kw) for vid, kw in proposal.items()})

        # 5. Consent cư dân "được lùi giờ bắt đầu tối đa" (backend, ADR-018): quá hạn mà chưa sạc → buộc bắt đầu
        forced = _start_minimums(ctx, observation, interval)
        setpoints = _fit_with_minimums(setpoints, forced, candidates, budgets.output_kw, limits)
        diagnostics["consent_forced_start_kw"] = forced

        # 6. Guard vật lý của simulator trên đề xuất cuối, với ngân sách coordinator vừa giao
        guard(scenario, candidates, setpoints, budgets.output_kw, limits=limits)
        self.last_diagnostics = diagnostics

        waiting = [b for b in ctx.state.queue if b not in assignments.values()]
        return assignments, setpoints, waiting


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
