"""Dựng nhanh Booking / StationState / PlanningContext cho test optimizer, simulator, control loop.

Dùng chung cho nhiều file test để mọi test cùng một cách dựng dữ liệu trên topology thật của
config/station.yaml (ADR-010): AC-01-1, AC-02-1 (11 kW), DC-01-1, DC-01-2 (60 kW).
"""

from datetime import datetime, timedelta, timezone

from src.models.charging import Booking, BookingStatus, ChargeMode, ChargeRequest, ConsentScope, EnergyEstimate
from src.models.station import ConnectorState, ConnectorStatus, SessionProgress, StationState
from src.optimizer.base import PlanningContext
from src.services import catalog

VN = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 23, 20, 0, tzinfo=VN)


def booking(
    booking_id: str,
    *,
    kwh: float = 20,
    hours: float = 10,
    zone: str = "AC",
    cap: float | None = None,
    arrival: datetime | None = None,
    status: BookingStatus = BookingStatus.CONFIRMED,
    now: datetime = NOW,
) -> Booking:
    request = ChargeRequest(
        vehicle_model="VF8_NEW_2026",
        soc_now=20,
        soc_target=80,
        arrival_time=arrival,
        deadline=(arrival or now) + timedelta(hours=hours),
        mode=ChargeMode.RESERVATION if arrival else ChargeMode.WALK_IN,
        zone=zone,
    )
    energy = EnergyEstimate(
        vehicle_model="VF8_NEW_2026",
        soc_now=20,
        soc_target=80,
        battery_energy_kwh=kwh,
        grid_energy_kwh=kwh,
        efficiency=1,
    )
    return Booking(
        booking_id=booking_id,
        resident_id=f"res-{booking_id}",
        request=request,
        status=status,
        energy=energy,
        max_charge_power_kw=cap or (60 if zone == "DC" else 11),
        consent=ConsentScope(max_start_delay_minutes=24 * 60),
        schedule_version=0,
        created_at=now,
    )


def state(
    plugged: dict[str, str] | None = None,
    *,
    queue: tuple[str, ...] = (),
    delivered: dict[str, float] | None = None,
    available: float = 106,
    fault: tuple[str, ...] = (),
    finished: tuple[str, ...] = (),
    now: datetime = NOW,
) -> StationState:
    """plugged: connector_id → booking_id đang cắm; queue: booking đã đến nhưng chưa cắm."""
    plugged = plugged or {}
    delivered = delivered or {}
    connectors = []
    for spec in catalog.load_station_config().connectors:
        bid = plugged.get(spec.connector_id)
        status = ConnectorStatus.IDLE if bid is None else ConnectorStatus.THROTTLED
        if spec.connector_id in fault:
            status = ConnectorStatus.FAULT
        if spec.connector_id in finished:
            status = ConnectorStatus.FINISHED
        connectors.append(
            ConnectorState(
                connector_id=spec.connector_id,
                status=status,
                power_kw=0,
                max_power_kw=spec.max_power_kw,
                booking_id=bid,
            )
        )
    sessions = [
        SessionProgress(
            booking_id=b, connector_id=c, arrived_at=now, plugged_in_at=now, delivered_grid_kwh=delivered.get(b, 0)
        )
        for c, b in plugged.items()
    ] + [SessionProgress(booking_id=b, arrived_at=now) for b in queue]
    return StationState(
        timestamp=now,
        available_power_kw=available,
        connectors=connectors,
        queue=list(queue),
        sessions=sessions,
        schedule_version=0,
    )


def context(bookings, st: StationState | None = None, **kw) -> PlanningContext:
    return PlanningContext(
        now=(st.timestamp if st else NOW),
        state=st or state(),
        bookings=tuple(bookings),
        config=catalog.load_station_config(),
        tariff=catalog.load_tariff(),
        **kw,
    )


def energy_of(plan, booking_id: str) -> float:
    session = next(s for s in plan.sessions if s.booking_id == booking_id)
    return sum(s.power_kw for s in session.slots) * plan.step_minutes / 60


def total_by_step(plan) -> dict:
    out: dict = {}
    for s in plan.sessions:
        for slot in s.slots:
            out[slot.start] = out.get(slot.start, 0) + slot.power_kw
    return out
