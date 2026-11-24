"""Authorization, privacy projection, JSON Pointer resolution, and EvidenceCollector (WP2.4 / G2-F02 / G2-F07).

Invariants enforced here:
- Role and actor identity come exclusively from trusted server-side `ActorContext`.
- Resident ownership is verified against both active and historical bookings.
- Resident unauthorized ID and nonexistent ID yield identical non-enumerating FORBIDDEN responses.
- `resolve_evidence_ref` requires trusted authorization context (verified `AuthorizedSubject` or `Booking`
  ownership match) and validates ref_id/source_path/schema/correlation/policy/decided_at/subject/temporal consistency.
- `EvidenceCollector.add_fact` verifies direct facts against canonical trace fields and requires explicit
  `derivation_op` + validated `input_evidence_refs` for derived facts.
- `EvidenceCollector.add_reason` validates correlation_id & provenance consistency for all referenced facts/refs.
- Resident EvidenceRefs and serialized WhyAnswers use explicit safe projection + defense-in-depth screening.
"""

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src.models.charging import Booking
from src.models.control import Role
from src.models.copilot import (
    ActorContext,
    DerivationOp,
    EvidenceCategory,
    EvidenceRef,
    FactDerivationKind,
    FactStage,
    TemporalBasis,
    WhyAnswer,
    WhyFact,
    WhyQuery,
    WhyReason,
    WhyStatus,
    WhySubjectScope,
)
from src.services.copilot.trace_reader import ResolvedTrace, parse_iso_aware


def encode_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def decode_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def resolve_json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    """RFC 6901 JSON Pointer dereference. Returns (found, value)."""
    if not pointer or not pointer.startswith("/"):
        return False, None
    current = document
    for raw_token in pointer.split("/")[1:]:
        token = decode_pointer_token(raw_token)
        if isinstance(current, dict):
            if token not in current:
                return False, None
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit():
                return False, None
            index = int(token)
            if not (0 <= index < len(current)):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


@dataclass(frozen=True)
class AuthorizedSubject:
    """Trusted authorization context produced only after server-side ownership verification."""

    actor: ActorContext
    station_id: str
    own_booking_id: str | None = None


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    status: WhyStatus
    subject_id: str | None
    booking: Booking | None
    missing_evidence: tuple[str, ...] = ()
    authorized_subject: AuthorizedSubject | None = None


def authorize_why_query(
    query: WhyQuery,
    actor: ActorContext,
    *,
    station_id: str,
    get_booking: Callable[[str], Booking | None],
    active_booking: Callable[[str], Booking | None],
    list_resident_bookings: Callable[[str], list[Booking]],
) -> AuthorizationResult:
    """Enforce role/scope authorization without acting as an ID-existence oracle."""
    if actor.station_id != station_id:
        return AuthorizationResult(False, WhyStatus.FORBIDDEN, None, None, ("station_not_accessible",))

    if actor.role == Role.RESIDENT:
        if query.subject_scope == WhySubjectScope.STATION:
            return AuthorizationResult(False, WhyStatus.FORBIDDEN, None, None, ("station_scope_forbidden",))
        if query.booking_id is not None:
            booking = get_booking(query.booking_id)
            if booking is None or booking.resident_id != actor.actor_id:
                return AuthorizationResult(False, WhyStatus.FORBIDDEN, None, None, ("booking_not_accessible",))
            return AuthorizationResult(
                True,
                WhyStatus.OK,
                booking.booking_id,
                booking,
                authorized_subject=AuthorizedSubject(
                    actor=actor, station_id=station_id, own_booking_id=booking.booking_id
                ),
            )
        booking = active_booking(actor.actor_id)
        if booking is None:
            history = list_resident_bookings(actor.actor_id)
            booking = max(history, key=lambda b: b.created_at) if history else None
        if booking is None:
            return AuthorizationResult(False, WhyStatus.NO_DATA, None, None, ("no_booking_for_actor",))
        return AuthorizationResult(
            True,
            WhyStatus.OK,
            booking.booking_id,
            booking,
            authorized_subject=AuthorizedSubject(actor=actor, station_id=station_id, own_booking_id=booking.booking_id),
        )

    if actor.role == Role.OPERATOR:
        if query.subject_scope == WhySubjectScope.OWN_BOOKING:
            return AuthorizationResult(False, WhyStatus.FORBIDDEN, None, None, ("operator_cannot_use_own_booking",))
        if query.subject_scope == WhySubjectScope.STATION:
            return AuthorizationResult(
                True,
                WhyStatus.OK,
                station_id,
                None,
                authorized_subject=AuthorizedSubject(actor=actor, station_id=station_id),
            )
        assert query.booking_id is not None
        booking = get_booking(query.booking_id)
        if booking is None:
            return AuthorizationResult(False, WhyStatus.NO_DATA, query.booking_id, None, ("booking_not_found",))
        return AuthorizationResult(
            True,
            WhyStatus.OK,
            booking.booking_id,
            booking,
            authorized_subject=AuthorizedSubject(actor=actor, station_id=station_id),
        )

    return AuthorizationResult(False, WhyStatus.FORBIDDEN, None, None, ("role_not_supported",))


def authorize_evidence_subject(
    actor: ActorContext,
    *,
    station_id: str,
    booking: Booking | None = None,
) -> AuthorizedSubject | None:
    """Build a verified AuthorizedSubject for evidence dereferencing (never trusts arbitrary booking IDs)."""
    if actor.station_id != station_id:
        return None
    if actor.role == Role.OPERATOR:
        return AuthorizedSubject(actor=actor, station_id=station_id)
    if actor.role == Role.RESIDENT:
        if booking is None or booking.resident_id != actor.actor_id:
            return None
        return AuthorizedSubject(actor=actor, station_id=station_id, own_booking_id=booking.booking_id)
    return None


# Explicit leaf / safe scalar paths allowed for Resident (never raw cross-resident dicts or unprojected objects).
_RESIDENT_SAFE_EXACT_PATHS = frozenset(
    {
        "/policy/id",
        "/policy/version",
        "/experiment/policy_id",
        "/experiment/policy_version",
        "/experiment/dc_charging_model/name",
        "/experiment/dc_charging_model/version",
        "/experiment/fingerprint",
        "/state_version",
        "/schedule_version",
        "/minute",
        "/interval/start_minute",
        "/interval/end_minute",
        "/interval/start_at",
        "/interval/end_at",
        "/interval/planning_interval_minutes",
        "/validation/pre_apply_physical",
        "/validation/post_apply",
        "/validation/fail_safe/status",
        "/applied/coverage/status",
        "/applied/coverage/expected_minutes",
        "/applied/coverage/retained_minutes",
        "/applied/coverage/dropped_minutes",
        "/applied/coverage/dropped_hard_violations",
        "/planned/minute",
        "/planned/end_minute",
        "/planned/physical_limits/supply_mode",
        "/planned/physical_limits/grid_input_kw",
        "/planned/physical_limits/grid_input_unbounded",
        "/planned/physical_limits/conversion_efficiency",
        "/planned/physical_limits/charging_efficiency",
        "/decision/physical_limits/conversion_efficiency",
        "/decision/physical_limits/charging_efficiency",
        "/guard_inputs/limits/conversion",
        "/planned/coordinator/policy",
        "/planned/coordinator/fallback_reason",
        "/planned/observed/faulted_connectors",
    }
)


def is_pointer_authorized_for_resident(pointer: str, trace: dict, own_booking_id: str) -> bool:
    """Explicit safe-projection allowlist for Resident JSON Pointers (G2-F07)."""
    if not pointer or not pointer.startswith("/"):
        return False
    tokens = [decode_pointer_token(t) for t in pointer.split("/")[1:]]
    if not tokens:
        return False

    found, value = resolve_json_pointer(trace, pointer)
    if not found:
        return False

    # Exact safe station-level scalar/leaf paths
    if pointer in _RESIDENT_SAFE_EXACT_PATHS:
        return not _contains_any_id(value, _other_booking_ids(trace, own_booking_id))

    # Zone aggregate summary leaves (counts only)
    if len(tokens) == 5 and tokens[:3] == ["planned", "observed", "zone_summary"]:
        if tokens[4] in ("total_ports", "occupied_ports", "empty_ports", "faulted_ports", "waiting_count"):
            return True
        return False

    # Zone-level physical limits leaves
    if len(tokens) == 4 and tokens[:2] == ["planned", "physical_limits"]:
        if tokens[2] in ("zone_output_kw", "independent_grid_input_kw", "port_output_kw"):
            return True
        return False

    # Zone-level coordinator budget / reason code leaves
    if len(tokens) == 4 and tokens[:2] == ["planned", "coordinator"]:
        if tokens[2] in ("assigned_output_kw", "default_zone_budget_kw"):
            return True
        return False
    if len(tokens) == 5 and tokens[:3] == ["planned", "coordinator", "reason_codes"] and tokens[4].isdigit():
        return True

    # Zone-level optimizer status/fallback leaves + own projected shortfall only
    if len(tokens) >= 4 and tokens[:2] == ["planned", "optimizers"]:
        field = tokens[3]
        if field in ("policy", "solver_status", "fallback_reason") and len(tokens) == 4:
            return True
        if field == "stage_status" and len(tokens) == 5:
            return True
        if field in ("projected_shortfall_kwh", "projection_cutoff_minute"):
            return len(tokens) == 5 and tokens[4] == own_booking_id
        return False

    # Dispatch policy leaf only
    if len(tokens) == 4 and tokens[:2] == ["planned", "dispatch"] and tokens[3] == "policy":
        return True

    # Own booking scoped leaves
    if len(tokens) >= 4 and tokens[:3] == ["safety", "by_booking", own_booking_id]:
        return True
    if len(tokens) >= 5 and tokens[:4] == ["planned", "observed", "vehicles", own_booking_id]:
        return True
    if len(tokens) >= 4 and tokens[:3] == ["planned", "dc_waiting_laxity", own_booking_id]:
        return True
    if len(tokens) == 4 and tokens[0] == "power" and tokens[1] in ("proposed", "approved"):
        return tokens[2] == "by_booking_kw" and tokens[3] == own_booking_id
    if len(tokens) == 4 and tokens[:3] == ["power", "actual_output", "average_by_booking_kw"]:
        return tokens[3] == own_booking_id
    if len(tokens) == 4 and tokens[:3] == ["power", "actual_output", "sample_minutes_by_booking"]:
        return tokens[3] == own_booking_id
    if len(tokens) == 6 and tokens[0] == "power" and tokens[1] in ("actual_output", "effective_setpoint"):
        return (
            tokens[2] == "samples"
            and tokens[3].isdigit()
            and tokens[4] == "by_booking_kw"
            and tokens[5] == own_booking_id
        )
    if (
        len(tokens) == 3
        and tokens[0] == "applied"
        and tokens[1] in ("output_kwh", "grid_input_kwh", "battery_stored_kwh")
    ):
        return tokens[2] == own_booking_id
    if len(tokens) >= 4 and tokens[:3] == ["applied", "completed_by_booking", own_booking_id]:
        return True
    if len(tokens) == 3 and tokens[:2] == ["consent", "adjustments_kw"] and tokens[2] == own_booking_id:
        return True

    # Binding constraint leaf (kw/limit/id) for non-foreign binding constraint
    if (
        len(tokens) in (3, 4)
        and tokens[:2] == ["planned", "binding_constraints"]
        and tokens[2].isdigit()
        and (len(tokens) == 3 or tokens[3] in ("kw", "limit", "id", "stage"))
    ):
        item_ok, item = resolve_json_pointer(trace, f"/planned/binding_constraints/{tokens[2]}")
        if not item_ok or not isinstance(item, dict):
            return False
        if item.get("limit") == "individual_allowed_output":
            return item.get("id") == own_booking_id
        return not _contains_any_id(item, _other_booking_ids(trace, own_booking_id))

    # Command / emergency_command / command_exclusion leaf: ONLY if row.booking_id == own_booking_id
    if (
        len(tokens) >= 3
        and tokens[0] in ("commands", "emergency_commands", "command_exclusions")
        and tokens[1].isdigit()
    ):
        row_found, row = resolve_json_pointer(trace, f"/{tokens[0]}/{tokens[1]}")
        if not row_found or not isinstance(row, dict):
            return False
        return row.get("booking_id") == own_booking_id

    return False


def _implied_booking_from_pointer(pointer: str, trace: dict) -> str | None:
    """If `pointer` directly addresses a specific booking's record, return that booking ID."""
    tokens = [decode_pointer_token(t) for t in pointer.split("/")[1:]]
    if len(tokens) >= 4 and tokens[:3] == ["planned", "observed", "vehicles"]:
        return tokens[3]
    if len(tokens) >= 3 and tokens[:2] == ["planned", "dc_waiting_laxity"]:
        return tokens[2]
    if len(tokens) >= 3 and tokens[:2] == ["safety", "by_booking"]:
        return tokens[2]
    if (
        len(tokens) == 4
        and tokens[0] == "power"
        and tokens[1] in ("proposed", "approved")
        and tokens[2] == "by_booking_kw"
    ):
        return tokens[3]
    if len(tokens) == 4 and tokens[:3] in (
        ["power", "actual_output", "average_by_booking_kw"],
        ["power", "actual_output", "sample_minutes_by_booking"],
    ):
        return tokens[3]
    if len(tokens) == 6 and tokens[0] == "power" and tokens[2] == "samples" and tokens[4] == "by_booking_kw":
        return tokens[5]
    if (
        len(tokens) >= 3
        and tokens[0] == "applied"
        and tokens[1]
        in (
            "output_kwh",
            "grid_input_kwh",
            "battery_stored_kwh",
            "completed_by_booking",
        )
    ):
        return tokens[2]
    if len(tokens) == 3 and tokens[:2] == ["consent", "adjustments_kw"]:
        return tokens[2]
    if (
        len(tokens) == 5
        and tokens[:2] == ["planned", "optimizers"]
        and tokens[3]
        in (
            "projected_shortfall_kwh",
            "projection_cutoff_minute",
        )
    ):
        return tokens[4]
    if (
        len(tokens) >= 2
        and tokens[0] in ("commands", "emergency_commands", "command_exclusions")
        and tokens[1].isdigit()
    ):
        ok, row = resolve_json_pointer(trace, f"/{tokens[0]}/{tokens[1]}")
        if ok and isinstance(row, dict) and row.get("booking_id"):
            return str(row["booking_id"])
    if len(tokens) >= 3 and tokens[:2] == ["planned", "binding_constraints"] and tokens[2].isdigit():
        ok, row = resolve_json_pointer(trace, f"/planned/binding_constraints/{tokens[2]}")
        if ok and isinstance(row, dict) and row.get("limit") == "individual_allowed_output" and row.get("id"):
            return str(row["id"])
    return None


def _validate_ref_temporal_bounds(ref: EvidenceRef, trace: dict) -> bool:
    if ref.interval_start is None and ref.interval_end is None:
        return True
    if ref.interval_start is None or ref.interval_end is None:
        return False
    r_start = ref.interval_start.astimezone(UTC)
    r_end = ref.interval_end.astimezone(UTC)
    if r_end < r_start:
        return False

    decided = parse_iso_aware(trace.get("decided_at"))
    if decided is None:
        return False
    decided_u = decided.astimezone(UTC)
    tokens = [decode_pointer_token(t) for t in ref.source_path.split("/")[1:]]

    # If referencing a specific power sample, verify interval lies inside that sample's bounds
    if (
        len(tokens) >= 4
        and tokens[0] == "power"
        and tokens[1] in ("actual_output", "effective_setpoint")
        and tokens[2] == "samples"
        and tokens[3].isdigit()
    ):
        ok, sample = resolve_json_pointer(trace, f"/power/{tokens[1]}/samples/{tokens[3]}")
        if not ok or not isinstance(sample, dict):
            return False
        s_start = parse_iso_aware(sample.get("start_at"))
        s_end = parse_iso_aware(sample.get("end_at"))
        if s_start is None or s_end is None:
            base_min = trace.get("minute")
            if base_min is not None and sample.get("start_minute") is not None and sample.get("end_minute") is not None:
                s_start = decided + timedelta(minutes=int(sample["start_minute"]) - int(base_min))
                s_end = decided + timedelta(minutes=int(sample["end_minute"]) - int(base_min))
        if s_start is not None and s_end is not None:
            return r_start >= s_start.astimezone(UTC) and r_end <= s_end.astimezone(UTC)
        return True

    # General trace upper bound check (planned_end or closed_at or measured_end)
    upper_candidates: list[datetime] = [decided_u]
    interval = trace.get("interval") or {}
    if interval.get("end_at"):
        dt = parse_iso_aware(interval["end_at"])
        if dt is not None:
            upper_candidates.append(dt.astimezone(UTC))
    applied = trace.get("applied") or {}
    for key in ("closed_at", "to_at"):
        if applied.get(key):
            dt = parse_iso_aware(applied[key])
            if dt is not None:
                upper_candidates.append(dt.astimezone(UTC))
    max_upper = max(upper_candidates)
    return r_start >= decided_u and r_end <= max_upper


def resolve_evidence_ref(
    ref: EvidenceRef,
    trace: dict,
    actor: ActorContext,
    *,
    authorized_subject: AuthorizedSubject | None = None,
    booking: Booking | None = None,
) -> tuple[bool, Any]:
    """Authorized, provenance-checked dereferencing of an EvidenceRef against a trace payload (G2-F07).

    Requires a verified `authorized_subject` (or `booking` verified against `actor.actor_id`) for
    Resident callers — never accepts an unverified arbitrary booking ID string.
    """
    # 1. Structural & provenance consistency checks
    expected_ref_id = f"{ref.correlation_id}:{ref.trace_schema}#{ref.source_path}"
    if ref.ref_id != expected_ref_id:
        return False, None
    if trace.get("correlation_id") != ref.correlation_id:
        return False, None
    if trace.get("trace_schema") != ref.trace_schema:
        return False, None
    if trace.get("station_id") != actor.station_id:
        return False, None

    policy = trace.get("policy") or {}
    if str(policy.get("id") or "unknown") != ref.policy_id:
        return False, None
    if str(policy.get("version") or "unknown") != ref.policy_version:
        return False, None

    trace_decided = parse_iso_aware(trace.get("decided_at"))
    if trace_decided is None or trace_decided.astimezone(UTC) != ref.decided_at.astimezone(UTC):
        return False, None

    # 2. Subject consistency with source_path
    implied_booking = _implied_booking_from_pointer(ref.source_path, trace)
    if implied_booking is not None and ref.subject != implied_booking:
        return False, None

    # 3. Temporal interval consistency
    if not _validate_ref_temporal_bounds(ref, trace):
        return False, None

    # 4. Role & ownership authorization
    if actor.role == Role.RESIDENT:
        own_id: str | None = None
        if authorized_subject is not None:
            if authorized_subject.actor != actor or authorized_subject.station_id != actor.station_id:
                return False, None
            own_id = authorized_subject.own_booking_id
        elif booking is not None:
            if booking.resident_id != actor.actor_id:
                return False, None
            own_id = booking.booking_id
        if not own_id:
            return False, None
        if implied_booking is not None and implied_booking != own_id:
            return False, None
        if not is_pointer_authorized_for_resident(ref.source_path, trace, own_id):
            return False, None
    elif actor.role == Role.OPERATOR:
        if authorized_subject is not None and (
            authorized_subject.actor != actor or authorized_subject.station_id != actor.station_id
        ):
            return False, None
    else:
        return False, None

    return resolve_json_pointer(trace, ref.source_path)


def _other_booking_ids(trace: dict, own_booking_id: str) -> set[str]:
    found: set[str] = set()
    for vid in trace.get("booking_ids") or ():
        if vid and vid != own_booking_id:
            found.add(str(vid))
    planned = trace.get("planned") or {}
    for vid in (planned.get("observed") or {}).get("vehicles") or {}:
        if vid and vid != own_booking_id:
            found.add(str(vid))
    for zone_q in ((planned.get("observed") or {}).get("queues_by_zone") or {}).values():
        for vid in zone_q or ():
            if vid and vid != own_booking_id:
                found.add(str(vid))
    for vid in (trace.get("safety") or {}).get("held_booking_ids") or ():
        if vid and vid != own_booking_id:
            found.add(str(vid))
    for row in (
        (trace.get("commands") or [])
        + (trace.get("emergency_commands") or [])
        + (trace.get("command_exclusions") or [])
    ):
        vid = row.get("booking_id")
        if vid and vid != own_booking_id:
            found.add(str(vid))
    return found


def _contains_any_id(value: Any, forbidden_ids: set[str]) -> bool:
    if not forbidden_ids:
        return False
    blob = json.dumps(value, ensure_ascii=False)
    for item in forbidden_ids:
        if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(item)}(?![A-Za-z0-9_-])", blob):
            return True
    return False


def verify_privacy_projection(
    answer: WhyAnswer,
    actor: ActorContext,
    traces: list[ResolvedTrace],
    *,
    authorized_subject: AuthorizedSubject | None = None,
) -> None:
    """Explicit projection + defense-in-depth gate over the entire serialized WhyAnswer for Resident callers."""
    if actor.role != Role.RESIDENT:
        return
    if authorized_subject is None or authorized_subject.actor != actor or not authorized_subject.own_booking_id:
        raise PermissionError("Resident privacy projection requires verified AuthorizedSubject")
    own_booking_id = authorized_subject.own_booking_id

    forbidden: set[str] = set()
    for item in traces:
        forbidden.update(_other_booking_ids(item.payload, own_booking_id))

    # Explicit structural check on every reason's params & summary
    for reason in answer.reasons:
        if reason.subject not in (own_booking_id, "station"):
            raise PermissionError(f"Resident reason has disallowed subject {reason.subject!r}")
        if _contains_any_id(reason.params, forbidden) or _contains_any_id(reason.summary, forbidden):
            raise PermissionError(f"Resident reason {reason.code!r} contains cross-resident metadata")

    # Full serialized defense-in-depth scan
    serialized = json.dumps(answer.model_dump(mode="json"), ensure_ascii=False)
    for bad in sorted(forbidden):
        if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(bad)}(?![A-Za-z0-9_-])", serialized):
            raise PermissionError(f"Resident privacy projection violation: leaked booking reference {bad!r}")

    # Verify every EvidenceRef in the answer passes full provenance + resident authorization
    by_cid = {item.provenance.correlation_id: item.payload for item in traces}
    for ref in answer.evidence_refs:
        trace = by_cid.get(ref.correlation_id)
        if trace is None:
            raise PermissionError(f"Unverified resident evidence ref {ref.ref_id!r}")
        ok, _ = resolve_evidence_ref(ref, trace, actor, authorized_subject=authorized_subject)
        if not ok:
            raise PermissionError(f"Unauthorized or inconsistent resident evidence ref {ref.source_path!r}")


def _direct_values_match(raw: Any, claimed: float | int | str | bool | None) -> bool:
    if raw is None or claimed is None:
        return raw is None and claimed is None
    if isinstance(raw, bool) or isinstance(claimed, bool):
        return isinstance(raw, bool) and isinstance(claimed, bool) and raw is claimed
    if isinstance(raw, (int, float)) and isinstance(claimed, (int, float)):
        return abs(float(raw) - float(claimed)) <= 1e-5
    return raw == claimed


class EvidenceCollector:
    """Builds validated, deduplicated EvidenceRefs, WhyFacts, and WhyReasons for one WhyAnswer."""

    def __init__(
        self,
        actor: ActorContext,
        *,
        authorized_subject: AuthorizedSubject | None = None,
        own_booking_id: str | None = None,
    ) -> None:
        self.actor = actor
        self.authorized_subject = authorized_subject
        self.own_booking_id = authorized_subject.own_booking_id if authorized_subject is not None else own_booking_id
        self._refs: dict[str, EvidenceRef] = {}
        self.facts: list[WhyFact] = []
        self._facts_by_id: dict[str, WhyFact] = {}
        self.reasons: list[WhyReason] = []
        self.assumptions: list[str] = []
        self.missing_evidence: list[str] = []

    @property
    def evidence_refs(self) -> list[EvidenceRef]:
        return list(self._refs.values())

    def add_assumption(self, text: str) -> None:
        if text and text not in self.assumptions:
            self.assumptions.append(text)

    def add_missing(self, code: str) -> None:
        if code and code not in self.missing_evidence:
            self.missing_evidence.append(code)

    def add_ref(
        self,
        resolved: ResolvedTrace,
        source_path: str,
        subject: str,
        *,
        time_scope: TemporalBasis | None = None,
        interval_start: datetime | None = None,
        interval_end: datetime | None = None,
    ) -> EvidenceRef | None:
        """Create and validate an EvidenceRef. Returns None if pointer does not exist or is unauthorized."""
        trace = resolved.payload
        found, _ = resolve_json_pointer(trace, source_path)
        if not found:
            return None
        if self.actor.role == Role.RESIDENT:
            if not self.own_booking_id or not is_pointer_authorized_for_resident(
                source_path, trace, self.own_booking_id
            ):
                return None

        prov = resolved.provenance
        ref_id = f"{prov.correlation_id}:{prov.trace_schema}#{source_path}"
        if ref_id not in self._refs:
            candidate = EvidenceRef(
                ref_id=ref_id,
                correlation_id=prov.correlation_id,
                trace_schema=prov.trace_schema,
                source_path=source_path,
                subject=subject,
                decided_at=prov.decided_at,
                policy_id=prov.policy_id,
                policy_version=prov.policy_version,
                time_scope=time_scope,
                interval_start=interval_start,
                interval_end=interval_end,
            )
            if not _validate_ref_temporal_bounds(candidate, trace):
                raise ValueError(f"EvidenceRef {ref_id!r} has out-of-bounds temporal interval")
            implied = _implied_booking_from_pointer(source_path, trace)
            if implied is not None and subject != implied:
                raise ValueError(f"EvidenceRef subject {subject!r} disagrees with pointer target {implied!r}")
            self._refs[ref_id] = candidate
        return self._refs[ref_id]

    def add_fact(
        self,
        resolved: ResolvedTrace,
        *,
        name: str,
        subject: str,
        stage: FactStage,
        value: float | int | str | bool | None,
        unit: str | None,
        source_path: str,
        time_scope: TemporalBasis = TemporalBasis.DECISION_SNAPSHOT,
        interval_start: datetime | None = None,
        interval_end: datetime | None = None,
        derivation_kind: FactDerivationKind = FactDerivationKind.DIRECT,
        derivation_op: DerivationOp | None = None,
        input_evidence_refs: Sequence[str] | None = None,
        derivation_params: dict[str, float | int | str | bool | None] | None = None,
    ) -> WhyFact | None:
        prov = resolved.provenance
        if derivation_kind == FactDerivationKind.DIRECT:
            found, raw_val = resolve_json_pointer(resolved.payload, source_path)
            if not found:
                return None
            if not _direct_values_match(raw_val, value):
                raise ValueError(
                    f"Direct fact {name!r} value {value!r} does not match trace value {raw_val!r} at {source_path!r}"
                )
            ref = self.add_ref(
                resolved,
                source_path,
                subject,
                time_scope=time_scope,
                interval_start=interval_start,
                interval_end=interval_end,
            )
            if ref is None:
                return None
            resolved_inputs = [ref.ref_id]
            primary_ref_id = ref.ref_id
        else:
            if derivation_op is None:
                raise ValueError(f"Derived fact {name!r} requires a derivation_op")
            validated_inputs: list[str] = []
            for rid in dict.fromkeys(input_evidence_refs or ()):
                ref_obj = self._refs.get(rid)
                if ref_obj is None:
                    raise ValueError(f"Derived fact {name!r} references unregistered input evidence {rid!r}")
                if ref_obj.correlation_id != prov.correlation_id:
                    raise ValueError(f"Derived fact {name!r} input ref {rid!r} belongs to another trace")
                validated_inputs.append(rid)
            if not validated_inputs:
                return None
            primary_ref_id = validated_inputs[0]
            resolved_inputs = validated_inputs

        fact_id = f"f{len(self.facts) + 1:03d}:{prov.correlation_id[:8]}:{name}"
        fact = WhyFact(
            fact_id=fact_id,
            name=name,
            subject=subject,
            stage=stage,
            value=value,
            unit=unit,
            correlation_id=prov.correlation_id,
            policy_id=prov.policy_id,
            policy_version=prov.policy_version,
            decided_at=prov.decided_at,
            time_scope=time_scope,
            interval_start=interval_start,
            interval_end=interval_end,
            source_path=source_path,
            evidence_ref=primary_ref_id,
            derivation_kind=derivation_kind,
            derivation_op=derivation_op,
            input_evidence_refs=resolved_inputs,
            derivation_params=dict(derivation_params or {}),
        )
        self.facts.append(fact)
        self._facts_by_id[fact_id] = fact
        return fact

    def add_reason(
        self,
        resolved: ResolvedTrace,
        *,
        code: str,
        category: EvidenceCategory,
        subject: str,
        fact_refs: list[str],
        evidence_refs: list[str],
        template_key: str,
        params: dict[str, float | int | str | bool | None],
        summary: str,
    ) -> WhyReason:
        prov = resolved.provenance
        valid_facts: list[str] = []
        for fid in dict.fromkeys(fact_refs):
            fobj = self._facts_by_id.get(fid)
            if fobj is None:
                continue
            if fobj.correlation_id != prov.correlation_id:
                raise ValueError(f"WhyReason {code!r} fact_ref {fid!r} belongs to another trace")
            valid_facts.append(fid)

        valid_refs: list[str] = []
        for rid in dict.fromkeys(evidence_refs):
            robj = self._refs.get(rid)
            if robj is None:
                continue
            if robj.correlation_id != prov.correlation_id:
                raise ValueError(f"WhyReason {code!r} evidence_ref {rid!r} belongs to another trace")
            valid_refs.append(rid)

        if not valid_refs:
            raise ValueError(f"WhyReason {code!r} requires at least one validated evidence_ref")
        reason = WhyReason(
            code=code,
            category=category,
            subject=subject,
            correlation_id=prov.correlation_id,
            policy_id=prov.policy_id,
            policy_version=prov.policy_version,
            decided_at=prov.decided_at,
            fact_refs=valid_facts,
            evidence_refs=valid_refs,
            template_key=template_key,
            params=params,
            summary=summary,
        )
        self.reasons.append(reason)
        return reason
