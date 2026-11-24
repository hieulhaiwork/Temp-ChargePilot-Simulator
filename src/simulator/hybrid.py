"""Offline hybrid runtime (CLI, benchmark MVP-1/2/3, golden, DecisionTrace) on the one station kernel (ADR-019).

`HybridSimulator` is `StationKernel` (`src/simulator/core/kernel.py`) plus trace / frame / event / report recording.
The backend station (`hybrid_station.py`) drives the same kernel.
"""

from dataclasses import replace
from time import perf_counter

from src.models.decisions import AppliedResult, TimeConfig
from src.models.scheduling.observations import ObservationModel
from src.models.scheduling.optimization import SchedulingPolicy
from src.models.simulation_core import Scenario, clock

from .core.algorithms import Algorithms, algorithm_labels, default_algorithms
from .core.ev2gym_adapter import EV2GymAdapter
from .core.kernel import StationKernel
from .core.queue import QueueController
from .evaluation.metrics import summarize
from .evaluation.trace import decision_record

ZERO_POWER = dict.fromkeys(("requested_output_kw", "allowed_output_kw", "actual_output_kw"), 0.0)


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
        observation_model: ObservationModel | None = None,
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
            observation_model=observation_model,
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
