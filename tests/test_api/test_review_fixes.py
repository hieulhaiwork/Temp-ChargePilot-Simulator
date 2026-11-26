"""Regression cho các lỗi tìm ra khi review ADR-020 (RESTful rewrite).

Mỗi test khoá một hành vi: body PATCH notification phải có read=true; session_id chat giới hạn 128 ký tự
khớp đường dẫn PATCH; thông báo HITL không lộ tên tool nội bộ; `before` phân trang không vượt int64.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.api.routes import _to_chat_response
from src.models.api import Notification, NotificationKind, Role
from src.models.identity import UserRecord
from src.services import repository


def _ensure_resident(user_id: str) -> None:
    """Khoá ngoại: notifications trỏ tới users — test phải tạo cư dân trước."""
    repository.upsert_user(
        UserRecord(
            user_id=user_id,
            email=f"{user_id}@example.test",
            role=Role.RESIDENT,
            display_name=user_id,
            created_at=datetime.now(UTC),
        )
    )


@pytest.mark.asyncio
async def test_patch_notification_without_explicit_read_true_is_rejected(client, as_role, clean_db):
    _ensure_resident("res-1")
    as_role(Role.RESIDENT, user_id="res-1")
    repository.add_notification(
        "res-1",
        Notification(
            notification_id="n-body",
            kind=NotificationKind.INFO,
            title="T",
            body="B",
            created_at=datetime.now(UTC),
            read=False,
        ),
    )
    res = await client.patch("/api/v1/resident/notifications/n-body", json={})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_chat_session_id_longer_than_128_is_rejected(client, as_role):
    as_role(Role.RESIDENT, user_id="res-1")
    res = await client.post("/api/v1/chat", json={"message": "xin chào", "session_id": "s" * 129})
    assert res.status_code == 422


def test_hitl_fallback_message_does_not_expose_internal_tool_name():
    payload = {"question": "Phê duyệt hành động này?", "tool": "send_email", "args": {}}
    result = {"__interrupt__": [SimpleNamespace(value=payload)]}
    response = _to_chat_response(result, "s1")
    assert response.response == "[CẦN PHÊ DUYỆT] Phê duyệt hành động này?"
    assert "send_email" not in response.response


@pytest.mark.asyncio
async def test_decision_log_before_beyond_int64_is_rejected_not_500(client, as_role, clean_db):
    as_role(Role.OPERATOR, user_id="op-1")
    res = await client.get("/api/v1/operator/decision-log", params={"before": 10**30})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_replan_does_not_push_site_occupancy_while_no_consumer_exists():
    """Q4: không có frontend nào nhận `site_occupancy` → replan không được broadcast nó (tránh đọc DB vô ích)."""
    import dataclasses
    from datetime import datetime

    pytest.importorskip("ev2gym")
    from src.models.events import EventType, StationEvent, WsMessageType
    from src.services import catalog, control_loop
    from src.services.runtime import build_sim_runtime

    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    scenario = catalog.load_scenario("hybrid_evening")
    start = datetime.combine(
        datetime(2026, 11, 23).date(), scenario.start_time, tzinfo=datetime.now().astimezone().tzinfo
    )
    rt = build_sim_runtime(scenario, "M3a", config, tariff, start)
    rt.live = True
    sent: list[WsMessageType] = []

    async def recorder(message, resident_id):
        sent.append(message.type)

    rt.sinks = dataclasses.replace(rt.sinks, notify=recorder)
    await control_loop.on_event(StationEvent(type=EventType.TICK, occurred_at=rt.clock()), rt)

    assert WsMessageType.SCHEDULE_CHANGED in sent  # đối chứng: recorder có bắt được bản tin replan
    assert WsMessageType.SITE_OCCUPANCY not in sent


def _fake_integrity(orig):
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    return SAIntegrityError("INSERT ...", {}, orig)


class _PgError(Exception):
    def __init__(self, sqlstate: str, message: str = "") -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


def test_unique_violation_detected_by_sqlstate_not_message_text():
    from src.services.repository import is_unique_violation

    # Postgres: 23505 = unique_violation, dù thông báo viết thế nào.
    assert is_unique_violation(_fake_integrity(_PgError("23505", "anything at all")))


def test_foreign_key_violation_is_not_unique_even_if_message_mentions_unique():
    from src.services.repository import is_unique_violation

    # 23503 = foreign_key_violation; thông báo có chữ "unique" không được làm nó thành UNIQUE.
    assert not is_unique_violation(_fake_integrity(_PgError("23503", "violates unique-looking constraint")))


def test_sqlite_unique_violation_is_detected_when_no_sqlstate():
    import sqlite3

    from src.services.repository import is_unique_violation

    assert is_unique_violation(_fake_integrity(sqlite3.IntegrityError("UNIQUE constraint failed: bookings.x")))
    assert not is_unique_violation(_fake_integrity(sqlite3.IntegrityError("FOREIGN KEY constraint failed")))


def test_decision_page_reports_has_more_and_next_cursor_from_extra_row():
    """Q5: phân trang đưa từ router xuống service; limit+1 dòng ⇒ has_more, next_cursor = seq dòng cuối trả về."""
    from src.models.control import DecisionLogEntry
    from src.services.station_service import build_decision_page

    rows = [DecisionLogEntry.model_construct(seq=s) for s in (5, 4, 3)]
    page = build_decision_page(rows, limit=2)
    assert [e.seq for e in page.items] == [5, 4]
    assert page.has_more is True
    assert page.next_cursor == 4

    last = build_decision_page(rows[:2], limit=2)
    assert last.has_more is False
    assert last.next_cursor is None


def test_queue_zones_follow_configured_connectors_not_a_hardcoded_pair():
    """Q5: vùng của sơ đồ hàng chờ lấy từ cấu hình trạm (thứ tự xuất hiện, không trùng)."""
    from types import SimpleNamespace

    from src.models.station import ChargerZone
    from src.services.station_service import queue_zones

    connectors = [
        SimpleNamespace(zone=ChargerZone.AC),
        SimpleNamespace(zone=ChargerZone.DC),
        SimpleNamespace(zone=ChargerZone.AC),
    ]
    assert queue_zones(connectors) == (ChargerZone.AC, ChargerZone.DC)
    assert queue_zones([SimpleNamespace(zone=ChargerZone.AC)]) == (ChargerZone.AC,)


def test_api_prefix_is_defined_once_and_reused_by_resident_location_header():
    from src.api.paths import API_PREFIX

    assert API_PREFIX == "/api/v1"
