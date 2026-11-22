"""LiveStation — trạm giả lập chạy liên tục cho backend (chế độ live + benchmark của backend).

Vì sao có file này (quyết định 2026-11-22 của người phụ trách, lệch một phần ADR-011): HybridSimulator
(src/simulator/src/) chạy trọn một kịch bản với optimizer + guard riêng và bắt buộc ev2gym, nên không đặt
được sau chokepoint Guard của backend (ADR-002) theo từng bước. LiveStation cài đúng Protocol
src/simulator/base.py: nhận lệnh đã qua Guard, tiến đồng hồ từng phút, nhận sự cố. HybridSimulator giữ
vai trò công cụ R&D / benchmark offline; số liệu hai bên KHÔNG được trộn vào cùng một bảng.

Mô hình vật lý (cố ý đơn giản, mọi tham số lấy từ StationConfig — ADR-003):
  - Công suất của cổng là công suất ĐẦU RA tủ (kW). Năng lượng tích phân = Σ p·Δt, đối chiếu với
    VehicleVisit.required_kwh (Booking.energy.grid_energy_kwh). Không mô phỏng đường sạc DC
    (taper) — giới hạn xe là hằng số max_power_kw. [GIẢ ĐỊNH, ghi trong ADR bổ sung]
  - Xe đủ điện → cổng FINISHED, công suất 0. Xe AC giữ cổng tới giờ rời khai báo; xe DC rút sau
    dc_unplug_delay_minutes (F14). Xe chờ quá giờ rời mà chưa được cắm thì rời bãi.
  - Lệnh không hợp lệ về vật lý (gán xe chưa đến, cổng đang bận / lỗi) bị bỏ qua và ghi log — Guard đã
    phải chặn trước; đây chỉ là lưới an toàn cuối.

Owner: TV3. Task: T1.4 (thay HybridStation).
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.models.control import Command, CommandType
from src.models.events import EventType, StationEvent
from src.models.simulation import Incident, IncidentType, Scenario, SessionOutcome
from src.models.station import (
    ConnectorSpec,
    ConnectorState,
    ConnectorStatus,
    SessionProgress,
    StationConfig,
    StationState,
)
from src.simulator.base import VehicleVisit

logger = logging.getLogger(__name__)
EPS_KWH = 1e-6


@dataclass
class _Port:
    spec: ConnectorSpec
    power_kw: float = 0.0
    booking_id: str | None = None
    fault: bool = False


@dataclass
class _Session:
    visit: VehicleVisit
    arrived_at: datetime
    plugged_in_at: datetime | None = None
    connector_id: str | None = None
    delivered_kwh: float = 0.0
    delivered_by_deadline_kwh: float = 0.0
    finished_at: datetime | None = None


class LiveStation:
    """Cài StationReader + StationActuator (src/simulator/base.py). Một instance = một trạm."""

    def __init__(self, config: StationConfig, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("start phải có múi giờ")
        self.config = config
        self._tz = ZoneInfo(config.timezone)
        self._start = start.astimezone(self._tz)
        self._init(self._start, config.grid_input_limit_kw or config.power_limit_kw)

    def _init(self, now: datetime, available_kw: float) -> None:
        self.now = now
        self.available_power_kw = available_kw
        self.schedule_version = 0
        self._ports = {c.connector_id: _Port(spec=c) for c in self.config.connectors}
        self._visits: dict[str, VehicleVisit] = {}
        self._sessions: dict[str, _Session] = {}  # xe đang ở bãi
        self._queue: list[str] = []  # đã đến, chưa cắm — theo thứ tự đến
        self._history: list[SessionOutcome] = []  # xe đã rời

    # ---- StationReader -------------------------------------------------------------------

    def reset(self, scenario: Scenario) -> StationState:
        start = datetime.combine(self._start.date(), scenario.start_time, tzinfo=self._tz)
        self._init(start, scenario.power_limit_kw)
        return self.state()

    def state(self) -> StationState:
        return StationState(
            timestamp=self.now,
            available_power_kw=self.available_power_kw,
            connectors=[self._connector_state(p) for p in self._ports.values()],
            queue=list(self._queue),
            sessions=[
                SessionProgress(
                    booking_id=s.visit.booking_id,
                    connector_id=s.connector_id,
                    arrived_at=s.arrived_at,
                    plugged_in_at=s.plugged_in_at,
                    delivered_grid_kwh=round(s.delivered_kwh, 6),
                )
                for s in self._sessions.values()
            ],
            schedule_version=self.schedule_version,
        )

    def step(self, minutes: int) -> list[StationEvent]:
        events: list[StationEvent] = []
        dt_h = 1 / 60
        for _ in range(max(minutes, 0)):
            for port in self._ports.values():
                session = self._sessions.get(port.booking_id) if port.booking_id else None
                if session is None or port.power_kw <= 0:
                    continue
                remaining = session.visit.required_kwh - session.delivered_kwh
                energy = min(port.power_kw * dt_h, max(remaining, 0.0))
                session.delivered_kwh += energy
                if self.now < session.visit.departure_time:
                    session.delivered_by_deadline_kwh += energy
                if session.delivered_kwh >= session.visit.required_kwh - EPS_KWH:
                    port.power_kw = 0.0
                    session.finished_at = self.now + timedelta(minutes=1)
            self.now += timedelta(minutes=1)
            events += self._time_events()
        return events

    def inject_incident(self, incident: Incident) -> list[StationEvent]:
        if incident.type == IncidentType.POWER_LIMIT_CHANGE:
            self.available_power_kw = float(incident.new_power_limit_kw)
            return [
                StationEvent(
                    type=EventType.POWER_LIMIT_CHANGED,
                    occurred_at=self.now,
                    new_power_limit_kw=self.available_power_kw,
                    detail=f"Giới hạn nguồn còn {self.available_power_kw:g} kW",
                )
            ]
        port = self._ports.get(incident.connector_id or "")
        if port is None:
            raise ValueError(f"Không có đầu nối {incident.connector_id}")
        if incident.type == IncidentType.CONNECTOR_FAULT:
            port.fault = True
            port.power_kw = 0.0
            booking_id = port.booking_id
            if booking_id and booking_id in self._sessions:
                # Xe bị gián đoạn: rút khỏi cổng lỗi, quay lại ĐẦU hàng chờ để được gán cổng khác.
                session = self._sessions[booking_id]
                session.connector_id = None
                session.plugged_in_at = None
                port.booking_id = None
                self._queue.insert(0, booking_id)
            return [
                StationEvent(
                    type=EventType.CONNECTOR_FAULT,
                    occurred_at=self.now,
                    connector_id=port.spec.connector_id,
                    booking_id=booking_id,
                    detail=f"Đầu nối {port.spec.connector_id} lỗi",
                )
            ]
        port.fault = False
        return [
            StationEvent(
                type=EventType.CONNECTOR_RESTORED,
                occurred_at=self.now,
                connector_id=port.spec.connector_id,
                detail=f"Đầu nối {port.spec.connector_id} hoạt động lại",
            )
        ]

    def upsert_vehicle(self, visit: VehicleVisit) -> list[StationEvent]:
        if visit.booking_id in self._sessions:
            self._sessions[visit.booking_id].visit = visit  # đổi yêu cầu khi xe đang ở bãi
        else:
            self._visits[visit.booking_id] = visit
        return self._time_events()

    def remove_vehicle(self, booking_id: str) -> list[StationEvent]:
        self._visits.pop(booking_id, None)
        if booking_id not in self._sessions:
            return []
        return [self._depart(booking_id, "Huỷ lịch / không còn ở bãi")]

    # ---- StationActuator — CHỈ guard/dispatcher.py gọi ----------------------------------

    def apply_commands(self, commands: Sequence[Command]) -> None:
        for cmd in commands:
            port = self._ports.get(cmd.connector_id)
            if port is None:
                logger.warning("Bỏ qua lệnh %s: không có đầu nối %s", cmd.command_id, cmd.connector_id)
                continue
            if cmd.type == CommandType.ASSIGN_CONNECTOR:
                self._plug(port, cmd)
            elif cmd.type == CommandType.STOP:
                port.power_kw = 0.0
            else:
                self._set_power(port, cmd)
            self.schedule_version = max(self.schedule_version, cmd.based_on_schedule_version + 1)

    # ---- Báo cáo cho KPI (benchmark) ----------------------------------------------------

    def outcomes(self) -> list[SessionOutcome]:
        """Kết cục của mọi xe đã đến (đã rời + còn ở bãi tại lúc gọi)."""
        return [*self._history, *(self._outcome(s) for s in self._sessions.values())]

    # ---- nội bộ --------------------------------------------------------------------------

    def _vehicle_cap(self, port: _Port) -> float:
        session = self._sessions.get(port.booking_id) if port.booking_id else None
        cap = port.spec.max_power_kw
        return min(cap, session.visit.max_power_kw) if session else cap

    def _connector_state(self, port: _Port) -> ConnectorState:
        session = self._sessions.get(port.booking_id) if port.booking_id else None
        if port.fault:
            status = ConnectorStatus.FAULT
        elif session is None:
            status = ConnectorStatus.IDLE
        elif session.finished_at is not None:
            status = ConnectorStatus.FINISHED
        elif port.power_kw >= self._vehicle_cap(port) - 1e-6:
            status = ConnectorStatus.CHARGING
        else:
            status = ConnectorStatus.THROTTLED
        return ConnectorState(
            connector_id=port.spec.connector_id,
            status=status,
            power_kw=round(port.power_kw, 6),
            max_power_kw=port.spec.max_power_kw,
            booking_id=port.booking_id,
        )

    def _plug(self, port: _Port, cmd: Command) -> None:
        booking_id = cmd.booking_id or ""
        session = self._sessions.get(booking_id)
        if session is None or port.fault or (port.booking_id and port.booking_id != booking_id):
            logger.warning("Bỏ qua ASSIGN %s → %s: xe chưa đến hoặc cổng bận/lỗi", booking_id, port.spec.connector_id)
            return
        if session.visit.zone != port.spec.zone:
            logger.warning("Bỏ qua ASSIGN %s: xe vùng %s, cổng vùng %s", booking_id, session.visit.zone, port.spec.zone)
            return
        if session.connector_id and session.connector_id != port.spec.connector_id:
            self._ports[session.connector_id].booking_id = None
            self._ports[session.connector_id].power_kw = 0.0
        port.booking_id = booking_id
        session.connector_id = port.spec.connector_id
        session.plugged_in_at = session.plugged_in_at or self.now
        if booking_id in self._queue:
            self._queue.remove(booking_id)

    def _set_power(self, port: _Port, cmd: Command) -> None:
        if port.fault or port.booking_id is None:
            port.power_kw = 0.0
            return
        session = self._sessions[port.booking_id]
        if session.finished_at is not None:
            port.power_kw = 0.0
            return
        wanted = cmd.power_kw if cmd.power_kw is not None else self._vehicle_cap(port)
        port.power_kw = max(0.0, min(float(wanted), self._vehicle_cap(port)))

    def _time_events(self) -> list[StationEvent]:
        events: list[StationEvent] = []
        for booking_id, visit in list(self._visits.items()):
            if booking_id not in self._sessions and visit.arrival_time <= self.now:
                if visit.departure_time <= self.now:
                    continue  # đến sau giờ rời: không bao giờ có mặt
                self._sessions[booking_id] = _Session(visit=visit, arrived_at=self.now)
                self._queue.append(booking_id)
                del self._visits[booking_id]
                events.append(StationEvent(type=EventType.VEHICLE_ARRIVED, occurred_at=self.now, booking_id=booking_id))
        unplug_delay = timedelta(minutes=self.config.dc_unplug_delay_minutes)
        for booking_id, session in list(self._sessions.items()):
            leave = self.now >= session.visit.departure_time
            if session.finished_at is not None and session.visit.zone == "DC":
                leave = leave or self.now >= session.finished_at + unplug_delay
            if leave:
                events.append(self._depart(booking_id, "Tới giờ rời"))
        return events

    def _depart(self, booking_id: str, reason: str) -> StationEvent:
        session = self._sessions.pop(booking_id)
        connector_id = session.connector_id
        if connector_id:
            port = self._ports[connector_id]
            port.booking_id = None
            port.power_kw = 0.0
        if booking_id in self._queue:
            self._queue.remove(booking_id)
        self._history.append(self._outcome(session))
        return StationEvent(
            type=EventType.VEHICLE_DEPARTED,
            occurred_at=self.now,
            connector_id=connector_id,
            booking_id=booking_id,
            detail=reason,
        )

    def _outcome(self, s: _Session) -> SessionOutcome:
        return SessionOutcome(
            booking_id=s.visit.booking_id,
            accepted=True,
            feasible=True,
            arrival_time=s.arrived_at,
            plug_in_time=s.plugged_in_at,
            deadline=s.visit.departure_time,
            requested_kwh=s.visit.required_kwh,
            delivered_kwh_by_deadline=round(s.delivered_by_deadline_kwh, 6),
        )
