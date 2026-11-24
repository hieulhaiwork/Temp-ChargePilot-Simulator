"""Màn S8 — mô phỏng kịch bản & đối chứng (F7, FR18, US8). Owner: TV1. Task: T3.4, T3.5."""

import asyncio
import functools

from fastapi import APIRouter, HTTPException, status

from src.api.deps import OperatorUser
from src.models.api import SimulationRunRequest
from src.models.simulation import BenchmarkReport, Incident, PolicyInfo, Scenario, SimulationRunResult
from src.services import catalog, simulation_service

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("/scenarios", response_model=list[Scenario])
async def scenarios(user: OperatorUser) -> list[Scenario]:
    """Dropdown "Kịch bản" ở S8 — nạp từ config/scenarios/*.yaml (chạy thật)."""
    return catalog.list_scenarios()


@router.post("/runs", response_model=SimulationRunResult)
async def run(body: SimulationRunRequest, user: OperatorUser) -> SimulationRunResult:
    """S8 nút "▶ Chạy" — một kịch bản × một chiến lược → bảng KPI."""
    try:
        scenario = catalog.load_scenario(body.scenario_id)
    except catalog.UnknownScenarioError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Không có kịch bản {body.scenario_id!r}") from None
    overrides = body.model_dump(include={"n_vehicles", "power_limit_kw", "seed"}, exclude_none=True)
    # Mô phỏng 24 h mất vài giây (LP mỗi bước) — chạy ở thread riêng để không chặn event loop / WebSocket.
    # policy_id luôn có sau validate (client cũ gửi strategy ⇒ policy_id = strategy.value).
    return await asyncio.to_thread(
        functools.partial(
            simulation_service.run_scenario,
            scenario.model_copy(update=overrides),
            body.strategy or body.policy_id,
            strict_incidents=bool(body.strict_incidents),
        )
    )


@router.get("/policies", response_model=list[PolicyInfo])
async def policies(user: OperatorUser) -> list[PolicyInfo]:
    """Policy hợp lệ của Planning Core — đọc từ registry (cùng nguồn với runtime / benchmark), không chép tay."""
    return simulation_service.list_policies()


@router.post("/incidents", status_code=202)
async def inject_incident(body: Incident, user: OperatorUser) -> dict[str, str]:
    """US6 — bơm sự cố (trụ hỏng / nguồn giảm) vào simulator đang chạy để demo trực tiếp."""
    await simulation_service.inject_incident(body)
    return {"status": "accepted"}


@router.get("/benchmark", response_model=BenchmarkReport)
async def benchmark(user: OperatorUser) -> BenchmarkReport:
    """US8 — bảng B0 / M2b / M3a / M3b của baseline có version hiện hành; `source` ghi nguồn + version + điều kiện đo."""
    return simulation_service.latest_benchmark()
