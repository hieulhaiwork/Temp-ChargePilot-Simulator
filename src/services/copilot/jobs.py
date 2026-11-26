"""Bounded, owner-scoped advisory simulation jobs for the single-worker backend."""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from math import isfinite
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from src.models.copilot import ActorContext
from src.models.recommendation import RecommendationGoal, RecommendationResult
from src.models.what_if import WhatIfJobStatus, WhatIfPatch, WhatIfResult
from src.services.copilot.counterfactual import LiveBusyProbe
from src.services.copilot.recommendation import run_recommendation
from src.services.copilot.snapshot import CapturedSnapshot
from src.services.copilot.what_if import DEFAULT_WHAT_IF_TIMEOUT_S, _prepare_patch, run_what_if

logger = logging.getLogger(__name__)


class WhatIfCapacityError(RuntimeError):
    """The job service is at its bounded queue or retention capacity."""


class SimulationJobView(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    job_kind: Literal["what_if", "how_to"]
    status: WhatIfJobStatus
    error: Literal["timeout", "execution_failed"] | None = None
    result: WhatIfResult | RecommendationResult | None = None
    applied: Literal[False] = False


@dataclass
class _Job:
    actor: ActorContext
    view: SimulationJobView
    deadline: float
    snapshot: CapturedSnapshot | None
    workload: WhatIfPatch | RecommendationGoal | None
    session: str | None
    submitted_at: float
    expires_at: float | None = None


class WhatIfJobs:
    """One asynchronous consumer per service. The native solver remains shared."""

    def __init__(
        self,
        *,
        max_queued: int = 4,
        max_retained: int = 64,
        max_active_per_actor: int | None = None,
        ttl_s: float = 300,
        timeout_s: float = DEFAULT_WHAT_IF_TIMEOUT_S,
        live_busy_probe: LiveBusyProbe | None = None,
    ):
        if (
            not 1 <= max_queued < max_retained
            or (max_active_per_actor is not None and max_active_per_actor < 1)
            or not isfinite(ttl_s)
            or ttl_s <= 0
            or not 0 < timeout_s <= 600
        ):
            raise ValueError("Invalid WHAT-IF job bounds")
        self._max_queued = max_queued
        self._max_retained = max_retained
        self._max_active_per_actor = max_active_per_actor
        self._ttl_s = ttl_s
        self._timeout_s = timeout_s
        self._live_busy_probe = live_busy_probe
        self._jobs: dict[str, _Job] = {}
        self._queue: deque[str] = deque()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._worker: asyncio.Task[None] | None = None
        self._active_task: asyncio.Task | None = None
        self._active_id: str | None = None
        self._closed = False

    def _clock(self) -> float:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        if self._loop is not loop:
            raise RuntimeError("WHAT-IF jobs are owned by one event loop")
        return loop.time()

    def _purge(self, now: float) -> None:
        for job_id, job in tuple(self._jobs.items()):
            if job.expires_at is None or now < job.expires_at:
                continue
            if now >= job.expires_at + self._ttl_s:
                del self._jobs[job_id]
            else:
                job.view = job.view.model_copy(
                    update={"status": WhatIfJobStatus.EXPIRED, "result": None, "error": None}
                )

    def submit(
        self, actor: ActorContext, snapshot: CapturedSnapshot, patch: WhatIfPatch | dict, *, session: str | None = None
    ) -> SimulationJobView:
        return self._submit(actor, snapshot, _prepare_patch(snapshot, actor, patch).patch, "what_if", session)

    def submit_recommendation(
        self, actor: ActorContext, snapshot: CapturedSnapshot, goal: RecommendationGoal, *, session: str
    ) -> SimulationJobView:
        return self._submit(actor, snapshot, goal, "how_to", session)

    def check_admission(self, actor: ActorContext, *, session: str | None = None) -> float:
        now = self._clock()
        if self._closed:
            raise RuntimeError("Simulation jobs service is closed")
        self._purge(now)
        if len(self._queue) >= self._max_queued or len(self._jobs) >= self._max_retained:
            raise WhatIfCapacityError("Simulation job capacity exhausted")
        if self._max_active_per_actor is not None:
            active_for_actor = sum(1 for job in self._jobs.values() if job.actor == actor and job.expires_at is None)
            if active_for_actor >= self._max_active_per_actor:
                raise WhatIfCapacityError("Actor already has an active simulation")
        if (session is not None or self._max_active_per_actor is not None) and any(
            job.actor == actor
            and (
                (session is not None and job.expires_at is None)
                or (job.session is not None and now - job.submitted_at < 15)
            )
            for job in self._jobs.values()
        ):
            raise WhatIfCapacityError("Actor already has an active or recent chat simulation")
        return now

    def _submit(
        self,
        actor: ActorContext,
        snapshot: CapturedSnapshot,
        workload: WhatIfPatch | RecommendationGoal,
        kind: Literal["what_if", "how_to"],
        session: str | None,
    ) -> SimulationJobView:
        now = self.check_admission(actor, session=session)
        job_id = uuid4().hex
        view = SimulationJobView(job_id=job_id, job_kind=kind, status=WhatIfJobStatus.QUEUED)
        self._jobs[job_id] = _Job(actor.model_copy(), view, now + self._timeout_s, snapshot, workload, session, now)
        self._queue.append(job_id)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._consume())
        return view

    def _owned(self, actor: ActorContext, job_id: str, session: str | None) -> _Job | None:
        self._purge(self._clock())
        job = self._jobs.get(job_id)
        return job if job is not None and job.actor == actor and job.session == session else None

    def get(self, actor: ActorContext, job_id: str, *, session: str | None = None) -> SimulationJobView | None:
        job = self._owned(actor, job_id, session)
        return None if job is None else job.view.model_copy(deep=True)

    def cancel(self, actor: ActorContext, job_id: str, *, session: str | None = None) -> SimulationJobView | None:
        job = self._owned(actor, job_id, session)
        if job is None:
            return None
        if job.view.status == WhatIfJobStatus.QUEUED:
            self._queue.remove(job_id)
            self._finish(job, WhatIfJobStatus.CANCELLED)
        elif job.view.status == WhatIfJobStatus.RUNNING and self._active_task is not None and self._active_id == job_id:
            self._active_task.cancel()
        return job.view.model_copy(deep=True)

    def _finish(self, job: _Job, status: WhatIfJobStatus, **fields) -> None:
        job.snapshot = None
        job.workload = None
        job.view = job.view.model_copy(update={"status": status, **fields})
        job.expires_at = self._clock() + self._ttl_s

    async def _run(self, job: _Job, remaining: float) -> WhatIfResult | RecommendationResult:
        assert job.snapshot is not None and job.workload is not None
        run = run_recommendation if job.view.job_kind == "how_to" else run_what_if
        return await run(
            job.snapshot, job.actor, job.workload, timeout_s=remaining, live_busy_probe=self._live_busy_probe
        )

    async def _consume(self) -> None:
        while self._queue:
            job_id = self._queue.popleft()
            job = self._jobs[job_id]
            remaining = job.deadline - self._clock()
            if remaining <= 0:
                self._finish(job, WhatIfJobStatus.FAILED, error="timeout")
                continue

            job.view = job.view.model_copy(update={"status": WhatIfJobStatus.RUNNING})
            self._active_id = job_id
            self._active_task = asyncio.create_task(self._run(job, remaining))
            try:
                result = await self._active_task
            except asyncio.CancelledError:
                self._finish(job, WhatIfJobStatus.CANCELLED)
            except TimeoutError:
                self._finish(job, WhatIfJobStatus.FAILED, error="timeout")
            except Exception as exc:
                logger.error(
                    "simulation_job_failed job_id=%s kind=%s error_type=%s",
                    job_id,
                    job.view.job_kind,
                    type(exc).__name__,
                )
                self._finish(job, WhatIfJobStatus.FAILED, error="execution_failed")
            else:
                self._finish(job, WhatIfJobStatus.SUCCEEDED, result=result)
            finally:
                self._active_id = None
                self._active_task = None

    async def close(self) -> None:
        """Stop accepting jobs and wait for coroutine cleanup."""
        self._clock()
        self._closed = True
        while self._queue:
            job_id = self._queue.popleft()
            self._finish(self._jobs[job_id], WhatIfJobStatus.CANCELLED)
        if self._active_task is not None:
            self._active_task.cancel()
        if self._worker is not None:
            await self._worker
