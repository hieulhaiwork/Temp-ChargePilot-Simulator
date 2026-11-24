"""ADR-019 Phase 4, quyết định 3: root-cause sai lệch AC +1,97 kW và cơ chế ưu tiên giảm tải.

Tái hiện đúng lô lệnh ở phút 560 của `peak_evening` seed 2 M3b (PHASE3_REPORT §7): lưới 35 kW, η 0,95 ⇒ trần đầu ra
33,25 kW. Kế hoạch đã qua Physical Guard dùng đúng trần: AC-01-1 7,278906… (giảm từ 9,25), DC-01-2 22,372009 (giữ),
DC-01-1 3,599085… (xe mới). Không luật cứng nào được nới: TOL vẫn 1e-7, lệnh TĂNG vẫn bị chặn khi tổng vượt.
"""

from dataclasses import replace
from datetime import timedelta

from src.guard import dispatcher
from src.guard.checker import check_batch
from src.guard.rules import check_total_power, is_safety_reduction
from src.models.charging import ConsentScope
from src.models.control import CommandSource, CommandType, GuardRule, quantize_kw
from tests.test_guard.test_dispatcher import RecordingActuator, Sinks
from tests.test_guard.test_rules import NOW, _booking, _cmd, _ctx, _state

AC_APPROVED = 7.278906094890233
DC_NEW_APPROVED = 3.5990853858902767


def _minute_560(power):
    """Trạng thái + lô lệnh của phút 560; `power` mã hoá setpoint thành số trong Command."""
    ctx = _ctx(_state(available=35, empty=("DC-01-1",), AC_01_1=9.25, DC_01_2=22.372009))
    assign = _cmd("DC-01-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b-new")
    ac = _cmd("AC-01-1", power(AC_APPROVED), booking_id="b-ac1")
    dc = _cmd("DC-01-1", power(DC_NEW_APPROVED), booking_id="b-new")
    return ctx, [assign, ac, dc]


def test_plan_saturates_the_grid_exactly():
    assert abs(AC_APPROVED + 22.37200851922121 + DC_NEW_APPROVED - 35 * 0.95) < 1e-9


def test_round_to_nearest_pushed_the_batch_over_the_hard_grid_cap():
    """Phase 3 (round 3 chữ số): AC 7,279 kW ⇒ Σ = 33,250009 kW > 33,25 ⇒ lệnh tăng DC bị chặn đúng (trần cứng)."""
    ctx, batch = _minute_560(lambda kw: round(kw, 3))
    verdicts = check_batch(batch, ctx)
    assert GuardRule.TOTAL_POWER in {v.rule for v in verdicts[2].violations}


def test_quantize_never_exceeds_the_approved_setpoint():
    for kw in (AC_APPROVED, DC_NEW_APPROVED, 4.35, 9.25, 0.0, 1e-12, 59.9999999):
        q = quantize_kw(kw)
        assert q <= kw + 1e-9 and kw - q < 0.001 + 1e-9
    assert quantize_kw(4.35) == 4.35 and quantize_kw(7.2789) == 7.278 and quantize_kw(-1) == 0.0


def test_floor_quantised_batch_passes_and_reduction_is_applied():
    ctx, batch = _minute_560(quantize_kw)
    assert all(v.passed for v in check_batch(batch, ctx))


def test_a_load_reduction_is_never_blocked_by_an_overloading_increase_in_the_same_batch():
    """Lệnh giảm AC hợp lệ dù lệnh bật DC cùng lô làm tổng vượt (lệnh bật DC vẫn bị chặn)."""
    ctx, (assign, ac, _) = _minute_560(quantize_kw)
    too_much = _cmd("DC-01-1", 5.0, booking_id="b-new")
    verdicts = check_batch([assign, ac, too_much], ctx)
    assert verdicts[1].passed
    assert GuardRule.TOTAL_POWER in {v.rule for v in verdicts[2].violations}


def test_total_power_still_blocks_any_increase():
    ctx = _ctx(_state(available=35, AC_01_1=9.25, DC_01_2=22.372009))
    assert check_total_power(_cmd("AC-01-1", 11.0, booking_id="b-ac1"), replace(ctx, batch=())) is not None


def _toggles(connector: str, n: int):
    return tuple(_cmd(connector, 7 if i % 2 == 0 else 0, created_at=NOW - timedelta(minutes=9 - i)) for i in range(n))


def test_safety_reduction_is_not_blocked_by_anti_flapping():
    """Trạm đang vượt trần cứng (nguồn giảm còn 10 kW): tắt AC-01-1 là giảm tải cần cho an toàn."""
    history = _toggles("AC-01-1", 3)  # on, off, on → lệnh off là lần đổi thứ 3
    over = _ctx(_state(available=10, AC_01_1=7, AC_02_1=7), recent_commands=history)
    off = _cmd("AC-01-1", 0)
    assert is_safety_reduction(off, over)
    assert GuardRule.ANTI_FLAPPING not in {v.rule for v in check_batch([off], over)[0].violations}
    # Không vượt trần: anti_flapping giữ nguyên hiệu lực với lệnh tắt thường.
    ok = replace(over, state=_state(available=106, AC_01_1=7))
    blocked = replace(ok, recent_commands=(*history, _cmd("AC-01-1", 0, created_at=NOW - timedelta(minutes=5))))
    assert not is_safety_reduction(off, ok)
    assert GuardRule.ANTI_FLAPPING in {
        v.rule for v in check_batch([_cmd("AC-01-1", 7)], blocked)[0].violations
    }  # bật lại lần thứ 4 vẫn bị chặn


def test_emergency_reduction_counts_as_safety_reduction():
    ctx = _ctx(_state(AC_01_1=7))
    assert is_safety_reduction(_cmd("AC-01-1", 3, source=CommandSource.EMERGENCY), ctx)
    assert not is_safety_reduction(_cmd("AC-01-1", 3), ctx)
    assert not is_safety_reduction(_cmd("AC-01-1", 9, source=CommandSource.EMERGENCY), ctx)


async def test_safety_reduction_does_not_wait_for_resident_consent():
    """Cư dân không cho giảm công suất (HITL) nhưng trạm đang vượt trần cứng ⇒ giảm ngay, ghi chú, báo sau."""
    strict = _booking().model_copy(update={"consent": ConsentScope(allow_power_reduction=False)})
    over = replace(_ctx(_state(available=40, DC_01_1=50)), bookings={"b-dc1": strict})
    down = _cmd("DC-01-1", 30, booking_id="b-dc1")
    actuator, sinks = RecordingActuator(), Sinks()
    entries = await dispatcher.submit([down], over, actuator, sinks.build())
    assert actuator.applied == [[down]] and entries[0].executed
    assert "Giảm tải an toàn" in entries[0].note and not sinks.approvals
    # Không vượt trần: cùng lệnh vẫn phải chờ cư dân duyệt (quyền phê duyệt không bị nới).
    normal = replace(over, state=_state(available=106, DC_01_1=50))
    actuator, sinks = RecordingActuator(), Sinks()
    entries = await dispatcher.submit([down], normal, actuator, sinks.build())
    assert actuator.applied == [] and sinks.approvals and not entries[0].executed


async def test_increase_that_relies_on_a_reduction_held_for_approval_is_not_applied():
    """Lô: hạ DC-01-1 60→30 (cần cư dân duyệt) + tăng DC-01-2 0→45 (60 + 45 = 105 kW / 0,95 > 106 kW lưới). Lô hợp lệ nếu áp cả hai; nhưng lệnh hạ bị giữ
    ⇒ áp riêng lệnh tăng sẽ vượt lưới ⇒ fail-safe: không áp lệnh tăng."""
    strict = _booking().model_copy(update={"consent": ConsentScope(allow_power_reduction=False)})
    ctx = replace(_ctx(_state(DC_01_1=60)), bookings={"b-dc1": strict})
    down, up = _cmd("DC-01-1", 30, booking_id="b-dc1"), _cmd("DC-01-2", 45)
    actuator, sinks = RecordingActuator(), Sinks()
    entries = await dispatcher.submit([down, up], ctx, actuator, sinks.build())
    assert actuator.applied == []
    assert [e.executed for e in entries] == [False, False]
    assert "chờ phê duyệt" in entries[0].note.lower() and "phụ thuộc lệnh giảm" in entries[1].note
    # Đối chứng: lô không cần duyệt thì vẫn áp cả hai (không chặn oan, test_total_power_counts_reductions…).
    actuator, sinks = RecordingActuator(), Sinks()
    await dispatcher.submit([down, up], _ctx(_state(DC_01_1=60)), actuator, sinks.build())
    assert actuator.applied == [[down, up]]


async def test_increase_that_relies_on_a_reduction_blocked_by_guard_is_not_applied():
    """Final Review §4.5: lệnh hạ DC-01-1 60→0 bị CHÍNH Guard chặn (anti_flapping, trạm không vượt trần nên không
    phải giảm tải an toàn) chứ không phải chờ duyệt. Lệnh tăng DC-01-2 0→45 chỉ qua `check_total_power` nhờ lệnh hạ đó
    ⇒ áp riêng sẽ vượt lưới (60 + 45 > 106 × 0,95) ⇒ không được áp."""
    history = tuple(
        _cmd("DC-01-1", 60 if i % 2 == 0 else 0, created_at=NOW - timedelta(minutes=9 - i)) for i in range(5)
    )
    ctx = _ctx(_state(DC_01_1=60), recent_commands=history)
    down, up = _cmd("DC-01-1", 0), _cmd("DC-01-2", 45)
    verdicts = check_batch([down, up], ctx)
    assert GuardRule.ANTI_FLAPPING in {v.rule for v in verdicts[0].violations} and verdicts[1].passed
    actuator, sinks = RecordingActuator(), Sinks()
    entries = await dispatcher.submit([down, up], ctx, actuator, sinks.build())
    assert actuator.applied == []
    assert [e.executed for e in entries] == [False, False]
    assert GuardRule.TOTAL_POWER in {v.rule for v in entries[1].verdict.violations}
