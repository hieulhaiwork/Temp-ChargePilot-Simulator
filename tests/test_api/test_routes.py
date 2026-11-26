import pytest

from src.models.control import Role


@pytest.fixture
def resident(as_role):
    """/chat và PATCH /chat/sessions/{session_id} yêu cầu vai trò resident (ADR-006)."""
    return as_role(Role.RESIDENT)


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_empty_message(client, resident):
    response = await client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_without_session_id_gets_own_session(client, monkeypatch, resident):
    from src.api import routes
    from src.llm_chat.schemas import AgentDecision
    from tests.conftest import ScriptedReasoner, make_test_graph

    final = AgentDecision(thought="t", action="final", enough_data=True, final_answer="ok")
    monkeypatch.setattr(routes, "agent", make_test_graph(ScriptedReasoner([final, final])))

    first = (await client.post("/api/v1/chat", json={"message": "Chào"})).json()
    second = (await client.post("/api/v1/chat", json={"message": "Chào"})).json()

    assert first["session_id"] and second["session_id"]
    assert first["session_id"] != second["session_id"]


@pytest.mark.asyncio
async def test_resume_requires_session_id_and_valid_decision(client, resident):
    missing_session = await client.patch("/api/v1/chat/sessions/", json={"resume": "approve"})
    assert missing_session.status_code == 404
    invalid_body = await client.patch("/api/v1/chat/sessions/s1", json={})
    assert invalid_body.status_code == 422


@pytest.mark.asyncio
async def test_chat_analysis_only_lists_tool_names(client, monkeypatch, resident):
    from src.api import routes
    from src.llm_chat.schemas import AgentDecision
    from tests.conftest import ScriptedReasoner, make_test_graph

    lookup = AgentDecision(
        thought="Tra thông số xe.",
        action="tool",
        tool_name="lookup_vehicle",
        tool_args={"vehicle_model": "DEMO-60"},
        enough_data=True,
    )
    monkeypatch.setattr(routes, "agent", make_test_graph(ScriptedReasoner([lookup])))

    response = await client.post("/api/v1/chat", json={"message": "Tra giúp mình mẫu DEMO-60."})

    assert response.status_code == 200
    assert response.json()["analysis"] == "lookup_vehicle"


@pytest.mark.asyncio
async def test_resume_surfaces_second_interrupt(client, monkeypatch, resident):
    from src.api import routes
    from src.llm_chat.schemas import AgentDecision
    from tests.conftest import ScriptedReasoner, make_test_graph

    email = AgentDecision(
        thought="gửi",
        action="tool",
        tool_name="send_email",
        tool_args={"to": "a@example.com", "subject": "s", "body": "b"},
    )
    monkeypatch.setattr(routes, "agent", make_test_graph(ScriptedReasoner([email, email])))

    first = (await client.post("/api/v1/chat", json={"message": "Gửi 2 email"})).json()
    resumed = await client.patch(f"/api/v1/chat/sessions/{first['session_id']}", json={"resume": "approve"})

    assert resumed.status_code == 200
    assert resumed.json()["response"].startswith("[CẦN PHÊ DUYỆT]")


@pytest.mark.asyncio
async def test_chat_stream_returns_sse_events(client, monkeypatch, resident):
    from src.api import routes
    from src.llm_chat.schemas import AgentDecision
    from tests.conftest import ScriptedReasoner, make_test_graph

    final = AgentDecision(thought="t", action="final", enough_data=True, final_answer="Xin chào cư dân")
    monkeypatch.setattr(routes, "agent", make_test_graph(ScriptedReasoner([final])))

    response = await client.post("/api/v1/chat/stream", json={"message": "Chào", "session_id": "s-stream"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type": "status"' in response.text
    assert '"type": "delta"' in response.text
    assert '"type": "done"' in response.text
    assert '"session_id": "s-stream"' in response.text


@pytest.mark.asyncio
async def test_chat_stream_enforces_concurrent_limit_and_timeout(client, monkeypatch, resident):
    from src.api import routes

    monkeypatch.setattr(routes, "MAX_CONCURRENT_STREAMS_PER_USER", 1)
    routes._active_user_streams[resident.user_id] = 1
    try:
        too_many = await client.post("/api/v1/chat/stream", json={"message": "Chào", "session_id": "s-limit"})
        assert too_many.status_code == 429
    finally:
        routes._active_user_streams.pop(resident.user_id, None)
