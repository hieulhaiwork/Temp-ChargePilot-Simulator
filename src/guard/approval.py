"""Phê duyệt lệnh nhạy cảm (FR13, AC4) — chỉ áp cho lệnh ĐÃ QUA Guard.

Hai loại (FR13 — cơ chế đang chờ BTC xác nhận, nên gom logic phân loại vào MỘT hàm
requires_approval để đổi dễ):
  - Điều chỉnh tối ưu VƯỢT booking.consent → RESIDENT_CONSENT: thông báo S4, có nút
    Đồng ý / Từ chối; chỉ thực thi SAU khi được chấp thuận.
  - Bảo vệ khẩn cấp (source=EMERGENCY) → None: thực thi ngay, báo sau (emergency.py).
  - Đề xuất của Agent → OPERATOR_REVIEW (màn S7). Lệnh vận hành tự xếp tay (source=OPERATOR) là
    quyết định của chính vận hành nên không hỏi lại vận hành; vẫn hỏi cư dân nếu vượt consent.

Hết hạn (expires_at) = EXPIRED = KHÔNG thực thi (AC4). Lưu ý: wireframe S4 có
"Tự áp dụng sau: 04:12" — MÂU THUẪN với AC4; mặc định làm theo PRD (xem
PROJECT_CONTEXT.md §0.2).

Module THUẦN: không đọc/ghi DB. Việc lưu do dispatcher (DispatchSinks.save_approval) và
services.control_loop đảm nhận.

Owner: TV3. Task: T3.2.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Literal

from src.models.api import ErrorCode
from src.models.charging import Booking
from src.models.control import (
    Approval,
    ApprovalKind,
    ApprovalStatus,
    Command,
    CommandSource,
    CommandType,
    GuardVerdict,
    Role,
)
from src.services.errors import DomainError

OPERATOR_INBOX = "operator"  # requested_from của OPERATOR_REVIEW
TOL_KW = 1e-6


def start_delay_minutes(cmd: Command, booking: Booking) -> float:
    """Lệnh bắt đầu sạc muộn hơn planned_start đã hứa bao nhiêu phút (0 nếu không muộn / không có mốc)."""
    if cmd.type not in (CommandType.START, CommandType.ASSIGN_CONNECTOR) or booking.planned_start is None:
        return 0.0
    return max((cmd.created_at - booking.planned_start).total_seconds() / 60, 0.0)


def requires_approval(cmd: Command, booking: Booking | None) -> ApprovalKind | None:
    """Phân loại lệnh đã qua Guard: cần ai duyệt, hay thực thi ngay (None)."""
    if cmd.source == CommandSource.EMERGENCY:
        return None  # FR13 dòng 2: cư dân đã đồng ý trước, báo sau
    if cmd.source == CommandSource.AGENT:
        return ApprovalKind.OPERATOR_REVIEW
    if booking is None:
        return None
    consent = booking.consent
    reduces = (cmd.type == CommandType.STOP) or (
        cmd.type == CommandType.SET_POWER
        and cmd.power_kw is not None
        and cmd.power_kw + TOL_KW < booking.max_charge_power_kw
    )
    if reduces and not consent.allow_power_reduction:
        return ApprovalKind.RESIDENT_CONSENT
    if start_delay_minutes(cmd, booking) > consent.max_start_delay_minutes:
        return ApprovalKind.RESIDENT_CONSENT
    return None


def open_approval(
    cmd: Command,
    verdict: GuardVerdict,
    kind: ApprovalKind,
    *,
    booking: Booking | None = None,
    ttl_minutes: int = 15,
    current_power_kw: float | None = None,
) -> Approval:
    """Tạo Approval PENDING (chưa lưu) — dispatcher lưu qua sinks.save_approval và đẩy APPROVAL_REQUEST."""
    if kind == ApprovalKind.RESIDENT_CONSENT and booking is None:
        raise ValueError("RESIDENT_CONSENT cần booking để biết hỏi cư dân nào")
    requested_from = booking.resident_id if kind == ApprovalKind.RESIDENT_CONSENT else OPERATOR_INBOX
    if booking is not None and booking.planned_end is not None:
        tz = booking.request.deadline.tzinfo
        impact = f"Cam kết {booking.request.soc_target:g}% trước {booking.request.deadline.astimezone(tz):%H:%M}"
    else:
        impact = "Không ảnh hưởng cam kết đã biết"
    reason = f" — {cmd.reason}" if cmd.reason else ""
    return Approval(
        kind=kind,
        command=cmd,
        verdict=verdict,
        requested_from=requested_from,
        impact_summary=f"{impact}{reason}",
        created_at=cmd.created_at,
        expires_at=cmd.created_at + timedelta(minutes=ttl_minutes),
        # G7: khung áp dụng = từ lúc lệnh được đề xuất tới khi cam kết của booking kết thúc; công suất hiện tại để so.
        current_power_kw=current_power_kw,
        effective_from=cmd.created_at,
        effective_until=booking.planned_end if booking is not None else None,
    )


def decide(
    approval: Approval,
    decision: Literal["approve", "reject"],
    actor_id: str,
    actor_role: Role,
    now: datetime,
) -> Approval:
    """Ghi quyết định (chưa lưu, chưa thực thi). Kiểm actor đúng là người được hỏi.

    APPROVED → services.control_loop gọi dispatcher.execute_approved (kiểm Guard lần 2).
    """
    if approval.status != ApprovalStatus.PENDING:
        raise DomainError(ErrorCode.APPROVAL_ALREADY_DECIDED, f"Yêu cầu này đã ở trạng thái {approval.status.value}")
    if approval.expires_at is not None and now >= approval.expires_at:
        raise DomainError(ErrorCode.APPROVAL_ALREADY_DECIDED, "Yêu cầu đã hết hạn — không thực thi (AC4)")
    allowed = (
        actor_role == Role.OPERATOR
        if approval.requested_from == OPERATOR_INBOX
        else (actor_role == Role.RESIDENT and actor_id == approval.requested_from)
    )
    if not allowed:
        raise DomainError(ErrorCode.FORBIDDEN, "Bạn không phải người được hỏi cho yêu cầu này")
    status = ApprovalStatus.APPROVED if decision == "approve" else ApprovalStatus.REJECTED
    return approval.model_copy(update={"status": status, "decided_at": now, "decided_by": actor_id})


def expire_overdue(pending: Iterable[Approval], now: datetime) -> list[Approval]:
    """Đánh dấu EXPIRED các yêu cầu quá hạn (danh sách lấy từ repository.overdue_approvals) — KHÔNG thực thi."""
    return [
        a.model_copy(update={"status": ApprovalStatus.EXPIRED, "decided_at": now})
        for a in pending
        if a.status == ApprovalStatus.PENDING and a.expires_at is not None and a.expires_at <= now
    ]
