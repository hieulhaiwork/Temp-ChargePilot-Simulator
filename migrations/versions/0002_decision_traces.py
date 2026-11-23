"""decision traces (ADR-019 Phase 4, quyết định 6)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Khớp src/db/tables.py::DecisionTraceRow (test_head_matches_metadata kiểm).
    op.create_table(
        "decision_traces",
        sa.Column("correlation_id", sa.String(length=32), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_id", sa.String(length=16), nullable=False),
        sa.Column("schedule_version", sa.Integer(), nullable=False),
        sa.Column("budget_deviation_kw_max", sa.Float(), nullable=False),
        sa.Column("hard_violations", sa.Integer(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.PrimaryKeyConstraint("correlation_id", name=op.f("pk_decision_traces")),
    )
    with op.batch_alter_table("decision_traces", schema=None) as batch_op:
        batch_op.create_index("ix_decision_traces_decided", ["decided_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("decision_traces", schema=None) as batch_op:
        batch_op.drop_index("ix_decision_traces_decided")
    op.drop_table("decision_traces")
