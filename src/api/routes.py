"""API chat với Agent F1 — /chat, /chat/sessions/{session_id}, /status.

Graph compile với checkpointer nên mọi lần invoke cần `configurable.thread_id`. Client giữ
session_id và gửi lại kèm resume khi cư dân bấm "Xác nhận" / "Đổi phương án" ở màn S3.

ChargePilot (ADR-006):
  - Chat và job phân tích dùng danh tính đã xác thực của cư dân hoặc vận hành.
  - Resume booking và transcribe chỉ dành cho cư dân.
  - Runtime context giữ user và service. Checkpointer chỉ thấy định danh thread đã băm.
Lỗi (ADR-008): NotImplementedError / DomainError đi thẳng ra handler chung; lỗi nhà cung cấp LLM
thành 503 `llm_unavailable` để frontend chuyển sang form (NFR khả dụng). Không trả `str(exc)` cho client.
"""

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime
from hashlib import sha256
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from anyio import move_on_after
from fastapi import APIRouter, HTTPException, Path, Request, Response, status
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from openai import OpenAIError
from pydantic import BaseModel, ValidationError
from starlette.types import Receive, Scope, Send

from src.api.deps import CurrentUser, ResidentUser
from src.config import get_settings
from src.llm_chat.graph import BLOCKED_BY_HUMAN, CONFIRM_TOOL_NAME, TOOL_ERROR_PREFIX, ChatContext, agent
from src.models.api import ErrorCode, UserProfile
from src.models.charging import ChargeRequest, ScheduleProposal
from src.models.control import Role
from src.models.copilot_integration import JobReply
from src.models.schemas import ChatRequest, ChatResponse, TranscribeRequest, TranscribeResponse
from src.services import catalog, charging_service, speech
from src.services.errors import DomainError
from src.services.llm import describe_provider
from src.services.runtime import get_runtime

logger = logging.getLogger("chargepilot.api.chat")

router = APIRouter()

CHAT_STREAM_TIMEOUT_SECONDS = 60.0
MAX_CONCURRENT_STREAMS_PER_USER = 3
MAX_GLOBAL_CONCURRENT_TURNS = 8
_active_user_streams: dict[str, int] = defaultdict(int)
_active_global_turns = 0
_active_threads: set[str] = set()


def _context(request: Request, user: UserProfile, session_id: str) -> ChatContext:
    credential = request.headers.get("Authorization", "").partition(" ")[2].strip()
    scope = sha256(json.dumps([user.user_id, user.role, credential, session_id]).encode()).hexdigest()
    return ChatContext(user=user, session=scope, copilot=getattr(request.app.state, "copilot", None))


def _config(context: ChatContext) -> dict:
    configurable = {"thread_id": context.session}
    if context.user.role == Role.RESIDENT:
        configurable["resident_id"] = context.user.user_id
    return {"configurable": configurable}


def _turn_context(context: ChatContext) -> dict:
    user = context.user
    tz_name = catalog.load_station_config().timezone
    return {
        "now": datetime.now(ZoneInfo(tz_name)).isoformat(),
        "station_now": get_runtime().simulator.now.isoformat() if context.copilot else None,
        "timezone": tz_name,
        "vehicle_model": user.vehicle_model,
        "role": user.role.value,
    }


def _reserve_thread(context: ChatContext) -> None:
    global _active_global_turns
    user_id = context.user.user_id
    if _active_user_streams.get(user_id, 0) >= MAX_CONCURRENT_STREAMS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Bạn đang mở quá nhiều luồng chat đồng thời. Vui lòng đợi phản hồi hiện tại hoàn tất.",
        )
    if _active_global_turns >= MAX_GLOBAL_CONCURRENT_TURNS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trợ lý đang xử lý tối đa số lượt đồng thời. Vui lòng thử lại sau giây lát.",
        )
    if context.session in _active_threads:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phiên chat đang xử lý một yêu cầu.")
    _active_threads.add(context.session)
    _active_user_streams[user_id] += 1
    _active_global_turns += 1


def _release_thread(context: ChatContext) -> None:
    global _active_global_turns
    user_id = context.user.user_id
    _active_threads.discard(context.session)
    _active_user_streams[user_id] = max(0, _active_user_streams[user_id] - 1)
    if _active_user_streams[user_id] == 0:
        _active_user_streams.pop(user_id, None)
    _active_global_turns = max(0, _active_global_turns - 1)


def _proposal_from(payload: dict) -> ScheduleProposal | None:
    raw = payload.get("proposal")
    if not raw:
        return None
    try:
        return ScheduleProposal.model_validate(raw)
    except ValidationError:
        logger.error("FAILED chat — payload interrupt có proposal sai schema")
        return None


_PUBLIC_DRAFT_KEYS = frozenset({"vehicle_model", "soc_now", "soc_target", "zone", "mode", "arrival_time", "deadline"})


def _public_draft(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    cleaned = {k: v for k, v in raw.items() if k in _PUBLIC_DRAFT_KEYS and v is not None}
    return cleaned or None


def _request_from(payload: dict) -> ChargeRequest | None:
    """G3: yêu cầu đang chờ xác nhận, lấy từ interrupt của confirm_booking. Sai schema → None, không đoán."""
    if payload.get("tool") != CONFIRM_TOOL_NAME:
        return None
    raw = (payload.get("args") or {}).get("request")
    if not raw:
        return None
    try:
        return ChargeRequest.model_validate(raw)
    except ValidationError:
        logger.error("FAILED chat — interrupt confirm_booking có request sai schema")
        return None


def _confirmation_text(proposal: ScheduleProposal | None, timezone: str) -> str:
    """G13: câu cho cư dân, dựng từ proposal (đầu nối, khung giờ, kWh) — không lấy chuỗi kỹ thuật của graph.

    Giờ hiển thị theo múi giờ của trạm: planned_* là datetime có tzinfo (UTC), in thẳng sẽ lệch."""
    if proposal is None or not proposal.feasible or proposal.connector_id is None:
        return "Bạn xác nhận thao tác này không?"
    window = ""
    if proposal.planned_start and proposal.planned_end:
        tz = ZoneInfo(timezone)
        start = proposal.planned_start.astimezone(tz)
        end = proposal.planned_end.astimezone(tz)
        window = f", khung giờ {start:%H:%M}–{end:%H:%M}"
    kwh = proposal.energy.battery_energy_kwh
    return f"Phương án: đầu nối {proposal.connector_id}{window}, {kwh:g} kWh. Bạn xác nhận lịch này không?"


def _to_chat_response(result: dict, session_id: str) -> ChatResponse:
    # Cả /chat lẫn PATCH /chat/sessions/{session_id} đều có thể dừng ở interrupt (hành động rủi ro kế tiếp).
    if "__interrupt__" in result:
        interrupts = result["__interrupt__"]
        payload = getattr(interrupts[0], "value", interrupts[0])
        structured = payload if isinstance(payload, dict) else {}
        tool_name = structured.get("tool")
        # Chỉ confirm_booking mang phương án của lượt này; interrupt rủi ro khác không được lấy proposal cũ của phiên.
        proposal = _proposal_from(structured) if tool_name == CONFIRM_TOOL_NAME else None
        if proposal is not None:
            body = _confirmation_text(proposal, get_runtime().config.timezone)
        else:
            question = structured.get("question") or "Vui lòng xác nhận thao tác này."
            body = question
        return ChatResponse(
            response=f"[CẦN PHÊ DUYỆT] {body}",
            analysis="HITL interrupt",
            session_id=session_id,
            status="needs_confirmation",
            proposal=proposal,
            request=_request_from(structured),
            pending={"tool": structured.get("tool"), "args": structured.get("args")} if structured else None,
            draft=_public_draft(result.get("draft_request")),
        )
    trace = result.get("tool_trace", [])
    analysis = "; ".join(entry["tool"] for entry in trace)
    # G5: phương án chỉ gắn khi CHÍNH lượt này vừa tính; proposal trong state là của phiên, có thể đã cũ.
    turn_proposal = (
        _proposal_from(result) if any(entry.get("tool") == "propose_charging_plan" for entry in trace) else None
    )
    return ChatResponse(
        response=result.get("response", ""),
        analysis=analysis,
        session_id=session_id,
        status="refused" if result.get("refusal_reason") else "answer",
        advisory=result.get("copilot_results", []),
        proposal=turn_proposal if not result.get("copilot_results") else None,
        suggestions=list(result.get("suggestions") or []),
        draft=_public_draft(result.get("draft_request")),
    )


def _pending_interrupts(snapshot) -> list:
    """Các interrupt đang chờ trong thread (rỗng = không còn gì để resume)."""
    pending: list = []
    for task in getattr(snapshot, "tasks", None) or ():
        pending.extend(getattr(task, "interrupts", None) or ())
    return pending


def _confirmed_booking_succeeded(result: dict) -> bool:
    """G4: lượt resume vừa chốt lịch thành công (tool confirm_booking không báo lỗi)."""
    trace = result.get("tool_trace") or []
    return any(
        entry.get("tool") == CONFIRM_TOOL_NAME
        and str(entry.get("output", "")) != BLOCKED_BY_HUMAN
        and not str(entry.get("output", "")).startswith(TOOL_ERROR_PREFIX)
        for entry in trace
    )


async def _abort_turn_state(config: dict) -> None:
    try:
        snap = await agent.aget_state(config)
        if snap and _pending_interrupts(snap):
            return
        await agent.aupdate_state(config, {"pending_copilot_clarification": None, "turn_in_progress": False})
    except Exception:
        logger.debug("chat — skip abort state cleanup", exc_info=True)


async def _invoke(payload: dict | Command, context: ChatContext) -> dict:
    config = _config(context)
    try:
        async with asyncio.timeout(CHAT_STREAM_TIMEOUT_SECONDS):
            return await agent.ainvoke(payload, config=config, context=context)
    except (OpenAIError, TimeoutError) as exc:
        await _abort_turn_state(config)
        logger.error(
            "FAILED chat — nhà cung cấp LLM lỗi: %s (%s)", type(exc).__name__, getattr(exc, "status_code", "-")
        )
        raise DomainError(
            ErrorCode.LLM_UNAVAILABLE, "Trợ lý tạm thời không dùng được. Bạn có thể đặt lịch bằng form."
        ) from exc
    except BaseException:
        await _abort_turn_state(config)
        raise


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: CurrentUser, http_request: Request) -> ChatResponse:
    """Chat với Agent (S2). `status = needs_confirmation` nghĩa là đang chờ cư dân xác nhận ở S3."""
    context = _context(http_request, user, request.session_id)
    _reserve_thread(context)
    try:
        result = await _invoke({"query": request.message, "turn_context": _turn_context(context)}, context)
        return _to_chat_response(result, request.session_id)
    finally:
        _release_thread(context)


def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"


class _ManagedChatStream(StreamingResponse):
    """Release the turn even when disconnect happens before the body iterator starts."""

    def __init__(self, *args, cleanup: Callable[[], Awaitable[None]], **kwargs):
        super().__init__(*args, **kwargs)
        self._cleanup = cleanup

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._cleanup()


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, user: CurrentUser, http_request: Request) -> StreamingResponse:
    """Chat streaming (SSE) cho S2 — phát tiến độ node, từng đoạn câu trả lời và ChatResponse cuối."""
    context = _context(http_request, user, request.session_id)
    payload = {"query": request.message, "turn_context": _turn_context(context)}
    config = _config(context)
    _reserve_thread(context)
    final_state: dict = {}
    stream_completed = False
    released = False

    async def _cleanup() -> None:
        nonlocal released
        if released:
            return
        released = True
        try:
            if not stream_completed and "__interrupt__" not in final_state:
                # Starlette cancels the body iterator in an AnyIO cancel scope.
                # Bound and shield cleanup; always release admission in finally.
                with move_on_after(2, shield=True):
                    await _abort_turn_state(config)
        finally:
            _release_thread(context)

    async def _generate():
        nonlocal final_state, stream_completed
        stage_labels = {
            "guardrail": "Đang kiểm tra yêu cầu…",
            "reason": "Trợ lý đang phân tích nhu cầu…",
            "act": "Đang tra cứu & tính phương án…",
            "assess": "Đang tổng hợp kết quả…",
            "human_review": "Đang chuẩn bị xác nhận đặt lịch…",
        }
        try:
            async with asyncio.timeout(CHAT_STREAM_TIMEOUT_SECONDS):
                async for mode, chunk in agent.astream(
                    payload, config=config, context=context, stream_mode=["updates", "values"]
                ):
                    if mode == "updates" and isinstance(chunk, dict):
                        for node_name, node_out in chunk.items():
                            if isinstance(node_out, dict):
                                stage = node_out.get("stage") or node_name
                                if stage in stage_labels:
                                    yield _sse("status", {"stage": stage, "label": stage_labels[stage]})
                    elif mode == "values" and isinstance(chunk, dict):
                        final_state = chunk

                if "__interrupt__" not in final_state:
                    snap = await agent.aget_state(config)
                    if snap and getattr(snap, "tasks", None):
                        for task in snap.tasks:
                            if getattr(task, "interrupts", None):
                                final_state = {**final_state, "__interrupt__": task.interrupts}
                                break

                chat_resp = _to_chat_response(final_state, request.session_id)
                if "__interrupt__" not in final_state and chat_resp.response:
                    words = chat_resp.response.split(" ")
                    for idx in range(0, len(words), 3):
                        piece = " ".join(words[idx : idx + 3]) + (" " if idx + 3 < len(words) else "")
                        yield _sse("delta", {"text": piece})
                        await asyncio.sleep(0)

                stream_completed = True
                yield _sse("done", {"data": chat_resp.model_dump(mode="json")})
        except (TimeoutError, OpenAIError) as exc:
            logger.error(
                "FAILED chat/stream — nhà cung cấp LLM lỗi hoặc quá hạn: %s (%s)",
                type(exc).__name__,
                getattr(exc, "status_code", "-"),
            )
            yield _sse(
                "error",
                {
                    "code": ErrorCode.LLM_UNAVAILABLE,
                    "detail": "Trợ lý tạm thời không dùng được hoặc phản hồi quá thời gian. Bạn có thể đặt lịch bằng form.",
                },
            )
        finally:
            await _cleanup()

    return _ManagedChatStream(
        _generate(),
        cleanup=_cleanup,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ChatSessionResumeRequest(BaseModel):
    resume: Literal["approve", "reject"]  # 422 nếu giá trị khác (G1)


@router.patch("/chat/sessions/{session_id}", response_model=ChatResponse)
async def chat_resume(
    session_id: Annotated[str, Path(min_length=1, max_length=128)],
    request: ChatSessionResumeRequest,
    user: ResidentUser,
    http_request: Request,
) -> ChatResponse:
    """S3 — "Xác nhận" (approve) hoặc "Đổi phương án" (reject) cho hành động đang chờ.

    G1: thread không còn interrupt (backend restart, bấm lặp) → 409, KHÔNG chạy graph với đầu vào rỗng.
    """
    context = _context(http_request, user, session_id)
    _reserve_thread(context)
    try:
        snapshot = await agent.aget_state(_config(context))
        if not _pending_interrupts(snapshot):
            raise DomainError(ErrorCode.NO_PENDING_CONFIRMATION, "Phiên chat không còn yêu cầu nào đang chờ xác nhận")
        result = await _invoke(Command(resume=request.resume), context)
        response = _to_chat_response(result, session_id)
        if response.status == "answer" and _confirmed_booking_succeeded(result):
            response.booking = charging_service.current_booking(user.user_id)
        return response
    finally:
        _release_thread(context)


ChatSessionId = Annotated[str, Path(min_length=1, max_length=128)]
ChatJobId = Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]


@router.get("/chat/sessions/{session_id}/jobs/{job_id}", response_model=JobReply)
@router.delete("/chat/sessions/{session_id}/jobs/{job_id}", response_model=JobReply)
async def chat_job(
    session_id: ChatSessionId, job_id: ChatJobId, user: CurrentUser, request: Request, response: Response
) -> JobReply:
    response.headers["Cache-Control"] = "no-store"
    context = _context(request, user, session_id)
    if context.copilot is None:
        raise DomainError(ErrorCode.COPILOT_NOT_READY, "Trợ lý phân tích chưa sẵn sàng.")
    return context.copilot.job(user, job_id, session=context.session, cancel=request.method == "DELETE")


@router.post("/chat/transcribe", response_model=TranscribeResponse)
async def chat_transcribe(request: TranscribeRequest, user: ResidentUser) -> TranscribeResponse:
    """Nhận giọng nói tiếng Việt đa vùng miền (Bắc/Trung/Nam) và trả về văn bản để cư dân kiểm tra trước khi gửi."""
    _ = user  # ADR-006: yêu cầu cư dân đã đăng nhập
    return await speech.transcribe_audio(request.audio_base64, request.mime_type)


@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    settings = get_settings()
    return {
        "status": "ready",
        "agent": "LangGraph Agent v2.0",
        "llm": describe_provider(),
        "demo_services": settings.agent_demo_services,
    }
