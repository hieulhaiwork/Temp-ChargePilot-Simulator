"""Typed internal contracts for AI-4.2B WHAT-IF."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter, model_validator

from src.models.copilot import MAX_COUNTERFACTUAL_HORIZON_MINUTES


def _iso_datetime(value: object) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(value, datetime):
        return value
    raise ValueError("Provide an ISO-8601 timestamp with an offset")


PatchDatetime = Annotated[AwareDatetime, BeforeValidator(_iso_datetime)]


class ReviseVehicle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["revise_vehicle"]
    booking_id: str = Field(strict=True, min_length=1, max_length=64)
    target_soc: float | None = Field(default=None, strict=True, ge=0, le=100, allow_inf_nan=False)
    deadline: PatchDatetime | None = None

    @model_validator(mode="after")
    def _has_change(self) -> "ReviseVehicle":
        if self.target_soc is None and self.deadline is None:
            raise ValueError("Provide target_soc or deadline")
        return self


class SiteLimit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["site_limit"]
    grid_input_kw: float = Field(strict=True, gt=0, allow_inf_nan=False)
    hypothetical_infrastructure: bool = Field(default=False, strict=True)


class Outage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["outage"]
    connector_id: str = Field(strict=True, min_length=1, max_length=64)
    starts_at: PatchDatetime | None = None
    duration_minutes: int = Field(strict=True, gt=0, le=MAX_COUNTERFACTUAL_HORIZON_MINUTES)


WhatIfPatch = Annotated[ReviseVehicle | SiteLimit | Outage, Field(discriminator="op")]
PATCH_ADAPTER: TypeAdapter[WhatIfPatch] = TypeAdapter(WhatIfPatch)


class CommitmentOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_soc: float = Field(ge=0, le=100)
    deadline: AwareDatetime
    target_reached_at: AwareDatetime | None
    already_satisfied_at_snapshot: bool
    met_deadline: bool | None
    remaining_battery_kwh: float
    remaining_output_kwh: float


class WhatIfVehicleOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    booking_id: str
    baseline_original: CommitmentOutcome
    patched_original: CommitmentOutcome
    patched_revised: CommitmentOutcome | None
    baseline_plug_in_at: AwareDatetime | None
    patched_plug_in_at: AwareDatetime | None
    baseline_first_charge_at: AwareDatetime | None
    patched_first_charge_at: AwareDatetime | None
    baseline_release_at: AwareDatetime | None
    patched_release_at: AwareDatetime | None
    initial_soc_pct: float
    baseline_final_soc_pct: float
    patched_final_soc_pct: float
    baseline_horizon_battery_kwh: float
    patched_horizon_battery_kwh: float


class SlaMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cohort_size: int
    denominator: int
    met_count: int
    on_time_rate: float | None
    censored_count: int


class StationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cohort_size: int
    sla: SlaMetrics
    by_zone: dict[str, SlaMetrics]
    service_coverage_denominator: int
    service_coverage_rate: float | None
    charged_coverage_rate: float | None
    plug_wait_observed_count: int
    plug_wait_censored_count: int
    plug_wait_mean_minutes: float | None
    plug_wait_p90_minutes: float | None
    charge_wait_observed_count: int
    charge_wait_censored_count: int
    charge_wait_mean_minutes: float | None
    charge_wait_p90_minutes: float | None
    horizon_battery_kwh: float
    horizon_output_kwh: float
    horizon_grid_input_kwh: float
    horizon_energy_cost_vnd: float
    unmet_original_battery_kwh: float
    unmet_original_output_kwh: float
    peak_charger_output_kw: float
    peak_grid_input_kw: float


class WhatIfBranch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    input_sha256: str
    config_sha256: str
    final_physics_sha256: str
    status: Literal["completed", "unsafe", "unresolved_safety"]
    observed_until: AwareDatetime
    metrics: StationMetrics
    hard_violations: int
    rejected_allocations: int
    sampled_grid_over_limit_minutes: int
    unresolved_safety_count: int
    blocked_commands: int
    pending_approvals: int
    pending_approval_commands: int


class WhatIfResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    applied: Literal[False] = False
    status: Literal["completed", "unsafe", "incomplete"]
    snapshot_id: str
    snapshot_digest: str
    snapshot_time: AwareDatetime
    state_version: int
    experiment_fingerprint: str
    event_manifest_sha256: str
    horizon_end: AwareDatetime
    horizon_minutes: int
    known_booking_count: int
    known_limit_event_count: int
    patch: WhatIfPatch
    patch_sha256: str
    hypothetical_infrastructure: bool
    baseline: WhatIfBranch
    patched: WhatIfBranch
    delta: dict[str, float | None] | None
    feasible: bool | None
    affected_vehicles: tuple[WhatIfVehicleOutcome, ...]
    assumptions: tuple[str, ...]


class WhatIfJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class WhatIfJobView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    applied: Literal[False] = False
    job_id: str
    status: WhatIfJobStatus
    error: Literal["timeout", "execution_failed"] | None = None
    result: WhatIfResult | None = None
