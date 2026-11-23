"""Admission / feasibility cho quote, booking, đổi yêu cầu — CÙNG Planning Core + Physical Core với thực thi.

Vì sao tồn tại (ADR-019 Phase 3, PHASE0_FINDINGS §3): trước đây quote tính bằng LP backend riêng (bước 15', không DC
taper, không coordinator, gán cổng EDF) nên có thể hứa SLA mà policy thực thi (M3a…) không đạt. Ở đây:

    runtime.fork_runtime(rt)           bản sao sâu của trạm + cùng policy, control_loop, Guard (store trong bộ nhớ)
    fork.upsert_vehicle(xe giả định)   trạm live không đổi
    control_loop.on_minute / fork.step(1) tới deadline của xe   (y hệt vòng benchmark)

rồi đọc thời điểm cắm / bắt đầu / đầy, năng lượng giao trước deadline (cùng quy tắc KPI `outcomes()`), chi phí theo
giá TOU từng phút, vị trí hàng chờ. Khác thực thi thật (ghi trong PHASE3_REPORT): không biết xe chưa đặt lịch, sự cố
tương lai, và phê duyệt HITL của cư dân (lệnh cần duyệt coi như chưa thực thi, như benchmark).
"""

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from src.models.charging import Booking
from src.models.events import EventType, StationEvent
from src.services import control_loop
from src.services.runtime import StationRuntime, fork_runtime, visit_of

EPS_KWH = 1e-9


@dataclass(frozen=True)
class Admission:
    """Kết quả what-if của MỘT xe, đo trên bản fork chạy đúng policy thực thi."""

    policy: str
    connector_id: str | None
    plugged_at: datetime | None
    charge_start: datetime | None
    charge_end: datetime | None
    completed: bool
    delivered_kwh: float
    unmet_kwh: float
    cost_vnd: float | None
    queue_position: int | None
    decisions: int


async def evaluate(rt: StationRuntime, candidate: Booking, *, exclude: str | None = None) -> Admission:
    """Chạy bản fork tới deadline của `candidate`. `exclude` = booking cũ được thay (đổi yêu cầu)."""
    others = [b for b in rt.store.active_bookings() if b.booking_id not in {candidate.booking_id, exclude}]
    frt = fork_runtime(rt, [*others, candidate])
    sim = frt.simulator
    cid = candidate.booking_id
    tz = ZoneInfo(rt.config.timezone)
    events = sim.upsert_vehicle(visit_of(candidate, sim.now))
    kind = EventType.BOOKING_CHANGED if exclude else EventType.BOOKING_CREATED
    events.append(StationEvent(type=kind, occurred_at=sim.now, booking_id=cid))
    deadline = sim.minute_of(candidate.request.deadline)
    connector = plugged = start = end = None
    queue_position = None
    cost = 0.0
    decisions = 0
    first = True
    while sim.minute < deadline:
        if await control_loop.on_minute(frt, events) is not None:
            decisions += 1
        session = sim.queue.sessions.get(cid)
        if first:
            first = False
            waiting = list(sim.queue.waiting[candidate.request.zone])
            queue_position = waiting.index(cid) + 1 if cid in waiting else None
        if session is None or session.state == "DEPARTED":
            break
        if session.connector is not None and connector is None:
            connector, plugged = sim.connector_of(session.connector), sim.now
        at = sim.now
        before = sim.kernel.output_kwh.get(cid, 0.0)
        events = sim.step(1)
        delivered = sim.kernel.output_kwh.get(cid, 0.0) - before
        if delivered > EPS_KWH:
            start = start or at
            end = sim.now
            cost += delivered * rt.tariff.price_at(at.astimezone(tz).time())
        if session.completed_at is not None:
            break
    outcome = next((o for o in sim.outcomes() if o.booking_id == cid), None)
    delivered_kwh = outcome.delivered_kwh_by_deadline if outcome else 0.0
    need = candidate.energy.grid_energy_kwh
    session = sim.queue.sessions.get(cid)
    completed = session is not None and session.completed_at is not None
    return Admission(
        policy=frt.scheduler.name.value,
        connector_id=connector,
        plugged_at=plugged,
        charge_start=start,
        charge_end=end,
        completed=completed,
        delivered_kwh=delivered_kwh,
        unmet_kwh=max(need - delivered_kwh, 0.0),
        cost_vnd=round(cost) if start is not None else None,
        queue_position=queue_position,
        decisions=decisions,
    )


def run_sync(coro):
    """Chạy coroutine từ code đồng bộ — kể cả khi đang ở trong event loop (chạy ở thread riêng)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict = {}

    def target() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 — chuyển lỗi về thread gọi
            box["error"] = exc

    worker = threading.Thread(target=target)
    worker.start()
    worker.join()
    if "error" in box:
        raise box["error"]
    return box["value"]
