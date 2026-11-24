"""Deterministic WHY Engine (Phase AI-4.1 — Gate 2 + Remediation G2-F01..G2-F07).

Produces evidence-grounded, authorization-enforced, privacy-projected `WhyAnswer` outputs
for topics: `queue`, `power`, `deadline_risk`, `incident`, `policy`, `overview`.

Hard invariants:
- Strictly read-only: NEVER calls `sync_clock`, `simulator.step`, actuator, or mutating repo APIs.
- Zero LLM usage: all facts, reason codes, and summary templates are 100% deterministic.
- Never conflates observed state, planned assignments, approved power, dispatched commands,
  effective held setpoints, and measured actual output.
- Direct facts strictly match canonical trace values; derived facts declare a finite
  `DerivationOp` and all contributing `input_evidence_refs`.
- Never fabricates measured facts from active traces, substitutes 0 for missing readings,
  leaks future completions into earlier `at` queries, or uses silent efficiency defaults.
- Never attributes station-level violations to a vehicle without subject-specific evidence,
  nor emits `NO_INCIDENT_OBSERVED` when evidence is active, incomplete, or un-evaluated.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

from src.models.charging import Booking
from src.models.control import Role
from src.models.copilot import (
    SUPPORTED_WHY_TOPICS,
    ActorContext,
    DerivationOp,
    EvidenceCategory,
    FactDerivationKind,
    FactStage,
    TemporalBasis,
    TimeWindow,
    WhyAnswer,
    WhyQuery,
    WhyStatus,
    WhySubjectScope,
    WhyTopic,
)
from src.models.physical_constraints import TOL
from src.services import catalog, repository
from src.services.copilot.evidence import (
    EvidenceCollector,
    authorize_why_query,
    encode_pointer_token,
    verify_privacy_projection,
)
from src.services.copilot.trace_reader import (
    ResolvedTrace,
    SampleSlice,
    extract_measured_slice,
    fetch_temporal_traces,
    parse_iso_aware,
    resolve_traces_from_records,
)

# Verified coordinator reason codes mapped strictly from src/optimizer/coordination/{fixed_budget,dynamic_slack}.py
_KNOWN_COORDINATOR_REASONS: dict[tuple[str, str], tuple[str, str]] = {
    ("fixed_share", "fixed_share"): (
        "COORDINATOR_FIXED_SHARE",
        "Bộ điều phối fixed_share phân bổ theo ngân sách vùng cố định {zone}.",
    ),
    ("fixed_budget", "fixed_share"): (
        "COORDINATOR_FIXED_SHARE",
        "Bộ điều phối fixed_budget phân bổ theo ngân sách vùng cố định {zone}.",
    ),
    ("fixed_share", "source_limited"): (
        "COORDINATOR_SOURCE_LIMITED",
        "Ngân sách vùng {zone} bị giảm tỷ lệ do giới hạn nguồn điện hiệu lực.",
    ),
    ("fixed_budget", "source_limited"): (
        "COORDINATOR_SOURCE_LIMITED",
        "Ngân sách vùng {zone} bị giảm tỷ lệ do giới hạn nguồn điện hiệu lực.",
    ),
    ("dynamic_slack", "deadline_headroom"): (
        "COORDINATOR_DEADLINE_HEADROOM",
        "Bộ điều phối dynamic_slack cấp ưu tiên vùng {zone} theo nhu cầu sát hạn (deadline_headroom).",
    ),
    ("dynamic_slack", "fixed_reservation"): (
        "COORDINATOR_FIXED_RESERVATION",
        "Bộ điều phối dynamic_slack giữ phần ngân sách dự trữ cố định cho vùng {zone}.",
    ),
    ("dynamic_slack", "shared_slack"): (
        "COORDINATOR_SHARED_SLACK",
        "Bộ điều phối dynamic_slack chia phần công suất dư của nguồn chung cho vùng {zone}.",
    ),
    ("dynamic_slack", "independent_supply"): (
        "COORDINATOR_INDEPENDENT_SUPPLY",
        "Chế độ nguồn độc lập: vùng {zone} dùng riêng giới hạn nguồn của mình, không chuyển ngân sách xuyên vùng.",
    ),
    ("dynamic_slack", "no_connected_demand"): (
        "COORDINATOR_NO_CONNECTED_DEMAND",
        "Vùng {zone} không có nhu cầu công suất từ xe đang cắm ở khoảng này.",
    ),
    ("dynamic_slack", "shared_supply_scarcity"): (
        "COORDINATOR_SHARED_SUPPLY_SCARCITY",
        "Nguồn chung khan hiếm: ngân sách vùng {zone} thấp hơn nhu cầu khả dụng của vùng.",
    ),
    ("dynamic_slack", "effective_capacity_bound"): (
        "COORDINATOR_EFFECTIVE_CAPACITY_BOUND",
        "Công suất khả dụng của vùng {zone} bị chặn bởi trần tủ/vùng hiệu lực.",
    ),
}


def _live_open_trace_state() -> tuple[str | None, bool, datetime | None]:
    """Read-only peek at in-memory live runtime's open_trace and physics clock without stepping.

    G2-F04: When `runtime._live is None` (e.g., fresh process after restart before runtime init),
    we KNOW there is no live open trace in this process (`live_known=True, cid=None`), so any
    unclosed active trace left in DB is immediately classified as `stale_after_restart=True`.
    """
    from src.services import runtime

    live = getattr(runtime, "_live", None)
    if live is None:
        return None, True, None
    holder = getattr(live, "open_trace", None)
    sim = getattr(live, "simulator", None)
    sim_now = getattr(sim, "now", None) if sim is not None else None
    if isinstance(sim_now, datetime) and (sim_now.tzinfo is None or sim_now.utcoffset() is None):
        sim_now = None
    if not isinstance(holder, dict):
        return None, True, sim_now if isinstance(sim_now, datetime) else None
    trace = holder.get("trace")
    cid = trace.get("correlation_id") if isinstance(trace, dict) else None
    return cid, True, sim_now if isinstance(sim_now, datetime) else None


def _seg(value: str) -> str:
    return encode_pointer_token(value)


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC)


def explain_why(
    query: WhyQuery,
    actor: ActorContext,
    *,
    station_id: str | None = None,
    live_open_correlation_id: str | None = None,
    live_open_known: bool | None = None,
    live_physics_clock: datetime | None = None,
    raw_traces: Sequence[dict] | None = None,
    legacy_summary_only_count: int = 0,
    bookings_override: Mapping[str, Booking] | None = None,
) -> WhyAnswer:
    """Deterministic, read-only WHY Engine entry point."""
    resolved_station_id = station_id or catalog.load_station_config().station_id

    if bookings_override is not None:
        get_booking = bookings_override.get
        active_booking = lambda rid: next(  # noqa: E731
            (
                b
                for b in bookings_override.values()
                if b.resident_id == rid and b.status.value in ("confirmed", "queued", "charging")
            ),
            None,
        )
        list_resident = lambda rid: [b for b in bookings_override.values() if b.resident_id == rid]  # noqa: E731
    else:
        get_booking = repository.get_booking
        active_booking = repository.active_booking
        list_resident = lambda rid: repository.list_bookings(resident_id=rid)  # noqa: E731

    auth = authorize_why_query(
        query,
        actor,
        station_id=resolved_station_id,
        get_booking=get_booking,
        active_booking=active_booking,
        list_resident_bookings=list_resident,
    )
    if not auth.allowed:
        return WhyAnswer(
            status=auth.status,
            topic=query.topic,
            subject_scope=query.subject_scope,
            subject_id=auth.subject_id,
            query_at=query.at,
            query_window=query.window,
            missing_evidence=list(auth.missing_evidence),
        )

    if query.topic not in SUPPORTED_WHY_TOPICS:
        return WhyAnswer(
            status=WhyStatus.UNSUPPORTED,
            topic=query.topic,
            subject_scope=query.subject_scope,
            subject_id=auth.subject_id,
            query_at=query.at,
            query_window=query.window,
            missing_evidence=[f"unsupported_topic:{query.topic}"],
        )

    if live_open_known is None:
        live_cid, live_known, detected_clock = _live_open_trace_state()
        live_clock = live_physics_clock if live_physics_clock is not None else detected_clock
    else:
        live_cid, live_known, live_clock = live_open_correlation_id, live_open_known, live_physics_clock

    booking_filter = auth.subject_id if query.subject_scope != WhySubjectScope.STATION else None
    if raw_traces is not None:
        # Preserve station-wide timeline metadata even when filtering raw_traces by booking_id (G2-F04)
        station_timeline = [
            {
                "correlation_id": t.get("correlation_id"),
                "decided_at": t.get("decided_at"),
                "schedule_version": t.get("schedule_version", 0),
            }
            for t in raw_traces
            if t.get("station_id") == resolved_station_id and t.get("decided_at")
        ]
        candidates = (
            [t for t in raw_traces if booking_filter in (t.get("booking_ids") or ())]
            if booking_filter is not None
            else list(raw_traces)
        )
        resolution = resolve_traces_from_records(
            candidates,
            at=query.at,
            window=query.window,
            station_id=resolved_station_id,
            limit=query.limit,
            cursor=query.cursor,
            legacy_summary_only_count=legacy_summary_only_count,
            station_timeline=station_timeline,
            live_open_correlation_id=live_cid,
            live_open_known=live_known,
            live_physics_clock=live_clock,
        )
    else:
        resolution = fetch_temporal_traces(
            at=query.at,
            window=query.window,
            booking_id=booking_filter,
            station_id=resolved_station_id,
            limit=query.limit,
            cursor=query.cursor,
            live_open_correlation_id=live_cid,
            live_open_known=live_known,
            live_physics_clock=live_clock,
        )

    if not resolution.traces:
        missing = list(resolution.missing_evidence)
        if "no_matching_decision_trace" not in missing:
            missing.append("no_matching_decision_trace")
        return WhyAnswer(
            status=WhyStatus.NO_DATA,
            topic=query.topic,
            subject_scope=query.subject_scope,
            subject_id=auth.subject_id,
            query_at=query.at,
            query_window=query.window,
            missing_evidence=missing,
            truncated=resolution.truncated,
            next_cursor=resolution.next_cursor,
        )

    collector = EvidenceCollector(actor, authorized_subject=auth.authorized_subject)
    for miss in resolution.missing_evidence:
        collector.add_missing(miss)

    topic = WhyTopic(query.topic)
    is_station = query.subject_scope == WhySubjectScope.STATION
    subject_id = auth.subject_id or resolved_station_id

    for resolved in resolution.traces:
        sample_slice = (
            extract_measured_slice(resolved, at=query.at, window=query.window) if resolved.provenance.closed else None
        )
        _annotate_trace_limitations(resolved, sample_slice, collector)
        if is_station:
            _explain_station_trace(
                topic,
                resolved,
                sample_slice,
                resolved_station_id,
                collector,
                has_temporal_gap=resolution.has_temporal_gap,
            )
        else:
            _explain_booking_trace(
                topic,
                resolved,
                sample_slice,
                subject_id,
                actor.role,
                auth.booking,
                collector,
                query_at=query.at,
                query_window=query.window,
                has_temporal_gap=resolution.has_temporal_gap,
            )

    status = _determine_status(resolution, collector)
    provenances = [r.provenance for r in resolution.traces]
    single = provenances[0] if len(provenances) == 1 else None
    unique_policies = {(p.policy_id, p.policy_version) for p in provenances}
    common_policy = next(iter(unique_policies)) if len(unique_policies) == 1 else (None, None)

    answer = WhyAnswer(
        status=status,
        topic=query.topic,
        subject_scope=query.subject_scope,
        subject_id=auth.subject_id,
        query_at=query.at,
        query_window=query.window,
        decision_time=single.decided_at if single is not None else None,
        policy_id=common_policy[0],
        policy_version=common_policy[1],
        state_version=single.state_version if single is not None else None,
        traces=provenances,
        facts=collector.facts,
        reasons=collector.reasons,
        evidence_refs=collector.evidence_refs,
        assumptions=collector.assumptions,
        missing_evidence=collector.missing_evidence,
        truncated=resolution.truncated,
        next_cursor=resolution.next_cursor,
    )
    verify_privacy_projection(answer, actor, resolution.traces, authorized_subject=auth.authorized_subject)
    return answer


def _annotate_trace_limitations(
    resolved: ResolvedTrace, sample_slice: SampleSlice | None, collector: EvidenceCollector
) -> None:
    prov = resolved.provenance
    trace = resolved.payload
    if not prov.closed:
        collector.add_missing("active_trace_no_measured_data")
        collector.add_assumption(
            "Trace đang mở (active): chỉ có dữ kiện tại thời điểm quyết định, chưa có số đo thực tế."
        )
    if resolved.exceeds_live_physics_clock:
        collector.add_missing("query_exceeds_live_physics_clock")
        collector.add_assumption(
            "Thời điểm truy vấn nằm trong khoảng kế hoạch nhưng vượt quá đồng hồ vật lý hiện tại; "
            "các dữ kiện tương lai chỉ mang tính kế hoạch (planned), chưa phải quan sát/đo đạc đã xác nhận."
        )
    if prov.stale_after_restart:
        collector.add_missing("stale_active_trace_unclosed_after_restart")
        collector.add_assumption(
            "Trace active cũ còn lại sau khởi động lại tiến trình; không suy diễn số đo sau mốc này."
        )
    if prov.coverage_status == "incomplete":
        collector.add_missing("incomplete_measured_coverage")
        collector.add_assumption(
            "Dữ liệu mẫu đo không đầy đủ (có mẫu bị loại bỏ hoặc gián đoạn); không ngoại suy toàn khoảng."
        )
    elif prov.closed and prov.post_apply_status == "no_samples":
        collector.add_missing("no_measured_samples")
    if trace.get("planned") is None and trace.get("decision") is None:
        collector.add_missing("planned_diagnostics_unavailable")
    if sample_slice is not None:
        if sample_slice.has_partial_overlap:
            collector.add_assumption(
                "Giả định công suất không đổi từng đoạn (piecewise-constant) trong mỗi mẫu đo khi tích phân theo khoảng giao chính xác."
            )
        if sample_slice.overlapping_samples_detected:
            collector.add_missing("overlapping_measured_samples_deduplicated")
            collector.add_assumption(
                "Phát hiện mẫu đo trùng/giao nhau; đã cắt lọc khoảng giao để tránh cộng trùng năng lượng."
            )
        if sample_slice.is_subwindow and not sample_slice.samples and prov.closed:
            collector.add_missing("no_retained_samples_in_subwindow")
        if sample_slice.is_subwindow and sample_slice.samples and not sample_slice.complete_for_window:
            collector.add_missing("incomplete_subwindow_sample_coverage")


def _determine_status(resolution, collector: EvidenceCollector) -> WhyStatus:
    if not collector.facts and not collector.reasons:
        return WhyStatus.NO_DATA
    partial_triggers = {
        "temporal_gap_in_window",
        "trace_window_truncated",
        "incomplete_measured_coverage",
        "incomplete_subwindow_sample_coverage",
        "no_retained_samples_in_subwindow",
        "stale_active_trace_unclosed_after_restart",
        "legacy_summary_only_trace",
        "planned_diagnostics_unavailable",
        "query_exceeds_available_evidence",
        "query_exceeds_live_physics_clock",
        "active_trace_no_measured_data",
        "missing_conversion_efficiency_evidence",
        "missing_charging_efficiency_evidence",
        "completion_timestamp_unknown_for_as_of_query",
        "insufficient_evidence_to_confirm_no_incident",
    }
    if (
        resolution.truncated
        or resolution.has_temporal_gap
        or resolution.exceeds_live_physics_clock
        or any(m in partial_triggers for m in collector.missing_evidence)
    ):
        return WhyStatus.PARTIAL
    return WhyStatus.OK


# ---- Shared helpers ----------------------------------------------------------------------


def _planned_vehicle(trace: dict, booking_id: str) -> tuple[dict | None, str]:
    planned = trace.get("planned")
    if isinstance(planned, dict):
        vehicles = (planned.get("observed") or {}).get("vehicles") or {}
        if booking_id in vehicles:
            return vehicles[booking_id], f"/planned/observed/vehicles/{_seg(booking_id)}"
    return None, ""


def _booking_cabinet(planned: dict, vrow: dict) -> str | None:
    conn = vrow.get("connector_id") or vrow.get("planned_assigned_connector")
    if not conn:
        return None
    port_row = ((planned.get("observed") or {}).get("ports") or {}).get(conn)
    return port_row.get("cabinet_id") if isinstance(port_row, dict) else None


def _resolve_charging_efficiency(trace: dict) -> tuple[float | None, str | None]:
    """Return decision-time charging efficiency and canonical pointer, NEVER a silent default (G2-F06)."""
    planned_limits = (trace.get("planned") or {}).get("physical_limits") or {}
    val = planned_limits.get("charging_efficiency")
    if isinstance(val, (int, float)) and val > 0:
        return float(val), "/planned/physical_limits/charging_efficiency"
    decision_limits = (trace.get("decision") or {}).get("physical_limits") or {}
    val = decision_limits.get("charging_efficiency")
    if isinstance(val, (int, float)) and val > 0:
        return float(val), "/decision/physical_limits/charging_efficiency"
    return None, None


def _can_confirm_no_incident(resolved: ResolvedTrace, *, has_temporal_gap: bool) -> bool:
    """G2-F05 #4: Only assert NO_INCIDENT_OBSERVED when evidence is closed, complete, evaluated, and contiguous."""
    prov = resolved.provenance
    return (
        prov.closed
        and prov.post_apply_status == "pass"
        and prov.coverage_status == "complete"
        and not prov.stale_after_restart
        and not resolved.exceeds_live_physics_clock
        and resolved.payload.get("planned") is not None
        and not has_temporal_gap
    )


def _add_command_guard_and_approval_facts(
    resolved: ResolvedTrace,
    *,
    key: str,
    idx: int,
    row: dict,
    booking_id: str,
    collector: EvidenceCollector,
) -> tuple[list, list]:
    """G2-F05 #5/#6: Emit direct verdict/rule/approval facts so blocked/pending reasons are fully grounded."""
    guard_facts = []
    approval_facts = []
    if row.get("guard_passed") is False:
        f_gp = collector.add_fact(
            resolved,
            name="dispatch.command_guard_passed",
            subject=booking_id,
            stage=FactStage.DISPATCHED,
            value=False,
            unit=None,
            source_path=f"/{key}/{idx}/guard_passed",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_gp is not None:
            guard_facts.append(f_gp)
        for v_idx, viol in enumerate(row.get("violations") or []):
            if isinstance(viol, dict) and "rule" in viol:
                f_rule = collector.add_fact(
                    resolved,
                    name="dispatch.business_guard_rule",
                    subject=booking_id,
                    stage=FactStage.DISPATCHED,
                    value=viol["rule"],
                    unit=None,
                    source_path=f"/{key}/{idx}/violations/{v_idx}/rule",
                    time_scope=TemporalBasis.DECISION_SNAPSHOT,
                )
                if f_rule is not None:
                    guard_facts.append(f_rule)
    if row.get("approval_id") and not row.get("executed"):
        f_appr = collector.add_fact(
            resolved,
            name="dispatch.command_approval_id",
            subject=booking_id,
            stage=FactStage.DISPATCHED,
            value=row["approval_id"],
            unit=None,
            source_path=f"/{key}/{idx}/approval_id",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_appr is not None:
            approval_facts.append(f_appr)
    return guard_facts, approval_facts


# ---- Booking-scoped explainers (Resident or Operator) ------------------------------------


def _explain_booking_trace(
    topic: WhyTopic,
    resolved: ResolvedTrace,
    sample_slice: SampleSlice | None,
    booking_id: str,
    role: Role,
    booking: Booking | None,
    collector: EvidenceCollector,
    *,
    query_at: datetime | None,
    query_window: TimeWindow | None,
    has_temporal_gap: bool,
) -> None:
    if topic == WhyTopic.QUEUE:
        _explain_booking_queue(resolved, booking_id, booking, collector)
    elif topic == WhyTopic.POWER:
        _explain_booking_power(resolved, sample_slice, booking_id, collector)
    elif topic == WhyTopic.DEADLINE_RISK:
        _explain_booking_deadline_risk(
            resolved, booking_id, booking, collector, query_at=query_at, query_window=query_window
        )
    elif topic == WhyTopic.INCIDENT:
        _explain_booking_incident(resolved, booking_id, role, collector, has_temporal_gap=has_temporal_gap)
    elif topic == WhyTopic.POLICY:
        _explain_policy(resolved, booking_id, booking, collector, is_station=False)
    elif topic == WhyTopic.OVERVIEW:
        _explain_booking_queue(resolved, booking_id, booking, collector)
        _explain_booking_power(resolved, sample_slice, booking_id, collector)
        _explain_booking_deadline_risk(
            resolved, booking_id, booking, collector, query_at=query_at, query_window=query_window
        )
        _explain_booking_incident(
            resolved, booking_id, role, collector, emit_no_incident=False, has_temporal_gap=has_temporal_gap
        )


def _explain_booking_queue(
    resolved: ResolvedTrace,
    booking_id: str,
    booking: Booking | None,
    collector: EvidenceCollector,
) -> None:
    trace = resolved.payload
    planned = trace.get("planned") if isinstance(trace.get("planned"), dict) else None
    vrow, vpath = _planned_vehicle(trace, booking_id)
    zone = vrow["zone"] if vrow else (str(booking.request.zone) if booking else None)
    p_start, p_end = resolved.planned_start, resolved.planned_end

    # G2-F03: Decision-time observation snapshots have time_scope=DECISION_SNAPSHOT (interval=None)
    state_fact = conn_fact = pos_fact = None
    if vrow is not None:
        state_fact = collector.add_fact(
            resolved,
            name="vehicle.observed_state",
            subject=booking_id,
            stage=FactStage.OBSERVED,
            value=vrow.get("state"),
            unit=None,
            source_path=f"{vpath}/state",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        conn_fact = collector.add_fact(
            resolved,
            name="vehicle.observed_connector",
            subject=booking_id,
            stage=FactStage.OBSERVED,
            value=vrow.get("connector_id"),
            unit=None,
            source_path=f"{vpath}/connector_id",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if vrow.get("queue_position") is not None:
            pos_fact = collector.add_fact(
                resolved,
                name="queue.observed_position",
                subject=booking_id,
                stage=FactStage.OBSERVED,
                value=vrow["queue_position"],
                unit="rank",
                source_path=f"{vpath}/queue_position",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )

    zone_sum = ((planned or {}).get("observed") or {}).get("zone_summary", {}).get(zone) if zone else None
    empty_fact = fault_fact = waiting_fact = policy_fact = None
    if zone and zone_sum is not None:
        zpath = f"/planned/observed/zone_summary/{_seg(zone)}"
        empty_fact = collector.add_fact(
            resolved,
            name="queue.zone_empty_ports",
            subject=zone,
            stage=FactStage.OBSERVED,
            value=zone_sum["empty_ports"],
            unit="count",
            source_path=f"{zpath}/empty_ports",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        fault_fact = collector.add_fact(
            resolved,
            name="queue.zone_faulted_ports",
            subject=zone,
            stage=FactStage.OBSERVED,
            value=zone_sum["faulted_ports"],
            unit="count",
            source_path=f"{zpath}/faulted_ports",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        waiting_fact = collector.add_fact(
            resolved,
            name="queue.zone_waiting_count",
            subject=zone,
            stage=FactStage.OBSERVED,
            value=zone_sum["waiting_count"],
            unit="count",
            source_path=f"{zpath}/waiting_count",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        collector.add_fact(
            resolved,
            name="queue.zone_occupied_ports",
            subject=zone,
            stage=FactStage.OBSERVED,
            value=zone_sum["occupied_ports"],
            unit="count",
            source_path=f"{zpath}/occupied_ports",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        dpolicy = ((planned or {}).get("dispatch") or {}).get(zone, {}).get("policy")
        if dpolicy:
            policy_fact = collector.add_fact(
                resolved,
                name="dispatch.policy",
                subject=zone,
                stage=FactStage.CONFIG,
                value=dpolicy,
                unit=None,
                source_path=f"/planned/dispatch/{_seg(zone)}/policy",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )

    planned_conn = vrow.get("planned_assigned_connector") if vrow else None
    planned_assign_fact = None
    if vrow is not None and planned_conn is not None:
        planned_assign_fact = collector.add_fact(
            resolved,
            name="dispatch.planned_assigned_connector",
            subject=booking_id,
            stage=FactStage.PLANNED,
            value=planned_conn,
            unit=None,
            source_path=f"{vpath}/planned_assigned_connector",
            time_scope=TemporalBasis.PLANNED_INTERVAL,
            interval_start=p_start,
            interval_end=p_end,
        )

    assign_cmds = [
        (idx, row)
        for idx, row in enumerate(trace.get("commands") or [])
        if row.get("booking_id") == booking_id and row.get("type") == "assign_connector"
    ]
    assign_exclusions = [
        (idx, row)
        for idx, row in enumerate(trace.get("command_exclusions") or [])
        if row.get("booking_id") == booking_id and row.get("type") == "assign_connector"
    ]

    executed_assign = None
    for idx, row in assign_cmds:
        f_exec = collector.add_fact(
            resolved,
            name="dispatch.assign_command_executed",
            subject=booking_id,
            stage=FactStage.DISPATCHED,
            value=bool(row.get("executed")),
            unit=None,
            source_path=f"/commands/{idx}/executed",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if row.get("executed"):
            executed_assign = (f_exec, row)
        else:
            guard_facts, approval_facts = _add_command_guard_and_approval_facts(
                resolved, key="commands", idx=idx, row=row, booking_id=booking_id, collector=collector
            )
            if row.get("guard_passed") is False:
                all_f = [f for f in (planned_assign_fact, f_exec, *guard_facts) if f is not None]
                rules = ", ".join(v.get("rule", "unknown") for v in (row.get("violations") or []))
                collector.add_reason(
                    resolved,
                    code="PLANNED_ASSIGNMENT_BLOCKED_BY_GUARD",
                    category=EvidenceCategory.OBSERVED,
                    subject=booking_id,
                    fact_refs=[f.fact_id for f in all_f],
                    evidence_refs=[f.evidence_ref for f in all_f],
                    template_key="queue.assign_blocked_guard",
                    params={"connector_id": row.get("connector_id"), "rules": rules},
                    summary=f"Lệnh gán cổng {row.get('connector_id')} đã lập kế hoạch nhưng bị Business Guard chặn ({rules}); xe chưa kết nối.",
                )
            elif row.get("approval_id"):
                all_f = [f for f in (planned_assign_fact, f_exec, *approval_facts) if f is not None]
                collector.add_reason(
                    resolved,
                    code="PLANNED_ASSIGNMENT_PENDING_APPROVAL",
                    category=EvidenceCategory.OBSERVED,
                    subject=booking_id,
                    fact_refs=[f.fact_id for f in all_f],
                    evidence_refs=[f.evidence_ref for f in all_f],
                    template_key="queue.assign_pending_approval",
                    params={
                        "connector_id": row.get("connector_id"),
                        "approval_id": row.get("approval_id"),
                        "decision_time_only": True,
                    },
                    summary=(
                        f"Tại thời điểm quyết định, lệnh gán cổng {row.get('connector_id')} chờ phê duyệt "
                        f"({row.get('approval_id')}); xe chưa kết nối (không phản ánh trạng thái phê duyệt hiện tại)."
                    ),
                )
                collector.add_assumption(
                    "Trạng thái chờ phê duyệt phản ánh thời điểm quyết định, không khẳng định trạng thái phê duyệt hiện tại."
                )

    for idx, row in assign_exclusions:
        f_excl = collector.add_fact(
            resolved,
            name="dispatch.assign_excluded_reason",
            subject=booking_id,
            stage=FactStage.DISPATCHED,
            value=row.get("primary_reason"),
            unit=None,
            source_path=f"/command_exclusions/{idx}/primary_reason",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_excl is not None:
            f_refs = [f.fact_id for f in (planned_assign_fact, f_excl) if f is not None]
            e_refs = [f.evidence_ref for f in (planned_assign_fact, f_excl) if f is not None]
            collector.add_reason(
                resolved,
                code=f"PLANNED_ASSIGNMENT_EXCLUDED_{row.get('primary_reason')}",
                category=EvidenceCategory.OBSERVED,
                subject=booking_id,
                fact_refs=f_refs,
                evidence_refs=e_refs,
                template_key="queue.assign_excluded",
                params={"connector_id": row.get("connector_id"), "primary_reason": row.get("primary_reason")},
                summary=f"Lệnh gán cổng {row.get('connector_id')} bị loại trước khi gửi do {row.get('primary_reason')}; xe chưa kết nối.",
            )

    if executed_assign is not None:
        f_exec, row = executed_assign
        f_refs = [f.fact_id for f in (planned_assign_fact, f_exec) if f is not None]
        e_refs = [f.evidence_ref for f in (planned_assign_fact, f_exec) if f is not None]
        collector.add_reason(
            resolved,
            code="ASSIGNMENT_DISPATCHED",
            category=EvidenceCategory.OBSERVED,
            subject=booking_id,
            fact_refs=f_refs,
            evidence_refs=e_refs,
            template_key="queue.assign_dispatched",
            params={"connector_id": row.get("connector_id")},
            summary=f"Lệnh gán cổng {row.get('connector_id')} đã được thực thi qua dispatcher.",
        )
    elif planned_assign_fact is not None and not assign_cmds and not assign_exclusions:
        collector.add_reason(
            resolved,
            code="PLANNED_ASSIGNMENT_NOT_DISPATCHED",
            category=EvidenceCategory.OBSERVED,
            subject=booking_id,
            fact_refs=[planned_assign_fact.fact_id],
            evidence_refs=[planned_assign_fact.evidence_ref],
            template_key="queue.assign_not_dispatched",
            params={"connector_id": planned_conn},
            summary=f"Bộ lập lịch dự kiến gán cổng {planned_conn} nhưng chưa có lệnh gán được thực thi trong trace (không khẳng định xe đã kết nối).",
        )

    if vrow is not None and vrow.get("state") == "QUEUED" and executed_assign is None:
        if empty_fact is not None and empty_fact.value == 0:
            f_refs = [f.fact_id for f in (state_fact, pos_fact, empty_fact, fault_fact) if f is not None]
            e_refs = [f.evidence_ref for f in (state_fact, pos_fact, empty_fact, fault_fact) if f is not None]
            collector.add_reason(
                resolved,
                code="NO_FREE_COMPATIBLE_PORT",
                category=EvidenceCategory.OBSERVED,
                subject=booking_id,
                fact_refs=f_refs,
                evidence_refs=e_refs,
                template_key="queue.no_free_port",
                params={"zone": zone, "faulted_ports": fault_fact.value if fault_fact else 0},
                summary=f"Xe đang chờ vì vùng {zone} không còn cổng tương thích trống ở thời điểm quyết định.",
            )
            if fault_fact is not None and int(fault_fact.value or 0) > 0:
                collector.add_reason(
                    resolved,
                    code="COMPATIBLE_PORT_FAULTED",
                    category=EvidenceCategory.OBSERVED,
                    subject=booking_id,
                    fact_refs=[fault_fact.fact_id],
                    evidence_refs=[fault_fact.evidence_ref],
                    template_key="queue.port_faulted",
                    params={"zone": zone, "faulted_ports": fault_fact.value},
                    summary=f"Vùng {zone} hiện có {fault_fact.value} đầu nối đang lỗi, làm giảm số cổng khả dụng.",
                )
        elif empty_fact is not None and int(empty_fact.value or 0) > 0 and planned_assign_fact is None:
            f_refs = [f.fact_id for f in (state_fact, pos_fact, empty_fact, waiting_fact, policy_fact) if f is not None]
            e_refs = [
                f.evidence_ref for f in (state_fact, pos_fact, empty_fact, waiting_fact, policy_fact) if f is not None
            ]
            lax = ((planned or {}).get("dc_waiting_laxity") or {}).get(booking_id)
            if lax is not None:
                f_lax = collector.add_fact(
                    resolved,
                    name="queue.optimistic_laxity_minutes",
                    subject=booking_id,
                    stage=FactStage.PLANNED,
                    value=lax.get("optimistic_laxity_minutes"),
                    unit="minutes",
                    source_path=f"/planned/dc_waiting_laxity/{_seg(booking_id)}/optimistic_laxity_minutes",
                    time_scope=TemporalBasis.DECISION_SNAPSHOT,
                )
                if f_lax is not None:
                    f_refs.append(f_lax.fact_id)
                    e_refs.append(f_lax.evidence_ref)
            dpol_val = policy_fact.value if policy_fact else "unknown"
            collector.add_reason(
                resolved,
                code="NOT_SELECTED_BY_DISPATCH_POLICY",
                category=EvidenceCategory.POLICY_REASON,
                subject=booking_id,
                fact_refs=f_refs,
                evidence_refs=e_refs,
                template_key="queue.not_selected_policy",
                params={"zone": zone, "dispatch_policy": dpol_val, "empty_ports": empty_fact.value},
                summary=(
                    f"Cổng trống vùng {zone} ({empty_fact.value}) được phân bổ theo chính sách dispatch '{dpol_val}'; "
                    "trace không ghi điểm xếp hạng đầy đủ của các xe khác nên chỉ báo trạng thái và chính sách."
                ),
            )
    elif vrow is not None and vrow.get("connector_id") is not None and state_fact is not None and conn_fact is not None:
        collector.add_reason(
            resolved,
            code="VEHICLE_ALREADY_CONNECTED",
            category=EvidenceCategory.OBSERVED,
            subject=booking_id,
            fact_refs=[state_fact.fact_id, conn_fact.fact_id],
            evidence_refs=[state_fact.evidence_ref, conn_fact.evidence_ref],
            template_key="queue.already_connected",
            params={"connector_id": vrow["connector_id"], "state": vrow.get("state")},
            summary=f"Xe đang kết nối tại đầu nối {vrow['connector_id']} (trạng thái quan sát: {vrow.get('state')}).",
        )


def _explain_booking_power(
    resolved: ResolvedTrace,
    sample_slice: SampleSlice | None,
    booking_id: str,
    collector: EvidenceCollector,
) -> None:
    trace = resolved.payload
    planned = trace.get("planned") if isinstance(trace.get("planned"), dict) else None
    power = trace.get("power") or {}
    vrow, vpath = _planned_vehicle(trace, booking_id)
    zone = vrow["zone"] if vrow else None
    p_start, p_end = resolved.planned_start, resolved.planned_end

    # 1. Proposed & Approved setpoints (direct facts with planned interval)
    proposed_map = (power.get("proposed") or {}).get("by_booking_kw") or {}
    approved_map = (power.get("approved") or {}).get("by_booking_kw") or {}
    f_prop = f_appr = None
    if booking_id in proposed_map:
        f_prop = collector.add_fact(
            resolved,
            name="power.proposed_output_kw",
            subject=booking_id,
            stage=FactStage.PLANNED,
            value=proposed_map[booking_id],
            unit="kW",
            source_path=f"/power/proposed/by_booking_kw/{_seg(booking_id)}",
            time_scope=TemporalBasis.PLANNED_INTERVAL,
            interval_start=p_start,
            interval_end=p_end,
        )
    if booking_id in approved_map:
        f_appr = collector.add_fact(
            resolved,
            name="power.approved_output_kw",
            subject=booking_id,
            stage=FactStage.APPROVED,
            value=approved_map[booking_id],
            unit="kW",
            source_path=f"/power/approved/by_booking_kw/{_seg(booking_id)}",
            time_scope=TemporalBasis.PLANNED_INTERVAL,
            interval_start=p_start,
            interval_end=p_end,
        )

    consent_adj = ((trace.get("consent") or {}).get("adjustments_kw") or {}).get(booking_id)
    if consent_adj is not None:
        f_adj = collector.add_fact(
            resolved,
            name="power.consent_forced_min_kw",
            subject=booking_id,
            stage=FactStage.APPROVED,
            value=consent_adj,
            unit="kW",
            source_path=f"/consent/adjustments_kw/{_seg(booking_id)}",
            time_scope=TemporalBasis.PLANNED_INTERVAL,
            interval_start=p_start,
            interval_end=p_end,
        )
        if f_adj is not None:
            collector.add_reason(
                resolved,
                code="CONSENT_MINIMUM_START_ADJUSTMENT",
                category=EvidenceCategory.POLICY_REASON,
                subject=booking_id,
                fact_refs=[f.fact_id for f in (f_prop, f_appr, f_adj) if f is not None],
                evidence_refs=[f.evidence_ref for f in (f_prop, f_appr, f_adj) if f is not None],
                template_key="power.consent_adjusted",
                params={"forced_kw": consent_adj},
                summary=f"Công suất được điều chỉnh theo consent max_start_delay tối thiểu {consent_adj:g} kW và đã qua Physical Guard kiểm lại.",
            )

    # 2. Dispatched commands, Business Guard blocks, Pending Approvals, and Command Exclusions
    for key, is_emergency in (("emergency_commands", True), ("commands", False)):
        for idx, row in enumerate(trace.get(key) or []):
            if row.get("booking_id") != booking_id:
                continue
            if row.get("type") not in ("set_power", "stop"):
                continue
            if row.get("power_kw") is not None:
                f_cmd = collector.add_fact(
                    resolved,
                    name="power.emergency_dispatched_kw" if is_emergency else "power.dispatched_command_kw",
                    subject=booking_id,
                    stage=FactStage.DISPATCHED,
                    value=row["power_kw"],
                    unit="kW",
                    source_path=f"/{key}/{idx}/power_kw",
                    time_scope=TemporalBasis.DECISION_SNAPSHOT,
                )
            else:
                f_cmd = collector.add_fact(
                    resolved,
                    name="power.emergency_command_type" if is_emergency else "power.dispatched_command_type",
                    subject=booking_id,
                    stage=FactStage.DISPATCHED,
                    value=row["type"],
                    unit=None,
                    source_path=f"/{key}/{idx}/type",
                    time_scope=TemporalBasis.DECISION_SNAPSHOT,
                )
            f_exec = collector.add_fact(
                resolved,
                name="power.command_executed",
                subject=booking_id,
                stage=FactStage.DISPATCHED,
                value=bool(row.get("executed")),
                unit=None,
                source_path=f"/{key}/{idx}/executed",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            guard_facts, approval_facts = _add_command_guard_and_approval_facts(
                resolved, key=key, idx=idx, row=row, booking_id=booking_id, collector=collector
            )
            if row.get("guard_passed") is False:
                all_f = [f for f in (f_cmd, f_exec, *guard_facts) if f is not None]
                rules = ", ".join(v.get("rule", "unknown") for v in (row.get("violations") or []))
                if all_f:
                    collector.add_reason(
                        resolved,
                        code="BUSINESS_GUARD_BLOCKED",
                        category=EvidenceCategory.OBSERVED,
                        subject=booking_id,
                        fact_refs=[f.fact_id for f in all_f],
                        evidence_refs=[f.evidence_ref for f in all_f],
                        template_key="power.guard_blocked",
                        params={"rules": rules, "command_id": row.get("command_id")},
                        summary=f"Lệnh công suất bị Business Guard chặn (luật: {rules}).",
                    )
            elif row.get("approval_id") and not row.get("executed"):
                all_f = [f for f in (f_cmd, f_exec, *approval_facts) if f is not None]
                if all_f:
                    collector.add_reason(
                        resolved,
                        code="COMMAND_PENDING_APPROVAL",
                        category=EvidenceCategory.OBSERVED,
                        subject=booking_id,
                        fact_refs=[f.fact_id for f in all_f],
                        evidence_refs=[f.evidence_ref for f in all_f],
                        template_key="power.pending_approval",
                        params={"approval_id": row.get("approval_id"), "decision_time_only": True},
                        summary=(
                            f"Tại thời điểm quyết định, lệnh công suất chờ phê duyệt HITL ({row.get('approval_id')}) "
                            "và chưa được áp (không phản ánh trạng thái phê duyệt hiện tại)."
                        ),
                    )
                    collector.add_assumption(
                        "Trạng thái chờ phê duyệt phản ánh thời điểm quyết định, không khẳng định trạng thái phê duyệt hiện tại."
                    )
            elif is_emergency and row.get("executed"):
                all_f = [f for f in (f_cmd, f_exec) if f is not None]
                if all_f:
                    collector.add_reason(
                        resolved,
                        code="EMERGENCY_POWER_COMMAND_EXECUTED",
                        category=EvidenceCategory.OBSERVED,
                        subject=booking_id,
                        fact_refs=[f.fact_id for f in all_f],
                        evidence_refs=[f.evidence_ref for f in all_f],
                        template_key="power.emergency_executed",
                        params={"power_kw": row.get("power_kw")},
                        summary=f"Lệnh khẩn cấp đặt công suất {row.get('power_kw'):g} kW đã thực thi qua dispatcher.",
                    )

    for idx, row in enumerate(trace.get("command_exclusions") or []):
        if row.get("booking_id") != booking_id or row.get("type") not in ("set_power", "stop"):
            continue
        primary = row.get("primary_reason")
        f_ex = collector.add_fact(
            resolved,
            name="power.command_excluded_reason",
            subject=booking_id,
            stage=FactStage.DISPATCHED,
            value=primary,
            unit=None,
            source_path=f"/command_exclusions/{idx}/primary_reason",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_ex is not None:
            collector.add_reason(
                resolved,
                code=f"EXCLUDED_{primary}",
                category=EvidenceCategory.OBSERVED,
                subject=booking_id,
                fact_refs=[f_ex.fact_id],
                evidence_refs=[f_ex.evidence_ref],
                template_key="power.excluded",
                params={"primary_reason": primary, "reasons": ", ".join(row.get("reasons") or [])},
                summary=f"Lệnh điều phối bị loại trước khi gửi do {primary} (tất cả lý do: {', '.join(row.get('reasons') or [])}).",
            )

    # 3. Effective held setpoint & Measured actual output (G2-F01 / G2-F02 / G2-F03 / G2-F06)
    if resolved.provenance.closed and sample_slice is not None:
        _add_booking_measured_power_facts(resolved, sample_slice, booking_id, collector)

    # 4. Physical limits, Vehicle taper, Binding constraints, Coordinator & Optimizer reasons
    if planned is not None:
        _add_limits_and_policy_power_evidence(resolved, planned, booking_id, zone, vrow, vpath, collector)

    # 5. Post-apply violation / incomplete coverage (G2-F05 #3: subject-verified)
    _add_booking_post_apply_evidence(resolved, booking_id, collector)


def _add_booking_measured_power_facts(
    resolved: ResolvedTrace,
    sample_slice: SampleSlice,
    booking_id: str,
    collector: EvidenceCollector,
) -> None:
    trace = resolved.payload
    seg_bid = _seg(booking_id)

    # Register EVERY contributing held sample ref with exact sample interval
    held_contribs = [c for c in sample_slice.held_contributions if booking_id in (c.sample.get("by_booking_kw") or {})]
    held_refs = []
    for c in held_contribs:
        ref = collector.add_ref(
            resolved,
            f"/power/effective_setpoint/samples/{c.sample_index}/by_booking_kw/{seg_bid}",
            booking_id,
            time_scope=TemporalBasis.SAMPLE_INTERVAL,
            interval_start=c.sample_start,
            interval_end=c.sample_end,
        )
        if ref is not None:
            held_refs.append((c, ref))

    if held_refs and booking_id in sample_slice.held_avg_kw_by_booking:
        if sample_slice.is_point_query and len(held_refs) == 1:
            c0, r0 = held_refs[0]
            collector.add_fact(
                resolved,
                name="power.effective_held_setpoint_kw",
                subject=booking_id,
                stage=FactStage.EFFECTIVE_SETPOINT,
                value=round(float(c0.sample["by_booking_kw"][booking_id]), 6),
                unit="kW",
                source_path=r0.source_path,
                time_scope=TemporalBasis.SAMPLE_INTERVAL,
                interval_start=c0.sample_start,
                interval_end=c0.sample_end,
                derivation_kind=FactDerivationKind.DIRECT,
            )
        else:
            h_start = held_refs[0][0].overlap_start
            h_end = held_refs[-1][0].overlap_end
            collector.add_fact(
                resolved,
                name="power.effective_held_setpoint_avg_kw",
                subject=booking_id,
                stage=FactStage.EFFECTIVE_SETPOINT,
                value=round(sample_slice.held_avg_kw_by_booking[booking_id], 6),
                unit="kW",
                source_path=held_refs[0][1].source_path,
                time_scope=TemporalBasis.DERIVATION_INTERVAL,
                interval_start=h_start,
                interval_end=h_end,
                derivation_kind=FactDerivationKind.DERIVED,
                derivation_op=DerivationOp.AVERAGE,
                input_evidence_refs=[r.ref_id for _, r in held_refs],
                derivation_params={"sample_count": len(held_refs)},
            )

    # Register EVERY contributing actual sample ref with exact sample interval
    actual_contribs = [
        c for c in sample_slice.sample_contributions if booking_id in (c.sample.get("by_booking_kw") or {})
    ]
    actual_refs = []
    for c in actual_contribs:
        ref = collector.add_ref(
            resolved,
            f"/power/actual_output/samples/{c.sample_index}/by_booking_kw/{seg_bid}",
            booking_id,
            time_scope=TemporalBasis.SAMPLE_INTERVAL,
            interval_start=c.sample_start,
            interval_end=c.sample_end,
        )
        if ref is not None:
            actual_refs.append((c, ref))

    if not actual_refs or booking_id not in sample_slice.average_output_kw_by_booking:
        return

    # G2-F01: Point query (`at`) exposes sample-interval power ONLY — NEVER accumulated sample energy!
    if sample_slice.is_point_query and len(actual_refs) == 1:
        c0, r0 = actual_refs[0]
        collector.add_fact(
            resolved,
            name="power.measured_actual_output_kw",
            subject=booking_id,
            stage=FactStage.MEASURED,
            value=round(float(c0.sample["by_booking_kw"][booking_id]), 6),
            unit="kW",
            source_path=r0.source_path,
            time_scope=TemporalBasis.SAMPLE_INTERVAL,
            interval_start=c0.sample_start,
            interval_end=c0.sample_end,
            derivation_kind=FactDerivationKind.DIRECT,
        )
        return

    # Window query: derived average & exact-overlap energy carrying exact derivation_interval & ALL sample refs
    d_start = actual_refs[0][0].overlap_start
    d_end = actual_refs[-1][0].overlap_end
    ov_mins = round(sample_slice.sample_minutes_by_booking[booking_id], 6)
    input_ids = [r.ref_id for _, r in actual_refs]

    collector.add_fact(
        resolved,
        name="power.measured_actual_output_avg_kw",
        subject=booking_id,
        stage=FactStage.MEASURED,
        value=round(sample_slice.average_output_kw_by_booking[booking_id], 6),
        unit="kW",
        source_path=actual_refs[0][1].source_path,
        time_scope=TemporalBasis.DERIVATION_INTERVAL,
        interval_start=d_start,
        interval_end=d_end,
        derivation_kind=FactDerivationKind.DERIVED,
        derivation_op=DerivationOp.AVERAGE,
        input_evidence_refs=input_ids,
        derivation_params={"overlap_minutes": ov_mins, "sample_count": len(actual_refs)},
    )
    collector.add_fact(
        resolved,
        name="energy.measured_output_kwh",
        subject=booking_id,
        stage=FactStage.MEASURED,
        value=round(sample_slice.output_kwh_by_booking[booking_id], 6),
        unit="kWh",
        source_path=actual_refs[0][1].source_path,
        time_scope=TemporalBasis.DERIVATION_INTERVAL,
        interval_start=d_start,
        interval_end=d_end,
        derivation_kind=FactDerivationKind.DERIVED,
        derivation_op=DerivationOp.TIME_INTEGRATION,
        input_evidence_refs=input_ids,
        derivation_params={"overlap_minutes": ov_mins, "sample_count": len(actual_refs)},
    )

    # G2-F06: NEVER use silent 0.95 fallback; require decision-time conversion efficiency ref!
    if sample_slice.conversion_efficiency is not None and sample_slice.conversion_source_path is not None:
        conv_ref = collector.add_ref(
            resolved,
            sample_slice.conversion_source_path,
            "station",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if conv_ref is not None and booking_id in sample_slice.grid_input_kwh_by_booking:
            collector.add_fact(
                resolved,
                name="energy.measured_grid_input_kwh",
                subject=booking_id,
                stage=FactStage.MEASURED,
                value=round(sample_slice.grid_input_kwh_by_booking[booking_id], 6),
                unit="kWh",
                source_path=actual_refs[0][1].source_path,
                time_scope=TemporalBasis.DERIVATION_INTERVAL,
                interval_start=d_start,
                interval_end=d_end,
                derivation_kind=FactDerivationKind.DERIVED,
                derivation_op=DerivationOp.EFFICIENCY_CONVERSION,
                input_evidence_refs=[*input_ids, conv_ref.ref_id],
                derivation_params={
                    "conversion_efficiency": sample_slice.conversion_efficiency,
                    "overlap_minutes": ov_mins,
                },
            )
    else:
        collector.add_missing("missing_conversion_efficiency_evidence")

    # Battery stored kWh is only directly known for full unclipped measured coverage
    if (
        not sample_slice.is_subwindow
        and not sample_slice.has_partial_overlap
        and booking_id in ((trace.get("applied") or {}).get("battery_stored_kwh") or {})
    ):
        collector.add_fact(
            resolved,
            name="energy.measured_battery_stored_kwh",
            subject=booking_id,
            stage=FactStage.MEASURED,
            value=round(float(trace["applied"]["battery_stored_kwh"][booking_id]), 6),
            unit="kWh",
            source_path=f"/applied/battery_stored_kwh/{seg_bid}",
            time_scope=TemporalBasis.MEASURED_COVERAGE,
            interval_start=resolved.measured_start or d_start,
            interval_end=resolved.measured_end or d_end,
            derivation_kind=FactDerivationKind.DIRECT,
        )


def _add_limits_and_policy_power_evidence(
    resolved: ResolvedTrace,
    planned: dict,
    booking_id: str,
    zone: str | None,
    vrow: dict | None,
    vpath: str,
    collector: EvidenceCollector,
) -> None:
    trace = resolved.payload
    limits = planned.get("physical_limits") or {}
    p_start, p_end = resolved.planned_start, resolved.planned_end

    supply_mode = limits.get("supply_mode")
    if supply_mode:
        f_mode = collector.add_fact(
            resolved,
            name="limits.supply_mode",
            subject="station",
            stage=FactStage.CONFIG,
            value=supply_mode,
            unit=None,
            source_path="/planned/physical_limits/supply_mode",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if supply_mode == "shared" and limits.get("grid_input_kw") is not None:
            collector.add_fact(
                resolved,
                name="limits.site_grid_input_kw",
                subject="station",
                stage=FactStage.CONFIG,
                value=limits["grid_input_kw"],
                unit="kW",
                source_path="/planned/physical_limits/grid_input_kw",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
        elif supply_mode == "independent" and zone:
            ind_val = (limits.get("independent_grid_input_kw") or {}).get(zone)
            if ind_val is not None:
                f_ind = collector.add_fact(
                    resolved,
                    name="limits.independent_zone_grid_input_kw",
                    subject=zone,
                    stage=FactStage.CONFIG,
                    value=ind_val,
                    unit="kW",
                    source_path=f"/planned/physical_limits/independent_grid_input_kw/{_seg(zone)}",
                    time_scope=TemporalBasis.DECISION_SNAPSHOT,
                )
                if f_ind is not None and f_mode is not None:
                    collector.add_reason(
                        resolved,
                        code="INDEPENDENT_SUPPLY_MODE",
                        category=EvidenceCategory.OBSERVED,
                        subject=booking_id,
                        fact_refs=[f_mode.fact_id, f_ind.fact_id],
                        evidence_refs=[f_mode.evidence_ref, f_ind.evidence_ref],
                        template_key="power.independent_supply",
                        params={"zone": zone, "grid_input_kw": ind_val},
                        summary=f"Trạm chạy nguồn độc lập; vùng {zone} giới hạn nguồn riêng {ind_val:g} kW và không chia sẻ ngân sách xuyên vùng.",
                    )

    # G2-F03: Observed decision-time vehicle acceptance has time_scope=DECISION_SNAPSHOT (no planned interval!)
    if vrow is not None and vrow.get("allowed_output_kw") is not None:
        allowed_kw = float(vrow["allowed_output_kw"])
        vmax_kw = float(vrow.get("vehicle_max_output_kw") or allowed_kw)
        f_allow = collector.add_fact(
            resolved,
            name="vehicle.allowed_output_kw",
            subject=booking_id,
            stage=FactStage.OBSERVED,
            value=allowed_kw,
            unit="kW",
            source_path=f"{vpath}/allowed_output_kw",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        conn_id = vrow.get("connector_id") or vrow.get("planned_assigned_connector")
        port_kw = (limits.get("port_output_kw") or {}).get(conn_id) if conn_id else None
        hardware_cap = min(vmax_kw, float(port_kw)) if port_kw is not None else vmax_kw
        if f_allow is not None and allowed_kw + TOL < hardware_cap:
            dc_model = ((trace.get("experiment") or {}).get("dc_charging_model") or {}).get("name")
            f_model = None
            if dc_model:
                f_model = collector.add_fact(
                    resolved,
                    name="physics.dc_charging_model",
                    subject="station",
                    stage=FactStage.CONFIG,
                    value=dc_model,
                    unit=None,
                    source_path="/experiment/dc_charging_model/name",
                    time_scope=TemporalBasis.DECISION_SNAPSHOT,
                )
            f_refs = [f.fact_id for f in (f_allow, f_model) if f is not None]
            e_refs = [f.evidence_ref for f in (f_allow, f_model) if f is not None]
            collector.add_reason(
                resolved,
                code="VEHICLE_ACCEPTANCE_TAPER_LIMIT",
                category=EvidenceCategory.BINDING_CONSTRAINT,
                subject=booking_id,
                fact_refs=f_refs,
                evidence_refs=e_refs,
                template_key="power.vehicle_taper",
                params={
                    "allowed_kw": round(allowed_kw, 3),
                    "hardware_cap_kw": round(hardware_cap, 3),
                    "model": dc_model or "simulation_charging_model",
                },
                summary=(
                    f"Công suất chấp nhận của xe ở SOC hiện tại là {allowed_kw:g} kW (< trần phần cứng {hardware_cap:g} kW) "
                    f"theo mô hình sạc mô phỏng ({dc_model or 'adapter'})."
                ),
            )
            collector.add_assumption(
                "Đường giảm công suất theo SOC (taper) là mô hình mô phỏng, chưa hiệu chuẩn BMS thực tế."
            )

    # Binding constraints (direct scalar at /planned/binding_constraints/{idx}/kw)
    for idx, binding in enumerate(planned.get("binding_constraints") or []):
        if binding.get("stage") != "approved":
            continue
        limit_kind = binding.get("limit")
        bid_or_id = binding.get("id")
        relevant = (
            (limit_kind == "individual_allowed_output" and bid_or_id == booking_id)
            or (
                limit_kind == "port_output"
                and vrow is not None
                and bid_or_id in (vrow.get("connector_id"), vrow.get("planned_assigned_connector"))
            )
            or (limit_kind in ("zone_budget", "zone_limit", "independent_grid_input") and bid_or_id == zone)
            or (limit_kind == "site_grid_input")
            or (limit_kind == "cabinet_output" and vrow is not None and _booking_cabinet(planned, vrow) == bid_or_id)
        )
        if not relevant:
            continue
        f_bind = collector.add_fact(
            resolved,
            name=f"binding.{limit_kind}",
            subject=booking_id if limit_kind == "individual_allowed_output" else str(bid_or_id),
            stage=FactStage.APPROVED,
            value=binding.get("kw"),
            unit="kW",
            source_path=f"/planned/binding_constraints/{idx}/kw",
            time_scope=TemporalBasis.PLANNED_INTERVAL,
            interval_start=p_start,
            interval_end=p_end,
        )
        if f_bind is not None:
            collector.add_reason(
                resolved,
                code=f"BINDING_{str(limit_kind).upper()}",
                category=EvidenceCategory.BINDING_CONSTRAINT,
                subject=booking_id,
                fact_refs=[f_bind.fact_id],
                evidence_refs=[f_bind.evidence_ref],
                template_key="power.binding_constraint",
                params={"limit": limit_kind, "id": bid_or_id, "kw": binding.get("kw")},
                summary=f"Ràng buộc {limit_kind} ({bid_or_id}) chạm ngưỡng {binding.get('kw'):g} kW ở kế hoạch đã duyệt (đây là ràng buộc chạm trần, không suy diễn vượt bằng chứng).",
            )

    if zone:
        _add_coordinator_evidence(resolved, planned, zone, subject=booking_id, collector=collector)
        _add_optimizer_evidence(resolved, planned, zone, subject=booking_id, collector=collector)


def _add_coordinator_evidence(
    resolved: ResolvedTrace,
    planned: dict,
    zone: str,
    *,
    subject: str,
    collector: EvidenceCollector,
) -> None:
    coord = planned.get("coordinator") or {}
    coord_policy = str(coord.get("policy") or "unknown")
    assigned = (coord.get("assigned_output_kw") or {}).get(zone)
    f_budget = None
    if assigned is not None:
        f_budget = collector.add_fact(
            resolved,
            name="coordinator.assigned_zone_budget_kw",
            subject=zone,
            stage=FactStage.PLANNED,
            value=assigned,
            unit="kW",
            source_path=f"/planned/coordinator/assigned_output_kw/{_seg(zone)}",
            time_scope=TemporalBasis.PLANNED_INTERVAL,
            interval_start=resolved.planned_start,
            interval_end=resolved.planned_end,
        )
    codes = (coord.get("reason_codes") or {}).get(zone) or []
    for idx, code in enumerate(codes):
        f_code = collector.add_fact(
            resolved,
            name="coordinator.reason_code",
            subject=zone,
            stage=FactStage.PLANNED,
            value=code,
            unit=None,
            source_path=f"/planned/coordinator/reason_codes/{_seg(zone)}/{idx}",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_code is None:
            continue
        f_refs = [f.fact_id for f in (f_budget, f_code) if f is not None]
        e_refs = [f.evidence_ref for f in (f_budget, f_code) if f is not None]
        known = _KNOWN_COORDINATOR_REASONS.get((coord_policy, str(code)))
        if known is not None:
            reason_code, template = known
            collector.add_reason(
                resolved,
                code=reason_code,
                category=EvidenceCategory.POLICY_REASON,
                subject=subject,
                fact_refs=f_refs,
                evidence_refs=e_refs,
                template_key=f"coordinator.{code}",
                params={"zone": zone, "coordinator_policy": coord_policy, "budget_kw": assigned},
                summary=template.format(zone=zone),
            )
        else:
            collector.add_reason(
                resolved,
                code="UNKNOWN_POLICY_REASON_CODE",
                category=EvidenceCategory.POLICY_REASON,
                subject=subject,
                fact_refs=f_refs,
                evidence_refs=e_refs,
                template_key="coordinator.unknown_code",
                params={"zone": zone, "coordinator_policy": coord_policy, "raw_code": str(code)},
                summary=f"Mã lý do điều phối '{code}' của policy '{coord_policy}' chưa có ánh xạ xác định; không suy diễn nhân quả.",
            )


def _add_optimizer_evidence(
    resolved: ResolvedTrace,
    planned: dict,
    zone: str,
    *,
    subject: str,
    collector: EvidenceCollector,
) -> None:
    opt = (planned.get("optimizers") or {}).get(zone) or {}
    opt_policy = opt.get("policy")
    f_pol = None
    if opt_policy:
        f_pol = collector.add_fact(
            resolved,
            name="optimizer.policy",
            subject=zone,
            stage=FactStage.CONFIG,
            value=opt_policy,
            unit=None,
            source_path=f"/planned/optimizers/{_seg(zone)}/policy",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )

    fallback_reason = opt.get("fallback_reason")
    if fallback_reason:
        f_fb = collector.add_fact(
            resolved,
            name="optimizer.fallback_reason",
            subject=zone,
            stage=FactStage.PLANNED,
            value=fallback_reason,
            unit=None,
            source_path=f"/planned/optimizers/{_seg(zone)}/fallback_reason",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_fb is not None:
            collector.add_reason(
                resolved,
                code="OPTIMIZER_FALLBACK_TO_EQUAL_SHARE",
                category=EvidenceCategory.POLICY_REASON,
                subject=subject,
                fact_refs=[f.fact_id for f in (f_pol, f_fb) if f is not None],
                evidence_refs=[f.evidence_ref for f in (f_pol, f_fb) if f is not None],
                template_key="optimizer.fallback",
                params={"zone": zone, "optimizer_policy": opt_policy, "fallback_reason": fallback_reason},
                summary=f"Bộ tối ưu vùng {zone} ({opt_policy}) chuyển sang fallback equal_share do '{fallback_reason}'.",
            )
    elif (
        opt_policy == "ac_rolling_lp"
        and isinstance(opt.get("stage_status"), dict)
        and opt["stage_status"].get("tou") == "optimal"
        and planned.get("tariff") is not None
    ):
        f_tou = collector.add_fact(
            resolved,
            name="optimizer.tou_stage_status",
            subject=zone,
            stage=FactStage.PLANNED,
            value="optimal",
            unit=None,
            source_path=f"/planned/optimizers/{_seg(zone)}/stage_status/tou",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_tou is not None:
            collector.add_reason(
                resolved,
                code="AC_LP_TOU_OPTIMIZED",
                category=EvidenceCategory.POLICY_REASON,
                subject=subject,
                fact_refs=[f.fact_id for f in (f_pol, f_tou) if f is not None],
                evidence_refs=[f.evidence_ref for f in (f_pol, f_tou) if f is not None],
                template_key="optimizer.ac_tou",
                params={"zone": zone, "optimizer_policy": opt_policy},
                summary="Bộ tối ưu AC (ac_rolling_lp) giải tối ưu bậc hai theo biểu giá TOU sau khi tối thiểu hóa thiếu điện.",
            )


def _has_vehicle_specific_violation(trace: dict, booking_id: str) -> bool:
    safety = trace.get("safety") or {}
    if booking_id in (safety.get("by_booking") or {}):
        return True
    for hv in safety.get("hard_limit_violations") or []:
        if booking_id in (hv.get("booking_ids") or ()):
            return True
    applied = trace.get("applied") or {}
    for detail in applied.get("hard_violation_details") or []:
        if booking_id in (detail.get("vehicle_ids") or ()):
            return True
    return False


def _add_booking_post_apply_evidence(resolved: ResolvedTrace, booking_id: str, collector: EvidenceCollector) -> None:
    """G2-F05 #3: Never attribute a station-level violation to a vehicle without subject-specific evidence."""
    prov = resolved.provenance
    f_post = collector.add_fact(
        resolved,
        name="validation.post_apply_status",
        subject="station",
        stage=FactStage.MEASURED if prov.closed else FactStage.PLANNED,
        value=prov.post_apply_status,
        unit=None,
        source_path="/validation/post_apply",
        time_scope=TemporalBasis.MEASURED_COVERAGE if prov.closed else TemporalBasis.DECISION_SNAPSHOT,
        interval_start=resolved.measured_start
        if prov.closed and resolved.measured_start and resolved.measured_end
        else None,
        interval_end=resolved.measured_end
        if prov.closed and resolved.measured_start and resolved.measured_end
        else None,
    )
    if f_post is None:
        return
    if prov.post_apply_status == "violation":
        cov = prov.coverage_status
        vehicle_linked = _has_vehicle_specific_violation(resolved.payload, booking_id)
        if vehicle_linked:
            collector.add_reason(
                resolved,
                code="POST_APPLY_HARD_VIOLATION",
                category=EvidenceCategory.OBSERVED,
                subject=booking_id,
                fact_refs=[f_post.fact_id],
                evidence_refs=[f_post.evidence_ref],
                template_key="validation.post_apply_violation",
                params={"post_apply": prov.post_apply_status, "coverage": cov, "scope": "booking"},
                summary=(
                    "Ghi nhận vi phạm trần cứng liên quan tới phiên sạc sau khi áp (dữ liệu mẫu đo không đầy đủ)."
                    if cov == "incomplete"
                    else "Ghi nhận vi phạm trần cứng liên quan tới phiên sạc ở khoảng quyết định này."
                ),
            )
        else:
            collector.add_reason(
                resolved,
                code="STATION_POST_APPLY_HARD_VIOLATION",
                category=EvidenceCategory.OBSERVED,
                subject="station",
                fact_refs=[f_post.fact_id],
                evidence_refs=[f_post.evidence_ref],
                template_key="validation.station_post_apply_violation",
                params={"post_apply": prov.post_apply_status, "coverage": cov, "scope": "station"},
                summary=(
                    "Trạm ghi nhận vi phạm trần cứng cấp trạm sau khi áp (chưa có bằng chứng quy kết riêng cho xe này; dữ liệu mẫu đo không đầy đủ)."
                    if cov == "incomplete"
                    else "Trạm ghi nhận vi phạm trần cứng cấp trạm sau khi áp (không có bằng chứng quy kết riêng cho xe này)."
                ),
            )
    elif prov.post_apply_status == "incomplete":
        collector.add_reason(
            resolved,
            code="INCOMPLETE_MEASURED_COVERAGE",
            category=EvidenceCategory.OBSERVED,
            subject="station",
            fact_refs=[f_post.fact_id],
            evidence_refs=[f_post.evidence_ref],
            template_key="validation.incomplete_coverage",
            params={"post_apply": prov.post_apply_status, "coverage": prov.coverage_status},
            summary="Dữ liệu mẫu đo của quyết định không đầy đủ nên không kết luận đạt pass toàn khoảng.",
        )


def _add_station_post_apply_evidence(resolved: ResolvedTrace, station_id: str, collector: EvidenceCollector) -> None:
    prov = resolved.provenance
    f_post = collector.add_fact(
        resolved,
        name="validation.post_apply_status",
        subject="station",
        stage=FactStage.MEASURED if prov.closed else FactStage.PLANNED,
        value=prov.post_apply_status,
        unit=None,
        source_path="/validation/post_apply",
        time_scope=TemporalBasis.MEASURED_COVERAGE if prov.closed else TemporalBasis.DECISION_SNAPSHOT,
        interval_start=resolved.measured_start
        if prov.closed and resolved.measured_start and resolved.measured_end
        else None,
        interval_end=resolved.measured_end
        if prov.closed and resolved.measured_start and resolved.measured_end
        else None,
    )
    if f_post is None:
        return
    if prov.post_apply_status == "violation":
        cov = prov.coverage_status
        summary = (
            "Ghi nhận vi phạm trần cứng sau khi áp (và dữ liệu mẫu đo không đầy đủ — cần xem cả coverage)."
            if cov == "incomplete"
            else "Ghi nhận vi phạm trần cứng sau khi áp ở khoảng quyết định này."
        )
        collector.add_reason(
            resolved,
            code="POST_APPLY_HARD_VIOLATION",
            category=EvidenceCategory.OBSERVED,
            subject=station_id,
            fact_refs=[f_post.fact_id],
            evidence_refs=[f_post.evidence_ref],
            template_key="validation.post_apply_violation",
            params={"post_apply": prov.post_apply_status, "coverage": cov},
            summary=summary,
        )
    elif prov.post_apply_status == "incomplete":
        collector.add_reason(
            resolved,
            code="INCOMPLETE_MEASURED_COVERAGE",
            category=EvidenceCategory.OBSERVED,
            subject=station_id,
            fact_refs=[f_post.fact_id],
            evidence_refs=[f_post.evidence_ref],
            template_key="validation.incomplete_coverage",
            params={"post_apply": prov.post_apply_status, "coverage": prov.coverage_status},
            summary="Dữ liệu mẫu đo của quyết định không đầy đủ nên không kết luận đạt pass toàn khoảng.",
        )


def _explain_booking_deadline_risk(
    resolved: ResolvedTrace,
    booking_id: str,
    booking: Booking | None,
    collector: EvidenceCollector,
    *,
    query_at: datetime | None,
    query_window: TimeWindow | None,
) -> None:
    trace = resolved.payload
    planned = trace.get("planned") if isinstance(trace.get("planned"), dict) else None
    vrow, vpath = _planned_vehicle(trace, booking_id)
    if vrow is None:
        collector.add_missing("booking_not_in_planned_observation")
        return

    zone = vrow["zone"]
    f_rem = collector.add_fact(
        resolved,
        name="vehicle.remaining_kwh",
        subject=booking_id,
        stage=FactStage.OBSERVED,
        value=round(float(vrow["remaining_kwh"]), 6),
        unit="kWh",
        source_path=f"{vpath}/remaining_kwh",
        time_scope=TemporalBasis.DECISION_SNAPSHOT,
    )
    # SOC and target_soc are converted from [0, 1] fraction to % -> explicit DERIVED SOC_CONVERSION (G2-F02)
    ref_soc = collector.add_ref(resolved, f"{vpath}/soc", booking_id, time_scope=TemporalBasis.DECISION_SNAPSHOT)
    f_soc = (
        collector.add_fact(
            resolved,
            name="vehicle.observed_soc",
            subject=booking_id,
            stage=FactStage.OBSERVED,
            value=round(float(vrow["soc"]) * 100.0, 2),
            unit="%",
            source_path=f"{vpath}/soc",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
            derivation_kind=FactDerivationKind.DERIVED,
            derivation_op=DerivationOp.SOC_CONVERSION,
            input_evidence_refs=[ref_soc.ref_id],
            derivation_params={"scale": 100.0},
        )
        if ref_soc is not None
        else None
    )
    ref_tgt = collector.add_ref(resolved, f"{vpath}/target_soc", booking_id, time_scope=TemporalBasis.DECISION_SNAPSHOT)
    f_tgt = (
        collector.add_fact(
            resolved,
            name="vehicle.target_soc",
            subject=booking_id,
            stage=FactStage.OBSERVED,
            value=round(float(vrow["target_soc"]) * 100.0, 2),
            unit="%",
            source_path=f"{vpath}/target_soc",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
            derivation_kind=FactDerivationKind.DERIVED,
            derivation_op=DerivationOp.SOC_CONVERSION,
            input_evidence_refs=[ref_tgt.ref_id],
            derivation_params={"scale": 100.0},
        )
        if ref_tgt is not None
        else None
    )

    now_min = int((planned or {}).get("minute", trace.get("minute") or 0))
    deadline_min = int(vrow["deadline_minute"])
    rem_kwh = float(vrow["remaining_kwh"])
    applied = trace.get("applied") or {}
    completed_by_booking = applied.get("completed_by_booking") or {}
    completed_list = applied.get("completed") or []

    # 1. G2-F05 #1 & #2: Observed completion ONLY if already completed at decision time OR at/before query time,
    #    with direct completion evidence (NEVER pointing to pre-decision state='CHARGING'!).
    if vrow.get("completed_at_minute") is not None:
        f_done = collector.add_fact(
            resolved,
            name="deadline.observed_completed_at_minute",
            subject=booking_id,
            stage=FactStage.OBSERVED,
            value=vrow["completed_at_minute"],
            unit="minute",
            source_path=f"{vpath}/completed_at_minute",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_done is not None:
            collector.add_reason(
                resolved,
                code="OBSERVED_CHARGE_COMPLETED",
                category=EvidenceCategory.OBSERVED,
                subject=booking_id,
                fact_refs=[f.fact_id for f in (f_done, f_soc, f_tgt) if f is not None],
                evidence_refs=[f.evidence_ref for f in (f_done, f_soc, f_tgt) if f is not None],
                template_key="deadline.completed",
                params={"completed_at_minute": vrow["completed_at_minute"]},
                summary="Xe đã hoàn tất sạc trước hoặc tại thời điểm quyết định theo dữ kiện quan sát.",
            )
        return

    if resolved.provenance.closed and booking_id in completed_by_booking:
        comp_row = completed_by_booking[booking_id]
        comp_min = comp_row.get("minute")
        comp_dt = parse_iso_aware(comp_row.get("completed_at"))
        if comp_dt is None and comp_min is not None and trace.get("minute") is not None:
            comp_dt = resolved.decided_at + timedelta(minutes=int(comp_min) - int(trace["minute"]))
        completion_reached = comp_dt is not None and (
            (query_at is not None and _utc(query_at) >= _utc(comp_dt))
            or (query_window is not None and _utc(query_window.end) >= _utc(comp_dt))
        )
        if completion_reached:
            f_done = collector.add_fact(
                resolved,
                name="deadline.observed_completed_at_minute",
                subject=booking_id,
                stage=FactStage.MEASURED,
                value=comp_min,
                unit="minute",
                source_path=f"/applied/completed_by_booking/{_seg(booking_id)}/minute",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            if f_done is not None:
                collector.add_reason(
                    resolved,
                    code="OBSERVED_CHARGE_COMPLETED",
                    category=EvidenceCategory.OBSERVED,
                    subject=booking_id,
                    fact_refs=[f.fact_id for f in (f_done, f_soc, f_tgt) if f is not None],
                    evidence_refs=[f.evidence_ref for f in (f_done, f_soc, f_tgt) if f is not None],
                    template_key="deadline.completed",
                    params={
                        "completed_at_minute": comp_min,
                        "completed_at": comp_dt.isoformat() if comp_dt else None,
                    },
                    summary=f"Xe đã hoàn tất sạc tại phút mô phỏng {comp_min} trong khoảng thực thi.",
                )
            return
    elif resolved.provenance.closed and booking_id in completed_list:
        # Legacy closed trace without per-booking completion timestamp:
        # NEVER leak completion into an `at` query before effective_end!
        if (
            query_at is not None
            and resolved.effective_end is not None
            and _utc(query_at) < _utc(resolved.effective_end)
        ):
            collector.add_missing("completion_timestamp_unknown_for_as_of_query")
        elif (
            query_window is not None
            and resolved.effective_end is not None
            and _utc(query_window.end) >= _utc(resolved.effective_end)
        ):
            comp_idx = completed_list.index(booking_id)
            f_done = collector.add_fact(
                resolved,
                name="deadline.observed_completed_booking_id",
                subject=booking_id,
                stage=FactStage.MEASURED,
                value=booking_id,
                unit=None,
                source_path=f"/applied/completed/{comp_idx}",
                time_scope=TemporalBasis.MEASURED_COVERAGE,
                interval_start=resolved.measured_start,
                interval_end=resolved.measured_end,
            )
            if f_done is not None:
                collector.add_reason(
                    resolved,
                    code="OBSERVED_CHARGE_COMPLETED",
                    category=EvidenceCategory.OBSERVED,
                    subject=booking_id,
                    fact_refs=[f.fact_id for f in (f_done, f_soc, f_tgt) if f is not None],
                    evidence_refs=[f.evidence_ref for f in (f_done, f_soc, f_tgt) if f is not None],
                    template_key="deadline.completed",
                    params={},
                    summary="Xe hoàn tất sạc trong khoảng thực thi đã đóng của quyết định này.",
                )
            return

    if now_min >= deadline_min and rem_kwh > TOL and f_rem is not None:
        collector.add_reason(
            resolved,
            code="OBSERVED_DEADLINE_MISSED",
            category=EvidenceCategory.OBSERVED,
            subject=booking_id,
            fact_refs=[f.fact_id for f in (f_rem, f_soc, f_tgt) if f is not None],
            evidence_refs=[f.evidence_ref for f in (f_rem, f_soc, f_tgt) if f is not None],
            template_key="deadline.observed_missed",
            params={"remaining_kwh": round(rem_kwh, 3)},
            summary=f"Đã quá hạn lấy xe và vẫn còn thiếu {rem_kwh:.2f} kWh pin theo dữ kiện quan sát.",
        )

    # 2. Optimizer projected shortfall
    opt = ((planned or {}).get("optimizers") or {}).get(zone) or {}
    shortfalls = opt.get("projected_shortfall_kwh")
    if isinstance(shortfalls, dict) and booking_id in shortfalls:
        sf_val = float(shortfalls[booking_id])
        f_sf = collector.add_fact(
            resolved,
            name="deadline.projected_shortfall_kwh",
            subject=booking_id,
            stage=FactStage.PLANNED,
            value=round(sf_val, 6),
            unit="kWh",
            source_path=f"/planned/optimizers/{_seg(zone)}/projected_shortfall_kwh/{_seg(booking_id)}",
            time_scope=TemporalBasis.PLANNED_INTERVAL,
            interval_start=resolved.planned_start,
            interval_end=resolved.planned_end,
        )
        if f_sf is not None and sf_val > TOL:
            collector.add_reason(
                resolved,
                code="PROJECTED_SHORTFALL_UNDER_PERSISTENCE",
                category=EvidenceCategory.INFERENCE_BOUND,
                subject=booking_id,
                fact_refs=[f.fact_id for f in (f_rem, f_sf) if f is not None],
                evidence_refs=[f.evidence_ref for f in (f_rem, f_sf) if f is not None],
                template_key="deadline.projected_shortfall",
                params={"projected_shortfall_kwh": round(sf_val, 3), "optimizer_policy": opt.get("policy")},
                summary=(
                    f"Bộ tối ưu {opt.get('policy')} dự báo thiếu {sf_val:.2f} kWh dưới giả định persistence của ngân sách/ràng buộc "
                    "(đây là dự báo kế hoạch, không phải kết luận đã trễ hạn thực tế)."
                ),
            )
            collector.add_assumption(
                "projected_shortfall_kwh giả định ngân sách vùng và tập xe hiện biết giữ nguyên (persistence)."
            )
        elif f_sf is not None:
            collector.add_reason(
                resolved,
                code="NO_PROJECTED_SHORTFALL",
                category=EvidenceCategory.INFERENCE_BOUND,
                subject=booking_id,
                fact_refs=[f_sf.fact_id],
                evidence_refs=[f_sf.evidence_ref],
                template_key="deadline.no_projected_shortfall",
                params={"projected_shortfall_kwh": 0.0, "optimizer_policy": opt.get("policy")},
                summary=f"Bộ tối ưu {opt.get('policy')} không dự báo thiếu năng lượng trong chân trời lập kế hoạch hiện tại (không bảo đảm tuyệt đối trước sự cố/xe mới).",
            )

    # 3. Optimistic waiting laxity bound (DC queue)
    lax_row = ((planned or {}).get("dc_waiting_laxity") or {}).get(booking_id)
    if isinstance(lax_row, dict):
        lax_val = lax_row.get("optimistic_laxity_minutes")
        f_lax = collector.add_fact(
            resolved,
            name="deadline.optimistic_laxity_minutes",
            subject=booking_id,
            stage=FactStage.PLANNED,
            value=round(float(lax_val), 6) if lax_val is not None else None,
            unit="minutes",
            source_path=f"/planned/dc_waiting_laxity/{_seg(booking_id)}/optimistic_laxity_minutes",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_lax is not None:
            at_risk = bool(lax_row.get("at_risk_under_optimistic_bound"))
            collector.add_reason(
                resolved,
                code="OPTIMISTIC_LAXITY_NEGATIVE" if at_risk else "OPTIMISTIC_LAXITY_NONNEGATIVE",
                category=EvidenceCategory.INFERENCE_BOUND,
                subject=booking_id,
                fact_refs=[f.fact_id for f in (f_rem, f_lax) if f is not None],
                evidence_refs=[f.evidence_ref for f in (f_rem, f_lax) if f is not None],
                template_key="deadline.optimistic_laxity",
                params={"optimistic_laxity_minutes": f_lax.value, "at_risk": at_risk},
                summary=(
                    f"Cận lạc quan độ dư thời gian là {f_lax.value} phút (bỏ qua taper và tranh chấp công suất): "
                    + (
                        "nguy cơ không kịp hạn ngay cả theo cận lạc quan."
                        if at_risk
                        else "chưa âm theo cận lạc quan, nhưng không bảo đảm đúng hạn."
                    )
                ),
            )
            collector.add_assumption("optimistic_laxity_minutes là cận lạc quan bỏ qua taper DC và nhu cầu chia sẻ.")

    # 4. G2-F05 #7 & G2-F06: Strict single-vehicle hardware upper bound with FULL evidence inputs, NO silent 0.98!
    eta, eta_path = _resolve_charging_efficiency(trace)
    time_left_min = max(0, deadline_min - now_min)
    if time_left_min > 0 and f_rem is not None:
        if eta is None or eta_path is None:
            collector.add_missing("missing_charging_efficiency_evidence")
            return
        limits = (planned or {}).get("physical_limits") or {}
        port_output_map = limits.get("port_output_kw") or {}
        ports_obs = ((planned or {}).get("observed") or {}).get("ports") or {}
        compat_ports = [
            (cid, float(port_output_map.get(cid, p["port_limit_kw"])))
            for cid, p in ports_obs.items()
            if p.get("zone") == zone
        ]
        if not compat_ports:
            return
        best_port_id, max_port_kw = max(compat_ports, key=lambda item: item[1])
        vmax_kw = float(vrow["vehicle_max_output_kw"])
        max_rate_kw = min(vmax_kw, max_port_kw)
        max_deliverable_battery_kwh = max_rate_kw * eta * (time_left_min / 60.0)
        if rem_kwh > max_deliverable_battery_kwh + TOL:
            f_dl = collector.add_fact(
                resolved,
                name="vehicle.deadline_minute",
                subject=booking_id,
                stage=FactStage.OBSERVED,
                value=deadline_min,
                unit="minute",
                source_path=f"{vpath}/deadline_minute",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            f_now = collector.add_fact(
                resolved,
                name="decision.minute",
                subject="station",
                stage=FactStage.OBSERVED,
                value=now_min,
                unit="minute",
                source_path="/planned/minute" if planned is not None and "minute" in planned else "/minute",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            f_vmax = collector.add_fact(
                resolved,
                name="vehicle.max_output_kw",
                subject=booking_id,
                stage=FactStage.OBSERVED,
                value=vmax_kw,
                unit="kW",
                source_path=f"{vpath}/vehicle_max_output_kw",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            port_path = (
                f"/planned/physical_limits/port_output_kw/{_seg(best_port_id)}"
                if best_port_id in port_output_map
                else f"/planned/observed/ports/{_seg(best_port_id)}/port_limit_kw"
            )
            f_pcap = collector.add_fact(
                resolved,
                name="limits.compatible_port_max_output_kw",
                subject=zone,
                stage=FactStage.CONFIG,
                value=max_port_kw,
                unit="kW",
                source_path=port_path,
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            f_eta = collector.add_fact(
                resolved,
                name="limits.charging_efficiency",
                subject="station",
                stage=FactStage.CONFIG,
                value=eta,
                unit=None,
                source_path=eta_path,
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            bound_inputs = [f for f in (f_dl, f_now, f_vmax, f_pcap, f_eta) if f is not None]
            f_bound = (
                collector.add_fact(
                    resolved,
                    name="deadline.hardware_max_deliverable_kwh",
                    subject=booking_id,
                    stage=FactStage.PLANNED,
                    value=round(max_deliverable_battery_kwh, 6),
                    unit="kWh",
                    source_path=f_rem.source_path,
                    time_scope=TemporalBasis.DECISION_SNAPSHOT,
                    derivation_kind=FactDerivationKind.DERIVED,
                    derivation_op=DerivationOp.HARDWARE_BOUND,
                    input_evidence_refs=[f.evidence_ref for f in bound_inputs],
                    derivation_params={
                        "time_left_minutes": time_left_min,
                        "max_rate_kw": max_rate_kw,
                        "charging_efficiency": eta,
                    },
                )
                if bound_inputs
                else None
            )
            all_f = [f for f in (f_rem, f_dl, f_now, f_vmax, f_pcap, f_eta, f_bound) if f is not None]
            all_e = list(dict.fromkeys(f.evidence_ref for f in all_f))
            collector.add_reason(
                resolved,
                code="SINGLE_VEHICLE_HARDWARE_BOUND_EXCEEDED",
                category=EvidenceCategory.INFERENCE_BOUND,
                subject=booking_id,
                fact_refs=[f.fact_id for f in all_f],
                evidence_refs=all_e,
                template_key="deadline.hardware_bound_exceeded",
                params={
                    "remaining_kwh": round(rem_kwh, 3),
                    "max_deliverable_kwh": round(max_deliverable_battery_kwh, 3),
                    "time_left_minutes": time_left_min,
                    "charging_efficiency": eta,
                },
                summary=(
                    f"Cần nạp {rem_kwh:.2f} kWh pin trong {time_left_min} phút còn lại, vượt cận trên phần cứng một xe "
                    f"({max_deliverable_battery_kwh:.2f} kWh ở {max_rate_kw:g} kW × η={eta:g})."
                ),
            )


def _explain_booking_incident(
    resolved: ResolvedTrace,
    booking_id: str,
    role: Role,
    collector: EvidenceCollector,
    *,
    emit_no_incident: bool = True,
    has_temporal_gap: bool = False,
) -> None:
    trace = resolved.payload
    planned = trace.get("planned") if isinstance(trace.get("planned"), dict) else None
    found_incident = False

    held_by_booking = (trace.get("safety") or {}).get("by_booking") or {}
    if booking_id in held_by_booking:
        f_hold = collector.add_fact(
            resolved,
            name="safety.booking_safety_hold",
            subject=booking_id,
            stage=FactStage.OBSERVED,
            value=True,
            unit=None,
            source_path=f"/safety/by_booking/{_seg(booking_id)}/safety_hold",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_hold is not None:
            found_incident = True
            collector.add_reason(
                resolved,
                code="BOOKING_UNDER_SAFETY_HOLD",
                category=EvidenceCategory.OBSERVED,
                subject=booking_id,
                fact_refs=[f_hold.fact_id],
                evidence_refs=[f_hold.evidence_ref],
                template_key="incident.safety_hold",
                params={},
                summary="Phiên sạc đang ở trạng thái Safety Hold do sự cố an toàn; hệ thống không tự cấp lại công suất.",
            )

    for idx, row in enumerate(trace.get("emergency_commands") or []):
        if row.get("booking_id") != booking_id:
            continue
        f_em = collector.add_fact(
            resolved,
            name="incident.emergency_command_kw",
            subject=booking_id,
            stage=FactStage.DISPATCHED,
            value=row.get("power_kw"),
            unit="kW",
            source_path=f"/emergency_commands/{idx}/power_kw",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_em is not None:
            found_incident = True
            collector.add_reason(
                resolved,
                code="EMERGENCY_CURTAILMENT_APPLIED" if row.get("executed") else "EMERGENCY_COMMAND_NOT_EXECUTED",
                category=EvidenceCategory.OBSERVED,
                subject=booking_id,
                fact_refs=[f_em.fact_id],
                evidence_refs=[f_em.evidence_ref],
                template_key="incident.emergency_command",
                params={"power_kw": row.get("power_kw"), "executed": bool(row.get("executed"))},
                summary=f"Lệnh khẩn cấp đặt {row.get('power_kw'):g} kW (executed={bool(row.get('executed'))}).",
            )

    faulted = ((planned or {}).get("observed") or {}).get("faulted_connectors") or []
    if faulted:
        ref_flt = collector.add_ref(
            resolved, "/planned/observed/faulted_connectors", "station", time_scope=TemporalBasis.DECISION_SNAPSHOT
        )
        f_flt = (
            collector.add_fact(
                resolved,
                name="incident.faulted_connector_count",
                subject="station",
                stage=FactStage.OBSERVED,
                value=len(faulted),
                unit="count",
                source_path="/planned/observed/faulted_connectors",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
                derivation_kind=FactDerivationKind.DERIVED,
                derivation_op=DerivationOp.COUNT,
                input_evidence_refs=[ref_flt.ref_id],
            )
            if ref_flt is not None
            else None
        )
        if f_flt is not None:
            found_incident = True
            collector.add_reason(
                resolved,
                code="CONNECTOR_FAULT_ACTIVE",
                category=EvidenceCategory.OBSERVED,
                subject=booking_id,
                fact_refs=[f_flt.fact_id],
                evidence_refs=[f_flt.evidence_ref],
                template_key="incident.connector_fault",
                params={"faulted_count": len(faulted)},
                summary=f"Trạm hiện có {len(faulted)} đầu nối đang lỗi.",
            )

    if resolved.provenance.post_apply_status == "violation":
        found_incident = True
        _add_booking_post_apply_evidence(resolved, booking_id, collector)

    if not found_incident and emit_no_incident:
        if _can_confirm_no_incident(resolved, has_temporal_gap=has_temporal_gap):
            f_status = collector.add_fact(
                resolved,
                name="validation.post_apply_status",
                subject="station",
                stage=FactStage.MEASURED,
                value=resolved.provenance.post_apply_status,
                unit=None,
                source_path="/validation/post_apply",
                time_scope=TemporalBasis.MEASURED_COVERAGE,
                interval_start=resolved.measured_start,
                interval_end=resolved.measured_end,
            )
            if f_status is not None:
                collector.add_reason(
                    resolved,
                    code="NO_INCIDENT_OBSERVED",
                    category=EvidenceCategory.OBSERVED,
                    subject=booking_id,
                    fact_refs=[f_status.fact_id],
                    evidence_refs=[f_status.evidence_ref],
                    template_key="incident.none",
                    params={},
                    summary="Không ghi nhận sự cố, vi phạm trần cứng hay Safety Hold tác động lên phiên sạc trong khoảng truy vấn.",
                )
        else:
            collector.add_fact(
                resolved,
                name="validation.post_apply_status",
                subject="station",
                stage=FactStage.MEASURED if resolved.provenance.closed else FactStage.PLANNED,
                value=resolved.provenance.post_apply_status,
                unit=None,
                source_path="/validation/post_apply",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            collector.add_missing("insufficient_evidence_to_confirm_no_incident")


# ---- Station-scoped explainers (Operator only) -------------------------------------------


def _explain_station_trace(
    topic: WhyTopic,
    resolved: ResolvedTrace,
    sample_slice: SampleSlice | None,
    station_id: str,
    collector: EvidenceCollector,
    *,
    has_temporal_gap: bool,
) -> None:
    if topic == WhyTopic.QUEUE:
        _explain_station_queue(resolved, station_id, collector)
    elif topic == WhyTopic.POWER:
        _explain_station_power(resolved, sample_slice, station_id, collector)
    elif topic == WhyTopic.DEADLINE_RISK:
        _explain_station_deadline_risk(resolved, station_id, collector)
    elif topic == WhyTopic.INCIDENT:
        _explain_station_incident(resolved, station_id, collector, has_temporal_gap=has_temporal_gap)
    elif topic == WhyTopic.POLICY:
        _explain_policy(resolved, station_id, None, collector, is_station=True)
    elif topic == WhyTopic.OVERVIEW:
        _explain_station_queue(resolved, station_id, collector)
        _explain_station_power(resolved, sample_slice, station_id, collector)
        _explain_station_deadline_risk(resolved, station_id, collector)
        _explain_station_incident(
            resolved, station_id, collector, emit_no_incident=False, has_temporal_gap=has_temporal_gap
        )


def _explain_station_queue(resolved: ResolvedTrace, station_id: str, collector: EvidenceCollector) -> None:
    planned = resolved.payload.get("planned")
    if not isinstance(planned, dict):
        return
    zsums = (planned.get("observed") or {}).get("zone_summary") or {}
    for zone, info in zsums.items():
        zpath = f"/planned/observed/zone_summary/{_seg(zone)}"
        f_wait = collector.add_fact(
            resolved,
            name="queue.zone_waiting_count",
            subject=zone,
            stage=FactStage.OBSERVED,
            value=info["waiting_count"],
            unit="count",
            source_path=f"{zpath}/waiting_count",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        f_emp = collector.add_fact(
            resolved,
            name="queue.zone_empty_ports",
            subject=zone,
            stage=FactStage.OBSERVED,
            value=info["empty_ports"],
            unit="count",
            source_path=f"{zpath}/empty_ports",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        f_occ = collector.add_fact(
            resolved,
            name="queue.zone_occupied_ports",
            subject=zone,
            stage=FactStage.OBSERVED,
            value=info["occupied_ports"],
            unit="count",
            source_path=f"{zpath}/occupied_ports",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        f_flt = collector.add_fact(
            resolved,
            name="queue.zone_faulted_ports",
            subject=zone,
            stage=FactStage.OBSERVED,
            value=info["faulted_ports"],
            unit="count",
            source_path=f"{zpath}/faulted_ports",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_wait is not None and info["waiting_count"] > 0 and info["empty_ports"] == 0:
            f_refs = [f.fact_id for f in (f_wait, f_emp, f_occ, f_flt) if f is not None]
            e_refs = [f.evidence_ref for f in (f_wait, f_emp, f_occ, f_flt) if f is not None]
            collector.add_reason(
                resolved,
                code="ZONE_PORTS_SATURATED",
                category=EvidenceCategory.OBSERVED,
                subject=zone,
                fact_refs=f_refs,
                evidence_refs=e_refs,
                template_key="station.zone_saturated",
                params={
                    "zone": zone,
                    "waiting": info["waiting_count"],
                    "occupied": info["occupied_ports"],
                    "faulted": info["faulted_ports"],
                },
                summary=f"Vùng {zone} có {info['waiting_count']} xe chờ vì hết cổng trống (đang dùng: {info['occupied_ports']}, lỗi: {info['faulted_ports']}).",
            )


def _explain_station_power(
    resolved: ResolvedTrace,
    sample_slice: SampleSlice | None,
    station_id: str,
    collector: EvidenceCollector,
) -> None:
    trace = resolved.payload
    planned = trace.get("planned") if isinstance(trace.get("planned"), dict) else None
    power = trace.get("power") or {}
    p_start, p_end = resolved.planned_start, resolved.planned_end

    # Total proposed & approved output kW (explicit DERIVED SUM over per-booking inputs)
    for stage_key, stage_enum, fact_name in (
        ("proposed", FactStage.PLANNED, "power.station_proposed_total_kw"),
        ("approved", FactStage.APPROVED, "power.station_approved_total_kw"),
    ):
        kw_map = (power.get(stage_key) or {}).get("by_booking_kw") or {}
        if kw_map:
            refs = [
                collector.add_ref(
                    resolved,
                    f"/power/{stage_key}/by_booking_kw/{_seg(vid)}",
                    vid,
                    time_scope=TemporalBasis.PLANNED_INTERVAL,
                    interval_start=p_start,
                    interval_end=p_end,
                )
                for vid in sorted(kw_map)
            ]
            ref_ids = [r.ref_id for r in refs if r is not None]
        else:
            parent_ref = collector.add_ref(
                resolved,
                f"/power/{stage_key}/by_booking_kw",
                station_id,
                time_scope=TemporalBasis.PLANNED_INTERVAL,
                interval_start=p_start,
                interval_end=p_end,
            )
            ref_ids = [parent_ref.ref_id] if parent_ref is not None else []
        if ref_ids:
            collector.add_fact(
                resolved,
                name=fact_name,
                subject=station_id,
                stage=stage_enum,
                value=round(sum(float(v) for v in kw_map.values()), 6),
                unit="kW",
                source_path=f"/power/{stage_key}/by_booking_kw",
                time_scope=TemporalBasis.PLANNED_INTERVAL,
                interval_start=p_start,
                interval_end=p_end,
                derivation_kind=FactDerivationKind.DERIVED,
                derivation_op=DerivationOp.SUM,
                input_evidence_refs=ref_ids,
                derivation_params={"booking_count": len(kw_map)},
            )

    # Measured station power/energy (G2-F01 / G2-F02 / G2-F03 / G2-F06)
    if resolved.provenance.closed and sample_slice is not None and sample_slice.sample_contributions:
        sample_refs = []
        for c in sample_slice.sample_contributions:
            for vid in sorted(c.sample.get("by_booking_kw") or {}):
                ref = collector.add_ref(
                    resolved,
                    f"/power/actual_output/samples/{c.sample_index}/by_booking_kw/{_seg(vid)}",
                    vid,
                    time_scope=TemporalBasis.SAMPLE_INTERVAL,
                    interval_start=c.sample_start,
                    interval_end=c.sample_end,
                )
                if ref is not None:
                    sample_refs.append(ref)
        if sample_refs:
            ref_ids = [r.ref_id for r in sample_refs]
            if sample_slice.is_point_query:
                c0 = sample_slice.sample_contributions[0]
                total_kw = sum(float(v) for v in (c0.sample.get("by_booking_kw") or {}).values())
                collector.add_fact(
                    resolved,
                    name="power.station_measured_output_kw",
                    subject=station_id,
                    stage=FactStage.MEASURED,
                    value=round(total_kw, 6),
                    unit="kW",
                    source_path=sample_refs[0].source_path,
                    time_scope=TemporalBasis.SAMPLE_INTERVAL,
                    interval_start=c0.sample_start,
                    interval_end=c0.sample_end,
                    derivation_kind=FactDerivationKind.DERIVED,
                    derivation_op=DerivationOp.SUM,
                    input_evidence_refs=ref_ids,
                )
            else:
                d_start = sample_slice.derivation_start
                d_end = sample_slice.derivation_end
                total_out_kwh = sum(sample_slice.output_kwh_by_booking.values())
                collector.add_fact(
                    resolved,
                    name="energy.station_measured_output_kwh",
                    subject=station_id,
                    stage=FactStage.MEASURED,
                    value=round(total_out_kwh, 6),
                    unit="kWh",
                    source_path=sample_refs[0].source_path,
                    time_scope=TemporalBasis.DERIVATION_INTERVAL,
                    interval_start=d_start,
                    interval_end=d_end,
                    derivation_kind=FactDerivationKind.DERIVED,
                    derivation_op=DerivationOp.TIME_INTEGRATION,
                    input_evidence_refs=ref_ids,
                    derivation_params={"overlap_minutes": round(sample_slice.covered_minutes, 6)},
                )
                if sample_slice.conversion_efficiency is not None and sample_slice.conversion_source_path is not None:
                    conv_ref = collector.add_ref(
                        resolved,
                        sample_slice.conversion_source_path,
                        "station",
                        time_scope=TemporalBasis.DECISION_SNAPSHOT,
                    )
                    if conv_ref is not None:
                        total_grid_kwh = sum(sample_slice.grid_input_kwh_by_booking.values())
                        collector.add_fact(
                            resolved,
                            name="energy.station_measured_grid_input_kwh",
                            subject=station_id,
                            stage=FactStage.MEASURED,
                            value=round(total_grid_kwh, 6),
                            unit="kWh",
                            source_path=sample_refs[0].source_path,
                            time_scope=TemporalBasis.DERIVATION_INTERVAL,
                            interval_start=d_start,
                            interval_end=d_end,
                            derivation_kind=FactDerivationKind.DERIVED,
                            derivation_op=DerivationOp.EFFICIENCY_CONVERSION,
                            input_evidence_refs=[*ref_ids, conv_ref.ref_id],
                            derivation_params={"conversion_efficiency": sample_slice.conversion_efficiency},
                        )
                else:
                    collector.add_missing("missing_conversion_efficiency_evidence")

    if planned is not None:
        limits = planned.get("physical_limits") or {}
        if limits.get("supply_mode"):
            collector.add_fact(
                resolved,
                name="limits.supply_mode",
                subject=station_id,
                stage=FactStage.CONFIG,
                value=limits["supply_mode"],
                unit=None,
                source_path="/planned/physical_limits/supply_mode",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
        if limits.get("grid_input_kw") is not None:
            collector.add_fact(
                resolved,
                name="limits.site_grid_input_kw",
                subject=station_id,
                stage=FactStage.CONFIG,
                value=limits["grid_input_kw"],
                unit="kW",
                source_path="/planned/physical_limits/grid_input_kw",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
        for zone in (planned.get("coordinator") or {}).get("assigned_output_kw") or {}:
            _add_coordinator_evidence(resolved, planned, zone, subject=zone, collector=collector)
            _add_optimizer_evidence(resolved, planned, zone, subject=zone, collector=collector)
        for idx, binding in enumerate(planned.get("binding_constraints") or []):
            if binding.get("stage") != "approved":
                continue
            f_b = collector.add_fact(
                resolved,
                name=f"binding.{binding.get('limit')}",
                subject=str(binding.get("id")),
                stage=FactStage.APPROVED,
                value=binding.get("kw"),
                unit="kW",
                source_path=f"/planned/binding_constraints/{idx}/kw",
                time_scope=TemporalBasis.PLANNED_INTERVAL,
                interval_start=p_start,
                interval_end=p_end,
            )
            if f_b is not None:
                collector.add_reason(
                    resolved,
                    code=f"BINDING_{str(binding.get('limit')).upper()}",
                    category=EvidenceCategory.BINDING_CONSTRAINT,
                    subject=str(binding.get("id")),
                    fact_refs=[f_b.fact_id],
                    evidence_refs=[f_b.evidence_ref],
                    template_key="station.binding_constraint",
                    params={"limit": binding.get("limit"), "id": binding.get("id"), "kw": binding.get("kw")},
                    summary=f"Ràng buộc {binding.get('limit')} ({binding.get('id')}) chạm trần {binding.get('kw'):g} kW.",
                )

    _add_station_post_apply_evidence(resolved, station_id, collector)


def _explain_station_deadline_risk(resolved: ResolvedTrace, station_id: str, collector: EvidenceCollector) -> None:
    planned = resolved.payload.get("planned")
    if not isinstance(planned, dict):
        return
    at_risk_projected: list[str] = []
    for zone, opt in (planned.get("optimizers") or {}).items():
        shortfalls = opt.get("projected_shortfall_kwh") if isinstance(opt, dict) else None
        if not isinstance(shortfalls, dict):
            continue
        for vid, sf in sorted(shortfalls.items()):
            sf_val = float(sf)
            if sf_val > TOL:
                at_risk_projected.append(vid)
                f_sf = collector.add_fact(
                    resolved,
                    name="deadline.projected_shortfall_kwh",
                    subject=vid,
                    stage=FactStage.PLANNED,
                    value=round(sf_val, 6),
                    unit="kWh",
                    source_path=f"/planned/optimizers/{_seg(zone)}/projected_shortfall_kwh/{_seg(vid)}",
                    time_scope=TemporalBasis.PLANNED_INTERVAL,
                    interval_start=resolved.planned_start,
                    interval_end=resolved.planned_end,
                )
                if f_sf is not None:
                    collector.add_reason(
                        resolved,
                        code="PROJECTED_SHORTFALL_UNDER_PERSISTENCE",
                        category=EvidenceCategory.INFERENCE_BOUND,
                        subject=vid,
                        fact_refs=[f_sf.fact_id],
                        evidence_refs=[f_sf.evidence_ref],
                        template_key="station.projected_shortfall",
                        params={"booking_id": vid, "zone": zone, "projected_shortfall_kwh": round(sf_val, 3)},
                        summary=f"Xe {vid} (vùng {zone}) có dự báo thiếu {sf_val:.2f} kWh dưới giả định persistence của optimizer.",
                    )

    for vid, lax in sorted((planned.get("dc_waiting_laxity") or {}).items()):
        if lax.get("at_risk_under_optimistic_bound"):
            f_lax = collector.add_fact(
                resolved,
                name="deadline.optimistic_laxity_minutes",
                subject=vid,
                stage=FactStage.PLANNED,
                value=lax.get("optimistic_laxity_minutes"),
                unit="minutes",
                source_path=f"/planned/dc_waiting_laxity/{_seg(vid)}/optimistic_laxity_minutes",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            if f_lax is not None:
                collector.add_reason(
                    resolved,
                    code="OPTIMISTIC_LAXITY_NEGATIVE",
                    category=EvidenceCategory.INFERENCE_BOUND,
                    subject=vid,
                    fact_refs=[f_lax.fact_id],
                    evidence_refs=[f_lax.evidence_ref],
                    template_key="station.optimistic_laxity",
                    params={"booking_id": vid, "optimistic_laxity_minutes": f_lax.value},
                    summary=f"Xe chờ DC {vid} có cận lạc quan độ dư thời gian âm ({f_lax.value} phút).",
                )

    if not at_risk_projected and not any(
        lax.get("at_risk_under_optimistic_bound") for lax in (planned.get("dc_waiting_laxity") or {}).values()
    ):
        f_pol = collector.add_fact(
            resolved,
            name="policy.id",
            subject=station_id,
            stage=FactStage.CONFIG,
            value=resolved.provenance.policy_id,
            unit=None,
            source_path="/policy/id",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_pol is not None:
            collector.add_reason(
                resolved,
                code="NO_DEADLINE_RISK_SIGNALED",
                category=EvidenceCategory.OBSERVED,
                subject=station_id,
                fact_refs=[f_pol.fact_id],
                evidence_refs=[f_pol.evidence_ref],
                template_key="station.no_deadline_risk",
                params={},
                summary="Không có cảnh báo thiếu điện dự báo hay cận lạc quan âm trong trace quyết định.",
            )


def _explain_station_incident(
    resolved: ResolvedTrace,
    station_id: str,
    collector: EvidenceCollector,
    *,
    emit_no_incident: bool = True,
    has_temporal_gap: bool = False,
) -> None:
    trace = resolved.payload
    planned = trace.get("planned") if isinstance(trace.get("planned"), dict) else None
    found = False

    safety = trace.get("safety") or {}
    for idx, hv in enumerate(safety.get("hard_limit_violations") or []):
        kind_facts = []
        for k_idx, kind in enumerate(hv.get("kinds") or []):
            f_hv = collector.add_fact(
                resolved,
                name="safety.hard_limit_violation_kind",
                subject=station_id,
                stage=FactStage.OBSERVED,
                value=str(kind),
                unit=None,
                source_path=f"/safety/hard_limit_violations/{idx}/kinds/{k_idx}",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            if f_hv is not None:
                kind_facts.append(f_hv)
        if kind_facts:
            found = True
            kinds_str = ", ".join(str(f.value) for f in kind_facts)
            collector.add_reason(
                resolved,
                code="HARD_LIMIT_VIOLATION_TRIGGERED",
                category=EvidenceCategory.OBSERVED,
                subject=station_id,
                fact_refs=[f.fact_id for f in kind_facts],
                evidence_refs=[f.evidence_ref for f in kind_facts],
                template_key="station.hard_violation",
                params={"kinds": kinds_str, "booking_ids": ", ".join(hv.get("booking_ids") or [])},
                summary=f"Sự kiện vi phạm trần cứng ({kinds_str}) kích hoạt vòng fail-safe.",
            )

    held = safety.get("held_booking_ids") or []
    if held:
        ref_held = collector.add_ref(
            resolved, "/safety/held_booking_ids", station_id, time_scope=TemporalBasis.DECISION_SNAPSHOT
        )
        f_held = (
            collector.add_fact(
                resolved,
                name="safety.held_booking_count",
                subject=station_id,
                stage=FactStage.OBSERVED,
                value=len(held),
                unit="count",
                source_path="/safety/held_booking_ids",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
                derivation_kind=FactDerivationKind.DERIVED,
                derivation_op=DerivationOp.COUNT,
                input_evidence_refs=[ref_held.ref_id],
            )
            if ref_held is not None
            else None
        )
        if f_held is not None:
            found = True
            collector.add_reason(
                resolved,
                code="STATION_SAFETY_HOLDS_ACTIVE",
                category=EvidenceCategory.OBSERVED,
                subject=station_id,
                fact_refs=[f_held.fact_id],
                evidence_refs=[f_held.evidence_ref],
                template_key="station.safety_holds",
                params={"held_count": len(held), "booking_ids": ", ".join(held)},
                summary=f"Đang có {len(held)} booking trong Safety Hold ({', '.join(held)}).",
            )

    fs = (trace.get("validation") or {}).get("fail_safe") or {}
    if fs.get("status") and fs.get("status") != "not_triggered":
        f_fs = collector.add_fact(
            resolved,
            name="validation.fail_safe_status",
            subject=station_id,
            stage=FactStage.DISPATCHED,
            value=fs["status"],
            unit=None,
            source_path="/validation/fail_safe/status",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
        if f_fs is not None:
            found = True
            outcomes = fs.get("outcomes") or []
            res_summary = outcomes[-1].get("resolution") if outcomes else "unknown"
            collector.add_reason(
                resolved,
                code="FAIL_SAFE_OUTCOME",
                category=EvidenceCategory.OBSERVED,
                subject=station_id,
                fact_refs=[f_fs.fact_id],
                evidence_refs=[f_fs.evidence_ref],
                template_key="station.failsafe_outcome",
                params={"fail_safe_status": fs["status"], "resolution": res_summary},
                summary=f"Fail-safe trạng thái '{fs['status']}' (resolution='{res_summary}').",
            )

    faulted = ((planned or {}).get("observed") or {}).get("faulted_connectors") or []
    if faulted:
        flt_facts = []
        for f_idx, cid in enumerate(faulted):
            f_flt = collector.add_fact(
                resolved,
                name="incident.faulted_connectors",
                subject=station_id,
                stage=FactStage.OBSERVED,
                value=str(cid),
                unit=None,
                source_path=f"/planned/observed/faulted_connectors/{f_idx}",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            if f_flt is not None:
                flt_facts.append(f_flt)
        if flt_facts:
            found = True
            joined = ", ".join(str(f.value) for f in flt_facts)
            collector.add_reason(
                resolved,
                code="CONNECTOR_FAULT_ACTIVE",
                category=EvidenceCategory.OBSERVED,
                subject=station_id,
                fact_refs=[f.fact_id for f in flt_facts],
                evidence_refs=[f.evidence_ref for f in flt_facts],
                template_key="station.connector_fault",
                params={"connectors": joined},
                summary=f"Các đầu nối đang lỗi: {joined}.",
            )

    if resolved.provenance.post_apply_status == "violation":
        found = True
        _add_station_post_apply_evidence(resolved, station_id, collector)

    if not found and emit_no_incident:
        if _can_confirm_no_incident(resolved, has_temporal_gap=has_temporal_gap):
            f_v = collector.add_fact(
                resolved,
                name="validation.post_apply_status",
                subject=station_id,
                stage=FactStage.MEASURED,
                value=resolved.provenance.post_apply_status,
                unit=None,
                source_path="/validation/post_apply",
                time_scope=TemporalBasis.MEASURED_COVERAGE,
                interval_start=resolved.measured_start,
                interval_end=resolved.measured_end,
            )
            if f_v is not None:
                collector.add_reason(
                    resolved,
                    code="NO_INCIDENT_OBSERVED",
                    category=EvidenceCategory.OBSERVED,
                    subject=station_id,
                    fact_refs=[f_v.fact_id],
                    evidence_refs=[f_v.evidence_ref],
                    template_key="station.no_incident",
                    params={},
                    summary="Không có sự cố, vi phạm trần cứng hay đầu nối lỗi được ghi nhận trong khoảng truy vấn.",
                )
        else:
            collector.add_fact(
                resolved,
                name="validation.post_apply_status",
                subject="station",
                stage=FactStage.MEASURED if resolved.provenance.closed else FactStage.PLANNED,
                value=resolved.provenance.post_apply_status,
                unit=None,
                source_path="/validation/post_apply",
                time_scope=TemporalBasis.DECISION_SNAPSHOT,
            )
            collector.add_missing("insufficient_evidence_to_confirm_no_incident")


def _explain_policy(
    resolved: ResolvedTrace,
    subject: str,
    booking: Booking | None,
    collector: EvidenceCollector,
    *,
    is_station: bool,
) -> None:
    trace = resolved.payload
    planned = trace.get("planned") if isinstance(trace.get("planned"), dict) else None
    f_pid = collector.add_fact(
        resolved,
        name="policy.id",
        subject="station",
        stage=FactStage.CONFIG,
        value=resolved.provenance.policy_id,
        unit=None,
        source_path="/policy/id",
        time_scope=TemporalBasis.DECISION_SNAPSHOT,
    )
    f_pver = collector.add_fact(
        resolved,
        name="policy.version",
        subject="station",
        stage=FactStage.CONFIG,
        value=resolved.provenance.policy_version,
        unit=None,
        source_path="/policy/version",
        time_scope=TemporalBasis.DECISION_SNAPSHOT,
    )
    if (trace.get("experiment") or {}).get("fingerprint"):
        collector.add_fact(
            resolved,
            name="experiment.fingerprint",
            subject="station",
            stage=FactStage.CONFIG,
            value=trace["experiment"]["fingerprint"],
            unit=None,
            source_path="/experiment/fingerprint",
            time_scope=TemporalBasis.DECISION_SNAPSHOT,
        )
    if f_pid is not None:
        collector.add_reason(
            resolved,
            code="POLICY_PROVENANCE",
            category=EvidenceCategory.POLICY_REASON,
            subject=subject,
            fact_refs=[f.fact_id for f in (f_pid, f_pver) if f is not None],
            evidence_refs=[f.evidence_ref for f in (f_pid, f_pver) if f is not None],
            template_key="policy.provenance",
            params={"policy_id": resolved.provenance.policy_id, "policy_version": resolved.provenance.policy_version},
            summary=f"Quyết định sử dụng policy {resolved.provenance.policy_id} (version {resolved.provenance.policy_version}).",
        )

    if planned is not None:
        vrow, _ = (None, "") if is_station else _planned_vehicle(trace, subject)
        zones = (
            list((planned.get("coordinator") or {}).get("assigned_output_kw") or [])
            if is_station
            else ([vrow["zone"]] if vrow else ([str(booking.request.zone)] if booking else []))
        )
        for zone in zones:
            _add_coordinator_evidence(resolved, planned, zone, subject=subject, collector=collector)
            _add_optimizer_evidence(resolved, planned, zone, subject=subject, collector=collector)
