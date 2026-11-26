"""Luồng đầu–cuối theo tiêu chí nghiệm thu của PRD §9 (sequence diagram: docs/plan/10-backend.md §6).

Chạy trên runtime live THẬT (HybridStation + Planning Core M3a + Guard + repository trên DB test). Đồng hồ trạm được
cố định bằng fixture `station_clock` để kết quả không phụ thuộc giờ chạy test (giá điện theo giờ).
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.config import get_settings
from src.guard import dispatcher
from src.models.charging import ConsentScope
from src.models.control import ApprovalStatus, Command, CommandSource, CommandType, Role
from src.models.events import WsMessage, WsMessageType
from src.models.identity import UserRecord
from src.services import auth, control_loop, realtime, repository, runtime

VN = timezone(timedelta(hours=7))
T0 = datetime(2026, 11, 23, 18, 0, tzinfo=VN)


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def advance(self, **kw) -> None:
        self.at += timedelta(**kw)


@pytest.fixture
def station_clock(monkeypatch, clean_db) -> Clock:
    clock = Clock(T0)
    monkeypatch.setattr(runtime, "_live_clock", lambda config: clock)
    runtime.reset_runtime()
    return clock


@pytest.fixture
def resident(as_role):
    """Tạo cư dân thật trong DB (booking có khoá ngoại tới users) và đăng nhập bằng override."""

    def make(user_id: str = "res-a", consent: ConsentScope | None = None):
        repository.upsert_user(
            UserRecord(
                user_id=user_id,
                email=f"{user_id}@example.invalid",
                role=Role.RESIDENT,
                display_name=user_id,
                vehicle_model="VF8_NEW_2026",
                consent=consent or ConsentScope(),
                created_at=T0,
            )
        )
        return as_role(Role.RESIDENT, user_id=user_id)

    return make


def _ac_request(hours: float = 12, soc_now: float = 30, soc_target: float = 80, **kw) -> dict:
    return {
        "vehicle_model": "VF8_NEW_2026",
        "soc_now": soc_now,
        "soc_target": soc_target,
        "deadline": (T0 + timedelta(hours=hours)).isoformat(),
        "mode": "walk_in",
        "zone": "AC",
    } | kw


def _dc_request(hours: float = 2, soc_now: float = 20) -> dict:
    return {
        "vehicle_model": "VF8_NEW_2026",
        "soc_now": soc_now,
        "soc_target": 80,
        "deadline": (T0 + timedelta(hours=hours)).isoformat(),
        "mode": "walk_in",
        "zone": "DC",
    }


# ---- NFR khả dụng, AC1 (FR3), Q6, idempotency ----------------------------------------------


async def test_form_booking_works_without_llm(client, station_clock, resident):
    """NFR. Đặt lịch bằng form (quote → bookings) không cần LLM; kWh đúng công thức FR3; xe được cắm ngay."""
    resident("res-a")
    quote = await client.post("/api/v1/resident/quotes", json=_ac_request())
    assert quote.status_code == 200, quote.text
    proposal = quote.json()
    assert proposal["feasible"] is True
    assert proposal["energy"]["battery_energy_kwh"] == pytest.approx(60.13 * 0.5)
    assert proposal["connector_id"].startswith("AC-")
    created = await client.post("/api/v1/resident/bookings", json=_ac_request())
    assert created.status_code == 201, created.text
    booking = created.json()
    assert created.headers["location"] == f"/api/v1/resident/bookings/{booking['booking_id']}"
    current = (await client.get("/api/v1/resident/bookings/current")).json()
    assert current["booking_id"] == booking["booking_id"]
    assert current["status"] == "charging"  # control loop đã gán cổng ngay trong request (ADR-007)
    assert current["connector_id"] == proposal["connector_id"]


async def test_second_active_booking_is_conflict(client, station_clock, resident):
    resident("res-a")
    assert (await client.post("/api/v1/resident/bookings", json=_ac_request())).status_code == 201
    again = await client.post("/api/v1/resident/bookings", json=_ac_request(hours=11))
    assert again.status_code == 409
    assert again.json()["code"] == "booking_conflict"


async def test_double_confirm_creates_one_booking(client, station_clock, resident):
    resident("res-a")
    headers = {"Idempotency-Key": "key-123456"}
    first = await client.post("/api/v1/resident/bookings", json=_ac_request(), headers=headers)
    second = await client.post("/api/v1/resident/bookings", json=_ac_request(), headers=headers)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["booking_id"] == second.json()["booking_id"]
    other = await client.post("/api/v1/resident/bookings", json=_ac_request(hours=10), headers=headers)
    assert other.status_code == 409
    assert other.json()["code"] == "idempotency_mismatch"


async def test_infeasible_quote_has_alternatives(client, station_clock, resident):
    """FR4. 54 kWh trong 1 giờ ở cổng AC 11 kW là bất khả thi → feasible=False, có phương án thay thế."""
    resident("res-a")
    proposal = (
        await client.post("/api/v1/resident/quotes", json=_ac_request(hours=1, soc_now=10, soc_target=100))
    ).json()
    assert proposal["feasible"] is False
    kinds = {a["kind"] for a in proposal["alternatives"]}
    assert "other_time" in kinds and "lower_target" in kinds
    assert any("Thiếu" in r for r in proposal["reasons"])
    # Quote không giữ chỗ (FR4 what-if).
    assert repository.list_bookings() == []


# ---- AC2: hàng đợi walk-in -----------------------------------------------------------------


async def test_walk_in_when_full_gets_queue_position(client, station_clock, resident):
    """AC2. 2 cổng AC đã có xe (giữ tới giờ rời — F14) → xe AC thứ ba vào hàng đợi, có vị trí + ETA."""
    for uid, hours in (("res-a", 3), ("res-b", 4)):
        resident(uid)
        r = await client.post("/api/v1/resident/bookings", json=_ac_request(hours=hours, soc_now=70, soc_target=80))
        assert r.status_code == 201, r.text
    resident("res-c")
    r = await client.post("/api/v1/resident/bookings", json=_ac_request(hours=10, soc_now=70, soc_target=80))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "queued"
    queue = (await client.get("/api/v1/resident/queue")).json()
    assert queue["position"] == 1
    # Có cổng sau ~3 h (21:00, xe res-a rời); LP dời lúc BẮT ĐẦU SẠC sang thấp điểm 22:00 vì vẫn kịp hạn.
    assert 180 <= queue["estimated_wait_minutes"] <= 240
    assert queue["estimated_start"] is not None


# ---- FR8: đổi yêu cầu, huỷ -----------------------------------------------------------------


async def test_change_booking_triggers_replan(client, station_clock, resident):
    resident("res-a")
    booking = (await client.post("/api/v1/resident/bookings", json=_ac_request())).json()
    version_before = runtime.get_runtime().plan.version
    changed = await client.patch(f"/api/v1/resident/bookings/{booking['booking_id']}", json={"soc_target": 60})
    assert changed.status_code == 200, changed.text
    assert changed.json()["energy"]["battery_energy_kwh"] == pytest.approx(60.13 * 0.3)
    assert runtime.get_runtime().plan.version > version_before
    # Không còn khả thi → 409 kèm phương án, booking cũ giữ nguyên.
    too_soon = await client.patch(
        f"/api/v1/resident/bookings/{booking['booking_id']}",
        json={"soc_target": 100, "deadline": (T0 + timedelta(hours=1)).isoformat()},
    )
    assert too_soon.status_code == 409
    assert "Lấy xe lúc" in too_soon.json()["detail"]
    assert repository.get_booking(booking["booking_id"]).request.soc_target == 60


async def test_cancel_frees_connector(client, station_clock, resident):
    resident("res-a")
    booking = (await client.post("/api/v1/resident/bookings", json=_ac_request())).json()
    cancelled = await client.delete(f"/api/v1/resident/bookings/{booking['booking_id']}")
    assert cancelled.status_code == 204
    assert cancelled.content == b""
    assert repository.get_booking(booking["booking_id"]).status.value == "cancelled"
    state = runtime.get_runtime().simulator.state()
    assert all(c.booking_id is None for c in state.connectors)
    assert (await client.get("/api/v1/resident/bookings/current")).json() is None


# ---- AC4: phê duyệt điều chỉnh vượt phạm vi đồng ý -----------------------------------------


async def _pending_power_cut(client, resident) -> tuple[str, str]:
    """Xe DC của cư dân KHÔNG cho giảm công suất đang sạc; một lệnh tối ưu hạ công suất → phải chờ cư dân."""
    resident("res-a", consent=ConsentScope(allow_power_reduction=False))
    booking = (await client.post("/api/v1/resident/bookings", json=_dc_request())).json()
    rt = runtime.get_runtime()
    state = rt.simulator.state()
    conn = next(c for c in state.connectors if c.booking_id == booking["booking_id"])
    assert conn.power_kw > 30
    cut = Command(
        type=CommandType.SET_POWER,
        connector_id=conn.connector_id,
        power_kw=30,
        booking_id=booking["booking_id"],
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=state.schedule_version,
        based_on_state_at=state.timestamp,
        created_at=state.timestamp,
        reason="Chia công suất cho xe mới",
    )
    entries = await dispatcher.submit([cut], control_loop.build_guard_context(rt, None), rt.simulator, rt.sinks)
    assert entries[0].approval_id and entries[0].executed is False
    return entries[0].approval_id, conn.connector_id


async def test_adjustment_outside_consent_waits_for_resident(client, station_clock, resident):
    approval_id, connector_id = await _pending_power_cut(client, resident)
    rt = runtime.get_runtime()
    # Chưa ai trả lời → simulator KHÔNG nhận lệnh; có Approval PENDING + Notification cho cư dân.
    assert next(c for c in rt.simulator.state().connectors if c.connector_id == connector_id).power_kw > 30
    assert repository.get_approval(approval_id).status == ApprovalStatus.PENDING
    notes = (await client.get("/api/v1/resident/notifications")).json()
    assert notes[0]["approval_id"] == approval_id
    detail = (await client.get(f"/api/v1/resident/approvals/{approval_id}")).json()
    assert detail["requested_from"] == "res-a"
    decided = await client.patch(f"/api/v1/resident/approvals/{approval_id}", json={"decision": "approve"})
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"
    log = [d for d in repository.list_decisions(limit=50) if d.approval_id == approval_id]
    executed = [d for d in log if d.executed]
    assert executed and executed[0].approved_by == "res-a" and executed[0].verdict.passed
    again = await client.patch(f"/api/v1/resident/approvals/{approval_id}", json={"decision": "reject"})
    assert again.status_code == 409


async def test_other_resident_cannot_see_or_decide(client, station_clock, resident):
    approval_id, _ = await _pending_power_cut(client, resident)
    resident("res-intruder")
    assert (await client.get(f"/api/v1/resident/approvals/{approval_id}")).status_code == 404
    assert (
        await client.patch(f"/api/v1/resident/approvals/{approval_id}", json={"decision": "approve"})
    ).status_code == 404


async def test_expired_approval_is_never_applied(client, station_clock, resident):
    """AC4 (PRD thắng wireframe "tự áp dụng sau 04:12"): quá hạn → EXPIRED, không tới simulator."""
    approval_id, connector_id = await _pending_power_cut(client, resident)
    rt = runtime.get_runtime()
    station_clock.advance(minutes=rt.config.guard.approval_ttl_minutes + 1)
    expired = control_loop.expire_overdue_approvals(rt)
    assert [a.approval_id for a in expired] == [approval_id]
    assert repository.get_approval(approval_id).status == ApprovalStatus.EXPIRED
    log = [d for d in repository.list_decisions(limit=50) if d.approval_id == approval_id]
    assert not any(d.executed for d in log)
    late = await client.patch(f"/api/v1/resident/approvals/{approval_id}", json={"decision": "approve"})
    assert late.status_code == 409


# ---- AC5: bảo vệ khẩn cấp ------------------------------------------------------------------


async def test_power_drop_is_curtailed_before_replan(client, station_clock, resident, as_role):
    for uid in ("res-a", "res-b"):
        resident(uid)
        assert (await client.post("/api/v1/resident/bookings", json=_dc_request())).status_code == 201
    rt = runtime.get_runtime()
    assert rt.simulator.state().total_power_kw > 70
    as_role(Role.OPERATOR, user_id="op-1")
    r = await client.post("/api/v1/simulation/incidents", json={"type": "power_limit_change", "new_power_limit_kw": 40})
    assert r.status_code == 202
    state = rt.simulator.state()
    assert state.available_power_kw == 40
    assert state.total_power_kw / rt.config.power_conversion_efficiency <= 40 + 1e-6
    emergency = [d for d in repository.list_decisions(limit=50) if d.command.source == CommandSource.EMERGENCY]
    assert emergency and all(d.executed for d in emergency)
    resident("res-a")
    kinds = {n["kind"] for n in (await client.get("/api/v1/resident/notifications")).json()}
    assert "emergency_curtailment" in kinds
    as_role(Role.OPERATOR, user_id="op-1")
    overview = (await client.get("/api/v1/operator/station")).json()
    assert any("Nguồn đang giảm" in a for a in overview["alerts"])


# ---- AC6: lệnh sai bị chặn -----------------------------------------------------------------


async def test_blocked_commands_show_up_for_operator(client, station_clock, as_role):
    rt = runtime.get_runtime()
    state = rt.simulator.state()

    def cmd(**kw) -> Command:
        base = {
            "type": CommandType.SET_POWER,
            "connector_id": "AC-01-1",
            "power_kw": 5,
            "source": CommandSource.OPTIMIZER,
            "issued_by": "optimizer",
            "based_on_schedule_version": state.schedule_version,
            "based_on_state_at": state.timestamp,
            "created_at": state.timestamp,
        }
        return Command(**(base | kw))

    bad = [
        cmd(power_kw=50),  # vượt cổng
        cmd(connector_id="DC-01-1", power_kw=200),  # vượt cổng + lưới
        cmd(based_on_schedule_version=state.schedule_version + 9),  # lịch cũ
        cmd(based_on_state_at=state.timestamp - timedelta(minutes=5)),  # dữ liệu cũ
    ]
    entries = await dispatcher.submit(bad, control_loop.build_guard_context(rt, None), rt.simulator, rt.sinks)
    resident_cmd = cmd(connector_id="AC-02-1")
    entries += await dispatcher.submit(
        [resident_cmd], control_loop.build_guard_context(rt, Role.RESIDENT), rt.simulator, rt.sinks
    )
    assert not any(e.executed for e in entries)
    assert rt.simulator.state().total_power_kw == 0
    as_role(Role.OPERATOR, user_id="op-1")
    blocked_page = (await client.get("/api/v1/operator/commands/blocked")).json()
    blocked = blocked_page["items"]
    assert len(blocked) == 5
    assert blocked_page["has_more"] is False and blocked_page["next_cursor"] is None
    rules = {v["rule"] for b in blocked for v in b["verdict"]["violations"]}
    assert {"connector_power_limit", "schedule_version", "stale_state", "permission"} <= rules


# ---- S5/S6: vận hành -----------------------------------------------------------------------


async def test_operator_views_and_manual_assign(client, station_clock, resident, as_role):
    for uid, hours in (("res-a", 3), ("res-b", 4), ("res-c", 10)):
        resident(uid)
        await client.post("/api/v1/resident/bookings", json=_ac_request(hours=hours, soc_now=70, soc_target=80))
    as_role(Role.OPERATOR, user_id="op-1")
    overview = (await client.get("/api/v1/operator/station")).json()
    # 18:00 là giờ cao điểm: LP dời việc sạc sang 22:00 (vẫn kịp hạn) nên xe đã cắm nhưng chưa cấp điện.
    assert overview["queue_length"] == 1
    assert sum(1 for c in overview["state"]["connectors"] if c["booking_id"]) == 2
    plan = (await client.get("/api/v1/operator/schedule")).json()
    assert plan["queue"] and len(plan["sessions"]) == 3
    queued = (await client.get("/api/v1/operator/bookings", params={"status": "queued"})).json()
    assert len(queued) == 1
    detail = (await client.get("/api/v1/operator/connectors/AC-01-1")).json()
    assert detail["booking"] is not None and detail["recent_decisions"]
    events = (await client.get("/api/v1/operator/events")).json()
    assert any(e["type"] == "booking_created" for e in events)
    assert (await client.get("/api/v1/operator/load", params={"hours": 1})).json()
    # Xếp tay vào cổng ĐANG BẬN → Guard chặn; vào cổng DC (sai vùng) → Guard chặn.
    busy = await client.post(
        f"/api/v1/operator/bookings/{queued[0]['booking_id']}/assignments", json={"connector_id": "AC-01-1"}
    )
    assert busy.json()["executed"] is False
    wrong_zone = await client.post(
        f"/api/v1/operator/bookings/{queued[0]['booking_id']}/assignments", json={"connector_id": "DC-01-1"}
    )
    assert wrong_zone.json()["executed"] is False
    replanned = await client.post("/api/v1/operator/schedule/replans")
    assert replanned.status_code == 200 and replanned.json()["version"] > plan["version"]


# ---- FR16: WebSocket -----------------------------------------------------------------------


def _token(user_id: str, role: Role) -> str:
    repository.upsert_user(
        UserRecord(
            user_id=user_id,
            email=f"{user_id}@example.invalid",
            password_hash=auth.hash_password("pw-123456"),
            role=role,
            display_name=user_id,
            created_at=T0,
        )
    )
    return auth.authenticate(f"{user_id}@example.invalid", "pw-123456").access_token


def test_ws_requires_auth_message(clean_db):
    """ADR-006: sai vai trò → 4403; token đúng → nhận ngay station_snapshot; ping → pong."""
    from src.main import app

    resident_token = _token("res-ws", Role.RESIDENT)
    operator_token = _token("op-ws", Role.OPERATOR)
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as closed:
            with tc.websocket_connect("/api/v1/ws/operator") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": resident_token}))
                ws.receive_text()
        assert closed.value.code == 4403
        with tc.websocket_connect("/api/v1/ws/operator") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": operator_token}))
            first = json.loads(ws.receive_text())
            assert first["type"] == "station_snapshot"
            ws.send_text(json.dumps({"type": "ping"}))
            assert json.loads(ws.receive_text())["type"] == "pong"
        with tc.websocket_connect("/api/v1/ws/resident") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": resident_token}))
            assert json.loads(ws.receive_text())["type"] == "schedule_changed"


async def test_resident_stream_never_leaks_other_residents():
    """Bản tin gửi cho cư dân A chỉ tới A (và vận hành), không tới cư dân B."""
    received: dict[str, list] = {"A": [], "B": [], "op": []}

    def sink(name):
        async def send(msg):
            received[name].append(msg.type)

        return send

    ids = [
        realtime.register(sink("A"), Role.RESIDENT, "res-A"),
        realtime.register(sink("B"), Role.RESIDENT, "res-B"),
        realtime.register(sink("op"), Role.OPERATOR, "op-1"),
    ]
    try:
        msg = WsMessage(type=WsMessageType.SCHEDULE_CHANGED, payload={}, sent_at=T0)
        await realtime.broadcast(msg, user_id="res-A")
        await realtime.broadcast(msg, role=Role.OPERATOR)
        assert received == {"A": ["schedule_changed"], "B": [], "op": ["schedule_changed", "schedule_changed"]}
    finally:
        for cid in ids:
            realtime.unregister(cid)


# ---- AC1 / FR2: chat với Agent (LLM giả, dịch vụ THẬT) -------------------------------------


@pytest.fixture
def mock_llm_real_services(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("AGENT_DEMO_SERVICES", "false")
    # LLM giả hiểu "7h sáng mai" theo đồng hồ của nó — khoá về cùng mốc với đồng hồ trạm.
    monkeypatch.setattr("src.llm_chat.mock_llm._now_local", lambda state: T0)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_chat_booking_kwh_matches_fr3(client, station_clock, resident, mock_llm_real_services):
    """AC1 + FR2: hỏi lại chỗ thiếu → proposal (kWh do code) → HITL xác nhận → booking thật trong DB."""
    resident("res-chat")
    sid = "chat-ac1"
    t1 = (
        await client.post("/api/v1/chat", json={"message": "Cần 80% pin trước 7h sáng mai", "session_id": sid})
    ).json()
    assert t1["status"] == "answer" and t1["analysis"] == ""
    t2 = (await client.post("/api/v1/chat", json={"message": "Mình đang ở bãi, pin còn 32%", "session_id": sid})).json()
    assert t2["analysis"] == "propose_charging_plan"
    t3 = (await client.post("/api/v1/chat", json={"message": "Chốt lịch này nhé", "session_id": sid})).json()
    assert t3["status"] == "needs_confirmation"
    assert t3["proposal"]["feasible"] is True
    kwh = t3["proposal"]["energy"]["battery_energy_kwh"]
    t4 = (await client.patch(f"/api/v1/chat/sessions/{sid}", json={"resume": "approve"})).json()
    assert t4["status"] == "answer" and t4["analysis"] == "confirm_booking"
    current = (await client.get("/api/v1/resident/bookings/current")).json()
    assert current is not None
    assert current["energy"]["battery_energy_kwh"] == pytest.approx(kwh)
    explanation = (await client.get("/api/v1/resident/explanation")).json()
    assert any(current["booking_id"] in line for line in explanation)


# ---- Nghiệm thu E2E Phase 4 (ADR-019): booking → planning → Guard/HITL → vật lý → trace → KPI --------------------


async def test_e2e_unified_core_acceptance(client, station_clock, resident, as_role):
    """Một luồng xuyên suốt trên runtime thật (HybridStation + Planning Core M3a + Guard + DB test):

    quote có điều kiện → booking → control loop lập lịch → lệnh qua dispatcher (Guard) → vật lý kernel từng phút →
    sự kiện CHARGE_COMPLETED → mọi lệnh truy được về DecisionTrace theo correlation ID → không vi phạm vật lý →
    `/simulation/benchmark` chỉ còn policy của registry, có nguồn / version.
    """
    from src.models.events import EventType

    resident("res-a")
    request = _dc_request(hours=3, soc_now=60)
    quote = (await client.post("/api/v1/resident/quotes", json=request)).json()
    assert quote["feasible"] is True
    assert quote["certainty"] in ("estimate", "conditional") and quote["assumptions"], "quote không được là SLA"
    assert (await client.post("/api/v1/resident/bookings", json=request)).status_code == 201

    rt = runtime.get_runtime()
    seen: list = []
    for _ in range(240):
        station_clock.advance(minutes=1)
        async with rt.lock:
            events = rt.sync_clock()
        seen += events
        await control_loop.on_minute(rt, events)
        if any(e.type == EventType.CHARGE_COMPLETED for e in seen):
            break
    assert any(e.type == EventType.CHARGE_COMPLETED for e in seen), "kernel / backend phải phát CHARGE_COMPLETED"
    assert getattr(rt.simulator, "applied_constraint_violation_count", 0) == 0

    decisions = repository.list_decisions(limit=500)
    executed = [d for d in decisions if d.executed]
    assert executed, "lệnh phải tới trạm qua dispatcher"
    for entry in executed:
        cid = entry.command.correlation_id
        assert cid, f"lệnh {entry.command.command_id} thiếu correlation_id"
        trace = repository.get_decision_trace(cid)
        if entry.command.source != CommandSource.EMERGENCY:
            assert trace is not None and trace.policy_id == "M3a", cid

    as_role(Role.OPERATOR, user_id="op-1")
    kinds = {e["type"] for e in (await client.get("/api/v1/operator/events?limit=200")).json()}
    assert EventType.CHARGE_COMPLETED.value in kinds
    bench = await client.get("/api/v1/simulation/benchmark")
    assert bench.status_code == 200, bench.text
    report = bench.json()
    assert report["source"], "benchmark phải ghi nguồn + version"
    assert {run["strategy"] for run in report["runs"]} <= {"B0", "M2b", "M3a", "M3b"}
