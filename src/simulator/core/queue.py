"""Vehicle sessions, waiting queues and connector lifecycle."""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

from src.models.simulation_core import Cabinet, Scenario, Vehicle

from .ev2gym_adapter import EV2GymAdapter


@dataclass
class Session:
    vehicle: Vehicle
    state: str = "NOT_ARRIVED"
    connector: str | None = None
    last_connector: str | None = None
    charge_started: int | None = None
    completed_at: int | None = None
    departed_at: int | None = None
    delivered_battery_kwh: float = 0.0
    delivered_grid_kwh: float = 0.0


class QueueController:
    """Owns queue order and occupancy; foreign EV IDs never enter the ledger."""

    def __init__(self, scenario: Scenario):
        self.sessions = {v.id: Session(v) for v in scenario.vehicles}
        self.waiting = {zone: deque() for zone in scenario.zone_kw}
        self.connectors: dict[str, tuple[Cabinet, int]] = {
            f"{cab.id}/P{i + 1}": (cab, i) for cab in scenario.cabinets for i in range(cab.ports)
        }
        self.occupied: dict[str, str] = {}

    def advance(self, when: int, scenario: Scenario, adapter: EV2GymAdapter, emit) -> None:
        for vid, session in self.sessions.items():
            v = session.vehicle
            if session.state in ("NOT_ARRIVED", "DEPARTED"):
                continue
            dc_unplug = (
                v.zone == "DC" and session.completed_at is not None and when >= session.completed_at + scenario.delay
            )
            if when < v.departure and not dc_unplug:
                continue
            port = session.connector
            if port is None:
                self.waiting[v.zone].remove(vid)
                emit(when, "LEFT_QUEUE", v, reason="declared_departure")
            else:
                cab, index = self.connectors[port]
                adapter.disconnect(vid, cab.id, index)
                del self.occupied[port]
                emit(
                    when,
                    "UNPLUGGED",
                    v,
                    connector=port,
                    completed=session.completed_at is not None,
                    reason="declared_departure" if when >= v.departure else "dc_unplug_delay",
                )
            session.connector = None
            session.state = "DEPARTED"
            session.departed_at = when
        if when == scenario.end:
            return
        for vid, session in self.sessions.items():
            v = session.vehicle
            if session.state == "NOT_ARRIVED" and v.arrival == when:
                session.state = "QUEUED"
                self.waiting[v.zone].append(vid)
                emit(when, "ARRIVED", v)

    def connect(self, when: int, plan: Mapping[str, str], adapter: EV2GymAdapter, emit) -> None:
        """Apply validated assignments in stable connector order."""
        for port, (cab, index) in self.connectors.items():
            if port not in plan:
                continue
            vid = plan[port]
            adapter.connect(vid, cab.id, index)
            self.waiting[cab.zone].remove(vid)
            self.occupied[port] = vid
            session = self.sessions[vid]
            session.connector = session.last_connector = port
            session.charge_started = when
            session.state = "CHARGING"
            emit(when, "PLUGGED_IN", session.vehicle, connector=port)

    def next_boundary(self, now: int, scenario: Scenario, *, include_unseen_arrivals: bool = True) -> int:
        boundary = min(now + scenario.timestep, scenario.end)
        for session in self.sessions.values():
            v = session.vehicle
            if session.state == "NOT_ARRIVED":
                if include_unseen_arrivals:
                    boundary = min(boundary, v.arrival)
            elif session.state != "DEPARTED":
                boundary = min(boundary, v.departure)
                if v.zone == "DC" and session.completed_at is not None:
                    boundary = min(boundary, session.completed_at + scenario.delay)
        return boundary
