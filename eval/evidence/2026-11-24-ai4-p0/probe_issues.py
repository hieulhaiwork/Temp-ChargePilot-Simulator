"""P0 diagnostic using synthetic fixtures. A successful assertion confirms the observed baseline behavior."""

import asyncio
import json
from dataclasses import replace

from alembic import command
from alembic.config import Config

import tests  # noqa: F401  # Sets an isolated SQLite path before importing application modules.
from src.config import get_settings
from src.models.decisions import ReasonCode
from src.services import control_loop, decision_trace, repository
from src.services.runtime import fork_runtime
from tests.test_services.test_safety_event_delivery import _sim_runtime


def emit(issue, **facts):
    print(json.dumps({"issue": issue, **facts}, sort_keys=True, allow_nan=False), flush=True)


def booking_power(rt, booking_id):
    return next(c.power_kw for c in rt.simulator.state().connectors if c.booking_id == booking_id)


async def run():
    rt = await _sim_runtime(failsafe=True)
    sim = rt.simulator
    original_step = sim.adapter.step

    def faulty_step(vehicle_id, cabinet, kw, minutes):
        delivery = original_step(vehicle_id, cabinet, kw, minutes)
        if vehicle_id == "dc-a" and kw > 0:
            return replace(delivery, battery_kwh=delivery.battery_kwh * 3)
        return delivery

    sim.adapter.step = faulty_step
    events = sim.step(5)
    sim.adapter.step = original_step
    await control_loop.on_minute(rt, events)

    trace = rt.recorder.decision_traces[-1]
    post_apply = trace["applied"]
    assert post_apply["hard_violations"] and post_apply["minutes"] > 0
    assert trace["decision"]["guard"]["status"] == "pass"
    assert ReasonCode.VIOLATION_AFTER_APPLY in trace["reason_codes"]
    emit(
        "R03",
        hard_violation_kinds=[v["kind"] for v in post_apply["hard_violation_details"]],
        applied_minutes=post_apply["minutes"],
        nested_guard_status=trace["decision"]["guard"]["status"],
    )

    current = rt.open_trace["trace"]
    held = current["held_for_pending_approval"]
    assert "dc-a" in held and rt.safety_hold_booking_ids == {"dc-a"}
    assert not rt.store.pending_approvals()
    emit(
        "R04",
        approval_labeled_booking_ids=held,
        safety_hold_booking_ids=sorted(rt.safety_hold_booking_ids),
        pending_approvals=len(rt.store.pending_approvals()),
    )

    fork = fork_runtime(rt, list(rt.store.active_bookings()))
    assert not fork.safety_hold_booking_ids
    assert booking_power(rt, "dc-a") == booking_power(fork, "dc-a") == 0
    from src.models.events import EventType, StationEvent

    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=fork.clock()), fork)
    assert booking_power(rt, "dc-a") == 0 and booking_power(fork, "dc-a") > 0
    emit(
        "R01",
        live_holds=sorted(rt.safety_hold_booking_ids),
        fork_holds=sorted(fork.safety_hold_booking_ids),
        live_output_kw=booking_power(rt, "dc-a"),
        fork_output_kw=booking_power(fork, "dc-a"),
    )

    zero = decision_trace.close_open(rt)
    zero_decision = zero["decision"]
    assert zero["applied"]["minutes"] == 0
    assert zero_decision["interval_minutes"] > 0 and zero_decision["guard"]["status"] == "pass"
    assert zero_decision["vehicles"]
    assert all(row["actual_output_kw"] == 0 for row in zero_decision["vehicles"].values())
    emit(
        "R03",
        applied_minutes=0,
        decision_interval_minutes=zero_decision["interval_minutes"],
        nested_guard_status=zero_decision["guard"]["status"],
    )

    vid = next(vid for vid, val in zero["approved_setpoints_kw"].items() if val > 0)
    row = zero_decision["vehicles"][vid]
    assert row["requested_output_kw"] == zero["approved_setpoints_kw"][vid]
    assert row["actual_output_kw"] == 0
    emit(
        "R05",
        applied_minutes=0,
        approved_output_kw=zero["approved_setpoints_kw"][vid],
        nested_requested_output_kw=row["requested_output_kw"],
        nested_actual_output_kw=row["actual_output_kw"],
    )

    settings = get_settings()
    assert settings.decision_trace_dir == "" and "chargepilot-test-" in settings.database_url
    command.upgrade(Config("alembic.ini"), "head")
    repository.init()
    decision_trace.persist(zero, True)
    repository.dispose()
    repository.init()
    stored = repository.get_decision_trace(zero["correlation_id"])
    assert stored is not None and stored.closed and stored.artifact is None
    assert "decision" not in stored.model_dump() and "applied" not in stored.model_dump()
    repository.dispose()
    emit(
        "R02",
        sqlite_summary_after_reopen=True,
        trace_dir_configured=False,
        artifact_present=False,
        full_decision_fields_available=False,
    )


if __name__ == "__main__":
    asyncio.run(run())
