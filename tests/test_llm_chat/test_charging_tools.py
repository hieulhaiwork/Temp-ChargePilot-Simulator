"""Tool sạc của Agent F1 — phần chạy thật (danh mục xe, FR3) + đấu nối HITL cho confirm_booking."""

import json

import pytest

from src.llm_chat.tools import RISKY_TOOL_NAMES, TOOL_REGISTRY
from src.models.charging import ChargeRequest
from src.models.schemas import AgentDecision
from src.services.errors import DomainError
from tests.conftest import ScriptedReasoner, make_test_graph

REQUEST = {
    "vehicle_model": "DEMO-60",
    "soc_now": 32,
    "soc_target": 80,
    "arrival_time": "2026-11-16T22:00:00+07:00",
    "deadline": "2026-11-17T07:00:00+07:00",
    "mode": "reservation",
}


def test_lookup_vehicle_returns_spec():
    data = json.loads(TOOL_REGISTRY["lookup_vehicle"].invoke({"vehicle_model": "DEMO-60"}))
    assert data["usable_capacity_kwh"] == 60


def test_lookup_unknown_vehicle_lists_valid_models_instead_of_guessing():
    data = json.loads(TOOL_REGISTRY["lookup_vehicle"].invoke({"vehicle_model": "VF-KHONG-CO"}))
    assert data["error"] == "unknown_vehicle_model"
    assert "DEMO-60" in data["valid_models"]


def test_energy_tool_is_computed_by_code():
    out = TOOL_REGISTRY["estimate_charging_energy"].invoke(
        {"vehicle_model": "DEMO-60", "soc_now": 32, "soc_target": 80}
    )
    assert json.loads(out)["battery_energy_kwh"] == pytest.approx(28.8)


def test_tool_boundary_validates_llm_extraction():
    """Schema-first: LLM trích soc_target < soc_now → bị chặn tại ranh giới tool."""
    with pytest.raises(ValueError, match="soc_target"):
        TOOL_REGISTRY["propose_charging_plan"].invoke(
            {"request": REQUEST | {"soc_now": 90}}, {"configurable": {"resident_id": "res-1"}}
        )


def test_resident_identity_never_comes_from_llm():
    """ADR-006: không có resident_id phía server (config) → tool fail tường minh, không đoán danh tính."""
    with pytest.raises(DomainError, match="resident_id"):
        TOOL_REGISTRY["get_queue_status"].invoke({})


def test_tool_with_identity_reaches_the_real_service(clean_db):
    """Có resident_id từ config → tới charging_service thật (T2.2): cư dân chưa đặt lịch → không ở hàng đợi."""
    out = TOOL_REGISTRY["get_queue_status"].invoke({}, {"configurable": {"resident_id": "res-1"}})
    assert "position" in str(out) or "queue_length" in str(out)


def test_confirm_booking_is_risky():
    assert "confirm_booking" in RISKY_TOOL_NAMES


async def test_confirm_booking_interrupts_for_resident_confirmation():
    """AC1/S3: chốt lịch qua chat phải DỪNG graph chờ cư dân bấm "Xác nhận"."""
    ChargeRequest.model_validate(REQUEST)  # payload mẫu phải hợp lệ
    reasoner = ScriptedReasoner(
        [
            AgentDecision(
                thought="chốt lịch", action="tool", tool_name="confirm_booking", tool_args={"request": REQUEST}
            ),
        ]
    )
    graph = make_test_graph(reasoner)
    result = await graph.ainvoke(
        {"query": "chốt giúp mình lịch này"}, config={"configurable": {"thread_id": "confirm-booking"}}
    )
    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert payload["tool"] == "confirm_booking"
