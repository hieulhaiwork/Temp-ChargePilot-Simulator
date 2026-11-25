"""Typed contracts for AI-4 Decision Copilot (Phase AI-4.1 WHY Engine & Phase AI-4.2A Counterfactual Foundation).

Pure Pydantic contracts with no infrastructure or service dependencies.
`ActorContext` is constructed only at trusted server-side boundaries (JWT / deps);
`WhyQuery` forbids untrusted actor/role fields via `extra="forbid"`.
"""

from datetime import timedelta
from enum import StrEnum
from math import isfinite
from typing import Literal

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


class FactDerivationKind(StrEnum):
    DIRECT = "direct"
    DERIVED = "derived"


class DerivationOp(StrEnum):
    SUM = "sum"
    COUNT = "count"
    AVERAGE = "average"
    TIME_INTEGRATION = "time_integration"
    EFFICIENCY_CONVERSION = "efficiency_conversion"
    SOC_CONVERSION = "soc_conversion"
    HARDWARE_BOUND = "hardware_bound"


class TemporalBasis(StrEnum):
    DECISION_SNAPSHOT = "decision_snapshot"
    PLANNED_INTERVAL = "planned_interval"
    EFFECTIVE_INTERVAL = "effective_interval"
    MEASURED_COVERAGE = "measured_coverage"
    DERIVATION_INTERVAL = "derivation_interval"
    SAMPLE_INTERVAL = "sample_interval"
    QUERY_WINDOW = "query_window"


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
    cursor: str | None = Field(default=None, min_length=1, max_length=128)

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
    time_scope: TemporalBasis | None = None
    interval_start: AwareDatetime | None = None
    interval_end: AwareDatetime | None = None

    @model_validator(mode="after")
    def _validate_interval(self) -> "EvidenceRef":
        if (self.interval_start is None) != (self.interval_end is None):
            raise ValueError("interval_start and interval_end must both be set or both be None")
        if (
            self.interval_start is not None
            and self.interval_end is not None
            and self.interval_end < self.interval_start
        ):
            raise ValueError("interval_end must not precede interval_start")
        return self


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
    time_scope: TemporalBasis = TemporalBasis.DECISION_SNAPSHOT
    interval_start: AwareDatetime | None = None
    interval_end: AwareDatetime | None = None
    source_path: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    derivation_kind: FactDerivationKind = FactDerivationKind.DIRECT
    derivation_op: DerivationOp | None = None
    input_evidence_refs: list[str] = Field(default_factory=list)
    derivation_params: dict[str, float | int | str | bool | None] = Field(default_factory=dict)

    @field_validator("value")
    @classmethod
    def _validate_finite_value(cls, value: float | int | str | bool | None) -> float | int | str | bool | None:
        return _check_finite(value)

    @field_validator("derivation_params")
    @classmethod
    def _validate_derivation_params(
        cls, value: dict[str, float | int | str | bool | None]
    ) -> dict[str, float | int | str | bool | None]:
        for key, item in value.items():
            _check_finite(item)
            if not key:
                raise ValueError("Derivation param key must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_fact(self) -> "WhyFact":
        if (self.interval_start is None) != (self.interval_end is None):
            raise ValueError("interval_start and interval_end must both be set or both be None")
        if (
            self.interval_start is not None
            and self.interval_end is not None
            and self.interval_end < self.interval_start
        ):
            raise ValueError("interval_end must not precede interval_start")
        if self.derivation_kind == FactDerivationKind.DERIVED:
            if self.derivation_op is None:
                raise ValueError("Derived WhyFact must specify derivation_op")
            if not self.input_evidence_refs:
                raise ValueError("Derived WhyFact must include input_evidence_refs")
        elif self.derivation_op is not None:
            raise ValueError("Direct WhyFact must not specify derivation_op")
        return self


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
    next_cursor: str | None = None


# ---- Phase AI-4.2A: Counterfactual Foundation (Gate 3) -----------------------------------------

SNAPSHOT_SCHEMA_VERSION = "chargepilot.copilot_snapshot/1"
EVENT_MANIFEST_SCHEMA_VERSION = "chargepilot.event_manifest/1"
OUTCOME_LEDGER_SCHEMA_VERSION = "chargepilot.outcome_ledger/1"
MAX_COUNTERFACTUAL_HORIZON_MINUTES = 24 * 60


class SnapshotStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"


class SnapshotNotReadyReason(StrEnum):
    UNRESOLVED_HARD_SAFETY_EVENT = "unresolved_hard_safety_event"
    UNSAFE_PHYSICAL_STATE = "unsafe_physical_state"
    INCONSISTENT_COHORT = "inconsistent_cohort"
    UNSUPPORTED_STATE = "unsupported_state"


class KnownLimitEvent(BaseModel):
    """Exogenous supply/cabinet limit event already announced at or before capture time T."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    announced_minute: int = Field(ge=0)
    announced_at: AwareDatetime
    effective_minute: int = Field(ge=0)
    effective_at: AwareDatetime
    grid_input_kw: float | None = Field(default=None, ge=0)
    cabinet_output_kw: dict[str, float] = Field(default_factory=dict)

    @field_validator("grid_input_kw")
    @classmethod
    def _finite_grid(cls, value: float | None) -> float | None:
        return _check_finite(value)  # type: ignore[return-value]

    @field_validator("cabinet_output_kw")
    @classmethod
    def _finite_cabinets(cls, value: dict[str, float]) -> dict[str, float]:
        for key, kw in value.items():
            if not key:
                raise ValueError("Cabinet ID must not be empty")
            _check_finite(kw)
            if kw < 0:
                raise ValueError("Cabinet output kW must be non-negative")
        return value

    @model_validator(mode="after")
    def _check_times(self) -> "KnownLimitEvent":
        _require_aware(self.announced_at, "announced_at")
        _require_aware(self.effective_at, "effective_at")
        if self.announced_minute > self.effective_minute:
            raise ValueError("announced_minute must not exceed effective_minute")
        return self


class EventManifest(BaseModel):
    """Prospective `known_at(T)` manifest materialized once and shared identically across sandbox branches."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default=EVENT_MANIFEST_SCHEMA_VERSION, min_length=1)
    station_id: str = Field(min_length=1, max_length=64)
    as_of: AwareDatetime
    as_of_minute: int = Field(ge=0)
    horizon_minutes: int = Field(gt=0, le=MAX_COUNTERFACTUAL_HORIZON_MINUTES)
    horizon_end: AwareDatetime
    horizon_end_minute: int = Field(gt=0)
    known_booking_ids: list[str] = Field(default_factory=list)
    already_present_booking_ids: list[str] = Field(default_factory=list)
    known_future_arrival_booking_ids: list[str] = Field(default_factory=list)
    excluded_future_booking_count: int = Field(default=0, ge=0)
    excluded_unbooked_not_arrived_count: int = Field(default=0, ge=0)
    known_limit_events: list[KnownLimitEvent] = Field(default_factory=list)
    excluded_unannounced_limit_event_count: int = Field(default=0, ge=0)
    active_faulted_connectors: list[str] = Field(default_factory=list)
    effective_grid_limit_kw_at_capture: float = Field(ge=0)
    assumptions: list[str] = Field(default_factory=list)
    manifest_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("effective_grid_limit_kw_at_capture")
    @classmethod
    def _finite_limit(cls, value: float) -> float:
        return _check_finite(value)  # type: ignore[return-value]

    @model_validator(mode="after")
    def _validate_manifest(self) -> "EventManifest":
        _require_aware(self.as_of, "as_of")
        _require_aware(self.horizon_end, "horizon_end")
        if self.horizon_end <= self.as_of:
            raise ValueError("horizon_end must be strictly after as_of")
        if self.horizon_end_minute != self.as_of_minute + self.horizon_minutes:
            raise ValueError("horizon_end_minute must equal as_of_minute + horizon_minutes")
        for ev in self.known_limit_events:
            if ev.announced_minute > self.as_of_minute:
                raise ValueError("EventManifest must not contain limit events announced after as_of_minute")
        return self


class SnapshotEnvelope(BaseModel):
    """Pure serializable metadata and cryptographic digests for an atomic counterfactual snapshot at T.

    `experiment_fingerprint` hashes the static resolved policy/component/config setup (`ResolvedExperiment`),
    whereas `snapshot_digest` hashes the complete canonical dynamic + static state at T (strictly distinct from
    both `experiment_fingerprint` and `StationRuntime.admission_fingerprint()`).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default=SNAPSHOT_SCHEMA_VERSION, min_length=1)
    snapshot_id: str = Field(min_length=1, max_length=64)
    status: SnapshotStatus = SnapshotStatus.READY
    station_id: str = Field(min_length=1, max_length=64)
    as_of: AwareDatetime
    sim_minute: int = Field(ge=0)
    horizon_minutes: int = Field(gt=0, le=MAX_COUNTERFACTUAL_HORIZON_MINUTES)
    booking_version: int = Field(ge=0)
    plan_version: int | None = Field(default=None, ge=0)
    state_version: int = Field(ge=0)
    schedule_version: int = Field(ge=0)
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    dc_charging_model_name: str = Field(min_length=1)
    time_config: dict[str, int | None] = Field(default_factory=dict)
    station_config_sha256: str = Field(min_length=64, max_length=64)
    tariff_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    experiment_fingerprint: str = Field(min_length=64, max_length=64)
    event_manifest_sha256: str = Field(min_length=64, max_length=64)
    stateful_components_sha256: str = Field(min_length=64, max_length=64)
    snapshot_digest: str = Field(min_length=64, max_length=64)
    known_booking_count: int = Field(ge=0)
    safety_hold_booking_ids: list[str] = Field(default_factory=list)
    rejected_booking_ids: list[str] = Field(default_factory=list)
    pending_approval_ids: list[str] = Field(default_factory=list)
    recent_command_count: int = Field(ge=0)
    undelivered_ordinary_outbox_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_envelope(self) -> "SnapshotEnvelope":
        _require_aware(self.as_of, "as_of")
        if self.snapshot_digest == self.experiment_fingerprint:
            raise ValueError("snapshot_digest must be distinct from experiment_fingerprint")
        return self


class VehicleOutcomeStatus(StrEnum):
    ALREADY_COMPLETED_AT_SNAPSHOT = "already_completed_at_snapshot"
    COMPLETED_ON_TIME = "completed_on_time"
    COMPLETED_LATE = "completed_late"
    CENSORED_NOT_ARRIVED = "censored_not_arrived"
    MISSED_DEADLINE_NOT_ARRIVED = "missed_deadline_not_arrived"
    CENSORED_IN_PROGRESS = "censored_in_progress"
    UNSERVED_DEPARTED_OR_EXPIRED = "unserved_departed_or_expired"
    PARTIAL_MISSED_DEADLINE = "partial_missed_deadline"


class VehicleReleaseReason(StrEnum):
    DC_UNPLUG_DELAY = "dc_unplug_delay"
    DECLARED_DEPARTURE = "declared_departure"


class VehicleOutcomeRecord(BaseModel):
    """Per-vehicle counterfactual outcome preserving original commitments and separating pre- vs post-snapshot kWh."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    booking_id: str = Field(min_length=1)
    zone: Literal["AC", "DC"]
    vehicle_model: str = Field(min_length=1)
    within_optimistic_energy_bound: bool = Field(
        description="Vehicle power cap × available hours can cover requested output energy under ideal conditions."
    )
    original_arrival_at: AwareDatetime
    original_deadline: AwareDatetime
    original_soc_now_pct: float = Field(ge=0, le=100)
    original_target_soc_pct: float = Field(gt=0, le=100)
    original_required_battery_kwh: float = Field(ge=0)
    original_required_output_kwh: float = Field(ge=0)

    initial_session_state: str = Field(min_length=1)
    initial_soc_pct: float = Field(ge=0, le=100)
    already_plugged_at_snapshot: bool
    already_completed_at_snapshot: bool
    pre_snapshot_battery_stored_kwh: float = Field(ge=0)
    pre_snapshot_output_kwh: float = Field(ge=0)
    pre_snapshot_grid_input_kwh: float = Field(ge=0)

    arrived_at: AwareDatetime | None = None
    assigned_connector_id: str | None = None
    plug_in_at: AwareDatetime | None = None
    first_charge_at: AwareDatetime | None = None
    first_rollout_charge_at: AwareDatetime | None = None
    historical_plug_time_unknown: bool = False
    target_reached_at: AwareDatetime | None = None
    release_or_departure_at: AwareDatetime | None = None
    release_reason: VehicleReleaseReason | None = None

    plug_wait_minutes: float | None = Field(default=None, ge=0)
    censored_plug_wait_minutes: float | None = Field(default=None, ge=0)
    charge_start_wait_minutes: float | None = Field(default=None, ge=0)
    censored_charge_start_wait_minutes: float | None = Field(default=None, ge=0)
    fault_unplug_count: int = Field(default=0, ge=0)

    horizon_battery_stored_kwh: float = Field(ge=0)
    horizon_output_kwh: float = Field(ge=0)
    horizon_grid_input_kwh: float = Field(ge=0)

    final_session_state: str = Field(min_length=1)
    final_soc_pct: float = Field(ge=0, le=100)
    cumulative_battery_stored_kwh: float = Field(ge=0)
    cumulative_output_kwh: float = Field(ge=0)
    cumulative_grid_input_kwh: float = Field(ge=0)
    remaining_to_original_target_battery_kwh: float = Field(ge=0)

    status: VehicleOutcomeStatus
    sla_evaluable: bool
    censored: bool
    unserved: bool
    met_original_sla: bool | None = None

    @model_validator(mode="after")
    def _validate_record(self) -> "VehicleOutcomeRecord":
        _require_aware(self.original_arrival_at, "original_arrival_at")
        _require_aware(self.original_deadline, "original_deadline")
        for field_name in (
            "arrived_at",
            "plug_in_at",
            "first_charge_at",
            "target_reached_at",
            "release_or_departure_at",
        ):
            val = getattr(self, field_name)
            if val is not None:
                _require_aware(val, field_name)
        for num_field in (
            "original_soc_now_pct",
            "original_target_soc_pct",
            "original_required_battery_kwh",
            "original_required_output_kwh",
            "initial_soc_pct",
            "pre_snapshot_battery_stored_kwh",
            "pre_snapshot_output_kwh",
            "pre_snapshot_grid_input_kwh",
            "plug_wait_minutes",
            "censored_plug_wait_minutes",
            "charge_start_wait_minutes",
            "censored_charge_start_wait_minutes",
            "horizon_battery_stored_kwh",
            "horizon_output_kwh",
            "horizon_grid_input_kwh",
            "final_soc_pct",
            "cumulative_battery_stored_kwh",
            "cumulative_output_kwh",
            "cumulative_grid_input_kwh",
            "remaining_to_original_target_battery_kwh",
        ):
            _check_finite(getattr(self, num_field))
        if self.sla_evaluable != (self.met_original_sla is not None):
            raise ValueError("met_original_sla must be non-None iff sla_evaluable is True")
        if self.censored and self.sla_evaluable:
            raise ValueError("A censored vehicle outcome cannot be sla_evaluable")
        return self


class ZoneSlaSummary(BaseModel):
    """Per-zone SLA and service denominators (`None` rate when denominator is 0, never 1.0)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    zone: Literal["AC", "DC"]
    cohort_count: int = Field(ge=0)
    arrived_count: int = Field(ge=0)
    not_arrived_count: int = Field(ge=0)
    plugged_count: int = Field(ge=0)
    charged_count: int = Field(ge=0)
    unserved_count: int = Field(ge=0)
    censored_count: int = Field(ge=0)
    sla_denominator: int = Field(ge=0)
    sla_met_count: int = Field(ge=0)
    on_time_rate: float | None = Field(default=None, ge=0, le=1)
    energy_bound_sla_denominator: int = Field(ge=0)
    energy_bound_sla_met_count: int = Field(ge=0)
    energy_bound_on_time_rate: float | None = Field(default=None, ge=0, le=1)
    service_coverage_rate: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _validate_denominators(self) -> "ZoneSlaSummary":
        if (self.sla_denominator == 0) != (self.on_time_rate is None):
            raise ValueError("on_time_rate must be None iff sla_denominator == 0")
        if (self.energy_bound_sla_denominator == 0) != (self.energy_bound_on_time_rate is None):
            raise ValueError("energy_bound_on_time_rate must be None iff energy_bound_sla_denominator == 0")
        if (self.arrived_count == 0) != (self.service_coverage_rate is None):
            raise ValueError("service_coverage_rate must be None iff arrived_count == 0")
        return self


class OutcomeLedger(BaseModel):
    """Additive AI-4 Outcome Ledger over a fixed snapshot cohort `[as_of, horizon_end)`.

    Frozen `HybridStation.outcomes()` and `simulation_service.compute_kpis()` remain untouched.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default=OUTCOME_LEDGER_SCHEMA_VERSION, min_length=1)
    station_id: str = Field(min_length=1, max_length=64)
    as_of: AwareDatetime
    horizon_end: AwareDatetime
    horizon_minutes: int = Field(gt=0)
    observed_until: AwareDatetime

    cohort_size: int = Field(ge=0)
    arrived_count: int = Field(ge=0)
    not_arrived_count: int = Field(ge=0)
    plugged_count: int = Field(ge=0)
    charged_count: int = Field(ge=0)
    completed_on_time_count: int = Field(ge=0)
    completed_late_count: int = Field(ge=0)
    already_completed_at_snapshot_count: int = Field(ge=0)
    unserved_count: int = Field(ge=0)
    partial_missed_deadline_count: int = Field(ge=0)
    censored_count: int = Field(ge=0)
    censored_not_arrived_count: int = Field(ge=0)
    censored_in_progress_count: int = Field(ge=0)

    sla_denominator: int = Field(ge=0)
    sla_met_count: int = Field(ge=0)
    on_time_rate: float | None = Field(default=None, ge=0, le=1)
    energy_bound_sla_denominator: int = Field(ge=0)
    energy_bound_sla_met_count: int = Field(ge=0)
    energy_bound_on_time_rate: float | None = Field(default=None, ge=0, le=1)
    service_coverage_denominator: int = Field(ge=0)
    service_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    charged_coverage_rate: float | None = Field(default=None, ge=0, le=1)

    plug_wait_observed_count: int = Field(ge=0)
    charge_start_wait_observed_count: int = Field(ge=0)
    plug_wait_mean_minutes: float | None = Field(default=None, ge=0)
    plug_wait_p90_minutes: float | None = Field(default=None, ge=0)
    charge_start_wait_mean_minutes: float | None = Field(default=None, ge=0)
    charge_start_wait_p90_minutes: float | None = Field(default=None, ge=0)

    pre_snapshot_battery_stored_kwh: float = Field(ge=0)
    pre_snapshot_output_kwh: float = Field(ge=0)
    pre_snapshot_grid_input_kwh: float = Field(ge=0)

    horizon_battery_stored_kwh: float = Field(ge=0)
    horizon_output_kwh: float = Field(ge=0)
    horizon_grid_input_kwh: float = Field(ge=0)
    horizon_energy_cost_vnd: float = Field(ge=0)
    remaining_to_original_target_battery_kwh: float = Field(ge=0)

    peak_charger_output_kw: float = Field(ge=0)
    peak_grid_input_kw: float = Field(ge=0)

    pre_snapshot_applied_constraint_violation_count: int = Field(ge=0)
    horizon_applied_constraint_violation_count: int = Field(ge=0)
    horizon_rejected_allocation_count: int = Field(ge=0)
    horizon_sampled_grid_over_limit_minutes: int = Field(ge=0)
    horizon_hard_safety_event_count: int = Field(ge=0)
    horizon_guard_blocked_command_count: int = Field(ge=0)
    horizon_pending_approval_command_count: int = Field(ge=0)

    by_zone: dict[str, ZoneSlaSummary] = Field(default_factory=dict)
    vehicles: list[VehicleOutcomeRecord] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_ledger(self) -> "OutcomeLedger":
        _require_aware(self.as_of, "as_of")
        _require_aware(self.horizon_end, "horizon_end")
        if self.cohort_size != len(self.vehicles):
            raise ValueError("cohort_size must equal len(vehicles)")
        if self.arrived_count + self.not_arrived_count != self.cohort_size:
            raise ValueError("arrived_count + not_arrived_count must equal cohort_size")
        if (self.sla_denominator == 0) != (self.on_time_rate is None):
            raise ValueError("on_time_rate must be None iff sla_denominator == 0")
        if (self.energy_bound_sla_denominator == 0) != (self.energy_bound_on_time_rate is None):
            raise ValueError("energy_bound_on_time_rate must be None iff energy_bound_sla_denominator == 0")
        if (self.service_coverage_denominator == 0) != (self.service_coverage_rate is None):
            raise ValueError("service_coverage_rate must be None iff service_coverage_denominator == 0")
        if (self.service_coverage_denominator == 0) != (self.charged_coverage_rate is None):
            raise ValueError("charged_coverage_rate must be None iff service_coverage_denominator == 0")
        return self


class SandboxBranchResult(BaseModel):
    """Result of running a single isolated sandbox branch from a `CapturedSnapshot`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    branch_label: str = Field(min_length=1, max_length=64)
    status: Literal["completed", "unsafe", "unresolved_safety"]
    observed_until: AwareDatetime
    unresolved_safety_count: int = Field(ge=0)
    applied: Literal[False] = False
    snapshot_id: str = Field(min_length=1, max_length=64)
    initial_snapshot_digest: str = Field(min_length=64, max_length=64)
    experiment_fingerprint: str = Field(min_length=64, max_length=64)
    event_manifest_sha256: str = Field(min_length=64, max_length=64)
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    as_of: AwareDatetime
    horizon_end: AwareDatetime
    horizon_minutes: int = Field(gt=0)
    decisions_count: int = Field(ge=0)
    executed_command_count: int = Field(ge=0)
    blocked_command_count: int = Field(ge=0)
    pending_approval_count_end: int = Field(ge=0)
    safety_hold_booking_ids_end: list[str] = Field(default_factory=list)
    final_physics_digest: str = Field(min_length=64, max_length=64)
    wall_time_ms: float = Field(ge=0)
    outcome_ledger: OutcomeLedger


class PairedNoOpResult(BaseModel):
    """Gate 3 paired no-op validation output: two independent forks from one immutable snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    applied: Literal[False] = False
    snapshot_id: str = Field(min_length=1, max_length=64)
    snapshot_digest: str = Field(min_length=64, max_length=64)
    experiment_fingerprint: str = Field(min_length=64, max_length=64)
    event_manifest_sha256: str = Field(min_length=64, max_length=64)
    horizon_minutes: int = Field(gt=0)
    known_booking_ids: list[str] = Field(default_factory=list)
    baseline: SandboxBranchResult
    counterfactual: SandboxBranchResult
    non_timing_kpis_equal: bool
    final_physics_digests_equal: bool
