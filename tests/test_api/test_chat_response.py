"""Regression: _to_chat_response chỉ gắn phương án của CHÍNH lượt đó (G5) và không lấy proposal cũ
của phiên cho interrupt không phải confirm_booking. Proposal nằm trong state theo phiên (graph.py entry_node
không reset), nên lấy bừa sẽ hiện lại thẻ phương án cũ."""

from datetime import UTC, datetime
from types import SimpleNamespace

from src.api.routes import _to_chat_response
from src.llm_chat.graph import CONFIRM_TOOL_NAME
from src.models.charging import EnergyEstimate, ScheduleProposal


def _stale_proposal() -> dict:
    energy = EnergyEstimate(
        vehicle_model="DEMO-60",
        soc_now=32,
        soc_target=80,
        battery_energy_kwh=28.8,
        grid_energy_kwh=32.0,
        efficiency=0.9,
    )
    return ScheduleProposal(
        feasible=True, energy=energy, planned_start=datetime(2026, 11, 25, 8, tzinfo=UTC)
    ).model_dump(mode="json")


def test_answer_turn_without_planning_does_not_return_previous_proposal():
    result = {
        "response": "Xin chào",
        "tool_trace": [{"tool": "get_status", "args": {}, "output": "{}"}],
        "proposal": _stale_proposal(),
    }
    assert _to_chat_response(result, "s1").proposal is None


def test_answer_turn_that_planned_keeps_its_proposal():
    result = {
        "response": "Phương án của bạn",
        "tool_trace": [{"tool": "propose_charging_plan", "args": {}, "output": "{}"}],
        "proposal": _stale_proposal(),
    }
    assert _to_chat_response(result, "s1").proposal is not None


def test_interrupt_for_unrelated_risky_tool_does_not_carry_stale_proposal():
    payload = {
        "question": "Phê duyệt hành động rủi ro này của agent?",
        "tool": "send_email",
        "args": {"to": "x"},
        "proposal": _stale_proposal(),
    }
    result = {"__interrupt__": [SimpleNamespace(value=payload)]}
    response = _to_chat_response(result, "s1")
    assert response.proposal is None
    assert response.status == "needs_confirmation"
    assert response.response.startswith("[CẦN PHÊ DUYỆT]")


def test_interrupt_for_confirm_booking_carries_its_proposal():
    payload = {"tool": CONFIRM_TOOL_NAME, "args": {}, "proposal": _stale_proposal()}
    result = {"__interrupt__": [SimpleNamespace(value=payload)]}
    assert _to_chat_response(result, "s1").proposal is not None


def test_rejected_confirmation_is_not_reported_as_booked():
    """G4: người dùng bấm "Đổi phương án" (reject) → human_review ghi BLOCKED_BY_HUMAN, KHÔNG phải đặt lịch."""
    from src.api.routes import _confirmed_booking_succeeded

    rejected = {"tool_trace": [{"tool": CONFIRM_TOOL_NAME, "args": {}, "output": "BLOCKED_BY_HUMAN"}]}
    assert _confirmed_booking_succeeded(rejected) is False


def test_approved_confirmation_is_reported_as_booked():
    from src.api.routes import _confirmed_booking_succeeded

    approved = {"tool_trace": [{"tool": CONFIRM_TOOL_NAME, "args": {}, "output": '{"booking_id": "bk-1"}'}]}
    assert _confirmed_booking_succeeded(approved) is True


def test_confirmation_text_shows_station_local_time_not_utc():
    """G13/G3: câu xác nhận phải in giờ của trạm (Asia/Ho_Chi_Minh, UTC+7), không in giờ UTC thô."""
    from src.api.routes import _confirmation_text

    proposal = ScheduleProposal(
        feasible=True,
        energy=EnergyEstimate(
            vehicle_model="DEMO-60",
            soc_now=32,
            soc_target=80,
            battery_energy_kwh=28.8,
            grid_energy_kwh=32.0,
            efficiency=0.9,
        ),
        connector_id="AC-01-1",
        planned_start=datetime(2026, 11, 25, 8, 0, tzinfo=UTC),
        planned_end=datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
    )
    text = _confirmation_text(proposal, "Asia/Ho_Chi_Minh")
    assert "15:00–17:00" in text
    assert "08:00" not in text
