"""Application service cho luồng đặt lịch sạc của cư dân — điểm vào CHUNG của Agent và API.

Vì sao tồn tại: tool của Agent (F1) và form thủ công (NFR: LLM lỗi vẫn đặt được lịch)
phải đi CÙNG một đường nghiệp vụ, nếu không hai đường sẽ lệch nhau. Agent chỉ được
gọi các hàm ở đây — không gọi thẳng optimizer/guard/simulator (FR5; khoá bởi
tests/test_architecture.py).

Đồng bộ / bất đồng bộ (ADR-007):
  - hàm CHỈ ĐỌC là `def` (router chạy trong threadpool): quote, current_booking,
    session_view, queue_status, explain;
  - hàm PHÁT SỰ KIỆN là `async def` vì event_bus.publish → control_loop.on_event chạy ngay
    trong request: book, cancel, change.

Lỗi nghiệp vụ: ném services.errors.DomainError (không ném HTTPException).
`resident_id` LUÔN do phía gọi lấy từ token (router) hoặc RunnableConfig (tool) — ADR-006.

Owner: TV3. Task: T2.2 (gán đầu nối, hàng đợi, idempotency), T2.5 (Agent), T2.8 (đổi yêu cầu).
"""

import hashlib
import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.models.api import BookingChangeRequest, ErrorCode, QueueStatus, ResidentSessionView
from src.models.charging import (
    Alternative,
    AlternativeKind,
    Booking,
    BookingStatus,
    ChargeRequest,
    ConsentScope,
    ScheduleProposal,
    VehicleSpec,
)
from src.models.events import EventType, StationEvent
from src.models.station import StationConfig
from src.optimizer.assignment import assign_connectors
from src.optimizer.lp_model import solve_with_unmet
from src.services import catalog, event_bus, repository, solver
from src.services.control_loop import build_planning_context
from src.services.energy import estimate_energy
from src.services.errors import DomainError
from src.services.runtime import StationRuntime, get_runtime, visit_of

QUOTE_ID = "quote-what-if"
UNMET_TOL_KWH = 0.05  # dưới mức này coi như đủ (sai số làm tròn của LP)
ACTIVE = (BookingStatus.CONFIRMED, BookingStatus.QUEUED, BookingStatus.CHARGING)


# ---- helpers -----------------------------------------------------------------------------


def _vehicle(model: str) -> VehicleSpec:
    try:
        return catalog.get_vehicle(model)
    except catalog.UnknownVehicleError:
        raise DomainError(ErrorCode.NOT_FOUND, f"Không có mẫu xe {model!r} trong danh mục") from None


def vehicle_power_cap(config: StationConfig, request: ChargeRequest, vehicle: VehicleSpec) -> float:
    """min(cổng tốt nhất của vùng, giới hạn của xe) — CODE tính lúc đặt, optimizer/guard không gọi catalog."""
    ports = [c.max_power_kw for c in config.connectors if c.zone == request.zone]
    if not ports:
        raise DomainError(ErrorCode.NOT_FOUND, f"Bãi không có cổng vùng {request.zone}")
    if request.zone == "DC":
        if vehicle.max_dc_kw is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"Xe {vehicle.vehicle_model} không sạc DC")
        return min(max(ports), vehicle.max_dc_kw)
    return min(max(ports), vehicle.max_ac_power_kw)


def _local(dt: datetime, rt: StationRuntime) -> str:
    return dt.astimezone(ZoneInfo(rt.config.timezone)).strftime("%H:%M %d/%m")


def _request_hash(request: ChargeRequest) -> str:
    return hashlib.sha256(request.model_dump_json().encode()).hexdigest()


def _hypothetical(rt: StationRuntime, request: ChargeRequest, resident_id: str, booking_id: str) -> Booking:
    vehicle = _vehicle(request.vehicle_model)
    energy = estimate_energy(vehicle, request.soc_now, request.soc_target)
    return Booking(
        booking_id=booking_id,
        resident_id=resident_id,
        request=request,
        status=BookingStatus.CONFIRMED,
        energy=energy,
        max_charge_power_kw=vehicle_power_cap(rt.config, request, vehicle),
        schedule_version=0,
        created_at=rt.clock(),
    )


def _what_if(rt: StationRuntime, candidate: Booking, exclude: str | None = None) -> ScheduleProposal:
    """Thêm booking giả định vào PlanningContext, giải LP (chiến lược B), đọc điện thiếu — KHÔNG giữ chỗ."""
    base = build_planning_context(rt)
    others = tuple(b for b in base.bookings if b.booking_id != exclude)
    ctx = replace(base, bookings=(*others, candidate), oracle_bookings=())
    assignment = assign_connectors(ctx, "edf")
    plan, unmet_by_booking = solver.run(solve_with_unmet, ctx, assignment, rt.scheduler.name)
    session = next((s for s in plan.sessions if s.booking_id == candidate.booking_id), None)
    energy = candidate.energy
    need = energy.grid_energy_kwh
    unmet = unmet_by_booking.get(candidate.booking_id, need)
    connector_id = session.connector_id if session else None
    step = timedelta(minutes=plan.step_minutes)
    tz = ZoneInfo(rt.config.timezone)
    planned_start = session.slots[0].start if session and session.slots else None
    planned_end = (session.slots[-1].start + step) if session and session.slots else None
    if planned_end and planned_end > candidate.request.deadline:
        planned_end = candidate.request.deadline
    cost = None
    if session and session.slots:
        cost = round(
            sum(
                s.power_kw * plan.step_minutes / 60 * rt.tariff.price_at(s.start.astimezone(tz).time())
                for s in session.slots
            )
        )
    queue_position = (
        (assignment.queue.index(candidate.booking_id) + 1) if candidate.booking_id in assignment.queue else None
    )
    feasible = connector_id is not None and unmet <= UNMET_TOL_KWH
    reasons = [f"Cần {energy.grid_energy_kwh:.1f} kWh (tính bằng code từ dung lượng pin và hiệu suất, FR3)"]
    if connector_id:
        reasons.append(f"Đầu nối {connector_id}, công suất tối đa {candidate.max_charge_power_kw:g} kW")
    if planned_start and planned_end:
        reasons.append(f"Dự kiến sạc {_local(planned_start, rt)} → {_local(planned_end, rt)}")
    if queue_position:
        reasons.append(f"Đang hết cổng {candidate.request.zone}: vị trí {queue_position} trong hàng đợi")
    if unmet > UNMET_TOL_KWH:
        reasons.append(f"Thiếu khoảng {unmet:.1f} kWh so với yêu cầu trước giờ lấy xe")
    slack = (candidate.request.deadline - planned_end).total_seconds() / 60 if feasible and planned_end else None
    alternatives = [] if feasible else _alternatives(rt, candidate, need - unmet, planned_start, connector_id)
    return ScheduleProposal(
        feasible=feasible,
        energy=energy,
        connector_id=connector_id,
        planned_start=planned_start,
        planned_end=planned_end,
        estimated_cost_vnd=cost,
        slack_minutes=round(slack) if slack is not None else None,
        queue_position=queue_position,
        reasons=reasons,
        alternatives=alternatives,
    )


def _alternatives(
    rt: StationRuntime, candidate: Booking, deliverable_kwh: float, start: datetime | None, connector_id: str | None
) -> list[Alternative]:
    """FR4 — luôn ≥ 1 phương án: giờ khác (đủ điện), mức pin thấp hơn (kịp giờ), vào hàng đợi."""
    req = candidate.request
    vehicle = _vehicle(req.vehicle_model)
    begin = max(start or req.arrival_time or rt.clock(), rt.clock())
    hours_needed = candidate.energy.grid_energy_kwh / candidate.max_charge_power_kw
    later = begin + timedelta(hours=hours_needed)
    later = later.replace(second=0, microsecond=0) + timedelta(minutes=15 - later.minute % 15)
    options = [
        Alternative(
            kind=AlternativeKind.OTHER_TIME,
            description=f"Lấy xe lúc {_local(later, rt)} để đạt {req.soc_target:g}%",
            deadline=later,
        )
    ]
    efficiency = candidate.energy.efficiency
    reachable = math.floor(req.soc_now + max(deliverable_kwh, 0) * efficiency / vehicle.usable_capacity_kwh * 100)
    if req.soc_now < reachable < req.soc_target:
        options.append(
            Alternative(
                kind=AlternativeKind.LOWER_TARGET,
                description=f"Sạc tới {reachable}% thì kịp giờ lấy xe",
                soc_target=reachable,
            )
        )
    if connector_id is None:
        options.append(
            Alternative(
                kind=AlternativeKind.JOIN_QUEUE, description="Vào hàng đợi, hệ thống gán cổng khi có cổng trống"
            )
        )
    return options


def _own_active(booking_id: str, resident_id: str) -> Booking:
    booking = repository.get_booking(booking_id)
    if booking is None or booking.resident_id != resident_id:
        raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy lịch sạc này")  # không lộ booking của người khác
    if booking.status not in ACTIVE:
        raise DomainError(ErrorCode.BOOKING_CONFLICT, f"Lịch sạc đã ở trạng thái {booking.status.value}")
    return booking


# ---- API ---------------------------------------------------------------------------------


def quote(request: ChargeRequest, resident_id: str) -> ScheduleProposal:
    """What-if cho màn S3: hỏi bộ tối ưu phương án, KHÔNG giữ chỗ.

    Cách làm (docs/plan/30-ai.md §5.3): thêm booking giả định vào PlanningContext, giải, đọc
    điện thiếu. Không khả thi thì PHẢI trả ≥ 1 phương án thay thế (FR4 — ScheduleProposal ép
    điều này). `reasons` do code sinh từ nghiệm, Agent chỉ diễn đạt lại.
    """
    rt = get_runtime()
    rt.sync_clock()
    return _what_if(rt, _hypothetical(rt, request, resident_id, QUOTE_ID))


async def book(
    request: ChargeRequest,
    resident_id: str,
    consent: ConsentScope | None = None,
    idempotency_key: str | None = None,
) -> Booking:
    """Chốt lịch (sau khi cư dân bấm "Xác nhận" ở S3). Phát BOOKING_CREATED → control_loop tính lại ngay.

    - consent=None → lấy ConsentScope mặc định trong hồ sơ cư dân (F8, FR13).
    - idempotency_key: cùng key + cùng request trả lại booking cũ; khác request → DomainError
      IDEMPOTENCY_MISMATCH. Luồng chat dùng key "chat:{session_id}" (ADR-008).
    - Cư dân đã có booking đang hiệu lực → DomainError BOOKING_CONFLICT (mặc định Q6).
    - Tính lại mà không còn khả thi (trạm đã đổi từ lúc quote) → DomainError PROPOSAL_EXPIRED.
    """
    request_hash = _request_hash(request)
    if idempotency_key:
        existing = repository.find_idempotent(idempotency_key, resident_id, request_hash)
        if existing is not None:
            return existing
    current = repository.active_booking(resident_id)
    if current is not None:
        raise DomainError(ErrorCode.BOOKING_CONFLICT, f"Bạn đã có lịch sạc {current.booking_id} đang hiệu lực")
    rt = get_runtime()
    rt.sync_clock()
    booking_id = uuid4().hex[:12]
    candidate = _hypothetical(rt, request, resident_id, booking_id)
    proposal = _what_if(rt, candidate)
    if not proposal.feasible:
        raise DomainError(
            ErrorCode.PROPOSAL_EXPIRED,
            "Phương án không còn kịp hạn — " + "; ".join(a.description for a in proposal.alternatives),
        )
    user = repository.get_user(resident_id)
    booking = candidate.model_copy(
        update={
            "status": BookingStatus.QUEUED if proposal.queue_position else BookingStatus.CONFIRMED,
            "consent": consent or (user.consent if user else ConsentScope()),
            "connector_id": proposal.connector_id,
            "planned_start": proposal.planned_start,
            "planned_end": proposal.planned_end,
            "estimated_cost_vnd": proposal.estimated_cost_vnd,
            "schedule_version": rt.plan.version if rt.plan else 0,
            "created_at": datetime.now(UTC),
        }
    )
    repository.save_booking(booking, idempotency_key=idempotency_key, request_hash=request_hash)
    async with rt.lock:
        rt.simulator.upsert_vehicle(visit_of(booking, rt.simulator.now))
    await event_bus.publish(
        StationEvent(type=EventType.BOOKING_CREATED, occurred_at=rt.clock(), booking_id=booking.booking_id)
    )
    return repository.get_booking(booking.booking_id) or booking


async def cancel(booking_id: str, resident_id: str) -> Booking:
    booking = _own_active(booking_id, resident_id)
    cancelled = booking.model_copy(update={"status": BookingStatus.CANCELLED})
    repository.save_booking(cancelled)
    rt = get_runtime()
    async with rt.lock:
        rt.sync_clock()
        rt.simulator.remove_vehicle(booking_id)
    await event_bus.publish(
        StationEvent(type=EventType.BOOKING_CANCELLED, occurred_at=rt.clock(), booking_id=booking_id)
    )
    return cancelled


async def change(booking_id: str, patch: BookingChangeRequest, resident_id: str) -> Booking:
    """FR8 "đổi yêu cầu": đổi soc_target / deadline của booking đang hiệu lực, phát BOOKING_CHANGED.

    Dựng lại ChargeRequest (validator chạy lại) và tính lại kWh bằng services.energy (FR3).
    Không khả thi → DomainError kèm phương án thay thế (FR4), booking cũ giữ nguyên.
    """
    booking = _own_active(booking_id, resident_id)
    try:
        request = ChargeRequest.model_validate({**booking.request.model_dump(), **patch.model_dump(exclude_none=True)})
    except ValueError as exc:
        raise DomainError(ErrorCode.BOOKING_CONFLICT, f"Yêu cầu mới không hợp lệ: {exc}") from None
    rt = get_runtime()
    rt.sync_clock()
    candidate = _hypothetical(rt, request, resident_id, booking_id)
    proposal = _what_if(rt, candidate, exclude=booking_id)
    if not proposal.feasible:
        raise DomainError(
            ErrorCode.PROPOSAL_EXPIRED,
            "Không đổi được — " + "; ".join(a.description for a in proposal.alternatives),
        )
    updated = booking.model_copy(
        update={
            "request": request,
            "energy": candidate.energy,
            "max_charge_power_kw": candidate.max_charge_power_kw,
            "planned_start": proposal.planned_start or booking.planned_start,
            "planned_end": proposal.planned_end,
            "estimated_cost_vnd": proposal.estimated_cost_vnd,
        }
    )
    repository.save_booking(updated)
    async with rt.lock:
        rt.simulator.upsert_vehicle(visit_of(updated, rt.simulator.now))
    await event_bus.publish(StationEvent(type=EventType.BOOKING_CHANGED, occurred_at=rt.clock(), booking_id=booking_id))
    return repository.get_booking(booking_id) or updated


def current_booking(resident_id: str) -> Booking | None:
    """Thẻ xe ở S2: lịch hiện tại (đầu nối, khung giờ)."""
    return repository.active_booking(resident_id)


def session_view(resident_id: str) -> ResidentSessionView:
    """S2 (FR15): booking + lịch công suất + tiến độ sạc + % pin ước tính của chính cư dân."""
    booking = repository.active_booking(resident_id)
    if booking is None:
        return ResidentSessionView()
    rt = get_runtime()
    rt.sync_clock()
    state = rt.simulator.state()
    progress = next((s for s in state.sessions if s.booking_id == booking.booking_id), None)
    plan = next((s for s in rt.plan.sessions if s.booking_id == booking.booking_id), None) if rt.plan else None
    soc = None
    if progress is not None:
        vehicle = _vehicle(booking.request.vehicle_model)
        gained = progress.delivered_grid_kwh * booking.energy.efficiency / vehicle.usable_capacity_kwh * 100
        soc = round(min(booking.request.soc_now + gained, booking.request.soc_target), 1)
    return ResidentSessionView(booking=booking, plan=plan, progress=progress, soc_estimate=soc)


def queue_status(resident_id: str) -> QueueStatus:
    """US2 / AC2 — vị trí hàng đợi + thời gian chờ dự kiến (từ lịch hiện hành; F6 hoãn)."""
    rt = get_runtime()
    rt.sync_clock()
    state = rt.simulator.state()
    booking = repository.active_booking(resident_id)
    if booking is None or booking.booking_id not in state.queue:
        return QueueStatus(booking_id=booking.booking_id if booking else None, queue_length=len(state.queue))
    position = state.queue.index(booking.booking_id) + 1
    session = next((s for s in rt.plan.sessions if s.booking_id == booking.booking_id), None) if rt.plan else None
    start = session.slots[0].start if session and session.slots else None
    wait = max((start - rt.clock()).total_seconds() / 60, 0) if start else None
    return QueueStatus(
        booking_id=booking.booking_id,
        position=position,
        queue_length=len(state.queue),
        estimated_wait_minutes=round(wait) if wait is not None else None,
        estimated_start=start,
    )


def explain(resident_id: str) -> list[str]:
    """US3 — lý do lịch được xếp/thay đổi, lấy từ nhật ký quyết định (không suy diễn)."""
    booking = repository.active_booking(resident_id)
    if booking is None:
        return ["Bạn chưa có lịch sạc nào đang hiệu lực."]
    rt = get_runtime()
    facts = [
        f"Lịch {booking.booking_id}: cần {booking.energy.grid_energy_kwh:.1f} kWh để từ {booking.request.soc_now:g}% "
        f"lên {booking.request.soc_target:g}% trước {_local(booking.request.deadline, rt)}."
    ]
    if booking.connector_id:
        facts.append(f"Đầu nối {booking.connector_id}, tối đa {booking.max_charge_power_kw:g} kW (min cổng và xe).")
    session = next((s for s in rt.plan.sessions if s.booking_id == booking.booking_id), None) if rt.plan else None
    if session and session.slots:
        tz = ZoneInfo(rt.config.timezone)
        prices = {rt.tariff.price_at(s.start.astimezone(tz).time()) for s in session.slots}
        facts.append(
            f"Lịch hiện hành v{rt.plan.version}: sạc {_local(session.slots[0].start, rt)} → "
            f"{_local(session.slots[-1].start + timedelta(minutes=rt.plan.step_minutes), rt)}, "
            f"giá {min(prices):,.0f}–{max(prices):,.0f} VND/kWh — bộ tối ưu chọn giờ rẻ nếu vẫn kịp hạn."
        )
    for entry in reversed(repository.list_decisions(limit=20, booking_id=booking.booking_id)):
        at = _local(entry.timestamp, rt)
        cmd = entry.command
        what = f"{cmd.type.value} {cmd.power_kw:g} kW" if cmd.power_kw is not None else cmd.type.value
        if entry.verdict is not None and not entry.verdict.passed:
            facts.append(f"{at}: lệnh {what} bị Guard chặn — " + "; ".join(v.detail for v in entry.verdict.violations))
        elif entry.executed:
            facts.append(
                f"{at}: {cmd.source.value} áp {what} trên {cmd.connector_id}"
                + (f" ({cmd.reason})" if cmd.reason else "")
            )
        else:
            facts.append(f"{at}: {what} — {entry.note or 'chưa thực thi'}")
    return facts
