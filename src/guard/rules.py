"""7 luật xác định của FR12. Mỗi luật: hàm THUẦN (Command, GuardContext) → Violation | None.

Quy ước: luật KHÔNG tự đọc DB/simulator — mọi dữ kiện nằm trong GuardContext, nên test
được bằng dữ liệu dựng tay. NFR: mỗi luật có ít nhất một unit test "lệnh vi phạm bị chặn"
và một test "lệnh hợp lệ không bị chặn oan" (tests/test_guard/).

Công suất SAU lệnh: mọi lệnh cùng lô (ctx.batch) được áp giả định trước khi so giới hạn, nên
một lô hạ A rồi tăng B không bị chặn oan. Hai luật vật lý GỌI Guard của HybridSimulator qua `physical/adapter.py`
(`src/guard/physical/validator.py`, ADR-017); ba tầng giới hạn (ADR-010):
  - cổng ≤ max_power_kw của cổng và ≤ Booking.max_charge_power_kw của xe;
    chỉ cấp điện cho cổng có xe đang sạc (không cổng trống, không xe đã đầy)  (connector_power_limit)
  - gán cổng: xe đã đến bãi, đang chờ (chưa ở cổng khác), đúng vùng, cổng trống (connector_power_limit)
  - Σ cổng của tủ ≤ output_limit_kw; Σ vùng ≤ config.zone_cap_kw (trần thiết bị, vắng thì ngân sách);
    nguồn chung: Σ cổng / η ≤ state.available_power_kw;
    nguồn độc lập: thêm Σ vùng / η ≤ independent_grid_input_limit_kw[vùng]          (total_power_limit)

Owner: TV3. Task: T3.1.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.guard.physical import adapter as physical
from src.models.charging import Booking
from src.models.control import Command, CommandSource, CommandType, GuardRule, Role, Violation
from src.models.station import ConnectorState, StationConfig, StationState

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


def _occupant_after(cmd: Command, ctx: GuardContext, current: ConnectorState) -> str | None:
    """Xe ở cổng SAU lô: lệnh gán cùng lô (lệnh đang xét hoặc lệnh khác) thắng xe đang cắm."""
    if cmd.type == CommandType.ASSIGN_CONNECTOR:
        return cmd.booking_id
    assigned = next(
        (
            c.booking_id
            for c in ctx.batch
            if c.type == CommandType.ASSIGN_CONNECTOR and c.connector_id == cmd.connector_id
        ),
        None,
    )
    return assigned or current.booking_id


def is_load_reduction(cmd: Command, ctx: GuardContext) -> bool:
    """Lệnh công suất KHÔNG tăng công suất cổng của nó (STOP / SET_POWER ≤ hiện tại) — không thể làm tổng tăng."""
    if cmd.type not in POWER_COMMANDS:
        return False
    current = _connector(ctx, cmd.connector_id)
    return current is not None and target_power_kw(cmd, current) <= current.power_kw + TOL_KW


def site_over_hard_limit(ctx: GuardContext) -> str | None:
    """Trạng thái HIỆN TẠI (chưa áp lệnh nào) đã vượt trần cứng tủ / vùng / nguồn? Trả mô tả, hoặc None."""
    occupants = {c.connector_id: c.booking_id for c in ctx.state.connectors}
    return physical.check_site_allocation(ctx.config, ctx.state, _power_after(ctx, ()), occupants)


def is_safety_reduction(cmd: Command, ctx: GuardContext) -> bool:
    """Giảm tải CẦN cho an toàn (ADR-019 Phase 4, quyết định 3): lệnh giảm khi trạm đang vượt trần cứng, hoặc lệnh
    giảm của bảo vệ khẩn cấp. Loại lệnh này không bị anti_flapping / HITL giữ lại (fail-safe ưu tiên giảm tải)."""
    if not is_load_reduction(cmd, ctx):
        return False
    current = _connector(ctx, cmd.connector_id)
    if target_power_kw(cmd, current) >= current.power_kw - TOL_KW:
        return False  # không thực sự giảm
    return cmd.source == CommandSource.EMERGENCY or site_over_hard_limit(ctx) is not None


def _is_on(cmd: Command, current: ConnectorState | None) -> bool | None:
    """Bật / tắt sau lệnh; None nếu lệnh không bật-tắt (ASSIGN_CONNECTOR)."""
    if cmd.type not in POWER_COMMANDS:
        return None
    return target_power_kw(cmd, current) > TOL_KW


# ---- 7 luật ------------------------------------------------------------------------------


def check_total_power(cmd: Command, ctx: GuardContext) -> Violation | None:
    """Σ công suất SAU khi áp lệnh ≤ trần tủ / vùng / nguồn — Guard simulator (MT4 — 0 lần vượt, ADR-017).

    Lệnh giảm tải (không tăng công suất cổng của nó) không bao giờ làm tổng tăng nên không bị luật này chặn, kể cả
    khi lệnh TĂNG khác cùng lô làm tổng vượt (lệnh tăng đó vẫn bị chặn). Trước Phase 4, một lệnh giảm AC bị chặn vì
    lô có lệnh bật DC → setpoint AC cũ giữ nguyên → vượt budget AC +1,97 kW (PHASE3_REPORT §7).
    """
    if cmd.type not in POWER_COMMANDS or is_load_reduction(cmd, ctx):
        return None
    batch = _batch_with(cmd, ctx)
    occupants = {c.connector_id: c.booking_id for c in ctx.state.connectors}
    for other in batch:
        if other.type == CommandType.ASSIGN_CONNECTOR:
            occupants[other.connector_id] = other.booking_id
    detail = physical.check_site_allocation(ctx.config, ctx.state, _power_after(ctx, batch), occupants)
    return Violation(rule=GuardRule.TOTAL_POWER, detail=detail) if detail else None


def check_connector_power(cmd: Command, ctx: GuardContext) -> Violation | None:
    """Cổng tồn tại; cấp điện chỉ cho xe đang sạc, ≤ cổng và ≤ xe; gán cổng hợp lệ — Guard simulator (ADR-017)."""
    current = _connector(ctx, cmd.connector_id)
    if current is None or not any(c.connector_id == cmd.connector_id for c in ctx.config.connectors):
        return Violation(rule=GuardRule.CONNECTOR_POWER, detail=f"Không có đầu nối {cmd.connector_id}")
    occupant = _occupant_after(cmd, ctx, current)
    booking_id = cmd.booking_id or occupant
    booking = ctx.bookings.get(booking_id) if booking_id else None
    if cmd.type == CommandType.ASSIGN_CONNECTOR:
        detail = physical.check_dispatch(ctx.config, ctx.state, cmd.connector_id, cmd.booking_id or "", booking)
    else:
        target = target_power_kw(cmd, current)
        detail = physical.check_connector_allocation(ctx.config, current, occupant, target, booking)
    return Violation(rule=GuardRule.CONNECTOR_POWER, detail=detail) if detail else None


def check_anti_flapping(cmd: Command, ctx: GuardContext) -> Violation | None:
    """≤ config.guard.flap_max_toggles lần bật/tắt trong flap_window_minutes (S5: "lần 4/10 phút")."""
    current = _connector(ctx, cmd.connector_id)
    if _is_on(cmd, current) is None or is_safety_reduction(cmd, ctx):
        return None  # tắt để giảm tải khi đang vượt trần cứng / khẩn cấp: an toàn thắng chống bật-tắt
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
    if cmd.type == CommandType.ASSIGN_CONNECTOR:
        for other in ctx.batch:
            if (
                other.command_id != cmd.command_id
                and other.type == CommandType.ASSIGN_CONNECTOR
                and other.booking_id == cmd.booking_id
                and other.connector_id != cmd.connector_id
            ):
                return Violation(rule=GuardRule.CONFLICT, detail=f"Xe {cmd.booking_id} được gán vào hai cổng cùng lô")
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
