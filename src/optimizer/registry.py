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

# ---- Danh mục policy có version (Final Review 4.1) -------------------------------------------------------------
# `POLICIES` ở trên vẫn là bảng thành phần duy nhất; phần dưới chỉ THÊM id + version + đăng ký policy mới, để backend
# (hybrid_planner / runtime / simulation_service / API) tra policy từ đây thay vì danh sách cứng.
FROZEN_POLICY_IDS = ("B0", "M2b", "M3a", "M3b")  # đóng băng MVP-2/3: không ghi đè, không gỡ, version "1"
POLICY_VERSIONS: dict[str, str] = dict.fromkeys(FROZEN_POLICY_IDS, "1")
POLICY_DESCRIPTIONS: dict[str, str] = {
    "B0": "FCFS + Equal Share AC/DC + Fixed Share",
    "M2b": "LLF + DC rolling LP + Fixed Share",
    "M3a": "LLF + AC/DC LP + Fixed Share",
    "M3b": "LLF + AC/DC LP + Dynamic Slack",
}


@dataclass(frozen=True)
class PolicySpec:
    """Một policy đã đăng ký: id, version, và bốn thành phần (khoá của DISPATCH / OPTIMIZERS / COORDINATORS)."""

    id: str
    version: str
    dispatch_dc: str
    optimizer_ac: str
    optimizer_dc: str
    coordinator: str
    description: str = ""

    @property
    def components(self) -> tuple[str, str, str, str]:
        return (self.dispatch_dc, self.optimizer_ac, self.optimizer_dc, self.coordinator)

    @property
    def frozen(self) -> bool:
        return self.id in FROZEN_POLICY_IDS


class UnknownPolicyError(KeyError):
    """Id policy không có trong registry."""


def policy_spec(policy_id: str) -> PolicySpec:
    """Tra policy theo id (đọc thẳng `POLICIES` ⇒ cấu hình nạp lúc khởi động / test monkeypatch đều thấy)."""
    if policy_id not in POLICIES:
        raise UnknownPolicyError(policy_id)
    return PolicySpec(
        policy_id,
        POLICY_VERSIONS.get(policy_id, "1"),
        *POLICIES[policy_id],
        description=POLICY_DESCRIPTIONS.get(policy_id, ""),
    )


def policy_specs() -> list[PolicySpec]:
    """Mọi policy hợp lệ theo thứ tự đăng ký (B0 / M2b / M3a / M3b trước)."""
    return [policy_spec(policy_id) for policy_id in POLICIES]


def register_policy(spec: PolicySpec) -> PolicySpec:
    """Đăng ký một policy MỚI ghép từ thành phần đã có. Không ghi đè id đã có (kể cả B0–M3b)."""
    if not spec.id or not isinstance(spec.id, str):
        raise ValueError("policy id phải là chuỗi khác rỗng")
    if spec.id in POLICIES:
        raise ValueError(f"policy {spec.id!r} đã đăng ký — đặt id mới thay vì ghi đè (baseline giữ nguyên nghĩa)")
    if not spec.version:
        raise ValueError("policy version phải khác rỗng")
    for name, table, field in (
        (spec.dispatch_dc, DISPATCH, "dispatch_dc"),
        (spec.optimizer_ac, OPTIMIZERS, "optimizer_ac"),
        (spec.optimizer_dc, OPTIMIZERS, "optimizer_dc"),
        (spec.coordinator, COORDINATORS, "coordinator"),
    ):
        if name not in table:
            raise ValueError(f"{field}={name!r} chưa đăng ký. Có: {', '.join(table)}")
    POLICIES[spec.id] = spec.components
    POLICY_VERSIONS[spec.id] = spec.version
    POLICY_DESCRIPTIONS[spec.id] = spec.description
    return policy_spec(spec.id)


def unregister_policy(policy_id: str) -> None:
    """Gỡ policy đã đăng ký thêm (dọn sau test / thí nghiệm). Policy đóng băng không gỡ được."""
    if policy_id in FROZEN_POLICY_IDS:
        raise ValueError(f"policy {policy_id!r} là bản đóng băng — không gỡ")
    POLICIES.pop(policy_id, None)
    POLICY_VERSIONS.pop(policy_id, None)
    POLICY_DESCRIPTIONS.pop(policy_id, None)
