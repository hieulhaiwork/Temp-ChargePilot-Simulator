"""Màn vận hành trạm S5–S7 (FR16), prefix /operator. Mọi lệnh của vận hành vẫn đi qua Guard.

Tên file là operations.py (không phải operator.py) để không trùng module chuẩn `operator`.
Router chỉ gọi src/services/* — KHÔNG import src.guard (ADR-007; tests/test_architecture.py).
Handler đọc là `def` (threadpool); handler ra lệnh / phát sự kiện là `async def`.

Owner: TV3. Task: T2.6, T3.2, T3.6.
"""

from datetime import date

from fastapi import APIRouter, Query

from src.api.deps import OperatorUser
from src.models.api import (
    ApprovalDecisionRequest,
    ConnectorDetail,
    DecisionLogPage,
    ManualAssignRequest,
    StationOverview,
)
from src.models.charging import Booking, BookingStatus, SchedulePlan
from src.models.control import Approval, ApprovalStatus, DecisionLogEntry, Role
from src.models.events import StationEvent
from src.models.station import LoadPoint
from src.services import control_loop, repository, station_service

router = APIRouter(prefix="/operator", tags=["operator"])

# seq lưu ở cột BIGINT/INTEGER 64-bit; con trỏ vượt ngưỡng này làm DB lỗi (500) thay vì 422.
_MAX_SEQ = 2**63 - 1


# ---- S5: dashboard ---------------------------------------------------------------------


@router.get("/station", response_model=StationOverview)
def station(user: OperatorUser) -> StationOverview:
    """S5 — thanh KPI, lưới 8 cột, cảnh báo, phiên có nguy cơ trễ hạn (US5)."""
    return station_service.overview()


@router.get("/load", response_model=list[LoadPoint])
def load(user: OperatorUser, hours: int = Query(default=24, ge=1, le=168)) -> list[LoadPoint]:
    """S5 — biểu đồ tải có vạch giới hạn."""
    return station_service.load_history(hours)


@router.get("/connectors/{connector_id}", response_model=ConnectorDetail)
def connector(connector_id: str, user: OperatorUser) -> ConnectorDetail:
    """S5 — popup chi tiết khi bấm vào một cột sạc."""
    return station_service.connector_detail(connector_id)


@router.get("/events", response_model=list[StationEvent])
def events(user: OperatorUser, limit: int = Query(default=20, ge=1, le=200)) -> list[StationEvent]:
    """S5 — dòng "Sự kiện gần nhất"."""
    return station_service.recent_events(limit)


# ---- S6: hàng đợi & lịch ---------------------------------------------------------------


@router.get("/schedule", response_model=SchedulePlan)
def schedule(
    user: OperatorUser,
    on_date: date | None = Query(default=None, alias="date", description="Bỏ trống = lịch hiện hành"),
) -> SchedulePlan:
    """S6 — Gantt theo đầu nối + hàng chờ."""
    return station_service.current_plan(on_date)


@router.get("/bookings", response_model=list[Booking])
def bookings(
    user: OperatorUser,
    status: list[BookingStatus] | None = Query(default=None),
) -> list[Booking]:
    """S6 — chi tiết các xe trong hàng chờ / đang sạc (SchedulePlan.queue chỉ có booking_id)."""
    return station_service.list_bookings(status)


@router.post("/schedule/replans", response_model=SchedulePlan)
async def replan(user: OperatorUser) -> SchedulePlan:
    """S6 nút "Lập lịch lại"."""
    return await station_service.replan(user.user_id)


@router.post("/bookings/{booking_id}/assignments", response_model=DecisionLogEntry)
async def manual_assign(booking_id: str, body: ManualAssignRequest, user: OperatorUser) -> DecisionLogEntry:
    """S6 nút "Xếp thủ công" — trả nhật ký để thấy Guard cho qua hay chặn."""
    return await station_service.manual_assign(booking_id, body.connector_id, user.user_id)


# ---- S7: duyệt lệnh --------------------------------------------------------------------


@router.get("/approvals", response_model=list[Approval])
def approvals(user: OperatorUser, status: ApprovalStatus | None = ApprovalStatus.PENDING) -> list[Approval]:
    """S7 tab "Chờ duyệt"."""
    return repository.list_approvals(status)


@router.patch("/approvals/{approval_id}", response_model=Approval)
async def decide_approval(approval_id: str, body: ApprovalDecisionRequest, user: OperatorUser) -> Approval:
    """S7 nút Duyệt / Từ chối."""
    return await control_loop.resolve_approval(approval_id, body.decision, user.user_id, actor_role=Role.OPERATOR)


@router.get("/commands/blocked", response_model=DecisionLogPage)
def blocked_commands(
    user: OperatorUser,
    limit: int = Query(default=100, ge=1, le=1000),
    before: int | None = Query(default=None, ge=1, le=_MAX_SEQ, description="Con trỏ phân trang (seq)"),
) -> DecisionLogPage:
    """S7 tab "Bị Guard chặn" — kèm luật vi phạm (AC6)."""
    return station_service.decision_page(limit, blocked_only=True, before=before)


@router.get("/decision-log", response_model=DecisionLogPage)
def decision_log(
    user: OperatorUser,
    limit: int = Query(default=100, ge=1, le=1000),
    before: int | None = Query(default=None, ge=1, le=_MAX_SEQ, description="Con trỏ phân trang (seq)"),
) -> DecisionLogPage:
    """FR14 — ai đề xuất, Guard kết luận gì, ai duyệt, lúc nào."""
    return station_service.decision_page(limit, before=before)
