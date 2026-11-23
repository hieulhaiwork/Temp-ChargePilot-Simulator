"""Hợp đồng PlanningContext + tham số optimizer trong config (ADR-003).

Test của LP backend A–D (T2.1–T2.4) bị xoá cùng LP backend ở ADR-019 Phase 3 — danh sách và test thay thế:
docs/refactor/DELETION_MANIFEST.md.
"""

import dataclasses
from datetime import UTC, datetime

import pytest

from src.models.planning import PlanningContext
from src.models.station import StationState
from src.services import catalog


def _context(**overrides) -> PlanningContext:
    now = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
    st = StationState(timestamp=now, available_power_kw=35, connectors=[], schedule_version=0)
    base = {
        "now": now,
        "state": st,
        "bookings": (),
        "config": catalog.load_station_config(),
        "tariff": catalog.load_tariff(),
    }
    return PlanningContext(**(base | overrides))


def test_planning_context_defaults_keep_live_mode_honest():
    """Live: không có dự báo, không booking nào bị khoá consent."""
    ctx = _context()
    assert ctx.departure_forecast is None
    assert not hasattr(ctx, "oracle_bookings")  # oracle (chiến lược D) đã bỏ — Phase 4 quyết định 1
    assert ctx.hard_consent_booking_ids == frozenset()


def test_planning_context_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _context().now = datetime(2027, 1, 1, tzinfo=UTC)


def test_objective_weights_come_from_config_not_code():
    """ADR-003: λ_u, ε, μ nằm ở config/station.yaml — phân tích độ nhạy không sửa code."""
    optimizer = catalog.load_station_config().optimizer
    assert optimizer.unmet_penalty_factor >= 10  # điện thiếu phải trội hẳn tiền điện
    assert 0 <= optimizer.early_charge_factor < 1
    assert 0 <= optimizer.smoothing_factor < 1
