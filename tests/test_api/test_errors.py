"""Quy ước lỗi của API (ADR-008): một envelope cho mọi lỗi, mã ổn định cho frontend."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models.api import ErrorCode
from src.models.control import Role
from src.services import charging_service
from src.services.errors import HTTP_STATUS, DomainError


@pytest.fixture
def stub_queue(monkeypatch):
    """Giả lập một service còn là stub (ADR-004) — mọi endpoint của sprint đã có code thật."""
    from src.services import charging_service

    def stub(resident_id):
        raise NotImplementedError("[T2.2] queue_status")

    monkeypatch.setattr(charging_service, "queue_status", stub)


async def test_not_implemented_envelope_carries_task_id(client, as_role, stub_queue):
    as_role(Role.RESIDENT)
    response = await client.get("/api/v1/resident/queue")
    body = response.json()
    assert response.status_code == 501
    assert body["code"] == "not_implemented"
    assert body["status"] == "not_implemented"  # tương thích ADR-004
    assert body["task_id"] == "T2.2"
    assert body["detail"].startswith("[T2.2]")


async def test_request_id_is_returned_in_header_and_body(client, as_role, stub_queue):
    as_role(Role.RESIDENT)
    response = await client.get("/api/v1/resident/queue", headers={"X-Request-ID": "demo-123"})
    assert response.headers["X-Request-ID"] == "demo-123"
    assert response.json()["request_id"] == "demo-123"


async def test_unsafe_request_id_is_replaced(client):
    response = await client.get("/health", headers={"X-Request-ID": "x" * 200})
    assert response.headers["X-Request-ID"] != "x" * 200
    assert len(response.headers["X-Request-ID"]) == 32


async def test_missing_token_uses_envelope_and_keeps_challenge_header(client):
    response = await client.get("/api/v1/resident/queue")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_wrong_role_is_forbidden_with_code(client, as_role):
    as_role(Role.RESIDENT)
    response = await client.get("/api/v1/operator/station")
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


async def test_domain_error_maps_to_http_status(client, as_role, monkeypatch):
    """Service ném DomainError (không ném HTTPException) → router trả đúng mã + code."""
    as_role(Role.RESIDENT)

    def _conflict(resident_id: str):
        raise DomainError(ErrorCode.BOOKING_CONFLICT, "Bạn đang có một lịch sạc còn hiệu lực")

    monkeypatch.setattr(charging_service, "current_booking", _conflict)
    response = await client.get("/api/v1/resident/bookings/current")
    assert response.status_code == 409
    assert response.json()["code"] == "booking_conflict"


async def test_unexpected_error_does_not_leak_internals(as_role, monkeypatch):
    as_role(Role.RESIDENT)

    def _boom(resident_id: str):
        raise RuntimeError("mật khẩu DB là hunter2")

    monkeypatch.setattr(charging_service, "current_booking", _boom)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as quiet_client:
        response = await quiet_client.get("/api/v1/resident/bookings/current")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "hunter2" not in response.text


def test_every_domain_error_code_has_http_status():
    """Thêm ErrorCode mới mà quên map HTTP thì DomainError.http_status sẽ KeyError lúc chạy thật."""
    missing = set(ErrorCode) - set(HTTP_STATUS) - {ErrorCode.HTTP_ERROR}
    assert not missing, f"Thiếu mã HTTP cho: {sorted(missing)}"


async def test_validation_error_keeps_fastapi_shape(client, as_role):
    """422 giữ dạng mặc định của FastAPI (detail là mảng) — frontend gắn lỗi vào từng ô nhập."""
    as_role(Role.RESIDENT)
    response = await client.post("/api/v1/resident/quotes", json={"vehicle_model": "DEMO-60"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


async def test_ready_reports_config_and_database(client):
    response = await client.get("/ready")
    body = response.json()
    assert response.status_code == 200
    assert body == {"status": "ok", "checks": {"config": "ok", "database": "ok"}}


async def test_chat_requires_resident_token(client):
    assert (await client.post("/api/v1/chat", json={"message": "Chào"})).status_code == 401


async def test_chat_rejects_operator(client, as_role):
    as_role(Role.OPERATOR)
    assert (await client.post("/api/v1/chat", json={"message": "Chào"})).status_code == 403


@pytest.mark.parametrize(
    ("method", "path", "role", "body"),
    [
        ("get", "/api/v1/resident/session", Role.RESIDENT, None),
        ("get", "/api/v1/resident/explanation", Role.RESIDENT, None),
        ("get", "/api/v1/resident/profile", Role.RESIDENT, None),
        ("patch", "/api/v1/resident/bookings/b1", Role.RESIDENT, {"soc_target": 70}),
        ("patch", "/api/v1/resident/approvals/a1", Role.RESIDENT, {"decision": "approve"}),
        ("get", "/api/v1/operator/connectors/AC-01-1", Role.OPERATOR, None),
        ("get", "/api/v1/operator/events", Role.OPERATOR, None),
        ("get", "/api/v1/operator/bookings", Role.OPERATOR, None),
        ("post", "/api/v1/operator/schedule/replans", Role.OPERATOR, None),
        ("patch", "/api/v1/operator/approvals/a1", Role.OPERATOR, {"decision": "reject"}),
        ("post", "/api/v1/simulation/incidents", Role.OPERATOR, {"type": "connector_fault", "connector_id": "A05"}),
    ],
)
async def test_endpoints_are_wired_to_real_services(client, as_role, clean_db, method, path, role, body):
    """Mọi endpoint của Pha B đã nối tới service thật: không còn 501; lỗi nghiệp vụ vẫn theo envelope (ADR-008)."""
    as_role(role)
    response = await client.request(method, path, json=body)
    assert response.status_code not in (405, 500, 501), response.text
    if response.status_code >= 400:
        assert response.json()["code"] in {"not_found", "forbidden", "booking_conflict"}, response.text
