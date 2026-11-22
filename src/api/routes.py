"""API chat với Agent F1 — /chat, /chat/resume, /status.

Graph compile với checkpointer nên mọi lần invoke cần `configurable.thread_id`. Client giữ
session_id và gửi lại kèm resume khi cư dân bấm "Xác nhận" / "Đổi phương án" ở màn S3.

ChargePilot (ADR-006):
  - Cả hai endpoint yêu cầu vai trò `resident`.
  - `resident_id` lấy từ token và đặt vào config["configurable"] — tool đọc ở đó, LLM không điền được.
  - thread_id = "{user_id}:{session_id}": người này không resume được phiên của người khác.
Lỗi (ADR-008): NotImplementedError / DomainError đi thẳng ra handler chung; lỗi nhà cung cấp LLM
thành 503 `llm_unavailable` để frontend chuyển sang form (NFR khả dụng). Không trả `str(exc)` cho client.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse
from langgraph.types import Command
from openai import OpenAIError
from pydantic import BaseModel, ValidationError

from src.agents.graph import agent
from src.api.deps import ResidentUser
from src.config import get_settings
from src.models.api import ErrorCode, UserProfile
from src.models.charging import ScheduleProposal
from src.models.schemas import ChatRequest, ChatResponse
from src.services import catalog, charging_demo
from src.services.errors import DomainError
from src.services.llm import describe_provider

logger = logging.getLogger("chargepilot.api.chat")

router = APIRouter()

CHAT_STREAM_TIMEOUT_SECONDS = 60.0
MAX_CONCURRENT_STREAMS_PER_USER = 3
_active_user_streams: dict[str, int] = defaultdict(int)


def _config(user: UserProfile, session_id: str) -> dict:
    return {"configurable": {"thread_id": f"{user.user_id}:{session_id}", "resident_id": user.user_id}}


def _turn_context(user: UserProfile) -> dict:
    """Bối cảnh do SERVER cung cấp cho lượt chat — gửi giờ địa phương của trạm (T2.5)."""
    tz_name = catalog.load_station_config().timezone
    return {
        "now": datetime.now(ZoneInfo(tz_name)).isoformat(),
        "timezone": tz_name,
        "vehicle_model": user.vehicle_model,
        "display_name": user.display_name,
    }


def _proposal_from(payload: dict) -> ScheduleProposal | None:
    raw = payload.get("proposal")
    if not raw:
        return None
    try:
        return ScheduleProposal.model_validate(raw)
    except ValidationError:
        logger.error("FAILED chat — payload interrupt có proposal sai schema")
        return None


def _to_chat_response(result: dict, session_id: str) -> ChatResponse:
    # Cả /chat lẫn /chat/resume đều có thể dừng ở interrupt (hành động rủi ro kế tiếp).
    if "__interrupt__" in result:
        interrupts = result["__interrupt__"]
        payload = getattr(interrupts[0], "value", interrupts[0])
        structured = payload if isinstance(payload, dict) else {}
        proposal = _proposal_from(structured)
        if proposal is not None:
            msg = (
                "[CẦN PHÊ DUYỆT] Vui lòng kiểm tra phương án sạc bên dưới và chọn "
                "“Xác nhận lịch” để giữ chỗ hoặc “Đổi phương án” để điều chỉnh."
            )
        else:
            question = structured.get("question") or "Vui lòng xác nhận thao tác này."
            tool_name = structured.get("tool")
            msg = f"[CẦN PHÊ DUYỆT] {question}" + (f" ({tool_name})." if tool_name else "")
        return ChatResponse(
            response=msg,
            analysis="HITL interrupt",
            session_id=session_id,
            status="needs_confirmation",
            proposal=proposal,
            pending={"tool": structured.get("tool"), "args": structured.get("args")} if structured else None,
        )
    trace = result.get("tool_trace", [])
    analysis = "; ".join(entry["tool"] for entry in trace)
    turn_proposal = (
        _proposal_from(result) if any(entry.get("tool") == "propose_charging_plan" for entry in trace) else None
    )
    return ChatResponse(
        response=result.get("response", ""),
        analysis=analysis,
        session_id=session_id,
        status="refused" if result.get("refusal_reason") else "answer",
        proposal=turn_proposal,
        suggestions=list(result.get("suggestions") or []),
    )


async def _invoke(payload: dict | Command, config: dict) -> dict:
    try:
        return await agent.ainvoke(payload, config=config)
    except OpenAIError as exc:
        logger.error(
            "FAILED chat — nhà cung cấp LLM lỗi: %s (%s)", type(exc).__name__, getattr(exc, "status_code", "-")
        )
        raise DomainError(
            ErrorCode.LLM_UNAVAILABLE, "Trợ lý tạm thời không dùng được. Bạn có thể đặt lịch bằng form."
        ) from exc


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: ResidentUser) -> ChatResponse:
    """Chat với Agent (S2). `status = needs_confirmation` nghĩa là đang chờ cư dân xác nhận ở S3."""
    payload = {"query": request.message, "turn_context": _turn_context(user)}
    result = await _invoke(payload, _config(user, request.session_id))
    return _to_chat_response(result, request.session_id)


def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, user: ResidentUser) -> StreamingResponse:
    """Chat streaming (SSE) cho S2 — phát tiến độ node, từng đoạn câu trả lời và ChatResponse cuối."""
    if _active_user_streams[user.user_id] >= MAX_CONCURRENT_STREAMS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Bạn đang mở quá nhiều luồng chat đồng thời. Vui lòng đợi phản hồi hiện tại hoàn tất.",
        )
    _active_user_streams[user.user_id] += 1
    payload = {"query": request.message, "turn_context": _turn_context(user)}
    config = _config(user, request.session_id)

    async def _generate():
        stage_labels = {
            "guardrail": "Đang kiểm tra yêu cầu…",
            "reason": "Trợ lý đang phân tích nhu cầu…",
            "act": "Đang tra cứu & tính phương án…",
            "assess": "Đang tổng hợp kết quả…",
            "human_review": "Đang chuẩn bị xác nhận đặt lịch…",
        }
        final_state: dict = {}
        try:
            async with asyncio.timeout(CHAT_STREAM_TIMEOUT_SECONDS):
                async for mode, chunk in agent.astream(payload, config=config, stream_mode=["updates", "values"]):
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
            _active_user_streams[user.user_id] = max(0, _active_user_streams[user.user_id] - 1)
            if _active_user_streams[user.user_id] == 0:
                _active_user_streams.pop(user.user_id, None)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ResumeRequest(BaseModel):
    session_id: str  # bắt buộc — lấy từ ChatResponse.session_id của /chat
    resume: str  # "approve" | "reject"


@router.post("/chat/resume", response_model=ChatResponse)
async def chat_resume(request: ResumeRequest, user: ResidentUser) -> ChatResponse:
    """S3 — "Xác nhận" (approve) hoặc "Đổi phương án" (reject) cho hành động đang chờ."""
    result = await _invoke(Command(resume=request.resume), _config(user, request.session_id))
    return _to_chat_response(result, request.session_id)


@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    settings = get_settings()
    return {
        "status": "ready",
        "agent": "LangGraph Agent v2.0",
        "llm": describe_provider(),
        "demo_services": settings.agent_demo_services,
        "playground": settings.agent_playground,
    }


@router.post("/dev/agent/reset", include_in_schema=False)
async def reset_demo_state():
    """Xoá booking giả lập trong bộ nhớ khi test trên /dev/agent."""
    if not get_settings().agent_playground:
        raise HTTPException(status_code=404, detail="Playground đang tắt (AGENT_PLAYGROUND=false)")
    charging_demo.reset()
    return {"status": "reset"}


@router.get("/dev/agent", response_class=HTMLResponse, include_in_schema=False)
async def agent_playground_page() -> HTMLResponse:
    """Trang web nhỏ để test nhanh Agent F1 + 6 tool + HITL S3 khi AGENT_PLAYGROUND=true."""
    if not get_settings().agent_playground:
        raise HTTPException(status_code=404, detail="Playground đang tắt (bật AGENT_PLAYGROUND=true trong .env)")
    return HTMLResponse(_PLAYGROUND_HTML)


_PLAYGROUND_HTML = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <title>ChargePilot — Agent F1 Playground</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 860px; margin: 24px auto; padding: 0 16px; background: #0f172a; color: #e2e8f0; }
    h1 { font-size: 1.35rem; margin-bottom: 4px; }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; background: #1e293b; font-size: 0.8rem; color: #38bdf8; }
    .presets { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }
    button { cursor: pointer; border: 1px solid #334155; background: #1e293b; color: #e2e8f0; padding: 6px 12px; border-radius: 6px; font-size: 0.85rem; }
    button:hover { background: #334155; }
    button.primary { background: #0284c7; border-color: #0284c7; color: #fff; }
    button.approve { background: #16a34a; border-color: #16a34a; color: #fff; }
    button.reject { background: #dc2626; border-color: #dc2626; color: #fff; }
    #log { background: #020617; border: 1px solid #1e293b; border-radius: 8px; padding: 14px; min-height: 300px; max-height: 460px; overflow-y: auto; }
    .msg { margin: 8px 0; padding: 10px 12px; border-radius: 8px; line-height: 1.45; white-space: pre-wrap; }
    .user { background: #1e3a8a; align-self: flex-end; }
    .bot { background: #1e293b; }
    .meta { font-size: 0.75rem; color: #94a3b8; margin-top: 4px; }
    .row { display: flex; gap: 8px; margin-top: 12px; }
    input { flex: 1; padding: 10px; border-radius: 6px; border: 1px solid #334155; background: #020617; color: #e2e8f0; }
    #hitl { display: none; margin-top: 12px; padding: 12px; border-radius: 8px; background: #1e293b; border: 1px solid #f59e0b; }
  </style>
</head>
<body>
  <h1>ChargePilot — Agent F1 Playground <span id="status-badge" class="badge">loading...</span></h1>
  <div class="presets">
    <button onclick="sendText('Tra giúp mình mẫu xe DEMO-60')">1. lookup_vehicle</button>
    <button onclick="sendText('Tính kWh cho xe DEMO-60 từ 32% lên 80%')">2. estimate_charging_energy</button>
    <button onclick="sendText('Cần 80% pin trước 7h sáng mai')">3. Hỏi thiếu trường (multi-turn)</button>
    <button onclick="sendText('Mình vừa về tới bãi, pin còn 32%, cần 80% trước 7h sáng mai')">4. propose_charging_plan</button>
    <button onclick="sendText('Chốt lịch này giúp mình')">5. confirm_booking (HITL S3)</button>
    <button onclick="sendText('Mình đang xếp thứ mấy trong hàng đợi?')">6. get_queue_status</button>
    <button onclick="sendText('Vì sao lịch sạc của mình được xếp như vậy?')">7. explain_schedule</button>
    <button onclick="newSession()">+ Phiên mới / Reset booking</button>
  </div>
  <div id="log"></div>
  <div id="hitl">
    <strong>[Màn S3 — Cần cư dân xác nhận đặt lịch]</strong>
    <div id="hitl-detail" class="meta"></div>
    <div style="margin-top:8px; display:flex; gap:8px;">
      <button class="approve" onclick="resumeChat('approve')">Xác nhận đặt lịch (Approve)</button>
      <button class="reject" onclick="resumeChat('reject')">Đổi phương án (Reject)</button>
    </div>
  </div>
  <div class="row">
    <input id="msg" placeholder="Nhập câu chat với Trợ lý sạc ChargePilot..." onkeydown="if(event.key==='Enter')sendInput()" />
    <button class="primary" onclick="sendInput()">Gửi</button>
  </div>
<script>
  let sessionId = crypto.randomUUID().replace(/-/g, '');
  async function loadStatus() {
    const r = await fetch('/api/v1/status');
    const d = await r.json();
    document.getElementById('status-badge').textContent =
      `provider=${d.llm?.provider} | model=${d.llm?.model} | demo_services=${d.demo_services}`;
  }
  function appendMsg(role, text, meta='') {
    const log = document.getElementById('log');
    const div = document.createElement('div');
    div.className = 'msg ' + (role === 'user' ? 'user' : 'bot');
    div.textContent = text;
    if (meta) {
      const m = document.createElement('div');
      m.className = 'meta';
      m.textContent = meta;
      div.appendChild(m);
    }
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }
  function handleResponse(d) {
    const meta = `status=${d.status} | tools=${d.analysis || '(none)'} | session=${d.session_id.slice(0,8)}`;
    appendMsg('bot', d.response, meta);
    const hitl = document.getElementById('hitl');
    if (d.status === 'needs_confirmation') {
      hitl.style.display = 'block';
      document.getElementById('hitl-detail').textContent = d.proposal
        ? `Đầu nối ${d.proposal.connector_id} | ${d.proposal.energy.battery_energy_kwh} kWh | ${d.proposal.estimated_cost_vnd} VND`
        : JSON.stringify(d.pending || {});
    } else {
      hitl.style.display = 'none';
    }
  }
  async function sendText(text) {
    appendMsg('user', text);
    const r = await fetch('/api/v1/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text, session_id: sessionId})
    });
    handleResponse(await r.json());
  }
  function sendInput() {
    const inp = document.getElementById('msg');
    if (!inp.value.trim()) return;
    sendText(inp.value.trim());
    inp.value = '';
  }
  async function resumeChat(decision) {
    appendMsg('user', `[S3] ${decision}`);
    const r = await fetch('/api/v1/chat/resume', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session_id: sessionId, resume: decision})
    });
    handleResponse(await r.json());
  }
  async function newSession() {
    sessionId = crypto.randomUUID().replace(/-/g, '');
    await fetch('/api/v1/dev/agent/reset', {method: 'POST'});
    document.getElementById('log').innerHTML = '';
    document.getElementById('hitl').style.display = 'none';
    appendMsg('bot', 'Đã tạo phiên mới và xoá booking giả lập.');
  }
  loadStatus();
</script>
</body>
</html>
"""
