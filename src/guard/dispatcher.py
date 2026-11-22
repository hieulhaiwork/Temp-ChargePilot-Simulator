"""Chokepoint DUY NHẤT đưa lệnh tới trạm (simulator).

    Command[] ─► checker.check_batch
                  ├─ bị chặn   → sinks.log_decision(executed=False)
                  │              + sinks.notify(COMMAND_BLOCKED) — KHÔNG tới simulator (AC6)
                  └─ qua Guard → approval.requires_approval
                                  ├─ cần duyệt → approval.open_approval → sinks.save_approval
                                  │              + sinks.notify(APPROVAL_REQUEST), chờ decide()
                                  └─ không     → actuator.apply_commands → sinks.log_decision(executed=True)

Khi một Approval được duyệt: execute_approved() kiểm Guard LẦN NỮA trên trạng thái mới
nhất (trạng thái có thể đã đổi trong lúc chờ người duyệt) rồi mới apply.

DispatchSinks (ADR-007): dispatcher không tự biết ghi nhật ký vào đâu. Chế độ chạy thật
truyền sinks trỏ tới repository + realtime; benchmark truyền sinks gom vào bộ nhớ — nhờ vậy
benchmark đi đúng đường Guard của production mà không ghi DB hay đẩy WebSocket.

Chỉ module này được import StationActuator / gọi apply_commands (tests/test_architecture.py).
Owner: TV3. Task: T3.1, T3.2.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace

from src.guard import approval as approval_rules
from src.guard.checker import check, check_batch
from src.guard.rules import GuardContext
from src.models.control import Approval, ApprovalKind, Command, DecisionLogEntry
from src.models.events import WsMessage, WsMessageType
from src.simulator.base import StationActuator


@dataclass(frozen=True)
class DispatchSinks:
    """Ba đầu ra của dispatcher — composition root (services/runtime.py) quyết định trỏ đi đâu."""

    log_decision: Callable[[DecisionLogEntry], None]  # FR14 — mọi lệnh, kể cả bị chặn
    save_approval: Callable[[Approval], None]  # FR13 — trạng thái phê duyệt phải được lưu thật
    notify: Callable[[WsMessage, str | None], Awaitable[None]]  # (bản tin, resident_id đích | None = vận hành)


def _message(kind: WsMessageType, payload, at) -> WsMessage:
    return WsMessage(type=kind, payload=payload.model_dump(mode="json"), sent_at=at)


def _booking_for(cmd: Command, ctx: GuardContext):
    if cmd.booking_id:
        return ctx.bookings.get(cmd.booking_id)
    conn = next((c for c in ctx.state.connectors if c.connector_id == cmd.connector_id), None)
    return ctx.bookings.get(conn.booking_id) if conn and conn.booking_id else None


async def submit(
    commands: Sequence[Command],
    ctx: GuardContext,
    actuator: StationActuator,
    sinks: DispatchSinks,
    *,
    approval_ttl_minutes: int = 15,
) -> list[DecisionLogEntry]:
    """Đưa một lô lệnh qua luồng ở docstring module; trả nhật ký cho từng lệnh (FR14), cùng thứ tự đầu vào.

    Lệnh hợp lệ trên các cổng khác vẫn được áp dù một lệnh trong lô bị chặn.
    """
    if not commands:
        return []
    verdicts = check_batch(commands, ctx)
    entries: list[DecisionLogEntry | None] = [None] * len(commands)
    to_apply: list[tuple[int, Command]] = []
    for i, (cmd, verdict) in enumerate(zip(commands, verdicts, strict=True)):
        if not verdict.passed:
            entry = DecisionLogEntry(timestamp=ctx.now, command=cmd, verdict=verdict, executed=False, note="Guard chặn")
            sinks.log_decision(entry)
            await sinks.notify(_message(WsMessageType.COMMAND_BLOCKED, entry, ctx.now), None)
            entries[i] = entry
            continue
        booking = _booking_for(cmd, ctx)
        kind = approval_rules.requires_approval(cmd, booking)
        if kind is None:
            to_apply.append((i, cmd))
            continue
        pending = approval_rules.open_approval(cmd, verdict, kind, booking=booking, ttl_minutes=approval_ttl_minutes)
        sinks.save_approval(pending)
        entry = DecisionLogEntry(
            timestamp=ctx.now,
            command=cmd,
            verdict=verdict,
            approval_id=pending.approval_id,
            executed=False,
            note=f"Chờ phê duyệt ({kind.value})",
        )
        sinks.log_decision(entry)
        target = pending.requested_from if kind == ApprovalKind.RESIDENT_CONSENT else None
        await sinks.notify(_message(WsMessageType.APPROVAL_REQUEST, pending, ctx.now), target)
        entries[i] = entry
    if to_apply:
        actuator.apply_commands([cmd for _, cmd in to_apply])
        for i, cmd in to_apply:
            entry = DecisionLogEntry(timestamp=ctx.now, command=cmd, verdict=verdicts[i], executed=True)
            sinks.log_decision(entry)
            entries[i] = entry
    return [e for e in entries if e is not None]


async def execute_approved(
    approval: Approval, ctx: GuardContext, actuator: StationActuator, sinks: DispatchSinks
) -> DecisionLogEntry:
    """Thực thi lệnh đã được duyệt — re-check Guard trên trạng thái MỚI NHẤT trước khi apply.

    Lệnh được dựa lại (rebase) lên phiên bản lịch / thời điểm trạng thái hiện tại: mục đích của lần kiểm
    thứ hai là giới hạn vật lý (nguồn có thể đã giảm trong lúc chờ), không phải chặn vì người duyệt chậm.
    """
    cmd = approval.command.model_copy(
        update={
            "based_on_schedule_version": ctx.state.schedule_version,
            "based_on_state_at": ctx.state.timestamp,
            "created_at": ctx.now,
        }
    )
    verdict = check(cmd, replace(ctx, batch=(cmd,)))
    if not verdict.passed:
        entry = DecisionLogEntry(
            timestamp=ctx.now,
            command=cmd,
            verdict=verdict,
            approval_id=approval.approval_id,
            approved_by=approval.decided_by,
            executed=False,
            note="Đã duyệt nhưng trạng thái trạm đổi — Guard chặn khi kiểm lại",
        )
        sinks.log_decision(entry)
        await sinks.notify(_message(WsMessageType.COMMAND_BLOCKED, entry, ctx.now), None)
        return entry
    actuator.apply_commands([cmd])
    entry = DecisionLogEntry(
        timestamp=ctx.now,
        command=cmd,
        verdict=verdict,
        approval_id=approval.approval_id,
        approved_by=approval.decided_by,
        executed=True,
    )
    sinks.log_decision(entry)
    return entry
