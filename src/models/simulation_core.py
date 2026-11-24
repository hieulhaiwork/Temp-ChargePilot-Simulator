"""Validated single source of truth for the offline hybrid simulator."""

from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType


def minute(clock: str) -> int:
    hour, minute_of_hour = map(int, clock.split(":"))
    if hour < 0 or not 0 <= minute_of_hour < 60:
        raise ValueError(f"Invalid clock: {clock}; use 24:xx after midnight")
    return hour * 60 + minute_of_hour


def clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def number(value, name, lower=0, upper=float("inf")) -> float:
    if type(value) not in (int, float) or not isfinite(value) or not lower <= value <= upper:
        raise ValueError(f"Invalid {name}: {value}")
    return float(value)


def integer(value, name, minimum=1) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def identifier(value, name) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing {name}")
    return value


@dataclass(frozen=True)
class Cabinet:
    id: str
    zone: str
    ports: int
    port_kw: float
    output_kw: float


@dataclass(frozen=True)
class Vehicle:
    id: str
    zone: str
    arrival: int
    departure: int
    battery_kwh: float
    initial_soc: float
    target: float
    max_kw: float
    vehicle_model: str | None = None


@dataclass(frozen=True)
class LimitEvent:
    effective_minute: int
    announced_minute: int
    grid_input_kw: float | None
    cabinet_output_kw: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cabinet_output_kw", MappingProxyType(dict(self.cabinet_output_kw)))


@dataclass(frozen=True)
class Tariff:
    currency: str
    starts: tuple[int, ...]
    prices: tuple[float, ...]

    def price_at(self, minute: int) -> float:
        return self.prices[bisect_right(self.starts, minute) - 1]


@dataclass(frozen=True)
class Scenario:
    id: str
    start: int
    end: int
    timestep: int
    delay: int
    conversion: float
    efficiency: float
    grid_kw: float
    zone_kw: Mapping[str, float]
    cabinets: tuple[Cabinet, ...]
    vehicles: tuple[Vehicle, ...]
    physical_zone_cap_kw: Mapping[str, float] | None = None
    independent_grid_input_limit_kw: Mapping[str, float] | None = None
    limit_events: tuple[LimitEvent, ...] = ()
    tariff: Tariff | None = None

    def __post_init__(self) -> None:
        # Freeze a copy so callers cannot retain a mutable reference to the limits.
        object.__setattr__(self, "zone_kw", MappingProxyType(dict(self.zone_kw)))
        object.__setattr__(self, "cabinets", tuple(self.cabinets))
        object.__setattr__(self, "vehicles", tuple(self.vehicles))
        object.__setattr__(self, "limit_events", tuple(self.limit_events))
        for field in ("physical_zone_cap_kw", "independent_grid_input_limit_kw"):
            values = getattr(self, field)
            if values is not None:
                object.__setattr__(self, field, MappingProxyType(dict(values)))

    @property
    def default_zone_budget_kw(self) -> Mapping[str, float]:
        return self.zone_kw

    @property
    def coordinated_limits(self) -> bool:
        return (
            self.physical_zone_cap_kw is not None
            or self.independent_grid_input_limit_kw is not None
            or bool(self.limit_events)
        )

    @classmethod
    def parse(cls, config: dict) -> "Scenario":
        start = minute(config["start_time"])
        end = start + integer(config["duration_minutes"], "duration_minutes")
        steps = [integer(config[key], key) for key in ("timestep_minutes", "step_minutes") if key in config]
        if len(set(steps)) > 1:
            raise ValueError("timestep_minutes and step_minutes disagree")
        step = steps[0] if steps else 1
        delay = integer(config["dc_unplug_delay_minutes"], "dc_unplug_delay_minutes", 0)
        if config.get("ac_unplug_policy", "declared_departure") != "declared_departure":
            raise ValueError("AC unplug policy must be declared_departure")
        conversion = number(config["power_conversion_efficiency"], "power_conversion_efficiency", upper=1)
        efficiency = number(config["charging_efficiency"], "charging_efficiency", upper=1)
        if not conversion or not efficiency:
            raise ValueError("Efficiencies must be positive")
        independent = _optional_zone_values(config, "independent_grid_input_limit_kw")
        if independent is None:
            grid_kw = number(config["grid_input_limit_kw"], "grid_input_limit_kw")
        else:
            grid_kw = number(sum(independent.values()), "aggregate independent grid input")
        legacy = {zone: config.get(f"{zone.lower()}_power_budget_kw") for zone in ("AC", "DC")}
        budgets = _zone_values(config.get("default_zone_budget_kw", legacy), "default_zone_budget_kw")
        if any(
            value is not None and number(value, f"{zone} budget") != budgets[zone] for zone, value in legacy.items()
        ):
            raise ValueError("Legacy zone budgets and default_zone_budget_kw disagree")
        physical = _optional_zone_values(config, "physical_zone_cap_kw")
        if physical is not None and any(budgets[zone] > physical[zone] for zone in budgets):
            raise ValueError("Fixed zone budgets exceed physical zone caps")
        if independent is not None and any(budgets[zone] > independent[zone] * conversion + 1e-9 for zone in budgets):
            raise ValueError("Fixed zone budgets exceed independent grid inputs after conversion")
        if independent is None and sum(budgets.values()) > grid_kw * conversion + 1e-9:
            raise ValueError("Fixed zone budgets exceed available grid input after conversion")
        cabinets = []
        for item in config["charger_cabinets"]:
            cid = identifier(item["id"], "cabinet ID")
            zone = item["zone"]
            if zone not in budgets:
                raise ValueError(f"Invalid zone for {cid}: {zone}")
            port_kw = number(item["port_limit_kw"], "port_limit_kw")
            output_kw = number(item["cabinet_output_limit_kw"], "cabinet_output_limit_kw")
            cabinets.append(Cabinet(cid, zone, integer(item["ports"], "ports"), port_kw, output_kw))
        if len({cab.id for cab in cabinets}) != len(cabinets):
            raise ValueError("Duplicate cabinet IDs")
        events = _limit_events(config.get("limit_events", []), start, end, cabinets, grid_kw, independent is not None)
        # An explicitly configured runtime schedule uses the online interval even before any announcements.
        if "limit_events" in config and physical is None:
            physical = budgets
        tariff = _tariff(config["tou_tariff"], start, end) if "tou_tariff" in config else None
        vehicles = []
        for item in config["vehicles"]:
            vid = identifier(item["id"], "vehicle ID")
            zone = item["zone"]
            if zone not in {cab.zone for cab in cabinets}:
                raise ValueError(f"No cabinet for {vid} in zone {zone}")
            arrival, departure = minute(item["arrival"]), minute(item["departure"])
            if not start <= arrival < end:
                raise ValueError(f"{vid}: arrival must be within scenario horizon [start, end)")
            if departure <= arrival:
                raise ValueError(f"{vid}: departure must be after arrival")
            initial = number(item["initial_soc"], "initial_soc", upper=1)
            target = number(item["target_soc"], "target_soc", upper=1)
            capacity = number(item.get("battery_kwh"), f"{vid} battery_kwh")
            if initial >= target or not capacity:
                raise ValueError(f"{vid}: require initial_soc < target_soc and positive capacity")
            max_kw = number(item[f"max_{zone.lower()}_kw"], f"{vid} vehicle cap")
            model = identifier(item["vehicle_model"], f"{vid} vehicle_model") if "vehicle_model" in item else None
            vehicles.append(Vehicle(vid, zone, arrival, departure, capacity, initial, target, max_kw, model))
        if len({v.id for v in vehicles}) != len(vehicles):
            raise ValueError("Duplicate vehicle IDs")
        return cls(
            identifier(config["scenario_id"], "scenario_id"),
            start,
            end,
            step,
            delay,
            conversion,
            efficiency,
            grid_kw,
            budgets,
            tuple(cabinets),
            tuple(sorted(vehicles, key=lambda v: v.id)),
            physical,
            independent,
            events,
            tariff,
        )


def _zone_values(values, label) -> dict[str, float]:
    if not isinstance(values, Mapping) or values.keys() != {"AC", "DC"}:
        raise ValueError(f"{label} must map exactly AC and DC to kW")
    return {zone: number(values[zone], f"{label}.{zone}") for zone in ("AC", "DC")}


def _optional_zone_values(config: dict, key: str) -> dict[str, float] | None:
    return _zone_values(config[key], key) if key in config else None


def _limit_events(rows, start, end, cabinets, grid_kw, independent) -> tuple[LimitEvent, ...]:
    if not isinstance(rows, list):
        raise ValueError("limit_events must be a list")
    maxima = {cab.id: cab.output_kw for cab in cabinets}
    events = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.keys() - {
            "effective_at",
            "announced_at",
            "grid_input_limit_kw",
            "cabinet_output_limit_kw",
        }:
            raise ValueError("Invalid limit event fields")
        when = minute(row["effective_at"])
        announced = minute(row.get("announced_at", row["effective_at"]))
        if not start <= when < end or announced > when:
            raise ValueError("Limit events require announcement by the effective time within the scenario horizon")
        site = None
        changes = row.get("cabinet_output_limit_kw", {})
        if not isinstance(changes, dict) or changes.keys() - maxima.keys():
            raise ValueError("Limit event contains an unknown cabinet")
        keys = {(when, "cabinet", key) for key in changes}
        if "grid_input_limit_kw" in row:
            if independent:
                raise ValueError("Shared grid limits require shared supply")
            site = number(row["grid_input_limit_kw"], "event grid input", upper=grid_kw)
            keys.add((when, "site", ""))
        if not keys or keys & seen:
            raise ValueError("Empty or conflicting limit event")
        seen.update(keys)
        events.append(
            LimitEvent(
                when,
                announced,
                site,
                {key: number(value, f"event cabinet {key}", upper=maxima[key]) for key, value in changes.items()},
            )
        )
    return tuple(sorted(events, key=lambda event: event.effective_minute))


def _tariff(config, start, end) -> Tariff:
    if not isinstance(config, dict) or config.keys() != {"currency", "periods"}:
        raise ValueError("tou_tariff requires currency and periods")
    rows = config["periods"]
    if (
        not isinstance(rows, list)
        or not rows
        or any(not isinstance(row, dict) or row.keys() != {"start", "price_per_kwh"} for row in rows)
    ):
        raise ValueError("tou_tariff periods require start and price_per_kwh")
    starts = tuple(minute(row["start"]) for row in rows)
    if starts[0] != start or starts[-1] >= end or starts != tuple(sorted(set(starts))):
        raise ValueError("Tariff periods must start at the scenario start and increase within the horizon")
    return Tariff(
        identifier(config["currency"], "tariff currency"),
        starts,
        tuple(number(row["price_per_kwh"], "tariff price_per_kwh") for row in rows),
    )
