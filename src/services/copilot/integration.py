"""Server-owned decision routing and lifecycle adapter for G6A."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from src.agents.copilot_grounding import GroundingError, render_what_if, render_why
from src.agents.copilot_intent import CopilotIntentParser
from src.models.api import ErrorCode, UserProfile
from src.models.control import Role
from src.models.copilot import ActorContext, WhyQuery, WhyStatus
from src.models.copilot_integration import (
    DEFAULT_HORIZON_MINUTES,
    AbsoluteTime,
    ClarifyField,
    ClarifyIntent,
    ConnectorOutage,
    CopilotConnector,
    CopilotContext,
    CopilotJob,
    CopilotNotice,
    CopilotQueryReply,
    CopilotQueryRequest,
    HowToIntent,
    JobReply,
    ParseSource,
    RelativeTime,
    SourceChange,
    TimeSelection,
    UnsupportedIntent,
    VehicleChange,
    WhatIfIntent,
    WhatIfRequest,
    WhyIntent,
    WhyReply,
)
from src.models.what_if import Outage, ReviseVehicle, SiteLimit, WhatIfJobView, WhatIfPatch
from src.services import runtime
from src.services.copilot.jobs import WhatIfCapacityError, WhatIfJobs
from src.services.copilot.snapshot import CapturedSnapshot, SnapshotNotReadyError, capture_atomic_snapshot
from src.services.copilot.what_if import WhatIfForbiddenError
from src.services.copilot.why import explain_why
from src.services.errors import DomainError
from src.services.runtime import StationRuntime

_CLARIFICATIONS: dict[ClarifyField, str] = {
    "intent": "Bạn muốn tìm lý do hay mô phỏng một thay đổi? Bạn cũng có thể dùng biểu mẫu.",
    "booking": "Hãy chọn lịch sạc cần xem.",
    "connector": "Hãy chọn một đầu nối cụ thể.",
    "time": "Hãy ghi rõ ngày và giờ tại trạm, hoặc số phút trước/sau thời điểm hiện tại của trạm.",
    "duration": "Sự cố giả định kéo dài bao nhiêu phút?",
    "target": "Mức pin mục tiêu mới là bao nhiêu phần trăm?",
    "grid_input": "Hãy cung cấp công suất đầu vào từ lưới (kW).",
    "infrastructure": "Mức này cần xác nhận giả định nâng cấp hạ tầng.",
}


class _ClarificationError(ValueError):
    def __init__(self, field: ClarifyField) -> None:
        self.field = field


def _resolve_time(selection: TimeSelection | None, now: datetime, timezone: str) -> datetime | None:
    if selection is None:
        return None
    if isinstance(selection, AbsoluteTime):
        return selection.timestamp
    if isinstance(selection, RelativeTime):
        return (now.astimezone(UTC) + timedelta(minutes=selection.offset_minutes)).astimezone(ZoneInfo(timezone))
    zone = ZoneInfo(timezone)
    offset = {"yesterday": -1, "today": 0, "tomorrow": 1}[selection.day]
    day = now.astimezone(zone).date() + timedelta(days=offset)
    naive = datetime.combine(day, time.fromisoformat(selection.clock))
    candidates = set()
    for fold in (0, 1):
        instant = naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(instant)
    if len(candidates) != 1:
        raise _ClarificationError("time")
    return candidates.pop().astimezone(zone)


def _forbidden() -> DomainError:
    return DomainError(ErrorCode.FORBIDDEN, "Bạn không có quyền xem hoặc mô phỏng đối tượng này.")


def _clarify(field: ClarifyField, source: ParseSource) -> CopilotNotice:
    return CopilotNotice(code="clarify", field=field, message=_CLARIFICATIONS[field], parse_source=source)


class CopilotIntegration:
    """One application-owned instance. Engine jobs and parsing have independent bounds."""

    def __init__(
        self,
        *,
        get_runtime: Callable[[], StationRuntime] = runtime.get_runtime,
        parser: CopilotIntentParser | None = None,
        jobs: WhatIfJobs | None = None,
    ) -> None:
        self._get_runtime = get_runtime
        self._parser = parser or CopilotIntentParser()
        self._capture = asyncio.Lock()
        self._jobs = jobs if jobs is not None else WhatIfJobs(live_busy_probe=self._live_busy)

    def _live_busy(self) -> bool:
        rt = self._get_runtime()
        return rt.lock.locked() or rt.has_pending_safety()

    async def close(self) -> None:
        await self._jobs.close()

    async def context(self, user: UserProfile) -> CopilotContext:
        rt = self._get_runtime()
        bookings = await asyncio.to_thread(rt.store.active_bookings)
        actor = ActorContext.from_user(user, rt.config.station_id)
        return CopilotContext(
            station_id=actor.station_id,
            role=actor.role,
            timezone=rt.config.timezone,
            as_of=rt.simulator.now,
            booking_ids=tuple(
                sorted(b.booking_id for b in bookings if actor.role == Role.OPERATOR or b.resident_id == actor.actor_id)
            ),
            connectors=tuple(
                CopilotConnector(connector_id=port.connector_id, zone=port.zone)
                for port in rt.config.connectors
                if actor.role == Role.OPERATOR
            ),
        )

    async def why(self, user: UserProfile, query: WhyQuery, *, source: ParseSource | None = None) -> WhyReply:
        rt = self._get_runtime()
        actor = ActorContext.from_user(user, rt.config.station_id)
        # Explain authorizes the subject before accessing DecisionTrace.
        result = await asyncio.to_thread(
            explain_why,
            query,
            actor,
            station_id=actor.station_id,
            live_physics_clock=rt.simulator.now,
        )
        if result.status == WhyStatus.FORBIDDEN:
            raise _forbidden()
        try:
            return render_why(result, source)
        except GroundingError as exc:
            raise DomainError(ErrorCode.COPILOT_NOT_READY, "Bằng chứng hiện tại chưa đủ để giải thích.") from exc

    async def _booking(
        self,
        rt: StationRuntime,
        actor: ActorContext,
        booking_id: str | None,
    ) -> str:
        if booking_id is not None:
            booking = await asyncio.to_thread(rt.store.get_booking, booking_id)
            if booking is None or (actor.role == Role.RESIDENT and booking.resident_id != actor.actor_id):
                raise _forbidden()
            return booking.booking_id
        if actor.role == Role.RESIDENT:
            bookings = await asyncio.to_thread(rt.store.active_bookings)
            owned = [booking.booking_id for booking in bookings if booking.resident_id == actor.actor_id]
            if len(owned) == 1:
                return owned[0]
        raise _ClarificationError("booking")

    @staticmethod
    def _connector(rt: StationRuntime, intent: ConnectorOutage, selected: str | None) -> str:
        allowed = [
            port.connector_id
            for port in rt.config.connectors
            if intent.connector_zone is None or port.zone == intent.connector_zone
        ]
        requested = intent.connector_id or selected
        if requested is None and len(allowed) == 1:
            return allowed[0]
        if requested is not None:
            match = next((key for key in allowed if key.casefold() == requested.casefold()), None)
            if match and not (
                intent.connector_id and selected and intent.connector_id.casefold() != selected.casefold()
            ):
                return match
        raise _ClarificationError("connector")

    async def _submit(
        self,
        rt: StationRuntime,
        actor: ActorContext,
        horizon: int,
        patch_at_snapshot: Callable[[CapturedSnapshot], WhatIfPatch],
    ) -> JobReply:
        if self._capture.locked():
            raise DomainError(
                ErrorCode.COPILOT_CAPACITY, "Đang chụp trạng thái cho một yêu cầu khác. Vui lòng thử lại."
            )
        try:
            async with self._capture:
                snapshot = await capture_atomic_snapshot(rt, horizon_minutes=horizon)
                view = self._jobs.submit(actor, snapshot, patch_at_snapshot(snapshot))
        except SnapshotNotReadyError as exc:
            raise DomainError(ErrorCode.COPILOT_NOT_READY, "Trạm chưa sẵn sàng để mô phỏng an toàn.") from exc
        except WhatIfForbiddenError as exc:
            raise _forbidden() from exc
        except WhatIfCapacityError as exc:
            raise DomainError(ErrorCode.COPILOT_CAPACITY, "Hàng đợi mô phỏng đã đầy. Vui lòng thử lại.") from exc
        except ValidationError as exc:
            detail = "Thông số mô phỏng không hợp lệ."
            if any(issue["type"] == "deadline_not_on_simulator_minute" for issue in exc.errors()):
                detail = "Hạn mới phải nằm đúng lưới phút của thời điểm chụp trạng thái trạm."
            raise DomainError(ErrorCode.COPILOT_INVALID_PATCH, detail) from exc
        except _ClarificationError:
            raise
        except ValueError as exc:
            message = {
                "Above-installed grid input requires hypothetical_infrastructure": _CLARIFICATIONS["infrastructure"],
                "Revised deadline must follow snapshot time and vehicle arrival": "Hạn mới phải sau thời điểm chụp và lúc xe đến.",
                "Unknown connector": "Đầu nối không hợp lệ.",
                "Outage must start on a simulator minute within the planned horizon": "Sự cố phải bắt đầu đúng lưới phút trong cửa sổ mô phỏng.",
            }.get(str(exc), "Thông số mô phỏng không hợp lệ ở trạng thái hiện tại.")
            raise DomainError(ErrorCode.COPILOT_INVALID_PATCH, message) from exc
        return self._job_reply(view, actor)

    async def what_if(self, user: UserProfile, request: WhatIfRequest) -> JobReply:
        rt = self._get_runtime()
        actor = ActorContext.from_user(user, rt.config.station_id)
        patch = request.patch
        if isinstance(patch, ReviseVehicle):
            await self._booking(rt, actor, patch.booking_id)
        elif actor.role != Role.OPERATOR:
            raise _forbidden()
        return await self._submit(rt, actor, request.horizon_minutes, lambda _: patch)

    def _job_reply(self, view: WhatIfJobView, actor: ActorContext, *, source: ParseSource | None = None) -> JobReply:
        job = CopilotJob(job_id=view.job_id, job_kind="what_if", status=view.status, error=view.error)
        if view.result is not None:
            try:
                job = job.model_copy(update={"result": render_what_if(view.result, actor.station_id)})
            except GroundingError:
                job = job.model_copy(update={"status": "failed", "error": "grounding_failed"})
        return JobReply(job=job, parse_source=source)

    def job(self, user: UserProfile, job_id: str, *, cancel: bool = False) -> JobReply:
        rt = self._get_runtime()
        actor = ActorContext.from_user(user, rt.config.station_id)
        view = self._jobs.cancel(actor, job_id) if cancel else self._jobs.get(actor, job_id)
        if view is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy tác vụ mô phỏng.")
        return self._job_reply(view, actor)

    async def _why_intent(
        self,
        user: UserProfile,
        rt: StationRuntime,
        intent: WhyIntent,
        request: CopilotQueryRequest,
        source: ParseSource,
    ) -> WhyReply:
        subject = intent.subject
        booking = intent.booking_id or request.selected_booking_id
        if intent.booking_id and request.selected_booking_id and intent.booking_id != request.selected_booking_id:
            raise _ClarificationError("booking")
        if subject == "station":
            booking = None
        if subject == "booking" and booking is None:
            raise _ClarificationError("booking")
        if subject == "own_booking" and user.role == Role.OPERATOR:
            if booking is None:
                raise _ClarificationError("booking")
            subject = "booking"
        now = rt.simulator.now
        query = WhyQuery(
            subject_scope=subject,
            topic=intent.topic,
            booking_id=booking,
            at=_resolve_time(intent.at, now, rt.config.timezone) or now,
        )
        return await self.why(user, query, source=source)

    async def _what_if_intent(
        self,
        user: UserProfile,
        rt: StationRuntime,
        intent: WhatIfIntent,
        request: CopilotQueryRequest,
        source: ParseSource,
    ) -> JobReply:
        actor = ActorContext.from_user(user, rt.config.station_id)
        change = intent.change
        booking_id = connector_id = None
        if isinstance(change, VehicleChange):
            if change.booking_id and request.selected_booking_id and change.booking_id != request.selected_booking_id:
                raise _ClarificationError("booking")
            booking_id = await self._booking(rt, actor, change.booking_id or request.selected_booking_id)
        elif actor.role != Role.OPERATOR:
            raise _forbidden()
        elif isinstance(change, ConnectorOutage):
            connector_id = self._connector(rt, change, request.selected_connector_id)

        def patch(snapshot: CapturedSnapshot) -> WhatIfPatch:
            now, tz = snapshot.envelope.as_of, rt.config.timezone
            if isinstance(change, VehicleChange):
                assert booking_id is not None
                return ReviseVehicle(
                    op="revise_vehicle",
                    booking_id=booking_id,
                    target_soc=change.target_soc,
                    deadline=_resolve_time(change.deadline, now, tz),
                )
            if isinstance(change, SourceChange):
                return SiteLimit(
                    op="site_limit",
                    grid_input_kw=change.grid_input_kw,
                    hypothetical_infrastructure=change.hypothetical_infrastructure,
                )
            assert connector_id is not None
            return Outage(
                op="outage",
                connector_id=connector_id,
                duration_minutes=change.duration_minutes,
                starts_at=_resolve_time(change.starts_at, now, tz),
            )

        job = await self._submit(rt, actor, intent.horizon_minutes or DEFAULT_HORIZON_MINUTES, patch)
        return job.model_copy(update={"parse_source": source})

    async def query(self, user: UserProfile, request: CopilotQueryRequest) -> CopilotQueryReply:
        if request.job_id is not None:
            return self.job(user, request.job_id)
        assert request.message is not None
        rt = self._get_runtime()
        intent, source = await self._parser.parse(request.message, rt.simulator.now, rt.config.timezone)
        try:
            match intent:
                case WhyIntent():
                    return await self._why_intent(user, rt, intent, request, source)
                case WhatIfIntent():
                    return await self._what_if_intent(user, rt, intent, request, source)
                case HowToIntent():
                    return CopilotNotice(
                        code="feature_not_available",
                        intent="how_to",
                        parse_source=source,
                        message="Tính năng đề xuất phương án HOW-TO hiện chưa khả dụng.",
                    )
                case ClarifyIntent(field=field):
                    return _clarify(field, source)
                case UnsupportedIntent():
                    return CopilotNotice(
                        code="unsupported",
                        parse_source=source,
                        message="Yêu cầu này nằm ngoài phạm vi WHY và WHAT-IF hiện tại.",
                    )
                case _:
                    return CopilotNotice(
                        code="structured_fallback",
                        parse_source=source,
                        message="Hãy dùng biểu mẫu để chọn câu hỏi hoặc thay đổi cần mô phỏng.",
                    )
        except _ClarificationError as exc:
            return _clarify(exc.field, source)
