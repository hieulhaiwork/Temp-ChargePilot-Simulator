"""Hợp đồng của bộ tối ưu (FR6, FR7, FR9) — công thức: docs/plan/30-ai.md §5.

Topology thật của config/station.yaml (ADR-010); bước LP = config.optimizer.planning_step_minutes.
"""

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from src.models.charging import ConsentScope, StrategyName
from src.models.station import StationState
from src.optimizer.assignment import assign_connectors
from src.optimizer.base import PlanningContext
from src.optimizer.lp_model import solve_power_allocation, solve_with_unmet
from src.optimizer.strategies import get_scheduler
from src.services import catalog
from tests.factories import NOW, booking, context, energy_of, state, total_by_step


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
    """Live: không có dự báo, không có oracle, không booking nào bị khoá consent."""
    ctx = _context()
    assert ctx.departure_forecast is None
    assert ctx.oracle_bookings == ()
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


# ---- T2.1: LP của một bước MPC -----------------------------------------------------------


def _lp(ctx):
    return solve_power_allocation(ctx, assign_connectors(ctx), StrategyName.OPT_NO_ML)


def test_total_power_never_exceeds_limit():
    """MT4. 2 xe AC + 2 xe DC cùng lúc, nguồn còn 40 kW lưới. Then ∀t: Σ p / η ≤ 40 và ngân sách DC ≤ 78."""
    bks = [
        booking("a1"),
        booking("a2"),
        booking("d1", zone="DC", kwh=50, hours=2),
        booking("d2", zone="DC", kwh=50, hours=2),
    ]
    st = state({"AC-01-1": "a1", "AC-02-1": "a2", "DC-01-1": "d1", "DC-01-2": "d2"}, available=40)
    ctx = context(bks, st)
    plan = _lp(ctx)
    eta = ctx.config.power_conversion_efficiency
    assert all(total / eta <= 40 + 1e-6 for total in total_by_step(plan).values())
    dc: dict = {}
    for s in plan.sessions:
        if s.booking_id.startswith("d"):
            for slot in s.slots:
                dc[slot.start] = dc.get(slot.start, 0) + slot.power_kw
    assert all(v <= 78 + 1e-6 for v in dc.values())


def test_power_respects_vehicle_and_connector_cap():
    plan = _lp(context([booking("a1", cap=3.7, kwh=30, hours=12)], state({"AC-01-1": "a1"})))
    assert all(slot.power_kw <= 3.7 + 1e-6 for s in plan.sessions for slot in s.slots)


def test_cheaper_slots_are_preferred_when_deadline_allows():
    """MT3. 14 kWh, cắm 20:00, hạn 07:00 → phần lớn năng lượng rơi vào thấp điểm 22:00–04:00."""
    plan = _lp(context([booking("a1", kwh=14, hours=11)], state({"AC-01-1": "a1"})))
    session = next(s for s in plan.sessions if s.booking_id == "a1")

    def off_peak(t: datetime) -> bool:
        hour = t.astimezone(NOW.tzinfo).hour
        return hour >= 22 or hour < 4

    cheap = sum(slot.power_kw for slot in session.slots if off_peak(slot.start))
    assert cheap / sum(slot.power_kw for slot in session.slots) > 0.9


def test_unmet_energy_is_reported_not_hidden():
    """FR4. 57 kWh trong 3 giờ ở 11 kW là bất khả thi: bài vẫn giải được, điện thiếu > 0 và lộ ra ngoài."""
    ctx = context([booking("a1", kwh=57, hours=3)], state({"AC-01-1": "a1"}))
    plan, unmet = solve_with_unmet(ctx, assign_connectors(ctx), StrategyName.OPT_NO_ML)
    assert unmet["a1"] == pytest.approx(57 - 33, abs=0.01)
    assert energy_of(plan, "a1") == pytest.approx(33, abs=0.01)


def test_no_energy_is_scheduled_after_declared_deadline():
    """FR9. Hạn là ràng buộc cứng: không bước nào ≥ deadline, kể cả khi còn thiếu điện."""
    plan = _lp(context([booking("a1", kwh=57, hours=3)], state({"AC-01-1": "a1"})))
    deadline = NOW + timedelta(hours=3)
    assert all(slot.start < deadline for s in plan.sessions for slot in s.slots)


def test_never_charges_beyond_requested_energy():
    plan = _lp(context([booking("a1", kwh=10, hours=12)], state({"AC-01-1": "a1"})))
    assert energy_of(plan, "a1") <= 10 + 1e-6


def test_already_delivered_energy_is_not_scheduled_again():
    plan = _lp(context([booking("a1", kwh=10, hours=12)], state({"AC-01-1": "a1"}, delivered={"a1": 7})))
    assert energy_of(plan, "a1") == pytest.approx(3, abs=1e-3)


# ---- FR13: consent "được lùi giờ bắt đầu tối đa" -----------------------------------------


def _no_delay(b, minutes: int = 0):
    return b.model_copy(update={"consent": ConsentScope(max_start_delay_minutes=minutes)})


def _first_step_kw(plan, booking_id: str) -> float:
    session = next(s for s in plan.sessions if s.booking_id == booking_id)
    return next((slot.power_kw for slot in session.slots if slot.start == plan.horizon_start), 0.0)


def test_no_delay_consent_starts_charging_now_even_if_cheaper_later():
    """Cắm 20:00 (giá thường), thấp điểm từ 22:00. Cư dân KHÔNG cho lùi giờ → bước đầu phải sạc, không chờ giá rẻ."""
    plan = _lp(context([_no_delay(booking("a1", kwh=14, hours=11))], state({"AC-01-1": "a1"})))
    assert _first_step_kw(plan, "a1") == pytest.approx(11, abs=1e-3)
    assert energy_of(plan, "a1") <= 14 + 1e-6


def test_delay_consent_still_lets_lp_wait_for_cheaper_hours():
    """Cho lùi tới 24 giờ → LP được chờ thấp điểm như trước (MT3 không đổi)."""
    plan = _lp(context([booking("a1", kwh=14, hours=11)], state({"AC-01-1": "a1"})))
    assert _first_step_kw(plan, "a1") == pytest.approx(0, abs=1e-3)


def test_start_delay_counts_from_plug_in_not_from_each_replan():
    """Cắm lúc 19:30, cho lùi 30 phút → lúc tính lại 20:00 đã hết hạn lùi: phải sạc ngay, không trôi theo now."""
    st = state({"AC-01-1": "a1"})
    sessions = [s.model_copy(update={"plugged_in_at": NOW - timedelta(minutes=30)}) for s in st.sessions]
    plan = _lp(context([_no_delay(booking("a1", kwh=14, hours=11), 30)], st.model_copy(update={"sessions": sessions})))
    assert _first_step_kw(plan, "a1") > 0


def test_started_session_may_pause_for_cheaper_hours():
    """Đã nhận điện → không còn là "lùi giờ bắt đầu"; tạm dừng chờ giá rẻ thuộc allow_power_reduction (Guard xét)."""
    st = state({"AC-01-1": "a1"}, delivered={"a1": 2})
    plan = _lp(context([_no_delay(booking("a1", kwh=14, hours=11))], st))
    assert _first_step_kw(plan, "a1") == pytest.approx(0, abs=1e-3)


def test_start_requirement_never_makes_the_plan_infeasible():
    """Nguồn chỉ còn 5 kW, 2 xe đều không cho lùi: bài vẫn giải, không vượt giới hạn (MT4 ưu tiên hơn consent)."""
    bks = [_no_delay(booking("a1")), _no_delay(booking("a2"))]
    ctx = context(bks, state({"AC-01-1": "a1", "AC-02-1": "a2"}, available=5))
    plan = _lp(ctx)
    eta = ctx.config.power_conversion_efficiency
    assert all(total / eta <= 5 + 1e-6 for total in total_by_step(plan).values())
    assert sum(_first_step_kw(plan, b) for b in ("a1", "a2")) == pytest.approx(5 * eta, abs=1e-3)


def test_plan_is_deterministic():
    """Scheduler.plan phải thuần: cùng PlanningContext → cùng SchedulePlan (trừ created_at / solve_time_s)."""
    ctx = context([booking("a1"), booking("d1", zone="DC", kwh=40, hours=2)], state({"AC-01-1": "a1", "DC-01-1": "d1"}))
    p1, p2 = (get_scheduler(StrategyName.OPT_NO_ML).plan(ctx) for _ in range(2))
    strip = {"created_at", "solve_time_s"}
    assert p1.model_dump(exclude=strip) == p2.model_dump(exclude=strip)


# ---- T2.2: gán đầu nối -------------------------------------------------------------------


def test_plugged_cars_keep_their_connector():
    bks = [booking("old", hours=10), booking("urgent", hours=1)]
    a = assign_connectors(context(bks, state({"AC-01-1": "old"}, queue=("urgent",))))
    assert a.connector_of["old"] == "AC-01-1"
    assert a.connector_of["urgent"] == "AC-02-1"


def test_waiting_cars_are_ordered_by_earliest_deadline():
    """FR7. 3 xe chờ với hạn 6h, 5h, 7h (cổng AC đều bận tới 12h) → queue theo hạn tăng dần; FIFO giữ thứ tự đến."""
    bks = [
        booking("p1", hours=12),
        booking("p2", hours=12),
        booking("q6", hours=6),
        booking("q5", hours=5),
        booking("q7", hours=7),
    ]
    st = state({"AC-01-1": "p1", "AC-02-1": "p2"}, queue=("q6", "q5", "q7"))
    assert assign_connectors(context(bks, st)).queue == ("q5", "q6", "q7")
    assert assign_connectors(context(bks, st), "fifo").queue == ("q6", "q5", "q7")


def test_faulted_connector_is_never_assigned():
    """FR18."""
    a = assign_connectors(context([booking("w1"), booking("w2")], state(queue=("w1", "w2"), fault=("AC-01-1",))))
    assert "AC-01-1" not in a.connector_of.values()
    assert a.connector_of == {"w1": "AC-02-1"}
    assert a.queue == ("w2",)


def test_finished_but_plugged_car_still_occupies_connector():
    bks = [booking("done", kwh=10), booking("x", hours=12), booking("w1", hours=3)]
    st = state({"AC-01-1": "done", "AC-02-1": "x"}, queue=("w1",), delivered={"done": 10}, finished=("AC-01-1",))
    a = assign_connectors(context(bks, st))
    assert a.connector_of["done"] == "AC-01-1"
    assert "w1" in a.queue


def test_zones_are_never_mixed():
    """ADR-010: xe DC chỉ vào cổng DC."""
    a = assign_connectors(context([booking("d1", zone="DC", kwh=30, hours=2)], state(queue=("d1",))))
    assert a.connector_of["d1"].startswith("DC-")


def test_future_reservation_gets_a_predicted_connector():
    arrival = NOW + timedelta(hours=2)
    a = assign_connectors(context([booking("r1", arrival=arrival)], state()))
    assert a.connector_of["r1"].startswith("AC-")
    assert a.start_of["r1"] == arrival


# ---- T1.5 / T3.4: đối chứng --------------------------------------------------------------


def test_fcfs_shares_power_equally_and_stays_under_limit():
    """A. 2 xe DC cùng tủ, ngân sách DC 78 kW → mỗi xe 39 kW ở bước đầu, tổng ≤ 78."""
    bks = [booking("d1", zone="DC", kwh=60, hours=3), booking("d2", zone="DC", kwh=60, hours=3)]
    plan = get_scheduler(StrategyName.FCFS).plan(context(bks, state({"DC-01-1": "d1", "DC-01-2": "d2"})))
    first = {s.booking_id: s.slots[0].power_kw for s in plan.sessions}
    assert first == {"d1": pytest.approx(39), "d2": pytest.approx(39)}


def test_edf_gives_power_to_the_earliest_deadline_first():
    bks = [booking("late", zone="DC", kwh=60, hours=3), booking("soon", zone="DC", kwh=60, hours=1)]
    plan = get_scheduler(StrategyName.EDF).plan(context(bks, state({"DC-01-1": "late", "DC-01-2": "soon"})))
    first = {s.booking_id: s.slots[0].power_kw for s in plan.sessions}
    assert first["soon"] == pytest.approx(60)
    assert first["late"] == pytest.approx(18)


def test_oracle_uses_future_bookings_only_in_strategy_d():
    """D thấy xe sắp đến trong oracle_bookings; B không được đọc field này."""
    future = booking("future", zone="DC", kwh=30, hours=2, arrival=NOW + timedelta(hours=1))
    ctx = context([booking("now", zone="DC", kwh=20, hours=4)], state({"DC-01-1": "now"}), oracle_bookings=(future,))
    oracle = get_scheduler(StrategyName.ORACLE).plan(ctx)
    mpc = get_scheduler(StrategyName.OPT_NO_ML).plan(ctx)
    assert "future" in {s.booking_id for s in oracle.sessions}
    assert "future" not in {s.booking_id for s in mpc.sessions}
