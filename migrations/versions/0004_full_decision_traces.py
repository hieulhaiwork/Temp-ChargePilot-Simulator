"""Versioned backend DecisionTrace evidence and booking lookup.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decision_traces", sa.Column("full_payload", sa.JSON().with_variant(JSONB(), "postgresql")))
    op.create_table(
        "decision_trace_bookings",
        sa.Column("booking_id", sa.String(32), nullable=False),
        sa.Column("correlation_id", sa.String(32), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("booking_id", "correlation_id"),
        sa.ForeignKeyConstraint(["correlation_id"], ["decision_traces.correlation_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_decision_trace_bookings_window", "decision_trace_bookings", ["booking_id", "decided_at"])


def downgrade() -> None:
    op.drop_table("decision_trace_bookings")
    with op.batch_alter_table("decision_traces") as batch_op:
        batch_op.drop_column("full_payload")
