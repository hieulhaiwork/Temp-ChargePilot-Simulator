"""Cửa DUY NHẤT của tầng ứng dụng tới dữ liệu bền vững (ADR-005).

Vì sao một module: mọi chỗ ghi/đọc dữ liệu đi qua đây; bên dưới là SQLAlchemy 2 (src/db/),
SQLite ở máy local/CI và Postgres (Neon) khi deploy. Đáp ứng NFR "simulator mất trạng thái:
giữ lịch gần nhất và cảnh báo" — lịch và booking được khôi phục từ đây.

Quy ước (docs/plan/40-database.md §5):
  - Vào và ra đều là model Pydantic của src/models/; KHÔNG lớp ORM nào lọt ra ngoài.
  - Mỗi hàm là một giao dịch ngắn. Việc cần nguyên tử thì gộp vào một hàm.
  - Không tìm thấy → None hoặc danh sách rỗng, không ném lỗi.
  - Truy cập ĐỒNG BỘ. Code async gọi qua asyncio.to_thread để không chặn event loop.
  - decision_log là CHỈ-THÊM (FR14): module này không có hàm sửa/xoá bảng đó.

Chỉ module này (và src/db/**) được import sqlalchemy / src.db — tests/test_architecture.py.

Owner: TV3. Task: T1.6.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from src.config import get_settings
from src.db import mappers
from src.db import session as db_session
from src.db.tables import (
    ApprovalRow,
    BookingRow,
    DecisionLogRow,
    DecisionTraceBookingRow,
    DecisionTraceRow,
    IdempotencyKeyRow,
    LoadPointRow,
    NotificationRow,
    SchedulePlanRow,
    StationEventRow,
    UserRow,
)
from src.models.api import ErrorCode, Notification
from src.models.charging import Booking, BookingStatus, SchedulePlan
from src.models.control import Approval, ApprovalStatus, DecisionLogEntry
from src.models.decision_trace import DecisionTraceSummary
from src.models.events import EventType, StationEvent
from src.models.identity import UserRecord
from src.models.station import LoadPoint
from src.services.errors import DomainError

PLAN_HISTORY_LIMIT = 200  # NFR: giữ 200 phiên bản lịch gần nhất
IDEMPOTENCY_TTL = timedelta(hours=24)  # ADR-008
ACTIVE_STATUSES = (BookingStatus.CONFIRMED, BookingStatus.QUEUED, BookingStatus.CHARGING)

# ---- Vòng đời ---------------------------------------------------------------------------


def init(database_url: str | None = None) -> None:
    """Tạo engine (lười, an toàn khi gọi lại). database_url=None → settings.database_url.

    KHÔNG tạo bảng: schema do Alembic quản lý (`alembic upgrade head`).
    """
    db_session.configure(database_url or get_settings().database_url)


def dispose() -> None:
    """Đóng pool kết nối — gọi lúc tắt app và giữa các test."""
    db_session.dispose()


def ping() -> bool:
    """Kiểm DB trả lời được (GET /ready). Tự init nếu chưa. Lỗi kết nối → raise, không nuốt."""
    _ensure()
    with db_session.session_scope() as session:
        session.execute(text("SELECT 1"))
    return True


def _ensure() -> None:
    if not db_session.is_configured():
        init()


# ---- Tài khoản (FR1, F8) ----------------------------------------------------------------


def get_user_by_email(email: str) -> UserRecord | None:
    _ensure()
    with db_session.session_scope() as s:
        row = s.scalars(select(UserRow).where(UserRow.email == email.strip().lower())).first()
        return mappers.row_to_user(row) if row else None


def get_user(user_id: str) -> UserRecord | None:
    _ensure()
    with db_session.session_scope() as s:
        row = s.get(UserRow, user_id)
        return mappers.row_to_user(row) if row else None


def upsert_user(record: UserRecord) -> None:
    """Tạo mới hoặc cập nhật theo email — dùng cho seed tài khoản demo (idempotent).

    Khi đã có: giữ user_id cũ (khoá ngoại của booking / notification trỏ vào nó).
    """
    _ensure()
    new = mappers.user_to_row(record)
    with db_session.session_scope() as s:
        row = s.scalars(select(UserRow).where(UserRow.email == new.email)).first() or s.get(UserRow, new.user_id)
        if row is None:
            s.add(new)
            return
        for col in (
            "email",
            "password_hash",
            "role",
            "display_name",
            "vehicle_model",
            "default_soc_target",
            "consent",
            "deleted_at",
        ):
            setattr(row, col, getattr(new, col))


def anonymize_user(user_id: str, at: datetime) -> None:
    """NFR riêng tư: email → giá trị vô nghĩa, xoá password_hash, đặt deleted_at. Giữ user_id giả danh."""
    _ensure()
    with db_session.session_scope() as s:
        row = s.get(UserRow, user_id)
        if row is None:
            return
        row.email = f"deleted-{user_id}@invalid"
        row.password_hash = None
        row.display_name = "Tài khoản đã xoá"
        row.vehicle_model = None
        row.default_soc_target = None
        row.deleted_at = at


# ---- Booking (FR2, FR8) -----------------------------------------------------------------


def save_booking(booking: Booking, *, idempotency_key: str | None = None, request_hash: str | None = None) -> None:
    """Ghi (thêm hoặc cập nhật) booking. Có idempotency_key thì ghi khoá CÙNG giao dịch.

    Vi phạm "một booking hiệu lực / cư dân" (index duy nhất, Q6) → DomainError BOOKING_CONFLICT.
    """
    _ensure()
    try:
        with db_session.session_scope() as s:
            s.merge(mappers.booking_to_row(booking))
            s.flush()
            if idempotency_key:
                s.merge(
                    IdempotencyKeyRow(
                        key=idempotency_key,
                        resident_id=booking.resident_id,
                        request_hash=request_hash or "",
                        booking_id=booking.booking_id,
                        created_at=datetime.now(UTC),
                    )
                )
    except IntegrityError as exc:
        raise DomainError(ErrorCode.BOOKING_CONFLICT, "Bạn đang có một lịch sạc hiệu lực khác") from exc


def get_booking(booking_id: str) -> Booking | None:
    _ensure()
    with db_session.session_scope() as s:
        row = s.get(BookingRow, booking_id)
        return mappers.row_to_booking(row) if row else None


def list_bookings(resident_id: str | None = None, statuses: tuple[BookingStatus, ...] | None = None) -> list[Booking]:
    """Sắp theo deadline tăng dần (thứ tự EDF tự nhiên của hàng chờ)."""
    _ensure()
    q = select(BookingRow)
    if resident_id is not None:
        q = q.where(BookingRow.resident_id == resident_id)
    if statuses:
        q = q.where(BookingRow.status.in_([st.value for st in statuses]))
    q = q.order_by(BookingRow.deadline, BookingRow.created_at)
    with db_session.session_scope() as s:
        return [mappers.row_to_booking(r) for r in s.scalars(q)]


def active_booking(resident_id: str) -> Booking | None:
    """Booking đang hiệu lực (confirmed | queued | charging) của cư dân — tối đa một (mặc định Q6)."""
    found = list_bookings(resident_id, ACTIVE_STATUSES)
    return found[0] if found else None


def find_idempotent(key: str, resident_id: str, request_hash: str) -> Booking | None:
    """Booking đã tạo với khoá này. Cùng key khác request_hash → DomainError IDEMPOTENCY_MISMATCH.

    Khoá cũ hơn IDEMPOTENCY_TTL bị xoá và coi như chưa dùng.
    """
    _ensure()
    with db_session.session_scope() as s:
        row = s.get(IdempotencyKeyRow, key)
        if row is None or row.resident_id != resident_id:
            return None
        if row.created_at < datetime.now(UTC) - IDEMPOTENCY_TTL:
            s.delete(row)
            return None
        if row.request_hash != request_hash:
            raise DomainError(ErrorCode.IDEMPOTENCY_MISMATCH, "Idempotency-Key đã dùng cho một yêu cầu khác")
        booking = s.get(BookingRow, row.booking_id)
        return mappers.row_to_booking(booking) if booking else None


# ---- Lịch (NFR khả dụng) ----------------------------------------------------------------


def save_plan(plan: SchedulePlan) -> None:
    """Giữ lịch gần nhất để khôi phục (NFR); cắt còn PLAN_HISTORY_LIMIT bản bằng một câu DELETE duy nhất."""
    _ensure()
    with db_session.session_scope() as s:
        s.merge(mappers.plan_to_row(plan))
        s.flush()
        keep_versions = (
            select(SchedulePlanRow.version).order_by(SchedulePlanRow.version.desc()).limit(PLAN_HISTORY_LIMIT)
        )
        s.execute(delete(SchedulePlanRow).where(SchedulePlanRow.version.not_in(keep_versions)))


def latest_plan() -> SchedulePlan | None:
    _ensure()
    with db_session.session_scope() as s:
        row = s.scalars(select(SchedulePlanRow).order_by(SchedulePlanRow.version.desc()).limit(1)).first()
        return mappers.row_to_plan(row) if row else None


def get_plan(version: int) -> SchedulePlan | None:
    _ensure()
    with db_session.session_scope() as s:
        row = s.get(SchedulePlanRow, version)
        return mappers.row_to_plan(row) if row else None


# ---- Phê duyệt (FR13, AC4) --------------------------------------------------------------


def save_approval(approval: Approval) -> None:
    _ensure()
    with db_session.session_scope() as s:
        s.merge(mappers.approval_to_row(approval))


def get_approval(approval_id: str) -> Approval | None:
    _ensure()
    with db_session.session_scope() as s:
        row = s.get(ApprovalRow, approval_id)
        return mappers.row_to_approval(row) if row else None


def list_approvals(status: ApprovalStatus | None = None, requested_from: str | None = None) -> list[Approval]:
    """Mới nhất trước."""
    _ensure()
    q = select(ApprovalRow)
    if status is not None:
        q = q.where(ApprovalRow.status == status.value)
    if requested_from is not None:
        q = q.where(ApprovalRow.requested_from == requested_from)
    q = q.order_by(ApprovalRow.created_at.desc())
    with db_session.session_scope() as s:
        return [mappers.row_to_approval(r) for r in s.scalars(q)]


def overdue_approvals(now: datetime) -> list[Approval]:
    """PENDING có expires_at ≤ now — guard.approval.expire_overdue đánh dấu EXPIRED (KHÔNG thực thi)."""
    _ensure()
    q = (
        select(ApprovalRow)
        .where(ApprovalRow.status == ApprovalStatus.PENDING.value)
        .where(ApprovalRow.expires_at.is_not(None))
        .where(ApprovalRow.expires_at <= now)
        .order_by(ApprovalRow.expires_at)
    )
    with db_session.session_scope() as s:
        return [mappers.row_to_approval(r) for r in s.scalars(q)]


# ---- Nhật ký quyết định (FR14) — CHỈ THÊM -----------------------------------------------


def append_decision(entry: DecisionLogEntry) -> None:
    """FR14 — append-only, không sửa/xoá bản ghi cũ."""
    _ensure()
    with db_session.session_scope() as s:
        s.add(mappers.decision_to_row(entry))


def list_decisions(
    limit: int = 100, blocked_only: bool = False, before: int | None = None, booking_id: str | None = None
) -> list[DecisionLogEntry]:
    """Mới nhất trước. `before` = con trỏ seq để phân trang; `booking_id` cho charging_service.explain."""
    _ensure()
    q = select(DecisionLogRow)
    if blocked_only:
        q = q.where(DecisionLogRow.guard_passed.is_(False))
    if before is not None:
        q = q.where(DecisionLogRow.seq < before)
    if booking_id is not None:
        q = q.where(DecisionLogRow.booking_id == booking_id)
    q = q.order_by(DecisionLogRow.seq.desc()).limit(limit)
    with db_session.session_scope() as s:
        return [mappers.row_to_decision(r) for r in s.scalars(q)]


# ---- DecisionTrace backend (ADR-019 Phase 4, quyết định 6) ------------------------------


def save_decision_trace(summary: DecisionTraceSummary, full_payload: dict | None = None) -> None:
    """Upsert evidence and its subject index together; a closed trace stays closed on retries."""
    _ensure()
    values = mappers.trace_columns(summary)
    condition = DecisionTraceRow.closed.is_(False)
    if full_payload is None:
        condition &= DecisionTraceRow.full_payload.is_(None)
    else:
        values["full_payload"] = full_payload
    with db_session.session_scope() as s:
        insert = postgres_insert if s.get_bind().dialect.name == "postgresql" else sqlite_insert
        stmt = insert(DecisionTraceRow.__table__).values(**values)
        written = s.execute(
            stmt.on_conflict_do_update(
                index_elements=[DecisionTraceRow.correlation_id],
                set_={key: stmt.excluded[key] for key in values if key != "correlation_id"},
                where=condition,
            ).returning(DecisionTraceRow.correlation_id)
        ).scalar_one_or_none()
        booking_ids = full_payload.get("booking_ids", []) if full_payload else []
        if written and booking_ids:
            s.execute(
                insert(DecisionTraceBookingRow.__table__)
                .values(
                    [
                        {"booking_id": booking_id, "correlation_id": written, "decided_at": summary.decided_at}
                        for booking_id in booking_ids
                    ]
                )
                .on_conflict_do_nothing()
            )


def get_decision_trace(correlation_id: str) -> DecisionTraceSummary | None:
    _ensure()
    with db_session.session_scope() as s:
        row = s.get(DecisionTraceRow, correlation_id)
        return mappers.row_to_trace(row) if row else None


def get_full_decision_trace(correlation_id: str) -> dict | None:
    """Return versioned evidence, or None for missing and historical summary-only records."""
    _ensure()
    with db_session.session_scope() as s:
        return s.scalar(select(DecisionTraceRow.full_payload).where(DecisionTraceRow.correlation_id == correlation_id))


def list_full_decision_traces(
    start: datetime, end: datetime, *, booking_id: str | None = None, closed: bool | None = None, limit: int = 50
) -> list[dict]:
    """Internal lookup over a bounded, half-open interval. Caller handles authorization."""
    if start.utcoffset() is None or end.utcoffset() is None or not timedelta(0) < end - start <= timedelta(days=31):
        raise ValueError("Trace window must be timezone-aware, positive and at most 31 days")
    if not 1 <= limit <= 100:
        raise ValueError("Trace limit must be between 1 and 100")
    _ensure()
    time_column = DecisionTraceRow.decided_at
    q = select(DecisionTraceRow.full_payload).where(DecisionTraceRow.full_payload.is_not(None))
    if booking_id is not None:
        time_column = DecisionTraceBookingRow.decided_at
        q = q.join(DecisionTraceBookingRow, DecisionTraceBookingRow.correlation_id == DecisionTraceRow.correlation_id)
        q = q.where(DecisionTraceBookingRow.booking_id == booking_id)
    if closed is not None:
        q = q.where(DecisionTraceRow.closed.is_(closed))
    q = q.where(time_column >= start, time_column < end)
    with db_session.session_scope() as s:
        return list(s.scalars(q.order_by(time_column.desc(), DecisionTraceRow.correlation_id.desc()).limit(limit)))


def list_decision_traces(limit: int = 100) -> list[DecisionTraceSummary]:
    """Mới nhất trước."""
    _ensure()
    q = select(DecisionTraceRow).order_by(DecisionTraceRow.decided_at.desc()).limit(limit)
    with db_session.session_scope() as s:
        return [mappers.row_to_trace(r) for r in s.scalars(q)]


def list_decision_traces_for_temporal_lookup(
    start: datetime,
    end: datetime,
    *,
    booking_id: str | None = None,
    inclusive_end: bool = False,
    lookback: timedelta = timedelta(days=1),
    limit: int = 100,
) -> dict:
    """Indexed candidate fetch for G1-F06 temporal overlap / as-of resolution (no schema migration).

    Fetches:
      - rows in [start - lookback, end] (or < end) using existing decided_at / (booking_id, decided_at) indexes,
        with limit + 1 to detect truncation accurately;
      - the single latest row strictly before `start - lookback` to cover long-lived traces;
      - counts of legacy summary-only rows (full_payload IS NULL) in the fetched window;
      - station-wide latest trace metadata and the next trace after `end` to detect superseded/stale active traces.
    """
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Trace lookup boundaries must be timezone-aware")
    if end < start or end - start > timedelta(days=31):
        raise ValueError("Trace lookup window must satisfy 0 <= end - start <= 31 days")
    if lookback < timedelta(0):
        raise ValueError("lookback must be non-negative")
    if not 1 <= limit <= 100:
        raise ValueError("Trace limit must be between 1 and 100")

    _ensure()
    fetch_start = start - lookback

    def _base_query():
        if booking_id is not None:
            return (
                select(
                    DecisionTraceRow.correlation_id,
                    DecisionTraceRow.decided_at,
                    DecisionTraceRow.schedule_version,
                    DecisionTraceRow.closed,
                    DecisionTraceRow.full_payload,
                )
                .join(
                    DecisionTraceBookingRow,
                    DecisionTraceBookingRow.correlation_id == DecisionTraceRow.correlation_id,
                )
                .where(DecisionTraceBookingRow.booking_id == booking_id),
                DecisionTraceBookingRow.decided_at,
            )
        return (
            select(
                DecisionTraceRow.correlation_id,
                DecisionTraceRow.decided_at,
                DecisionTraceRow.schedule_version,
                DecisionTraceRow.closed,
                DecisionTraceRow.full_payload,
            ),
            DecisionTraceRow.decided_at,
        )

    with db_session.session_scope() as s:
        q, time_col = _base_query()
        upper = time_col <= end if inclusive_end else time_col < end
        window_q = (
            q.where(time_col >= fetch_start, upper)
            .order_by(time_col.desc(), DecisionTraceRow.schedule_version.desc(), DecisionTraceRow.correlation_id.desc())
            .limit(limit + 1)
        )
        rows = list(s.execute(window_q).all())
        truncated = len(rows) > limit
        if truncated:
            rows = rows[:limit]

        prior_q, prior_col = _base_query()
        prior = s.execute(
            prior_q.where(prior_col < fetch_start)
            .order_by(
                prior_col.desc(), DecisionTraceRow.schedule_version.desc(), DecisionTraceRow.correlation_id.desc()
            )
            .limit(1)
        ).first()

        # Station-wide superseding signals (uses ix_decision_traces_decided)
        after_cond = DecisionTraceRow.decided_at > end if inclusive_end else DecisionTraceRow.decided_at >= end
        next_row = s.execute(
            select(
                DecisionTraceRow.correlation_id,
                DecisionTraceRow.decided_at,
                DecisionTraceRow.schedule_version,
            )
            .where(after_cond)
            .order_by(
                DecisionTraceRow.decided_at.asc(),
                DecisionTraceRow.schedule_version.asc(),
                DecisionTraceRow.correlation_id.asc(),
            )
            .limit(1)
        ).first()
        latest_row = s.execute(
            select(
                DecisionTraceRow.correlation_id,
                DecisionTraceRow.decided_at,
                DecisionTraceRow.schedule_version,
            )
            .order_by(
                DecisionTraceRow.decided_at.desc(),
                DecisionTraceRow.schedule_version.desc(),
                DecisionTraceRow.correlation_id.desc(),
            )
            .limit(1)
        ).first()

    combined = list(rows)
    seen_ids = {r.correlation_id for r in combined}
    if prior is not None and prior.correlation_id not in seen_ids:
        combined.append(prior)

    traces: list[dict] = []
    legacy_summary_only_ids: list[str] = []
    for row in combined:
        if row.full_payload is None:
            legacy_summary_only_ids.append(row.correlation_id)
        else:
            traces.append(row.full_payload)

    return {
        "traces": traces,
        "legacy_summary_only_ids": legacy_summary_only_ids,
        "truncated": truncated,
        "next_trace": (
            {
                "correlation_id": next_row.correlation_id,
                "decided_at": next_row.decided_at,
                "schedule_version": next_row.schedule_version,
            }
            if next_row is not None
            else None
        ),
        "latest_trace": (
            {
                "correlation_id": latest_row.correlation_id,
                "decided_at": latest_row.decided_at,
                "schedule_version": latest_row.schedule_version,
            }
            if latest_row is not None
            else None
        ),
    }


# ---- Thông báo (FR15) -------------------------------------------------------------------


def list_notifications(resident_id: str) -> list[Notification]:
    """Mới nhất trước."""
    _ensure()
    q = (
        select(NotificationRow)
        .where(NotificationRow.resident_id == resident_id)
        .order_by(NotificationRow.created_at.desc())
    )
    with db_session.session_scope() as s:
        return [mappers.row_to_notification(r) for r in s.scalars(q)]


def add_notification(resident_id: str, notification: Notification) -> None:
    _ensure()
    with db_session.session_scope() as s:
        s.merge(mappers.notification_to_row(resident_id, notification))


def mark_notification_read(notification_id: str, resident_id: str) -> Notification | None:
    """Đánh dấu đã đọc; None nếu không có hoặc không thuộc cư dân này (không lộ thông báo người khác)."""
    _ensure()
    with db_session.session_scope() as s:
        row = s.get(NotificationRow, notification_id)
        if row is None or row.resident_id != resident_id:
            return None
        if row.read_at is None:
            row.read_at = datetime.now(UTC)
        return mappers.row_to_notification(row)


# ---- Chuỗi thời gian cho S5 (FR16) ------------------------------------------------------


def append_event(event: StationEvent) -> None:
    _ensure()
    with db_session.session_scope() as s:
        row = mappers.event_to_row(event)
        if event.type != EventType.HARD_LIMIT_VIOLATED:
            s.add(row)
            return
        insert = postgres_insert if s.get_bind().dialect.name == "postgresql" else sqlite_insert
        values = {
            column.key: getattr(row, column.key) for column in StationEventRow.__table__.columns if column.key != "seq"
        }
        s.execute(
            insert(StationEventRow.__table__).values(**values).on_conflict_do_nothing(index_elements=["event_id"])
        )


def list_events(limit: int = 50, before: int | None = None) -> list[StationEvent]:
    """Mới nhất trước; `before` = con trỏ seq."""
    _ensure()
    q = select(StationEventRow)
    if before is not None:
        q = q.where(StationEventRow.seq < before)
    q = q.order_by(StationEventRow.seq.desc()).limit(limit)
    with db_session.session_scope() as s:
        return [mappers.row_to_event(r) for r in s.scalars(q)]


def append_load_point(point: LoadPoint) -> None:
    _ensure()
    with db_session.session_scope() as s:
        s.merge(mappers.load_point_to_row(point))


def list_load_points(since: datetime) -> list[LoadPoint]:
    """Tăng dần theo thời gian."""
    _ensure()
    q = select(LoadPointRow).where(LoadPointRow.ts >= since).order_by(LoadPointRow.ts)
    with db_session.session_scope() as s:
        return [mappers.row_to_load_point(r) for r in s.scalars(q)]
