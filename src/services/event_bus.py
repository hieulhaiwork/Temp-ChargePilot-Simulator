"""Event bus in-process — phát StationEvent tới control_loop và WebSocket hub (FR8, FR16).

Bản đầu: asyncio trong cùng process (Render free = 1 instance). Nếu chạy nhiều
instance thì thay phần thân bằng Redis pub/sub — giữ nguyên chữ ký subscribe/publish.

Handler chạy TUẦN TỰ theo thứ tự đăng ký, ngay trong lời gọi publish (ADR-007: đặt lịch xong là có lịch
mới). Handler lỗi được log FAILED và không làm rơi sự kiện của handler khác.

Owner: TV3. Task: T2.6.
"""

import logging
from collections.abc import Awaitable, Callable

from src.models.events import EventType, StationEvent

logger = logging.getLogger(__name__)

Handler = Callable[[StationEvent], Awaitable[None]]

_handlers: list[tuple[EventType | None, Handler]] = []


def subscribe(event_type: EventType | None, handler: Handler) -> None:
    """Đăng ký handler; event_type=None nghĩa là nhận mọi sự kiện (WebSocket hub)."""
    _handlers.append((event_type, handler))


def clear() -> None:
    """Gỡ mọi handler — dùng khi dựng lại runtime và giữa các test."""
    _handlers.clear()


async def publish(event: StationEvent) -> None:
    """Gửi sự kiện tới mọi handler đã đăng ký. Handler lỗi phải được log, không làm rơi sự kiện."""
    for event_type, handler in list(_handlers):
        if event_type is not None and event_type != event.type:
            continue
        try:
            await handler(event)
        except Exception:
            logger.exception("event_bus FAILED handler=%r event=%s", getattr(handler, "__name__", handler), event.type)
