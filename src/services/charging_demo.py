"""Dịch vụ sạc GIẢ LẬP trong bộ nhớ — chạy thử Agent đầu–cuối khi charging_service (T2.2) còn là stub.

Bật bằng AGENT_DEMO_SERVICES=true (chỉ dev — config chặn ở production). Cùng chữ ký với
services/charging_service.py, nên tool của Agent không cần biết đang gọi bản nào.

Mô hình cố ý đơn giản: một đầu nối, sạc đều ở min(đầu nối, OBC của xe), giá phẳng.
kWh vẫn tính bằng services.energy (FR3) — đúng công thức thật.
KHÔNG phải bộ tối ưu (không LP, không xét xe khác) — đừng dùng để đo KPI.
Khi T2.2 xong: tắt cờ, giữ file này cho demo / test Agent hoặc xoá.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.models.api import ErrorCode, QueueStatus
from src.models.charging import (
    Alternative,
    AlternativeKind,
    Booking,
    BookingStatus,
    ChargeRequest,
    ConsentScope,
    ScheduleProposal,
)
from src.services import catalog
from src.services.energy import estimate_energy
from src.services.errors import DomainError

DEMO_PRICE_VND_PER_KWH = 3_500
_ACTIVE = {BookingStatus.CONFIRMED, BookingStatus.QUEUED, BookingStatus.CHARGING}

_bookings: dict[str, Booking] = {}  # resident_id → booking gần nhất
_by_idempotency_key: dict[str, Booking] = {}
_now_override: datetime | None = None


def set_now(now: datetime | None = None) -> None:
    """Đặt đồng hồ giả lập cho eval offline/online theo mốc `now` của từng EvalCase."""
    global _now_override
    _now_override = now


def reset() -> None:
    """Xoá toàn bộ booking giả lập (test, nút "Reset" của playground)."""
    global _now_override
    _bookings.clear()
    _by_idempotency_key.clear()
    _now_override = None


def _plan(request: ChargeRequest, grid_kwh: float) -> tuple[str, float, datetime, datetime]:
    """(connector_id, công suất kW, giờ bắt đầu, giờ xong) — hỗ trợ cả AC và DC (ADR-010)."""
    station = catalog.load_station_config()
    tz = ZoneInfo(station.timezone)
    base_now = _now_override.astimezone(tz) if _now_override is not None else datetime.now(tz)
    start = request.arrival_time or base_now
    if request.zone == "DC":
        power_kw = 60.0
        return "DC-01-1", power_kw, start, start + timedelta(hours=grid_kwh / power_kw)
    connector = station.connectors[0]
    power_kw = min(connector.max_power_kw, catalog.get_vehicle(request.vehicle_model).max_ac_power_kw)
    return connector.connector_id, power_kw, start, start + timedelta(hours=grid_kwh / power_kw)


def quote(request: ChargeRequest, resident_id: str) -> ScheduleProposal:
    vehicle = catalog.get_vehicle(request.vehicle_model)
    energy = estimate_energy(vehicle, request.soc_now, request.soc_target)
    connector_id, power_kw, start, end = _plan(request, energy.grid_energy_kwh)
    slack_minutes = (request.deadline - end).total_seconds() / 60
    reasons = [f"Sạc đều {power_kw:g} kW tại đầu nối {connector_id} (giả lập — chưa có bộ tối ưu T2.2)"]

    if slack_minutes >= 0:
        return ScheduleProposal(
            feasible=True,
            energy=energy,
            connector_id=connector_id,
            planned_start=start,
            planned_end=end,
            estimated_cost_vnd=round(energy.grid_energy_kwh * DEMO_PRICE_VND_PER_KWH),
            slack_minutes=round(slack_minutes),
            reasons=reasons,
        )

    # FR4: không kịp hạn → luôn có phương án thay thế.
    local_end = end.astimezone(request.deadline.tzinfo)
    alternatives = [
        Alternative(
            kind=AlternativeKind.OTHER_TIME,
            description=f"Lấy xe lúc {local_end:%H:%M %d/%m} để đạt {request.soc_target:g}%",
            deadline=end,
        )
    ]
    hours_left = max((request.deadline - start).total_seconds() / 3600, 0)
    reachable = int(request.soc_now + hours_left * power_kw * energy.efficiency / vehicle.usable_capacity_kwh * 100)
    if reachable > request.soc_now:
        alternatives.append(
            Alternative(
                kind=AlternativeKind.LOWER_TARGET,
                description=f"Sạc tới {reachable}% thì kịp giờ lấy xe",
                soc_target=reachable,
            )
        )
    return ScheduleProposal(
        feasible=False,
        energy=energy,
        reasons=[*reasons, f"Thiếu khoảng {-slack_minutes:.0f} phút so với giờ lấy xe"],
        alternatives=alternatives,
    )


async def book(
    request: ChargeRequest,
    resident_id: str,
    consent: ConsentScope | None = None,
    idempotency_key: str | None = None,
) -> Booking:
    if idempotency_key and idempotency_key in _by_idempotency_key:
        existing = _by_idempotency_key[idempotency_key]
        if existing.request != request:
            raise DomainError(ErrorCode.IDEMPOTENCY_MISMATCH, "Phiên chat này đã đặt một lịch khác.")
        return existing
    current = _bookings.get(resident_id)
    if current and current.status in _ACTIVE:
        raise DomainError(ErrorCode.BOOKING_CONFLICT, f"Bạn đã có lịch sạc {current.booking_id} đang hiệu lực.")

    proposal = quote(request, resident_id)
    if not proposal.feasible:
        raise DomainError(ErrorCode.PROPOSAL_EXPIRED, "Phương án không còn kịp hạn — hãy chọn phương án thay thế.")

    _, power_kw, _, _ = _plan(request, proposal.energy.grid_energy_kwh)
    booking = Booking(
        booking_id=f"demo-{uuid4().hex[:6]}",
        resident_id=resident_id,
        request=request,
        status=BookingStatus.CONFIRMED,
        energy=proposal.energy,
        max_charge_power_kw=power_kw,
        consent=consent or ConsentScope(),
        connector_id=proposal.connector_id,
        planned_start=proposal.planned_start,
        planned_end=proposal.planned_end,
        estimated_cost_vnd=proposal.estimated_cost_vnd,
        schedule_version=1,
        created_at=datetime.now(UTC),
    )
    _bookings[resident_id] = booking
    if idempotency_key:
        _by_idempotency_key[idempotency_key] = booking
    return booking


def queue_status(resident_id: str) -> QueueStatus:
    """Bản giả lập không có hàng đợi: luôn còn đầu nối."""
    booking = _bookings.get(resident_id)
    return QueueStatus(booking_id=booking.booking_id if booking else None, queue_length=0)


def explain(resident_id: str) -> list[str]:
    booking = _bookings.get(resident_id)
    if booking is None:
        return ["Bạn chưa có lịch sạc nào."]
    start, end = (t.astimezone(booking.request.deadline.tzinfo) for t in (booking.planned_start, booking.planned_end))
    return [
        f"Lịch {booking.booking_id}: đầu nối {booking.connector_id}, {start:%H:%M}–{end:%H:%M}.",
        f"Sạc đều {booking.max_charge_power_kw:g} kW ngay khi cắm xe (giả lập — chưa có bộ tối ưu T2.2).",
    ]
