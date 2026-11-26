"""Kiểm tra các endpoint mở rộng G1–G24 trên nền Unified Core (BE <-> FE contract)."""

from datetime import UTC, datetime, timedelta

import pytest

from src.models.api import Notification, NotificationKind
from src.models.charging import BookingStatus
from src.models.control import (
    Approval,
    ApprovalKind,
    ApprovalStatus,
    Command,
    CommandSource,
    CommandType,
    DecisionLogEntry,
    GuardVerdict,
    Role,
)
from src.models.identity import UserRecord
from src.services import repository
from tests.factories import booking as make_booking


def _ensure_residents(*user_ids: str) -> None:
    """Khoá ngoại: notifications / bookings / approvals trỏ tới users — test phải tạo cư dân trước."""
    for user_id in user_ids:
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
async def test_station_config_includes_layout(client):
    res = await client.get("/api/v1/station/config")
    assert res.status_code == 200
    data = res.json()
    assert data["layout"] is not None
    assert data["layout"]["orientation"] == "landscape"
    bay_ids = [b["bay_id"] for b in data["layout"]["bays"]]
    assert bay_ids == ["B-A1", "B-A2", "B-D1", "B-D2"]


@pytest.mark.asyncio
async def test_resident_site_map_privacy_and_mine(client, as_role):
    as_role(Role.RESIDENT, user_id="res-map-1")
    res = await client.get("/api/v1/resident/site-map")
    assert res.status_code == 200
    body = res.json()
    assert len(body["bays"]) == 4
    for bay in body["bays"]:
        assert bay["public_status"] in ("busy", "idle", "fault")
        assert "vehicle_model" not in bay
        assert "soc_now" not in bay


@pytest.mark.asyncio
async def test_resident_approvals_and_read_all_notifications(client, as_role, clean_db):
    _ensure_residents("res-1", "res-other")
    as_role(Role.RESIDENT, user_id="res-1")
    now = datetime.now(UTC)
    cmd = Command(
        command_id="cmd-res-1",
        type=CommandType.SET_POWER,
        connector_id="AC-01-1",
        power_kw=7.0,
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=1,
        based_on_state_at=now,
        created_at=now,
    )
    verdict = GuardVerdict(command_id="cmd-res-1", passed=True, checked_at=now)
    ap_mine = Approval(
        approval_id="ap-res-1",
        kind=ApprovalKind.RESIDENT_CONSENT,
        status=ApprovalStatus.PENDING,
        command=cmd,
        verdict=verdict,
        requested_from="res-1",
        impact_summary="Giảm công suất 7 kW",
        created_at=now,
    )
    ap_other = ap_mine.model_copy(update={"approval_id": "ap-res-2", "requested_from": "res-other"})
    repository.save_approval(ap_mine)
    repository.save_approval(ap_other)

    res = await client.get("/api/v1/resident/approvals")
    assert res.status_code == 200
    ids = [a["approval_id"] for a in res.json()]
    assert ids == ["ap-res-1"]

    repository.add_notification(
        "res-1",
        Notification(
            notification_id="n1",
            kind=NotificationKind.INFO,
            title="Test 1",
            body="Body 1",
            created_at=now,
            read=False,
        ),
    )
    repository.add_notification(
        "res-1",
        Notification(
            notification_id="n2",
            kind=NotificationKind.INFO,
            title="Test 2",
            body="Body 2",
            created_at=now,
            read=False,
        ),
    )
    res_one = await client.patch("/api/v1/resident/notifications/n1", json={"read": True})
    assert res_one.status_code == 200
    assert res_one.json()["read"] is True
    res_read = await client.patch("/api/v1/resident/notifications", json={"read": True})
    assert res_read.status_code == 200
    assert res_read.json()["updated"] == 1
    assert all(n["read"] is True for n in (await client.get("/api/v1/resident/notifications")).json())


@pytest.mark.asyncio
async def test_operator_bookings_multi_status_and_decision_log_seq(client, as_role, clean_db):
    _ensure_residents("res-bk-q", "res-bk-c", "res-bk-d")
    as_role(Role.OPERATOR)
    now = datetime.now(UTC)
    b_q = make_booking("bk-q", status=BookingStatus.QUEUED, hours=4)
    b_c = make_booking("bk-c", status=BookingStatus.CHARGING, hours=4)
    b_d = make_booking("bk-d", status=BookingStatus.COMPLETED, hours=4)
    repository.save_booking(b_q)
    repository.save_booking(b_c)
    repository.save_booking(b_d)

    res = await client.get("/api/v1/operator/bookings", params=[("status", "queued"), ("status", "charging")])
    assert res.status_code == 200
    returned_ids = {b["booking_id"] for b in res.json()}
    assert returned_ids == {"bk-q", "bk-c"}

    for idx in range(3):
        cmd = Command(
            command_id=f"cmd-seq-{idx}",
            type=CommandType.SET_POWER,
            connector_id="AC-01-1",
            power_kw=7.0,
            source=CommandSource.OPTIMIZER,
            issued_by="optimizer",
            based_on_schedule_version=1,
            based_on_state_at=now,
            created_at=now,
        )
        repository.append_decision(
            DecisionLogEntry(
                entry_id=f"entry-seq-{idx}",
                timestamp=now + timedelta(seconds=idx),
                command=cmd,
                verdict=GuardVerdict(command_id=f"cmd-seq-{idx}", passed=True, checked_at=now),
                executed=True,
            )
        )

    page1 = (await client.get("/api/v1/operator/decision-log", params={"limit": 2})).json()
    assert len(page1["items"]) == 2
    assert page1["has_more"] is True
    assert page1["next_cursor"] == page1["items"][1]["seq"]
    assert page1["items"][0]["seq"] > page1["items"][1]["seq"]

    page2 = (
        await client.get("/api/v1/operator/decision-log", params={"limit": 2, "before": page1["next_cursor"]})
    ).json()
    assert len(page2["items"]) >= 1
    assert page2["items"][0]["seq"] < page1["items"][1]["seq"]


@pytest.mark.asyncio
async def test_chat_resume_without_interrupt_returns_409(client, as_role):
    as_role(Role.RESIDENT)
    res = await client.patch("/api/v1/chat/sessions/nonexistent-session", json={"resume": "approve"})
    assert res.status_code == 409
    assert res.json()["code"] == "no_pending_confirmation"


@pytest.mark.asyncio
async def test_resident_site_map_follows_g24_spec_shape(client, as_role):
    """Spec G24 (docs/plan/21-ui-spec.md): bays[].public_status ∈ busy|idle|fault; queues{AC,DC:{length,my_position}}.
    Web (resident/map/page.tsx) đọc đúng các tên này; backend phải trả đúng để sơ đồ không hiện mọi ô là "idle"."""
    as_role(Role.RESIDENT, user_id="res-map-spec")
    body = (await client.get("/api/v1/resident/site-map")).json()
    for bay in body["bays"]:
        assert bay["public_status"] in {"busy", "idle", "fault"}
        assert "status" not in bay
    assert set(body["queues"]) == {"AC", "DC"}
    for zone in ("AC", "DC"):
        assert set(body["queues"][zone]) == {"length", "my_position"}
