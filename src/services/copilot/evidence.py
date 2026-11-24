"""Authorization, privacy projection, JSON Pointer resolution, and EvidenceCollector (WP2.4).

Invariants enforced here:
- Role and actor identity come exclusively from trusted server-side `ActorContext`.
- Resident ownership is verified against both active and historical bookings.
- Resident unauthorized ID and nonexistent ID yield identical non-enumerating FORBIDDEN responses.
- Resident EvidenceRefs and serialized WhyAnswers can NEVER leak other residents' booking IDs,
  personal identifiers, or cross-resident dereferenceable paths.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.models.charging import Booking
from src.models.control import Role
from src.models.copilot import (
    ActorContext,
    EvidenceCategory,
    EvidenceRef,
    FactStage,
    WhyAnswer,
    WhyFact,
    WhyQuery,
    WhyReason,
    WhyStatus,
    WhySubjectScope,
)
from src.services.copilot.trace_reader import ResolvedTrace


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
class AuthorizationResult:
    allowed: bool
    status: WhyStatus
    subject_id: str | None
    booking: Booking | None
    missing_evidence: tuple[str, ...] = ()


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
                # Identical response for nonexistent ID and another resident's ID (no oracle).
                return AuthorizationResult(False, WhyStatus.FORBIDDEN, None, None, ("booking_not_accessible",))
            return AuthorizationResult(True, WhyStatus.OK, booking.booking_id, booking)
        # own_booking with booking_id=None: resolve active or most recent historical booking for actor
        booking = active_booking(actor.actor_id)
        if booking is None:
            history = list_resident_bookings(actor.actor_id)
            booking = max(history, key=lambda b: b.created_at) if history else None
        if booking is None:
            return AuthorizationResult(False, WhyStatus.NO_DATA, None, None, ("no_booking_for_actor",))
        return AuthorizationResult(True, WhyStatus.OK, booking.booking_id, booking)

    if actor.role == Role.OPERATOR:
        if query.subject_scope == WhySubjectScope.OWN_BOOKING:
            return AuthorizationResult(False, WhyStatus.FORBIDDEN, None, None, ("operator_cannot_use_own_booking",))
        if query.subject_scope == WhySubjectScope.STATION:
            return AuthorizationResult(True, WhyStatus.OK, station_id, None)
        assert query.booking_id is not None
        booking = get_booking(query.booking_id)
        if booking is None:
            return AuthorizationResult(False, WhyStatus.NO_DATA, query.booking_id, None, ("booking_not_found",))
        return AuthorizationResult(True, WhyStatus.OK, booking.booking_id, booking)

    return AuthorizationResult(False, WhyStatus.FORBIDDEN, None, None, ("role_not_supported",))


# Allowed top-level/prefix JSON Pointer patterns for Resident (never raw cross-resident arrays/maps).
_RESIDENT_SAFE_STATION_PREFIXES = (
    "/policy",
    "/experiment/policy_id",
    "/experiment/policy_version",
    "/experiment/dc_charging_model",
    "/experiment/fingerprint",
    "/interval",
    "/state_version",
    "/schedule_version",
    "/reason_codes",
    "/validation/pre_apply_physical",
    "/validation/post_apply",
    "/validation/fail_safe/status",
    "/applied/coverage",
    "/planned/observed/zone_summary",
    "/planned/physical_limits",
    "/planned/coordinator/policy",
    "/planned/coordinator/assigned_output_kw",
    "/planned/coordinator/default_zone_budget_kw",
    "/planned/coordinator/reason_codes",
    "/planned/coordinator/fallback_reason",
    "/planned/tariff",
)


def is_pointer_authorized_for_resident(pointer: str, trace: dict, own_booking_id: str) -> bool:
    """Return True iff dereferencing `pointer` in `trace` exposes only own booking or allowed aggregates."""
    if not pointer or not pointer.startswith("/"):
        return False
    tokens = [decode_pointer_token(t) for t in pointer.split("/")[1:]]
    if not tokens:
        return False

    # Never allow paths that directly expose raw cross-resident collections or raw trace root.
    if pointer in (
        "/booking_ids",
        "/safety",
        "/safety/held_booking_ids",
        "/safety/hard_limit_violations",
        "/planned",
        "/planned/observed",
        "/planned/observed/ports",
        "/planned/observed/queues_by_zone",
        "/planned/observed/vehicles",
        "/planned/dispatch",
        "/planned/dc_waiting_laxity",
        "/decision",
        "/applied",
        "/commands",
        "/emergency_commands",
        "/command_exclusions",
        "/power",
        "/guard_inputs",
    ):
        return False

    # Safe station/zone aggregate paths
    for prefix in _RESIDENT_SAFE_STATION_PREFIXES:
        if pointer == prefix or pointer.startswith(prefix + "/"):
            # Ensure no other booking ID is embedded in the leaf value
            found, value = resolve_json_pointer(trace, pointer)
            if not found:
                return False
            other_ids = _other_booking_ids(trace, own_booking_id)
            return not _contains_any_id(value, other_ids)

    # Zone-level optimizer status/fallback (never full projected_shortfall_kwh dict containing other bookings)
    if len(tokens) >= 4 and tokens[0] == "planned" and tokens[1] == "optimizers":
        field = tokens[3]
        if field in ("policy", "solver_status", "fallback_reason", "stage_status"):
            return len(tokens) == 4 or (field == "stage_status" and len(tokens) == 5)
        if field in ("projected_shortfall_kwh", "projection_cutoff_minute"):
            return len(tokens) == 5 and tokens[4] == own_booking_id
        return False

    # Dispatch policy & aggregate empty/faulted connectors per zone (never waiting lists or other assignments)
    if len(tokens) == 4 and tokens[0] == "planned" and tokens[1] == "dispatch" and tokens[3] == "policy":
        return True
    if len(tokens) == 4 and tokens[0] == "planned" and tokens[1] == "observed":
        if tokens[2] == "empty_connectors_by_zone":
            return True
    if pointer == "/planned/observed/faulted_connectors":
        return True

    # Own booking scoped paths
    if len(tokens) >= 3 and tokens[:2] == ["safety", "by_booking"] and tokens[2] == own_booking_id:
        return True
    if len(tokens) >= 4 and tokens[:3] == ["planned", "observed", "vehicles"] and tokens[3] == own_booking_id:
        return True
    if len(tokens) >= 3 and tokens[:2] == ["planned", "dc_waiting_laxity"] and tokens[2] == own_booking_id:
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
    if len(tokens) == 3 and tokens[:2] == ["consent", "adjustments_kw"] and tokens[2] == own_booking_id:
        return True

    # Planned/measured binding constraint item: allowed if zone/site/cabinet/own-port/own-booking, NEVER another booking
    if len(tokens) == 3 and tokens[:2] == ["planned", "binding_constraints"] and tokens[2].isdigit():
        found, item = resolve_json_pointer(trace, pointer)
        if not found or not isinstance(item, dict):
            return False
        if item.get("limit") == "individual_allowed_output":
            return item.get("id") == own_booking_id
        return not _contains_any_id(item, _other_booking_ids(trace, own_booking_id))

    # Command / emergency_command / command_exclusion row: ONLY if row.booking_id == own_booking_id
    if (
        len(tokens) >= 2
        and tokens[0] in ("commands", "emergency_commands", "command_exclusions")
        and tokens[1].isdigit()
    ):
        row_found, row = resolve_json_pointer(trace, f"/{tokens[0]}/{tokens[1]}")
        if not row_found or not isinstance(row, dict):
            return False
        return row.get("booking_id") == own_booking_id

    return False


def resolve_evidence_ref(
    ref: EvidenceRef,
    trace: dict,
    actor: ActorContext,
    *,
    own_booking_id: str | None = None,
) -> tuple[bool, Any]:
    """Authorized dereferencing of an EvidenceRef against a trace payload.

    Prevents a syntactically valid EvidenceRef from becoming an authorization bypass.
    """
    if trace.get("correlation_id") != ref.correlation_id:
        return False, None
    if trace.get("trace_schema") != ref.trace_schema:
        return False, None
    if trace.get("station_id") != actor.station_id:
        return False, None
    if actor.role == Role.RESIDENT:
        if not own_booking_id or not is_pointer_authorized_for_resident(ref.source_path, trace, own_booking_id):
            return False, None
    elif actor.role != Role.OPERATOR:
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
    own_booking_id: str | None = None,
) -> None:
    """Defense-in-depth gate over the entire serialized WhyAnswer for Resident callers."""
    if actor.role != Role.RESIDENT:
        return
    forbidden: set[str] = set()
    for item in traces:
        if own_booking_id is not None:
            forbidden.update(_other_booking_ids(item.payload, own_booking_id))
        else:
            forbidden.update(str(v) for v in (item.payload.get("booking_ids") or ()) if v)

    serialized = json.dumps(answer.model_dump(mode="json"), ensure_ascii=False)
    for bad in sorted(forbidden):
        if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(bad)}(?![A-Za-z0-9_-])", serialized):
            raise PermissionError(f"Resident privacy projection violation: leaked booking reference {bad!r}")

    # Verify every EvidenceRef in the answer passes resident authorization against its trace
    by_cid = {item.provenance.correlation_id: item.payload for item in traces}
    for ref in answer.evidence_refs:
        trace = by_cid.get(ref.correlation_id)
        if trace is None or not own_booking_id:
            raise PermissionError(f"Unverified resident evidence ref {ref.ref_id!r}")
        ok, _ = resolve_evidence_ref(ref, trace, actor, own_booking_id=own_booking_id)
        if not ok:
            raise PermissionError(f"Unauthorized or dangling resident evidence ref {ref.source_path!r}")


class EvidenceCollector:
    """Builds validated, deduplicated EvidenceRefs, WhyFacts, and WhyReasons for one WhyAnswer."""

    def __init__(self, actor: ActorContext, *, own_booking_id: str | None = None) -> None:
        self.actor = actor
        self.own_booking_id = own_booking_id
        self._refs: dict[str, EvidenceRef] = {}
        self.facts: list[WhyFact] = []
        self._fact_ids: set[str] = set()
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
            self._refs[ref_id] = EvidenceRef(
                ref_id=ref_id,
                correlation_id=prov.correlation_id,
                trace_schema=prov.trace_schema,
                source_path=source_path,
                subject=subject,
                decided_at=prov.decided_at,
                policy_id=prov.policy_id,
                policy_version=prov.policy_version,
                interval_start=interval_start,
                interval_end=interval_end,
            )
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
        interval_start: datetime | None = None,
        interval_end: datetime | None = None,
    ) -> WhyFact | None:
        ref = self.add_ref(resolved, source_path, subject, interval_start=interval_start, interval_end=interval_end)
        if ref is None:
            return None
        prov = resolved.provenance
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
            interval_start=interval_start,
            interval_end=interval_end,
            source_path=source_path,
            evidence_ref=ref.ref_id,
        )
        self.facts.append(fact)
        self._fact_ids.add(fact_id)
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
        valid_facts = [fid for fid in dict.fromkeys(fact_refs) if fid in self._fact_ids]
        valid_refs = [rid for rid in dict.fromkeys(evidence_refs) if rid in self._refs]
        if not valid_refs:
            raise ValueError(f"WhyReason {code!r} requires at least one validated evidence_ref")
        prov = resolved.provenance
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
