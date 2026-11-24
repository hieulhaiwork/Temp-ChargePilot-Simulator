"""Fork isolation of the kernel's pluggable components (Final Review §4.4).

`StationKernel.fork()` (admission / WHAT-IF) must never let the copy change the live kernel. Rule:

    share   only components DECLARED immutable / stateless: listed in `STATELESS` below (functions by identity,
            classes by exact type — a subclass may add state) or whose class sets `__stateless__ = True`;
    fork    a component with a `fork()` method → `component.fork()` (its own snapshot rule);
    copy    anything else → `copy.deepcopy` (safe default for undeclared / stateful components).

Python's `copy` returns plain functions / lambdas / closures unchanged: a component whose state lives in a closure
cannot be isolated by copying and must be an object with `fork()` (or a declared-stateless function).

The listing below is a reviewed fact about the CURRENT code (no attribute is ever assigned after construction; frozen
dataclasses or plain functions), so the fork shares exactly what it shared before this module existed.
"""

import copy
from dataclasses import replace

from src.models.scheduling.observations import PerfectObservation
from src.optimizer.coordination.dynamic_slack import DynamicSlackCoordinator
from src.optimizer.coordination.fixed_budget import FixedBudgetCoordinator, FixedShareCoordinator
from src.optimizer.dispatch.arrival_order import arrival_order
from src.optimizer.dispatch.edf import earliest_deadline
from src.optimizer.dispatch.least_laxity import least_laxity
from src.optimizer.zones.ac_lp import ACRollingLP
from src.optimizer.zones.deadline_first import deadline_first
from src.optimizer.zones.equal_share import equal_share_policy, zone_equal_share
from src.optimizer.zones.rolling_lp import RollingHorizonLP

from .algorithms import Algorithms
from .charging_models.synthetic_dc import SyntheticTaperV1
from .charging_models.vehicle_profiles import VehicleProfilesDCModel

# Reviewed stateless components (functions: by identity; classes: instances of exactly this type).
STATELESS = frozenset(
    {
        # dispatch (plain functions)
        arrival_order,
        earliest_deadline,
        least_laxity,
        # zone optimizers / combined policies (plain functions, frozen dataclasses)
        zone_equal_share,
        equal_share_policy,
        deadline_first,
        RollingHorizonLP,
        ACRollingLP,
        # coordinators (frozen dataclasses / no attributes)
        FixedBudgetCoordinator,
        FixedShareCoordinator,
        DynamicSlackCoordinator,
        # DC charging models (frozen dataclasses, read-only lookups)
        SyntheticTaperV1,
        VehicleProfilesDCModel,
        # observation (identity)
        PerfectObservation,
    }
)


def is_shared(component) -> bool:
    """True when the component is declared immutable / stateless and may be shared between live and fork."""
    if component is None:
        return True
    try:
        if component in STATELESS:
            return True
    except TypeError:  # unhashable component: never in the set
        pass
    return type(component) in STATELESS or getattr(type(component), "__stateless__", False) is True


def fork_component(component, memo: dict):
    """The fork's version of `component`. `memo` (id → copy) keeps one copy per shared object, like `deepcopy`."""
    key = id(component)
    if key in memo:
        return memo[key]
    if is_shared(component):
        result = component
    elif callable(getattr(component, "fork", None)):
        result = component.fork()
    else:
        result = copy.deepcopy(component, memo)
    memo[key] = result
    return result


def isolated_algorithms(algorithms: Algorithms, memo: dict) -> Algorithms:
    """Algorithms of the fork: the SAME object when every component is shared (no behaviour change)."""
    dispatch = {zone: fork_component(policy, memo) for zone, policy in algorithms.dispatch.items()}
    optimizers = {zone: fork_component(optimizer, memo) for zone, optimizer in algorithms.optimizers.items()}
    coordinator = fork_component(algorithms.coordinator, memo)
    dc_model = fork_component(algorithms.dc_charging_model, memo)
    unchanged = (
        all(dispatch[zone] is policy for zone, policy in algorithms.dispatch.items())
        and all(optimizers[zone] is optimizer for zone, optimizer in algorithms.optimizers.items())
        and coordinator is algorithms.coordinator
        and dc_model is algorithms.dc_charging_model
    )
    if unchanged:
        return algorithms
    return replace(
        algorithms, dispatch=dispatch, optimizers=optimizers, coordinator=coordinator, dc_charging_model=dc_model
    )
