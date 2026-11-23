"""Unified station kernel and the offline hybrid runtime (ADR-019 Phase 3, docs/refactor/PHASE3_DESIGN.md).

`StationKernel` owns the physical state (ChargePilot queue + EV2Gym adapter, clock, held setpoints, faulted ports)
and the four operations shared by the standalone simulator and the backend station:

    observe()          arrivals / departures / DC unplug at `now`
    propose()          Planning Core: dispatch -> coordinator -> optimizer -> Physical Guard (before apply)
    approve()          accept a business-adjusted plan only after the SAME Physical Guard checks it again
    apply_approved()   plug assigned vehicles and hold the approved setpoints
    advance()          Physical Core: one integration loop, then the Physical Guard (after apply)

`HybridSimulator` is the kernel plus trace / frame / report recording. `HybridStation` (backend) holds a kernel.
`guard` is looked up as this module's global at call time, so both Guard stages stay patchable in one place.
"""

from collections.abc import Mapping
from dataclasses import replace
from logging import getLogger
from time import perf_counter
from types import MappingProxyType

from src.guard.physical.validator import guard, validate_budgets, validate_dispatch, validate_response
from src.models.decisions import AppliedResult, ApprovedDecision, ProposedDecision, ReasonCode, TimeConfig

from ..algorithms import Algorithms, algorithm_labels, default_algorithms
from ..dispatch.base import DispatchObservation
from ..evaluation.metrics import summarize
from ..evaluation.trace import decision_record
from ..observations import Candidate, SchedulingObservation, VehicleObservation
from ..optimizers.base import PowerProposal, SchedulingPolicy
from ..safety.constraints import TOL, ConstraintViolationError
from ..safety.limits import EffectiveLimits, effective_limits, environment_boundary
from ..scenario import Scenario, clock
from .ev2gym_adapter import EV2GymAdapter
from .queue import QueueController

ZERO_POWER = dict.fromkeys(("requested_output_kw", "allowed_output_kw", "actual_output_kw"), 0.0)
SOC_TOL = 1e-10
LOGGER = getLogger(__name__)


class StationKernel:
    """One physical + planning core. Callers differ only in TimeConfig, strictness and who supplies setpoints."""

    def __init__(
        self,
        scenario: Scenario,
        adapter: EV2GymAdapter,
        queue: QueueController,
        algorithms: Algorithms,
        *,
        policy: SchedulingPolicy | None = None,
        time: TimeConfig | None = None,
        strict: bool = True,
        policy_id: str = "custom",
        policy_version: str = "1",
        emit=None,
    ):
        self.scenario = scenario
        self.adapter = adapter
        self.queue = queue
        self.algorithms = algorithms
        # Compatibility path for existing combined power policies. The same guard applies.
        self.policy = policy
        self.time = TimeConfig() if time is None else time
        self.strict = strict
        self.policy_id = policy_id
        self.policy_version = policy_version
        if emit is not None:
            self.emit = emit
        self.now = scenario.start
        self.state_version = 0
        self.setpoints: dict[str, float] = {}  # vehicle -> held charger-output kW (until the next approved value)
        self.faults: set[str] = set()  # ports out of service: never offered to dispatch
        self.grid_input_override_kw: float | None = None  # backend power incident (immediately effective)
        self.output_kwh: dict[str, float] = {}  # charger-output energy (backend meaning)
        self.output_by_deadline_kwh: dict[str, float] = {}
        # Planning memo of the last approved decision. Not physical state: does not bump state_version.
        self.active_budget_kw: Mapping[str, float] | None = None
        self.next_decision_minute: int | None = None
        self._deviation_reported = False
        self.rejected_allocation_count = 0
        self.applied_constraint_violation_count = 0
        self.budget_deviation_count = 0
        self._constraint_failure = False

    # ---- state -------------------------------------------------------------------------------

    def emit(self, when, kind, v, **metadata) -> None:
        return None

    def constraint_metrics(self) -> dict[str, int]:
        return {
            "rejected_allocation_count": self.rejected_allocation_count,
            "applied_constraint_violation_count": self.applied_constraint_violation_count,
        }

    @property
    def decision_cap(self) -> int:
        return self.time.decision_interval_minutes or self.scenario.timestep

    def effective_limits(self, minute: int | None = None, scenario: Scenario | None = None) -> EffectiveLimits:
        limits = effective_limits(
            self.scenario if scenario is None else scenario, self.now if minute is None else minute
        )
        if self.grid_input_override_kw is not None:
            limits = replace(limits, grid_input_kw=self.grid_input_override_kw)
        return limits

    def boundary(
        self,
        now: int | None = None,
        *,
        cap: int | None = None,
        scenario: Scenario | None = None,
        include_unseen_arrivals: bool = True,
        online: bool = False,
    ) -> int:
        """The single event boundary: now+cap, horizon end, arrival, departure, DC unplug, TOU, limit events."""
        cfg = self.scenario if scenario is None else scenario
        now = self.now if now is None else now
        cap = self.decision_cap if cap is None else cap
        timed = cfg if cap == cfg.timestep else replace(cfg, timestep=cap)
        end = self.queue.next_boundary(now, timed, include_unseen_arrivals=include_unseen_arrivals)
        return environment_boundary(cfg, now, end, online=online)

    def observe(self) -> None:
        """Environment transitions at `now`: departures, DC unplug after delay, arrivals into the waiting queues."""
        before = [(s.state, s.connector) for s in self.queue.sessions.values()]
        self.queue.advance(self.now, self.scenario, self.adapter, self.emit)
        if before != [(s.state, s.connector) for s in self.queue.sessions.values()]:
            self.state_version += 1

    def _view(
        self, assignments: Mapping[str, str] | None = None, *, include_unseen: bool = False
    ) -> Mapping[str, VehicleObservation]:
        """Vehicle observations; `assignments` (port -> vehicle) are shown as plugged, exactly as connect() would."""
        plugged = {vid: port for port, vid in (assignments or {}).items()}
        rows = {}
        for vid, s in self.queue.sessions.items():
            if not include_unseen and s.state == "NOT_ARRIVED":
                continue
            if vid in plugged:
                rows[vid] = VehicleObservation(
                    s.vehicle, "CHARGING", self.adapter.soc(vid), plugged[vid], self.now, s.completed_at
                )
            else:
                rows[vid] = VehicleObservation(
                    s.vehicle, s.state, self.adapter.soc(vid), s.connector, s.charge_started, s.completed_at
                )
        return MappingProxyType(rows)

    def _occupied_after(self, assignments: Mapping[str, str]) -> dict[str, str]:
        # QueueController.connect appends new ports in stable connector order.
        occupied = dict(self.queue.occupied)
        for port in self.queue.connectors:
            if port in assignments:
                occupied[port] = assignments[port]
        return occupied

    def candidates(self, minutes: int, assignments: Mapping[str, str] | None = None) -> dict[str, Candidate]:
        """Vehicles that may draw power this interval and their individual allowed charger-output kW."""
        assigned = set((assignments or {}).values())
        candidates = {}
        for port, vid in self._occupied_after(assignments or {}).items():
            if vid in assigned or self.queue.sessions[vid].state == "CHARGING":
                cab, _ = self.queue.connectors[port]
                vehicle = self.queue.sessions[vid].vehicle
                candidates[vid] = Candidate(cab, min(cab.port_kw, self.adapter.acceptance_kw(vehicle, minutes)))
        return candidates

    def dispatch_observation(self, zone: str, effective: EffectiveLimits | None = None) -> DispatchObservation:
        effective = self.effective_limits() if effective is None else effective
        limits = {
            port: min(cab.port_kw, effective.cabinet_output_kw[cab.id], effective.zone_capacity_kw(zone))
            for port, (cab, _) in self.queue.connectors.items()
            if cab.zone == zone
        }
        empty = tuple(port for port in limits if port not in self.queue.occupied and port not in self.faults)
        return DispatchObservation(
            self.now,
            zone,
            empty,
            tuple(self.queue.waiting[zone]),
            self._view(),
            MappingProxyType(limits),
            self.scenario.efficiency,
        )

    # ---- Planning Core -----------------------------------------------------------------------

    def _dispatch(self, effective: EffectiveLimits) -> tuple[dict, dict]:
        observations, assignments = {}, {}
        for zone, policy in self.algorithms.dispatch.items():
            observation = self.dispatch_observation(zone, effective)
            observations[zone] = observation
            plan = policy(observation)
            validate_dispatch(observation, plan)
            assignments.update(plan)
        return observations, assignments

    def _online_observation(self, observation: SchedulingObservation) -> SchedulingObservation:
        # Execution can be interrupted by an arrival. The optimizer plans over the known boundary.
        end = self.boundary(scenario=observation.scenario, include_unseen_arrivals=False, online=True)
        minutes = end - self.now
        if self.time.planning_horizon_minutes is not None:
            minutes = min(minutes, self.time.planning_horizon_minutes)
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
        self, observation: SchedulingObservation, planning: SchedulingObservation, budgets, online: bool
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

    def propose(self, *, scenario: Scenario | None = None) -> ProposedDecision:
        """Pure planning on the current state. Raises ConstraintViolationError (REJECTED_BEFORE_APPLY)."""
        cfg = self.scenario if scenario is None else scenario
        try:
            limits = self.effective_limits(scenario=cfg)
            dispatch, assignments = self._dispatch(limits)
            end = self.boundary(scenario=cfg)
            minutes = end - self.now
            candidates = self.candidates(minutes, assignments)
            vehicles = self._view(assignments, include_unseen=self.policy is not None)
            occupied = self._occupied_after(assignments)
            published = tuple(event for event in cfg.limit_events if event.announced_minute <= self.now)
            known_scenario = cfg
            if len(vehicles) != len(cfg.vehicles) or published != cfg.limit_events:
                known_scenario = replace(
                    cfg,
                    vehicles=tuple(row.vehicle for row in vehicles.values()),
                    limit_events=published,
                )
            assigned = set(assignments.values())
            observation = SchedulingObservation(
                scenario=known_scenario,
                minute=self.now,
                interval_minutes=minutes,
                vehicles=vehicles,
                queues=MappingProxyType(
                    {zone: tuple(v for v in queue if v not in assigned) for zone, queue in self.queue.waiting.items()}
                ),
                ports=MappingProxyType({port: occupied.get(port) for port in self.queue.connectors}),
                candidates=MappingProxyType(candidates),
                dc_charging_model=self.adapter.dc_model,
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
            if self.strict:
                self._constraint_failure = True
            raise
        codes = [ReasonCode.PLANNED]
        if any(isinstance(d, Mapping) and d.get("fallback_reason") for d in diagnostics.values()):
            codes.append(ReasonCode.OPTIMIZER_FALLBACK)
        return ProposedDecision(
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            state_version=self.state_version,
            minute=self.now,
            interval_end=end,
            planning_interval_minutes=planning.interval_minutes,
            assignments=assignments,
            setpoints_kw=requested,
            budgets=budgets,
            effective_limits=limits,
            candidates=candidates,
            observation=observation,
            planning=planning,
            dispatch=dispatch,
            demand=demand,
            diagnostics=diagnostics,
            solver_ms=solver_ms,
            reason_codes=tuple(codes),
        )

    def approve(
        self,
        proposal: ProposedDecision,
        setpoints: Mapping[str, float] | None = None,
        *,
        adjustments: Mapping[str, float] | None = None,
        reason_codes: tuple[str, ...] = (),
    ) -> ApprovedDecision:
        """Business step result. A changed plan must pass the same Physical Guard on the same snapshot."""
        final = proposal.setpoints_kw if setpoints is None else setpoints
        changed = dict(final) != dict(proposal.setpoints_kw)
        if changed:
            try:
                guard(
                    proposal.observation.scenario,
                    proposal.candidates,
                    final,
                    proposal.budgets.output_kw,
                    limits=proposal.effective_limits,
                )
            except ConstraintViolationError:
                self.rejected_allocation_count += 1
                if self.strict:
                    self._constraint_failure = True
                raise
        self.active_budget_kw = proposal.budgets.output_kw
        self.next_decision_minute = proposal.interval_end
        self._deviation_reported = False
        codes = (*proposal.reason_codes, *reason_codes)
        if changed and ReasonCode.CONSENT_ADJUSTED not in codes:
            codes = (*codes, ReasonCode.CONSENT_ADJUSTED)
        return ApprovedDecision(proposal, final, adjustments or {}, changed, codes)

    def apply_approved(self, approved: ApprovedDecision) -> None:
        if approved.proposal.state_version != self.state_version or approved.proposal.minute != self.now:
            raise ConstraintViolationError(f"{ReasonCode.STALE_STATE}: decision was planned on another state")
        self.connect(approved.proposal.assignments)
        for vid in approved.proposal.candidates:
            self.hold_setpoint(vid, approved.setpoints_kw.get(vid, 0.0))

    # ---- actuation primitives (offline apply_approved and backend apply_commands) ------------------

    def connect(self, assignments: Mapping[str, str]) -> None:
        if assignments:
            self.queue.connect(self.now, assignments, self.adapter, self.emit)
            self.state_version += 1

    def hold_setpoint(self, vid: str, kw: float) -> None:
        if self.setpoints.get(vid) != kw:
            self.setpoints[vid] = kw
            self.state_version += 1

    def release(self, vid: str) -> None:
        if self.setpoints.pop(vid, None) is not None:
            self.state_version += 1

    def _unplug(self, vid: str) -> str | None:
        session = self.queue.sessions[vid]
        port = session.connector
        if port is not None:
            cab, index = self.queue.connectors[port]
            self.adapter.disconnect(vid, cab.id, index)
            del self.queue.occupied[port]
            session.connector = None
        self.setpoints.pop(vid, None)
        return port

    def fault_port(self, port: str) -> str | None:
        """Port out of service. A plugged vehicle is unplugged and returns to the HEAD of its zone queue."""
        self.faults.add(port)
        vid = self.queue.occupied.get(port)
        if vid is not None:
            session = self.queue.sessions[vid]
            self._unplug(vid)
            session.charge_started = None
            session.state = "QUEUED"
            self.queue.waiting[session.vehicle.zone].appendleft(vid)
        self.state_version += 1
        return vid

    def restore_port(self, port: str) -> None:
        self.faults.discard(port)
        self.state_version += 1

    def withdraw(self, vid: str) -> str | None:
        """Vehicle leaves before its declared departure (cancellation / no-show): queue or port is released."""
        session = self.queue.sessions[vid]
        if session.connector is None and vid in self.queue.waiting[session.vehicle.zone]:
            self.queue.waiting[session.vehicle.zone].remove(vid)
        port = self._unplug(vid)
        session.state = "DEPARTED"
        session.departed_at = self.now
        self.state_version += 1
        return port

    # ---- Physical Core -----------------------------------------------------------------------

    def _after_apply_violation(self, exc: Exception) -> None:
        self.applied_constraint_violation_count += 1
        if self.strict:
            self._constraint_failure = True
            raise exc
        LOGGER.error("minute=%s physical constraint violated after apply: %s", self.now, exc)

    def advance(
        self,
        until: int,
        *,
        candidates: Mapping[str, Candidate] | None = None,
        limits: EffectiveLimits | None = None,
        assigned_kw: Mapping[str, float] | None = None,
        stop_on_completion: bool = False,
    ) -> AppliedResult:
        """Integrate held setpoints over [now, until) in physics steps, then check the result physically.

        Compatibility mode (physics_step None): one zero-order hold over the interval with the decision's
        candidates / limits, post-check against the coordinator budget (strict). Otherwise each step recomputes
        acceptance for its own length, executes min(held setpoint, allowed), marks completion at the step end.
        """
        cfg = self.scenario
        start = self.now
        step = self.time.physics_step_minutes
        requested: dict[str, float] = {}
        allowed: dict[str, float] = {}
        energy_kw_minutes: dict[str, float] = {}
        last_actual: dict[str, float] = {}
        stored: dict[str, float] = {}
        completed: list[str] = []
        violations: list[str] = []
        deviation: dict[str, float] = {}
        steps = 0
        while self.now < until:
            end = until if step is None else min(self.now + step, until)
            minutes = end - self.now
            single = step is None
            try:
                step_candidates = candidates if single and candidates is not None else self.candidates(minutes)
            except ConstraintViolationError as exc:
                violations.append(str(exc))
                self._after_apply_violation(exc)
                step_candidates = {}
            step_limits = limits if single and limits is not None else self.effective_limits()
            actual: dict[str, float] = {}
            for vid, candidate in step_candidates.items():
                s = self.queue.sessions[vid]
                held = self.setpoints.get(vid, 0.0)
                setpoint = min(held, candidate.allowed_kw)
                before = self.adapter.soc(vid)
                try:
                    response = self.adapter.step(vid, candidate.cabinet.id, setpoint, minutes)
                    soc = self.adapter.soc(vid)
                    kw, energy = response.actual_output_kw, response.battery_kwh
                    validate_response(cfg, s.vehicle, minutes, setpoint, before, soc, kw, energy)
                except ConstraintViolationError as exc:
                    violations.append(str(exc))
                    self._after_apply_violation(exc)
                    continue
                # EV2Gym floating-point arithmetic can produce a tiny negative at zero headroom.
                actual[vid] = max(0.0, kw)
                s.delivered_battery_kwh += max(0.0, energy)
                s.delivered_grid_kwh += actual[vid] * minutes / 60 / cfg.conversion
                output = actual[vid] * minutes / 60
                self.output_kwh[vid] = self.output_kwh.get(vid, 0.0) + output
                if self.now < s.vehicle.departure:
                    self.output_by_deadline_kwh[vid] = self.output_by_deadline_kwh.get(vid, 0.0) + output
                requested[vid] = held if single else setpoint
                allowed[vid] = candidate.allowed_kw
                energy_kw_minutes[vid] = energy_kw_minutes.get(vid, 0.0) + actual[vid] * minutes
                last_actual[vid] = actual[vid]
                stored[vid] = stored.get(vid, 0.0) + max(0.0, energy)
                if soc >= s.vehicle.target - SOC_TOL:
                    s.state = "FINISHED"
                    s.completed_at = end
                    completed.append(vid)
                    self.emit(end, "CHARGE_COMPLETED", s.vehicle, connector=s.connector, effective_time=clock(end))
            hard_kw = assigned_kw if self.strict and assigned_kw is not None else step_limits.zone_output_kw
            try:
                guard(cfg, step_candidates, actual, hard_kw, limits=step_limits)
            except ConstraintViolationError as exc:
                violations.append(str(exc))
                self._after_apply_violation(exc)
            budget = assigned_kw if assigned_kw is not None else self.active_budget_kw
            if not self.strict and budget:
                for zone, cap in budget.items():
                    total = sum(kw for vid, kw in actual.items() if step_candidates[vid].cabinet.zone == zone)
                    if total > cap + TOL:
                        deviation[zone] = max(deviation.get(zone, 0.0), total - cap)
            self.now = end
            self.state_version += 1
            steps += 1
            if stop_on_completion and completed:
                break
        if deviation:
            self.budget_deviation_count += 1
            LOGGER.warning("minute=%s actual zone output above the assigned budget: %s", start, deviation)
        duration = self.now - start
        if steps == 1:
            actual_kw = last_actual
        else:
            actual_kw = {vid: value / duration for vid, value in energy_kw_minutes.items()}
        return AppliedResult(
            minute=start,
            end=self.now,
            physics_step_minutes=duration if step is None else step,
            requested_kw=requested,
            allowed_kw=allowed,
            actual_kw=actual_kw,
            stored_kwh=stored,
            completed=tuple(completed),
            violations=tuple(violations),
            budget_deviation_kw=deviation,
            state_version=self.state_version,
        )


class HybridSimulator(StationKernel):
    """Offline runtime: the kernel plus trace, frames, events and the report."""

    def __init__(
        self,
        scenario: Scenario,
        policy: SchedulingPolicy | None = None,
        adapter_factory=EV2GymAdapter,
        *,
        algorithms: Algorithms | None = None,
        record_decisions: bool = False,
        time: TimeConfig | None = None,
        policy_id: str = "custom",
        policy_version: str = "1",
    ):
        resolved = default_algorithms() if algorithms is None else algorithms
        adapter = (
            adapter_factory(scenario)
            if algorithms is None
            else adapter_factory(scenario, dc_model=resolved.dc_charging_model)
        )
        super().__init__(
            scenario,
            adapter,
            QueueController(scenario),
            resolved,
            policy=policy,
            time=time,
            strict=True,
            policy_id=policy_id,
            policy_version=policy_version,
        )
        self.events = []
        self.frames = []
        self.trace = []
        self.decision_trace = []
        self.decision_latency_ms = []
        self.applied_results: list[AppliedResult] = []
        self._decision_labels = algorithm_labels(self.algorithms, policy) if record_decisions else None

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

    def step(self) -> None:
        if self._constraint_failure:
            raise RuntimeError("Constraint failure stopped this simulation; start a new run")
        if self.finished:
            raise RuntimeError("Simulation horizon reached")
        cfg = self.scenario
        started = perf_counter() if self._decision_labels is not None else None
        self.observe()
        proposal = self.propose()
        approved = self.approve(proposal)
        if started is not None:
            self.decision_latency_ms.append(
                {
                    "minute": self.now,
                    "decision_ms": (perf_counter() - started) * 1000,
                    "solver_ms": dict(proposal.solver_ms),
                }
            )
        self.apply_approved(approved)
        frame = self._frame()
        candidates = proposal.candidates
        compatible = self.time.compatibility
        result = self.advance(
            proposal.interval_end,
            candidates=candidates if compatible else None,
            limits=proposal.effective_limits if compatible else None,
            assigned_kw=proposal.budgets.output_kw,
            stop_on_completion=not compatible,
        )
        self.applied_results.append(result)
        end = result.end
        minutes = end - proposal.minute
        for vid in candidates:
            self.setpoints.pop(vid, None)
        power_by_vehicle = {
            vid: {
                "requested_output_kw": result.requested_kw.get(vid, approved.setpoints_kw.get(vid, 0.0)),
                "allowed_output_kw": candidate.allowed_kw,
                "actual_output_kw": result.actual_kw.get(vid, 0.0),
            }
            for vid, candidate in candidates.items()
        }
        stored_by_vehicle = {vid: result.stored_kwh.get(vid, 0.0) for vid in candidates}
        totals = {
            zone: sum(
                row["actual_output_kw"] for vid, row in power_by_vehicle.items() if candidates[vid].cabinet.zone == zone
            )
            for zone in cfg.zone_kw
        }
        power = {
            "ac_output_kw": totals["AC"],
            "dc_output_kw": totals["DC"],
            "grid_input_kw": sum(totals.values()) / cfg.conversion,
        }
        if self._decision_labels is not None:
            observation = proposal.observation
            if minutes != observation.interval_minutes:
                observation = replace(observation, interval_minutes=minutes)
            self.decision_trace.append(
                decision_record(
                    observation,
                    proposal.dispatch,
                    proposal.assignments,
                    proposal.demand,
                    proposal.budgets,
                    self._decision_labels,
                    power_by_vehicle,
                    stored_by_vehicle,
                    proposal.diagnostics,
                )
            )
        for vid, row in frame["vehicles"].items():
            row.update(power_by_vehicle.get(vid, ZERO_POWER))
        self.frames.append({**frame, **power, "duration_minutes": minutes})
        self.trace.append(
            {
                "time": clock(proposal.minute),
                "minute": proposal.minute,
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
        if self.finished:
            self.observe()
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
