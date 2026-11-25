"""Bounded, owner-scoped WHAT-IF jobs for the single-worker backend."""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from math import isfinite
from uuid import uuid4

from src.models.copilot import ActorContext
from src.models.what_if import WhatIfJobStatus, WhatIfJobView, WhatIfPatch
from src.services.copilot.counterfactual import LiveBusyProbe
from src.services.copilot.snapshot import CapturedSnapshot
from src.services.copilot.what_if import DEFAULT_WHAT_IF_TIMEOUT_S, _prepare_patch, run_what_if

logger = logging.getLogger(__name__)


class WhatIfCapacityError(RuntimeError):
    """The job service is at its bounded queue or retention capacity."""


@dataclass
class _Job:
    actor: ActorContext
    view: WhatIfJobView
    deadline: float
    snapshot: CapturedSnapshot | None
    patch: WhatIfPatch | None
    expires_at: float | None = None


class WhatIfJobs:
    """One asynchronous consumer per service. The native solver remains shared."""

    def __init__(
        self,
        *,
        max_queued: int = 4,
        max_retained: int = 64,
        ttl_s: float = 300,
        timeout_s: float = DEFAULT_WHAT_IF_TIMEOUT_S,
        live_busy_probe: LiveBusyProbe | None = None,
    ):
        if not 1 <= max_queued < max_retained or not isfinite(ttl_s) or ttl_s <= 0 or not 0 < timeout_s <= 600:
            raise ValueError("Invalid WHAT-IF job bounds")
        self._max_queued = max_queued
        self._max_retained = max_retained
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
                job.view = WhatIfJobView(job_id=job_id, status=WhatIfJobStatus.EXPIRED)

    def submit(self, actor: ActorContext, snapshot: CapturedSnapshot, patch: WhatIfPatch | dict) -> WhatIfJobView:
        now = self._clock()
        if self._closed:
            raise RuntimeError("WHAT-IF jobs service is closed")
        self._purge(now)
        if len(self._queue) >= self._max_queued or len(self._jobs) >= self._max_retained:
            raise WhatIfCapacityError("WHAT-IF job capacity exhausted")
        prepared = _prepare_patch(snapshot, actor, patch)
        job_id = uuid4().hex
        view = WhatIfJobView(job_id=job_id, status=WhatIfJobStatus.QUEUED)
        self._jobs[job_id] = _Job(actor.model_copy(), view, now + self._timeout_s, snapshot, prepared.patch)
        self._queue.append(job_id)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._consume())
        return view

    def _owned(self, actor: ActorContext, job_id: str) -> _Job | None:
        self._purge(self._clock())
        job = self._jobs.get(job_id)
        return job if job is not None and job.actor == actor else None

    def get(self, actor: ActorContext, job_id: str) -> WhatIfJobView | None:
        job = self._owned(actor, job_id)
        return None if job is None else job.view.model_copy(deep=True)

    def cancel(self, actor: ActorContext, job_id: str) -> WhatIfJobView | None:
        job = self._owned(actor, job_id)
        if job is None:
            return None
        if job.view.status == WhatIfJobStatus.QUEUED:
            self._queue.remove(job_id)
            self._finish(job, WhatIfJobView(job_id=job_id, status=WhatIfJobStatus.CANCELLED))
        elif job.view.status == WhatIfJobStatus.RUNNING and self._active_task is not None and self._active_id == job_id:
            self._active_task.cancel()
        return job.view.model_copy(deep=True)

    def _finish(self, job: _Job, view: WhatIfJobView) -> None:
        job.snapshot = None
        job.patch = None
        job.view = view
        job.expires_at = self._clock() + self._ttl_s

    async def _consume(self) -> None:
        while self._queue:
            job_id = self._queue.popleft()
            job = self._jobs[job_id]
            remaining = job.deadline - self._clock()
            if remaining <= 0:
                self._finish(job, WhatIfJobView(job_id=job_id, status=WhatIfJobStatus.FAILED, error="timeout"))
                continue

            job.view = WhatIfJobView(job_id=job_id, status=WhatIfJobStatus.RUNNING)
            self._active_id = job_id
            assert job.snapshot is not None and job.patch is not None
            self._active_task = asyncio.create_task(
                run_what_if(
                    job.snapshot, job.actor, job.patch, timeout_s=remaining, live_busy_probe=self._live_busy_probe
                )
            )
            try:
                result = await self._active_task
            except asyncio.CancelledError:
                view = WhatIfJobView(job_id=job_id, status=WhatIfJobStatus.CANCELLED)
            except TimeoutError:
                view = WhatIfJobView(job_id=job_id, status=WhatIfJobStatus.FAILED, error="timeout")
            except Exception as exc:
                logger.error("what_if_job_failed job_id=%s error_type=%s", job_id, type(exc).__name__)
                view = WhatIfJobView(job_id=job_id, status=WhatIfJobStatus.FAILED, error="execution_failed")
            else:
                view = WhatIfJobView(job_id=job_id, status=WhatIfJobStatus.SUCCEEDED, result=result)
            finally:
                self._active_id = None
                self._active_task = None
            self._finish(job, view)

    async def close(self) -> None:
        """Stop accepting jobs and wait for coroutine cleanup."""
        self._clock()
        self._closed = True
        while self._queue:
            job_id = self._queue.popleft()
            self._finish(self._jobs[job_id], WhatIfJobView(job_id=job_id, status=WhatIfJobStatus.CANCELLED))
        if self._active_task is not None:
            self._active_task.cancel()
        if self._worker is not None:
            await self._worker
