"""Sổ kết nối WebSocket + phát bản tin theo vai trò / theo cư dân (FR16).

Vì sao nằm ở services (không ở src/api/ws.py): control_loop và guard (qua DispatchSinks.notify)
cần đẩy bản tin mà không được import tầng API. api/ws.py chỉ lo bắt tay + xác thực rồi
đăng ký hàm gửi vào đây.

Quy tắc đối tượng nhận (docs/plan/10-backend.md §8):
  - operator nhận mọi bản tin của trạm;
  - cư dân CHỈ nhận bản tin có user_id của chính mình — không lộ lịch của người khác.

Một process, một sổ (xem ADR-007: container chạy đúng một worker).
Owner: TV3. Task: T3.6.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from src.models.control import Role
from src.models.events import WsMessage

logger = logging.getLogger(__name__)

Send = Callable[[WsMessage], Awaitable[None]]


@dataclass(frozen=True)
class _Connection:
    send: Send
    role: Role
    user_id: str


_connections: dict[str, _Connection] = {}


def register(send: Send, role: Role, user_id: str) -> str:
    """Đăng ký một kết nối đã xác thực; trả connection_id để unregister khi đóng."""
    connection_id = uuid4().hex
    _connections[connection_id] = _Connection(send=send, role=role, user_id=user_id)
    return connection_id


def unregister(connection_id: str) -> None:
    _connections.pop(connection_id, None)


def connection_count() -> int:
    return len(_connections)


async def broadcast(
    message: WsMessage, *, role: Role | None = None, user_id: str | None = None, to_residents: bool = False
) -> None:
    """Gửi tới các kết nối khớp bộ lọc. Kết nối lỗi thì gỡ khỏi sổ, không làm rơi bản tin của người khác.

    role=None và user_id=None → mọi vận hành (bản tin của trạm). user_id → đúng cư dân đó (kèm mọi vận hành
    nếu role=None). Ghi log độ trễ `now − message.sent_at` để đo NFR "WebSocket trễ ≤ 1 s".
    """
    for connection_id, conn in list(_connections.items()):
        if role is not None and conn.role != role:
            continue
        if conn.role == Role.RESIDENT and not to_residents and conn.user_id != user_id:
            continue
        try:
            await conn.send(message)
        except Exception:
            logger.info("Gỡ kết nối WebSocket lỗi %s", connection_id)
            unregister(connection_id)
    lag_ms = (datetime.now(UTC) - message.sent_at).total_seconds() * 1000
    logger.debug("ws %s lag=%.0fms", message.type, lag_ms)
