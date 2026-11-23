"""xoá lịch cũ của chiến lược LP A–D đã bỏ

Revision ID: 0002_drop_lp_strategy_plans
Revises: 0001
Create Date: 2026-11-23

Phase 4 (quyết định 1 của Tech Lead): `StrategyName` không còn A_fcfs / A_edf / B / C / D. `schedule_plans.payload` là
`SchedulePlan` dạng JSON; dòng mang chiến lược cũ không đọc lại được (`row_to_plan` validate enum) và không còn
scheduler nào chạy được nó. Bảng này là bản lưu lịch gần nhất (dữ liệu dẫn xuất, tính lại từ booking ở lần replan kế
tiếp), không phải dữ liệu gốc của cư dân. Schema không đổi — chỉ dọn dữ liệu.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_drop_lp_strategy_plans"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REMOVED_STRATEGIES = ("A_fcfs", "A_edf", "B", "C", "D")


def upgrade() -> None:
    plans = sa.table("schedule_plans", sa.column("strategy", sa.String(8)))
    op.execute(plans.delete().where(plans.c.strategy.in_(REMOVED_STRATEGIES)))


def downgrade() -> None:
    # Dữ liệu dẫn xuất đã xoá không khôi phục được; schema không đổi nên không có gì để hạ.
    pass
