"""initial schema

Revision ID: 0001
Revises: -
Create Date: 2026-11-17 01:30:03.073362
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Sinh bằng --autogenerate từ src/db/tables.py, đã đọc lại bằng tay (ADR-005).
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_from", sa.String(length=32), nullable=False),
        sa.Column("command_id", sa.String(length=32), nullable=False),
        sa.Column("booking_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=32), nullable=True),
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.PrimaryKeyConstraint("approval_id", name=op.f("pk_approvals")),
    )
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.create_index("ix_approvals_requested_status", ["requested_from", "status"], unique=False)
        batch_op.create_index("ix_approvals_status_expires", ["status", "expires_at"], unique=False)

    op.create_table(
        "decision_log",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entry_id", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("command_id", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("command_type", sa.String(length=24), nullable=False),
        sa.Column("connector_id", sa.String(length=8), nullable=False),
        sa.Column("booking_id", sa.String(length=32), nullable=True),
        sa.Column("guard_passed", sa.Boolean(), nullable=True),
        sa.Column("executed", sa.Boolean(), nullable=False),
        sa.Column("approval_id", sa.String(length=32), nullable=True),
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_decision_log")),
        sa.UniqueConstraint("entry_id", name=op.f("uq_decision_log_entry_id")),
    )
    with op.batch_alter_table("decision_log", schema=None) as batch_op:
        batch_op.create_index("ix_decision_log_booking_seq", ["booking_id", "seq"], unique=False)
        batch_op.create_index("ix_decision_log_guard_seq", ["guard_passed", "seq"], unique=False)

    op.create_table(
        "load_points",
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_power_kw", sa.Float(), nullable=False),
        sa.Column("power_limit_kw", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("ts", name=op.f("pk_load_points")),
    )
    op.create_table(
        "schedule_plans",
        sa.Column("version", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("strategy", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("step_minutes", sa.Integer(), nullable=False),
        sa.Column("solve_time_s", sa.Float(), nullable=True),
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.PrimaryKeyConstraint("version", name=op.f("pk_schedule_plans")),
    )
    op.create_table(
        "station_events",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connector_id", sa.String(length=8), nullable=True),
        sa.Column("booking_id", sa.String(length=32), nullable=True),
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_station_events")),
        sa.UniqueConstraint("event_id", name=op.f("uq_station_events_event_id")),
    )
    with op.batch_alter_table("station_events", schema=None) as batch_op:
        batch_op.create_index("ix_station_events_occurred", ["occurred_at"], unique=False)

    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("vehicle_model", sa.String(length=64), nullable=True),
        sa.Column("default_soc_target", sa.Float(), nullable=True),
        sa.Column(
            "consent", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "bookings",
        sa.Column("booking_id", sa.String(length=32), nullable=False),
        sa.Column("resident_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("vehicle_model", sa.String(length=64), nullable=False),
        sa.Column("connector_id", sa.String(length=8), nullable=True),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planned_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schedule_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.ForeignKeyConstraint(["resident_id"], ["users.user_id"], name=op.f("fk_bookings_resident_id_users")),
        sa.PrimaryKeyConstraint("booking_id", name=op.f("pk_bookings")),
    )
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.create_index("ix_bookings_resident_status", ["resident_id", "status"], unique=False)
        batch_op.create_index("ix_bookings_status_deadline", ["status", "deadline"], unique=False)
        batch_op.create_index(
            "uq_bookings_one_active_per_resident",
            ["resident_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('confirmed', 'queued', 'charging')"),
            sqlite_where=sa.text("status IN ('confirmed', 'queued', 'charging')"),
        )

    op.create_table(
        "notifications",
        sa.Column("notification_id", sa.String(length=32), nullable=False),
        sa.Column("resident_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("approval_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["resident_id"], ["users.user_id"], name=op.f("fk_notifications_resident_id_users")),
        sa.PrimaryKeyConstraint("notification_id", name=op.f("pk_notifications")),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index("ix_notifications_resident_created", ["resident_id", "created_at"], unique=False)

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("resident_id", sa.String(length=32), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("booking_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.booking_id"], name=op.f("fk_idempotency_keys_booking_id_bookings")
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_idempotency_keys")),
    )


def downgrade() -> None:
    # Sinh bằng --autogenerate từ src/db/tables.py, đã đọc lại bằng tay (ADR-005).
    op.drop_table("idempotency_keys")
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index("ix_notifications_resident_created")

    op.drop_table("notifications")
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_bookings_one_active_per_resident",
            postgresql_where=sa.text("status IN ('confirmed', 'queued', 'charging')"),
            sqlite_where=sa.text("status IN ('confirmed', 'queued', 'charging')"),
        )
        batch_op.drop_index("ix_bookings_status_deadline")
        batch_op.drop_index("ix_bookings_resident_status")

    op.drop_table("bookings")
    op.drop_table("users")
    with op.batch_alter_table("station_events", schema=None) as batch_op:
        batch_op.drop_index("ix_station_events_occurred")

    op.drop_table("station_events")
    op.drop_table("schedule_plans")
    op.drop_table("load_points")
    with op.batch_alter_table("decision_log", schema=None) as batch_op:
        batch_op.drop_index("ix_decision_log_guard_seq")
        batch_op.drop_index("ix_decision_log_booking_seq")

    op.drop_table("decision_log")
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.drop_index("ix_approvals_status_expires")
        batch_op.drop_index("ix_approvals_requested_status")

    op.drop_table("approvals")
