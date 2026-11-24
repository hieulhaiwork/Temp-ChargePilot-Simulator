"""Typed contracts for AI-4 Decision Copilot (Phase AI-4.1: Deterministic WHY Engine).

Pure Pydantic contracts with no infrastructure or service dependencies.
`ActorContext` is constructed only at trusted server-side boundaries (JWT / deps);
`WhyQuery` forbids untrusted actor/role fields via `extra="forbid"`.
"""

from datetime import timedelta
from enum import StrEnum
from math import isfinite

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from src.models.api import UserProfile
from src.models.control import Role

MAX_WHY_WINDOW = timedelta(days=31)


class WhyTopic(StrEnum):
    QUEUE = "queue"
    POWER = "power"
    DEADLINE_RISK = "deadline_risk"
    INCIDENT = "incident"
    POLICY = "policy"
    OVERVIEW = "overview"


SUPPORTED_WHY_TOPICS = frozenset(topic.value for topic in WhyTopic)


class WhySubjectScope(StrEnum):
    OWN_BOOKING = "own_booking"
    BOOKING = "booking"
    STATION = "station"


class WhyStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    NO_DATA = "no_data"
    FORBIDDEN = "forbidden"
    UNSUPPORTED = "unsupported"


class FactStage(StrEnum):
    OBSERVED = "observed"
    PLANNED = "planned"
    APPROVED = "approved"
    DISPATCHED = "dispatched"
    EFFECTIVE_SETPOINT = "effective_setpoint"
    MEASURED = "measured"
    CONFIG = "config"


class EvidenceCategory(StrEnum):
    OBSERVED = "observed"
    POLICY_REASON = "policy_reason"
    BINDING_CONSTRAINT = "binding_constraint"
    INFERENCE_BOUND = "inference_bound"


def _require_aware(dt: AwareDatetime, field_name: str) -> AwareDatetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return dt


def _check_finite(value: float | int | str | bool | None) -> float | int | str | bool | None:
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("Non-finite float values (NaN/Inf) are not allowed")
    return value


class ActorContext(BaseModel):
    """Trusted server-side caller identity (derived from JWT / auth deps, never from query or LLM)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: str = Field(min_length=1, max_length=64)
    role: Role
    station_id: str = Field(min_length=1, max_length=64)

    @classmethod
    def from_user(cls, user: UserProfile, station_id: str) -> "ActorContext":
        return cls(actor_id=user.user_id, role=user.role, station_id=station_id)


class TimeWindow(BaseModel):
    """Half-open, timezone-aware query interval [start, end)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def _validate_window(self) -> "TimeWindow":
        _require_aware(self.start, "window.start")
        _require_aware(self.end, "window.end")
        if self.end <= self.start:
            raise ValueError("window.end must be strictly after window.start")
        if self.end - self.start > MAX_WHY_WINDOW:
            raise ValueError("window duration must be at most 31 days")
        return self


class WhyQuery(BaseModel):
    """Typed query for the deterministic WHY Engine.

    Invalid structure (naive timestamps, contradictory time selection, invalid scope/booking
    combination, unknown fields) raises ValidationError. An unknown topic string is accepted
    by schema so the service can return `WhyStatus.UNSUPPORTED` cleanly.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_scope: WhySubjectScope
    topic: str = Field(min_length=1, max_length=64)
    booking_id: str | None = Field(default=None, min_length=1, max_length=64)
    at: AwareDatetime | None = None
    window: TimeWindow | None = None
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("topic")
    @classmethod
    def _normalize_topic(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("topic must not be blank")
        return cleaned

    @model_validator(mode="after")
    def _validate_query(self) -> "WhyQuery":
        if self.at is not None:
            _require_aware(self.at, "at")
        if (self.at is None) == (self.window is None):
            raise ValueError("Specify exactly one of 'at' (as-of timestamp) or 'window' ([start, end))")
        if self.subject_scope == WhySubjectScope.STATION and self.booking_id is not None:
            raise ValueError("booking_id must not be set when subject_scope is 'station'")
        if self.subject_scope == WhySubjectScope.BOOKING and self.booking_id is None:
            raise ValueError("booking_id is required when subject_scope is 'booking'")
        return self


class EvidenceRef(BaseModel):
    """Stable, dereferenceable evidence pointer scoped to an authorized subject and trace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1, max_length=32)
    trace_schema: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    decided_at: AwareDatetime
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    interval_start: AwareDatetime | None = None
    interval_end: AwareDatetime | None = None


class WhyFact(BaseModel):
    """One atomic, typed fact grounded in a specific DecisionTrace and temporal boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    stage: FactStage
    value: float | int | str | bool | None = None
    unit: str | None = None
    correlation_id: str = Field(min_length=1, max_length=32)
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    decided_at: AwareDatetime
    interval_start: AwareDatetime | None = None
    interval_end: AwareDatetime | None = None
    source_path: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def _validate_finite_value(cls, value: float | int | str | bool | None) -> float | int | str | bool | None:
        return _check_finite(value)


class WhyReason(BaseModel):
    """One deterministic, evidence-backed reason referencing facts and evidence pointers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    category: EvidenceCategory
    subject: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1, max_length=32)
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    decided_at: AwareDatetime
    fact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    template_key: str = Field(min_length=1)
    params: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    summary: str = Field(min_length=1)

    @field_validator("params")
    @classmethod
    def _validate_finite_params(
        cls, value: dict[str, float | int | str | bool | None]
    ) -> dict[str, float | int | str | bool | None]:
        for key, item in value.items():
            _check_finite(item)
            if not key:
                raise ValueError("Reason param key must not be empty")
        return value


class TraceProvenance(BaseModel):
    """Temporal and policy provenance for one resolved DecisionTrace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    correlation_id: str = Field(min_length=1, max_length=32)
    trace_schema: str = Field(min_length=1)
    decided_at: AwareDatetime
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    state_version: int | None = None
    schedule_version: int
    closed: bool
    planned_interval_start: AwareDatetime | None = None
    planned_interval_end: AwareDatetime | None = None
    effective_start: AwareDatetime
    effective_end: AwareDatetime | None = None
    measured_start: AwareDatetime | None = None
    measured_end: AwareDatetime | None = None
    coverage_status: str = Field(min_length=1)
    post_apply_status: str = Field(min_length=1)
    stale_after_restart: bool = False


class WhyAnswer(BaseModel):
    """Structured output of the deterministic WHY Engine.

    For multi-trace windows, per-fact/per-reason provenance carries exact correlation_id,
    policy_id, policy_version and decided_at; top-level decision_time/state_version are only
    populated when a single trace is resolved, and top-level policy_id/policy_version only
    when unambiguous across all resolved traces.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: WhyStatus
    topic: str = Field(min_length=1)
    subject_scope: WhySubjectScope
    subject_id: str | None = None
    query_at: AwareDatetime | None = None
    query_window: TimeWindow | None = None
    decision_time: AwareDatetime | None = None
    policy_id: str | None = None
    policy_version: str | None = None
    state_version: int | None = None
    traces: list[TraceProvenance] = Field(default_factory=list)
    facts: list[WhyFact] = Field(default_factory=list)
    reasons: list[WhyReason] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    truncated: bool = False
