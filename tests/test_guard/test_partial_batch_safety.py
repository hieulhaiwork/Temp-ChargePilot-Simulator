"""Final Review §4.5 — tập lệnh THỰC SỰ tới actuator luôn an toàn, kể cả khi một phần lô không được áp.

Bổ sung cho `test_load_reduction.py::test_increase_that_relies_on_a_reduction_blocked_by_guard_is_not_applied`:
lệnh giảm bị chặn vì trạng thái cũ (stale_state) / lịch cũ (schedule_version), lệnh giảm chờ duyệt rồi hết hạn
(expired), và một bộ kiểm bất biến trên lô ngẫu nhiên (seed cố định). Cùng fail-safe `curtail_to_hard_limits`
(§4.5b): đưa trạm đang vượt trần cứng về trong trần, đi qua dispatcher như lệnh khẩn cấp.
"""

import random
from dataclasses import replace
from datetime import timedelta

import pytest

from src.guard import approval, dispatcher, emergency
from src.guard.checker import check_batch
from src.guard.physical import adapter as physical
from src.guard.rules import (
    POWER_COMMANDS,
    TOL_KW,
    _power_after,
    check_connector_power,
    is_load_reduction,
    site_over_hard_limit,
)
from src.models.charging import ConsentScope
from src.models.control import ApprovalStatus, CommandSource, CommandType, GuardRule, Role
from src.services.errors import DomainError
from tests.test_guard.test_dispatcher import RecordingActuator, Sinks
from tests.test_guard.test_rules import NOW, _booking, _cmd, _ctx, _state

STRICT = _booking().model_copy(update={"consent": ConsentScope(allow_power_reduction=False)})
PORT_KW = {"AC-01-1": 11.0, "AC-02-1": 11.0, "DC-01-1": 60.0, "DC-01-2": 60.0}


def _applied(actuator: RecordingActuator):
    return [cmd for batch in actuator.applied for cmd in batch]


def _site_after(ctx, applied):
    occupants = {c.connector_id: c.booking_id for c in ctx.state.connectors}
    for cmd in applied:
        if cmd.type == CommandType.ASSIGN_CONNECTOR:
            occupants[cmd.connector_id] = cmd.booking_id
    return physical.check_site_allocation(ctx.config, ctx.state, _power_after(ctx, applied), occupants)


def _assert_actuated_set_is_safe(ctx, actuator):
    applied = _applied(actuator)
    for cmd in applied:
        if cmd.type in POWER_COMMANDS:
            assert check_connector_power(cmd, replace(ctx, batch=tuple(applied))) is None, cmd
    if site_over_hard_limit(ctx) is None:
        assert _site_after(ctx, applied) is None, [(c.connector_id, c.power_kw) for c in applied]
    else:  # trạm đã vượt trần trước lô: chỉ được về trong trần, hoặc chỉ giảm
        assert _site_after(ctx, applied) is None or all(
            is_load_reduction(c, ctx) for c in applied if c.type in POWER_COMMANDS
        )


# ---- lô bị chặn / chờ duyệt / hết hạn / cũ -----------------------------------------------------


async def test_increase_relying_on_a_stale_reduction_is_not_applied():
    """Lệnh hạ DC-01-1 dựa trên trạng thái cũ 5 phút (stale_state, ngưỡng 60 s) bị chặn ⇒ lệnh tăng DC-01-2 dựa vào
    nó (60 + 45 > 106 × 0,95) không được áp."""
    ctx = _ctx(_state(DC_01_1=60))
    down = _cmd("DC-01-1", 0, based_on_state_at=NOW - timedelta(minutes=5))
    up = _cmd("DC-01-2", 45)
    verdicts = check_batch([down, up], ctx)
    assert GuardRule.STALE_STATE in {v.rule for v in verdicts[0].violations} and verdicts[1].passed
    actuator, sinks = RecordingActuator(), Sinks()
    entries = await dispatcher.submit([down, up], ctx, actuator, sinks.build())
    assert actuator.applied == [] and [e.executed for e in entries] == [False, False]
    assert GuardRule.TOTAL_POWER in {v.rule for v in entries[1].verdict.violations}
    _assert_actuated_set_is_safe(ctx, actuator)


async def test_increase_relying_on_a_reduction_from_an_old_schedule_is_not_applied():
    ctx = _ctx(_state(DC_01_1=60))
    down, up = _cmd("DC-01-1", 0, based_on_schedule_version=2), _cmd("DC-01-2", 45)
    actuator, sinks = RecordingActuator(), Sinks()
    entries = await dispatcher.submit([down, up], ctx, actuator, sinks.build())
    assert GuardRule.SCHEDULE_VERSION in {v.rule for v in entries[0].verdict.violations}
    assert actuator.applied == [] and not any(e.executed for e in entries)


async def test_expired_reduction_never_unlocks_the_increase_that_relied_on_it():
    """Lệnh hạ chờ cư dân duyệt rồi HẾT HẠN (AC4: không thực thi). Lệnh tăng đi kèm không được áp lúc gửi lô, và khi
    optimizer đề xuất lại riêng lệnh tăng trên trạng thái chưa giảm thì luật tổng công suất vẫn chặn."""
    ctx = replace(_ctx(_state(DC_01_1=60)), bookings={"b-dc1": STRICT})
    down, up = _cmd("DC-01-1", 30, booking_id="b-dc1"), _cmd("DC-01-2", 45)
    actuator, sinks = RecordingActuator(), Sinks()
    await dispatcher.submit([down, up], ctx, actuator, sinks.build())
    assert actuator.applied == [] and len(sinks.approvals) == 1
    pending = sinks.approvals[0]
    later = pending.expires_at + timedelta(seconds=1)
    expired = approval.expire_overdue([pending], later)
    assert [a.status for a in expired] == [ApprovalStatus.EXPIRED]
    with pytest.raises(DomainError):
        approval.decide(pending, "approve", "res-1", Role.RESIDENT, later)
    retry = replace(ctx, now=later)
    up_again = _cmd("DC-01-2", 45, based_on_state_at=later, created_at=later)
    entries = await dispatcher.submit([up_again], retry, actuator, sinks.build())
    assert actuator.applied == [] and not entries[0].executed
    assert GuardRule.TOTAL_POWER in {v.rule for v in entries[0].verdict.violations}


async def test_random_batches_only_ever_actuate_a_safe_set():
    """Bất biến (seed cố định, 400 lô): mọi lô lệnh (bị chặn / chờ duyệt / cũ / xung đột / chống bật-tắt lẫn lộn) —
    tập lệnh tới actuator không vượt cổng / xe, và trạm đang trong trần thì sau lô vẫn trong trần."""
    rng = random.Random(20261124)
    connectors = list(PORT_KW)
    checked = partial = 0
    for _ in range(400):
        powers = {
            cid.replace("-", "_"): round(rng.uniform(0, PORT_KW[cid]), 3) * rng.choice((0, 1, 1)) for cid in PORT_KW
        }
        ctx = _ctx(_state(available=rng.choice((106, 80, 60, 35, 20)), **powers))
        if rng.random() < 0.5:
            ctx = replace(ctx, bookings={"b-dc1": STRICT})
        if rng.random() < 0.3:
            cid = rng.choice(connectors)
            history = tuple(
                _cmd(cid, PORT_KW[cid] if i % 2 == 0 else 0, created_at=NOW - timedelta(minutes=9 - i))
                for i in range(4)
            )
            ctx = replace(ctx, recent_commands=history)
        batch = []
        for _ in range(rng.randint(1, 4)):
            cid = rng.choice(connectors)
            ctype = rng.choice((CommandType.SET_POWER, CommandType.SET_POWER, CommandType.STOP, CommandType.START))
            power = None if ctype == CommandType.STOP else round(rng.uniform(0, PORT_KW[cid] * 1.2), 3)
            extra = {}
            if rng.random() < 0.15:
                extra["based_on_state_at"] = NOW - timedelta(minutes=5)
            if rng.random() < 0.1:
                extra["based_on_schedule_version"] = 2
            if rng.random() < 0.2:
                extra["source"] = CommandSource.AGENT  # luôn chờ vận hành duyệt
            if cid == "DC-01-1" and rng.random() < 0.7:
                extra["booking_id"] = "b-dc1"
            batch.append(_cmd(cid, power, ctype=ctype, **extra))
        actuator, sinks = RecordingActuator(), Sinks()
        entries = await dispatcher.submit(batch, ctx, actuator, sinks.build())
        assert len(entries) == len(batch)
        executed = [e.command for e in entries if e.executed]
        assert executed == _applied(actuator)  # nhật ký khớp đúng những gì tới trạm
        partial += 0 < len(executed) < len(batch)
        _assert_actuated_set_is_safe(ctx, actuator)
        checked += 1
    assert checked == 400 and partial > 20  # đủ nhiều lô bị áp một phần để bất biến có ý nghĩa


# ---- fail-safe sau khi áp (§4.5b) --------------------------------------------------------------


def test_curtail_to_hard_limits_brings_the_site_back_within_every_hard_cap():
    over = _ctx(_state(available=60, AC_01_1=11, AC_02_1=11, DC_01_1=60, DC_01_2=60))
    assert site_over_hard_limit(over) is not None
    commands = emergency.curtail_to_hard_limits(over.state, over.config, NOW, "grid 60 kW")
    assert {c.connector_id for c in commands} == set(PORT_KW)
    assert all(c.source == CommandSource.EMERGENCY and c.type == CommandType.SET_POWER for c in commands)
    assert all(
        c.power_kw <= next(x.power_kw for x in over.state.connectors if x.connector_id == c.connector_id)
        for c in commands
    )
    assert _site_after(over, commands) is None
    total = sum(c.power_kw for c in commands)
    assert 60 * 0.95 - 0.01 <= total <= 60 * 0.95 + TOL_KW  # co vừa đủ, không cắt thừa
    assert emergency.curtail_to_hard_limits(_state(AC_01_1=11).model_copy(), over.config, NOW) == []


async def test_failsafe_commands_pass_dispatcher_without_waiting_for_consent_or_anti_flapping():
    history = tuple(
        _cmd("DC-01-1", 60 if i % 2 == 0 else 0, created_at=NOW - timedelta(minutes=9 - i)) for i in range(5)
    )
    over = replace(
        _ctx(_state(available=40, DC_01_1=50, DC_01_2=20), recent_commands=history), bookings={"b-dc1": STRICT}
    )
    commands = emergency.curtail_to_hard_limits(over.state, over.config, NOW)
    actuator, sinks = RecordingActuator(), Sinks()
    entries = await dispatcher.submit(commands, over, actuator, sinks.build())
    assert all(e.executed for e in entries) and not sinks.approvals
    assert _site_after(over, _applied(actuator)) is None
