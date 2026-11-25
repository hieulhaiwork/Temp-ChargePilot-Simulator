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
  - Setpoint giữ tới lệnh sau; công suất thực = min(setpoint, cổng, acceptance 1'). Vi phạm sau khi áp đếm + log
    (trạm live không được chết); bật `guard.after_apply_failsafe` ⇒ phát HARD_LIMIT_VIOLATED (có loại vi phạm) và dừng
    catch-up ở phút vi phạm để runtime xử lý an toàn qua dispatcher (Final Acceptance §1); HybridSimulator thì raise.
  - Lỗi cổng: xe đang cắm bị rút, về ĐẦU hàng chờ, `charge_started` xoá. Không đổi cổng cho xe đang cắm.
  - Xe đã rời mà upsert lại ⇒ bỏ qua (log).

DC charging model: `dc_charging_model=<tên DC_MODELS>` (cùng registry với simulator offline) hoặc `dc_model` tự dựng;
mặc định `SyntheticTaperV1()`. `vinfast_profiles_v0_1` dùng provider resolve profile khi xe được upsert
(`core/charging_models/live_profiles.py`, Final Review 4.2).
"""

import copy
import functools
import hashlib
import json
import logging
import math
import threading
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timedelta
from random import Random
from types import FunctionType, MappingProxyType
from zoneinfo import ZoneInfo

import numpy as np

from src.models.charging_physics import DCChargingModel
from src.models.control import Command, CommandType
from src.models.decision_trace import BackendAppliedSample
from src.models.decisions import AppliedResult, ApprovedDecision, TimeConfig
from src.models.events import EventType, StationEvent
from src.models.physical_constraints import TOL, ConstraintViolationError
from src.models.physical_limits import EffectiveLimits
from src.models.scheduling.observations import ObservationModel, SchedulingObservation
from src.models.simulation import Incident, IncidentType, SessionOutcome
from src.models.simulation import Scenario as BackendScenario
from src.models.simulation_core import Cabinet, Scenario, Vehicle
from src.models.station import ConnectorState, ConnectorStatus, SessionProgress, StationConfig, StationState
from src.models.station_protocols import VehicleVisit
from src.optimizer.dispatch.least_laxity import optimistic_laxity
from src.simulator.core.algorithms import Algorithms, algorithm_labels, default_algorithms, station_dc_model
from src.simulator.core.charging_models.synthetic_dc import SyntheticTaperV1
from src.simulator.core.ev2gym_adapter import EV2GymAdapter
from src.simulator.core.isolation import is_shared
from src.simulator.core.kernel import SOC_TOL, StationKernel
from src.simulator.core.queue import QueueController, Session
from src.simulator.evaluation.trace import decision_record

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PhysicsSnapshotSeed:
    """Lock-free, actuator-free physics seed captured atomically from `HybridStation`.

    Holds a detached `StationKernel` (`emit=None`) and immutable station metadata so
    counterfactual snapshots contain zero locks, event loops, DB connections, WebSocket
    clients, or `StationActuator` instances. Each sandbox branch forks `detached_kernel`
    again, leaving this seed completely untouched.
    """

    start: datetime
    available_power_kw: float
    schedule_version: int
    dc_model_name: str | None
    policy: tuple[str, str]
    time: TimeConfig
    halted_on: tuple | None
    visits: tuple[tuple[str, VehicleVisit], ...]
    cabinets: tuple[Cabinet, ...]
    connector_to_port: tuple[tuple[str, str], ...]
    port_to_connector: tuple[tuple[str, str], ...]
    detached_kernel: StationKernel

    def integrity_state(self) -> dict:
        """Canonical execution state of the detached backend seed, without invoking its components."""
        kernel = self.detached_kernel
        adapter = kernel.adapter
        ids_by_model = {id(ev): vid for vid, ev in adapter.models.items()}
        return _seed_value(
            {
                "station": {f.name: getattr(self, f.name) for f in fields(self) if f.name != "detached_kernel"},
                "kernel": {k: v for k, v in vars(kernel).items() if k not in {"adapter", "queue", "emit"}},
                "queue": vars(kernel.queue),
                "adapter": {
                    "efficiency": adapter.efficiency,
                    "dc_model": adapter.dc_model,
                    "connections": adapter._connections,
                    "vehicles": {vid: [type(ev).__qualname__, vars(ev)] for vid, ev in adapter.models.items()},
                    "chargers": {
                        key: {
                            **vars(charger),
                            "evs_connected": [
                                None if ev is None else ids_by_model[id(ev)] for ev in charger.evs_connected
                            ],
                        }
                        for key, charger in adapter.stations.items()
                    },
                },
            }
        )


def _seed_value(value):
    """Encode the value types used by backend physics and explicitly supported component state."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"float": value.hex()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return {"dtype": value.dtype.str, "shape": value.shape, "values": _seed_value(value.tolist())}
    if isinstance(value, np.generic):
        return _seed_value(value.item())
    if isinstance(value, Mapping):
        # Preserve iteration order, which can affect the planner and event delivery.
        return [[_seed_value(key), _seed_value(item)] for key, item in value.items()]
    if isinstance(value, (list, tuple, deque)):
        return [_seed_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_seed_value(item) for item in value), key=json.dumps)
    if isinstance(value, Random):
        return {"random_state": _seed_value(value.getstate())}
    if isinstance(value, FunctionType) and is_shared(value):
        return {"function": f"{value.__module__}.{value.__qualname__}"}
    kind = f"{type(value).__module__}.{type(value).__qualname__}"
    if is_dataclass(value):
        return {"type": kind, "fields": _seed_value({f.name: getattr(value, f.name) for f in fields(value)})}
    if hasattr(value, "__dict__") and not isinstance(value, (FunctionType, type)):
        return {"type": kind, "fields": _seed_value(vars(value))}
    raise TypeError(f"Unsupported snapshot physics state: {kind}")


def _component_state_signature(component: object) -> dict[str, object]:
    """Deterministic JSON-serializable state descriptor for pluggable components."""
    shared = is_shared(component)
    cls_name = f"{type(component).__module__}.{type(component).__qualname__}"
    if shared:
        return {"type": cls_name, "shared": True}
    payload: dict[str, object] = {"type": cls_name, "shared": False}
    profiles = getattr(component, "profiles", None)
    if isinstance(profiles, Mapping):
        payload["registered_vehicle_ids"] = sorted(str(k) for k in profiles)
    unresolved = getattr(component, "unresolved", None)
    if isinstance(unresolved, Mapping):
        payload["unresolved"] = {str(k): str(v) for k, v in sorted(unresolved.items())}
    rng = getattr(component, "rng", None)
    if rng is not None and callable(getattr(rng, "getstate", None)):
        payload["rng_state_repr"] = repr(rng.getstate())
    if hasattr(component, "__dict__"):
        attrs = {}
        for key, value in sorted(vars(component).items()):
            if key in ("_profiles", "profiles", "unresolved", "rng", "inner", "delegate", "fallback"):
                continue
            attrs[key] = repr(value)
        if attrs:
            payload["attrs"] = attrs
    for nested_name in ("inner", "delegate", "fallback"):
        nested = getattr(component, nested_name, None)
        if nested is not None:
            payload[nested_name] = _component_state_signature(nested)
    return payload


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


def _violation_signature(result: AppliedResult) -> tuple:
    """Nhận diện "cùng một vi phạm" giữa hai phút liền nhau: loại + xe + thông điệp Physical Guard."""
    if result.hard_violations:
        return tuple((v.kind, v.vehicle_ids, v.message) for v in result.hard_violations)
    return tuple(result.violations)


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
        observation_model: ObservationModel | None = None,
        dc_charging_model: str | None = None,
    ) -> None:
        """`dc_charging_model`: tên trong `DC_MODELS` của simulator (vd. `vinfast_profiles_v0_1`); None ⇒ `dc_model`
        hoặc `SyntheticTaperV1()` như cũ. Không truyền cả hai."""
        if start.tzinfo is None:
            raise ValueError("start phải có múi giờ")
        if dc_model is not None and dc_charging_model is not None:
            raise ValueError("Chọn dc_model HOẶC dc_charging_model, không cả hai")
        self.config = config
        # Final Review §4.3: lớp quan sát giữa ground truth và optimizer (mặc định PerfectObservation = như cũ)
        self._observation_model = observation_model
        self.lock = threading.RLock()
        self.is_fork = False
        self._tz = ZoneInfo(config.timezone)
        self._dc_model = dc_model
        self.dc_model_name = dc_charging_model
        self._algorithms = algorithms
        self._policy = (policy_id, policy_version)
        self._connector_to_port: dict[str, str] = {}
        self._port_to_connector: dict[str, str] = {}
        self._cabinets = self._build_cabinets(config)
        if dc_charging_model is not None:
            # Cùng registry DC_MODELS với offline; model cần biết xe ⇒ provider resolve khi xe được upsert.
            self._dc_model = station_dc_model(dc_charging_model, self._build_scenario())
        self.time = TimeConfig(physics_step_minutes=1, decision_interval_minutes=config.optimizer.planning_step_minutes)
        self._init(start.astimezone(self._tz), config.grid_input_limit_kw or config.power_limit_kw)

    @classmethod
    def with_vinfast_profiles(cls, *args, **kwargs) -> "HybridStation":
        """Trạm dùng profile DC VinFast (`vinfast_profiles_v0_1`), resolve theo xe lúc upsert (xe đến động)."""
        return cls(*args, dc_charging_model="vinfast_profiles_v0_1", **kwargs)

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
        if self.dc_model_name is not None and hasattr(self._dc_model, "clear"):
            self._dc_model.clear()  # reset: trạm mới không còn xe nào ⇒ bảng profile theo xe cũng rỗng
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
            observation_model=self._observation_model,
        )
        self.kernel.command_resolution_kw = COMMAND_RESOLUTION_KW
        self.available_power_kw = available_kw
        self._visits: dict[str, VehicleVisit] = {}
        self._events: list[StationEvent] = []
        self._halted_on: tuple | None = None  # vi phạm mà step() đã dừng catch-up ở phút gần nhất (§1.3)
        # Kết quả từng bước vật lý từ lần drain trước — DecisionTrace backend đóng quyết định bằng số đo thật.
        self._applied: deque[BackendAppliedSample] = deque(maxlen=APPLIED_BUFFER_STEPS)
        self._dropped_applied_minutes = 0
        self._dropped_hard_violations = 0

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

    def time_at(self, minute: int) -> str:
        """ISO-8601 station-local timestamp for a simulation minute."""
        return self._at(minute).isoformat()

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
    def safety_state(self) -> StationState:
        """Occupied-port held commands, before acceptance clipping or display rounding."""
        state = self.state()
        return state.model_copy(
            update={
                "connectors": [
                    port.model_copy(update={"power_kw": self.kernel.setpoints.get(port.booking_id, 0.0)})
                    for port in state.connectors
                ]
            }
        )

    @_locked
    def step(self, minutes: int) -> list[StationEvent]:
        """Physical Core của kernel, từng bước vật lý 1'; sau mỗi bước xử lý xe đến / rời / rút DC.

        Bật `guard.after_apply_failsafe` (Final Acceptance §1.3): catch-up nhiều phút DỪNG ở phút có vi phạm cứng mới
        (trả sự kiện, các phút còn lại chưa tích phân) để fail-safe xử lý trước; lần gọi sau chạy tiếp từ đó. Vi phạm y
        hệt vi phạm đã dừng ở lần trước, liền mạch (fail-safe đã có một lượt mà không sửa được, vd. lỗi charging model)
        thì không dừng lại nữa — vẫn phát sự kiện mỗi lần step — để đồng hồ trạm không bị treo.
        """
        self._events = []
        kernel = self.kernel
        failsafe = self.config.guard.after_apply_failsafe or self.is_fork
        signalled = False
        for _ in range(max(minutes, 0)):
            held = {vid: kernel.setpoints.get(vid, 0.0) for vid in self.queue.occupied.values()}
            result = kernel.advance(kernel.now + 1)
            if self._applied and len(self._applied) == self._applied.maxlen:
                evicted = self._applied[0].result
                self._dropped_applied_minutes += evicted.end - evicted.minute
                self._dropped_hard_violations += len(evicted.violations)
            self._applied.append(BackendAppliedSample(result, held))
            halt = False
            if failsafe and result.violations:
                if not signalled:
                    # Final Review §4.5b: kernel non-strict chỉ đếm + log vi phạm trần cứng sau khi áp. Tín hiệu cho
                    # runtime sinh lệnh an toàn qua guard/dispatcher.py (trạm không tự hạ setpoint). Một sự kiện / step.
                    signalled = True
                    self._events.append(self._violation_event(result))
                signature = _violation_signature(result)
                halt = signature != self._halted_on
                self._halted_on = signature
            elif failsafe:
                self._halted_on = None
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
            if halt:
                break
        return self._drain()

    def _violation_event(self, result: AppliedResult) -> StationEvent:
        """HARD_LIMIT_VIOLATED có loại vi phạm + xe liên quan (Final Acceptance §1.4) để fail-safe chọn cách xử lý."""
        kinds = list(dict.fromkeys(v.kind for v in result.hard_violations))
        vehicles = sorted({vid for v in result.hard_violations for vid in v.vehicle_ids})
        label = ", ".join(kinds) or "?"
        return StationEvent(
            type=EventType.HARD_LIMIT_VIOLATED,
            occurred_at=self._at(result.end),
            detail=f"Vi phạm trần cứng sau khi áp ({label}): {result.violations[0]}"[:500],
            violation_kinds=kinds,
            violation_booking_ids=vehicles,
        )

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
            self._register_profile(vehicle)
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
        twin.config = self.config.model_copy(deep=True)
        twin._connector_to_port = dict(self._connector_to_port)
        twin._port_to_connector = dict(self._port_to_connector)
        twin._visits = dict(self._visits)
        twin._events = []
        twin._applied = deque(maxlen=APPLIED_BUFFER_STEPS)
        twin._dropped_applied_minutes = 0
        twin._dropped_hard_violations = 0
        twin.kernel = self.kernel.fork(emit=twin._emit)
        # Thành phần có trạng thái đã được cô lập trong kernel.fork (Final Review §4.4): bản fork giữ bản của nó.
        if self._algorithms is not None:
            twin._algorithms = twin.kernel.algorithms
        if self._observation_model is not None:
            twin._observation_model = twin.kernel.observation_model
        # DC model có trạng thái (provider profile theo xe, có fork()) đã được kernel.fork tách bằng memo chung cho
        # adapter + algorithms; bản fork đăng ký xe what-if không đụng bản live.
        twin._dc_model = twin.kernel.adapter.dc_model
        return twin

    @_locked
    def export_physics_seed(self) -> PhysicsSnapshotSeed:
        """Export a lock-free, actuator-free physics seed for immutable counterfactual snapshots."""
        detached = self.kernel.fork(emit=None)
        return PhysicsSnapshotSeed(
            start=self._start,
            available_power_kw=float(self._available_power_kw),
            schedule_version=int(self.schedule_version),
            dc_model_name=self.dc_model_name,
            policy=tuple(self._policy),
            time=self.time,
            halted_on=None if self._halted_on is None else tuple(self._halted_on),
            visits=tuple(sorted(self._visits.items())),
            cabinets=tuple(self._cabinets),
            connector_to_port=tuple(sorted(self._connector_to_port.items())),
            port_to_connector=tuple(sorted(self._port_to_connector.items())),
            detached_kernel=detached,
        )

    @classmethod
    def from_physics_seed(cls, config: StationConfig, seed: PhysicsSnapshotSeed) -> "HybridStation":
        """Materialize a fresh isolated sandbox fork from `seed` without mutating `seed`."""
        twin = cls.__new__(cls)
        twin.config = config.model_copy(deep=True)
        twin.lock = threading.RLock()
        twin.is_fork = True
        twin._tz = ZoneInfo(twin.config.timezone)
        twin.dc_model_name = seed.dc_model_name
        twin._policy = seed.policy
        twin.time = seed.time
        twin._start = seed.start
        twin._available_power_kw = float(seed.available_power_kw)
        twin.schedule_version = int(seed.schedule_version)
        twin._halted_on = seed.halted_on
        twin._visits = dict(seed.visits)
        twin._cabinets = seed.cabinets
        twin._connector_to_port = dict(seed.connector_to_port)
        twin._port_to_connector = dict(seed.port_to_connector)
        twin._events = []
        twin._applied = deque(maxlen=APPLIED_BUFFER_STEPS)
        twin._dropped_applied_minutes = 0
        twin._dropped_hard_violations = 0
        twin.kernel = seed.detached_kernel.fork(emit=twin._emit)
        twin._algorithms = twin.kernel.algorithms
        twin._observation_model = twin.kernel.observation_model
        twin._dc_model = twin.kernel.adapter.dc_model
        return twin

    @_locked
    def snapshot_physics_state(self) -> dict:
        """Pure, deterministic, JSON-serializable ground-truth physics & component state at `now`."""
        sessions_payload: dict[str, dict] = {}
        for vid in sorted(self.queue.sessions):
            s = self.queue.sessions[vid]
            ev = self.adapter.models[vid]
            sessions_payload[vid] = {
                "state": s.state,
                "zone": s.vehicle.zone,
                "vehicle_model": s.vehicle.vehicle_model,
                "connector_id": self.connector_of(s.connector) if s.connector else None,
                "last_connector_id": self.connector_of(s.last_connector) if s.last_connector else None,
                "arrival_minute": s.vehicle.arrival,
                "arrival_at": self.time_at(s.vehicle.arrival),
                "departure_minute": s.vehicle.departure,
                "departure_at": self.time_at(s.vehicle.departure),
                "battery_capacity_kwh": round(float(s.vehicle.battery_kwh), 9),
                "initial_soc": round(float(s.vehicle.initial_soc), 9),
                "current_soc": round(float(self.adapter.soc(vid)), 9),
                "current_capacity_kwh": round(float(ev.current_capacity), 9),
                "target_soc": round(float(s.vehicle.target), 9),
                "max_kw": round(float(s.vehicle.max_kw), 9),
                "charge_started_minute": s.charge_started,
                "charge_started_at": self.time_at(s.charge_started) if s.charge_started is not None else None,
                "completed_at_minute": s.completed_at,
                "completed_at": self.time_at(s.completed_at) if s.completed_at is not None else None,
                "departed_at_minute": s.departed_at,
                "departed_at": self.time_at(s.departed_at) if s.departed_at is not None else None,
                "delivered_battery_kwh": round(float(s.delivered_battery_kwh), 9),
                "delivered_grid_kwh": round(float(s.delivered_grid_kwh), 9),
                "output_kwh": round(float(self.kernel.output_kwh.get(vid, 0.0)), 9),
                "output_by_deadline_kwh": round(float(self.kernel.output_by_deadline_kwh.get(vid, 0.0)), 9),
            }
        known_limit_events = [
            {
                "announced_minute": ev.announced_minute,
                "announced_at": self.time_at(ev.announced_minute),
                "effective_minute": ev.effective_minute,
                "effective_at": self.time_at(ev.effective_minute),
                "grid_input_kw": None if ev.grid_input_kw is None else round(float(ev.grid_input_kw), 9),
                "cabinet_output_kw": {k: round(float(v), 9) for k, v in sorted(ev.cabinet_output_kw.items())},
            }
            for ev in self.scenario.limit_events
            if ev.announced_minute <= self.minute
        ]
        hidden_limit_count = sum(1 for ev in self.scenario.limit_events if ev.announced_minute > self.minute)
        alg = self.kernel.algorithms
        stateful_sig = {
            "dispatch": {z: _component_state_signature(p) for z, p in sorted(alg.dispatch.items())},
            "optimizers": {z: _component_state_signature(o) for z, o in sorted(alg.optimizers.items())},
            "coordinator": _component_state_signature(alg.coordinator),
            "dc_charging_model": _component_state_signature(self.adapter.dc_model),
            "observation_model": _component_state_signature(self.kernel.observation_model),
            "combined_policy": None if self.kernel.policy is None else _component_state_signature(self.kernel.policy),
        }
        stateful_sha256 = hashlib.sha256(
            json.dumps(stateful_sig, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        effective = self.kernel.effective_limits()
        eff_grid = None if not math.isfinite(effective.grid_input_kw) else round(float(effective.grid_input_kw), 9)
        return {
            "minute": self.minute,
            "now_iso": self.now.isoformat(),
            "state_version": self.kernel.state_version,
            "schedule_version": self.schedule_version,
            "available_power_kw": round(float(self.available_power_kw), 9),
            "effective_grid_limit_kw": eff_grid,
            "grid_input_override_kw": (
                None
                if self.kernel.grid_input_override_kw is None
                else round(float(self.kernel.grid_input_override_kw), 9)
            ),
            "next_decision_minute": self.kernel.next_decision_minute,
            "halted_on": [] if self._halted_on is None else list(self._halted_on),
            "faulted_connectors": sorted(self.connector_of(p) for p in self.kernel.faults),
            "occupied_connectors": {self.connector_of(p): vid for p, vid in sorted(self.queue.occupied.items())},
            "queues_by_zone": {zone: list(self.queue.waiting[zone]) for zone in sorted(self.queue.waiting)},
            "held_setpoints_kw": {vid: round(float(kw), 9) for vid, kw in sorted(self.kernel.setpoints.items())},
            "active_budget_kw": (
                None
                if self.kernel.active_budget_kw is None
                else {z: round(float(v), 9) for z, v in sorted(self.kernel.active_budget_kw.items())}
            ),
            "active_setpoints_kw": (
                None
                if self.kernel.active_setpoints_kw is None
                else {vid: round(float(v), 9) for vid, v in sorted(self.kernel.active_setpoints_kw.items())}
            ),
            "output_kwh": {vid: round(float(v), 9) for vid, v in sorted(self.kernel.output_kwh.items())},
            "output_by_deadline_kwh": {
                vid: round(float(v), 9) for vid, v in sorted(self.kernel.output_by_deadline_kwh.items())
            },
            "constraint_counters": {
                "rejected_allocation_count": self.kernel.rejected_allocation_count,
                "applied_constraint_violation_count": self.kernel.applied_constraint_violation_count,
                "budget_deviation_count": self.kernel.budget_deviation_count,
                "command_deadband_count": self.kernel.command_deadband_count,
            },
            "time_config": {
                "physics_step_minutes": self.kernel.time.physics_step_minutes,
                "decision_interval_minutes": self.kernel.time.decision_interval_minutes,
                "planning_horizon_minutes": self.kernel.time.planning_horizon_minutes,
            },
            "efficiencies": {
                "conversion": round(float(self.scenario.conversion), 9),
                "charging": round(float(self.scenario.efficiency), 9),
                "dc_unplug_delay_minutes": int(self.scenario.delay),
            },
            "sessions": sessions_payload,
            "known_limit_events": known_limit_events,
            "hidden_unannounced_limit_event_count": hidden_limit_count,
            "stateful_components": stateful_sig,
            "stateful_components_sha256": stateful_sha256,
        }

    @_locked
    def effective_grid_limit_kw(self, minute: int | None = None) -> float:
        """Effective grid-input cap (kW) at `minute` (or `self.minute`) including overrides and known limit events."""
        limits = self.kernel.effective_limits(minute=minute)
        return float(limits.grid_input_kw)

    @_locked
    def enforce_known_at_on_fork(self, as_of_minute: int, known_booking_ids: frozenset[str]) -> dict[str, int]:
        """Strip future unannounced limit events and unregistered future arrivals on a sandbox fork ONLY."""
        if not self.is_fork:
            raise RuntimeError("enforce_known_at_on_fork is strictly restricted to sandbox forks")
        pruned_vehicles = 0
        for vid in list(self.queue.sessions):
            session = self.queue.sessions[vid]
            if session.state == "NOT_ARRIVED" and vid not in known_booking_ids:
                self._forget(vid)
                pruned_vehicles += 1
        known_events = tuple(ev for ev in self.kernel.scenario.limit_events if ev.announced_minute <= as_of_minute)
        pruned_events = len(self.kernel.scenario.limit_events) - len(known_events)
        kept_vehicles = tuple(s.vehicle for s in self.queue.sessions.values())
        for values in (
            self.kernel.setpoints,
            self.kernel.active_setpoints_kw,
            self.kernel.output_kwh,
            self.kernel.output_by_deadline_kwh,
        ):
            if values is not None:
                for vid in tuple(values):
                    if vid not in known_booking_ids:
                        values.pop(vid)
        if pruned_vehicles or pruned_events or kept_vehicles != self.kernel.scenario.vehicles:
            self.kernel.scenario = replace(
                self.kernel.scenario,
                vehicles=kept_vehicles,
                limit_events=known_events,
            )
        return {
            "pruned_future_vehicles": pruned_vehicles,
            "pruned_unannounced_limit_events": pruned_events,
        }

    def apply_approved(self, approved: ApprovedDecision) -> None:
        """Áp quyết định đã duyệt THẲNG vào kernel — chỉ cho bản fork; trạm thật chỉ nhận lệnh qua dispatcher."""
        if not self.is_fork:
            raise RuntimeError("apply_approved chỉ dùng cho bản fork (admission); trạm thật đi guard/dispatcher.py")
        with self.lock:
            self.kernel.apply_approved(approved)

    # ---- DecisionTrace (ADR-019 Phase 4, quyết định 6) ----------------------------------

    def drain_applied(self) -> list[AppliedResult]:
        return [sample.result for sample in self.drain_decision_samples()]

    def drain_decision_samples(self) -> list[BackendAppliedSample]:
        return self.drain_decision_evidence()[0]

    @_locked
    def drain_decision_evidence(self) -> tuple[list[BackendAppliedSample], int, int]:
        """Drain retained samples and counters covering evicted physics steps together."""
        evidence = (list(self._applied), self._dropped_applied_minutes, self._dropped_hard_violations)
        self._applied.clear()
        self._dropped_applied_minutes = self._dropped_hard_violations = 0
        return evidence

    @_locked
    def decision_labels(self) -> dict:
        return algorithm_labels(self.kernel.algorithms)

    @_locked
    def planned_decision_facts(self, approved: ApprovedDecision, *, labels: dict) -> dict:
        """Decision-time observed & planned facts for G1-F05 WHY evidence (no measured values).

        Uses `proposal.dispatch` (captured BEFORE planned assignments and BEFORE dispatcher.submit)
        for observed pre-dispatch state so planned assignments are never conflated with connected state.
        """
        proposal = approved.proposal
        observation = proposal.observation
        cfg = observation.scenario
        limits = proposal.effective_limits
        now = proposal.minute

        pre_vehicles: dict = {}
        for dispatch_obs in proposal.dispatch.values():
            for vid, item in dispatch_obs.vehicles.items():
                pre_vehicles.setdefault(vid, item)

        occupied_before = {item.connector: vid for vid, item in pre_vehicles.items() if item.connector is not None}
        empty_before = {port for dispatch_obs in proposal.dispatch.values() for port in dispatch_obs.empty_ports}
        ports_observed = {}
        faulted_connectors: list[str] = []
        for port, (cab, _) in self.queue.connectors.items():
            cid = self.connector_of(port)
            occupant = occupied_before.get(port)
            faulted = occupant is None and port not in empty_before
            if faulted:
                faulted_connectors.append(cid)
            ports_observed[cid] = {
                "port": port,
                "cabinet_id": cab.id,
                "zone": cab.zone,
                "port_limit_kw": cab.port_kw,
                "faulted": faulted,
                "occupied_booking_id": occupant,
            }

        waiting_all = {vid for dispatch_obs in proposal.dispatch.values() for vid in dispatch_obs.waiting}
        waiting_pos = {
            vid: idx + 1 for dispatch_obs in proposal.dispatch.values() for idx, vid in enumerate(dispatch_obs.waiting)
        }
        planned_connector_by_vid = {
            vid: self.connector_of(port)
            for port, vid in proposal.assignments.items()
            if port in self._port_to_connector
        }
        zone_summary = {}
        for zone in cfg.zone_kw:
            zone_ports = [p for p in ports_observed.values() if p["zone"] == zone]
            zone_dispatch = proposal.dispatch.get(zone)
            zone_summary[zone] = {
                "total_ports": len(zone_ports),
                "occupied_ports": sum(1 for p in zone_ports if p["occupied_booking_id"] is not None),
                "empty_ports": len(zone_dispatch.empty_ports) if zone_dispatch is not None else 0,
                "faulted_ports": sum(1 for p in zone_ports if p["faulted"]),
                "waiting_count": len(zone_dispatch.waiting) if zone_dispatch is not None else 0,
            }
        vehicles_observed = {}
        for vid, item in pre_vehicles.items():
            if item.state == "DEPARTED" and vid not in waiting_all and vid not in proposal.candidates:
                continue
            v = item.vehicle
            cand = proposal.candidates.get(vid)
            vehicles_observed[vid] = {
                "zone": v.zone,
                "state": item.state,
                "connector_id": self.connector_of(item.connector) if item.connector else None,
                "queue_position": waiting_pos.get(vid),
                "planned_assigned_connector": planned_connector_by_vid.get(vid),
                "soc": item.soc,
                "target_soc": v.target,
                "deadline_minute": v.departure,
                "deadline_at": self._at(v.departure).isoformat(),
                "remaining_kwh": item.remaining_kwh,
                "vehicle_max_output_kw": v.max_kw,
                "allowed_output_kw": cand.allowed_kw if cand is not None else None,
                "completed_at_minute": item.completed_at,
                "completed_at": self._at(item.completed_at).isoformat() if item.completed_at is not None else None,
            }

        dc_waiting_laxity = {}
        dc_dispatch = proposal.dispatch.get("DC")
        if dc_dispatch is not None:
            ports = dc_dispatch.empty_ports or tuple(dc_dispatch.port_output_kw)
            cap = max((dc_dispatch.port_output_kw[p] for p in ports), default=0.0)
            for vid in dc_dispatch.waiting:
                item = dc_dispatch.vehicles[vid]
                laxity = optimistic_laxity(item, now, cap, cfg.efficiency)
                dc_waiting_laxity[vid] = {
                    "optimistic_laxity_minutes": laxity,
                    "at_risk_under_optimistic_bound": laxity is None or laxity < 0,
                    "estimate_max_output_kw": min(item.vehicle.max_kw, cap),
                    "estimate_basis": "free_ports" if dc_dispatch.empty_ports else "installed_ports",
                }

        planned_bindings = self._planned_binding_constraints(proposal, approved)
        budget_diag = proposal.budgets.diagnostics or {}
        grid_unbounded = limits.grid_input_kw == math.inf
        return {
            "minute": now,
            "end_minute": proposal.interval_end,
            "interval_minutes": proposal.interval_minutes,
            "planning_interval_minutes": proposal.planning_interval_minutes,
            "interval_start_at": self._at(now).isoformat(),
            "interval_end_at": self._at(proposal.interval_end).isoformat(),
            "algorithms": labels,
            "observed": {
                "ports": ports_observed,
                "zone_summary": zone_summary,
                "queues_by_zone": {zone: list(d.waiting) for zone, d in proposal.dispatch.items()},
                "empty_connectors_by_zone": {
                    zone: [self.connector_of(p) for p in d.empty_ports] for zone, d in proposal.dispatch.items()
                },
                "faulted_connectors": sorted(faulted_connectors),
                "vehicles": vehicles_observed,
            },
            "dispatch": {
                zone: {
                    "policy": labels["dispatch"].get(zone),
                    "waiting_before": list(d.waiting),
                    "empty_connectors_before": [self.connector_of(p) for p in d.empty_ports],
                    "planned_assignments": {
                        self.connector_of(port): vid
                        for port, vid in proposal.assignments.items()
                        if port in d.empty_ports
                    },
                    "waiting_after_plan": list(observation.queues.get(zone, ())),
                }
                for zone, d in proposal.dispatch.items()
            },
            "dc_waiting_laxity": dc_waiting_laxity,
            "demand_output_kw": dict(proposal.demand),
            "physical_limits": {
                "grid_input_kw": None if grid_unbounded else limits.grid_input_kw,
                "grid_input_unbounded": grid_unbounded,
                "supply_mode": "shared" if limits.shared_supply else "independent",
                "independent_grid_input_kw": None if limits.shared_supply else dict(limits.independent_grid_input_kw),
                "zone_output_kw": dict(limits.zone_output_kw),
                "cabinet_output_kw": dict(limits.cabinet_output_kw),
                "port_output_kw": {
                    self.connector_of(port): cab.port_kw for port, (cab, _) in self.queue.connectors.items()
                },
                "conversion_efficiency": limits.conversion,
                "charging_efficiency": cfg.efficiency,
            },
            "coordinator": {
                "policy": labels["coordinator"],
                "assigned_output_kw": dict(proposal.budgets.output_kw),
                "default_zone_budget_kw": dict(cfg.default_zone_budget_kw),
                "requested_output_kw": dict(proposal.demand),
                "reason_codes": {str(z): list(codes) for z, codes in (budget_diag.get("reason_codes") or {}).items()},
                "fallback_reason": budget_diag.get("fallback_reason"),
                "diagnostics": {
                    str(k): v for k, v in budget_diag.items() if k not in ("reason_codes", "fallback_reason")
                },
            },
            "optimizers": {
                zone: {
                    "policy": labels["optimizers"].get(zone),
                    **(
                        dict(proposal.diagnostics[zone])
                        if isinstance(proposal.diagnostics.get(zone), Mapping)
                        else {"solver_status": "not_applicable", "fallback_reason": None}
                    ),
                }
                for zone in cfg.zone_kw
            },
            "binding_constraints": planned_bindings,
            "tariff": (
                {"currency": cfg.tariff.currency, "price_per_grid_kwh": cfg.tariff.price_at(now)}
                if cfg.tariff is not None
                else None
            ),
        }

    def _planned_binding_constraints(self, proposal, approved: ApprovedDecision) -> list[dict]:
        """Binding constraints at planned stages ('proposed', 'approved') — never measured."""
        observation = proposal.observation
        cfg = observation.scenario
        limits = proposal.effective_limits
        budgets = proposal.budgets.output_kw
        bindings: list[dict] = []
        for stage, setpoints in (("proposed", proposal.setpoints_kw), ("approved", approved.setpoints_kw)):
            cabinet_power: dict[str, float] = {}
            zone_power: dict[str, float] = {}
            for vid, candidate in proposal.candidates.items():
                kw = float(setpoints.get(vid, 0.0))
                cab = candidate.cabinet
                cabinet_power[cab.id] = cabinet_power.get(cab.id, 0.0) + kw
                zone_power[cab.zone] = zone_power.get(cab.zone, 0.0) + kw
                if abs(kw - candidate.allowed_kw) <= TOL:
                    bindings.append(
                        {"stage": stage, "limit": "individual_allowed_output", "id": vid, "kw": candidate.allowed_kw}
                    )
                if abs(kw - cab.port_kw) <= TOL:
                    port = observation.vehicles[vid].connector
                    port_id = self.connector_of(port) if port in self._port_to_connector else port
                    bindings.append({"stage": stage, "limit": "port_output", "id": port_id, "kw": cab.port_kw})
            for cab in cfg.cabinets:
                cap = limits.cabinet_output_kw[cab.id]
                if cab.id in cabinet_power and abs(cabinet_power[cab.id] - cap) <= TOL:
                    bindings.append({"stage": stage, "limit": "cabinet_output", "id": cab.id, "kw": cap})
            for zone, total in zone_power.items():
                for label, cap in (("zone_budget", budgets[zone]), ("zone_limit", limits.zone_output_kw[zone])):
                    if abs(total - cap) <= TOL:
                        bindings.append({"stage": stage, "limit": label, "id": zone, "kw": cap})
                if not limits.shared_supply:
                    cap = limits.independent_grid_input_kw[zone]
                    if abs(total / cfg.conversion - cap) <= TOL:
                        bindings.append({"stage": stage, "limit": "independent_grid_input", "id": zone, "kw": cap})
            if (
                limits.shared_supply
                and limits.grid_input_kw != math.inf
                and zone_power
                and abs(sum(zone_power.values()) / cfg.conversion - limits.grid_input_kw) <= TOL
            ):
                bindings.append({"stage": stage, "limit": "site_grid_input", "id": "site", "kw": limits.grid_input_kw})
        return bindings

    @_locked
    def decision_facts(
        self, approved: ApprovedDecision, results: Sequence[AppliedResult], *, labels: dict, post_apply: str
    ) -> dict:
        """Facts của một quyết định theo ĐÚNG schema DecisionTrace của simulator (`evaluation/trace.decision_record`).

        `results`: các bước vật lý đã chạy dưới quyết định này. Công suất thực = trung bình theo thời gian, năng lượng
        nạp = tổng; khoảng = số phút thực sự chạy (quyết định có thể bị thay sớm bởi sự kiện).
        Nếu chưa có mẫu, giữ khoảng lập kế hoạch và để số đo là null.
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
        facts = decision_record(
            observation,
            proposal.dispatch,
            proposal.assignments,
            proposal.demand,
            proposal.budgets,
            labels,
            power_by_vehicle,
            {vid: stored.get(vid, 0.0) for vid in proposal.candidates},
            proposal.diagnostics,
        )
        facts["guard"]["status"] = post_apply
        if not kw_minutes:
            facts["guard"]["checks"] = ["dispatch", "budgets", "requested"]
        for vid, row in facts["vehicles"].items():
            if vid not in kw_minutes:
                for key in (
                    "actual_output_kw",
                    "battery_kwh",
                    "grid_input_kw",
                    "grid_kwh",
                    "actual_minus_predicted_output_kw",
                    "actual_minus_predicted_battery_kwh",
                ):
                    if key in row:
                        row[key] = None
        if post_apply != "pass" or not all(r.actual_kw.keys() >= proposal.candidates.keys() for r in results):
            facts["guard"]["binding_constraints"] = [
                binding for binding in facts["guard"]["binding_constraints"] if binding["stage"] != "actual"
            ]
        return facts

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
        self._register_profile(vehicle)
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
        forget = getattr(self.adapter.dc_model, "forget_vehicle", None)
        if forget is not None:
            forget(vid)

    def _register_profile(self, vehicle: Vehicle) -> None:
        """Model DC cần biết xe (provider profile, Final Review 4.2): resolve lúc xe được upsert. Model khác: bỏ qua."""
        register = getattr(self.adapter.dc_model, "register_vehicle", None)
        if register is not None:
            register(vehicle, self.scenario)

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
            try:
                allowed = min(cab.port_kw, self.adapter.acceptance_kw(session.vehicle, 1))
            except ConstraintViolationError:
                # Final Acceptance §1.4: acceptance của xe lỗi ⇒ cổng hiển thị FAULT, 0 kW (Guard không cấp điện cho
                # cổng FAULT) thay vì làm hỏng cả state() của trạm. Đường bình thường không đổi.
                allowed = None
            if allowed is None:
                status = ConnectorStatus.FAULT
            else:
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
