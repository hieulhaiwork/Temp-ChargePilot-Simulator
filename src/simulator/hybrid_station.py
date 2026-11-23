"""HybridStation — trạm backend chạy liên tục, dùng NGUYÊN các thành phần của simulator R&D (src/simulator/src/).

Vì sao tồn tại: nhóm coi HybridSimulator (EV2Gym + QueueController + đường sạc DC) là mô hình vật lý gốc, còn
LiveStation (live.py) là mô hình đơn giản (không taper DC). HybridSimulator chạy trọn kịch bản với dispatch /
optimizer / guard của riêng nó nên không đặt được sau chokepoint Guard của backend (ADR-002). Lớp này tách phần
VẬT LÝ của `HybridSimulator.step` (src/simulator/src/engine/hybrid.py) ra: quyết định gán cổng / công suất đến từ
backend qua `apply_commands` (đã qua Guard), còn hàng chờ, xe đến / rời / rút DC, phản hồi pin, kiểm tra vật lý
là đúng code simulator (QueueController, EV2GymAdapter, safety.guard). Hành vi công khai giống LiveStation
(cùng Protocol StationReader + StationActuator của base.py) để thay thế được nhau.

Nguồn đối chiếu: `HybridSimulator.step` / `_dispatch` / `_observed_vehicles` (hybrid.py). Test
tests/test_simulator/test_hybrid_station.py phát lại quyết định của HybridSimulator trên fixture mvp1 và đòi
năng lượng từng xe khớp 1e-6 kWh ("live = research", ADR-016).

[GIẢ ĐỊNH]
  - Đồng hồ simulator = phút nguyên kể từ `start` của trạm (phút 0), `timestep=1`, `end` rất lớn. Mốc giờ
    đến / rời của VehicleVisit làm tròn LÊN phút (như LiveStation: xe "có mặt" khi now ≥ giờ đến).
  - VehicleVisit thiếu pin: battery_kwh = required_kwh × η_sạc, SOC 0 → 1. Có pin nhưng thiếu SOC: SOC đầu 0,
    target = min(1, SOC đầu + required_kwh × η_sạc / pin).
  - `SessionProgress.delivered_grid_kwh` của backend = năng lượng ĐẦU RA cổng (Σ kW·h, không chia η chuyển đổi),
    theo dõi riêng; `Session.delivered_grid_kwh` của simulator vẫn giữ nghĩa phía lưới (÷ conversion).
  - Xe đạt SOC target trước deadline ⇒ `delivered_kwh_by_deadline = max(thực tế, requested)` vì required_kwh
    (FR3, η mặc định) và SOC target (η của EV2Gym) có thể lệch nhau chút do hiệu suất.
  - Setpoint giữ tới lệnh sau; công suất thực = min(setpoint, cổng, acceptance của xe) — xe tự giới hạn theo
    đường sạc là vật lý, không phải lỗi. Vi phạm guard vật lý sau mỗi phút chỉ đếm + log, KHÔNG raise (trạm live
    không được chết); HybridSimulator thì raise.
  - Lỗi cổng: xe đang cắm bị rút, về ĐẦU hàng chờ (như LiveStation), `charge_started` xoá.
  - Không hỗ trợ đổi cổng cho xe đang cắm (ASSIGN xe không ở QUEUED bị bỏ qua) — QueueController không có thao tác này.
  - Xe đã rời mà upsert lại ⇒ bỏ qua (log).

Chưa làm: profile DC VinFast (`VehicleProfilesDCModel` cần biết xe từ trước, `from_scenario`) — TODO: truyền
`dc_model` tự dựng nếu cần. Không hỗ trợ limit_events / tariff của Scenario simulator (backend tự xử lý giá).
"""

import functools
import logging
import math
import threading
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo

from src.models.control import Command, CommandType
from src.models.events import EventType, StationEvent
from src.models.simulation import Incident, IncidentType, SessionOutcome
from src.models.simulation import Scenario as BackendScenario
from src.models.station import ConnectorState, ConnectorStatus, SessionProgress, StationConfig, StationState
from src.simulator.base import VehicleVisit
from src.simulator.src.charging_models.base import DCChargingModel
from src.simulator.src.charging_models.synthetic_dc import SyntheticTaperV1
from src.simulator.src.dispatch.base import DispatchObservation
from src.simulator.src.engine.ev2gym_adapter import EV2GymAdapter
from src.simulator.src.engine.queue import QueueController, Session
from src.simulator.src.observations import Candidate, SchedulingObservation, VehicleObservation
from src.simulator.src.safety.constraints import ConstraintViolationError
from src.simulator.src.safety.guard import guard, validate_response
from src.simulator.src.safety.limits import EffectiveLimits, effective_limits
from src.simulator.src.scenario import Cabinet, Scenario, Vehicle

logger = logging.getLogger(__name__)
EPS = 1e-6
SOC_TOL = 1e-10  # cùng ngưỡng hoàn thành của HybridSimulator.step
END_MINUTE = 10**9  # "end rất lớn" — trạm live không có chân trời


def _locked(method):
    """Mọi thao tác đọc / ghi trạng thái trạm chạy dưới `self.lock`.

    Vì sao: control_loop giải lịch trên thread solver (services/solver.py) và bộ lập lịch simulator đọc thẳng trạm,
    trong khi request khác có thể gọi `sync_clock()` → `step()` trên event loop. RLock để các hàm gọi lồng nhau được.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)

    return wrapper


def _ceil_minutes(delta: timedelta) -> int:
    return math.ceil(delta.total_seconds() / 60 - 1e-9)


class HybridStation:
    """Cài StationReader + StationActuator (src/simulator/base.py) trên mô hình vật lý của HybridSimulator."""

    def __init__(self, config: StationConfig, start: datetime, dc_model: DCChargingModel | None = None) -> None:
        if start.tzinfo is None:
            raise ValueError("start phải có múi giờ")
        self.config = config
        self.lock = threading.RLock()
        self._tz = ZoneInfo(config.timezone)
        self._dc_model = dc_model
        self._connector_to_port: dict[str, str] = {}
        self._port_to_connector: dict[str, str] = {}
        self._cabinets = self._build_cabinets(config)
        self._init(start.astimezone(self._tz), config.grid_input_limit_kw or config.power_limit_kw)

    @classmethod
    def with_vinfast_profiles(cls, *args, **kwargs) -> "HybridStation":
        # TODO: VehicleProfilesDCModel.from_scenario cần danh sách xe từ trước; trạm live nhận xe dần.
        raise NotImplementedError("Profile DC VinFast chưa nối vào HybridStation — truyền dc_model tự dựng")

    # ---- dựng Scenario simulator từ StationConfig ----------------------------------------

    def _build_cabinets(self, config: StationConfig) -> tuple[Cabinet, ...]:
        cabinets = []
        specs = config.cabinets or []
        if not specs:
            raise ValueError("HybridStation cần StationConfig.cabinets (topology ADR-010)")
        for cab in specs:
            conns = [c for c in config.connectors if c.cabinet_id == cab.cabinet_id]
            if not conns:
                raise ValueError(f"Tủ {cab.cabinet_id} không có đầu nối")
            port_kw = {c.max_power_kw for c in conns}
            if len(port_kw) != 1:
                raise ValueError(f"Các đầu nối của tủ {cab.cabinet_id} phải cùng max_power_kw: {sorted(port_kw)}")
            for index, conn in enumerate(conns):
                port = f"{cab.cabinet_id}/P{index + 1}"
                self._connector_to_port[conn.connector_id] = port
                self._port_to_connector[port] = conn.connector_id
            cabinets.append(Cabinet(cab.cabinet_id, str(cab.zone), len(conns), port_kw.pop(), cab.output_limit_kw))
        orphans = [c.connector_id for c in config.connectors if c.connector_id not in self._connector_to_port]
        if orphans:
            raise ValueError(f"Đầu nối không thuộc tủ nào: {orphans}")
        return tuple(cabinets)

    def _build_scenario(self) -> Scenario:
        cfg = self.config
        zones = ("AC", "DC")
        by_zone = {z: sum(c.output_kw for c in self._cabinets if c.zone == z) for z in zones}
        budgets = {str(k): v for k, v in (cfg.zone_budgets_kw or {}).items()}
        physical = {str(k): v for k, v in cfg.physical_zone_cap_kw.items()} if cfg.physical_zone_cap_kw else None
        zone_kw = {z: budgets.get(z, (physical or by_zone).get(z, by_zone[z])) for z in zones}
        independent = cfg.independent_grid_input_limit_kw
        return Scenario(
            id=f"live-{cfg.station_id}",
            start=0,
            end=END_MINUTE,
            timestep=1,
            delay=cfg.dc_unplug_delay_minutes,
            conversion=cfg.power_conversion_efficiency,
            efficiency=cfg.default_charging_efficiency,
            grid_kw=cfg.grid_input_limit_kw or cfg.power_limit_kw,
            zone_kw=zone_kw,
            cabinets=self._cabinets,
            vehicles=(),
            physical_zone_cap_kw=physical,
            independent_grid_input_limit_kw={str(k): v for k, v in independent.items()} if independent else None,
        )

    def _init(self, start: datetime, available_kw: float) -> None:
        self._start = start
        self.now = start
        self.available_power_kw = available_kw
        self.schedule_version = 0
        self.scenario = self._build_scenario()
        self.queue = QueueController(self.scenario)
        self.adapter = EV2GymAdapter(self.scenario, self._dc_model or SyntheticTaperV1())
        self._faults: set[str] = set()  # port simulator đang lỗi
        self._setpoint: dict[str, float] = {}  # vid → kW đầu ra (giữ tới lệnh sau)
        self._visits: dict[str, VehicleVisit] = {}
        self._output_kwh: dict[str, float] = {}  # năng lượng đầu ra cổng (nghĩa backend)
        self._output_by_deadline_kwh: dict[str, float] = {}
        self.applied_constraint_violation_count = 0
        self._events: list[StationEvent] = []

    # ---- tiện ích ánh xạ ------------------------------------------------------------------

    @property
    def minute(self) -> int:
        # now = start + số phút nguyên (step tiến từng phút) → phép chia luôn ra số nguyên; round chỉ khử sai số float.
        return round((self.now - self._start).total_seconds() / 60)

    def _at(self, minute: int) -> datetime:
        return self._start + timedelta(minutes=minute)

    def port_of(self, connector_id: str) -> str:
        return self._connector_to_port[connector_id]

    def connector_of(self, port: str) -> str:
        return self._port_to_connector[port]

    @_locked
    def effective_limits(self) -> EffectiveLimits:
        return replace(effective_limits(self.scenario, self.minute), grid_input_kw=self.available_power_kw)

    # ---- StationReader -------------------------------------------------------------------

    @_locked
    def reset(self, scenario: BackendScenario) -> StationState:
        start = datetime.combine(self._start.date(), scenario.start_time, tzinfo=self._tz)
        self._init(start, scenario.power_limit_kw)
        return self.state()

    @_locked
    def state(self) -> StationState:
        sessions = []
        queued = [vid for zone in self.queue.waiting.values() for vid in zone]
        for vid, s in self.queue.sessions.items():
            if s.state in ("NOT_ARRIVED", "DEPARTED"):
                continue
            sessions.append(
                SessionProgress(
                    booking_id=vid,
                    connector_id=self.connector_of(s.connector) if s.connector else None,
                    arrived_at=self._at(s.vehicle.arrival),
                    plugged_in_at=self._at(s.charge_started) if s.connector and s.charge_started is not None else None,
                    delivered_grid_kwh=round(self._output_kwh.get(vid, 0.0), 6),
                )
            )
        return StationState(
            timestamp=self.now,
            available_power_kw=self.available_power_kw,
            connectors=[self._connector_state(c.connector_id) for c in self.config.connectors],
            queue=queued,  # [GIẢ ĐỊNH] hàng AC rồi hàng DC, mỗi hàng giữ thứ tự của QueueController
            sessions=sessions,
            schedule_version=self.schedule_version,
        )

    @_locked
    def step(self, minutes: int) -> list[StationEvent]:
        self._events = []
        for _ in range(max(minutes, 0)):
            self._charge_one_minute()
            self.now += timedelta(minutes=1)
            self.queue.advance(self.minute, self.scenario, self.adapter, self._emit)
        return self._drain()

    @_locked
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
        connector_id = incident.connector_id or ""
        if connector_id not in self._connector_to_port:
            raise ValueError(f"Không có đầu nối {incident.connector_id}")
        port = self.port_of(connector_id)
        if incident.type == IncidentType.CONNECTOR_FAULT:
            self._faults.add(port)
            vid = self.queue.occupied.get(port)
            if vid is not None:
                # Xe bị gián đoạn: rút khỏi cổng lỗi, quay lại ĐẦU hàng chờ để được gán cổng khác.
                cab, index = self.queue.connectors[port]
                self.adapter.disconnect(vid, cab.id, index)
                del self.queue.occupied[port]
                session = self.queue.sessions[vid]
                session.connector = None
                session.charge_started = None
                session.state = "QUEUED"
                self.queue.waiting[cab.zone].appendleft(vid)
                self._setpoint.pop(vid, None)
            return [
                StationEvent(
                    type=EventType.CONNECTOR_FAULT,
                    occurred_at=self.now,
                    connector_id=connector_id,
                    booking_id=vid,
                    detail=f"Đầu nối {connector_id} lỗi",
                )
            ]
        self._faults.discard(port)
        return [
            StationEvent(
                type=EventType.CONNECTOR_RESTORED,
                occurred_at=self.now,
                connector_id=connector_id,
                detail=f"Đầu nối {connector_id} hoạt động lại",
            )
        ]

    @_locked
    def upsert_vehicle(self, visit: VehicleVisit) -> list[StationEvent]:
        self._events = []
        vid = visit.booking_id
        now = self.minute
        session = self.queue.sessions.get(vid)
        departure = _ceil_minutes(visit.departure_time - self._start)
        if session is not None and session.state == "DEPARTED":
            logger.warning("Bỏ qua upsert %s: xe đã rời bãi", vid)
            return []
        if session is not None and session.state != "NOT_ARRIVED":
            self._update_present(session, visit, departure)
        else:
            arrival = max(_ceil_minutes(visit.arrival_time - self._start), now)
            if departure <= arrival:
                self._forget(vid)  # đến sau giờ rời: không bao giờ có mặt
                return []
            vehicle = self._vehicle(visit, arrival, departure)
            self.queue.sessions[vid] = Session(vehicle)
            self.adapter.models[vid] = EV2GymAdapter._vehicle(vehicle, self.scenario)
            self._visits[vid] = visit
        self.queue.advance(now, self.scenario, self.adapter, self._emit)
        return self._drain()

    @_locked
    def remove_vehicle(self, booking_id: str) -> list[StationEvent]:
        session = self.queue.sessions.get(booking_id)
        if session is None or session.state == "DEPARTED":
            return []
        if session.state == "NOT_ARRIVED":
            self._forget(booking_id)
            return []
        port = session.connector
        if port is None:
            self.queue.waiting[session.vehicle.zone].remove(booking_id)
        else:
            cab, index = self.queue.connectors[port]
            self.adapter.disconnect(booking_id, cab.id, index)
            del self.queue.occupied[port]
        session.connector = None
        session.state = "DEPARTED"
        session.departed_at = self.minute
        self._setpoint.pop(booking_id, None)
        return [
            StationEvent(
                type=EventType.VEHICLE_DEPARTED,
                occurred_at=self.now,
                connector_id=self.connector_of(port) if port else None,
                booking_id=booking_id,
                detail="Huỷ lịch / không còn ở bãi",
            )
        ]

    # ---- StationActuator — CHỈ guard/dispatcher.py gọi ----------------------------------

    @_locked
    def apply_commands(self, commands: Sequence[Command]) -> None:
        for cmd in commands:
            port = self._connector_to_port.get(cmd.connector_id)
            if port is None:
                logger.warning("Bỏ qua lệnh %s: không có đầu nối %s", cmd.command_id, cmd.connector_id)
                continue
            if cmd.type == CommandType.ASSIGN_CONNECTOR:
                self._assign(port, cmd.booking_id or "")
            else:
                vid = self.queue.occupied.get(port)
                if vid is not None:
                    cab, _ = self.queue.connectors[port]
                    if cmd.type == CommandType.STOP or port in self._faults:
                        wanted = 0.0
                    else:
                        wanted = cab.port_kw if cmd.power_kw is None else float(cmd.power_kw)
                    self._setpoint[vid] = max(0.0, min(wanted, cab.port_kw))
            self.schedule_version = max(self.schedule_version, cmd.based_on_schedule_version + 1)

    # ---- Báo cáo cho KPI (benchmark) ----------------------------------------------------

    @_locked
    def outcomes(self) -> list[SessionOutcome]:
        """Kết cục của mọi xe đã đến (đã rời + còn ở bãi tại lúc gọi)."""
        rows = []
        for vid, s in self.queue.sessions.items():
            if s.state == "NOT_ARRIVED":
                continue
            visit = self._visits[vid]
            delivered = self._output_by_deadline_kwh.get(vid, 0.0)
            if s.completed_at is not None and s.completed_at <= s.vehicle.departure:
                delivered = max(delivered, visit.required_kwh)  # [GIẢ ĐỊNH] đạt SOC target = giao đủ
            rows.append(
                SessionOutcome(
                    booking_id=vid,
                    accepted=True,
                    feasible=True,
                    arrival_time=self._at(s.vehicle.arrival),
                    plug_in_time=self._at(s.charge_started) if s.charge_started is not None else None,
                    deadline=visit.departure_time,
                    requested_kwh=visit.required_kwh,
                    delivered_kwh_by_deadline=round(delivered, 6),
                )
            )
        return rows

    # ---- API đọc cho tầng lập lịch -------------------------------------------------------

    def _observed_vehicles(self) -> MappingProxyType:
        return MappingProxyType(
            {
                vid: VehicleObservation(
                    s.vehicle, s.state, self.adapter.soc(vid), s.connector, s.charge_started, s.completed_at
                )
                for vid, s in self.queue.sessions.items()
                if s.state != "NOT_ARRIVED"
            }
        )

    def _candidates(self, minutes: int) -> dict[str, Candidate]:
        candidates = {}
        for port, vid in self.queue.occupied.items():
            session = self.queue.sessions[vid]
            if session.state == "CHARGING":
                cab, _ = self.queue.connectors[port]
                candidates[vid] = Candidate(cab, min(cab.port_kw, self.adapter.acceptance_kw(session.vehicle, minutes)))
        return candidates

    @_locked
    def scheduling_observation(self, interval_minutes: int = 1) -> SchedulingObservation:
        """Snapshot giống `HybridSimulator.step` (sau dispatch) cho optimizer / coordinator của simulator."""
        vehicles = self._observed_vehicles()
        return SchedulingObservation(
            scenario=replace(self.scenario, vehicles=tuple(row.vehicle for row in vehicles.values())),
            minute=self.minute,
            interval_minutes=interval_minutes,
            vehicles=vehicles,
            queues=MappingProxyType({zone: tuple(q) for zone, q in self.queue.waiting.items()}),
            ports=MappingProxyType({port: self.queue.occupied.get(port) for port in self.queue.connectors}),
            candidates=MappingProxyType(self._candidates(interval_minutes)),
            dc_charging_model=self.adapter.dc_model,
            effective_limits=self.effective_limits(),
        )

    @_locked
    def dispatch_observation(self, zone: str) -> DispatchObservation:
        """Giống `HybridSimulator._dispatch` cho một vùng; cổng lỗi không tính là cổng trống."""
        effective = self.effective_limits()
        limits = {
            port: min(cab.port_kw, effective.cabinet_output_kw[cab.id], effective.zone_capacity_kw(zone))
            for port, (cab, _) in self.queue.connectors.items()
            if cab.zone == zone
        }
        empty = tuple(p for p in limits if p not in self.queue.occupied and p not in self._faults)
        return DispatchObservation(
            self.minute,
            zone,
            empty,
            tuple(self.queue.waiting[zone]),
            self._observed_vehicles(),
            MappingProxyType(limits),
            self.scenario.efficiency,
        )

    # ---- nội bộ --------------------------------------------------------------------------

    def _vehicle(self, visit: VehicleVisit, arrival: int, departure: int) -> Vehicle:
        eta = self.scenario.efficiency
        if visit.battery_kwh is None:
            battery, initial, target = visit.required_kwh * eta, 0.0, 1.0
        else:
            battery = visit.battery_kwh
            initial = visit.soc_now if visit.soc_now is not None else 0.0
            target = visit.soc_target
            if target is None:
                target = min(1.0, initial + visit.required_kwh * eta / battery)
        return Vehicle(
            visit.booking_id,
            visit.zone,
            arrival,
            departure,
            battery,
            initial,
            target,
            visit.max_power_kw,
            visit.vehicle_model,
        )

    def _update_present(self, session: Session, visit: VehicleVisit, departure: int) -> None:
        """Xe đã ở bãi: chỉ đổi giờ rời / target (Vehicle frozen ⇒ replace, cập nhật EV model)."""
        old = session.vehicle
        fresh = self._vehicle(visit, old.arrival, departure)
        vehicle = replace(
            old,
            departure=max(departure, self.minute),
            target=fresh.target if visit.soc_target is not None else old.target,
            max_kw=visit.max_power_kw,
        )
        session.vehicle = vehicle
        ev = self.adapter.models[visit.booking_id]
        ev.desired_capacity = vehicle.target * vehicle.battery_kwh
        ev.time_of_departure = vehicle.departure - self.scenario.start
        if vehicle.zone == "AC":
            ev.max_ac_charge_power = vehicle.max_kw
        else:
            ev.max_dc_charge_power = vehicle.max_kw
        if session.state == "FINISHED" and self.adapter.soc(visit.booking_id) < vehicle.target - SOC_TOL:
            session.state, session.completed_at = "CHARGING", None
        self._visits[visit.booking_id] = visit

    def _forget(self, vid: str) -> None:
        self.queue.sessions.pop(vid, None)
        self.adapter.models.pop(vid, None)
        self._visits.pop(vid, None)

    def _assign(self, port: str, vid: str) -> None:
        session = self.queue.sessions.get(vid)
        cab, _ = self.queue.connectors[port]
        if session is not None and session.connector == port:
            return  # gán lại đúng cổng đang cắm: không đổi gì
        if (
            session is None
            or session.state != "QUEUED"
            or port in self._faults
            or port in self.queue.occupied
            or session.vehicle.zone != cab.zone
        ):
            logger.warning(
                "Bỏ qua ASSIGN %s → %s: xe không chờ / cổng bận, lỗi / khác vùng", vid, self._port_to_connector[port]
            )
            return
        self.queue.connect(self.minute, {port: vid}, self.adapter, self._emit)

    def _charge_one_minute(self) -> None:
        """Một phút vật lý — đúng thứ tự của HybridSimulator.step (sau dispatch)."""
        when = self.minute
        cfg = self.scenario
        try:
            candidates = self._candidates(1)
        except ConstraintViolationError as exc:
            self._violation(exc)
            return
        actual: dict[str, float] = {}
        for vid, candidate in candidates.items():
            s = self.queue.sessions[vid]
            setpoint = min(self._setpoint.get(vid, 0.0), candidate.allowed_kw)
            before = self.adapter.soc(vid)
            try:
                response = self.adapter.step(vid, candidate.cabinet.id, setpoint, 1)
                soc = self.adapter.soc(vid)
                kw, energy = response.actual_output_kw, response.battery_kwh
                validate_response(cfg, s.vehicle, 1, setpoint, before, soc, kw, energy)
            except ConstraintViolationError as exc:
                self._violation(exc)
                continue
            actual[vid] = max(0.0, kw)
            output_kwh = actual[vid] / 60
            s.delivered_battery_kwh += max(0.0, energy)
            s.delivered_grid_kwh += output_kwh / cfg.conversion  # nghĩa simulator (phía lưới)
            self._output_kwh[vid] = self._output_kwh.get(vid, 0.0) + output_kwh
            if when < s.vehicle.departure:
                self._output_by_deadline_kwh[vid] = self._output_by_deadline_kwh.get(vid, 0.0) + output_kwh
            if soc >= s.vehicle.target - SOC_TOL:
                s.state = "FINISHED"
                s.completed_at = when + 1
                self._emit(when + 1, "CHARGE_COMPLETED", s.vehicle, connector=s.connector)
        limits = self.effective_limits()
        try:
            guard(cfg, candidates, actual, limits.zone_output_kw, limits=limits)
        except ConstraintViolationError as exc:
            self._violation(exc)

    def _violation(self, exc: Exception) -> None:
        self.applied_constraint_violation_count += 1
        logger.error("HybridStation vi phạm ràng buộc vật lý lúc %s: %s", self.now.isoformat(), exc)

    def _emit(self, when: int, kind: str, v: Vehicle, **metadata) -> None:
        """Dịch sự kiện simulator → StationEvent như LiveStation phát (chỉ xe đến / rời)."""
        port = metadata.get("connector")
        connector_id = self._port_to_connector.get(port) if port else None
        if kind == "ARRIVED":
            event_type, detail = EventType.VEHICLE_ARRIVED, ""
        elif kind in ("UNPLUGGED", "LEFT_QUEUE"):
            event_type = EventType.VEHICLE_DEPARTED
            detail = "Tới giờ rời" if metadata.get("reason") == "declared_departure" else "Xe DC rút sau khi đầy"
            self._setpoint.pop(v.id, None)
        else:
            return  # PLUGGED_IN / CHARGE_COMPLETED: LiveStation không phát sự kiện tương ứng
        self._events.append(
            StationEvent(
                type=event_type, occurred_at=self._at(when), connector_id=connector_id, booking_id=v.id, detail=detail
            )
        )

    def _drain(self) -> list[StationEvent]:
        events, self._events = self._events, []
        return events

    def _connector_state(self, connector_id: str) -> ConnectorState:
        port = self.port_of(connector_id)
        cab, _ = self.queue.connectors[port]
        vid = self.queue.occupied.get(port)
        session = self.queue.sessions.get(vid) if vid else None
        power = 0.0
        if port in self._faults:
            status = ConnectorStatus.FAULT
        elif session is None:
            status = ConnectorStatus.IDLE
        elif session.state == "FINISHED":
            status = ConnectorStatus.FINISHED
        else:
            allowed = min(cab.port_kw, self.adapter.acceptance_kw(session.vehicle, 1))
            power = min(self._setpoint.get(vid, 0.0), allowed)
            cap = min(cab.port_kw, session.vehicle.max_kw)
            status = ConnectorStatus.CHARGING if power >= cap - EPS else ConnectorStatus.THROTTLED
        return ConnectorState(
            connector_id=connector_id,
            status=status,
            power_kw=round(power, 6),
            max_power_kw=cab.port_kw,
            booking_id=vid,
        )
