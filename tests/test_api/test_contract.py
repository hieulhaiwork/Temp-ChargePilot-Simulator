"""Hợp đồng API cho frontend (TV4): đường dẫn đã mở, phân quyền, 501 cho phần chưa làm."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.main import app
from src.models.control import Role

PLANNED_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/vehicles",
    "/api/v1/energy/estimate",
    "/api/v1/station/config",
    "/api/v1/resident/quote",
    "/api/v1/resident/bookings",
    "/api/v1/resident/queue",
    "/api/v1/resident/approvals/{approval_id}",
    "/api/v1/operator/station",
    "/api/v1/operator/schedule",
    "/api/v1/operator/approvals",
    "/api/v1/operator/commands/blocked",
    "/api/v1/operator/decision-log",
    "/api/v1/simulation/scenarios",
    "/api/v1/simulation/runs",
    "/api/v1/simulation/benchmark",
    # Bổ sung ở Pha B (docs/plan/10-backend.md §3)
    "/api/v1/auth/me",
    "/api/v1/tariff",
    "/api/v1/chat",
    "/api/v1/chat/resume",
    "/api/v1/resident/bookings/current",
    "/api/v1/resident/bookings/{booking_id}",
    "/api/v1/resident/session",
    "/api/v1/resident/explanation",
    "/api/v1/resident/notifications",
    "/api/v1/resident/notifications/{notification_id}/read",
    "/api/v1/resident/profile",
    "/api/v1/operator/load",
    "/api/v1/operator/connectors/{connector_id}",
    "/api/v1/operator/events",
    "/api/v1/operator/bookings",
    "/api/v1/operator/schedule/replan",
    "/api/v1/operator/queue/{booking_id}/assign",
    "/api/v1/operator/approvals/{approval_id}",
    "/api/v1/simulation/incidents",
    "/health",
    "/ready",
}


def test_openapi_exposes_planned_contract():
    paths = set(app.openapi()["paths"])
    assert PLANNED_PATHS <= paths, f"Thiếu: {sorted(PLANNED_PATHS - paths)}"


async def test_vehicle_catalog_is_public(client):
    response = await client.get("/api/v1/vehicles")
    assert response.status_code == 200
    assert "DEMO-60" in {v["vehicle_model"] for v in response.json()}


async def test_energy_estimate_uses_fr3_formula(client):
    body = {"vehicle_model": "DEMO-60", "soc_now": 32, "soc_target": 80}
    data = (await client.post("/api/v1/energy/estimate", json=body)).json()
    assert data["battery_energy_kwh"] == pytest.approx(28.8)
    assert data["grid_energy_kwh"] == pytest.approx(28.8 / data["efficiency"])


async def test_energy_estimate_rejects_bad_input(client):
    unknown = await client.post("/api/v1/energy/estimate", json={"vehicle_model": "X", "soc_now": 1, "soc_target": 2})
    reversed_soc = await client.post(
        "/api/v1/energy/estimate", json={"vehicle_model": "DEMO-60", "soc_now": 80, "soc_target": 20}
    )
    assert unknown.status_code == 404
    assert reversed_soc.status_code == 422


async def test_station_config_endpoint(client):
    data = (await client.get("/api/v1/station/config")).json()
    # Fixture mvp1 (ADR-010, T1.10): thay 8 × 7 kW / 35 kW của PRD v0.2.
    assert len(data["connectors"]) == 4 and data["power_limit_kw"] == 106
    assert data["grid_input_limit_kw"] == 106 and data["zone_budgets_kw"] == {"AC": 22.0, "DC": 78.0}


async def test_resident_endpoint_requires_token(client):
    assert (await client.get("/api/v1/resident/queue")).status_code == 401


async def test_operator_endpoint_rejects_resident(client, as_role):
    as_role(Role.RESIDENT)
    assert (await client.get("/api/v1/operator/station")).status_code == 403


async def test_unimplemented_logic_returns_501_with_task_id(client, as_role, monkeypatch):
    """ADR-004: stub `[Txx]` còn lại (vd F6 hoãn) vẫn phải ra 501 kèm task — giả lập bằng một service stub."""
    from src.services import charging_service

    def stub(resident_id):
        raise NotImplementedError("[T2.3] chưa làm")

    monkeypatch.setattr(charging_service, "queue_status", stub)
    as_role(Role.RESIDENT)
    response = await client.get("/api/v1/resident/queue")
    assert response.status_code == 501
    assert response.json()["detail"].startswith("[T")


async def test_scenarios_listed_for_operator(client, as_role):
    as_role(Role.OPERATOR)
    response = await client.get("/api/v1/simulation/scenarios")
    assert response.status_code == 200
    assert {"peak_evening", "power_drop"} <= {s["scenario_id"] for s in response.json()}


async def test_simulation_run_unknown_scenario_is_404(client, as_role):
    as_role(Role.OPERATOR)
    response = await client.post("/api/v1/simulation/runs", json={"scenario_id": "khong_co", "strategy": "B"})
    assert response.status_code == 404


def test_websocket_without_auth_message_is_closed_4401():
    """ADR-006: bản tin đầu phải là {"type": "auth", "token": …}; không có → đóng 4401."""
    with TestClient(app) as tc, pytest.raises(WebSocketDisconnect) as closed:
        with tc.websocket_connect("/api/v1/ws/operator") as ws:
            ws.send_text('{"type": "hello"}')
            ws.receive_text()
    assert closed.value.code == 4401
