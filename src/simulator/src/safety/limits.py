"""Canonical interval limits for coordination, optimization and validation."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from ..scenario import Scenario


@dataclass(frozen=True)
class EffectiveLimits:
    minute: int
    conversion: float
    grid_input_kw: float
    zone_output_kw: Mapping[str, float]
    cabinet_output_kw: Mapping[str, float]
    independent_grid_input_kw: Mapping[str, float] | None

    def __post_init__(self) -> None:
        for name in ("zone_output_kw", "cabinet_output_kw", "independent_grid_input_kw"):
            values = getattr(self, name)
            if values is not None:
                object.__setattr__(self, name, MappingProxyType(dict(values)))

    @property
    def shared_supply(self) -> bool:
        return self.independent_grid_input_kw is None

    @property
    def site_output_kw(self) -> float:
        return self.grid_input_kw * self.conversion

    def zone_capacity_kw(self, zone: str) -> float:
        grid = self.grid_input_kw if self.shared_supply else self.independent_grid_input_kw[zone]
        return min(self.zone_output_kw[zone], grid * self.conversion)

    def as_optimizer_scenario(self, scenario: Scenario) -> Scenario:
        """Project current caps into the unchanged zone optimizer contract."""
        if not scenario.coordinated_limits:
            return scenario
        return replace(
            scenario,
            grid_kw=self.grid_input_kw,
            zone_kw={zone: self.zone_capacity_kw(zone) for zone in self.zone_output_kw},
            cabinets=tuple(replace(cab, output_kw=self.cabinet_output_kw[cab.id]) for cab in scenario.cabinets),
        )


def effective_limits(scenario: Scenario, minute: int) -> EffectiveLimits:
    independent = scenario.independent_grid_input_limit_kw
    grid = scenario.grid_kw if independent is None else sum(independent.values())
    cabinets = {cab.id: cab.output_kw for cab in scenario.cabinets}
    for event in scenario.limit_events:
        if event.effective_minute > minute:
            break
        if event.grid_input_kw is not None:
            grid = event.grid_input_kw
        cabinets.update(event.cabinet_output_kw)
    return EffectiveLimits(
        minute,
        scenario.conversion,
        grid,
        scenario.physical_zone_cap_kw or scenario.zone_kw,
        cabinets,
        independent,
    )


def environment_boundary(scenario: Scenario, now: int, until: int, *, online: bool) -> int:
    if scenario.tariff is not None:
        until = min((start for start in scenario.tariff.starts if now < start < until), default=until)
    for event in scenario.limit_events:
        if online and event.announced_minute > now:
            continue
        if now < event.announced_minute < until:
            until = event.announced_minute
        if now < event.effective_minute < until:
            until = event.effective_minute
    return until
