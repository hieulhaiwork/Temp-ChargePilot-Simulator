"""Admission ↔ policy thực thi (ADR-019 Phase 3, PHASE3_DESIGN §6).

Quote / booking chạy CÙNG policy, control_loop, Guard và kernel trên bản fork của trạm. Khi không có gì mới xảy ra,
booking được chấp nhận phải được thực thi đúng như quote đã hứa (cùng cổng, cùng lúc cắm / bắt đầu / kết thúc, cùng
năng lượng giao trước deadline) — tức quote không mâu thuẫn với ràng buộc của policy thực thi.
"""

from datetime import datetime

import pytest

pytest.importorskip("ev2gym")

from src.models.charging import StrategyName  # noqa: E402
from src.models.events import EventType, StationEvent  # noqa: E402
from src.services import admission, catalog, control_loop  # noqa: E402
from src.services.runtime import build_sim_runtime, visit_of  # noqa: E402
from tests.factories import VN, booking  # noqa: E402


async def _runtime(strategy=StrategyName.SIM_M3A):
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=VN)
    rt = build_sim_runtime(scenario, strategy, config, tariff, start)
    for b in (
        booking("dc-a", zone="DC", kwh=35, hours=1.5, now=rt.clock()),
        booking("dc-b", zone="DC", kwh=30, hours=2, now=rt.clock()),
        booking("ac-a", zone="AC", kwh=20, hours=8, now=rt.clock()),
    ):
        rt.store.save_booking(b)
        rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)
    return rt


async def _execute(rt, candidate) -> dict:
    """Chấp nhận booking trên runtime thật rồi chạy vòng điều khiển tới deadline của nó (như benchmark)."""
    rt.store.save_booking(candidate)
    sim = rt.simulator
    events = sim.upsert_vehicle(visit_of(candidate, sim.now))
    events.append(StationEvent(type=EventType.BOOKING_CREATED, occurred_at=sim.now, booking_id=candidate.booking_id))
    deadline = sim.minute_of(candidate.request.deadline)
    cid, seen = candidate.booking_id, {"connector": None, "plugged": None, "start": None, "end": None}
    while sim.minute < deadline:
        await control_loop.on_minute(rt, events)
        session = sim.queue.sessions[cid]
        if session.state == "DEPARTED":
            break
        if session.connector and seen["connector"] is None:
            seen["connector"], seen["plugged"] = sim.connector_of(session.connector), sim.now
        at, before = sim.now, sim.kernel.output_kwh.get(cid, 0.0)
        events = sim.step(1)
        if sim.kernel.output_kwh.get(cid, 0.0) - before > 1e-9:
            seen["start"] = seen["start"] or at
            seen["end"] = sim.now
        if session.completed_at is not None:
            break
    seen["delivered"] = next(o for o in sim.outcomes() if o.booking_id == cid).delivered_kwh_by_deadline
    return seen


@pytest.mark.parametrize(
    "zone,kwh,hours",
    [("DC", 25, 2), ("AC", 15, 6), ("DC", 80, 1)],  # vào hàng chờ DC · AC qua đêm · bất khả thi (thiếu điện)
)
async def test_accepted_booking_is_executed_exactly_as_quoted(zone, kwh, hours):
    rt = await _runtime()
    candidate = booking("cand", zone=zone, kwh=kwh, hours=hours, now=rt.clock())
    before = rt.simulator.state()
    quoted = await admission.evaluate(rt, candidate)
    assert rt.simulator.state() == before and "cand" not in rt.simulator.queue.sessions  # không mutate trạm live
    assert quoted.policy == "M3a" and quoted.decisions >= 1
    real = await _execute(rt, candidate)
    assert real["connector"] == quoted.connector_id
    assert real["plugged"] == quoted.plugged_at
    assert real["start"] == quoted.charge_start and real["end"] == quoted.charge_end
    assert real["delivered"] == pytest.approx(quoted.delivered_kwh, abs=1e-9)
    if kwh == 80:
        assert quoted.unmet_kwh > 0.05  # quote báo thiếu, không hứa SLA mà policy không đạt
    else:
        assert quoted.unmet_kwh <= 0.05


async def test_quote_queue_position_comes_from_the_execution_policy():
    rt = await _runtime()
    first = booking("dc-c", zone="DC", kwh=20, hours=3, now=rt.clock())
    quoted = await admission.evaluate(rt, first)
    assert quoted.queue_position == 1  # 2 cổng DC đã bận ⇒ chờ, vị trí do dispatch của policy (LLF) quyết
    assert quoted.connector_id is not None and quoted.plugged_at > rt.clock()
