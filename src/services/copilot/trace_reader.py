"""Temporal DecisionTrace reader & overlap/as-of resolver (G1-F06).

Distinguishes three distinct temporal intervals for every trace:
  1. Planned interval:   [planned_start, planned_end) from decision-time `interval`.
  2. Effective interval: [effective_start, effective_end) when the decision actually governed
                         (ends early on replan, capped for unconfirmed active traces after restart).
  3. Measured interval:  [measured_start, measured_end) covered by retained applied samples.

Strictly read-only: never calls `sync_clock`, `simulator.step`, or mutates runtime/DB.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.models.copilot import TimeWindow, TraceProvenance
from src.services import repository


def parse_iso_aware(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return value
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Naive timestamp in trace: {value!r}")
    return parsed


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC)


@dataclass(frozen=True)
class SampleSlice:
    """Measured power/energy strictly restricted to retained samples overlapping a query window."""

    samples: tuple[dict, ...]
    held_samples: tuple[dict, ...]
    covered_minutes: int
    expected_window_minutes: float | None
    is_subwindow: bool
    has_sample_timestamps: bool
    complete_for_window: bool
    output_kwh_by_booking: dict[str, float]
    grid_input_kwh_by_booking: dict[str, float]
    average_output_kw_by_booking: dict[str, float]
    sample_minutes_by_booking: dict[str, int]
    held_avg_kw_by_booking: dict[str, float]


@dataclass(frozen=True)
class ResolvedTrace:
    """One DecisionTrace enriched with its resolved planned/effective/measured temporal bounds."""

    payload: dict
    provenance: TraceProvenance
    decided_at: datetime
    effective_start: datetime
    effective_end: datetime | None
    planned_start: datetime | None
    planned_end: datetime | None
    measured_start: datetime | None
    measured_end: datetime | None
    is_point_decision: bool
    stale_after_restart: bool


@dataclass(frozen=True)
class TemporalResolution:
    traces: list[ResolvedTrace]
    legacy_summary_only_count: int
    truncated: bool
    has_temporal_gap: bool
    exceeds_available_evidence: bool
    stale_active_traces_detected: int
    missing_evidence: list[str]


def _sort_key(trace: dict) -> tuple:
    decided = _utc(parse_iso_aware(trace["decided_at"]))
    sched = int(trace.get("schedule_version") or 0)
    cid = str(trace.get("correlation_id") or "")
    return (decided, sched, cid)


def _trace_intervals(
    trace: dict,
    *,
    next_decided_at: datetime | None,
    latest_trace_key: tuple | None,
    live_open_correlation_id: str | None,
    live_open_known: bool,
) -> ResolvedTrace:
    decided_at = parse_iso_aware(trace["decided_at"])
    assert decided_at is not None
    cid = str(trace["correlation_id"])
    closed = bool(trace.get("closed", False))
    interval = trace.get("interval") or {}
    applied = trace.get("applied") or {}
    coverage = applied.get("coverage") or {}
    validation = trace.get("validation") or {}
    policy = trace.get("policy") or {}

    planned_start: datetime | None = None
    planned_end: datetime | None = None
    if interval:
        planned_start = parse_iso_aware(interval.get("start_at")) or decided_at
        if interval.get("end_at"):
            planned_end = parse_iso_aware(interval["end_at"])
        elif interval.get("start_minute") is not None and interval.get("end_minute") is not None:
            delta_m = int(interval["end_minute"]) - int(interval["start_minute"])
            if delta_m >= 0:
                planned_end = planned_start + timedelta(minutes=delta_m)

    measured_start: datetime | None = None
    measured_end: datetime | None = None
    if closed and applied:
        if applied.get("from_at"):
            measured_start = parse_iso_aware(applied["from_at"])
        elif applied.get("from_minute") is not None and trace.get("minute") is not None:
            measured_start = decided_at + timedelta(minutes=int(applied["from_minute"]) - int(trace["minute"]))
        if applied.get("to_at"):
            measured_end = parse_iso_aware(applied["to_at"])
        elif applied.get("to_minute") is not None and trace.get("minute") is not None:
            measured_end = decided_at + timedelta(minutes=int(applied["to_minute"]) - int(trace["minute"]))

    effective_start = decided_at
    effective_end: datetime | None = None
    stale_after_restart = False

    if closed:
        if applied.get("closed_at"):
            effective_end = parse_iso_aware(applied["closed_at"])
        elif coverage.get("expected_to_at"):
            effective_end = parse_iso_aware(coverage["expected_to_at"])
        elif coverage.get("expected_minutes") is not None:
            effective_end = decided_at + timedelta(minutes=max(0, int(coverage["expected_minutes"])))
        elif measured_end is not None:
            effective_end = measured_end
        elif applied.get("minutes") is not None:
            effective_end = decided_at + timedelta(minutes=max(0, int(applied["minutes"])))
        else:
            effective_end = decided_at
        if effective_end < effective_start:
            effective_end = effective_start
    else:
        # Active trace: must NEVER extend infinitely across restarts or superseding decisions.
        superseded_by_next = next_decided_at is not None and _utc(next_decided_at) >= _utc(decided_at)
        superseded_by_latest = latest_trace_key is not None and _sort_key(trace) < latest_trace_key
        not_live_open = live_open_known and cid != live_open_correlation_id
        if superseded_by_next or superseded_by_latest or not_live_open:
            stale_after_restart = True
            caps = [c for c in (next_decided_at, planned_end) if c is not None and _utc(c) >= _utc(decided_at)]
            effective_end = min(caps, key=_utc) if caps else decided_at
        else:
            # Currently active (or unconfirmed latest): bound by planned_end if present; if live_open confirmed
            # without planned_end, still do not invent an unbounded historical span beyond decided_at.
            effective_end = planned_end if planned_end is not None else decided_at

    is_point = effective_end is not None and _utc(effective_end) == _utc(effective_start)
    coverage_status = str(coverage.get("status") or ("not_evaluated" if not closed else "no_samples"))
    post_apply_status = str(validation.get("post_apply") or ("not_evaluated" if not closed else "no_samples"))

    provenance = TraceProvenance(
        correlation_id=cid,
        trace_schema=str(trace.get("trace_schema") or "unknown"),
        decided_at=decided_at,
        policy_id=str(policy.get("id") or "unknown"),
        policy_version=str(policy.get("version") or "unknown"),
        state_version=trace.get("state_version"),
        schedule_version=int(trace.get("schedule_version") or 0),
        closed=closed,
        planned_interval_start=planned_start,
        planned_interval_end=planned_end,
        effective_start=effective_start,
        effective_end=effective_end,
        measured_start=measured_start,
        measured_end=measured_end,
        coverage_status=coverage_status,
        post_apply_status=post_apply_status,
        stale_after_restart=stale_after_restart,
    )
    return ResolvedTrace(
        payload=trace,
        provenance=provenance,
        decided_at=decided_at,
        effective_start=effective_start,
        effective_end=effective_end,
        planned_start=planned_start,
        planned_end=planned_end,
        measured_start=measured_start,
        measured_end=measured_end,
        is_point_decision=is_point,
        stale_after_restart=stale_after_restart,
    )


def _matches_as_of(resolved: ResolvedTrace, at: datetime) -> bool:
    at_u = _utc(at)
    start_u = _utc(resolved.effective_start)
    if at_u < start_u:
        return False
    if resolved.is_point_decision:
        return at_u == start_u
    if resolved.effective_end is None:
        return True
    return at_u < _utc(resolved.effective_end)


def _matches_window(resolved: ResolvedTrace, window: TimeWindow) -> bool:
    w_start, w_end = _utc(window.start), _utc(window.end)
    t_start = _utc(resolved.effective_start)
    if resolved.is_point_decision:
        return w_start <= t_start < w_end
    if resolved.effective_end is None:
        return t_start < w_end
    t_end = _utc(resolved.effective_end)
    return t_start < w_end and t_end > w_start


def _window_has_gap(traces: Sequence[ResolvedTrace], window: TimeWindow) -> bool:
    w_start, w_end = _utc(window.start), _utc(window.end)
    intervals: list[tuple[datetime, datetime]] = []
    for item in traces:
        if item.is_point_decision or item.effective_end is None:
            continue
        seg_start = max(_utc(item.effective_start), w_start)
        seg_end = min(_utc(item.effective_end), w_end)
        if seg_end > seg_start:
            intervals.append((seg_start, seg_end))
    if not intervals:
        return True
    intervals.sort()
    merged_start, merged_end = intervals[0]
    if merged_start > w_start:
        return True
    for seg_start, seg_end in intervals[1:]:
        if seg_start > merged_end:
            return True
        if seg_end > merged_end:
            merged_end = seg_end
    return merged_end < w_end


def resolve_traces_from_records(
    raw_traces: Sequence[dict],
    *,
    at: datetime | None = None,
    window: TimeWindow | None = None,
    station_id: str | None = None,
    limit: int = 20,
    legacy_summary_only_count: int = 0,
    db_truncated: bool = False,
    next_trace_decided_at: datetime | None = None,
    latest_trace_meta: dict | None = None,
    live_open_correlation_id: str | None = None,
    live_open_known: bool = False,
) -> TemporalResolution:
    """Resolve matching traces with exact temporal overlap / as-of semantics."""
    filtered = [t for t in raw_traces if station_id is None or t.get("station_id") == station_id]
    ordered = sorted(filtered, key=_sort_key)

    latest_key: tuple | None = None
    if latest_trace_meta is not None:
        latest_key = (
            _utc(parse_iso_aware(latest_trace_meta["decided_at"])),
            int(latest_trace_meta.get("schedule_version") or 0),
            str(latest_trace_meta.get("correlation_id") or ""),
        )
    elif ordered:
        latest_key = _sort_key(ordered[-1])

    resolved_all: list[ResolvedTrace] = []
    for idx, trace in enumerate(ordered):
        decided_u = _utc(parse_iso_aware(trace["decided_at"]))
        next_dt: datetime | None = None
        for later in ordered[idx + 1 :]:
            later_dt = parse_iso_aware(later["decided_at"])
            if _utc(later_dt) > decided_u:
                next_dt = later_dt
                break
        if next_dt is None and next_trace_decided_at is not None and _utc(next_trace_decided_at) > decided_u:
            next_dt = next_trace_decided_at
        resolved_all.append(
            _trace_intervals(
                trace,
                next_decided_at=next_dt,
                latest_trace_key=latest_key,
                live_open_correlation_id=live_open_correlation_id,
                live_open_known=live_open_known,
            )
        )

    matched = [r for r in resolved_all if (_matches_as_of(r, at) if at is not None else _matches_window(r, window))]
    truncated = db_truncated or len(matched) > limit
    if len(matched) > limit:
        matched = matched[:limit]

    missing: list[str] = []
    if legacy_summary_only_count > 0:
        missing.append("legacy_summary_only_trace")
    if truncated:
        missing.append("trace_window_truncated")

    stale_count = sum(1 for r in matched if r.stale_after_restart)
    # Also check if a stale unclosed active trace existed prior to `at` and expired
    stale_expired = any(
        not r.provenance.closed
        and r.stale_after_restart
        and (
            (at is not None and r.effective_end is not None and _utc(at) >= _utc(r.effective_end))
            or (window is not None and r.effective_end is not None and _utc(window.end) > _utc(r.effective_end))
        )
        for r in resolved_all
    )
    if stale_count > 0 or stale_expired:
        missing.append("stale_active_trace_unclosed_after_restart")

    has_gap = False
    if window is not None and matched:
        has_gap = _window_has_gap(matched, window)
        if has_gap:
            missing.append("temporal_gap_in_window")

    exceeds_available = False
    if resolved_all:
        max_end = max(
            _utc(r.effective_end) if r.effective_end is not None else _utc(r.effective_start) for r in resolved_all
        )
        if at is not None and _utc(at) > max_end:
            exceeds_available = True
        elif window is not None and _utc(window.end) > max_end:
            exceeds_available = True
    if exceeds_available:
        missing.append("query_exceeds_available_evidence")

    return TemporalResolution(
        traces=matched,
        legacy_summary_only_count=legacy_summary_only_count,
        truncated=truncated,
        has_temporal_gap=has_gap,
        exceeds_available_evidence=exceeds_available,
        stale_active_traces_detected=stale_count + (1 if stale_expired and stale_count == 0 else 0),
        missing_evidence=list(dict.fromkeys(missing)),
    )


def fetch_temporal_traces(
    *,
    at: datetime | None = None,
    window: TimeWindow | None = None,
    booking_id: str | None = None,
    station_id: str | None = None,
    limit: int = 20,
    live_open_correlation_id: str | None = None,
    live_open_known: bool = False,
) -> TemporalResolution:
    """Read-only repository query + G1-F06 temporal overlap/as-of resolution."""
    if at is not None:
        start, end, inclusive_end = at, at, True
    else:
        assert window is not None
        start, end, inclusive_end = window.start, window.end, False

    raw = repository.list_decision_traces_for_temporal_lookup(
        start,
        end,
        booking_id=booking_id,
        inclusive_end=inclusive_end,
        limit=min(max(limit, 20), 100),
    )
    next_trace = raw["next_trace"]
    return resolve_traces_from_records(
        raw["traces"],
        at=at,
        window=window,
        station_id=station_id,
        limit=limit,
        legacy_summary_only_count=len(raw["legacy_summary_only_ids"]),
        db_truncated=bool(raw["truncated"]),
        next_trace_decided_at=next_trace["decided_at"] if next_trace else None,
        latest_trace_meta=raw["latest_trace"],
        live_open_correlation_id=live_open_correlation_id,
        live_open_known=live_open_known,
    )


def _sample_interval(sample: dict, decided_at: datetime, base_minute: int | None) -> tuple[datetime, datetime] | None:
    if sample.get("start_at") and sample.get("end_at"):
        return parse_iso_aware(sample["start_at"]), parse_iso_aware(sample["end_at"])
    if base_minute is not None and sample.get("start_minute") is not None and sample.get("end_minute") is not None:
        s_dt = decided_at + timedelta(minutes=int(sample["start_minute"]) - base_minute)
        e_dt = decided_at + timedelta(minutes=int(sample["end_minute"]) - base_minute)
        return s_dt, e_dt
    return None


def extract_measured_slice(
    resolved: ResolvedTrace,
    *,
    at: datetime | None = None,
    window: TimeWindow | None = None,
) -> SampleSlice:
    """Extract retained measured/held samples overlapping the query time/sub-window.

    Never copies a full-trace average into a sub-window: computes averages and energies
    exclusively from retained samples whose timestamps overlap the queried sub-window.
    """
    trace = resolved.payload
    power = trace.get("power") or {}
    actual_block = power.get("actual_output")
    held_block = power.get("effective_setpoint")
    base_minute = trace.get("minute")
    decided_at = resolved.decided_at

    conversion = 0.95
    planned = trace.get("planned") or {}
    limits = planned.get("physical_limits") or (trace.get("decision") or {}).get("physical_limits") or {}
    if limits.get("conversion_efficiency"):
        conversion = float(limits["conversion_efficiency"])
    elif (trace.get("guard_inputs") or {}).get("limits", {}).get("conversion"):
        conversion = float(trace["guard_inputs"]["limits"]["conversion"])

    raw_samples = list((actual_block or {}).get("samples") or [])
    raw_held = list((held_block or {}).get("samples") or [])

    if window is not None and resolved.effective_end is not None and not resolved.is_point_decision:
        clip_start = max(_utc(window.start), _utc(resolved.effective_start))
        clip_end = min(_utc(window.end), _utc(resolved.effective_end))
        is_subwindow = clip_start > _utc(resolved.effective_start) or clip_end < _utc(resolved.effective_end)
        expected_minutes: float | None = max(0.0, (clip_end - clip_start).total_seconds() / 60.0)
    elif at is not None:
        clip_start = _utc(at)
        clip_end = _utc(at)
        is_subwindow = not resolved.is_point_decision
        expected_minutes = None
    else:
        clip_start = _utc(resolved.effective_start)
        clip_end = _utc(resolved.effective_end) if resolved.effective_end else clip_start
        is_subwindow = False
        expected_minutes = max(0.0, (clip_end - clip_start).total_seconds() / 60.0)

    def _overlaps(s_start: datetime, s_end: datetime) -> bool:
        su, eu = _utc(s_start), _utc(s_end)
        if at is not None:
            return su <= clip_start < eu
        return su < clip_end and eu > clip_start

    matched_actual: list[dict] = []
    matched_held: list[dict] = []
    has_ts = True

    for sample in raw_samples:
        bounds = _sample_interval(sample, decided_at, base_minute)
        if bounds is None:
            has_ts = False
            continue
        if _overlaps(*bounds):
            matched_actual.append(sample)

    for sample in raw_held:
        bounds = _sample_interval(sample, decided_at, base_minute)
        if bounds is None:
            continue
        if _overlaps(*bounds):
            matched_held.append(sample)

    covered_minutes = sum(int(s["end_minute"]) - int(s["start_minute"]) for s in matched_actual)
    output_kwh: dict[str, float] = {}
    sample_minutes: dict[str, int] = {}
    for sample in matched_actual:
        dur = int(sample["end_minute"]) - int(sample["start_minute"])
        if dur <= 0:
            continue
        for vid, kw in (sample.get("by_booking_kw") or {}).items():
            output_kwh[vid] = output_kwh.get(vid, 0.0) + float(kw) * dur / 60.0
            sample_minutes[vid] = sample_minutes.get(vid, 0) + dur

    avg_kw = {vid: output_kwh[vid] * 60.0 / mins for vid, mins in sample_minutes.items() if mins > 0}
    grid_kwh = {vid: kwh / conversion for vid, kwh in output_kwh.items()}

    held_kw_min: dict[str, float] = {}
    held_min: dict[str, int] = {}
    for sample in matched_held:
        dur = int(sample["end_minute"]) - int(sample["start_minute"])
        if dur <= 0:
            continue
        for vid, kw in (sample.get("by_booking_kw") or {}).items():
            held_kw_min[vid] = held_kw_min.get(vid, 0.0) + float(kw) * dur
            held_min[vid] = held_min.get(vid, 0) + dur
    held_avg = {vid: held_kw_min[vid] / mins for vid, mins in held_min.items() if mins > 0}

    cov_status = resolved.provenance.coverage_status
    if not matched_actual:
        complete_for_window = False
    elif at is not None:
        complete_for_window = True
    elif expected_minutes is not None:
        complete_for_window = covered_minutes + 1e-6 >= expected_minutes and cov_status == "complete"
    else:
        complete_for_window = cov_status == "complete"

    return SampleSlice(
        samples=tuple(matched_actual),
        held_samples=tuple(matched_held),
        covered_minutes=covered_minutes,
        expected_window_minutes=expected_minutes,
        is_subwindow=is_subwindow,
        has_sample_timestamps=has_ts,
        complete_for_window=complete_for_window,
        output_kwh_by_booking=output_kwh,
        grid_input_kwh_by_booking=grid_kwh,
        average_output_kw_by_booking=avg_kw,
        sample_minutes_by_booking=sample_minutes,
        held_avg_kw_by_booking=held_avg,
    )
