"""Một thread DUY NHẤT cho mọi lần giải LP (scheduler.plan, quote what-if).

Vì sao tồn tại (lỗi đã tái hiện 2026-11-22, Windows + scipy 1.18 HiGHS): gọi linprog(method="highs") lần lượt từ
NHIỀU thread khác nhau (asyncio.to_thread / threadpool của FastAPI) làm process crash native (segfault) sau vài chục
lần giải; cùng khối lượng chạy trên một thread cố định thì không lỗi. Gom mọi lần giải về một worker thread vừa tránh
lỗi đó vừa giữ event loop không bị chặn (MT5, WebSocket).
"""

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")

_thread_ident: int | None = None


def _mark() -> None:
    global _thread_ident
    _thread_ident = threading.get_ident()


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lp-solver", initializer=_mark)


def run(fn: Callable[..., T], *args) -> T:  # noqa: UP047
    """Chạy đồng bộ trên thread solver (gọi từ code sync, vd router threadpool)."""
    if threading.get_ident() == _thread_ident:
        return fn(*args)  # đã ở thread solver — tránh tự chờ chính mình
    return _executor.submit(fn, *args).result()


async def run_async(fn: Callable[..., T], *args) -> T:  # noqa: UP047
    """Chạy trên thread solver mà không chặn event loop."""
    return await asyncio.get_running_loop().run_in_executor(_executor, fn, *args)
