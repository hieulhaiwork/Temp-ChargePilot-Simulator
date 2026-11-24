"""10 bảng của ChargePilot — cột khoá + `payload` (docs/plan/40-database.md §3).

Quy ước:
  - Cột khoá phục vụ lọc / sắp xếp / ràng buộc. `payload` = model_dump(mode="json") của model
    Pydantic tương ứng và là bản gốc khi đọc lại. Chỉ src/db/mappers.py ghi cả hai.
  - Mọi thời điểm dùng UtcDateTime. Mọi id là chuỗi do tầng ứng dụng sinh (uuid4().hex).
  - Đổi file này → viết revision trong migrations/versions/ (test_migrations.py kiểm).
"""

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.db.types import JsonDoc, UtcDateTime

# Trạng thái booking "đang hiệu lực" — khớp BookingStatus trong src/models/charging.py.
ACTIVE_BOOKING_STATUSES = ("confirmed", "queued", "charging")
_ACTIVE_BOOKING_SQL = text("status IN ('confirmed', 'queued', 'charging')")


class UserRow(Base):
    """FR1, F8 — tài khoản. Bảng DUY NHẤT chứa email; nơi khác chỉ dùng user_id giả danh."""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(80))
    vehicle_model: Mapped[str | None] = mapped_column(String(64))
    default_soc_target: Mapped[float | None] = mapped_column(Float)
    consent: Mapped[dict] = mapped_column(JsonDoc)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class BookingRow(Base):
    """FR2, FR8, US2 — payload = Booking."""

    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_resident_status", "resident_id", "status"),
        Index("ix_bookings_status_deadline", "status", "deadline"),
        # Mặc định Q6: mỗi cư dân tối đa MỘT booking đang hiệu lực — ràng buộc ở tầng DB để hai
        # request đồng thời không lọt. Index duy nhất một phần: Postgres và SQLite đều hỗ trợ.
        Index(
            "uq_bookings_one_active_per_resident",
            "resident_id",
            unique=True,
            postgresql_where=_ACTIVE_BOOKING_SQL,
            sqlite_where=_ACTIVE_BOOKING_SQL,
        ),
    )

    booking_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    resident_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.user_id"))
    status: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16))
    vehicle_model: Mapped[str] = mapped_column(String(64))
    connector_id: Mapped[str | None] = mapped_column(String(8))
    arrival_time: Mapped[datetime | None] = mapped_column(UtcDateTime)
    deadline: Mapped[datetime] = mapped_column(UtcDateTime)
    planned_start: Mapped[datetime | None] = mapped_column(UtcDateTime)
    planned_end: Mapped[datetime | None] = mapped_column(UtcDateTime)
    schedule_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
    payload: Mapped[dict] = mapped_column(JsonDoc)


class IdempotencyKeyRow(Base):
    """ADR-008 — chống tạo hai booking khi bấm "Xác nhận" hai lần. Xoá bản ghi cũ hơn 24 giờ."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    resident_id: Mapped[str] = mapped_column(String(32))
    request_hash: Mapped[str] = mapped_column(String(64))
    booking_id: Mapped[str] = mapped_column(String(32), ForeignKey("bookings.booking_id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class SchedulePlanRow(Base):
    """NFR "giữ lịch gần nhất" — payload = SchedulePlan. Giữ 200 phiên bản gần nhất."""

    __tablename__ = "schedule_plans"

    version: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    strategy: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    horizon_start: Mapped[datetime] = mapped_column(UtcDateTime)
    step_minutes: Mapped[int] = mapped_column(Integer)
    solve_time_s: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JsonDoc)


class ApprovalRow(Base):
    """FR13, AC4 — payload = Approval. Trạng thái phê duyệt phải được LƯU, không chỉ gửi thông báo."""

    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_status_expires", "status", "expires_at"),
        Index("ix_approvals_requested_status", "requested_from", "status"),
    )

    approval_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16))
    requested_from: Mapped[str] = mapped_column(String(32))
    command_id: Mapped[str] = mapped_column(String(32))
    booking_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    decided_by: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JsonDoc)


class DecisionLogRow(Base):
    """FR14 — CHỈ THÊM. payload = DecisionLogEntry. `seq` là thứ tự ghi và con trỏ phân trang."""

    __tablename__ = "decision_log"
    __table_args__ = (
        Index("ix_decision_log_guard_seq", "guard_passed", "seq"),
        Index("ix_decision_log_booking_seq", "booking_id", "seq"),
    )

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(String(32), unique=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)
    command_id: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))
    command_type: Mapped[str] = mapped_column(String(24))
    connector_id: Mapped[str] = mapped_column(String(8))
    booking_id: Mapped[str | None] = mapped_column(String(32))
    guard_passed: Mapped[bool | None] = mapped_column(Boolean)  # None = không có verdict
    executed: Mapped[bool] = mapped_column(Boolean)
    approval_id: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JsonDoc)


class NotificationRow(Base):
    """FR15 — chuông của cư dân."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_resident_created", "resident_id", "created_at"),)

    notification_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    resident_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.user_id"))
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    approval_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    read_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class StationEventRow(Base):
    """S5 "Sự kiện gần nhất" — payload = StationEvent. Giữ 7 ngày."""

    __tablename__ = "station_events"
    __table_args__ = (Index("ix_station_events_occurred", "occurred_at"),)

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(32), unique=True)
    type: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime)
    connector_id: Mapped[str | None] = mapped_column(String(8))
    booking_id: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JsonDoc)


class LoadPointRow(Base):
    """S5 biểu đồ tải (FR16) — một điểm mỗi bước. Giữ 7 ngày (API cho xem tối đa 168 giờ)."""

    __tablename__ = "load_points"

    ts: Mapped[datetime] = mapped_column(UtcDateTime, primary_key=True)
    total_power_kw: Mapped[float] = mapped_column(Float)
    power_limit_kw: Mapped[float] = mapped_column(Float)


class DecisionTraceRow(Base):
    """Backend trace summary and optional versioned evidence; legacy summary rows have no full payload."""

    __tablename__ = "decision_traces"
    __table_args__ = (Index("ix_decision_traces_decided", "decided_at"),)

    correlation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    decided_at: Mapped[datetime] = mapped_column(UtcDateTime)
    policy_id: Mapped[str] = mapped_column(String(16))
    schedule_version: Mapped[int] = mapped_column(Integer)
    budget_deviation_kw_max: Mapped[float] = mapped_column(Float)
    hard_violations: Mapped[int] = mapped_column(Integer)
    closed: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict] = mapped_column(JsonDoc)
    full_payload: Mapped[dict | None] = mapped_column(JsonDoc, nullable=True)


class DecisionTraceBookingRow(Base):
    """Lookup by booking ID and time without indexing the full JSON document."""

    __tablename__ = "decision_trace_bookings"
    __table_args__ = (Index("ix_decision_trace_bookings_window", "booking_id", "decided_at"),)

    booking_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("decision_traces.correlation_id", ondelete="CASCADE"), primary_key=True
    )
    decided_at: Mapped[datetime] = mapped_column(UtcDateTime)
