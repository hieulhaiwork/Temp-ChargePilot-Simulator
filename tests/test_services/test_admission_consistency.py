"""Final Acceptance §2 — admission consistency cho `book` / `change` / `cancel`.

- `change` dùng optimistic concurrency như `book`: admission NGOÀI khoá, commit dưới `rt.booking_lock` kiểm lại
  `rt.admission_fingerprint()`; đổi ⇒ chạy lại admission (có giới hạn) / PROPOSAL_EXPIRED.
- `change` / `cancel` kiểm lại trạng thái booking dưới khoá: booking đã huỷ không "sống lại"; hai lần huỷ đồng thời
  chỉ một lần đổi trạng thái + một sự kiện.
- Nguồn / đầu nối đổi giữa snapshot và commit ⇒ admission chạy lại trên trạng thái mới.
- Consent: `change` chạy admission trên consent thật của booking; `quote` ghi rõ consent giả định.
"""

import asyncio
from datetime import datetime, timedelta

import pytest

pytest.importorskip("ev2gym")

from src.models.api import BookingChangeRequest, ErrorCode  # noqa: E402
from src.models.charging import BookingStatus, ChargeMode, ChargeRequest, ConsentScope  # noqa: E402
from src.models.control import Role  # noqa: E402
from src.models.events import EventType  # noqa: E402
from src.models.identity import UserRecord  # noqa: E402
from src.models.simulation import Incident, IncidentType  # noqa: E402
from src.services import admission, charging_service, event_bus, repository, runtime  # noqa: E402
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


def _wrap_evaluate(monkeypatch, live, during=None, parties=0):
    """Bọc admission.evaluate: ghi lại lời gọi; `during(order)` chạy sau khi admission tính xong (trước commit) — giả
    lập một thay đổi đồng thời; `parties` lượt đầu chờ nhau (ép cửa sổ race như test booking concurrency)."""
    real = admission.evaluate
    done = asyncio.Event()
    calls = {"n": 0, "locked_during_admission": False, "candidates": []}

    async def evaluate(rt, candidate, *, exclude=None):
        calls["n"] += 1
        order = calls["n"]
        calls["candidates"].append(candidate)
        calls["locked_during_admission"] |= live.booking_lock.locked()
        result = await real(rt, candidate, exclude=exclude)
        if order <= parties:
            if order == parties:
                done.set()
            await asyncio.wait_for(done.wait(), timeout=30)
        if during is not None:
            await during(order)
        return result

    monkeypatch.setattr(admission, "evaluate", evaluate)
    return calls


def _count_events(kind: EventType) -> list:
    seen: list = []

    async def handler(event):
        if event.type == kind:
            seen.append(event)

    event_bus.subscribe(kind, handler)
    return seen


# ---- change: optimistic concurrency -----------------------------------------------------------------------------


async def test_change_racing_a_booking_reruns_admission_on_the_new_state(live, monkeypatch):
    mine = await charging_service.book(_request(hours=10), "res-a")
    version = live.booking_version
    calls = _wrap_evaluate(monkeypatch, live, parties=2)
    changed, other = await asyncio.gather(
        charging_service.change(mine.booking_id, BookingChangeRequest(soc_target=70), "res-a"),
        charging_service.book(_request(hours=8), "res-b"),
    )
    assert calls["n"] == 3  # bên commit sau thấy fingerprint đổi và chạy lại admission trên trạng thái mới
    assert not calls["locked_during_admission"]
    assert changed.request.soc_target == 70 and other.resident_id == "res-b"
    assert live.booking_version == version + 2
    assert {s for s in live.simulator.queue.sessions} >= {mine.booking_id, other.booking_id}


async def test_change_gives_up_with_proposal_expired_after_bounded_retries(live, monkeypatch):
    mine = await charging_service.book(_request(hours=10), "res-a")

    async def churn(order):
        live.booking_version += 1  # tập booking đổi sau MỖI lần admission

    calls = _wrap_evaluate(monkeypatch, live, during=churn)
    with pytest.raises(DomainError) as err:
        await charging_service.change(mine.booking_id, BookingChangeRequest(soc_target=70), "res-a")
    assert err.value.code == ErrorCode.PROPOSAL_EXPIRED
    assert calls["n"] == charging_service.BOOKING_COMMIT_ATTEMPTS
    assert repository.get_booking(mine.booking_id).request.soc_target == 80  # booking cũ giữ nguyên


# ---- change / cancel: kiểm lại trạng thái dưới khoá ---------------------------------------------------------


async def test_change_does_not_resurrect_a_booking_cancelled_during_admission(live, monkeypatch):
    mine = await charging_service.book(_request(hours=10), "res-a")
    changed_events = _count_events(EventType.BOOKING_CHANGED)

    async def cancel_concurrently(order):
        if order == 1:
            await charging_service.cancel(mine.booking_id, "res-a")

    _wrap_evaluate(monkeypatch, live, during=cancel_concurrently)
    with pytest.raises(DomainError) as err:
        await charging_service.change(mine.booking_id, BookingChangeRequest(soc_target=70), "res-a")
    assert err.value.code == ErrorCode.BOOKING_CONFLICT
    stored = repository.get_booking(mine.booking_id)
    assert stored.status == BookingStatus.CANCELLED and stored.request.soc_target == 80
    assert not changed_events
    session = live.simulator.queue.sessions.get(mine.booking_id)
    assert session is None or session.state == "DEPARTED"  # xe không được đưa lại vào trạm


async def test_two_concurrent_cancels_change_state_once_and_emit_one_event(live):
    mine = await charging_service.book(_request(hours=10), "res-a")
    cancelled_events = _count_events(EventType.BOOKING_CANCELLED)
    version = live.booking_version
    await live.booking_lock.acquire()  # giữ khoá để cả hai lần huỷ cùng qua kiểm tra nhanh rồi chờ khoá
    tasks = [asyncio.create_task(charging_service.cancel(mine.booking_id, "res-a")) for _ in range(2)]
    for _ in range(5):
        await asyncio.sleep(0)
    assert not any(t.done() for t in tasks)
    live.booking_lock.release()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok = [r for r in results if not isinstance(r, Exception)]
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(ok) == 1 and ok[0].status == BookingStatus.CANCELLED
    assert len(errors) == 1 and isinstance(errors[0], DomainError) and errors[0].code == ErrorCode.BOOKING_CONFLICT
    assert len(cancelled_events) == 1
    assert live.booking_version == version + 1


# ---- nguồn / đầu nối đổi trong lúc admission ---------------------------------------------------------------


@pytest.mark.parametrize(
    "incident",
    [
        Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=80.0),
        Incident(type=IncidentType.CONNECTOR_FAULT, connector_id="AC-02-1"),
    ],
    ids=["power_limit", "connector_fault"],
)
async def test_booking_reruns_admission_when_supply_or_connector_changes_during_admission(live, monkeypatch, incident):
    seen_limits: list[float] = []

    async def change_station(order):
        seen_limits.append(live.simulator.available_power_kw)
        if order == 1:
            with live.simulator.lock:
                live.simulator.inject_incident(incident)

    calls = _wrap_evaluate(monkeypatch, live, during=change_station)
    booked = await charging_service.book(_request(hours=10), "res-a")
    assert calls["n"] == 2  # snapshot ≠ commit ⇒ tính lại trên trạng thái mới
    assert booked.booking_id in live.simulator.queue.sessions
    if incident.type == IncidentType.POWER_LIMIT_CHANGE:
        assert seen_limits == [106.0, 80.0]
    else:
        assert booked.connector_id != "AC-02-1"


async def test_booking_fails_when_a_power_drop_during_admission_makes_it_infeasible(live, monkeypatch):
    urgent = _request(zone="DC", hours=1, soc_now=20, soc_target=80)
    assert charging_service.quote(urgent, "res-a").feasible

    async def drop(order):
        if order == 1:
            with live.simulator.lock:
                live.simulator.inject_incident(Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=5.0))

    calls = _wrap_evaluate(monkeypatch, live, during=drop)
    with pytest.raises(DomainError) as err:
        await charging_service.book(urgent, "res-a")
    assert err.value.code == ErrorCode.PROPOSAL_EXPIRED
    assert calls["n"] == 2
    assert repository.active_booking("res-a") is None


async def test_change_reruns_admission_when_power_limit_changes(live, monkeypatch):
    mine = await charging_service.book(_request(hours=10), "res-a")

    async def drop(order):
        if order == 1:
            with live.simulator.lock:
                live.simulator.inject_incident(Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=80.0))

    calls = _wrap_evaluate(monkeypatch, live, during=drop)
    changed = await charging_service.change(mine.booking_id, BookingChangeRequest(soc_target=70), "res-a")
    assert calls["n"] == 2 and changed.request.soc_target == 70


# ---- consent ------------------------------------------------------------------------------------------------


async def test_change_runs_admission_on_the_bookings_real_consent(live, monkeypatch):
    strict = ConsentScope(allow_power_reduction=False, max_start_delay_minutes=5)
    mine = await charging_service.book(_request(hours=10), "res-a", consent=strict)
    calls = _wrap_evaluate(monkeypatch, live)
    changed = await charging_service.change(mine.booking_id, BookingChangeRequest(soc_target=70), "res-a")
    assert [c.consent for c in calls["candidates"]] == [strict]
    assert changed.consent == strict


async def test_quote_states_its_consent_assumption(live):
    proposal = charging_service.quote(_request(), "res-a")
    assert proposal.assumptions[: len(admission.ASSUMPTIONS)] == list(admission.ASSUMPTIONS)
    (note,) = proposal.assumptions[len(admission.ASSUMPTIONS) :]
    default = ConsentScope()
    assert "consent" in note and f"{default.max_start_delay_minutes} phút" in note
    assert "consent thật" in note
