"""Pydantic ↔ hàng ORM — chỗ DUY NHẤT ghi cả cột khoá lẫn `payload` (ADR-005).

Quy tắc cho từng cặp hàm:
  - *_to_row: cột khoá lấy từ model; payload = model.model_dump(mode="json").
  - row_to_*: dựng lại bằng Model.model_validate(row.payload) — payload là bản gốc, KHÔNG
    ráp lại từ cột khoá (nếu không thêm field Pydantic sẽ phải sửa mapper).
  - Riêng UserRecord và Notification không có payload: ánh xạ từng cột.
Mỗi cặp có test round-trip ở tests/test_services/test_repository.py (kể cả giữ múi giờ).

Owner: TV3. Task: T1.6.
"""

from datetime import UTC, datetime

from src.db.tables import (
    ApprovalRow,
    BookingRow,
    DecisionLogRow,
    DecisionTraceRow,
    LoadPointRow,
    NotificationRow,
    SchedulePlanRow,
    StationEventRow,
    UserRow,
)
from src.models.api import Notification
from src.models.charging import Booking, SchedulePlan
from src.models.control import Approval, DecisionLogEntry
from src.models.decision_trace import DecisionTraceSummary
from src.models.events import StationEvent
from src.models.identity import UserRecord
from src.models.station import LoadPoint


def user_to_row(record: UserRecord) -> UserRow:
    return UserRow(
        user_id=record.user_id,
        email=record.email.lower(),
        password_hash=record.password_hash,
        role=record.role.value,
        display_name=record.display_name,
        vehicle_model=record.vehicle_model,
        default_soc_target=record.default_soc_target,
        consent=record.consent.model_dump(mode="json"),
        created_at=record.created_at,
        deleted_at=record.deleted_at,
    )


def row_to_user(row: UserRow) -> UserRecord:
    return UserRecord(
        user_id=row.user_id,
        email=row.email,
        password_hash=row.password_hash,
        role=row.role,
        display_name=row.display_name,
        vehicle_model=row.vehicle_model,
        default_soc_target=row.default_soc_target,
        consent=row.consent or {},
        created_at=row.created_at,
        deleted_at=row.deleted_at,
    )


def booking_to_row(booking: Booking) -> BookingRow:
    now = datetime.now(UTC)
    return BookingRow(
        booking_id=booking.booking_id,
        resident_id=booking.resident_id,
        status=booking.status.value,
        mode=booking.request.mode.value,
        vehicle_model=booking.request.vehicle_model,
        connector_id=booking.connector_id,
        arrival_time=booking.request.arrival_time,
        deadline=booking.request.deadline,
        planned_start=booking.planned_start,
        planned_end=booking.planned_end,
        schedule_version=booking.schedule_version,
        created_at=booking.created_at,
        updated_at=now,
        payload=booking.model_dump(mode="json"),
    )


def row_to_booking(row: BookingRow) -> Booking:
    return Booking.model_validate(row.payload)


def plan_to_row(plan: SchedulePlan) -> SchedulePlanRow:
    return SchedulePlanRow(
        version=plan.version,
        strategy=plan.strategy.value,
        created_at=plan.created_at,
        horizon_start=plan.horizon_start,
        step_minutes=plan.step_minutes,
        solve_time_s=plan.solve_time_s,
        payload=plan.model_dump(mode="json"),
    )


def row_to_plan(row: SchedulePlanRow) -> SchedulePlan:
    return SchedulePlan.model_validate(row.payload)


def approval_to_row(approval: Approval) -> ApprovalRow:
    return ApprovalRow(
        approval_id=approval.approval_id,
        kind=approval.kind.value,
        status=approval.status.value,
        requested_from=approval.requested_from,
        command_id=approval.command.command_id,
        booking_id=approval.command.booking_id,
        created_at=approval.created_at,
        expires_at=approval.expires_at,
        decided_at=approval.decided_at,
        decided_by=approval.decided_by,
        payload=approval.model_dump(mode="json"),
    )


def row_to_approval(row: ApprovalRow) -> Approval:
    return Approval.model_validate(row.payload)


def decision_to_row(entry: DecisionLogEntry) -> DecisionLogRow:
    return DecisionLogRow(
        entry_id=entry.entry_id,
        timestamp=entry.timestamp,
        command_id=entry.command.command_id,
        source=entry.command.source.value,
        command_type=entry.command.type.value,
        connector_id=entry.command.connector_id,
        booking_id=entry.command.booking_id,
        guard_passed=None if entry.verdict is None else entry.verdict.passed,
        executed=entry.executed,
        approval_id=entry.approval_id,
        payload=entry.model_dump(mode="json"),
    )


def row_to_decision(row: DecisionLogRow) -> DecisionLogEntry:
    return DecisionLogEntry.model_validate(row.payload)


def notification_to_row(resident_id: str, notification: Notification) -> NotificationRow:
    return NotificationRow(
        notification_id=notification.notification_id,
        resident_id=resident_id,
        kind=notification.kind.value,
        title=notification.title,
        body=notification.body,
        approval_id=notification.approval_id,
        created_at=notification.created_at,
        read_at=notification.created_at if notification.read else None,
    )


def row_to_notification(row: NotificationRow) -> Notification:
    return Notification(
        notification_id=row.notification_id,
        kind=row.kind,
        title=row.title,
        body=row.body,
        created_at=row.created_at,
        read=row.read_at is not None,
        approval_id=row.approval_id,
    )


def event_to_row(event: StationEvent) -> StationEventRow:
    return StationEventRow(
        event_id=event.event_id,
        type=event.type.value,
        occurred_at=event.occurred_at,
        connector_id=event.connector_id,
        booking_id=event.booking_id,
        payload=event.model_dump(mode="json"),
    )


def row_to_event(row: StationEventRow) -> StationEvent:
    return StationEvent.model_validate(row.payload)


def load_point_to_row(point: LoadPoint) -> LoadPointRow:
    return LoadPointRow(ts=point.timestamp, total_power_kw=point.total_power_kw, power_limit_kw=point.power_limit_kw)


def row_to_load_point(row: LoadPointRow) -> LoadPoint:
    return LoadPoint(timestamp=row.ts, total_power_kw=row.total_power_kw, power_limit_kw=row.power_limit_kw)


def trace_to_row(summary: DecisionTraceSummary) -> DecisionTraceRow:
    return DecisionTraceRow(
        correlation_id=summary.correlation_id,
        decided_at=summary.decided_at,
        policy_id=summary.policy_id,
        schedule_version=summary.schedule_version,
        budget_deviation_kw_max=summary.budget_deviation_kw_max,
        hard_violations=summary.hard_violations,
        closed=summary.closed,
        payload=summary.model_dump(mode="json"),
    )


def row_to_trace(row: DecisionTraceRow) -> DecisionTraceSummary:
    return DecisionTraceSummary.model_validate(row.payload)
