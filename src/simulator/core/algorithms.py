"""Composition and explicit JSON registry for the modular simulator."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType

from src.guard.physical.validator import guard
from src.models.charging_physics import DCChargingModel
from src.models.physical_constraints import TOL
from src.models.scheduling.coordination import GlobalCoordinator
from src.models.scheduling.dispatch import DispatchPolicy
from src.models.scheduling.optimization import SchedulingPolicy, ZonePowerOptimizer
from src.models.simulation_core import Scenario
from src.optimizer.coordination.fixed_budget import FixedBudgetCoordinator
from src.optimizer.dispatch.arrival_order import arrival_order
from src.optimizer.registry import COORDINATORS, DISPATCH, OPTIMIZERS, Registration
from src.optimizer.zones.equal_share import zone_equal_share

from .charging_models.synthetic_dc import SyntheticTaperV1
from .charging_models.vehicle_profiles import INTEGRATION_SECONDS, PROFILE_VERSION, VehicleProfilesDCModel

ZONES = ("AC", "DC")


@dataclass(frozen=True)
class Algorithms:
    dispatch: Mapping[str, DispatchPolicy]
    optimizers: Mapping[str, ZonePowerOptimizer]
    coordinator: GlobalCoordinator
    dc_charging_model: DCChargingModel

    def __post_init__(self) -> None:
        for name in ("dispatch", "optimizers"):
            entries = dict(getattr(self, name))
            if entries.keys() != set(ZONES):
                raise ValueError(f"{name} must have exactly AC and DC entries")
            object.__setattr__(self, name, MappingProxyType(entries))


def default_algorithms() -> Algorithms:
    return Algorithms(
        dict.fromkeys(ZONES, arrival_order),
        dict.fromkeys(ZONES, zone_equal_share),
        FixedBudgetCoordinator(),
        SyntheticTaperV1(),
    )


def _synthetic_taper(params: dict, scenario: Scenario) -> tuple[SyntheticTaperV1, dict]:
    model = SyntheticTaperV1()
    return model, {
        "parameters": asdict(model),
        "provenance": "ChargePilot synthetic SOC taper",
        "observed_vs_estimated": "synthetic_assumption",
        "validity": {"soc_fraction": [0.0, 1.0], "scope": "offline simulation; no hardware calibration"},
    }


def _vehicle_profiles(params: dict, scenario: Scenario) -> tuple[VehicleProfilesDCModel, dict]:
    model = VehicleProfilesDCModel.from_scenario(scenario)
    return model, {
        "parameters": {"integration_seconds": INTEGRATION_SECONDS, "unlabelled_dc_fallback": "synthetic_taper_v1"},
        "provenance": "Per-vehicle research profiles from the ChargePilot DC model handoff",
        "observed_vs_estimated": "scenario_based_research_estimate",
        "validity": {"soc_fraction": [0.0, 1.0], "scope": "offline simulation; no hardware calibration"},
        "vehicle_profiles": {
            vehicle.id: model.metadata_for(vehicle) for vehicle in scenario.vehicles if vehicle.zone == "DC"
        },
    }


DC_MODELS = {
    "synthetic_taper_v1": Registration(SyntheticTaperV1, configure=_synthetic_taper),
    "vinfast_profiles_v0_1": Registration(VehicleProfilesDCModel, version=PROFILE_VERSION, configure=_vehicle_profiles),
}


def algorithm_labels(algorithms: Algorithms, combined: SchedulingPolicy | None = None) -> dict:
    def name(registry, choice):
        for label, entry in registry.items():
            if entry.implementation is choice or entry.implementation is type(choice):
                return label
        return getattr(choice, "__name__", type(choice).__name__)

    return {
        "dispatch": {
            zone: ("fifo" if zone == "AC" else "fcfs") if policy is arrival_order else name(DISPATCH, policy)
            for zone, policy in algorithms.dispatch.items()
        },
        "optimizers": {
            zone: name(OPTIMIZERS, combined if combined is not None else optimizer)
            for zone, optimizer in algorithms.optimizers.items()
        },
        "coordinator": name(COORDINATORS, algorithms.coordinator),
    }


def _choice(value, registry: Mapping[str, Registration], field: str) -> tuple[str, Registration, dict]:
    if isinstance(value, str):
        name, params = value, {}
    elif isinstance(value, dict) and value.keys() <= {"name", "parameters"}:
        name, params = value.get("name"), value.get("parameters", {})
    else:
        raise ValueError(f"{field} must be a name or an object with name and parameters")
    if not isinstance(name, str) or name not in registry:
        raise ValueError(f"Unknown {field}: {name!r}. Available: {', '.join(registry)}")
    entry = registry[name]
    if not isinstance(params, dict) or params.keys() - set(entry.parameters):
        raise ValueError(f"Unsupported parameters for {field} ({name})")
    return name, entry, params


def _metadata(name: str, entry: Registration, source: str, details: dict) -> dict:
    implementation = entry.implementation
    return {
        "name": name,
        "version": entry.version,
        "implementation": f"{implementation.__module__}.{implementation.__qualname__}",
        "config_source": source,
        **details,
    }


def resolve_algorithms(selection: dict, scenario: Scenario, source: str) -> tuple[Algorithms, dict]:
    fields = {"dispatch", "optimizers", "coordinator", "dc_charging_model", "physical_guard"}
    if not isinstance(selection, dict) or selection.keys() - fields:
        raise ValueError(f"Algorithms must be an object with supported keys: {', '.join(sorted(fields))}")

    dispatch, optimizers, metadata = {}, {}, {}
    for field, target, registry, defaults in (
        ("dispatch", dispatch, DISPATCH, {"AC": "fifo", "DC": "fcfs"}),
        ("optimizers", optimizers, OPTIMIZERS, dict.fromkeys(ZONES, "equal_share")),
    ):
        configured = selection.get(field, {})
        if not isinstance(configured, dict) or configured.keys() - set(ZONES):
            raise ValueError(f"{field} must map AC/DC to algorithm choices")
        metadata[field] = {}
        for zone in ZONES:
            name, entry, params = _choice(configured.get(zone, defaults[zone]), registry, f"{field}.{zone}")
            if zone != "DC" and name in {"llf", "rolling_lp"}:
                raise ValueError(f"{name} only supports DC")
            if zone != "AC" and name == "ac_rolling_lp":
                raise ValueError(f"{name} only supports AC")
            target[zone], details = entry.build(params, scenario)
            metadata[field][zone] = _metadata(name, entry, source if zone in configured else "default", details)

    name, entry, params = _choice(selection.get("coordinator", "fixed_budget"), COORDINATORS, "coordinator")
    coordinator, details = entry.build(params, scenario)
    metadata["coordinator"] = _metadata(name, entry, source if "coordinator" in selection else "default", details)
    name, entry, params = _choice(
        selection.get("dc_charging_model", "synthetic_taper_v1"), DC_MODELS, "dc_charging_model"
    )
    dc_model, details = entry.build(params, scenario)
    metadata["dc_charging_model"] = _metadata(
        name, entry, source if "dc_charging_model" in selection else "default", details
    )

    # The selection only verifies the identifier. The runtime always calls this guard.
    name, entry, _ = _choice(
        selection.get("physical_guard", "physical_v1"), {"physical_v1": Registration(guard)}, "physical_guard"
    )
    metadata["physical_guard"] = _metadata(
        name, entry, source if "physical_guard" in selection else "default", {"parameters": {"absolute_tolerance": TOL}}
    )
    return Algorithms(dispatch, optimizers, coordinator, dc_model), metadata
