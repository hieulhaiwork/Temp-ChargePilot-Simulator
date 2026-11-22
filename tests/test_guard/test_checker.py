"""Safety Guard (F4) — checker. Test từng luật FR12: tests/test_guard/test_rules.py.

AC6: bộ kiểm thử lệnh vi phạm (vượt tải, bật-tắt liên tục, lịch cũ, sai quyền…) phải bị
chặn 100%, hiện trên dashboard, không tới simulator.
"""

from datetime import datetime, timedelta, timezone

from src.guard.checker import check, check_batch
from src.guard.rules import RULES, GuardContext
from src.models.control import Command, CommandSource, CommandType, GuardRule, Violation
from src.models.station import ConnectorState, ConnectorStatus, StationState
from src.services import catalog

VN = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 16, 19, 0, tzinfo=VN)


def _ctx() -> GuardContext:
    state = StationState(
        timestamp=NOW,
        available_power_kw=35,
        schedule_version=3,
        connectors=[ConnectorState(connector_id="A01", status=ConnectorStatus.IDLE, power_kw=0, max_power_kw=7)],
    )
    return GuardContext(now=NOW, state=state, config=catalog.load_station_config())


def _cmd(connector_id: str = "A01") -> Command:
    return Command(
        type=CommandType.SET_POWER,
        connector_id=connector_id,
        power_kw=7,
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=3,
        based_on_state_at=NOW,
        created_at=NOW,
    )


def _ok(cmd, ctx):
    return None


def _fail(rule: GuardRule):
    return lambda cmd, ctx: Violation(rule=rule, detail=f"{rule} vi phạm")


def test_rules_registry_covers_every_fr12_rule():
    assert set(RULES) == set(GuardRule)


def test_command_passes_when_no_rule_fires():
    verdict = check(_cmd(), _ctx(), rules={GuardRule.TOTAL_POWER: _ok, GuardRule.PERMISSION: _ok})
    assert verdict.passed and verdict.violations == []


def test_all_violations_are_collected_not_just_the_first():
    rules = {
        GuardRule.TOTAL_POWER: _fail(GuardRule.TOTAL_POWER),
        GuardRule.PERMISSION: _ok,
        GuardRule.STALE_STATE: _fail(GuardRule.STALE_STATE),
    }
    verdict = check(_cmd(), _ctx(), rules=rules)
    assert not verdict.passed
    assert [v.rule for v in verdict.violations] == [GuardRule.TOTAL_POWER, GuardRule.STALE_STATE]


def test_batch_context_is_visible_to_every_rule():
    seen: list[int] = []

    def spy(cmd, ctx):
        seen.append(len(ctx.batch))
        return None

    check_batch([_cmd("A01"), _cmd("A02")], _ctx(), rules={GuardRule.CONFLICT: spy})
    assert seen == [2, 2]
