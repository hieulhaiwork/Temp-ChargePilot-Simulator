"""xoá lịch cũ của chiến lược LP A–D đã bỏ

Revision ID: 0003
Revises: 0002 (decision_traces; nối thành một head khi gộp Phase 4)
Create Date: 2026-11-23

Phase 4 (quyết định 1 của Tech Lead): `StrategyName` không còn A_fcfs / A_edf / B / C / D. `schedule_plans.payload` là
`SchedulePlan` dạng JSON; dòng mang chiến lược cũ không đọc lại được (`row_to_plan` validate enum) và không còn
scheduler nào chạy được nó. Bảng này là bản lưu lịch gần nhất (dữ liệu dẫn xuất, tính lại từ booking ở lần replan kế
tiếp), không phải dữ liệu gốc của cư dân: không bảng nào có khoá ngoại tới `schedule_plans`, và repository tự xoá
lịch cũ, chỉ giữ `PLAN_HISTORY_LIMIT` bản gần nhất. Booking, cư dân, approval, guard log, sự kiện không bị đụng.
Schema không đổi — chỉ dọn dữ liệu.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REMOVED_STRATEGIES = ("A_fcfs", "A_edf", "B", "C", "D")


def upgrade() -> None:
    plans = sa.table("schedule_plans", sa.column("strategy", sa.String(8)))
    op.execute(plans.delete().where(plans.c.strategy.in_(REMOVED_STRATEGIES)))


def downgrade() -> None:
    # Dữ liệu dẫn xuất đã xoá không khôi phục được; schema không đổi nên không có gì để hạ.
    pass
