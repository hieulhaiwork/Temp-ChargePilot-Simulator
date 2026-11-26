"""Điền các trường hợp đồng đã khai báo nhưng chưa có nơi ghi (G6, G7, G24-WS).

- Alternative.request (G6): phương án đã chỉnh sẵn để cư dân bấm là đổi được luôn.
- Approval.effective_from / effective_until / current_power_kw (G7): khung áp dụng và công suất hiện tại.
- WsMessageType.SITE_OCCUPANCY (G24): bản tin cho cư dân khi sơ đồ bãi đổi.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from src.guard import approval as approval_rules
from src.models.control import ApprovalKind, Command, CommandSource, CommandType, GuardVerdict, Role
from src.models.events import EventType, WsMessage, WsMessageType
from src.services import realtime
from src.services.charging_service import _alternatives
from tests.factories import booking as make_booking

NOW = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)


def _fake_rt() -> SimpleNamespace:
    return SimpleNamespace(clock=lambda: NOW, config=SimpleNamespace(timezone="Asia/Ho_Chi_Minh"))


def test_alternatives_carry_prefilled_requests():
    candidate = make_booking("bk-alt", kwh=40, hours=6)
    alts = _alternatives(_fake_rt(), candidate, deliverable_kwh=10, start=NOW, connector_id="AC-01-1")
    kinds = {a.kind.value for a in alts}
    assert "lower_target" in kinds, "tình huống phải sinh phương án hạ mức pin để kiểm tra"
    for alt in alts:
        assert alt.request is not None, f"{alt.kind} thiếu request đã chỉnh sẵn (G6)"
    lower = next(a for a in alts if a.kind.value == "lower_target")
    assert lower.request.soc_target == lower.soc_target
    other = next(a for a in alts if a.kind.value == "other_time")
    assert other.request.deadline == other.deadline


def _set_power(connector_id: str = "AC-01-1") -> Command:
    return Command(
        type=CommandType.SET_POWER,
        connector_id=connector_id,
        power_kw=5.0,
        source=CommandSource.OPTIMIZER,
        issued_by="optimizer",
        based_on_schedule_version=1,
        based_on_state_at=NOW,
        created_at=NOW,
    )


def test_open_approval_records_effective_window_and_current_power():
    booking = make_booking("bk-appr").model_copy(update={"planned_end": NOW + timedelta(hours=2)})
    cmd = _set_power()
    verdict = GuardVerdict(command_id=cmd.command_id, passed=True, checked_at=NOW)
    approval = approval_rules.open_approval(
        cmd,
        verdict,
        ApprovalKind.RESIDENT_CONSENT,
        booking=booking,
        current_power_kw=7.4,
    )
    assert approval.current_power_kw == 7.4
    assert approval.effective_from == NOW
    assert approval.effective_until == booking.planned_end


def test_site_occupancy_is_a_websocket_message_not_a_station_event():
    assert WsMessageType.SITE_OCCUPANCY == "site_occupancy"
    assert not hasattr(EventType, "SITE_OCCUPANCY")


class _Recorder:
    def __init__(self) -> None:
        self.received: list[WsMessage] = []

    async def __call__(self, message: WsMessage) -> None:
        self.received.append(message)


def test_site_occupancy_reaches_every_resident_connection():
    a, b, op = _Recorder(), _Recorder(), _Recorder()
    ids = [
        realtime.register(a, Role.RESIDENT, "res-a"),
        realtime.register(b, Role.RESIDENT, "res-b"),
        realtime.register(op, Role.OPERATOR, "op-1"),
    ]
    try:
        msg = WsMessage(type=WsMessageType.SITE_OCCUPANCY, payload={"bays": []}, sent_at=NOW)
        asyncio.run(realtime.broadcast(msg, role=Role.RESIDENT, to_residents=True))
        assert len(a.received) == 1 and len(b.received) == 1
        assert op.received == []
    finally:
        for cid in ids:
            realtime.unregister(cid)
