"""Test tích hợp toàn diện cho Agent F1 với 3 chế độ (openai / local / mock) và 6 tool sạc.

Kiểm chứng:
1. LLM_PROVIDER=mock + AGENT_DEMO_SERVICES=true chạy thật cả 6 tool sạc qua LangGraph và FastAPI.
2. Hội thoại nhiều lượt (hỏi thiếu trường → bổ sung → propose_charging_plan → confirm_booking HITL S3).
3. Guardrail check_grounded_numbers bắt số kWh hoặc mã đầu nối bịa ngoài tool_trace.
4. Trang test nhanh /api/v1/dev/agent khi bật AGENT_PLAYGROUND=true.
"""

import pytest

from src.agents.guardrails import GuardrailViolation, guardrails
from src.config import get_settings
from src.models.control import Role
from src.services import charging_demo


@pytest.fixture
def mock_agent_env(monkeypatch):
    """Bật chế độ mock LLM + dịch vụ sạc giả lập trong bộ nhớ cho toàn bộ test trong file này."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("AGENT_DEMO_SERVICES", "true")
    monkeypatch.setenv("AGENT_PLAYGROUND", "true")
    get_settings.cache_clear()
    charging_demo.reset()
    yield
    charging_demo.reset()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_mock_agent_runs_lookup_and_energy_tools(client, mock_agent_env, as_role):
    as_role(Role.RESIDENT, user_id="res-tools")

    r1 = await client.post("/api/v1/chat", json={"message": "Tra giúp mình mẫu xe DEMO-60"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["analysis"] == "lookup_vehicle"
    assert "60.0 kWh" in d1["response"] or "60 kWh" in d1["response"]

    r2 = await client.post("/api/v1/chat", json={"message": "Tính kWh cho xe DEMO-60 từ 32% lên 80%"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["analysis"] == "estimate_charging_energy"
    assert "28.8 kWh" in d2["response"]


@pytest.mark.asyncio
async def test_mock_agent_multi_turn_propose_confirm_queue_and_explain(client, mock_agent_env, as_role):
    as_role(Role.RESIDENT, user_id="res-e2e")
    sid = "session-e2e-1"

    # Lượt 1: thiếu % pin hiện tại và mode → Agent hỏi lại, chưa gọi tool
    t1 = (
        await client.post("/api/v1/chat", json={"message": "Cần 80% pin trước 7h sáng mai", "session_id": sid})
    ).json()
    assert t1["status"] == "answer"
    assert t1["analysis"] == ""
    assert "% pin hiện tại" in t1["response"]

    # Lượt 2: bổ sung phần thiếu → Agent đủ 6 trường → gọi propose_charging_plan
    t2 = (
        await client.post(
            "/api/v1/chat",
            json={"message": "Mình đang ở bãi, pin còn 32%", "session_id": sid},
        )
    ).json()
    assert t2["status"] == "answer"
    assert t2["analysis"] == "propose_charging_plan"
    assert "28.8 kWh" in t2["response"]

    # Lượt 3: cư dân nhắn "chốt" → confirm_booking dừng ở HITL interrupt (màn S3)
    t3 = (await client.post("/api/v1/chat", json={"message": "Chốt lịch này nhé", "session_id": sid})).json()
    assert t3["status"] == "needs_confirmation"
    assert t3["pending"]["tool"] == "confirm_booking"
    assert t3["proposal"]["feasible"] is True
    assert t3["proposal"]["energy"]["battery_energy_kwh"] == pytest.approx(28.8)
    # Mã đầu nối do hệ thống gán (định dạng ADR-010, vd AC-01-1) — dùng lại ở lượt 6, không hardcode
    assigned_connector = t3["proposal"]["connector_id"]
    assert assigned_connector

    # Lượt 4: cư dân bấm "Xác nhận" ở màn S3 → resume="approve" → đặt lịch thành công
    t4 = (await client.post("/api/v1/chat/resume", json={"session_id": sid, "resume": "approve"})).json()
    assert t4["status"] == "answer"
    assert t4["analysis"] == "confirm_booking"
    assert "confirmed" in t4["response"]

    # Lượt 5: kiểm tra hàng đợi (get_queue_status)
    t5 = (
        await client.post(
            "/api/v1/chat",
            json={"message": "Mình đang xếp thứ mấy trong hàng đợi?", "session_id": sid},
        )
    ).json()
    assert t5["analysis"] == "get_queue_status"

    # Lượt 6: hỏi giải thích lịch sạc (explain_schedule)
    t6 = (
        await client.post(
            "/api/v1/chat",
            json={"message": "Vì sao lịch sạc của mình được xếp như vậy?", "session_id": sid},
        )
    ).json()
    assert t6["analysis"] == "explain_schedule"
    # Câu giải thích phải nhắc đúng đầu nối đã được gán cho booking
    assert assigned_connector in t6["response"]


@pytest.mark.asyncio
async def test_mock_agent_infeasible_request_offers_alternatives(client, mock_agent_env, as_role):
    as_role(Role.RESIDENT, user_id="res-infeasible")
    # 5% lên 100% (57 kWh) với đầu nối 7 kW không thể xong kịp nếu deadline quá sát
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    soon = (datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")) + timedelta(hours=1)).strftime("%H:%M")
    resp = (
        await client.post(
            "/api/v1/chat",
            json={"message": f"Mình đang ở bãi, xe DEMO-60, pin còn 5%, cần 100% trước {soon}"},
        )
    ).json()
    assert resp["analysis"] == "propose_charging_plan"
    assert "Phương án thay thế" in resp["response"]


def test_check_grounded_numbers_validates_kwh_and_connector():
    trace = [
        {
            "tool": "propose_charging_plan",
            "args": {},
            "output": '{"connector_id": "A07", "energy": {"battery_energy_kwh": 28.8, "grid_energy_kwh": 32.0}}',
        }
    ]
    # Hợp lệ: mọi con số kWh và mã đầu nối đều nằm trong trace
    guardrails.check_grounded_numbers("Sạc tại A07, nạp 28.8 kWh (lưới 32.0 kWh).", trace)

    # Bịa kWh không có trong trace → chặn
    with pytest.raises(GuardrailViolation, match="kWh"):
        guardrails.check_grounded_numbers("Sạc tại A07, nạp 45.5 kWh.", trace)

    # Bịa mã đầu nối không có trong trace → chặn
    with pytest.raises(GuardrailViolation, match="A03"):
        guardrails.check_grounded_numbers("Sạc tại A03, nạp 28.8 kWh.", trace)


@pytest.mark.asyncio
async def test_finalize_node_enforces_grounded_numbers():
    from src.agents.nodes.finalize_node import _make_finalize
    from src.models.schemas import FinalAnswer

    async def _bad_generator(state, partial: bool = False) -> FinalAnswer:
        return FinalAnswer(answer="Sạc tại A05, nạp 99.9 kWh.", confidence=0.9, used_tools=[])

    node = _make_finalize(_bad_generator, partial=False)
    with pytest.raises(GuardrailViolation, match="99.9 kWh"):
        await node({"query": "xếp lịch", "tool_trace": []})


@pytest.mark.asyncio
async def test_llm_generate_skips_second_llm_call_when_no_tools_used(monkeypatch):
    """Tối ưu RPM: khi reason trả action='final' (không gọi tool) và đã có final_answer,
    llm_generate dùng luôn câu đó mà không tốn thêm 1 request LLM ở tầng generate.
    """
    from src.agents.nodes import finalize_node

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()

    def _must_not_call_llm(*args, **kwargs):
        raise AssertionError("Không được gọi LLM tầng generate khi không có tool_trace và đã có final_answer")

    monkeypatch.setattr(finalize_node, "get_structured_llm", _must_not_call_llm)
    ans = await finalize_node.llm_generate(
        {
            "query": "Cần 80% trước 7h sáng mai",
            "tool_trace": [],
            "last_decision": {"action": "final", "final_answer": "Bạn cho mình biết thêm % pin hiện tại nhé?"},
        },
        partial=False,
    )
    assert ans.answer == "Bạn cho mình biết thêm % pin hiện tại nhé?"
    assert ans.used_tools == []


@pytest.mark.asyncio
async def test_playground_page_and_no_token_demo_access(client, mock_agent_env):
    page = await client.get("/api/v1/dev/agent")
    assert page.status_code == 200
    assert "Agent F1 Playground" in page.text

    # Khi AGENT_PLAYGROUND=true, gọi /api/v1/chat không cần Bearer token vẫn dùng DEMO_RESIDENT
    chat = await client.post("/api/v1/chat", json={"message": "Tra giúp mình mẫu xe DEMO-60"})
    assert chat.status_code == 200
    assert chat.json()["analysis"] == "lookup_vehicle"


def test_resolve_time_month_boundary_and_timezone():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from src.agents.mock_llm import _extract_draft, _resolve_time

    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    end_of_month = datetime(2026, 11, 30, 23, 30, tzinfo=tz)
    assert _resolve_time(end_of_month, 7, 0, force_next_day=True) == "2026-12-01T07:00:00+07:00"

    draft_after_midnight = _extract_draft(
        {
            "query": "Vừa cắm xe, còn 20%, mai 7h sáng cần 80%",
            "turn_context": {"now": "2026-11-30T00:30:00+07:00", "timezone": "Asia/Ho_Chi_Minh"},
        }
    )
    assert draft_after_midnight.get("_deadline_ambiguous") is True
