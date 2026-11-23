"""Hợp đồng mô phỏng & đánh giá: kịch bản, sự cố, trace, KPI, benchmark B0 / M2b / M3a / M3b có nguồn + version.

Vì sao tồn tại: màn S8 (F7) và báo cáo eval (AC7) phải dùng CÙNG định nghĩa KPI và
cùng định dạng kịch bản, nếu không số trên web và số trong báo cáo sẽ lệch nhau.
"""

from datetime import time
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from src.models.charging import StrategyName
from src.models.station import LoadPoint


class IncidentType(StrEnum):
    CONNECTOR_FAULT = "connector_fault"
    CONNECTOR_RESTORED = "connector_restored"
    POWER_LIMIT_CHANGE = "power_limit_change"


class Incident(BaseModel):
    """Sự cố bơm vào mô phỏng (US6, FR18, AC5) — dùng cả trong kịch bản lẫn API."""

    type: IncidentType
    connector_id: str | None = None
    new_power_limit_kw: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check_payload(self) -> "Incident":
        if self.type == IncidentType.POWER_LIMIT_CHANGE and self.new_power_limit_kw is None:
            raise ValueError("power_limit_change cần new_power_limit_kw")
        if self.type != IncidentType.POWER_LIMIT_CHANGE and not self.connector_id:
            raise ValueError(f"{self.type} cần connector_id")
        return self


class ScheduledIncident(Incident):
    at_minute: int = Field(ge=0, description="Số phút kể từ đầu kịch bản")


class SessionSource(StrEnum):
    """Nguồn phiên sạc cho mô phỏng (PRD §8)."""

    SYNTHETIC = "synthetic"
    NORWAY_2024 = "norway_2024"  # khu dân cư, 35.377 phiên, 267 người dùng
    NORWAY_2021 = "norway_2021"  # chung cư, 6.878 phiên, 97 người dùng
    ACN = "acn"  # ACN-Data (Caltech), khớp ACN-Sim


class Scenario(BaseModel):
    """Một kịch bản mô phỏng — config/scenarios/<scenario_id>.yaml."""

    scenario_id: str = Field(min_length=1)
    name: str
    description: str = ""
    start_time: time
    duration_hours: int = Field(gt=0, le=24 * 14)
    n_vehicles: int = Field(gt=0)
    power_limit_kw: float = Field(gt=0)
    session_source: SessionSource
    seed: int = 0
    incidents: list[ScheduledIncident] = Field(default_factory=list)

    @model_validator(mode="after")
    def _incidents_inside_horizon(self) -> "Scenario":
        limit = self.duration_hours * 60
        late = [i.at_minute for i in self.incidents if i.at_minute >= limit]
        if late:
            raise ValueError(f"Sự cố ngoài thời lượng kịch bản ({limit} phút): {late}")
        return self


class SessionOutcome(BaseModel):
    """Kết cục của một yêu cầu trong một lần mô phỏng — đầu vào tính KPI."""

    booking_id: str
    accepted: bool
    feasible: bool = Field(description="Có khả thi về vật lý không (loại khỏi mẫu số MT1 nếu không)")
    arrival_time: AwareDatetime
    plug_in_time: AwareDatetime | None = None
    deadline: AwareDatetime
    requested_kwh: float = Field(ge=0)
    delivered_kwh_by_deadline: float = Field(ge=0)


class SimulationTrace(BaseModel):
    """Toàn bộ dữ kiện một lần chạy cần để tính KPI (src/simulator/kpi.py)."""

    step_minutes: int = Field(gt=0)
    outcomes: list[SessionOutcome] = Field(default_factory=list)
    load_trace: list[LoadPoint] = Field(default_factory=list)
    replan_durations_s: list[float] = Field(default_factory=list)
    blocked_commands: int = Field(default=0, ge=0)


class KpiReport(BaseModel):
    """KPI theo PRD §2 (MT1–MT6) và AC7 — định nghĩa chi tiết ở src/simulator/kpi.py."""

    on_time_rate: float = Field(ge=0, le=1, description="MT1 — mục tiêu ≥ 0.95")
    wait_mean_minutes: float = Field(ge=0, description="MT2 — thấp hơn FCFS")
    wait_p90_minutes: float = Field(ge=0, description="MT2 — phân vị 90%")
    unmet_energy_kwh: float = Field(ge=0)
    delivered_energy_kwh: float = Field(
        ge=0, description="Tổng điện đã nạp — so chi phí/kWh ở mức phục vụ tương đương (MT3)"
    )
    service_rate: float = Field(ge=0, le=1)
    energy_cost_vnd: float = Field(ge=0, description="MT3")
    peak_load_kw: float = Field(ge=0)
    power_limit_violations: int = Field(ge=0, description="MT4 — mục tiêu 0")
    replan_p95_seconds: float | None = Field(default=None, ge=0, description="MT5 — mục tiêu ≤ 2 s")
    blocked_commands: int = Field(ge=0, description="MT6 — số lệnh bị Guard chặn")


class SimulationRunResult(BaseModel):
    run_id: str
    scenario_id: str
    strategy: StrategyName
    kpis: KpiReport
    started_at: AwareDatetime
    finished_at: AwareDatetime
    notes: str = ""


class BenchmarkSourceKind(StrEnum):
    VERSIONED_BASELINE = "versioned_baseline"  # số đã đo, lưu có version ở eval/evidence/*-baseline/ (manifest.json)
    GENERATED = "generated"  # vừa sinh bằng eval/run_benchmark.py — chưa phải baseline chính thức


class BenchmarkSource(BaseModel):
    """Nguồn + điều kiện đo của bảng benchmark (Phase 4 quyết định 8): không so hai bảng khác điều kiện."""

    kind: BenchmarkSourceKind
    baseline_id: str | None = None
    version: str | None = None
    status: str | None = Field(default=None, description="provisional = baseline tạm; final = baseline nghiệm thu")
    code_commit: str | None = None
    path: str | None = Field(default=None, description="Đường dẫn trong repo của dữ liệu")
    scenarios: list[str] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)
    seeds: list[int] = Field(default_factory=list)
    time_config: dict[str, int | None] = Field(default_factory=dict, description="TimeConfig của trạm khi đo (P1)")
    libraries: dict[str, str] = Field(default_factory=dict)
    note: str = ""


class BenchmarkReport(BaseModel):
    """Bảng B0 / M2b / M3a / M3b cùng tập phiên, cùng biểu giá (PRD §8, AC7). `source` ghi nguồn + version."""

    generated_at: AwareDatetime
    runs: list[SimulationRunResult]
    notes: list[str] = Field(default_factory=list)
    source: BenchmarkSource | None = Field(default=None, description="Nguồn và version của bảng (Phase 4)")
