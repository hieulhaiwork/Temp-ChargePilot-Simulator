"""StationRuntime — composition root của trạm (ADR-007).

Vì sao tồn tại: benchmark phải chạy CÙNG control_loop.on_event và CÙNG đường Guard với vận
hành thật (ADR-002), nhưng với simulator khác, đồng hồ mô phỏng, và không ghi DB hay đẩy
WebSocket. Gom mọi phụ thuộc vào một dataclass rồi truyền tường minh thì hai chế độ dùng
chung code mà không giẫm lên nhau.

    live       get_runtime()                 đồng hồ thật × SIM_TIME_SCALE, store → repository, sinks → DB + WebSocket
    benchmark  build_sim_runtime(sc, strat)  đồng hồ mô phỏng, store + sinks → bộ nhớ

Đây là NƠI DUY NHẤT (cùng simulation_service) giữ nguyên một simulator. Phần ghi
(apply_commands) chỉ guard/dispatcher.py được gọi — tests/test_architecture.py kiểm điều này.
Container phải chạy đúng MỘT worker: runtime nằm trong RAM của process.

Owner: TV3. Task: T2.6 (live), T1.5 (benchmark).
"""

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.config import get_settings
from src.forecast.predict import DepartureForecaster
from src.guard.dispatcher import DispatchSinks
from src.models.api import ErrorCode, Notification, NotificationKind
from src.models.charging import Booking, BookingStatus, SchedulePlan, StrategyName
from src.models.control import Approval, ApprovalStatus, Command, DecisionLogEntry, Role
from src.models.events import StationEvent, WsMessage, WsMessageType
from src.models.planning import Scheduler
from src.models.simulation import Scenario
from src.models.station import LoadPoint, StationConfig, Tariff
from src.models.station_protocols import StationSimulator, VehicleVisit
from src.services.errors import DomainError

logger = logging.getLogger(__name__)

ACTIVE = (BookingStatus.CONFIRMED, BookingStatus.QUEUED, BookingStatus.CHARGING)
RECENT_COMMANDS = 200  # đủ cho cửa sổ anti_flapping (10 phút × 4 cổng)


@dataclass
class RuntimeStore:
    """Dữ liệu bền của một runtime — live trỏ vào repository, benchmark giữ trong bộ nhớ."""

    active_bookings: Callable[[], list[Booking]]
    get_booking: Callable[[str], Booking | None]
    save_booking: Callable[[Booking], None]
    save_plan: Callable[[SchedulePlan], None]
    record_event: Callable[[StationEvent], None]
    record_load: Callable[[LoadPoint], None]
    pending_approvals: Callable[[], list[Approval]]
    add_notification: Callable[[str, Notification], None]
    # DecisionTrace (ADR-019 Phase 4): (trace, closed) — live: tóm tắt vào DB + artifact khi đóng; benchmark: bộ nhớ
    save_trace: Callable[[dict, bool], None] = lambda trace, closed: None


@dataclass
class SimRecorder:
    """Số đo của một lần chạy (benchmark) hoặc của process (live) — MT4, MT5, MT6."""

    replan_durations_s: list[float] = field(default_factory=list)
    blocked_commands: int = 0
    load_trace: list[LoadPoint] = field(default_factory=list)
    decision_traces: list[dict] = field(default_factory=list)  # DecisionTrace đã đóng (benchmark / admission / test)


@dataclass
class StationRuntime:
    """Mọi thứ control_loop.on_event cần — truyền vào, không đọc biến toàn cục."""

    config: StationConfig
    tariff: Tariff
    simulator: StationSimulator  # HybridStation; đọc qua .state()/.step(); KHÔNG gọi phần ghi ở ngoài dispatcher
    scheduler: Scheduler  # SimulatorScheduler (Planning Core của kernel) — make_scheduler(strategy)
    forecaster: DepartureForecaster | None  # chỉ chiến lược C (F6 hoãn — ADR-015 → None)
    clock: Callable[[], datetime]  # trả thời điểm hiện tại CÓ múi giờ
    sinks: DispatchSinks  # nơi dispatcher ghi nhật ký / phê duyệt / thông báo
    store: RuntimeStore
    plan: SchedulePlan | None = None  # lịch hiện hành
    open_trace: dict | None = None  # DecisionTrace của quyết định đang hiệu lực (đóng ở lần tính lại kế tiếp)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # on_event chạy tuần tự
    # Final Review §4.6 — optimistic concurrency của booking: admission chạy NGOÀI khoá; commit (lưu booking + đưa xe
    # vào trạm) dưới `booking_lock`, kiểm lại `booking_version` (tăng mỗi lần tập booking đổi: đặt / đổi / huỷ).
    # Thứ tự khoá: booking_lock rồi lock (on_event chỉ lấy lock) — không deadlock.
    booking_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    booking_version: int = 0
    recent_commands: deque[Command] = field(default_factory=lambda: deque(maxlen=RECENT_COMMANDS))
    rejected_booking_ids: set[str] = field(default_factory=set)  # AC4 — hard_consent_booking_ids
    recorder: SimRecorder = field(default_factory=SimRecorder)
    live: bool = True

    def sync_clock(self) -> list[StationEvent]:
        """Tiến simulator tới đồng hồ của runtime (live: thời gian thật × SIM_TIME_SCALE); trả sự kiện phát sinh."""
        minutes = int((self.clock() - self.simulator.now).total_seconds() // 60)
        return self.simulator.step(minutes) if minutes > 0 else []


def make_station(config: StationConfig, start: datetime, engine: str | None = None):
    """Trạm mô phỏng của backend: `HybridStation` trên kernel dùng chung với simulator (ADR-018, ADR-019 Phase 3).

    `LiveStation` đã bị xoá (DELETION_MANIFEST); STATION_ENGINE chỉ còn "hybrid".
    """
    engine = engine or get_settings().station_engine
    if engine != "hybrid":
        raise ValueError(f"STATION_ENGINE={engine!r} không còn được hỗ trợ — chỉ 'hybrid' (ADR-019 Phase 3)")
    from src.simulator.hybrid_station import HybridStation  # cần ev2gym — import trễ

    dc_name = config.planning.dc_charging_model if config.planning is not None else None
    if dc_name is None:
        return HybridStation(config, start=start)  # mặc định: SyntheticTaperV1 như cũ
    return HybridStation(config, start=start, dc_charging_model=dc_name)


def make_scheduler(
    strategy: StrategyName | str,
    station: Callable[[], object],
    algorithms=None,
    *,
    parameters: dict | None = None,
) -> Scheduler:
    """Policy đã đăng ký (`src/optimizer/registry.py POLICIES`) chạy trên Planning Core của kernel (`SimulatorScheduler`).

    `strategy`: StrategyName hoặc id chuỗi — tra thẳng registry, nên policy mới đăng ký chạy được không sửa ở đây.
    """
    from src.services.hybrid_planner import SimulatorScheduler, is_registered, policy_key

    if not is_registered(strategy):
        from src.optimizer.registry import POLICIES

        raise DomainError(
            ErrorCode.NOT_FOUND,
            f"Policy {policy_key(strategy)!r} không có trong registry — có: {', '.join(POLICIES)}",
        )
    return SimulatorScheduler(strategy, station, algorithms=algorithms, parameters=parameters)


def live_policy(config: StationConfig) -> tuple[str, dict]:
    """Policy của runtime live: `planning.policy_id` của station.yaml nếu có, không thì env LIVE_STRATEGY (như cũ).

    `planning.version` (nếu có) phải khớp version đăng ký trong registry — config không âm thầm chạy bản khác.
    """
    from src.optimizer import registry

    planning = config.planning
    policy_id = planning.policy_id if planning is not None and planning.policy_id else get_settings().live_strategy
    if planning is not None and planning.version is not None and policy_id in registry.POLICIES:
        registered = registry.policy_spec(policy_id).version
        if planning.version != registered:
            raise ValueError(
                f"planning.version={planning.version!r} không khớp version đăng ký của {policy_id}: {registered!r}"
            )
    return policy_id, dict(planning.parameters) if planning is not None else {}


def visit_of(booking: Booking, now: datetime) -> VehicleVisit:
    """Booking → dữ kiện môi trường cho simulator (simulator không biết cư dân / booking)."""
    return VehicleVisit(
        booking_id=booking.booking_id,
        arrival_time=booking.request.arrival_time or now,
        departure_time=booking.request.deadline,
        required_kwh=booking.energy.grid_energy_kwh,
        zone=booking.request.zone,
        max_power_kw=booking.max_charge_power_kw,
        battery_kwh=_battery_kwh(booking),
        soc_now=booking.request.soc_now / 100,
        soc_target=booking.request.soc_target / 100,
        vehicle_model=booking.request.vehicle_model,
    )


def _battery_kwh(booking: Booking) -> float | None:
    """Dung lượng khả dụng: lấy từ danh mục xe; xe lạ thì suy từ năng lượng / Δ%pin."""
    from src.services import catalog  # import trễ như get_runtime: tránh vòng import

    spec = catalog.load_vehicle_catalog().get(booking.request.vehicle_model)
    if spec is not None:
        return spec.usable_capacity_kwh
    delta = (booking.request.soc_target - booking.request.soc_now) / 100
    return booking.energy.battery_energy_kwh / delta if delta > 0 else None


def _remember_executed(rt_ref: list[StationRuntime], entry: DecisionLogEntry) -> None:
    if rt_ref and entry.executed:
        rt_ref[0].recent_commands.append(entry.command)
    if rt_ref and entry.verdict is not None and not entry.verdict.passed:
        rt_ref[0].recorder.blocked_commands += 1


# ---- live --------------------------------------------------------------------------------

_live: StationRuntime | None = None


def _live_clock(config: StationConfig) -> Callable[[], datetime]:
    tz = ZoneInfo(config.timezone)
    scale = get_settings().sim_time_scale
    origin = datetime.now(UTC)

    def clock() -> datetime:
        real = datetime.now(UTC)
        return (origin + (real - origin) * scale).astimezone(tz)

    return clock


def get_runtime() -> StationRuntime:
    """Runtime của chế độ chạy thật — dựng LƯỜI ở lần gọi đầu, giữ lại cho các lần sau.

    Dựng lười (không dựng trong lifespan) để app vẫn khởi động khi DB chậm. Khi dựng: nạp
    repository.latest_plan() + booking còn hiệu lực (NFR: simulator mất trạng thái thì giữ lịch gần nhất
    và cảnh báo — xe đang cắm trước khi restart được coi như đang chờ và gán lại).
    """
    global _live
    if _live is not None:
        return _live
    from src.services import catalog, control_loop, decision_trace, event_bus, realtime, repository

    config = catalog.load_station_config()
    clock = _live_clock(config)
    station = make_station(config, clock())
    rt_ref: list[StationRuntime] = []

    def log_decision(entry: DecisionLogEntry) -> None:
        repository.append_decision(entry)
        _remember_executed(rt_ref, entry)

    async def notify(message: WsMessage, resident_id: str | None) -> None:
        if resident_id is None:
            await realtime.broadcast(message, role=Role.OPERATOR)
            return
        if message.type == WsMessageType.APPROVAL_REQUEST:
            approval = Approval.model_validate(message.payload)
            note = Notification(
                notification_id=approval.approval_id,
                kind=NotificationKind.APPROVAL_REQUEST,
                title="Cần bạn đồng ý điều chỉnh lịch sạc",
                body=approval.impact_summary,
                created_at=message.sent_at,
                approval_id=approval.approval_id,
            )
            repository.add_notification(resident_id, note)
            await realtime.broadcast(
                WsMessage(
                    type=WsMessageType.NOTIFICATION, payload=note.model_dump(mode="json"), sent_at=message.sent_at
                ),
                user_id=resident_id,
            )
        await realtime.broadcast(message, user_id=resident_id)

    store = RuntimeStore(
        active_bookings=lambda: repository.list_bookings(statuses=ACTIVE),
        get_booking=repository.get_booking,
        save_booking=lambda b: repository.save_booking(b),
        save_plan=repository.save_plan,
        record_event=repository.append_event,
        record_load=repository.append_load_point,
        pending_approvals=lambda: repository.list_approvals(status=ApprovalStatus.PENDING),
        add_notification=repository.add_notification,
        save_trace=decision_trace.persist,
    )
    policy_id, parameters = live_policy(config)
    rt = StationRuntime(
        config=config,
        tariff=catalog.load_tariff(),
        simulator=station,
        scheduler=make_scheduler(policy_id, lambda: station, parameters=parameters or None),
        forecaster=None,
        clock=clock,
        sinks=DispatchSinks(log_decision=log_decision, save_approval=repository.save_approval, notify=notify),
        store=store,
        plan=repository.latest_plan(),
    )
    rt_ref.append(rt)
    restored = store.active_bookings()
    for booking in restored:
        rt.simulator.upsert_vehicle(visit_of(booking, rt.simulator.now))
    if restored or rt.plan:
        logger.warning(
            "Khởi động lại runtime: nạp %d booking hiệu lực + lịch v%s; trạng thái cắm/công suất trước đó đã mất",
            len(restored),
            rt.plan.version if rt.plan else "-",
        )
    event_bus.subscribe(None, lambda event: control_loop.on_event(event, rt))
    _live = rt
    return rt


def reset_runtime() -> None:
    """Bỏ runtime đang giữ — dùng trong test và khi vận hành đổi chiến lược."""
    global _live
    from src.services import event_bus

    _live = None
    event_bus.clear()


# ---- benchmark ---------------------------------------------------------------------------


def build_sim_runtime(
    scenario: Scenario,
    strategy: StrategyName | str,
    config: StationConfig,
    tariff: Tariff,
    start: datetime,
    engine: str | None = None,
) -> StationRuntime:
    """Runtime cho MỘT lần chạy benchmark: simulator mới, đồng hồ mô phỏng, store + sinks vào bộ nhớ.

    Đồng hồ = đồng hồ của simulator (simulation_service tự gọi simulator.step). Yêu cầu phê duyệt trong
    benchmark không có người trả lời → hết hạn = không thực thi (AC4), đúng như vận hành thật.
    """
    simulator = make_station(config, start, engine)
    simulator.reset(scenario)
    return _memory_runtime(simulator, make_scheduler(strategy, lambda: simulator), config, tariff)


def fork_runtime(rt: StationRuntime, bookings: list[Booking]) -> StationRuntime:
    """Runtime what-if cho admission: bản fork của trạm + CÙNG policy, control_loop, Guard; store trong bộ nhớ.

    Trạm live không đổi. Phê duyệt đang chờ, lệnh gần đây (anti_flapping), booking đã từ chối và lịch hiện hành được
    chép sang để bản fork đi đúng đường như runtime thật (PHASE3_DESIGN §6).
    """
    fork = rt.simulator.fork()
    # Final Review §4.4: thuật toán của bản fork là bản ĐÃ CÔ LẬP bởi `StationKernel.fork` (thành phần có trạng thái
    # được fork / copy; thành phần khai báo stateless dùng chung — cùng object như trước). Không gắn lại bản live.
    kernel = getattr(fork, "kernel", None)
    live_algorithms = getattr(rt.scheduler, "algorithms", None)
    if kernel is not None:
        algorithms = kernel.algorithms
    else:
        algorithms = live_algorithms() if callable(live_algorithms) else None
    scheduler = make_scheduler(
        rt.scheduler.name,
        lambda: fork,
        algorithms,
        parameters=getattr(rt.scheduler, "parameters", None) or None,
    )
    frt = _memory_runtime(
        fork, scheduler, rt.config, rt.tariff, bookings=bookings, approvals=rt.store.pending_approvals()
    )
    frt.plan = rt.plan
    frt.recent_commands.extend(rt.recent_commands)
    frt.rejected_booking_ids.update(rt.rejected_booking_ids)
    return frt


def _memory_runtime(
    simulator,
    scheduler: Scheduler,
    config: StationConfig,
    tariff: Tariff,
    *,
    bookings: list[Booking] = (),
    approvals: list[Approval] = (),
) -> StationRuntime:
    store_bookings: dict[str, Booking] = {b.booking_id: b for b in bookings}
    store_approvals: dict[str, Approval] = {a.approval_id: a for a in approvals}
    rt_ref: list[StationRuntime] = []

    async def notify(message: WsMessage, resident_id: str | None) -> None:
        return None

    def record_load(point: LoadPoint) -> None:
        if rt_ref:
            rt_ref[0].recorder.load_trace.append(point)

    store = RuntimeStore(
        active_bookings=lambda: [b for b in store_bookings.values() if b.status in ACTIVE],
        get_booking=store_bookings.get,
        save_booking=lambda b: store_bookings.__setitem__(b.booking_id, b),
        save_plan=lambda plan: None,
        record_event=lambda event: None,
        record_load=record_load,
        pending_approvals=lambda: [a for a in store_approvals.values() if a.status == ApprovalStatus.PENDING],
        add_notification=lambda resident_id, note: None,
        save_trace=lambda trace, closed: rt_ref[0].recorder.decision_traces.append(trace) if closed else None,
    )
    rt = StationRuntime(
        config=config,
        tariff=tariff,
        simulator=simulator,
        scheduler=scheduler,
        forecaster=None,
        clock=lambda: simulator.now,
        sinks=DispatchSinks(
            log_decision=lambda entry: _remember_executed(rt_ref, entry),
            save_approval=lambda a: store_approvals.__setitem__(a.approval_id, a),
            notify=notify,
        ),
        store=store,
        live=False,
    )
    rt_ref.append(rt)
    return rt
