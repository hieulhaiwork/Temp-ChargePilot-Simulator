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
from src.guard.rules import POWER_COMMANDS, GuardContext, check_total_power, is_load_reduction, is_safety_reduction
from src.models.control import Approval, ApprovalKind, Command, DecisionLogEntry, GuardVerdict
from src.models.events import WsMessage, WsMessageType
from src.models.station_protocols import StationActuator

SAFETY_REDUCTION_NOTE = "Giảm tải an toàn"  # tiền tố ghi chú: giảm tải được ưu tiên, không chờ HITL (ADR-019 Phase 4)


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
    notes: dict[int, str] = {}
    held: list[tuple[int, Command, ApprovalKind]] = []
    for i, (cmd, verdict) in enumerate(zip(commands, verdicts, strict=True)):
        if not verdict.passed:
            entry = DecisionLogEntry(timestamp=ctx.now, command=cmd, verdict=verdict, executed=False, note="Guard chặn")
            sinks.log_decision(entry)
            await sinks.notify(_message(WsMessageType.COMMAND_BLOCKED, entry, ctx.now), None)
            entries[i] = entry
            continue
        booking = _booking_for(cmd, ctx)
        kind = approval_rules.requires_approval(cmd, booking)
        if kind is not None and is_safety_reduction(cmd, ctx):
            # Fail-safe (ADR-019 Phase 4, quyết định 3): giảm tải khi trạm đang vượt trần cứng không chờ người duyệt.
            notes[i] = f"{SAFETY_REDUCTION_NOTE} — thực thi ngay, không chờ {kind.value} (trạm đang vượt trần cứng)"
            kind = None
        if kind is None:
            to_apply.append((i, cmd))
            continue
        held.append((i, cmd, kind))
    # Lệnh TĂNG được Guard duyệt với giả định cả lô cùng áp. Lệnh nào của lô không áp (Guard chặn HOẶC giữ chờ duyệt)
    # ⇒ kiểm lại từng lệnh tăng trên đúng tập sẽ áp; lệnh tăng chỉ hợp lệ nhờ một lệnh giảm không được áp thì không áp.
    partial = len(to_apply) < len(commands)
    to_apply, dropped = _without_unsafe_increases(to_apply, ctx) if partial else (to_apply, [])
    for i, cmd, verdict in dropped:
        verdicts[i] = verdict
        entry = DecisionLogEntry(
            timestamp=ctx.now,
            command=cmd,
            verdict=verdict,
            executed=False,
            note="Guard chặn: lệnh tăng phụ thuộc lệnh giảm cùng lô không được áp (bị chặn / chờ phê duyệt)",
        )
        sinks.log_decision(entry)
        await sinks.notify(_message(WsMessageType.COMMAND_BLOCKED, entry, ctx.now), None)
        entries[i] = entry
    for i, cmd, kind in held:
        verdict = verdicts[i]
        booking = _booking_for(cmd, ctx)
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
            entry = DecisionLogEntry(
                timestamp=ctx.now, command=cmd, verdict=verdicts[i], executed=True, note=notes.get(i, "")
            )
            sinks.log_decision(entry)
            entries[i] = entry
    return [e for e in entries if e is not None]


def _without_unsafe_increases(
    to_apply: list[tuple[int, Command]], ctx: GuardContext
) -> tuple[list[tuple[int, Command]], list[tuple[int, Command, GuardVerdict]]]:
    """Giữ mọi lệnh không tăng tải; nhận lần lượt từng lệnh tăng nếu luật tổng công suất vẫn qua trên tập đã nhận."""
    kept = [(i, cmd) for i, cmd in to_apply if cmd.type not in POWER_COMMANDS or is_load_reduction(cmd, ctx)]
    dropped = []
    for i, cmd in to_apply:
        if (i, cmd) in kept:
            continue
        trial = (*(c for _, c in kept), cmd)
        violation = check_total_power(cmd, replace(ctx, batch=trial))
        if violation is None:
            kept.append((i, cmd))
        else:
            verdict = GuardVerdict(command_id=cmd.command_id, passed=False, violations=[violation], checked_at=ctx.now)
            dropped.append((i, cmd, verdict))
    order = {i: n for n, (i, _) in enumerate(to_apply)}
    return sorted(kept, key=lambda item: order[item[0]]), dropped


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
