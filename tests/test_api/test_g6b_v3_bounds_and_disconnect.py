import asyncio
import json

import pytest
from starlette.requests import Request

from src.api import routes
from src.llm_chat.graph import build_graph
from src.llm_chat.schemas import AgentDecision
from src.services import auth as auth_service
from tests.test_api.test_copilot import demo_api as demo_api
from tests.test_api.test_unified_copilot import chat, decision, provider, wait_chat_job
from tests.test_services.test_recommendation import _site


@pytest.mark.asyncio
async def test_bound_never_silently_truncates_constraint(demo_api, monkeypatch):
    client, _, _, _, _, _, operator = demo_api
    prefix = (
        "Cần nguồn bao nhiêu để đạt mục tiêu đúng hạn 95%? Giữ xe AC đúng hạn. "
        + "Tôi muốn đọc kết quả phân tích để hiểu rõ tình hình. " * 22
    )
    first = prefix + "Bắt đầu từ ngày mai lúc 18h00."
    assert 1000 < len(prefix) < len(first) <= 5000
    provider(
        monkeypatch,
        {"thought": "missing bounds", "action": "clarify", "clarify_field": "bounds"},
        decision("copilot_how_to", {"goal": _site(22, 106, min_original_on_time_rate=0.95), "horizon_minutes": 120}),
    )
    r1 = await chat(client, operator, first, session="long")
    print("LONG1", len(first), r1["advisory"])
    assert r1["advisory"][0]["code"] == "unsupported"

    async def no_capture(*args, **kwargs):
        pytest.fail("An oversized clarification must not create a snapshot or job")

    monkeypatch.setattr("src.services.copilot.integration.capture_atomic_snapshot", no_capture)
    r2 = await chat(client, operator, "Thử 22 đến 106 kW.", session="long")
    a = r2["advisory"][0]
    if a.get("job"):
        j = await wait_chat_job(client, operator, a["job"], session="long")
        print(
            "LONG2",
            json.dumps(
                {"status": j["status"], "goal": j.get("result", {}).get("result", {}).get("goal")}, ensure_ascii=False
            ),
        )
    else:
        print("LONG2", a)
    assert not a.get("job"), "A valid-length request lost a mandatory constraint after the 1000-char pending truncation"


@pytest.mark.asyncio
async def test_real_asgi_disconnect_releases_permit(demo_api, monkeypatch):
    client, _, _, _, _, _, operator = demo_api
    graph = build_graph()
    entered = asyncio.Event()
    steps = iter([{"thought": "missing grid", "action": "clarify", "clarify_field": "grid_input"}, "WAIT"])

    class Model:
        async def ainvoke(self, _):
            nxt = next(steps)
            if nxt == "WAIT":
                entered.set()
                await asyncio.Future()
            return AgentDecision.model_validate(nxt)

    monkeypatch.setattr(routes, "agent", graph)
    monkeypatch.setattr("src.llm_chat.nodes.reason_node.get_structured_llm", lambda *_: Model())
    r1 = await chat(client, operator, "Nếu nguồn cấp riêng của cổng DC-01-1 bị giảm thì sao?", session="disconnect")
    assert r1["advisory"][0]["code"] == "clarify"
    user = auth_service.decode_token(operator["Authorization"].partition(" ")[2])
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/v1/chat/stream",
        "headers": [(b"authorization", operator["Authorization"].encode())],
        "app": client._transport.app,
    }
    req = Request(scope)
    config = routes._config(routes._context(req, user, "disconnect"))
    stream = await routes.chat_stream(routes.ChatRequest(message="50 kW.", session_id="disconnect"), user, req)

    async def receive():
        await entered.wait()
        return {"type": "http.disconnect"}

    async def send(_message):
        pass

    try:
        await asyncio.wait_for(stream(scope, receive, send), 5)
        s = await graph.aget_state(config)
        print(
            "DISCONNECT",
            routes._active_global_turns,
            dict(routes._active_user_streams),
            len(routes._active_threads),
            s.values.get("pending_copilot_clarification"),
            s.values.get("turn_in_progress"),
        )
        assert routes._active_global_turns == 0 and not routes._active_threads and not routes._active_user_streams
        assert s.values.get("pending_copilot_clarification") is None and s.values.get("turn_in_progress") is False
    finally:
        # Isolate tests from the permit leak being probed.
        if routes._active_threads:
            routes._release_thread(routes._context(req, user, "disconnect"))


@pytest.mark.asyncio
async def test_disconnect_before_generator_starts_releases_permit(demo_api, monkeypatch):
    client, _, _, _, _, _, operator = demo_api
    monkeypatch.setattr(routes, "agent", build_graph())
    user = auth_service.decode_token(operator["Authorization"].partition(" ")[2])
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/v1/chat/stream",
        "headers": [(b"authorization", operator["Authorization"].encode())],
        "app": client._transport.app,
    }
    req = Request(scope)
    stream = await routes.chat_stream(routes.ChatRequest(message="50 kW.", session_id="early-disconnect"), user, req)

    async def receive():
        return {"type": "http.disconnect"}

    async def send(_message):
        await asyncio.sleep(0.05)

    try:
        await asyncio.wait_for(stream(scope, receive, send), 5)
        print("EARLY", routes._active_global_turns, dict(routes._active_user_streams), len(routes._active_threads))
        assert routes._active_global_turns == 0 and not routes._active_threads and not routes._active_user_streams
    finally:
        if routes._active_threads:
            routes._release_thread(routes._context(req, user, "early-disconnect"))
