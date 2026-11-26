"""G6A transport, intent and grounding contracts."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from src.models.control import Role
from src.models.copilot import MAX_COUNTERFACTUAL_HORIZON_MINUTES, EvidenceCategory, FactStage, WhyAnswer, WhyTopic
from src.models.recommendation import RecommendationGoal, RecommendationResult
from src.models.what_if import PatchDatetime, WhatIfJobStatus, WhatIfPatch, WhatIfResult

Id = Annotated[str, Field(strict=True, min_length=1, max_length=64)]
Horizon = Annotated[int, Field(strict=True, gt=0, le=MAX_COUNTERFACTUAL_HORIZON_MINUTES)]
Soc = Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)]
GridInputKw = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
DEFAULT_HORIZON_MINUTES = 120


class CopilotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RelativeTime(CopilotModel):
    kind: Literal["relative"]
    offset_minutes: Annotated[int, Field(strict=True, ge=-44640, le=44640)]


class LocalTime(CopilotModel):
    kind: Literal["station_local"]
    day: Literal["today", "tomorrow", "yesterday"]
    clock: Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9](?:\.[0-9]{1,6})?)?$")]


class AbsoluteTime(CopilotModel):
    kind: Literal["absolute"]
    timestamp: PatchDatetime


TimeSelection = Annotated[RelativeTime | LocalTime | AbsoluteTime, Field(discriminator="kind")]


class WhyIntent(CopilotModel):
    kind: Literal["why"]
    topic: WhyTopic
    subject: Literal["own_booking", "booking", "station"]
    booking_id: Id | None = None
    at: TimeSelection | None = None


class VehicleChange(CopilotModel):
    op: Literal["revise_vehicle"]
    booking_id: Id | None = None
    target_soc: Soc | None = None
    deadline: TimeSelection | None = None

    @model_validator(mode="after")
    def _require_change(self) -> "VehicleChange":
        if self.target_soc is None and self.deadline is None:
            raise ValueError("Provide a target or deadline")
        return self


class SourceChange(CopilotModel):
    op: Literal["site_limit"]
    grid_input_kw: GridInputKw
    hypothetical_infrastructure: Annotated[bool, Field(strict=True)] = False


class ConnectorOutage(CopilotModel):
    op: Literal["outage"]
    connector_id: Id | None = None
    connector_zone: Literal["AC", "DC"] | None = None
    duration_minutes: Horizon
    starts_at: TimeSelection | None = None


class WhatIfIntent(CopilotModel):
    kind: Literal["what_if"]
    change: Annotated[VehicleChange | SourceChange | ConnectorOutage, Field(discriminator="op")]
    horizon_minutes: Horizon | None = None


class HowToIntent(CopilotModel):
    kind: Literal["how_to"]
    goal: Literal["max_soc_by_deadline", "earliest_completion_for_target", "min_tested_site_limit_for_sla", "other"]


ClarifyField = Literal[
    "intent",
    "booking",
    "connector",
    "time",
    "duration",
    "target",
    "grid_input",
    "infrastructure",
    "bounds",
    "sacrifices",
]


class ClarifyIntent(CopilotModel):
    kind: Literal["clarify"]
    field: ClarifyField


class UnsupportedIntent(CopilotModel):
    kind: Literal["unsupported"]


CopilotIntent = Annotated[
    WhyIntent | WhatIfIntent | HowToIntent | ClarifyIntent | UnsupportedIntent, Field(discriminator="kind")
]


class ParsedCopilotIntent(CopilotModel):
    """Provider output. It can express only requests, never execution authority."""

    intent: CopilotIntent


class CopilotQueryRequest(CopilotModel):
    message: str | None = Field(default=None, min_length=1, max_length=1000)
    job_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None = None
    selected_booking_id: Id | None = None
    selected_connector_id: Id | None = None

    @model_validator(mode="after")
    def _select_query_mode(self) -> "CopilotQueryRequest":
        if (self.message is None) == (self.job_id is None):
            raise ValueError("Provide one of message or job_id")
        if self.job_id is not None and (self.selected_booking_id is not None or self.selected_connector_id is not None):
            raise ValueError("A job follow-up uses only its job ID")
        if self.message is not None and not self.message.strip():
            raise ValueError("Message must contain a question")
        return self


class WhatIfRequest(CopilotModel):
    patch: WhatIfPatch
    horizon_minutes: Horizon = DEFAULT_HORIZON_MINUTES


class CopilotRequestFieldError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class CopilotRequestValidation(BaseModel):
    detail: list[CopilotRequestFieldError]


class CopilotConnector(CopilotModel):
    connector_id: str
    zone: Literal["AC", "DC"]


class CopilotContext(CopilotModel):
    station_id: str
    role: Role
    timezone: str
    as_of: AwareDatetime
    booking_ids: tuple[str, ...]
    connectors: tuple[CopilotConnector, ...]
    default_horizon_minutes: int = DEFAULT_HORIZON_MINUTES
    max_horizon_minutes: int = MAX_COUNTERFACTUAL_HORIZON_MINUTES


class GroundedClaim(CopilotModel):
    claim_id: str
    subject: str
    name: str
    value: bool | int | float | str | None
    unit: str | None = None
    stage: FactStage | Literal["simulated"]
    observed_at: AwareDatetime
    interval_start: AwareDatetime | None = None
    interval_end: AwareDatetime | None = None
    evidence_refs: tuple[str, ...]
    branch: Literal["baseline", "patched", "delta", "candidate"] | None = None
    direction: Literal["patched_minus_baseline", "baseline_minus_patched"] | None = None
    reason_code: str | None = None
    reason_category: EvidenceCategory | None = None


ParseSource = Literal["provider", "deterministic"]


class WhyReply(CopilotModel):
    kind: Literal["why"] = "why"
    result: WhyAnswer
    claims: tuple[GroundedClaim, ...]
    summary: str
    parse_source: ParseSource | None = None


class WhatIfReply(CopilotModel):
    kind: Literal["what_if"] = "what_if"
    result: WhatIfResult
    claims: tuple[GroundedClaim, ...]
    summary: str


class HowToRequest(CopilotModel):
    goal: RecommendationGoal
    horizon_minutes: Horizon = DEFAULT_HORIZON_MINUTES


class HowToReply(CopilotModel):
    kind: Literal["how_to"] = "how_to"
    result: RecommendationResult
    claims: tuple[GroundedClaim, ...]
    summary: str


CopilotResult = Annotated[WhyReply | WhatIfReply | HowToReply, Field(discriminator="kind")]


class CopilotJob(CopilotModel):
    job_id: str
    job_kind: Literal["what_if", "how_to"]
    status: WhatIfJobStatus
    error: Literal["timeout", "execution_failed", "grounding_failed"] | None = None
    result: CopilotResult | None = None
    applied: Literal[False] = False


class JobReply(CopilotModel):
    kind: Literal["job"] = "job"
    job: CopilotJob
    parse_source: ParseSource | None = None


class CopilotNotice(CopilotModel):
    kind: Literal["notice"] = "notice"
    code: Literal["clarify", "unsupported", "feature_not_available", "structured_fallback"]
    message: str
    field: ClarifyField | None = None
    intent: Literal["how_to"] | None = None
    parse_source: ParseSource | None = None


CopilotQueryReply = Annotated[WhyReply | JobReply | CopilotNotice, Field(discriminator="kind")]
