"""Màn cư dân S2–S4 (FR15). Chat với Agent nằm ở routes.py (/chat, /chat/sessions/{session_id}).

Form đặt lịch (/quotes, /bookings) là đường dự phòng khi LLM lỗi (NFR khả dụng) và đi
CÙNG charging_service với tool của Agent.

Quy ước (ADR-006, ADR-007):
  - `resident_id` luôn là `user.user_id` lấy từ token — không nhận từ body/query.
  - Router chỉ gọi src/services/*; KHÔNG import src.guard (tests/test_architecture.py).
  - Handler gọi service đồng bộ là `def` (FastAPI chạy trong threadpool, không chặn event loop);
    handler gọi service phát sự kiện là `async def`.

Owner: TV3. Task: T2.2, T2.5, T2.8, T3.2.
"""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Response, status

from src.api.deps import ResidentUser
from src.api.paths import API_PREFIX
from src.models.api import (
    ApprovalDecisionRequest,
    BookingChangeRequest,
    Notification,
    NotificationUpdateRequest,
    ProfileUpdateRequest,
    QueueStatus,
    ResidentProfile,
    ResidentSessionView,
)
from src.models.charging import Booking, ChargeRequest, ScheduleProposal
from src.models.control import Approval, ApprovalStatus, Role
from src.models.station import ResidentSiteMap
from src.services import auth as auth_service
from src.services import charging_service, control_loop, repository, station_service

router = APIRouter(prefix="/resident", tags=["resident"])


IdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=8, max_length=80, description="UUID do client sinh — ADR-008"),
]


# ---- S3: phương án + đặt lịch (form) ---------------------------------------------------


@router.post("/quotes", response_model=ScheduleProposal)
def quote(body: ChargeRequest, user: ResidentUser) -> ScheduleProposal:
    """S3 — phương án what-if (chưa giữ chỗ); không khả thi thì có phương án thay thế (FR4)."""
    return charging_service.quote(body, user.user_id)


@router.post("/bookings", response_model=Booking, status_code=201)
async def create_booking(
    body: ChargeRequest, user: ResidentUser, response: Response, idempotency_key: IdempotencyKey = None
) -> Booking:
    """S3 nút "Xác nhận" (luồng form). Luồng chat chốt qua PATCH /chat/sessions/{session_id}.

    Gửi lại cùng `Idempotency-Key` + cùng body sẽ nhận lại đúng booking cũ (bấm hai lần không tạo hai lịch).
    """
    booking = await charging_service.book(body, user.user_id, idempotency_key=idempotency_key)
    response.headers["Location"] = f"{API_PREFIX}/resident/bookings/{booking.booking_id}"
    return booking


@router.get("/bookings/current", response_model=Booking | None)
def current_booking(user: ResidentUser) -> Booking | None:
    """S2 — thẻ xe: đầu nối + khung giờ hiện tại."""
    return charging_service.current_booking(user.user_id)


@router.patch("/bookings/{booking_id}", response_model=Booking)
async def change_booking(booking_id: str, body: BookingChangeRequest, user: ResidentUser) -> Booking:
    """FR8 — cư dân đổi yêu cầu (mức pin / giờ nhận xe); hệ thống tính lại ngay."""
    return await charging_service.change(booking_id, body, user.user_id)


@router.post("/bookings/{booking_id}/quotes", response_model=ScheduleProposal)
def quote_change(booking_id: str, body: BookingChangeRequest, user: ResidentUser) -> ScheduleProposal:
    """G2 — xem trước lịch sau khi đổi yêu cầu; KHÔNG giữ chỗ, KHÔNG đổi booking."""
    return charging_service.quote_change(booking_id, body, user.user_id)


@router.delete("/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_booking(booking_id: str, user: ResidentUser) -> Response:
    await charging_service.cancel(booking_id, user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- S2: trạng thái của tôi ------------------------------------------------------------


@router.get("/session", response_model=ResidentSessionView)
def session(user: ResidentUser) -> ResidentSessionView:
    """S2 — lịch + tiến độ sạc + % pin ước tính của chính cư dân (FR15)."""
    return charging_service.session_view(user.user_id)


@router.get("/queue", response_model=QueueStatus)
def queue(user: ResidentUser) -> QueueStatus:
    """US2 / AC2 — vị trí hàng đợi + thời gian chờ dự kiến."""
    return charging_service.queue_status(user.user_id)


@router.get("/explanation", response_model=list[str])
def explanation(user: ResidentUser) -> list[str]:
    """US3 — "Vì sao?" ở S3: lý do lấy từ nhật ký quyết định, KHÔNG cần LLM."""
    return charging_service.explain(user.user_id)


@router.get("/notifications", response_model=list[Notification])
def notifications(user: ResidentUser) -> list[Notification]:
    """Chuông 🔔 ở S2 — yêu cầu phê duyệt, đổi lịch, giảm công suất khẩn cấp."""
    return repository.list_notifications(user.user_id)


@router.patch("/notifications/{notification_id}", response_model=Notification)
def mark_notification_read(notification_id: str, body: NotificationUpdateRequest, user: ResidentUser) -> Notification:
    notification = repository.mark_notification_read(notification_id, user.user_id)
    if notification is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có thông báo này")
    return notification


@router.patch("/notifications")
def mark_all_notifications_read(body: NotificationUpdateRequest, user: ResidentUser) -> dict[str, int]:
    """G18 — đánh dấu tất cả thông báo của chính cư dân là đã đọc."""
    return {"updated": repository.mark_all_notifications_read(user.user_id)}


@router.get("/site-map", response_model=ResidentSiteMap)
def site_map(user: ResidentUser) -> ResidentSiteMap:
    """G24 — chỉ public_status / mine / vị trí hàng của chính cư dân; không lộ SOC, mẫu xe, giờ rời."""
    return station_service.resident_site_map(user.user_id)


# ---- S4: phê duyệt điều chỉnh (AC4) ----------------------------------------------------


@router.get("/approvals", response_model=list[Approval])
def list_approvals(
    user: ResidentUser,
    status: ApprovalStatus | None = Query(default=ApprovalStatus.PENDING),
) -> list[Approval]:
    """G17 — đề nghị gửi cho chính cư dân, lọc theo trạng thái (mặc định pending)."""
    return repository.list_approvals(status=status, requested_from=user.user_id)


@router.get("/approvals/{approval_id}", response_model=Approval)
def get_approval(approval_id: str, user: ResidentUser) -> Approval:
    """S4 — chi tiết đề nghị điều chỉnh. Cư dân chỉ xem được đề nghị gửi cho chính mình."""
    approval = repository.get_approval(approval_id)
    if approval is None or approval.requested_from != user.user_id:
        # Cùng một câu trả lời cho "không có" và "không phải của bạn" — không lộ approval của người khác.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có yêu cầu phê duyệt này")
    return approval


@router.patch("/approvals/{approval_id}", response_model=Approval)
async def decide_approval(approval_id: str, body: ApprovalDecisionRequest, user: ResidentUser) -> Approval:
    """S4 — Đồng ý / Từ chối điều chỉnh vượt phạm vi đã đồng ý (AC4)."""
    return await control_loop.resolve_approval(approval_id, body.decision, user.user_id, actor_role=Role.RESIDENT)


# ---- Hồ sơ (F8, NFR riêng tư) ----------------------------------------------------------


@router.get("/profile", response_model=ResidentProfile)
def get_profile(user: ResidentUser) -> ResidentProfile:
    return auth_service.get_profile(user.user_id)


@router.put("/profile", response_model=ResidentProfile)
def update_profile(body: ProfileUpdateRequest, user: ResidentUser) -> ResidentProfile:
    return auth_service.update_profile(user.user_id, body)


@router.delete("/profile", status_code=204)
def delete_profile(user: ResidentUser) -> Response:
    """NFR "cho phép xoá thông tin": ẩn danh hoá tài khoản, huỷ booking đang hiệu lực."""
    auth_service.delete_account(user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
