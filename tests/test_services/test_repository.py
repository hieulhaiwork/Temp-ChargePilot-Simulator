"""services/repository.py — cửa duy nhất tới dữ liệu bền vững (ADR-005, T1.6).

Chạy trên SQLite tạm (local) và Postgres thật (job `backend-postgres` của CI đặt TEST_DATABASE_URL).
"""

import inspect
from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.models.api import ErrorCode, Notification, NotificationKind
from src.models.charging import (
    Booking,
    BookingStatus,
    ChargeMode,
    ChargeRequest,
    EnergyEstimate,
    PowerSlot,
    SchedulePlan,
    SessionPlan,
    StrategyName,
)
from src.models.control import (
    Approval,
    ApprovalKind,
    ApprovalStatus,
    Command,
    CommandSource,
    CommandType,
    DecisionLogEntry,
    GuardRule,
    GuardVerdict,
    Violation,
)
from src.models.events import EventType, StationEvent
from src.models.identity import UserRecord
from src.models.station import LoadPoint
from src.services import repository
from src.services.errors import DomainError

ICT = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 22, 19, 0, tzinfo=ICT)


def _user(user_id: str = "res-a", email: str = "a@example.invalid") -> UserRecord:
    return UserRecord(
        user_id=user_id, email=email, password_hash="scrypt$x", role="resident", display_name="A", created_at=NOW
    )


def _booking(booking_id: str = "b1", resident_id: str = "res-a", status=BookingStatus.CONFIRMED) -> Booking:
    req = ChargeRequest(
        vehicle_model="VF8_NEW_2026",
        soc_now=30,
        soc_target=80,
        arrival_time=NOW,
        deadline=NOW + timedelta(hours=12),
        mode=ChargeMode.RESERVATION,
    )
    energy = EnergyEstimate(
        vehicle_model="VF8_NEW_2026",
        soc_now=30,
        soc_target=80,
        battery_energy_kwh=40,
        grid_energy_kwh=44,
        efficiency=0.9,
    )
    return Booking(
        booking_id=booking_id,
        resident_id=resident_id,
        request=req,
        status=status,
        energy=energy,
        max_charge_power_kw=11,
        connector_id="AC-01-1",
        schedule_version=1,
        created_at=NOW,
    )


def _command(booking_id: str | None = "b1") -> Command:
    return Command(
        type=CommandType.SET_POWER,
        connector_id="AC-01-1",
        power_kw=7,
        booking_id=booking_id,
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=1,
        based_on_state_at=NOW,
        created_at=NOW,
    )


def _approval(status=ApprovalStatus.PENDING, expires_at=None) -> Approval:
    cmd = _command()
    return Approval(
        kind=ApprovalKind.RESIDENT_CONSENT,
        status=status,
        command=cmd,
        verdict=GuardVerdict(command_id=cmd.command_id, passed=True, checked_at=NOW),
        requested_from="res-a",
        impact_summary="Vẫn kịp 80% lúc 7:00",
        created_at=NOW,
        expires_at=expires_at,
    )


def _decision(passed: bool) -> DecisionLogEntry:
    cmd = _command()
    violations = [] if passed else [Violation(rule=GuardRule.TOTAL_POWER, detail="vượt 35 kW")]
    verdict = GuardVerdict(command_id=cmd.command_id, passed=passed, violations=violations, checked_at=NOW)
    return DecisionLogEntry(timestamp=NOW, command=cmd, verdict=verdict, executed=passed)


def _notification(nid: str, minutes: int = 0) -> Notification:
    return Notification(
        notification_id=nid,
        kind=NotificationKind.INFO,
        title="t",
        body="b",
        created_at=NOW + timedelta(minutes=minutes),
    )


def test_ping_answers_on_test_database():
    assert repository.ping() is True


def test_ping_reinitializes_after_dispose():
    """Lifespan gọi dispose() lúc tắt; lần gọi sau phải tự mở lại theo settings.database_url."""
    repository.dispose()
    assert repository.ping() is True


def test_decision_log_has_no_update_or_delete_function():
    """FR14: nhật ký quyết định là CHỈ-THÊM — interface không được có đường sửa/xoá."""
    names = [name for name, _ in inspect.getmembers(repository, inspect.isfunction)]
    forbidden = [n for n in names if "decision" in n and n.split("_")[0] in {"update", "delete", "remove", "edit"}]
    assert not forbidden, f"Không được có hàm sửa/xoá decision log: {forbidden}"
    assert "append_decision" in names


def test_user_roundtrip(clean_db):
    repository.upsert_user(_user())
    got = repository.get_user_by_email("  A@Example.INVALID ")
    assert got == _user()
    assert repository.get_user("res-a") == _user()
    assert repository.get_user("missing") is None


def test_upsert_user_is_idempotent_and_keeps_user_id(clean_db):
    repository.upsert_user(_user())
    repository.upsert_user(_user(user_id="res-other").model_copy(update={"display_name": "A2"}))
    got = repository.get_user_by_email("a@example.invalid")
    assert got.user_id == "res-a"
    assert got.display_name == "A2"


def test_booking_roundtrip_keeps_timezone(clean_db):
    repository.upsert_user(_user())
    repository.save_booking(_booking())
    got = repository.get_booking("b1")
    assert got == _booking()
    assert got.request.deadline.utcoffset() == timedelta(hours=7)


def test_one_active_booking_per_resident(clean_db):
    repository.upsert_user(_user())
    repository.save_booking(_booking("b1"))
    with pytest.raises(DomainError) as err:
        repository.save_booking(_booking("b2"))
    assert err.value.code == ErrorCode.BOOKING_CONFLICT
    # Huỷ booking cũ thì đặt được booking mới.
    repository.save_booking(_booking("b1", status=BookingStatus.CANCELLED))
    repository.save_booking(_booking("b2"))
    assert repository.active_booking("res-a").booking_id == "b2"
    assert {b.booking_id for b in repository.list_bookings("res-a")} == {"b1", "b2"}
    assert [b.booking_id for b in repository.list_bookings(statuses=(BookingStatus.CANCELLED,))] == ["b1"]


def test_same_key_same_booking(clean_db):
    repository.upsert_user(_user())
    repository.save_booking(_booking(), idempotency_key="k1", request_hash="h1")
    assert repository.find_idempotent("k1", "res-a", "h1") == _booking()
    assert repository.find_idempotent("k1", "res-other", "h1") is None
    assert repository.find_idempotent("unknown", "res-a", "h1") is None


def test_same_key_other_body_conflicts(clean_db):
    repository.upsert_user(_user())
    repository.save_booking(_booking(), idempotency_key="k1", request_hash="h1")
    with pytest.raises(DomainError) as err:
        repository.find_idempotent("k1", "res-a", "h2")
    assert err.value.code == ErrorCode.IDEMPOTENCY_MISMATCH


def test_overdue_approvals_are_listed(clean_db):
    overdue = _approval(expires_at=NOW - timedelta(minutes=1))
    future = _approval(expires_at=NOW + timedelta(hours=1))
    decided = _approval(status=ApprovalStatus.APPROVED, expires_at=NOW - timedelta(hours=1))
    for a in (overdue, future, decided):
        repository.save_approval(a)
    assert [a.approval_id for a in repository.overdue_approvals(NOW)] == [overdue.approval_id]
    assert repository.get_approval(future.approval_id) == future
    assert len(repository.list_approvals(status=ApprovalStatus.PENDING)) == 2
    assert len(repository.list_approvals(requested_from="res-a")) == 3


def test_decision_log_is_append_only_and_ordered(clean_db):
    entries = [_decision(True), _decision(False), _decision(True)]
    for e in entries:
        repository.append_decision(e)
    got = repository.list_decisions()
    assert [e.entry_id for e in got] == [e.entry_id for e in reversed(entries)]
    assert len(repository.list_decisions(limit=2)) == 2
    assert len(repository.list_decisions(booking_id="b1")) == 3


def test_blocked_only_filter(clean_db):
    ok, blocked = _decision(True), _decision(False)
    repository.append_decision(ok)
    repository.append_decision(blocked)
    assert [e.entry_id for e in repository.list_decisions(blocked_only=True)] == [blocked.entry_id]


def test_notifications_are_per_resident(clean_db):
    repository.upsert_user(_user())
    repository.upsert_user(_user("res-b", "b@example.invalid"))
    repository.add_notification("res-a", _notification("n-a1"))
    repository.add_notification("res-a", _notification("n-a2", minutes=5))
    repository.add_notification("res-b", _notification("n-b1"))
    assert [n.notification_id for n in repository.list_notifications("res-a")] == ["n-a2", "n-a1"]
    assert repository.mark_notification_read("n-b1", "res-a") is None
    assert repository.mark_notification_read("n-a1", "res-a").read is True
    assert not any(n.read for n in repository.list_notifications("res-b"))


def test_events_newest_first_with_cursor(clean_db):
    for i in range(3):
        repository.append_event(
            StationEvent(type=EventType.TICK, occurred_at=NOW + timedelta(minutes=i), detail=str(i))
        )
    got = repository.list_events()
    assert [e.detail for e in got] == ["2", "1", "0"]
    assert [e.detail for e in repository.list_events(limit=1)] == ["2"]


def test_load_points_window(clean_db):
    base = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)
    for h in range(48):
        repository.append_load_point(
            LoadPoint(timestamp=base + timedelta(hours=h), total_power_kw=h, power_limit_kw=35)
        )
    since = base + timedelta(hours=24)
    got = repository.list_load_points(since)
    assert len(got) == 24
    assert [p.timestamp for p in got] == sorted(p.timestamp for p in got)
    assert got[0].timestamp == since


def _plan(version: int) -> SchedulePlan:
    return SchedulePlan(
        version=version,
        strategy=StrategyName.OPT_NO_ML,
        created_at=NOW,
        horizon_start=NOW,
        step_minutes=15,
        sessions=[SessionPlan(booking_id="b1", connector_id="AC-01-1", slots=[PowerSlot(start=NOW, power_kw=7)])],
    )


def test_latest_plan_survives_restart(clean_db):
    repository.save_plan(_plan(2))
    repository.save_plan(_plan(3))
    repository.dispose()
    assert repository.latest_plan() == _plan(3)
    assert repository.get_plan(2) == _plan(2)


def test_plan_history_is_capped(clean_db, monkeypatch):
    monkeypatch.setattr(repository, "PLAN_HISTORY_LIMIT", 3)
    for v in range(1, 6):
        repository.save_plan(_plan(v))
    assert repository.get_plan(2) is None
    assert repository.get_plan(3) == _plan(3)
    assert repository.latest_plan().version == 5


def test_anonymize_removes_email_keeps_log(clean_db):
    repository.upsert_user(_user())
    repository.save_booking(_booking())
    repository.append_decision(_decision(True))
    repository.anonymize_user("res-a", NOW)
    user = repository.get_user("res-a")
    assert user.password_hash is None
    assert "example" not in user.email
    assert user.deleted_at == NOW
    assert repository.get_user_by_email("a@example.invalid") is None
    assert repository.get_booking("b1") is not None
    assert len(repository.list_decisions(booking_id="b1")) == 1
