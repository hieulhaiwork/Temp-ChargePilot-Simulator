"""HybridStation — trạm backend chạy liên tục trên CÙNG kernel với HybridSimulator (ADR-019 Phase 3).

Vì sao tồn tại: backend cần một trạm sống lâu, nhận lệnh đã qua Guard (ADR-002) và nhận dữ kiện môi trường dần dần
(booking, sự cố). Lớp này chỉ là adapter: mọi trạng thái vật lý, vòng tích phân (Physical Core) và lập kế hoạch
(Planning Core) nằm trong `StationKernel` (src/simulator/core/kernel.py), dùng chung với simulator standalone.
Ở đây chỉ còn: dịch StationConfig ↔ Scenario, booking ↔ Vehicle, Command → primitive của kernel, sự kiện simulator →
StationEvent, StationState / SessionOutcome cho backend.

Thời gian (P1, docs/refactor/PHASE3_DESIGN.md §2): `physics_step_minutes = 1`, `decision_interval_minutes =
optimizer.planning_step_minutes` (15). Chỉ `guard/dispatcher.py` được gọi `apply_commands`; bản fork (admission) nhận
quyết định đã duyệt qua `apply_approved`.

[GIẢ ĐỊNH]
  - Đồng hồ = phút nguyên kể từ `start` của trạm (phút 0), `end` rất lớn. Giờ đến / rời của VehicleVisit làm tròn LÊN
    phút (xe "có mặt" khi now ≥ giờ đến).
  - VehicleVisit thiếu pin: battery_kwh = required_kwh × η_sạc, SOC 0 → 1. Có pin nhưng thiếu SOC: SOC đầu 0,
    target = min(1, SOC đầu + required_kwh × η_sạc / pin).
  - `SessionProgress.delivered_grid_kwh` = năng lượng ĐẦU RA cổng (kernel.output_kwh); `Session.delivered_grid_kwh`
    của simulator giữ nghĩa phía lưới (÷ conversion).
  - Xe đạt SOC target trước deadline ⇒ `delivered_kwh_by_deadline = max(thực tế, requested)` (FR3 ↔ η EV2Gym).
  - Setpoint giữ tới lệnh sau; công suất thực = min(setpoint, cổng, acceptance 1'). Vi phạm sau khi áp chỉ đếm + log
    (trạm live không được chết); HybridSimulator thì raise.
  - Lỗi cổng: xe đang cắm bị rút, về ĐẦU hàng chờ, `charge_started` xoá. Không đổi cổng cho xe đang cắm.
  - Xe đã rời mà upsert lại ⇒ bỏ qua (log).

Chưa làm: profile DC VinFast (`VehicleProfilesDCModel` cần biết xe từ trước).
"""

import copy
import functools
import logging
import math
import threading
from collections import deque
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo

from src.models.charging_physics import DCChargingModel
from src.models.control import Command, CommandType
from src.models.decisions import AppliedResult, ApprovedDecision, TimeConfig
from src.models.events import EventType, StationEvent
from src.models.physical_limits import EffectiveLimits
from src.models.scheduling.observations import SchedulingObservation
from src.models.simulation import Incident, IncidentType, SessionOutcome
from src.models.simulation import Scenario as BackendScenario
from src.models.simulation_core import Cabinet, Scenario, Vehicle
from src.models.station import ConnectorState, ConnectorStatus, SessionProgress, StationConfig, StationState
from src.models.station_protocols import VehicleVisit
from src.simulator.core.algorithms import Algorithms, algorithm_labels, default_algorithms
from src.simulator.core.charging_models.synthetic_dc import SyntheticTaperV1
from src.simulator.core.ev2gym_adapter import EV2GymAdapter
from src.simulator.core.kernel import SOC_TOL, StationKernel
from src.simulator.core.queue import QueueController, Session
from src.simulator.evaluation.trace import decision_record

logger = logging.getLogger(__name__)
EPS = 1e-6
APPLIED_BUFFER_STEPS = 24 * 60  # tối đa một ngày bước 1' giữa hai lần drain (vòng nền drain ≤ 15')
# Độ phân giải lệnh công suất: control_loop.diff_commands không gửi lệnh khi đổi < POWER_TOL_KW (khoá bằng test).
COMMAND_RESOLUTION_KW = 0.01
END_MINUTE = 10**9  # "end rất lớn" — trạm live không có chân trời


def _locked(method):
    """Mọi thao tác đọc / ghi trạng thái trạm chạy dưới `self.lock`.

    Vì sao: control_loop giải lịch trên thread solver (services/solver.py) và bộ lập lịch đọc thẳng kernel, trong khi
    request khác có thể gọi `sync_clock()` → `step()` trên event loop. RLock để các hàm gọi lồng nhau được.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)

    return wrapper


def _ceil_minutes(delta: timedelta) -> int:
    return math.ceil(delta.total_seconds() / 60 - 1e-9)


class HybridStation:
    """StationReader + StationActuator (src/models/station_protocols.py) trên `StationKernel`."""

    def __init__(
        self,
        config: StationConfig,
        start: datetime,
        dc_model: DCChargingModel | None = None,
        *,
        algorithms: Algorithms | None = None,
        policy_id: str = "custom",
        policy_version: str = "1",
    ) -> None:
        if start.tzinfo is None:
            raise ValueError("start phải có múi giờ")
        self.config = config
        self.lock = threading.RLock()
        self.is_fork = False
        self._tz = ZoneInfo(config.timezone)
        self._dc_model = dc_model
        self._algorithms = algorithms
        self._policy = (policy_id, policy_version)
        self._connector_to_port: dict[str, str] = {}
        self._port_to_connector: dict[str, str] = {}
        self._cabinets = self._build_cabinets(config)
        self.time = TimeConfig(physics_step_minutes=1, decision_interval_minutes=config.optimizer.planning_step_minutes)
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
        self.schedule_version = 0
        scenario = self._build_scenario()
        adapter = EV2GymAdapter(scenario, self._dc_model or SyntheticTaperV1())
        algorithms = self._algorithms or replace(default_algorithms(), dc_charging_model=adapter.dc_model)
        self.kernel = StationKernel(
            scenario,
            adapter,
            QueueController(scenario),
            algorithms,
            time=self.time,
            strict=False,
            policy_id=self._policy[0],
            policy_version=self._policy[1],
            emit=self._emit,
        )
        self.kernel.command_resolution_kw = COMMAND_RESOLUTION_KW
        self.available_power_kw = available_kw
        self._visits: dict[str, VehicleVisit] = {}
        self._events: list[StationEvent] = []
        # Kết quả từng bước vật lý từ lần drain trước — DecisionTrace backend đóng quyết định bằng số đo thật.
        self._applied: deque[AppliedResult] = deque(maxlen=APPLIED_BUFFER_STEPS)

    def configure(self, algorithms: Algorithms, policy_id: str, policy_version: str = "1") -> None:
        """Chọn policy (thuật toán) cho Planning Core của kernel — composition root gọi một lần."""
        with self.lock:
            self._algorithms = algorithms
            self._policy = (policy_id, policy_version)
            self.kernel.algorithms = algorithms
            self.kernel.policy_id, self.kernel.policy_version = policy_id, policy_version

    # ---- tiện ích ánh xạ ------------------------------------------------------------------

    @property
    def scenario(self) -> Scenario:
        return self.kernel.scenario

    @property
    def queue(self) -> QueueController:
        return self.kernel.queue

    @property
    def adapter(self) -> EV2GymAdapter:
        return self.kernel.adapter

    @property
    def applied_constraint_violation_count(self) -> int:
        return self.kernel.applied_constraint_violation_count

    @property
    def available_power_kw(self) -> float:
        return self._available_power_kw

    @available_power_kw.setter
    def available_power_kw(self, value: float) -> None:
        self._available_power_kw = float(value)
        self.kernel.grid_input_override_kw = float(value)

    @property
    def minute(self) -> int:
        return self.kernel.now

    @property
    def now(self) -> datetime:
        return self._at(self.kernel.now)

    def _at(self, minute: int) -> datetime:
        return self._start + timedelta(minutes=minute)

    def minute_of(self, when: datetime) -> int:
        return _ceil_minutes(when - self._start)

    def port_of(self, connector_id: str) -> str:
        return self._connector_to_port[connector_id]

    def connector_of(self, port: str) -> str:
        return self._port_to_connector[port]

    @_locked
    def effective_limits(self) -> EffectiveLimits:
        return self.kernel.effective_limits()

    @property
    def next_decision_at(self) -> datetime | None:
        """Mốc boundary của quyết định gần nhất (TOU, xe đến / rời, rút DC, trần 15') — runtime phát TICK ở đây."""
        minute = self.kernel.next_decision_minute
        return None if minute is None else self._at(minute)

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
                    delivered_grid_kwh=round(self.kernel.output_kwh.get(vid, 0.0), 6),
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
        """Physical Core của kernel, từng bước vật lý 1'; sau mỗi bước xử lý xe đến / rời / rút DC."""
        self._events = []
        kernel = self.kernel
        for _ in range(max(minutes, 0)):
            result = kernel.advance(kernel.now + 1)
            self._applied.append(result)
            if result.budget_deviation_kw and not kernel._deviation_reported:
                # Assigned budget (Coordinator) ≠ hard cap: vượt budget không phải vi phạm vật lý — ghi + tính lại một lần.
                kernel._deviation_reported = True
                detail = ", ".join(f"{zone} +{kw:.3f} kW" for zone, kw in sorted(result.budget_deviation_kw.items()))
                self._events.append(
                    StationEvent(
                        type=EventType.REPLAN_REQUESTED,
                        occurred_at=self._at(result.end),
                        detail=f"Công suất thực vượt budget vùng ({detail})",
                    )
                )
            kernel.observe()
        return self._drain()

    @_locked
    def inject_incident(self, incident: Incident) -> list[StationEvent]:
        if incident.type == IncidentType.POWER_LIMIT_CHANGE:
            self.available_power_kw = float(incident.new_power_limit_kw)
            self.kernel.state_version += 1
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
            vid = self.kernel.fault_port(port)
            return [
                StationEvent(
                    type=EventType.CONNECTOR_FAULT,
                    occurred_at=self.now,
                    connector_id=connector_id,
                    booking_id=vid,
                    detail=f"Đầu nối {connector_id} lỗi",
                )
            ]
        self.kernel.restore_port(port)
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
        self.kernel.state_version += 1
        self.kernel.observe()
        return self._drain()

    @_locked
    def remove_vehicle(self, booking_id: str) -> list[StationEvent]:
        session = self.queue.sessions.get(booking_id)
        if session is None or session.state == "DEPARTED":
            return []
        if session.state == "NOT_ARRIVED":
            self._forget(booking_id)
            return []
        port = self.kernel.withdraw(booking_id)
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
                    if cmd.type == CommandType.STOP or port in self.kernel.faults:
                        wanted = 0.0
                    else:
                        wanted = cab.port_kw if cmd.power_kw is None else float(cmd.power_kw)
                    self.kernel.hold_setpoint(vid, max(0.0, min(wanted, cab.port_kw)))
            self.schedule_version = max(self.schedule_version, cmd.based_on_schedule_version + 1)

    # ---- bản fork cho admission (quote / booking) --------------------------------------

    @_locked
    def fork(self) -> "HybridStation":
        """Bản sao (EV2Gym, queue, setpoint, cổng lỗi, nguồn) để chạy what-if — trạm này không đổi."""
        twin = copy.copy(self)
        twin.lock = threading.RLock()
        twin.is_fork = True
        twin._visits = dict(self._visits)
        twin._events = []
        twin._applied = deque(maxlen=APPLIED_BUFFER_STEPS)
        twin.kernel = self.kernel.fork(emit=twin._emit)
        return twin

    def apply_approved(self, approved: ApprovedDecision) -> None:
        """Áp quyết định đã duyệt THẲNG vào kernel — chỉ cho bản fork; trạm thật chỉ nhận lệnh qua dispatcher."""
        if not self.is_fork:
            raise RuntimeError("apply_approved chỉ dùng cho bản fork (admission); trạm thật đi guard/dispatcher.py")
        with self.lock:
            self.kernel.apply_approved(approved)

    # ---- DecisionTrace (ADR-019 Phase 4, quyết định 6) ----------------------------------

    @_locked
    def drain_applied(self) -> list[AppliedResult]:
        """Kết quả các bước vật lý từ lần gọi trước (rồi xoá) — để đóng DecisionTrace của quyết định đang hiệu lực."""
        results, self._applied = list(self._applied), deque(maxlen=APPLIED_BUFFER_STEPS)
        return results

    @_locked
    def decision_facts(self, approved: ApprovedDecision, results: Sequence[AppliedResult]) -> dict:
        """Facts của một quyết định theo ĐÚNG schema DecisionTrace của simulator (`evaluation/trace.decision_record`).

        `results`: các bước vật lý đã chạy dưới quyết định này. Công suất thực = trung bình theo thời gian, năng lượng
        nạp = tổng; khoảng = số phút thực sự chạy (quyết định có thể bị thay sớm bởi sự kiện). Chưa chạy phút nào thì
        giữ khoảng đã lập kế hoạch và công suất thực 0.
        """
        proposal = approved.proposal
        minutes = sum(r.end - r.minute for r in results)
        kw_minutes: dict[str, float] = {}
        stored: dict[str, float] = {}
        for result in results:
            for vid, kw in result.actual_kw.items():
                kw_minutes[vid] = kw_minutes.get(vid, 0.0) + kw * (result.end - result.minute)
            for vid, kwh in result.stored_kwh.items():
                stored[vid] = stored.get(vid, 0.0) + kwh
        observation = proposal.observation
        if minutes > 0 and minutes != observation.interval_minutes:
            observation = replace(observation, interval_minutes=minutes)
        power_by_vehicle = {
            vid: {
                "requested_output_kw": approved.setpoints_kw.get(vid, 0.0),
                "allowed_output_kw": candidate.allowed_kw,
                "actual_output_kw": kw_minutes.get(vid, 0.0) / minutes if minutes else 0.0,
            }
            for vid, candidate in proposal.candidates.items()
        }
        return decision_record(
            observation,
            proposal.dispatch,
            proposal.assignments,
            proposal.demand,
            proposal.budgets,
            algorithm_labels(self.kernel.algorithms),
            power_by_vehicle,
            {vid: stored.get(vid, 0.0) for vid in proposal.candidates},
            proposal.diagnostics,
        )

    def guard_inputs(self, approved: ApprovedDecision) -> dict:
        """Đúng đầu vào Physical Guard đã dùng cho quyết định (để replay / debug lại phán quyết từ trace)."""
        proposal = approved.proposal
        limits = proposal.effective_limits
        return {
            "candidates": {
                vid: {
                    "cabinet": c.cabinet.id,
                    "zone": c.cabinet.zone,
                    "ports": c.cabinet.ports,
                    "port_kw": c.cabinet.port_kw,
                    "cabinet_kw": c.cabinet.output_kw,
                    "allowed_kw": c.allowed_kw,
                }
                for vid, c in proposal.candidates.items()
            },
            "budgets_kw": dict(proposal.budgets.output_kw),
            "limits": {
                "minute": limits.minute,
                "conversion": limits.conversion,
                "grid_input_kw": limits.grid_input_kw,
                "zone_output_kw": dict(limits.zone_output_kw),
                "cabinet_output_kw": dict(limits.cabinet_output_kw),
                "independent_grid_input_kw": None
                if limits.independent_grid_input_kw is None
                else dict(limits.independent_grid_input_kw),
            },
        }

    # ---- Báo cáo cho KPI (benchmark) ----------------------------------------------------

    @_locked
    def outcomes(self) -> list[SessionOutcome]:
        """Kết cục của mọi xe đã đến (đã rời + còn ở bãi tại lúc gọi)."""
        rows = []
        for vid, s in self.queue.sessions.items():
            if s.state == "NOT_ARRIVED":
                continue
            visit = self._visits[vid]
            delivered = self.kernel.output_by_deadline_kwh.get(vid, 0.0)
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

    @_locked
    def scheduling_observation(self, interval_minutes: int = 1) -> SchedulingObservation:
        """Snapshot (chưa dispatch) theo hợp đồng optimizer — cho ước tính ETA hàng chờ và test."""
        vehicles = self.kernel._view()
        return SchedulingObservation(
            scenario=replace(self.scenario, vehicles=tuple(row.vehicle for row in vehicles.values())),
            minute=self.minute,
            interval_minutes=interval_minutes,
            vehicles=vehicles,
            queues=MappingProxyType({zone: tuple(q) for zone, q in self.queue.waiting.items()}),
            ports=MappingProxyType({port: self.queue.occupied.get(port) for port in self.queue.connectors}),
            candidates=MappingProxyType(self.kernel.candidates(interval_minutes)),
            dc_charging_model=self.adapter.dc_model,
            effective_limits=self.kernel.effective_limits(),
        )

    @_locked
    def dispatch_observation(self, zone: str):
        """Như `StationKernel.dispatch_observation`: cổng lỗi không tính là cổng trống."""
        return self.kernel.dispatch_observation(zone)

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
            or port in self.kernel.faults
            or port in self.queue.occupied
            or session.vehicle.zone != cab.zone
        ):
            logger.warning(
                "Bỏ qua ASSIGN %s → %s: xe không chờ / cổng bận, lỗi / khác vùng", vid, self._port_to_connector[port]
            )
            return
        self.kernel.connect({port: vid})

    def _emit(self, when: int, kind: str, v: Vehicle, **metadata) -> None:
        """Dịch sự kiện simulator → StationEvent."""
        port = metadata.get("connector")
        connector_id = self._port_to_connector.get(port) if port else None
        if kind == "ARRIVED":
            event_type, detail = EventType.VEHICLE_ARRIVED, ""
        elif kind in ("UNPLUGGED", "LEFT_QUEUE"):
            event_type = EventType.VEHICLE_DEPARTED
            detail = "Tới giờ rời" if metadata.get("reason") == "declared_departure" else "Xe DC rút sau khi đầy"
            self.kernel.setpoints.pop(v.id, None)
        elif kind == "CHARGE_COMPLETED":
            # Kernel báo phiên đạt target: giải phóng công suất → tính lại ngay, không chờ mốc 15' (PHASE0 §2 #4).
            event_type, detail = EventType.CHARGE_COMPLETED, f"Xe {v.id} sạc xong"
        else:
            return  # PLUGGED_IN: hệ quả của lệnh ASSIGN vừa áp, không phải mốc mới
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
        if port in self.kernel.faults:
            status = ConnectorStatus.FAULT
        elif session is None:
            status = ConnectorStatus.IDLE
        elif session.state == "FINISHED":
            status = ConnectorStatus.FINISHED
        else:
            allowed = min(cab.port_kw, self.adapter.acceptance_kw(session.vehicle, 1))
            power = min(self.kernel.setpoints.get(vid, 0.0), allowed)
            cap = min(cab.port_kw, session.vehicle.max_kw)
            status = ConnectorStatus.CHARGING if power >= cap - EPS else ConnectorStatus.THROTTLED
        return ConnectorState(
            connector_id=connector_id,
            status=status,
            power_kw=round(power, 6),
            max_power_kw=cab.port_kw,
            booking_id=vid,
        )
