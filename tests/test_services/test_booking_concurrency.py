"""Final Review §4.6 — booking đồng thời (optimistic concurrency) + consent parity của `charging_service.book`.

Cửa sổ race được ép bằng một "barrier" quanh `admission.evaluate`: cả hai yêu cầu đều tính xong admission trên trạng
thái CHƯA có booking của nhau rồi mới được commit. Commit dưới `rt.booking_lock` kiểm lại booking hiệu lực của cư dân
và `rt.booking_version` ⇒ cùng cư dân: đúng 1 booking; trạm chỉ còn chỗ cho 1: không overbook (người sau chạy lại
admission và nhận PROPOSAL_EXPIRED). Admission không chạy dưới khoá commit (không khoá trạm suốt rollout).
"""

import asyncio
from datetime import datetime, timedelta

import pytest

pytest.importorskip("ev2gym")

from src.models.api import ErrorCode  # noqa: E402
from src.models.charging import ChargeMode, ChargeRequest, ConsentScope  # noqa: E402
from src.models.control import Role  # noqa: E402
from src.models.identity import UserRecord  # noqa: E402
from src.services import admission, charging_service, repository, runtime  # noqa: E402
from src.services.errors import DomainError  # noqa: E402
from tests.factories import NOW  # noqa: E402

T0 = datetime(2026, 11, 23, 18, 0, tzinfo=NOW.tzinfo)


@pytest.fixture
def live(monkeypatch, clean_db):
    monkeypatch.setattr(runtime, "_live_clock", lambda config: lambda: T0)
    runtime.reset_runtime()
    for uid in ("res-a", "res-b", "res-c"):
        repository.upsert_user(
            UserRecord(user_id=uid, email=f"{uid}@example.invalid", role=Role.RESIDENT, display_name=uid, created_at=T0)
        )
    return runtime.get_runtime()


def _request(zone="AC", hours=10.0, soc_now=30, soc_target=80) -> ChargeRequest:
    return ChargeRequest(
        vehicle_model="VF8_NEW_2026",
        soc_now=soc_now,
        soc_target=soc_target,
        deadline=T0 + timedelta(hours=hours),
        mode=ChargeMode.WALK_IN,
        zone=zone,
    )


def _barrier(monkeypatch, live, parties=2):
    """Bọc admission.evaluate: `parties` lượt đầu chờ nhau tính xong rồi mới trả (ép cửa sổ race)."""
    real = admission.evaluate
    done = asyncio.Event()
    calls = {"n": 0, "locked_during_admission": False, "consents": []}

    async def evaluate(rt, candidate, *, exclude=None):
        calls["n"] += 1
        order = calls["n"]
        calls["consents"].append((candidate.resident_id, candidate.consent))
        calls["locked_during_admission"] |= live.booking_lock.locked()
        result = await real(rt, candidate, exclude=exclude)
        if order <= parties:
            if order == parties:
                done.set()
            await asyncio.wait_for(done.wait(), timeout=30)
        return result

    monkeypatch.setattr(admission, "evaluate", evaluate)
    return calls


async def test_same_resident_two_concurrent_bookings_yield_exactly_one(live, monkeypatch):
    calls = _barrier(monkeypatch, live)
    results = await asyncio.gather(
        charging_service.book(_request(), "res-a"), charging_service.book(_request(), "res-a"), return_exceptions=True
    )
    created = [r for r in results if not isinstance(r, Exception)]
    errors = [r for r in results if isinstance(r, Exception)]
    assert calls["n"] == 2  # cả hai đã tính admission trên trạng thái chưa có booking của nhau
    assert len(created) == 1 and len(errors) == 1
    assert isinstance(errors[0], DomainError) and errors[0].code == ErrorCode.BOOKING_CONFLICT
    assert [b.booking_id for b in repository.list_bookings() if b.resident_id == "res-a"] == [created[0].booking_id]
    assert not calls["locked_during_admission"]
    assert list(live.simulator.queue.sessions) == [created[0].booking_id]


async def test_same_idempotency_key_concurrently_returns_the_same_booking(live, monkeypatch):
    _barrier(monkeypatch, live)
    first, second = await asyncio.gather(
        charging_service.book(_request(), "res-a", idempotency_key="chat:s1"),
        charging_service.book(_request(), "res-a", idempotency_key="chat:s1"),
    )
    assert first.booking_id == second.booking_id
    assert len(repository.list_bookings()) == 1


async def test_two_residents_racing_for_the_last_port_do_not_overbook(live, monkeypatch):
    """AC-01-1 bị xe ở lại 10 h giữ; còn MỘT cổng AC. Hai xe cần ~45' sạc trước hạn 1 h: một mình thì kịp, cả hai thì
    xe sau phải chờ cổng tới khi xe trước rời (giờ rời khai báo, F14) ⇒ không kịp."""
    stay = await charging_service.book(_request(hours=10), "res-c")
    assert stay.connector_id is not None
    urgent = _request(hours=1, soc_now=70, soc_target=80)
    assert charging_service.quote(urgent, "res-a").feasible  # mỗi xe một mình: khả thi
    calls = _barrier(monkeypatch, live)
    results = await asyncio.gather(
        charging_service.book(urgent, "res-a"), charging_service.book(urgent, "res-b"), return_exceptions=True
    )
    created = [r for r in results if not isinstance(r, Exception)]
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(created) == 1, results
    assert isinstance(errors[0], DomainError) and errors[0].code == ErrorCode.PROPOSAL_EXPIRED
    assert calls["n"] == 3  # người thua phát hiện booking_version đổi và chạy lại admission trên trạng thái mới
    active = [b for b in repository.list_bookings() if b.resident_id in ("res-a", "res-b")]
    assert [b.booking_id for b in active] == [created[0].booking_id]


async def test_booking_admission_runs_with_the_consent_that_is_stored(live, monkeypatch):
    calls = _barrier(monkeypatch, live, parties=0)
    strict = ConsentScope(allow_power_reduction=False, max_start_delay_minutes=5)
    booking = await charging_service.book(_request(), "res-a", consent=strict)
    assert booking.consent == strict
    assert calls["consents"] == [("res-a", strict)]  # admission đã chạy trên đúng consent được lưu
    user_default = repository.get_user("res-b").consent
    other = await charging_service.book(_request(zone="DC", hours=3), "res-b")
    assert other.consent == user_default and calls["consents"][-1] == ("res-b", user_default)


async def test_quote_keeps_the_default_consent(live, monkeypatch):
    calls = _barrier(monkeypatch, live, parties=0)
    charging_service.quote(_request(), "res-a")
    assert calls["consents"] == [("res-a", ConsentScope())]
