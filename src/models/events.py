"""Sự kiện của trạm (FR8) và bản tin WebSocket gửi web (FR16).

Vì sao tồn tại: "tính lại ngay khi có sự kiện" cần một danh sách sự kiện CHUNG giữa
simulator (sinh sự kiện), control_loop (tính lại lịch) và WebSocket (đẩy lên S5/S6/S7).
"""

from enum import StrEnum
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, Field

from src.models.api import Notification, ResidentSessionView, StationOverview
from src.models.charging import SchedulePlan
from src.models.control import Approval, DecisionLogEntry


class EventType(StrEnum):
    """FR8 — mọi sự kiện đều kích hoạt tính lại lịch."""

    TICK = "tick"  # bước MPC định kỳ (15 phút)
    VEHICLE_ARRIVED = "vehicle_arrived"
    VEHICLE_DEPARTED = "vehicle_departed"  # xe rút đầu nối
    BOOKING_CREATED = "booking_created"
    BOOKING_CHANGED = "booking_changed"
    BOOKING_CANCELLED = "booking_cancelled"
    CONNECTOR_FAULT = "connector_fault"
    CONNECTOR_RESTORED = "connector_restored"
    POWER_LIMIT_CHANGED = "power_limit_changed"
    # Xe đạt SOC mục tiêu (kernel phát cuối bước vật lý): phiên đổi trạng thái, công suất được giải phóng
    # (ADR-019 Phase 4, quyết định 2). Tách khỏi REPLAN_REQUESTED; gộp với sự kiện cùng thời điểm, một lần tính lại.
    CHARGE_COMPLETED = "charge_completed"
    # vận hành bấm "Lập lịch lại" (S6) / sau phê duyệt / trạm báo công suất thực vượt budget vùng (một lần / quyết định)
    REPLAN_REQUESTED = "replan_requested"
    # Final Review §4.5b (opt-in `guard.after_apply_failsafe`): trạm phát hiện vi phạm trần cứng SAU khi áp (Physical
    # Guard sau thực thi) → control_loop sinh lệnh giảm tải khẩn cấp qua guard/dispatcher.py rồi tính lại.
    HARD_LIMIT_VIOLATED = "hard_limit_violated"


class StationEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    type: EventType
    occurred_at: AwareDatetime
    connector_id: str | None = None
    booking_id: str | None = None
    new_power_limit_kw: float | None = Field(default=None, ge=0)
    detail: str = ""


class WsMessageType(StrEnum):
    STATION_SNAPSHOT = "station_snapshot"  # S5: lưới cột + tải tổng
    EVENT = "event"  # S5: dòng "Sự kiện gần nhất"
    SCHEDULE_CHANGED = "schedule_changed"  # S2 thẻ xe, S6 Gantt
    APPROVAL_REQUEST = "approval_request"  # S4 cư dân, S7 vận hành
    COMMAND_BLOCKED = "command_blocked"  # S7 tab "Bị Guard chặn"
    NOTIFICATION = "notification"  # chuông 🔔 của cư dân
    PONG = "pong"  # trả lời {"type": "ping"} của client — giữ kết nối


class WsMessage(BaseModel):
    """Phong bì chung cho mọi bản tin WebSocket — frontend switch theo `type`."""

    type: WsMessageType
    payload: dict
    sent_at: AwareDatetime


# type → model của `payload` (payload = model_dump(mode="json")). Mọi model ở đây đều đã có
# trên OpenAPI nhờ các endpoint REST, nên frontend dùng lại type sinh tự động
# (frontend/src/lib/ws/types.ts). schedule_changed: operator nhận SchedulePlan, cư dân nhận
# ResidentSessionView của chính mình. Bảng đầy đủ: docs/plan/10-backend.md §8.
WS_PAYLOAD_MODELS: dict[WsMessageType, tuple[type[BaseModel], ...]] = {
    WsMessageType.STATION_SNAPSHOT: (StationOverview,),
    WsMessageType.EVENT: (StationEvent,),
    WsMessageType.SCHEDULE_CHANGED: (SchedulePlan, ResidentSessionView),
    WsMessageType.APPROVAL_REQUEST: (Approval,),
    WsMessageType.COMMAND_BLOCKED: (DecisionLogEntry,),
    WsMessageType.NOTIFICATION: (Notification,),
    WsMessageType.PONG: (),
}
