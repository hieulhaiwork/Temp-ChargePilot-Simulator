"""7 luật xác định của FR12. Mỗi luật: hàm THUẦN (Command, GuardContext) → Violation | None.

Quy ước: luật KHÔNG tự đọc DB/simulator — mọi dữ kiện nằm trong GuardContext, nên test
được bằng dữ liệu dựng tay. NFR: mỗi luật có ít nhất một unit test "lệnh vi phạm bị chặn"
và một test "lệnh hợp lệ không bị chặn oan" (tests/test_guard/).

Công suất SAU lệnh: mọi lệnh cùng lô (ctx.batch) được áp giả định trước khi so giới hạn, nên
một lô hạ A rồi tăng B không bị chặn oan. Ba tầng giới hạn (ADR-010):
  - cổng ≤ max_power_kw của cổng và ≤ Booking.max_charge_power_kw của xe     (connector_power_limit)
  - Σ cổng của tủ ≤ output_limit_kw; Σ vùng ≤ zone_budgets_kw;
    Σ cổng / power_conversion_efficiency ≤ state.available_power_kw (lưới)   (total_power_limit)

Owner: TV3. Task: T3.1.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.models.charging import Booking
from src.models.control import Command, CommandSource, CommandType, GuardRule, Role, Violation
from src.models.station import ConnectorState, ConnectorStatus, StationConfig, StationState

TOL_KW = 1e-6
POWER_COMMANDS = (CommandType.SET_POWER, CommandType.START, CommandType.STOP)


@dataclass(frozen=True)
class GuardContext:
    """Mọi dữ kiện các luật cần — truyền vào, luật không tự đi đọc."""

    now: datetime  # có múi giờ
    state: StationState
    config: StationConfig  # ngưỡng ở config.guard (station.yaml)
    actor_role: Role | None = None  # None = thành phần hệ thống (optimizer, emergency)
    # booking_id → Booking: luật công suất cần Booking.max_charge_power_kw (OBC của xe), luật quyền cần chủ booking
    bookings: Mapping[str, Booking] = field(default_factory=dict)
    batch: tuple[Command, ...] = ()  # các lệnh cùng lô — luật xung đột
    recent_commands: tuple[Command, ...] = ()  # lệnh đã thực thi gần đây — luật chống bật-tắt


Rule = Callable[[Command, GuardContext], Violation | None]


# ---- Helpers -----------------------------------------------------------------------------


def _connector(ctx: GuardContext, connector_id: str) -> ConnectorState | None:
    return next((c for c in ctx.state.connectors if c.connector_id == connector_id), None)


def target_power_kw(cmd: Command, current: ConnectorState | None) -> float:
    """Công suất của cổng SAU khi áp lệnh. START không ghi power_kw = công suất tối đa của cổng."""
    if cmd.type == CommandType.STOP:
        return 0.0
    if cmd.type == CommandType.SET_POWER:
        return float(cmd.power_kw or 0.0)
    if cmd.type == CommandType.START:
        if cmd.power_kw is not None:
            return float(cmd.power_kw)
        return current.max_power_kw if current else 0.0
    return current.power_kw if current else 0.0  # ASSIGN_CONNECTOR không đổi công suất


def _batch_with(cmd: Command, ctx: GuardContext) -> tuple[Command, ...]:
    """Lô dùng để tính tổng SAU lệnh: lệnh đang xét + các lệnh khác trong lô KHÔNG tự vi phạm giới hạn cổng.

    Lệnh vượt giới hạn cổng chắc chắn bị chặn, nên không được tính vào tổng — nếu không, một lệnh sai ở
    cổng A sẽ kéo theo chặn oan lệnh đúng ở cổng B.
    """
    others = tuple(c for c in ctx.batch if c.command_id != cmd.command_id and check_connector_power(c, ctx) is None)
    return (*others, cmd)


def _power_after(ctx: GuardContext, commands: Iterable[Command]) -> dict[str, float]:
    """connector_id → công suất sau khi áp các lệnh (lệnh sau cùng trên một cổng thắng)."""
    power = {c.connector_id: c.power_kw for c in ctx.state.connectors}
    for cmd in commands:
        if cmd.type in POWER_COMMANDS:
            power[cmd.connector_id] = target_power_kw(cmd, _connector(ctx, cmd.connector_id))
    return power


def _is_on(cmd: Command, current: ConnectorState | None) -> bool | None:
    """Bật / tắt sau lệnh; None nếu lệnh không bật-tắt (ASSIGN_CONNECTOR)."""
    if cmd.type not in POWER_COMMANDS:
        return None
    return target_power_kw(cmd, current) > TOL_KW


# ---- 7 luật ------------------------------------------------------------------------------


def check_total_power(cmd: Command, ctx: GuardContext) -> Violation | None:
    """Σ công suất SAU khi áp lệnh ≤ giới hạn lưới / tủ / vùng (MT4 — 0 lần vượt)."""
    if cmd.type not in POWER_COMMANDS:
        return None
    power = _power_after(ctx, _batch_with(cmd, ctx))
    specs = {c.connector_id: c for c in ctx.config.connectors}
    grid_kw = sum(power.values()) / ctx.config.power_conversion_efficiency
    if grid_kw > ctx.state.available_power_kw + TOL_KW:
        return Violation(
            rule=GuardRule.TOTAL_POWER,
            detail=f"Tổng phía lưới sau lệnh {grid_kw:.2f} kW > giới hạn {ctx.state.available_power_kw:g} kW",
        )
    spec = specs.get(cmd.connector_id)
    if spec is None:
        return None  # cổng lạ: luật connector_power_limit báo
    if spec.cabinet_id:
        cabinet = next((c for c in ctx.config.cabinets if c.cabinet_id == spec.cabinet_id), None)
        cab_kw = sum(p for cid, p in power.items() if cid in specs and specs[cid].cabinet_id == spec.cabinet_id)
        if cabinet and cab_kw > cabinet.output_limit_kw + TOL_KW:
            return Violation(
                rule=GuardRule.TOTAL_POWER,
                detail=f"Tủ {cabinet.cabinet_id}: {cab_kw:.2f} kW > giới hạn tủ {cabinet.output_limit_kw:g} kW",
            )
    budgets = ctx.config.zone_budgets_kw or {}
    if spec.zone in budgets:
        zone_kw = sum(p for cid, p in power.items() if cid in specs and specs[cid].zone == spec.zone)
        if zone_kw > budgets[spec.zone] + TOL_KW:
            return Violation(
                rule=GuardRule.TOTAL_POWER,
                detail=f"Vùng {spec.zone}: {zone_kw:.2f} kW > ngân sách {budgets[spec.zone]:g} kW",
            )
    return None


def check_connector_power(cmd: Command, ctx: GuardContext) -> Violation | None:
    """Công suất lệnh ≤ max_power_kw của cổng và ≤ giới hạn của xe; cổng phải tồn tại và không lỗi."""
    current = _connector(ctx, cmd.connector_id)
    if current is None:
        return Violation(rule=GuardRule.CONNECTOR_POWER, detail=f"Không có đầu nối {cmd.connector_id}")
    target = target_power_kw(cmd, current)
    if current.status == ConnectorStatus.FAULT and (target > TOL_KW or cmd.type == CommandType.ASSIGN_CONNECTOR):
        return Violation(rule=GuardRule.CONNECTOR_POWER, detail=f"Đầu nối {cmd.connector_id} đang lỗi")
    if target > current.max_power_kw + TOL_KW:
        return Violation(
            rule=GuardRule.CONNECTOR_POWER,
            detail=f"{target:g} kW > giới hạn cổng {cmd.connector_id} {current.max_power_kw:g} kW",
        )
    booking_id = cmd.booking_id or current.booking_id
    booking = ctx.bookings.get(booking_id) if booking_id else None
    if booking is not None and target > booking.max_charge_power_kw + TOL_KW:
        return Violation(
            rule=GuardRule.CONNECTOR_POWER,
            detail=f"{target:g} kW > giới hạn của xe {booking.max_charge_power_kw:g} kW ({booking_id})",
        )
    if cmd.type == CommandType.ASSIGN_CONNECTOR and current.booking_id and current.booking_id != cmd.booking_id:
        return Violation(
            rule=GuardRule.CONNECTOR_POWER,
            detail=f"Đầu nối {cmd.connector_id} đang có xe {current.booking_id}",
        )
    spec = next((c for c in ctx.config.connectors if c.connector_id == cmd.connector_id), None)
    if cmd.type == CommandType.ASSIGN_CONNECTOR and booking is not None and spec and spec.zone != booking.request.zone:
        return Violation(
            rule=GuardRule.CONNECTOR_POWER,
            detail=f"Xe vùng {booking.request.zone} không cắm được cổng {spec.zone} {cmd.connector_id} (ADR-010)",
        )
    return None


def check_anti_flapping(cmd: Command, ctx: GuardContext) -> Violation | None:
    """≤ config.guard.flap_max_toggles lần bật/tắt trong flap_window_minutes (S5: "lần 4/10 phút")."""
    current = _connector(ctx, cmd.connector_id)
    if _is_on(cmd, current) is None:
        return None
    window_start = ctx.now - timedelta(minutes=ctx.config.guard.flap_window_minutes)
    history = sorted(
        (c for c in ctx.recent_commands if c.connector_id == cmd.connector_id and c.created_at >= window_start),
        key=lambda c: c.created_at,
    )
    toggles = 0
    previous: bool | None = None
    for past in history:
        on = _is_on(past, current)
        if on is None:
            continue
        if previous is not None and on != previous:
            toggles += 1
        previous = on
    if previous is None:
        previous = current.power_kw > TOL_KW if current else False
    is_toggle = _is_on(cmd, current) != previous
    if is_toggle and toggles + 1 > ctx.config.guard.flap_max_toggles:
        return Violation(
            rule=GuardRule.ANTI_FLAPPING,
            detail=(
                f"Bật/tắt {cmd.connector_id} lần {toggles + 1} trong {ctx.config.guard.flap_window_minutes} phút "
                f"(tối đa {ctx.config.guard.flap_max_toggles})"
            ),
        )
    return None


def check_stale_state(cmd: Command, ctx: GuardContext) -> Violation | None:
    """now − cmd.based_on_state_at ≤ config.guard.max_state_age_seconds."""
    age = (ctx.now - cmd.based_on_state_at).total_seconds()
    if age > ctx.config.guard.max_state_age_seconds:
        return Violation(
            rule=GuardRule.STALE_STATE,
            detail=f"Lệnh dựa trên trạng thái cũ {age:.0f} s (tối đa {ctx.config.guard.max_state_age_seconds:g} s)",
        )
    return None


def check_permission(cmd: Command, ctx: GuardContext) -> Violation | None:
    """Cư dân không ra lệnh công suất; Agent chỉ đề xuất; chỉ vận hành/hệ thống áp lệnh."""
    if ctx.actor_role == Role.RESIDENT:
        return Violation(rule=GuardRule.PERMISSION, detail="Cư dân không được ra lệnh điều khiển trạm")
    if cmd.source == CommandSource.OPERATOR and ctx.actor_role != Role.OPERATOR:
        return Violation(rule=GuardRule.PERMISSION, detail="Lệnh nguồn 'operator' phải do vận hành gửi")
    if cmd.source in (CommandSource.OPTIMIZER, CommandSource.LOAD_BALANCER, CommandSource.EMERGENCY) and (
        ctx.actor_role is not None
    ):
        return Violation(rule=GuardRule.PERMISSION, detail=f"Nguồn '{cmd.source}' chỉ dành cho thành phần hệ thống")
    return None


def check_schedule_version(cmd: Command, ctx: GuardContext) -> Violation | None:
    """cmd.based_on_schedule_version == state.schedule_version — chặn lệnh dựa trên lịch cũ."""
    if cmd.based_on_schedule_version != ctx.state.schedule_version:
        return Violation(
            rule=GuardRule.SCHEDULE_VERSION,
            detail=f"Lệnh dựa trên lịch v{cmd.based_on_schedule_version}, trạm đang ở v{ctx.state.schedule_version}",
        )
    return None


def check_conflicts(cmd: Command, ctx: GuardContext) -> Violation | None:
    """Không có lệnh khác trong ctx.batch mâu thuẫn trên CÙNG đầu nối."""
    current = _connector(ctx, cmd.connector_id)
    for other in ctx.batch:
        if other.command_id == cmd.command_id or other.connector_id != cmd.connector_id:
            continue
        if cmd.type in POWER_COMMANDS and other.type in POWER_COMMANDS:
            if abs(target_power_kw(cmd, current) - target_power_kw(other, current)) > TOL_KW:
                return Violation(
                    rule=GuardRule.CONFLICT,
                    detail=f"Hai lệnh công suất khác nhau cùng lô trên {cmd.connector_id}",
                )
        if (
            cmd.type == CommandType.ASSIGN_CONNECTOR
            and other.type == CommandType.ASSIGN_CONNECTOR
            and cmd.booking_id != other.booking_id
        ):
            return Violation(rule=GuardRule.CONFLICT, detail=f"Hai xe cùng được gán vào {cmd.connector_id}")
    return None


RULES: Mapping[GuardRule, Rule] = {
    GuardRule.TOTAL_POWER: check_total_power,
    GuardRule.CONNECTOR_POWER: check_connector_power,
    GuardRule.ANTI_FLAPPING: check_anti_flapping,
    GuardRule.STALE_STATE: check_stale_state,
    GuardRule.PERMISSION: check_permission,
    GuardRule.SCHEDULE_VERSION: check_schedule_version,
    GuardRule.CONFLICT: check_conflicts,
}
