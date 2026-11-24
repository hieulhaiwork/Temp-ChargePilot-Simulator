"""DecisionTrace backend (ADR-019 Phase 4, quyết định 6) — facts cùng schema với simulator, có correlation ID.

Một lần tính lại (`control_loop.on_event`) = một trace:

    mở   (sau dispatch)   trigger + policy / version + state_version + TimeConfig + interval
                          proposed / approved setpoint, consent, đầu vào Physical Guard, budget Coordinator
                          lệnh + phán quyết Guard (7 luật) / HITL / giảm tải ưu tiên, lệnh giữ vì chờ duyệt
    đóng (lần tính lại kế) `decision` = `evaluation/trace.decision_record` của simulator (ĐÚNG schema / facts / binding
                          constraints) dựng từ số đo thật của các bước vật lý đã chạy; `applied` = năng lượng,
                          sạc xong, budget deviation, command deadband, setpoint cũ còn giữ, vi phạm cứng

Không có LLM, không suy diễn: mọi trường là dữ kiện do code tính (AI-4 WHY / WHAT-IF chỉ được đọc). Không ghi
secret, token, resident_id hay dữ liệu cá nhân; chỉ mã booking nội bộ. Live: tóm tắt vào DB (repository, ADR-005),
trace chi tiết là JSONL trong DECISION_TRACE_DIR (nếu đặt). Benchmark / admission: giữ trong bộ nhớ.
"""

import json
import logging
from collections.abc import Iterable, Mapping
from math import inf
from pathlib import Path

from src.guard.dispatcher import SAFETY_REDUCTION_NOTE
from src.guard.physical.validator import guard
from src.models.control import DecisionLogEntry
from src.models.decision_trace import TRACE_SCHEMA, DecisionTraceSummary
from src.models.decisions import ReasonCode
from src.models.events import EventType, StationEvent
from src.models.physical_constraints import ConstraintViolationError
from src.models.physical_limits import EffectiveLimits
from src.models.scheduling.observations import Candidate
from src.models.simulation_core import Cabinet

logger = logging.getLogger(__name__)


def _plain(mapping: Mapping | None) -> dict:
    return {str(k): v for k, v in (mapping or {}).items()}


def _command_row(entry: DecisionLogEntry) -> dict:
    cmd, verdict = entry.command, entry.verdict
    return {
        "command_id": cmd.command_id,
        "type": cmd.type.value,
        "source": cmd.source.value,
        "connector_id": cmd.connector_id,
        "booking_id": cmd.booking_id,
        "power_kw": cmd.power_kw,
        "guard_passed": None if verdict is None else verdict.passed,
        "violations": []
        if verdict is None
        else [{"rule": v.rule.value, "detail": v.detail} for v in verdict.violations],
        "approval_id": entry.approval_id,
        "executed": entry.executed,
        "note": entry.note,
    }


def open_trace(
    rt,
    *,
    correlation_id: str,
    event: StationEvent,
    batch: Iterable[StationEvent],
    plan,
    entries: Iterable[DecisionLogEntry],
    emergency: Iterable[DecisionLogEntry] = (),
    held_for_approval: Iterable[str] = (),
) -> dict:
    """Ghi trace của quyết định vừa ra (chưa có số đo thực thi). Quyết định trước phải được `close_open` trước đó."""
    station = rt.simulator
    scheduler = rt.scheduler
    approved = getattr(scheduler, "last_approved", None)
    diagnostics = getattr(scheduler, "last_diagnostics", {}) or {}
    entries, emergency, batch = list(entries), list(emergency), tuple(batch)
    proposal = approved.proposal if approved is not None else None
    time = getattr(station, "time", None)
    codes = list(approved.reason_codes) if approved is not None else list(diagnostics.get("reason_codes", []))
    if any(e.note.startswith(SAFETY_REDUCTION_NOTE) for e in (*entries, *emergency)):
        codes.append(ReasonCode.LOAD_REDUCTION_PRIORITY)
    trace = {
        "trace_schema": TRACE_SCHEMA,
        "correlation_id": correlation_id,
        "station_id": rt.config.station_id,
        "decided_at": rt.clock().isoformat(),
        "minute": getattr(station, "minute", None),
        "trigger": {
            "type": event.type.value,
            "event_id": event.event_id,
            "batched": [{"type": e.type.value, "event_id": e.event_id} for e in batch],
        },
        "policy": {
            "id": proposal.policy_id if proposal else getattr(getattr(scheduler, "name", None), "value", None),
            "version": proposal.policy_version if proposal else None,
        },
        "state_version": proposal.state_version if proposal else None,
        "schedule_version": plan.version,
        "time_config": time.as_dict() if time is not None else None,
        "interval": None
        if proposal is None
        else {
            "start_minute": proposal.minute,
            "end_minute": proposal.interval_end,
            "planning_interval_minutes": proposal.planning_interval_minutes,
        },
        "reason_codes": codes,
        "budgets_kw": _plain(proposal.budgets.output_kw) if proposal else {},
        "proposed_setpoints_kw": _plain(proposal.setpoints_kw) if proposal else {},
        "approved_setpoints_kw": _plain(approved.setpoints_kw) if approved is not None else {},
        "consent": None
        if approved is None
        else {"adjustments_kw": _plain(approved.adjustments_kw), "rechecked_by_physical_guard": approved.rechecked},
        "guard_inputs": station.guard_inputs(approved) if approved is not None else None,
        "commands": [_command_row(e) for e in entries],
        "emergency_commands": [_command_row(e) for e in emergency],
        "held_for_pending_approval": sorted(set(held_for_approval)),
        # Final Acceptance §1.4: vi phạm cứng sau khi áp đã kích hoạt fail-safe trong lần tính lại này (loại + xe), và
        # booking đang bị giữ an toàn (ngắt công suất vì lỗi charging model / acceptance, chờ vận hành)
        "safety": {
            "hard_limit_violations": [
                {
                    "event_id": e.event_id,
                    "kinds": [str(k) for k in e.violation_kinds],
                    "booking_ids": list(e.violation_booking_ids),
                    "detail": e.detail,
                }
                for e in (*batch, event)
                if e.type == EventType.HARD_LIMIT_VIOLATED
            ],
            "held_booking_ids": sorted(getattr(rt, "safety_hold_booking_ids", ()) or ()),
        },
        "decision": None,
        "applied": None,
        "closed": False,
    }
    rt.open_trace = {"trace": trace, "approved": approved}
    rt.store.save_trace(trace, False)
    return trace


def _applied(results) -> dict:
    deviation, deadband, stale, energy = {}, {}, {}, {}
    completed, violations, details = [], [], []
    for result in results:
        minutes = result.end - result.minute
        for vid, kw in result.actual_kw.items():
            energy[vid] = energy.get(vid, 0.0) + kw * minutes / 60
        for target, source in ((deviation, result.budget_deviation_kw), (deadband, result.command_deadband_kw)):
            for zone, kw in source.items():
                target[zone] = max(target.get(zone, 0.0), kw)
        for vid, kw in result.stale_setpoint_kw.items():
            stale[vid] = max(stale.get(vid, 0.0), kw)
        completed += list(result.completed)
        violations += list(result.violations)
        details += [
            {"minute": result.minute, "kind": v.kind, "vehicle_ids": list(v.vehicle_ids), "message": v.message}
            for v in getattr(result, "hard_violations", ())
        ]
    return {
        "from_minute": results[0].minute if results else None,
        "to_minute": results[-1].end if results else None,
        "minutes": sum(r.end - r.minute for r in results),
        "output_kwh": energy,
        "completed": completed,
        "hard_violations": violations,
        # Final Acceptance §1.4: loại (aggregate_power / charging_model / acceptance) + xe của từng vi phạm cứng
        "hard_violation_details": details,
        "budget_deviation_kw": deviation,
        "budget_deviation_minutes": sum(1 for r in results if r.budget_deviation_kw),
        "command_deadband_kw": deadband,
        "command_deadband_minutes": sum(1 for r in results if r.command_deadband_kw),
        "stale_setpoint_kw": stale,
    }


def close_open(rt) -> dict | None:
    """Đóng trace đang mở bằng số đo thật của các bước vật lý đã chạy dưới quyết định đó."""
    station = rt.simulator
    drain = getattr(station, "drain_applied", None)
    results = drain() if drain is not None else []
    holder, rt.open_trace = rt.open_trace, None
    if holder is None:
        return None
    trace, approved = holder["trace"], holder["approved"]
    applied = _applied(results)
    trace["applied"] = applied
    if approved is not None:
        trace["decision"] = station.decision_facts(approved, results)
    codes = trace["reason_codes"]
    for flag, code in (
        (applied["hard_violations"], ReasonCode.VIOLATION_AFTER_APPLY),
        (applied["budget_deviation_kw"], ReasonCode.BUDGET_DEVIATION),
        (applied["command_deadband_kw"], ReasonCode.COMMAND_DEADBAND),
        (applied["completed"], ReasonCode.CHARGE_COMPLETED),
    ):
        if flag and code not in codes:
            codes.append(code)
    trace["closed"] = True
    rt.store.save_trace(trace, True)
    return trace


def summary(trace: dict) -> DecisionTraceSummary:
    commands = trace["commands"] + trace["emergency_commands"]
    applied = trace.get("applied") or {}
    interval = trace.get("interval") or {}
    return DecisionTraceSummary(
        correlation_id=trace["correlation_id"],
        decided_at=trace["decided_at"],
        trigger=trace["trigger"]["type"],
        policy_id=str(trace["policy"]["id"]),
        policy_version=str(trace["policy"]["version"]),
        state_version=trace["state_version"],
        schedule_version=trace["schedule_version"],
        interval_minutes=interval.get("end_minute", 0) - interval.get("start_minute", 0) if interval else 0,
        applied_minutes=applied.get("minutes", 0),
        reason_codes=list(trace["reason_codes"]),
        commands_total=len(commands),
        commands_executed=sum(1 for c in commands if c["executed"]),
        commands_blocked=sum(1 for c in commands if c["guard_passed"] is False),
        commands_pending_approval=sum(1 for c in commands if c["approval_id"] and not c["executed"]),
        load_reduction_priority=sum(1 for c in commands if c["note"].startswith(SAFETY_REDUCTION_NOTE)),
        budget_deviation_kw_max=max((applied.get("budget_deviation_kw") or {}).values(), default=0.0),
        command_deadband_kw_max=max((applied.get("command_deadband_kw") or {}).values(), default=0.0),
        hard_violations=len(applied.get("hard_violations") or []),
        closed=trace["closed"],
        artifact=trace.get("artifact"),
    )


def persist(trace: dict, closed: bool) -> None:
    """Live: tóm tắt vào DB (mở rồi ghi đè khi đóng); trace đầy đủ thêm vào JSONL ngày khi đã đóng và có thư mục.

    Lỗi ghi trace không được làm hỏng vòng điều khiển: log và bỏ qua.
    """
    from src.config import get_settings
    from src.services import repository

    try:
        directory = get_settings().decision_trace_dir
        if closed and directory:
            name = f"decision-trace-{trace['decided_at'][:10]}.jsonl"
            trace["artifact"] = name
            path = Path(directory)
            path.mkdir(parents=True, exist_ok=True)
            with (path / name).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(trace, ensure_ascii=False, allow_nan=False) + "\n")
        repository.save_decision_trace(summary(trace))
    except Exception:
        logger.exception("decision_trace: không ghi được trace %s", trace.get("correlation_id"))


# ---- replay / debug từ trace (không cần trạm, không cần DB) -------------------------------


def replay_physical_guard(trace: dict, setpoints: Mapping[str, float] | None = None) -> str | None:
    """Chạy lại Physical Guard gốc trên ĐÚNG đầu vào ghi trong trace. None = qua; chuỗi = lý do bị từ chối.

    `setpoints` mặc định = setpoint đã duyệt của trace (truyền khác để hỏi WHAT-IF / tái hiện vi phạm).
    """
    inputs = trace["guard_inputs"]
    if inputs is None:
        return "no approved decision (REJECTED_BEFORE_APPLY)"
    candidates = {
        vid: Candidate(
            Cabinet(row["cabinet"], row["zone"], row["ports"], row["port_kw"], row["cabinet_kw"]), row["allowed_kw"]
        )
        for vid, row in inputs["candidates"].items()
    }
    raw = inputs["limits"]
    limits = EffectiveLimits(
        minute=raw["minute"],
        conversion=raw["conversion"],
        grid_input_kw=inf if raw["grid_input_kw"] is None else raw["grid_input_kw"],
        zone_output_kw=raw["zone_output_kw"],
        cabinet_output_kw=raw["cabinet_output_kw"],
        independent_grid_input_kw=raw["independent_grid_input_kw"],
    )
    plan = trace["approved_setpoints_kw"] if setpoints is None else setpoints
    try:
        guard(None, candidates, plan, inputs["budgets_kw"], limits=limits)
    except ConstraintViolationError as exc:
        return str(exc)
    return None


def replay_commands(trace: dict) -> list[str]:
    """Kiểm lại từ trace: mọi lệnh SET_POWER của optimizer đã thực thi ≤ setpoint đã qua Physical Guard của xe đó."""
    approved = trace["approved_setpoints_kw"]
    problems = []
    for row in trace["commands"]:
        if row["executed"] and row["type"] == "set_power" and row["booking_id"] in approved:
            if row["power_kw"] > approved[row["booking_id"]] + 1e-9:
                problems.append(f"{row['command_id']}: {row['power_kw']} > approved {approved[row['booking_id']]}")
    return problems
