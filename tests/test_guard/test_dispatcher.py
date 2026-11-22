"""guard/dispatcher.py, approval.py, emergency.py — luồng check → duyệt → apply → log (FR12–FR14).

Test double cho actuator đặt ở đây (không ở src/): ghi lại mọi lô lệnh được áp, để khẳng định
"lệnh bị chặn KHÔNG tới simulator" (AC6).
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta

import pytest

from src.guard import approval, dispatcher, emergency
from src.guard.checker import check
from src.models.api import ErrorCode
from src.models.charging import ConsentScope
from src.models.control import ApprovalKind, ApprovalStatus, Command, CommandSource, CommandType, Role
from src.models.events import WsMessageType
from src.services.errors import DomainError
from tests.test_guard.test_rules import NOW, _booking, _cmd, _ctx, _state


class RecordingActuator:
    """Giả lập phần GHI của simulator — chỉ ghi nhận, không mô phỏng."""

    def __init__(self) -> None:
        self.applied: list[list[Command]] = []

    def apply_commands(self, commands: Sequence[Command]) -> None:
        self.applied.append(list(commands))


class Sinks:
    def __init__(self) -> None:
        self.decisions, self.approvals, self.messages = [], [], []

    def build(self) -> dispatcher.DispatchSinks:
        async def notify(msg, target):
            self.messages.append((msg.type, target))

        return dispatcher.DispatchSinks(
            log_decision=self.decisions.append, save_approval=self.approvals.append, notify=notify
        )


def test_recording_actuator_satisfies_protocol():
    actuator = RecordingActuator()
    actuator.apply_commands([])
    assert actuator.applied == [[]]


# ---- T3.1: dispatcher.submit -------------------------------------------------------------


async def test_valid_command_is_applied_and_logged():
    actuator, sinks = RecordingActuator(), Sinks()
    cmd = _cmd()
    entries = await dispatcher.submit([cmd], _ctx(), actuator, sinks.build())
    assert actuator.applied == [[cmd]]
    assert [e.executed for e in sinks.decisions] == [True]
    assert entries == sinks.decisions


async def test_blocked_command_never_reaches_actuator():
    """AC6."""
    actuator, sinks = RecordingActuator(), Sinks()
    entries = await dispatcher.submit([_cmd("AC-01-1", 50)], _ctx(), actuator, sinks.build())
    assert actuator.applied == []
    assert entries[0].executed is False
    assert entries[0].verdict.violations
    assert sinks.messages == [(WsMessageType.COMMAND_BLOCKED, None)]


async def test_every_command_is_logged():
    """FR14, MT6. Lô 3 lệnh: 1 hợp lệ, 1 bị chặn, 1 cần cư dân duyệt (xe không cho giảm công suất)."""
    actuator, sinks = RecordingActuator(), Sinks()
    strict = _booking().model_copy(update={"consent": ConsentScope(allow_power_reduction=False)})
    ctx = replace(_ctx(), bookings={"b-dc1": strict})
    cmds = [_cmd("AC-01-1", 7), _cmd("AC-02-1", 99), _cmd("DC-01-1", 20)]
    entries = await dispatcher.submit(cmds, ctx, actuator, sinks.build())
    assert len(sinks.decisions) == 3 == len(entries)
    assert [e.command.command_id for e in entries] == [c.command_id for c in cmds]
    assert actuator.applied == [[cmds[0]]]
    assert len(sinks.approvals) == 1
    assert sinks.approvals[0].requested_from == "res-1"
    assert (WsMessageType.APPROVAL_REQUEST, "res-1") in sinks.messages


async def test_one_bad_command_does_not_block_valid_ones_on_other_connectors():
    actuator = RecordingActuator()
    bad, good = _cmd("AC-01-1", 50), _cmd("AC-02-1", 7)
    await dispatcher.submit([bad, good], _ctx(), actuator, Sinks().build())
    assert actuator.applied == [[good]]


# ---- T3.2: approval ----------------------------------------------------------------------


def test_adjustment_within_consent_needs_no_approval():
    assert approval.requires_approval(_cmd("DC-01-1", 20), _booking()) is None


def test_adjustment_outside_consent_needs_resident():
    late = _booking().model_copy(update={"planned_start": NOW - timedelta(minutes=60)})
    start = _cmd("DC-01-1", None, ctype=CommandType.START)
    assert approval.requires_approval(start, late) == ApprovalKind.RESIDENT_CONSENT
    relaxed = late.model_copy(update={"consent": ConsentScope(max_start_delay_minutes=90)})
    assert approval.requires_approval(start, relaxed) is None


def test_emergency_command_is_never_held_for_approval():
    strict = _booking().model_copy(update={"consent": ConsentScope(allow_power_reduction=False)})
    assert approval.requires_approval(_cmd("DC-01-1", 1, source=CommandSource.EMERGENCY), strict) is None
    assert approval.requires_approval(_cmd(source=CommandSource.AGENT), None) == ApprovalKind.OPERATOR_REVIEW


def _pending():
    cmd = _cmd("DC-01-1", 20)
    return approval.open_approval(cmd, check(cmd, _ctx()), ApprovalKind.RESIDENT_CONSENT, booking=_booking())


def test_only_the_asked_person_can_decide():
    pending = _pending()
    with pytest.raises(DomainError) as err:
        approval.decide(pending, "approve", "res-other", Role.RESIDENT, NOW)
    assert err.value.code == ErrorCode.FORBIDDEN
    with pytest.raises(DomainError):
        approval.decide(pending, "approve", "op-1", Role.OPERATOR, NOW)
    assert approval.decide(pending, "reject", "res-1", Role.RESIDENT, NOW).status == ApprovalStatus.REJECTED


def test_deciding_twice_is_conflict():
    decided = approval.decide(_pending(), "approve", "res-1", Role.RESIDENT, NOW)
    with pytest.raises(DomainError) as err:
        approval.decide(decided, "reject", "res-1", Role.RESIDENT, NOW)
    assert err.value.code == ErrorCode.APPROVAL_ALREADY_DECIDED


def test_expired_approval_cannot_be_decided_and_is_marked():
    """AC4: hết hạn = không thực thi."""
    pending = _pending()
    later = pending.expires_at + timedelta(seconds=1)
    with pytest.raises(DomainError):
        approval.decide(pending, "approve", "res-1", Role.RESIDENT, later)
    assert [a.status for a in approval.expire_overdue([pending], later)] == [ApprovalStatus.EXPIRED]
    assert approval.expire_overdue([pending], NOW) == []


async def test_approved_command_is_rechecked_against_fresh_state():
    """Lệnh được duyệt nhưng nguồn đã giảm khiến lệnh vi phạm → KHÔNG áp, log executed=False."""
    decided = approval.decide(_pending(), "approve", "res-1", Role.RESIDENT, NOW)
    actuator, sinks = RecordingActuator(), Sinks()
    fresh = _ctx(_state(available=5).model_copy(update={"schedule_version": 7}))
    entry = await dispatcher.execute_approved(decided, fresh, actuator, sinks.build())
    assert entry.executed is False
    assert actuator.applied == []
    ok = await dispatcher.execute_approved(decided, _ctx(), actuator, sinks.build())
    assert ok.executed is True
    assert ok.approved_by == "res-1"
    assert len(actuator.applied) == 1


# ---- T3.2: emergency ---------------------------------------------------------------------


def test_total_power_under_new_limit_without_optimizer():
    """AC5. 4 cổng đang cấp điện, nguồn rớt còn 20 kW. Then Σ lệnh ≤ 20, source=EMERGENCY."""
    state = _state(AC_01_1=11, AC_02_1=11, DC_01_1=30, DC_01_2=30)
    cmds = emergency.curtail_to_limit(state, 20, NOW)
    assert sum(c.power_kw for c in cmds) <= 20
    assert all(c.source == CommandSource.EMERGENCY and c.type == CommandType.SET_POWER for c in cmds)
    with_eta = emergency.curtail_to_limit(state, 20, NOW, efficiency=0.95)
    assert sum(c.power_kw for c in with_eta) / 0.95 <= 20 + 1e-9


def test_no_commands_when_already_under_limit():
    assert emergency.curtail_to_limit(_state(AC_01_1=11, AC_02_1=4), 20, NOW) == []


async def test_emergency_commands_pass_guard_and_are_applied():
    state = _state(available=20, AC_01_1=11, AC_02_1=11, DC_01_1=30)
    actuator = RecordingActuator()
    cmds = emergency.curtail_to_limit(state, 20, NOW, efficiency=0.95)
    entries = await dispatcher.submit(cmds, _ctx(state), actuator, Sinks().build())
    assert all(e.executed for e in entries)
    assert len(actuator.applied) == 1
