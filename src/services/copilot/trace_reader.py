"""Temporal DecisionTrace reader, exact overlap integrator & as-of resolver (G1-F06 / G2-F01 / G2-F03 / G2-F04 / G2-F06).

Distinguishes distinct temporal intervals for every trace:
  1. Decision snapshot:   `decided_at` (instantaneous pre-dispatch observation).
  2. Planned interval:    [planned_start, planned_end) from decision-time `interval`.
  3. Effective interval:  [effective_start, effective_end) when the decision actually governed
                          (ends early on replan, capped on station-wide superseding decisions or restart).
  4. Measured coverage:   [measured_start, measured_end) covered by retained applied samples.
  5. Derivation interval: [derivation_start, derivation_end) of the exact overlap contributing to derived facts.

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


def encode_cursor(decided_at: datetime, schedule_version: int, correlation_id: str) -> str:
    return f"{decided_at.isoformat()}|{schedule_version}|{correlation_id}"


def decode_cursor(cursor: str) -> tuple[datetime, int, str]:
    parts = cursor.split("|", 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid pagination cursor: {cursor!r}")
    dt = parse_iso_aware(parts[0])
    if dt is None:
        raise ValueError(f"Invalid cursor timestamp: {cursor!r}")
    return dt, int(parts[1]), parts[2]


@dataclass(frozen=True)
class SampleContribution:
    """One non-overlapping sample interval contribution clipped to the queried window."""

    sample_index: int
    sample: dict
    sample_start: datetime
    sample_end: datetime
    overlap_start: datetime
    overlap_end: datetime
    overlap_minutes: float
    partial_overlap: bool


@dataclass(frozen=True)
class SampleSlice:
    """Measured power/energy strictly restricted to retained samples overlapping a query time/window."""

    is_point_query: bool
    samples: tuple[dict, ...]
    sample_contributions: tuple[SampleContribution, ...]
    held_samples: tuple[dict, ...]
    held_contributions: tuple[SampleContribution, ...]
    derivation_start: datetime | None
    derivation_end: datetime | None
    held_derivation_start: datetime | None
    held_derivation_end: datetime | None
    covered_minutes: float
    expected_window_minutes: float | None
    is_subwindow: bool
    has_sample_timestamps: bool
    has_partial_overlap: bool
    overlapping_samples_detected: bool
    complete_for_window: bool
    conversion_efficiency: float | None
    conversion_source_path: str | None
    output_kwh_by_booking: dict[str, float]
    grid_input_kwh_by_booking: dict[str, float]
    average_output_kw_by_booking: dict[str, float]
    sample_minutes_by_booking: dict[str, float]
    sample_indices_by_booking: dict[str, tuple[int, ...]]
    held_avg_kw_by_booking: dict[str, float]
    held_sample_indices_by_booking: dict[str, tuple[int, ...]]


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
    exceeds_live_physics_clock: bool = False


@dataclass(frozen=True)
class TemporalResolution:
    traces: list[ResolvedTrace]
    legacy_summary_only_count: int
    truncated: bool
    next_cursor: str | None
    has_temporal_gap: bool
    exceeds_available_evidence: bool
    exceeds_live_physics_clock: bool
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
    live_physics_clock: datetime | None = None,
    query_at: datetime | None = None,
    query_window: TimeWindow | None = None,
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
    exceeds_live_clock = False

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
        # Active trace: must NEVER extend infinitely across restarts or station-level superseding decisions.
        superseded_by_next = next_decided_at is not None and _utc(next_decided_at) >= _utc(decided_at)
        superseded_by_latest = latest_trace_key is not None and _sort_key(trace) < latest_trace_key
        not_live_open = live_open_known and cid != live_open_correlation_id
        if superseded_by_next or superseded_by_latest or not_live_open:
            stale_after_restart = True
            caps = [c for c in (next_decided_at, planned_end) if c is not None and _utc(c) >= _utc(decided_at)]
            effective_end = min(caps, key=_utc) if caps else decided_at
        else:
            effective_end = planned_end if planned_end is not None else decided_at
            if live_physics_clock is not None:
                clock_u = _utc(live_physics_clock)
                if query_at is not None and _utc(query_at) > clock_u:
                    exceeds_live_clock = True
                elif query_window is not None and _utc(query_window.end) > clock_u:
                    exceeds_live_clock = True

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
        exceeds_live_physics_clock=exceeds_live_clock,
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
    cursor: str | None = None,
    legacy_summary_only_count: int = 0,
    db_truncated: bool = False,
    station_timeline: Sequence[dict] | None = None,
    next_trace_decided_at: datetime | None = None,
    latest_trace_meta: dict | None = None,
    live_open_correlation_id: str | None = None,
    live_open_known: bool = False,
    live_physics_clock: datetime | None = None,
) -> TemporalResolution:
    """Resolve matching traces with exact temporal overlap / as-of semantics."""
    filtered = [t for t in raw_traces if station_id is None or t.get("station_id") == station_id]
    ordered = sorted(filtered, key=_sort_key)

    # Build unified station-wide sorted timestamps so booking-filtered queries see station-level superseding decisions
    timeline_dts: list[datetime] = []
    for item in ordered:
        dt = parse_iso_aware(item["decided_at"])
        if dt is not None:
            timeline_dts.append(dt)
    for meta in station_timeline or ():
        dt = parse_iso_aware(meta.get("decided_at"))
        if dt is not None:
            timeline_dts.append(dt)
    if next_trace_decided_at is not None:
        dt = parse_iso_aware(next_trace_decided_at)
        if dt is not None:
            timeline_dts.append(dt)
    timeline_dts.sort(key=_utc)

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
    for trace in ordered:
        decided_u = _utc(parse_iso_aware(trace["decided_at"]))
        next_dt = next((dt for dt in timeline_dts if _utc(dt) > decided_u), None)
        resolved_all.append(
            _trace_intervals(
                trace,
                next_decided_at=next_dt,
                latest_trace_key=latest_key,
                live_open_correlation_id=live_open_correlation_id,
                live_open_known=live_open_known,
                live_physics_clock=live_physics_clock,
                query_at=at,
                query_window=window,
            )
        )

    matched = [r for r in resolved_all if (_matches_as_of(r, at) if at is not None else _matches_window(r, window))]
    if cursor is not None:
        c_dt, c_ver, c_cid = decode_cursor(cursor)
        c_key = (_utc(c_dt), c_ver, c_cid)
        matched = [
            r
            for r in matched
            if (_utc(r.decided_at), r.provenance.schedule_version, r.provenance.correlation_id) > c_key
        ]

    truncated = db_truncated or len(matched) > limit
    if len(matched) > limit:
        matched = matched[:limit]

    next_cursor: str | None = None
    if truncated and matched:
        last = matched[-1]
        next_cursor = encode_cursor(last.decided_at, last.provenance.schedule_version, last.provenance.correlation_id)

    missing: list[str] = []
    if legacy_summary_only_count > 0:
        missing.append("legacy_summary_only_trace")
    if truncated:
        missing.append("trace_window_truncated")

    stale_count = sum(1 for r in matched if r.stale_after_restart)
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

    exceeds_live_clock = any(r.exceeds_live_physics_clock for r in matched)
    if exceeds_live_clock:
        missing.append("query_exceeds_live_physics_clock")

    has_gap = False
    if window is not None and matched and cursor is None:
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
        next_cursor=next_cursor,
        has_temporal_gap=has_gap,
        exceeds_available_evidence=exceeds_available,
        exceeds_live_physics_clock=exceeds_live_clock,
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
    cursor: str | None = None,
    live_open_correlation_id: str | None = None,
    live_open_known: bool = False,
    live_physics_clock: datetime | None = None,
) -> TemporalResolution:
    """Read-only repository query + G1-F06 / G2-F04 temporal overlap/as-of resolution."""
    if at is not None:
        start, end, inclusive_end = at, at, True
    else:
        assert window is not None
        start, end, inclusive_end = window.start, window.end, False

    parsed_cursor = decode_cursor(cursor) if cursor is not None else None
    raw = repository.list_decision_traces_for_temporal_lookup(
        start,
        end,
        booking_id=booking_id,
        inclusive_end=inclusive_end,
        limit=min(max(limit, 1), 100),
        cursor=parsed_cursor,
    )
    next_trace = raw["next_trace"]
    return resolve_traces_from_records(
        raw["traces"],
        at=at,
        window=window,
        station_id=station_id,
        limit=limit,
        cursor=cursor,
        legacy_summary_only_count=len(raw["legacy_summary_only_ids"]),
        db_truncated=bool(raw["truncated"]),
        station_timeline=raw.get("station_timeline"),
        next_trace_decided_at=next_trace["decided_at"] if next_trace else None,
        latest_trace_meta=raw["latest_trace"],
        live_open_correlation_id=live_open_correlation_id,
        live_open_known=live_open_known,
        live_physics_clock=live_physics_clock,
    )


def _sample_interval(sample: dict, decided_at: datetime, base_minute: int | None) -> tuple[datetime, datetime] | None:
    if sample.get("start_at") and sample.get("end_at"):
        return parse_iso_aware(sample["start_at"]), parse_iso_aware(sample["end_at"])
    if base_minute is not None and sample.get("start_minute") is not None and sample.get("end_minute") is not None:
        s_dt = decided_at + timedelta(minutes=int(sample["start_minute"]) - base_minute)
        e_dt = decided_at + timedelta(minutes=int(sample["end_minute"]) - base_minute)
        return s_dt, e_dt
    return None


def _resolve_conversion_efficiency(trace: dict) -> tuple[float | None, str | None]:
    """Return decision-time conversion efficiency and its canonical JSON pointer, NEVER a silent default."""
    planned_limits = (trace.get("planned") or {}).get("physical_limits") or {}
    val = planned_limits.get("conversion_efficiency")
    if isinstance(val, (int, float)) and val > 0:
        return float(val), "/planned/physical_limits/conversion_efficiency"
    decision_limits = (trace.get("decision") or {}).get("physical_limits") or {}
    val = decision_limits.get("conversion_efficiency")
    if isinstance(val, (int, float)) and val > 0:
        return float(val), "/decision/physical_limits/conversion_efficiency"
    guard_limits = (trace.get("guard_inputs") or {}).get("limits") or {}
    val = guard_limits.get("conversion")
    if isinstance(val, (int, float)) and val > 0:
        return float(val), "/guard_inputs/limits/conversion"
    return None, None


def _clip_non_overlapping_samples(
    raw_samples: Sequence[dict],
    *,
    decided_at: datetime,
    base_minute: int | None,
    at: datetime | None,
    clip_start: datetime,
    clip_end: datetime,
) -> tuple[list[SampleContribution], bool, bool]:
    """Select samples overlapping `at` or `[clip_start, clip_end)` with exact non-double-counted overlap."""
    parsed: list[tuple[int, dict, datetime, datetime]] = []
    has_ts = True
    for idx, sample in enumerate(raw_samples):
        bounds = _sample_interval(sample, decided_at, base_minute)
        if bounds is None:
            has_ts = False
            continue
        s_start, s_end = bounds
        if _utc(s_end) <= _utc(s_start):
            continue
        parsed.append((idx, sample, s_start, s_end))

    parsed.sort(key=lambda item: (_utc(item[2]), _utc(item[3]), item[0]))

    contributions: list[SampleContribution] = []
    overlapping_detected = False

    if at is not None:
        at_u = _utc(at)
        for idx, sample, s_start, s_end in parsed:
            if _utc(s_start) <= at_u < _utc(s_end):
                if contributions:
                    overlapping_detected = True
                    continue
                dur_min = (_utc(s_end) - _utc(s_start)).total_seconds() / 60.0
                contributions.append(
                    SampleContribution(
                        sample_index=idx,
                        sample=sample,
                        sample_start=s_start,
                        sample_end=s_end,
                        overlap_start=s_start,
                        overlap_end=s_end,
                        overlap_minutes=dur_min,
                        partial_overlap=False,
                    )
                )
        return contributions, has_ts, overlapping_detected

    high_water: datetime | None = None
    for idx, sample, s_start, s_end in parsed:
        su, eu = _utc(s_start), _utc(s_end)
        if eu <= clip_start or su >= clip_end:
            continue
        eff_s = max(su, clip_start)
        eff_e = min(eu, clip_end)
        if high_water is not None and eff_s < high_water:
            overlapping_detected = True
            eff_s = high_water
        if eff_e <= eff_s:
            continue
        high_water = eff_e
        tz = s_start.tzinfo or decided_at.tzinfo
        ov_start = eff_s.astimezone(tz) if tz is not None else eff_s
        ov_end = eff_e.astimezone(tz) if tz is not None else eff_e
        ov_minutes = (eff_e - eff_s).total_seconds() / 60.0
        partial = eff_s > su or eff_e < eu
        contributions.append(
            SampleContribution(
                sample_index=idx,
                sample=sample,
                sample_start=s_start,
                sample_end=s_end,
                overlap_start=ov_start,
                overlap_end=ov_end,
                overlap_minutes=ov_minutes,
                partial_overlap=partial,
            )
        )
    return contributions, has_ts, overlapping_detected


def extract_measured_slice(
    resolved: ResolvedTrace,
    *,
    at: datetime | None = None,
    window: TimeWindow | None = None,
) -> SampleSlice:
    """Extract retained measured/held samples with exact overlap duration (G2-F01 / G2-F03 / G2-F06).

    - Uses exact clipped overlap duration (piecewise-constant power within each sample).
    - Deduplicates overlapping sample intervals so energy is never double-counted.
    - For `at` (as-of point query): returns power at the active sample without computing
      accumulated interval energy.
    - Never silently falls back to default conversion efficiency (0.95).
    """
    trace = resolved.payload
    power = trace.get("power") or {}
    actual_block = power.get("actual_output")
    held_block = power.get("effective_setpoint")
    base_minute = trace.get("minute")
    decided_at = resolved.decided_at

    conversion, conversion_path = _resolve_conversion_efficiency(trace)

    raw_samples = list((actual_block or {}).get("samples") or [])
    raw_held = list((held_block or {}).get("samples") or [])

    is_point_query = at is not None
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

    actual_contribs, has_ts, actual_overlap_dup = _clip_non_overlapping_samples(
        raw_samples, decided_at=decided_at, base_minute=base_minute, at=at, clip_start=clip_start, clip_end=clip_end
    )
    held_contribs, _, held_overlap_dup = _clip_non_overlapping_samples(
        raw_held, decided_at=decided_at, base_minute=base_minute, at=at, clip_start=clip_start, clip_end=clip_end
    )

    covered_minutes = sum(c.overlap_minutes for c in actual_contribs)
    has_partial_overlap = any(c.partial_overlap for c in actual_contribs) or any(
        c.partial_overlap for c in held_contribs
    )

    output_kwh: dict[str, float] = {}
    sample_minutes: dict[str, float] = {}
    weighted_kw_min: dict[str, float] = {}
    indices_by_booking: dict[str, list[int]] = {}
    for c in actual_contribs:
        if c.overlap_minutes <= 0:
            continue
        for vid, kw in (c.sample.get("by_booking_kw") or {}).items():
            fkw = float(kw)
            weighted_kw_min[vid] = weighted_kw_min.get(vid, 0.0) + fkw * c.overlap_minutes
            sample_minutes[vid] = sample_minutes.get(vid, 0.0) + c.overlap_minutes
            indices_by_booking.setdefault(vid, []).append(c.sample_index)
            if not is_point_query:
                output_kwh[vid] = output_kwh.get(vid, 0.0) + fkw * c.overlap_minutes / 60.0

    avg_kw = {vid: weighted_kw_min[vid] / mins for vid, mins in sample_minutes.items() if mins > 0}
    grid_kwh = (
        {vid: kwh / conversion for vid, kwh in output_kwh.items()}
        if (not is_point_query and conversion is not None)
        else {}
    )

    held_kw_min: dict[str, float] = {}
    held_min: dict[str, float] = {}
    held_indices_by_booking: dict[str, list[int]] = {}
    for c in held_contribs:
        if c.overlap_minutes <= 0:
            continue
        for vid, kw in (c.sample.get("by_booking_kw") or {}).items():
            held_kw_min[vid] = held_kw_min.get(vid, 0.0) + float(kw) * c.overlap_minutes
            held_min[vid] = held_min.get(vid, 0.0) + c.overlap_minutes
            held_indices_by_booking.setdefault(vid, []).append(c.sample_index)
    held_avg = {vid: held_kw_min[vid] / mins for vid, mins in held_min.items() if mins > 0}

    derivation_start = actual_contribs[0].overlap_start if actual_contribs else None
    derivation_end = actual_contribs[-1].overlap_end if actual_contribs else None
    held_deriv_start = held_contribs[0].overlap_start if held_contribs else None
    held_deriv_end = held_contribs[-1].overlap_end if held_contribs else None

    cov_status = resolved.provenance.coverage_status
    if not actual_contribs:
        complete_for_window = False
    elif is_point_query:
        complete_for_window = True
    elif expected_minutes is not None:
        complete_for_window = covered_minutes + 1e-6 >= expected_minutes and cov_status == "complete"
    else:
        complete_for_window = cov_status == "complete"

    return SampleSlice(
        is_point_query=is_point_query,
        samples=tuple(c.sample for c in actual_contribs),
        sample_contributions=tuple(actual_contribs),
        held_samples=tuple(c.sample for c in held_contribs),
        held_contributions=tuple(held_contribs),
        derivation_start=derivation_start,
        derivation_end=derivation_end,
        held_derivation_start=held_deriv_start,
        held_derivation_end=held_deriv_end,
        covered_minutes=covered_minutes,
        expected_window_minutes=expected_minutes,
        is_subwindow=is_subwindow,
        has_sample_timestamps=has_ts,
        has_partial_overlap=has_partial_overlap,
        overlapping_samples_detected=actual_overlap_dup or held_overlap_dup,
        complete_for_window=complete_for_window,
        conversion_efficiency=conversion,
        conversion_source_path=conversion_path,
        output_kwh_by_booking=output_kwh,
        grid_input_kwh_by_booking=grid_kwh,
        average_output_kw_by_booking=avg_kw,
        sample_minutes_by_booking=sample_minutes,
        sample_indices_by_booking={k: tuple(v) for k, v in indices_by_booking.items()},
        held_avg_kw_by_booking=held_avg,
        held_sample_indices_by_booking={k: tuple(v) for k, v in held_indices_by_booking.items()},
    )
