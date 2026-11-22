"""Single offline hybrid runtime, with ChargePilot queue and EV2Gym components."""

from collections.abc import Mapping
from dataclasses import replace
from logging import getLogger
from time import perf_counter
from types import MappingProxyType

from ..algorithms import Algorithms, algorithm_labels, default_algorithms
from ..coordination.base import ZoneBudgets
from ..dispatch.base import DispatchObservation
from ..evaluation.metrics import summarize
from ..evaluation.trace import decision_record
from ..observations import Candidate, SchedulingObservation, VehicleObservation
from ..optimizers.base import PowerProposal, SchedulingPolicy
from ..safety.constraints import ConstraintViolationError
from ..safety.guard import guard, validate_budgets, validate_dispatch, validate_response
from ..safety.limits import EffectiveLimits, effective_limits, environment_boundary
from ..scenario import Scenario, clock
from .ev2gym_adapter import EV2GymAdapter
from .queue import QueueController

ZERO_POWER = dict.fromkeys(("requested_output_kw", "allowed_output_kw", "actual_output_kw"), 0.0)
LOGGER = getLogger(__name__)


class HybridSimulator:
    def __init__(
        self,
        scenario: Scenario,
        policy: SchedulingPolicy | None = None,
        adapter_factory=EV2GymAdapter,
        *,
        algorithms: Algorithms | None = None,
        record_decisions: bool = False,
    ):
        self.scenario = scenario
        self.algorithms = default_algorithms() if algorithms is None else algorithms
        self.adapter = (
            adapter_factory(scenario)
            if algorithms is None
            else adapter_factory(scenario, dc_model=self.algorithms.dc_charging_model)
        )
        self.queue = QueueController(scenario)
        # Compatibility path for existing combined power policies. The same guard applies.
        self.policy = policy
        self.events = []
        self.frames = []
        self.trace = []
        self.decision_trace = []
        self.decision_latency_ms = []
        self._decision_labels = algorithm_labels(self.algorithms, policy) if record_decisions else None
        self.now = scenario.start
        self.rejected_allocation_count = 0
        self.applied_constraint_violation_count = 0
        self._constraint_failure = False

    def constraint_metrics(self) -> dict[str, int]:
        return {
            "rejected_allocation_count": self.rejected_allocation_count,
            "applied_constraint_violation_count": self.applied_constraint_violation_count,
        }

    @property
    def finished(self) -> bool:
        return self.now == self.scenario.end

    def emit(self, when, kind, v, **metadata):
        self.events.append(dict(minute=when, time=clock(when), event=kind, car_id=v.id, zone=v.zone, **metadata))

    def _vehicles(self, when: int) -> dict:
        rows = {}
        for vid, s in self.queue.sessions.items():
            v = s.vehicle
            waiting = None
            if s.state != "NOT_ARRIVED":
                wait_end = s.charge_started if s.charge_started is not None else s.departed_at
                waiting = (when if wait_end is None else wait_end) - v.arrival
            rows[vid] = {
                "id": vid,
                "zone": v.zone,
                "state": s.state,
                "connector": s.connector,
                "arrival": v.arrival,
                "departure": v.departure,
                "target": v.target,
                "soc": self.adapter.soc(vid),
                "charge_started": s.charge_started,
                "completed_at": s.completed_at,
                "departed_at": s.departed_at,
                "waiting_minutes": waiting,
                "delivered_battery_kwh": s.delivered_battery_kwh,
                "delivered_grid_kwh": s.delivered_grid_kwh,
            }
        return rows

    def _frame(self) -> dict:
        return {
            "minute": self.now,
            "time": clock(self.now),
            "vehicles": self._vehicles(self.now),
            "queues": {zone: list(queue) for zone, queue in self.queue.waiting.items()},
            "ports": {port: self.queue.occupied.get(port) for port in self.queue.connectors},
            "completed": sum(s.completed_at is not None for s in self.queue.sessions.values()),
        }

    def snapshot(self) -> dict:
        return self._frame()

    def _observed_vehicles(self, *, include_unseen: bool = False) -> Mapping[str, VehicleObservation]:
        return MappingProxyType(
            {
                vid: VehicleObservation(
                    s.vehicle, s.state, self.adapter.soc(vid), s.connector, s.charge_started, s.completed_at
                )
                for vid, s in self.queue.sessions.items()
                if include_unseen or s.state != "NOT_ARRIVED"
            }
        )

    def _dispatch(self, vehicles: Mapping[str, VehicleObservation], effective: EffectiveLimits) -> tuple[dict, dict]:
        observations, assignments = {}, {}
        for zone, policy in self.algorithms.dispatch.items():
            limits = {
                port: min(cab.port_kw, effective.cabinet_output_kw[cab.id], effective.zone_capacity_kw(zone))
                for port, (cab, _) in self.queue.connectors.items()
                if cab.zone == zone
            }
            empty = tuple(port for port in limits if port not in self.queue.occupied)
            observation = DispatchObservation(
                self.now,
                zone,
                empty,
                tuple(self.queue.waiting[zone]),
                vehicles,
                MappingProxyType(limits),
                self.scenario.efficiency,
            )
            observations[zone] = observation
            plan = policy(observation)
            validate_dispatch(observation, plan)
            assignments.update(plan)
        self.queue.connect(self.now, assignments, self.adapter, self.emit)
        return observations, assignments

    def _online_observation(self, observation: SchedulingObservation) -> SchedulingObservation:
        # Execution can be interrupted by an arrival. The optimizer plans over the known boundary.
        end = self.queue.next_boundary(self.now, self.scenario, include_unseen_arrivals=False)
        minutes = environment_boundary(observation.scenario, self.now, end, online=True) - self.now
        if minutes == observation.interval_minutes:
            return observation
        candidates = {
            vid: Candidate(
                item.cabinet,
                min(item.cabinet.port_kw, self.adapter.acceptance_kw(observation.vehicles[vid].vehicle, minutes)),
            )
            for vid, item in observation.candidates.items()
        }
        return replace(observation, interval_minutes=minutes, candidates=MappingProxyType(candidates))

    def _power_plan(
        self, observation: SchedulingObservation, planning: SchedulingObservation, budgets: ZoneBudgets, online: bool
    ) -> tuple[Mapping, dict, dict]:
        if self.policy is not None:
            return self.policy(observation), {}, {}
        plan, diagnostics, solver_ms = {}, {}, {}
        for zone, optimizer in self.algorithms.optimizers.items():
            source = planning if online or getattr(optimizer, "uses_online_interval", False) else observation
            eligible = {vid: c for vid, c in source.candidates.items() if c.cabinet.zone == zone}
            scenario = source.scenario
            if not getattr(optimizer, "uses_published_limits", False):
                scenario = source.limits().as_optimizer_scenario(scenario)
            zone_observation = replace(source, scenario=scenario, candidates=MappingProxyType(eligible))
            proposal = optimizer(zone_observation, zone, budgets.output_kw[zone])
            if isinstance(proposal, PowerProposal):
                diagnostics[zone] = proposal.diagnostics
                if proposal.diagnostics.get("fallback_reason"):
                    LOGGER.warning(
                        "minute=%s zone=%s power optimizer fallback=%s",
                        self.now,
                        zone,
                        proposal.diagnostics["fallback_reason"],
                    )
                if proposal.solver_ms is not None:
                    solver_ms[zone] = proposal.solver_ms
                proposal = proposal.output_kw
            if not isinstance(proposal, Mapping):
                raise ConstraintViolationError("Allocation must map vehicle IDs to charger-output kW")
            if proposal.keys() - eligible.keys():
                raise ConstraintViolationError(f"{zone} optimizer proposed an ineligible or cross-zone vehicle")
            plan.update(proposal)
        return plan, diagnostics, solver_ms

    def step(self) -> None:
        if self._constraint_failure:
            raise RuntimeError("Constraint failure stopped this simulation; start a new run")
        if self.finished:
            raise RuntimeError("Simulation horizon reached")
        cfg = self.scenario
        started = perf_counter() if self._decision_labels is not None else None
        self.queue.advance(self.now, cfg, self.adapter, self.emit)
        try:
            limits = effective_limits(cfg, self.now)
            dispatch, assignments = self._dispatch(self._observed_vehicles(), limits)
            end = self.queue.next_boundary(self.now, cfg)
            end = environment_boundary(cfg, self.now, end, online=False)
            minutes = end - self.now
            frame = self._frame()
            candidates = {}
            for port, vid in self.queue.occupied.items():
                session = self.queue.sessions[vid]
                if session.state == "CHARGING":
                    cab, _ = self.queue.connectors[port]
                    allowed = min(cab.port_kw, self.adapter.acceptance_kw(session.vehicle, minutes))
                    candidates[vid] = Candidate(cab, allowed)
            vehicles = self._observed_vehicles(include_unseen=self.policy is not None)
            published = tuple(event for event in cfg.limit_events if event.announced_minute <= self.now)
            known_scenario = cfg
            if len(vehicles) != len(cfg.vehicles) or published != cfg.limit_events:
                known_scenario = replace(
                    cfg,
                    vehicles=tuple(row.vehicle for row in vehicles.values()),
                    limit_events=published,
                )
            observation = SchedulingObservation(
                scenario=known_scenario,
                minute=self.now,
                interval_minutes=minutes,
                vehicles=vehicles,
                queues=MappingProxyType({zone: tuple(queue) for zone, queue in frame["queues"].items()}),
                ports=MappingProxyType(frame["ports"].copy()),
                candidates=MappingProxyType(candidates),
                dc_charging_model=self.algorithms.dc_charging_model,
                effective_limits=limits,
            )
            planning = observation
            online = (
                known_scenario.coordinated_limits
                or known_scenario.tariff is not None
                or getattr(self.algorithms.coordinator, "uses_online_interval", False)
            )
            online_optimizer = any(
                getattr(optimizer, "uses_online_interval", False) for optimizer in self.algorithms.optimizers.values()
            )
            if self.policy is None and (online or online_optimizer):
                planning = self._online_observation(observation)
            demand = MappingProxyType(
                {
                    zone: sum(c.allowed_kw for c in planning.candidates.values() if c.cabinet.zone == zone)
                    for zone in cfg.zone_kw
                }
            )
            budgets = self.algorithms.coordinator(planning, demand)
            validate_budgets(planning, budgets)
            requested, diagnostics, solver_ms = self._power_plan(observation, planning, budgets, online)
            guard(cfg, candidates, requested, budgets.output_kw, limits=limits)
        except ConstraintViolationError:
            self.rejected_allocation_count += 1
            self._constraint_failure = True
            raise
        if started is not None:
            self.decision_latency_ms.append(
                {
                    "minute": self.now,
                    "decision_ms": (perf_counter() - started) * 1000,
                    "solver_ms": solver_ms,
                }
            )
        actual = {}
        power_by_vehicle = {}
        stored_by_vehicle = {}
        for vid, candidate in candidates.items():
            s = self.queue.sessions[vid]
            before = self.adapter.soc(vid)
            setpoint = requested.get(vid, 0.0)
            try:
                response = self.adapter.step(vid, candidate.cabinet.id, setpoint, minutes)
                soc = self.adapter.soc(vid)
                kw, energy = response.actual_output_kw, response.battery_kwh
                validate_response(cfg, s.vehicle, minutes, setpoint, before, soc, kw, energy)
            except ConstraintViolationError:
                self.applied_constraint_violation_count += 1
                self._constraint_failure = True
                raise
            # EV2Gym floating-point arithmetic can produce a tiny negative at zero headroom.
            actual[vid] = max(0.0, kw)
            s.delivered_battery_kwh += max(0.0, energy)
            s.delivered_grid_kwh += actual[vid] * minutes / 60 / cfg.conversion
            stored_by_vehicle[vid] = max(0.0, energy)
            power_by_vehicle[vid] = {
                "requested_output_kw": setpoint,
                "allowed_output_kw": candidate.allowed_kw,
                "actual_output_kw": actual[vid],
            }
            if soc >= s.vehicle.target - 1e-10:
                s.state = "FINISHED"
                s.completed_at = end
                self.emit(end, "CHARGE_COMPLETED", s.vehicle, connector=s.connector, effective_time=clock(end))
        try:
            guard(cfg, candidates, actual, budgets.output_kw, limits=limits)
        except ConstraintViolationError:
            self.applied_constraint_violation_count += 1
            self._constraint_failure = True
            raise
        totals = {
            zone: sum(p for vid, p in actual.items() if candidates[vid].cabinet.zone == zone) for zone in cfg.zone_kw
        }
        power = {
            "ac_output_kw": totals["AC"],
            "dc_output_kw": totals["DC"],
            "grid_input_kw": sum(totals.values()) / cfg.conversion,
        }
        if self._decision_labels is not None:
            self.decision_trace.append(
                decision_record(
                    observation,
                    dispatch,
                    assignments,
                    demand,
                    budgets,
                    self._decision_labels,
                    power_by_vehicle,
                    stored_by_vehicle,
                    diagnostics,
                )
            )
        for vid, row in frame["vehicles"].items():
            row.update(power_by_vehicle.get(vid, ZERO_POWER))
        self.frames.append({**frame, **power, "duration_minutes": minutes})
        self.trace.append(
            {
                "time": clock(self.now),
                "minute": self.now,
                "duration_minutes": minutes,
                **power,
                "ac_queue": len(frame["queues"]["AC"]),
                "dc_queue": len(frame["queues"]["DC"]),
                "occupied_ports": len(self.queue.occupied),
                "vehicles": {
                    vid: {
                        **row,
                        **power_by_vehicle.get(vid, ZERO_POWER),
                    }
                    for vid, row in self._vehicles(end).items()
                },
            }
        )
        self.now = end
        if self.finished:
            self.queue.advance(end, cfg, self.adapter, self.emit)
            final = self._frame()
            for row in final["vehicles"].values():
                row.update(ZERO_POWER)
            self.frames.append({**final, **dict.fromkeys(power, 0.0), "duration_minutes": 0})

    def run(self) -> dict:
        while not self.finished:
            self.step()
        rows = list(self._vehicles(self.now).values())
        for row in rows:
            s = self.queue.sessions[row["id"]]
            row["initial_soc"] = s.vehicle.initial_soc
            row["last_connector"] = s.last_connector
            row["wait_censored"] = row["state"] == "QUEUED"
        result = {
            "scenario_id": self.scenario.id,
            **summarize(self.scenario, self.now, rows, self.trace, self.constraint_metrics()),
            "vehicles": rows,
            "events": self.events,
            "power_trace": self.trace,
            "frames": self.frames,
        }
        if self._decision_labels is not None:
            result.update(decision_trace=self.decision_trace, decision_latency_ms=self.decision_latency_ms)
        return result
