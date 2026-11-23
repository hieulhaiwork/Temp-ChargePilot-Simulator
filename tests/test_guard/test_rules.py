"""7 luật FR12 — mỗi luật: 1 ca bị chặn + 1 ca hợp lệ không bị chặn oan (AC6, NFR an toàn).

Trạm dùng topology thật của config/station.yaml (ADR-010): AC-01-1, AC-02-1 (11 kW, tủ riêng),
DC-01-1, DC-01-2 (60 kW, chung tủ 120 kW); ngân sách AC 22 / DC 78 kW, trần vùng AC 22 / DC 120 kW (ADR-017); η = 0,95.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.guard.checker import check, check_batch
from src.guard.rules import RULES, GuardContext
from src.models.charging import Booking, BookingStatus, ChargeMode, ChargeRequest, EnergyEstimate
from src.models.control import Command, CommandSource, CommandType, GuardRule, Role
from src.models.station import ConnectorState, ConnectorStatus, SessionProgress, StationState
from src.services import catalog

VN = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 22, 19, 0, tzinfo=VN)


OCCUPANTS = {"AC-01-1": "b-ac1", "AC-02-1": "b-ac2", "DC-01-1": "b-dc1", "DC-01-2": "b-dc2"}
WAITING = ("b-new", "b1", "b2")  # xe đã đến bãi, đang chờ cổng


def _state(available: float = 106, empty: tuple[str, ...] = (), **powers: float) -> StationState:
    """Mọi cổng có xe (trừ `empty`) — Guard chỉ cho cấp điện cổng có xe đang sạc (ADR-017)."""
    conns, sessions = [], []
    for spec in catalog.load_station_config().connectors:
        p = powers.get(spec.connector_id.replace("-", "_"), 0.0)
        booking_id = None if spec.connector_id in empty else OCCUPANTS[spec.connector_id]
        conns.append(
            ConnectorState(
                connector_id=spec.connector_id,
                status=ConnectorStatus.CHARGING if p else ConnectorStatus.IDLE,
                power_kw=p,
                max_power_kw=spec.max_power_kw,
                booking_id=booking_id,
            )
        )
        if booking_id:
            sessions.append(
                SessionProgress(
                    booking_id=booking_id, connector_id=spec.connector_id, arrived_at=NOW, plugged_in_at=NOW
                )
            )
    sessions += [SessionProgress(booking_id=b, arrived_at=NOW) for b in WAITING]
    return StationState(
        timestamp=NOW,
        available_power_kw=available,
        connectors=conns,
        queue=list(WAITING),
        sessions=sessions,
        schedule_version=3,
    )


def _booking(max_kw: float = 60) -> Booking:
    req = ChargeRequest(
        vehicle_model="VF9_123",
        soc_now=20,
        soc_target=80,
        deadline=NOW + timedelta(hours=2),
        mode=ChargeMode.WALK_IN,
        zone="DC",
    )
    energy = EnergyEstimate(
        vehicle_model="VF9_123", soc_now=20, soc_target=80, battery_energy_kwh=74, grid_energy_kwh=75, efficiency=0.98
    )
    return Booking(
        booking_id="b-dc1",
        resident_id="res-1",
        request=req,
        status=BookingStatus.CHARGING,
        energy=energy,
        max_charge_power_kw=max_kw,
        connector_id="DC-01-1",
        schedule_version=3,
        created_at=NOW,
    )


def _ctx(state: StationState | None = None, **kw) -> GuardContext:
    return GuardContext(
        now=NOW,
        state=state or _state(),
        config=catalog.load_station_config(),
        bookings={"b-dc1": _booking()},
        **kw,
    )


def _cmd(connector_id: str = "AC-01-1", power: float | None = 7, ctype=CommandType.SET_POWER, **kw) -> Command:
    base = {
        "type": ctype,
        "connector_id": connector_id,
        "power_kw": power,
        "source": CommandSource.OPTIMIZER,
        "issued_by": "optimizer",
        "based_on_schedule_version": 3,
        "based_on_state_at": NOW,
        "created_at": NOW,
    }
    return Command(**(base | kw))


def _rules_hit(cmd: Command, ctx: GuardContext) -> set[GuardRule]:
    return {v.rule for v in check(cmd, replace(ctx, batch=ctx.batch or (cmd,))).violations}


def test_valid_command_passes_every_rule():
    assert _rules_hit(_cmd(), _ctx()) == set()


# ---- total_power_limit -------------------------------------------------------------------


def test_total_power_blocks_grid_overload():
    # 60 + 50 kW đầu ra / 0,95 > 106 kW lưới — đồng thời vượt ngân sách DC 78 kW.
    ctx = _ctx(_state(DC_01_1=60))
    assert GuardRule.TOTAL_POWER in _rules_hit(_cmd("DC-01-2", 50), ctx)


def test_total_power_blocks_reduced_supply():
    ctx = _ctx(_state(available=10, AC_02_1=5))
    assert GuardRule.TOTAL_POWER in _rules_hit(_cmd("AC-01-1", 7), ctx)


def test_total_power_blocks_physical_zone_cap():
    # station.yaml: trần thiết bị DC 120 kW (ADR-017). Lưới 106 kW đặt cao để chỉ luật vùng được thử.
    ctx = _ctx(_state(available=200, DC_01_1=60, AC_01_1=0))
    cfg = ctx.config.model_copy(update={"physical_zone_cap_kw": {"AC": 22.0, "DC": 100.0}})
    assert GuardRule.TOTAL_POWER in _rules_hit(_cmd("DC-01-2", 45), replace(ctx, config=cfg))  # 105 > 100
    assert GuardRule.TOTAL_POWER not in _rules_hit(_cmd("DC-01-2", 40), replace(ctx, config=cfg))


def test_fixed_share_budget_is_not_a_hard_cap():
    """22/78 là phân bổ Fixed Share, không phải trần: DC 80 kW hợp lệ khi lưới còn chỗ (như simulator MVP-3)."""
    ctx = _ctx(_state(DC_01_1=50))
    assert GuardRule.TOTAL_POWER not in _rules_hit(_cmd("DC-01-2", 30), ctx)  # Σ DC 80 ≤ 120; 80/0,95 ≤ 106


def test_zone_budget_is_the_cap_when_no_physical_cap():
    """Config cũ không khai trần thiết bị ⇒ ngân sách là trần (scenario legacy của simulator)."""
    ctx = _ctx(_state(DC_01_1=50))
    legacy = replace(ctx, config=ctx.config.model_copy(update={"physical_zone_cap_kw": None}))
    assert GuardRule.TOTAL_POWER in _rules_hit(_cmd("DC-01-2", 30), legacy)  # Σ DC 80 > 78


def test_total_power_blocks_independent_zone_supply():
    ctx = _ctx(_state(available=200, DC_01_1=40))
    cfg = ctx.config.model_copy(
        update={"supply_mode": "independent", "independent_grid_input_limit_kw": {"AC": 24.0, "DC": 84.0}}
    )
    ctx = replace(ctx, config=cfg)
    assert GuardRule.TOTAL_POWER in _rules_hit(_cmd("DC-01-2", 41), ctx)  # 81 / 0,95 = 85,3 > 84
    assert GuardRule.TOTAL_POWER not in _rules_hit(_cmd("DC-01-2", 39), ctx)  # 79 / 0,95 = 83,2


def test_total_power_counts_reductions_in_the_same_batch():
    """Hạ DC-01-1 và tăng DC-01-2 cùng lô: tổng sau lô hợp lệ → không chặn oan."""
    ctx = _ctx(_state(DC_01_1=60))
    down, up = _cmd("DC-01-1", 30), _cmd("DC-01-2", 40)
    verdicts = check_batch([down, up], ctx)
    assert all(v.passed for v in verdicts), [v.violations for v in verdicts]


# ---- connector_power_limit ---------------------------------------------------------------


def test_connector_power_blocks_over_port_limit():
    assert GuardRule.CONNECTOR_POWER in _rules_hit(_cmd("AC-01-1", 12), _ctx())


def test_connector_power_blocks_over_vehicle_limit():
    ctx = replace(_ctx(), bookings={"b-dc1": _booking(max_kw=24)})
    assert GuardRule.CONNECTOR_POWER in _rules_hit(_cmd("DC-01-1", 30), ctx)
    assert GuardRule.CONNECTOR_POWER not in _rules_hit(_cmd("DC-01-1", 24), ctx)


def test_connector_power_blocks_unknown_and_faulted_connector():
    assert GuardRule.CONNECTOR_POWER in _rules_hit(_cmd("A99", 1), _ctx())
    state = _state()
    state.connectors[0].status = ConnectorStatus.FAULT
    assert GuardRule.CONNECTOR_POWER in _rules_hit(_cmd("AC-01-1", 3), _ctx(state))
    # Tắt hẳn một cổng lỗi là hợp lệ.
    assert GuardRule.CONNECTOR_POWER not in _rules_hit(_cmd("AC-01-1", 0), _ctx(state))


def test_connector_power_blocks_power_to_empty_connector():
    """Simulator chỉ cấp điện cho xe đang sạc — cổng trống thì không có điện."""
    ctx = _ctx(_state(empty=("AC-01-1",)))
    assert GuardRule.CONNECTOR_POWER in _rules_hit(_cmd("AC-01-1", 7), ctx)
    assert GuardRule.CONNECTOR_POWER not in _rules_hit(_cmd("AC-01-1", 0), ctx)  # tắt cổng trống vẫn hợp lệ


def test_connector_power_allows_assign_then_power_in_same_batch():
    ctx = _ctx(_state(empty=("AC-01-1",)))
    assign = _cmd("AC-01-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b-new")
    power = _cmd("AC-01-1", 7, booking_id="b-new")
    verdicts = check_batch([assign, power], ctx)
    assert all(v.passed for v in verdicts), [v.violations for v in verdicts]


def test_connector_power_blocks_power_to_finished_vehicle():
    state = _state()
    state.connectors[0].status = ConnectorStatus.FINISHED
    assert GuardRule.CONNECTOR_POWER in _rules_hit(_cmd("AC-01-1", 7), _ctx(state))
    assert GuardRule.CONNECTOR_POWER not in _rules_hit(_cmd("AC-01-1", 0), _ctx(state))


def test_assign_requires_vehicle_waiting_at_station():
    ctx = _ctx(_state(empty=("AC-01-1",)))
    absent = _cmd("AC-01-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b-not-here")
    plugged = _cmd("AC-01-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b-ac2")  # đang ở AC-02-1
    waiting = _cmd("AC-01-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b-new")
    assert GuardRule.CONNECTOR_POWER in _rules_hit(absent, ctx)
    assert GuardRule.CONNECTOR_POWER in _rules_hit(plugged, ctx)
    assert _rules_hit(waiting, ctx) == set()


# ---- anti_flapping -----------------------------------------------------------------------


def _toggle_history(n: int) -> tuple[Command, ...]:
    return tuple(_cmd("AC-01-1", 7 if i % 2 == 0 else 0, created_at=NOW - timedelta(minutes=9 - i)) for i in range(n))


def test_anti_flapping_blocks_fourth_toggle_in_window():
    # Lịch sử: on, off, on, off (3 lần đổi) → lệnh "on" tiếp theo là lần đổi thứ 4.
    ctx = _ctx(recent_commands=_toggle_history(4))
    assert GuardRule.ANTI_FLAPPING in _rules_hit(_cmd("AC-01-1", 7), ctx)


def test_anti_flapping_allows_same_state_and_old_history():
    ctx = _ctx(recent_commands=_toggle_history(4))
    assert GuardRule.ANTI_FLAPPING not in _rules_hit(_cmd("AC-01-1", 0), ctx)  # vẫn "off" — không phải bật/tắt
    old = tuple(c.model_copy(update={"created_at": c.created_at - timedelta(hours=1)}) for c in _toggle_history(4))
    assert GuardRule.ANTI_FLAPPING not in _rules_hit(_cmd("AC-01-1", 7), _ctx(recent_commands=old))


# ---- stale_state -------------------------------------------------------------------------


def test_stale_state_blocks_old_snapshot():
    assert GuardRule.STALE_STATE in _rules_hit(_cmd(based_on_state_at=NOW - timedelta(seconds=61)), _ctx())
    assert GuardRule.STALE_STATE not in _rules_hit(_cmd(based_on_state_at=NOW - timedelta(seconds=59)), _ctx())


# ---- permission --------------------------------------------------------------------------


def test_permission_blocks_resident_and_spoofed_operator():
    assert GuardRule.PERMISSION in _rules_hit(_cmd(), _ctx(actor_role=Role.RESIDENT))
    spoof = _cmd(source=CommandSource.OPERATOR, issued_by="op-1")
    assert GuardRule.PERMISSION in _rules_hit(spoof, _ctx())
    assert GuardRule.PERMISSION not in _rules_hit(spoof, _ctx(actor_role=Role.OPERATOR))
    # Vận hành không được mạo danh optimizer.
    assert GuardRule.PERMISSION in _rules_hit(_cmd(), _ctx(actor_role=Role.OPERATOR))


# ---- schedule_version --------------------------------------------------------------------


def test_schedule_version_blocks_old_plan():
    assert GuardRule.SCHEDULE_VERSION in _rules_hit(_cmd(based_on_schedule_version=2), _ctx())
    assert GuardRule.SCHEDULE_VERSION not in _rules_hit(_cmd(based_on_schedule_version=3), _ctx())


# ---- conflicting_commands ----------------------------------------------------------------


def test_conflict_blocks_start_and_stop_on_same_connector():
    start = _cmd("AC-01-1", None, ctype=CommandType.START)
    stop = _cmd("AC-01-1", None, ctype=CommandType.STOP)
    verdicts = check_batch([start, stop], _ctx())
    assert all(GuardRule.CONFLICT in {v.rule for v in verdict.violations} for verdict in verdicts)


def test_conflict_allows_assign_then_start_and_other_connectors():
    assign = _cmd("AC-01-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b-new")
    start = _cmd("AC-01-1", 7, ctype=CommandType.START)
    other = _cmd("AC-02-1", 7)
    verdicts = check_batch([assign, start, other], _ctx())
    assert all(GuardRule.CONFLICT not in {v.rule for v in verdict.violations} for verdict in verdicts)


def test_two_cars_on_one_connector_is_conflict():
    a = _cmd("AC-01-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b1")
    b = _cmd("AC-01-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b2")
    assert not any(v.passed for v in check_batch([a, b], _ctx()))


def test_one_car_on_two_connectors_is_conflict():
    ctx = _ctx(_state(empty=("AC-01-1", "AC-02-1")))
    a = _cmd("AC-01-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b-new")
    b = _cmd("AC-02-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b-new")
    verdicts = check_batch([a, b], ctx)
    assert all(GuardRule.CONFLICT in {v.rule for v in verdict.violations} for verdict in verdicts)


@pytest.mark.parametrize("rule", list(GuardRule))
def test_every_rule_has_an_implementation(rule):
    assert RULES[rule](_cmd(), replace(_ctx(), batch=(_cmd(),))) is None
