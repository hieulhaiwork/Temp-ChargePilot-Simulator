"""MỘT registry thuật toán điều phối / lập lịch dùng chung cho simulator standalone, backend và benchmark (ADR-019).

Định nghĩa được chuyển NGUYÊN VĂN từ `src/simulator/src/algorithms.py` (registry) và `src/simulator/benchmark_mvp3.py`
(bảng policy). Phần ghép với vật lý (`Algorithms`, `DC_MODELS`, `resolve_algorithms`) ở lại simulator vì chọn DC
charging model là việc của lõi vật lý, và optimizer không được import simulator.

Thêm thuật toán: viết class đúng Protocol trong `src.models.scheduling`, đăng ký ở DISPATCH / OPTIMIZERS / COORDINATORS.
Thêm policy: thêm khoá mới vào POLICIES (B0 / M2b / M3a / M3b là bản đóng băng để tái lập số MVP-2/3 — không sửa).
"""

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from src.models.scheduling.dispatch import DispatchPolicy
from src.models.simulation_core import Scenario
from src.optimizer.coordination.dynamic_slack import DynamicSlackCoordinator
from src.optimizer.coordination.fixed_budget import FixedBudgetCoordinator, FixedShareCoordinator
from src.optimizer.dispatch.arrival_order import arrival_order
from src.optimizer.dispatch.edf import earliest_deadline
from src.optimizer.dispatch.least_laxity import least_laxity
from src.optimizer.zones.ac_lp import FORECAST as AC_FORECAST
from src.optimizer.zones.ac_lp import ACConfig, ACRollingLP
from src.optimizer.zones.deadline_first import deadline_first
from src.optimizer.zones.equal_share import zone_equal_share
from src.optimizer.zones.rolling_lp import FORECAST, SAMPLE_COUNT, LPConfig, RollingHorizonLP


@dataclass(frozen=True)
class Registration:
    implementation: Callable
    version: str = "1"
    parameters: tuple[str, ...] = ()
    configure: Callable[[dict, Scenario], tuple[Any, dict]] | None = None

    def build(self, supplied: dict, scenario: Scenario) -> tuple[Any, dict]:
        if self.configure is None:
            return self.implementation, {"parameters": supplied}
        return self.configure(supplied, scenario)


def _fixed_budget(
    params: dict, scenario: Scenario, factory=FixedBudgetCoordinator
) -> tuple[FixedBudgetCoordinator, dict]:
    output_kw = params.get("output_kw", scenario.default_zone_budget_kw)
    if not isinstance(output_kw, Mapping):
        raise ValueError("coordinator.parameters.output_kw must map AC/DC to output kW")
    return factory(output_kw), {"parameters": {"output_kw": dict(output_kw)}}


def _fixed_share(params: dict, scenario: Scenario) -> tuple[FixedBudgetCoordinator, dict]:
    return _fixed_budget(params, scenario, FixedShareCoordinator)


def _dynamic_slack(params: dict, scenario: Scenario) -> tuple[DynamicSlackCoordinator, dict]:
    return DynamicSlackCoordinator(), {
        "parameters": {},
        "shared_order": ["deadline_headroom", "fixed_reservation", "shared_slack"],
    }


def _rolling_lp(params: dict, scenario: Scenario) -> tuple[RollingHorizonLP, dict]:
    config = LPConfig(**params)
    return RollingHorizonLP(config), {
        "parameters": asdict(config),
        "solver": "scipy.optimize.linprog(method=highs)",
        "forecast": {**FORECAST, "acceptance_samples": SAMPLE_COUNT},
        "nonoptimal_result": "fallback_equal_share",
    }


def _llf(params: dict, scenario: Scenario) -> tuple[DispatchPolicy, dict]:
    return least_laxity, {
        "parameters": {},
        "laxity": "optimistic_ignores_taper_and_shared_demand",
        "negative_laxity_order": "after_feasible_then_smallest_deficit_first",
    }


def _ac_rolling_lp(params: dict, scenario: Scenario) -> tuple[ACRollingLP, dict]:
    config = ACConfig(**params)
    return ACRollingLP(config), {
        "parameters": asdict(config),
        "solver": "scipy.optimize.linprog(method=highs)",
        "objectives": ["minimum_total_shortfall_kwh", "minimum_tou_grid_cost"],
        "forecast": AC_FORECAST,
        "nonoptimal_result": "fallback_equal_share",
    }


DISPATCH = {
    "fifo": Registration(arrival_order),
    "fcfs": Registration(arrival_order),
    "edf": Registration(earliest_deadline),
    "llf": Registration(least_laxity, configure=_llf),
}
OPTIMIZERS = {
    "equal_share": Registration(zone_equal_share),
    "deadline_first": Registration(deadline_first),
    "rolling_lp": Registration(RollingHorizonLP, parameters=tuple(asdict(LPConfig())), configure=_rolling_lp),
    "ac_rolling_lp": Registration(ACRollingLP, parameters=tuple(asdict(ACConfig())), configure=_ac_rolling_lp),
}
COORDINATORS = {
    "fixed_budget": Registration(FixedBudgetCoordinator, parameters=("output_kw",), configure=_fixed_budget),
    "fixed_share": Registration(FixedShareCoordinator, parameters=("output_kw",), configure=_fixed_share),
    "dynamic_slack": Registration(DynamicSlackCoordinator, configure=_dynamic_slack),
}

# Policy bundles: (dispatch DC, optimizer AC, optimizer DC, coordinator). Frozen for MVP-2/3 reproducibility.
POLICIES = {
    "B0": ("fcfs", "equal_share", "equal_share", "fixed_share"),
    "M2b": ("llf", "equal_share", "rolling_lp", "fixed_share"),
    "M3a": ("llf", "ac_rolling_lp", "rolling_lp", "fixed_share"),
    "M3b": ("llf", "ac_rolling_lp", "rolling_lp", "dynamic_slack"),
}
