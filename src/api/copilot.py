"""Resident and operator Decision Copilot routes (ADR AI-4)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status

from src.api.deps import AuthenticatedUser
from src.models.api import ErrorResponse
from src.models.copilot import WhyQuery
from src.models.copilot_integration import (
    CopilotContext,
    CopilotQueryReply,
    CopilotQueryRequest,
    CopilotRequestValidation,
    JobReply,
    WhatIfRequest,
    WhyReply,
)
from src.services.copilot.integration import CopilotIntegration

router = APIRouter(prefix="/copilot", tags=["copilot"])
_SUBMIT_ERRORS = {
    422: {"model": ErrorResponse | CopilotRequestValidation, "description": "Invalid hypothetical operation or fields"},
    429: {"model": ErrorResponse, "description": "Copilot workload is at capacity"},
}


def get_copilot(request: Request) -> CopilotIntegration:
    return request.app.state.copilot


Copilot = Annotated[CopilotIntegration, Depends(get_copilot)]
JobId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


@router.get("/context", response_model=CopilotContext)
async def context(user: AuthenticatedUser, copilot: Copilot, response: Response) -> CopilotContext:
    """Station clock and authorized choices for structured input."""
    response.headers["Cache-Control"] = "no-store"
    return await copilot.context(user)


@router.post("/query", response_model=CopilotQueryReply, responses={202: {"model": JobReply}, **_SUBMIT_ERRORS})
async def query(
    body: CopilotQueryRequest, user: AuthenticatedUser, copilot: Copilot, response: Response
) -> CopilotQueryReply:
    """Route a question or retrieve the authorized result of a job follow-up."""
    result = await copilot.query(user, body)
    if isinstance(result, JobReply) and body.job_id is None:
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.post("/why", response_model=WhyReply)
async def why(body: WhyQuery, user: AuthenticatedUser, copilot: Copilot) -> WhyReply:
    """Read authorized deterministic WHY evidence."""
    return await copilot.why(user, body)


@router.post("/what-if", status_code=202, response_model=JobReply, responses=_SUBMIT_ERRORS)
async def what_if(body: WhatIfRequest, user: AuthenticatedUser, copilot: Copilot) -> JobReply:
    """Submit a bounded sandbox simulation."""
    return await copilot.what_if(user, body)


@router.get("/jobs/{job_id}", response_model=JobReply)
async def get_job(job_id: JobId, user: AuthenticatedUser, copilot: Copilot, response: Response) -> JobReply:
    """Poll a caller-owned job."""
    response.headers["Cache-Control"] = "no-store"
    return copilot.job(user, job_id)


@router.delete("/jobs/{job_id}", response_model=JobReply)
async def cancel_job(job_id: JobId, user: AuthenticatedUser, copilot: Copilot) -> JobReply:
    """Request cancellation of a caller-owned job."""
    return copilot.job(user, job_id, cancel=True)
