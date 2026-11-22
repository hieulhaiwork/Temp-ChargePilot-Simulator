"""WebSocket realtime (FR16: trễ ≤ 1 s) — phong bì bản tin: src/models/events.py:WsMessage.

    /api/v1/ws/operator  → S5 lưới cột + tải, S6 Gantt, S7 hàng chờ duyệt / lệnh bị chặn
    /api/v1/ws/resident  → S2 thẻ xe, S4 yêu cầu phê duyệt, thông báo giảm công suất

Giao thức (ADR-006; docs/plan/10-backend.md §8):
  1. Server accept. Trong 5 giây client gửi {"type": "auth", "token": "<JWT>"}.
     KHÔNG nhận token qua `?token=`: uvicorn ghi query string vào access log.
  2. Server kiểm token (services.auth.decode_token) và vai trò khớp đường dẫn, rồi gửi NGAY một
     bản tin trạng thái đầy đủ (operator: station_snapshot; resident: schedule_changed của mình).
  3. Sau đó chỉ gửi thay đổi, qua services.realtime.register / broadcast. Không phát lại bản tin
     đã lỡ: client nối lại sẽ nhận snapshot mới.
  4. Client gửi {"type": "ping"} mỗi 25 giây, server trả {"type": "pong"}.

Mã đóng: 4401 chưa xác thực / quá 5 giây · 4403 sai vai trò.
Owner: TV3 (server) + TV4 (client). Task: T3.6.
"""

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.models.control import Role
from src.models.events import WsMessage, WsMessageType
from src.services import auth as auth_service
from src.services import charging_service, realtime, station_service
from src.services.errors import DomainError

router = APIRouter(tags=["realtime"])

AUTH_TIMEOUT_SECONDS = 5
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403


async def _authenticate(websocket: WebSocket, role: Role):
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        message = json.loads(first)
        if message.get("type") != "auth" or not isinstance(message.get("token"), str):
            raise ValueError("bản tin đầu phải là auth")
        user = await asyncio.to_thread(auth_service.decode_token, message["token"])
    except (TimeoutError, ValueError, DomainError, WebSocketDisconnect):
        await websocket.close(code=CLOSE_UNAUTHENTICATED, reason="Chưa xác thực")
        return None
    if user.role != role:
        await websocket.close(code=CLOSE_FORBIDDEN, reason=f"Cần vai trò {role.value}")
        return None
    return user


async def _serve(websocket: WebSocket, role: Role, snapshot) -> None:
    user = await _authenticate(websocket, role)
    if user is None:
        return

    async def send(msg: WsMessage) -> None:
        await websocket.send_text(msg.model_dump_json())

    await send(await asyncio.to_thread(snapshot, user))
    connection_id = realtime.register(send, role, user.user_id)
    try:
        while True:
            text = await websocket.receive_text()
            try:
                kind = json.loads(text).get("type")
            except (ValueError, AttributeError):
                continue
            if kind == "ping":
                await send(WsMessage(type=WsMessageType.PONG, payload={}, sent_at=datetime.now(UTC)))
    except WebSocketDisconnect:
        pass
    finally:
        realtime.unregister(connection_id)


def _operator_snapshot(user) -> WsMessage:
    overview = station_service.overview()
    return WsMessage(
        type=WsMessageType.STATION_SNAPSHOT, payload=overview.model_dump(mode="json"), sent_at=datetime.now(UTC)
    )


def _resident_snapshot(user) -> WsMessage:
    view = charging_service.session_view(user.user_id)
    return WsMessage(
        type=WsMessageType.SCHEDULE_CHANGED, payload=view.model_dump(mode="json"), sent_at=datetime.now(UTC)
    )


@router.websocket("/ws/operator")
async def operator_stream(websocket: WebSocket) -> None:
    await _serve(websocket, Role.OPERATOR, _operator_snapshot)


@router.websocket("/ws/resident")
async def resident_stream(websocket: WebSocket) -> None:
    await _serve(websocket, Role.RESIDENT, _resident_snapshot)
