"""Probe fail-safe readback while a no-op fork owns the shared native solver worker."""

import asyncio
import threading
from datetime import timedelta
from unittest.mock import patch

from src.models.charging import StrategyName
from src.models.events import EventType, StationEvent
from src.services import control_loop
from src.services.copilot import capture_atomic_snapshot, run_sandbox_branch
from src.services.hybrid_planner import SimulatorScheduler
from src.services.runtime import visit_of
from tests.factories import booking
from tests.test_services.test_counterfactual_foundation import _sim_runtime


async def main():
    live = _sim_runtime(StrategyName.SIM_B0)
    booked = booking("load-dc", zone="DC", kwh=20, hours=2.0, now=live.clock())
    live.store.save_booking(booked)
    live.simulator.upsert_vehicle(visit_of(booked, live.clock()))
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=live.clock()), live)
    assert live.simulator.kernel.setpoints[booked.booking_id] > 0
    snapshot = await capture_atomic_snapshot(live, horizon_minutes=20)

    entered = threading.Event()
    release = threading.Event()
    original_plan = SimulatorScheduler.plan

    def plan(scheduler, context):
        if scheduler is not live.scheduler and not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original_plan(scheduler, context)

    with patch.object(SimulatorScheduler, "plan", plan):
        branch = asyncio.create_task(run_sandbox_branch(snapshot, timeout_s=10))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            hard = StationEvent(
                type=EventType.HARD_LIMIT_VIOLATED,
                occurred_at=live.clock(),
                violation_kinds=["charging_model"],
                violation_booking_ids=[booked.booking_id],
            )
            decision = asyncio.create_task(control_loop.on_event(hard, live))
            async with asyncio.timeout(3):
                while booked.booking_id not in live.safety_hold_booking_ids or live.has_pending_safety():
                    await asyncio.sleep(0)
            assert live.simulator.kernel.setpoints.get(booked.booking_id, 0.0) == 0
            assert not decision.done()
            assert not branch.done()
            print("PASS: live fail-safe stop and ACK before releasing sandbox solver worker")
        finally:
            release.set()
        await decision
        outcome = await branch
        assert outcome.observed_until == snapshot.envelope.as_of + timedelta(minutes=20)
        print("PASS: live replan and sandbox branch completed after worker release")


if __name__ == "__main__":
    asyncio.run(main())
