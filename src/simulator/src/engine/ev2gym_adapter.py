"""EV2Gym component adapter. AC runs EV.step; DC adds only a battery step."""

from dataclasses import dataclass
from math import isfinite, sqrt
from numbers import Real

from ev2gym.models.ev import EV
from ev2gym.models.ev_charger import EV_Charger

from ..charging_models.base import DCChargingModel, VehicleBatteryState
from ..charging_models.synthetic_dc import SyntheticTaperV1
from ..safety.constraints import ConstraintViolationError
from ..scenario import Cabinet, Scenario, Vehicle


class PrecisionEV(EV):
    """Keep the native AC response without EV2Gym's upward 0.01 kWh rounding."""

    def my_ceil(self, capacity, precision=2):
        return capacity


class DCEV(PrecisionEV):
    """Synthetic DC response in kWh. Capacity and energy counters are supported.

    Native AC current, charge cycles, SOC history and degradation are outside
    the DC model. The adapter reports actual DC power from the stored energy.
    """

    def record_charge(self, stored: float) -> None:
        self.prev_capacity = self.current_capacity
        self.current_capacity += stored
        self.current_energy = stored
        self.total_energy_exchanged += stored
        self.abs_total_energy_exchanged += stored
        self.required_energy -= stored

    def get_battery_degradation(self):
        raise NotImplementedError("ChargePilot DC does not model EV2Gym battery degradation")


@dataclass(frozen=True)
class Delivered:
    actual_output_kw: float
    battery_kwh: float


class EV2GymAdapter:
    def __init__(self, scenario: Scenario, dc_model: DCChargingModel | None = None):
        self.efficiency = scenario.efficiency
        self.dc_model = SyntheticTaperV1() if dc_model is None else dc_model
        self.models = {v.id: self._vehicle(v, scenario) for v in scenario.vehicles}
        self.stations = {c.id: self._station(c, index) for index, c in enumerate(scenario.cabinets)}
        self._connections: dict[str, tuple[str, int]] = {}

    @staticmethod
    def _vehicle(v: Vehicle, scenario: Scenario) -> PrecisionEV:
        model = PrecisionEV if v.zone == "AC" else DCEV
        return model(
            id=None,  # EV2Gym owns the local port index; models is keyed by ChargePilot ID.
            location=None,
            battery_capacity=v.battery_kwh,
            desired_capacity=v.target * v.battery_kwh,
            battery_capacity_at_arrival=v.initial_soc * v.battery_kwh,
            time_of_arrival=v.arrival - scenario.start,
            time_of_departure=v.departure - scenario.start,
            max_ac_charge_power=v.max_kw if v.zone == "AC" else 0,
            max_dc_charge_power=v.max_kw if v.zone == "DC" else 0,
            charge_efficiency=scenario.efficiency,
            timescale=1,  # Native spawn's AFAP loop uses arrival/departure in minute offsets.
        )

    @staticmethod
    def _station(cab: Cabinet, index: int) -> EV_Charger:
        phases = 3 if cab.zone == "AC" else 1
        return EV_Charger(
            index,
            0,
            0,
            n_ports=cab.ports,
            charger_type=cab.zone,
            phases=phases,
            voltage=400,
            max_charge_current=cab.port_kw * 1000 / (400 * sqrt(phases)),
            timescale=1,
        )

    def _checked_station(self, cabinet: str) -> EV_Charger:
        station = self.stations[cabinet]
        expected = {
            port: self.models[vehicle_id] for vehicle_id, (key, port) in self._connections.items() if key == cabinet
        }
        if (
            len(station.evs_connected) != station.n_ports
            or station.n_evs_connected != len(expected)
            or any(
                ev is not expected.get(index) or (ev is not None and (ev.id != index or ev.location != station.id))
                for index, ev in enumerate(station.evs_connected)
            )
        ):
            raise RuntimeError(f"EV2Gym occupancy diverged at cabinet {cabinet}")
        return station

    def connect(self, vehicle_id: str, cabinet: str, port: int) -> None:
        station = self._checked_station(cabinet)
        if vehicle_id in self._connections:
            raise RuntimeError(f"Vehicle already connected: {vehicle_id}")
        if not 0 <= port < station.n_ports or station.evs_connected[port] is not None:
            raise RuntimeError("Queue and EV2Gym occupancy diverged before connect")
        ev = self.models[vehicle_id]
        zone = "DC" if isinstance(ev, DCEV) else "AC"
        if station.charger_type != zone:
            raise RuntimeError(f"Incompatible charger type for {vehicle_id} at {cabinet}")
        # Reuse can follow a shortened AC interval. AFAP still takes minute offsets.
        ev.timescale = 1
        ev.location = station.id
        first_free = station.evs_connected.index(None)
        if station.spawn_ev(ev) != first_free or station.evs_connected[first_free] is not ev:
            raise RuntimeError(f"EV2Gym returned an unexpected port at cabinet {cabinet}")
        if first_free != port:
            # Upstream always inserts into the first free slot. Move only the
            # newly spawned EV when the validated plan chose another free port.
            station.evs_connected[first_free] = None
            station.evs_connected[port] = ev
            ev.id = port
        self._connections[vehicle_id] = (cabinet, port)
        self._checked_station(cabinet)

    def disconnect(self, vehicle_id: str, cabinet: str, port: int) -> None:
        station = self._checked_station(cabinet)
        if self._connections.get(vehicle_id) != (cabinet, port):
            raise RuntimeError("Queue and EV2Gym occupancy diverged before disconnect")
        # The domain owns departure times and must release ports before the next action.
        station.evs_connected[port] = None
        station.n_evs_connected -= 1
        ev = self.models[vehicle_id]
        ev.id = ev.location = None
        del self._connections[vehicle_id]
        self._checked_station(cabinet)

    def soc(self, vehicle_id: str) -> float:
        return float(self.models[vehicle_id].get_soc())

    @staticmethod
    def _battery_state(vehicle_id: str, ev: DCEV) -> VehicleBatteryState:
        return VehicleBatteryState(
            vehicle_id, ev.max_dc_charge_power, ev.battery_capacity, ev.current_capacity, ev.desired_capacity
        )

    def acceptance_kw(self, v: Vehicle, minutes: int) -> float:
        ev = self.models[v.id]
        vehicle_kw = v.max_kw
        if isinstance(ev, DCEV):
            try:
                acceptance = self.dc_model.acceptance_kw(self._battery_state(v.id, ev))
            except ValueError as exc:
                raise ConstraintViolationError(f"DC acceptance evaluation failed for {v.id}: {exc}") from exc
            if (
                isinstance(acceptance, bool)
                or not isinstance(acceptance, Real)
                or not isfinite(acceptance)
                or acceptance < 0
            ):
                raise ConstraintViolationError(f"Invalid DC acceptance for {v.id}")
            vehicle_kw = min(vehicle_kw, acceptance)
        remaining = max(0, ev.desired_capacity - ev.current_capacity)
        return min(vehicle_kw, remaining * 60 / minutes / self.efficiency)

    def step(self, vehicle_id: str, cabinet: str, output_kw: float, minutes: int) -> Delivered:
        ev = self.models[vehicle_id]
        connection = self._connections.get(vehicle_id)
        if connection is None or connection[0] != cabinet:
            raise RuntimeError(f"Vehicle {vehicle_id} is not connected to cabinet {cabinet}")
        station = self._checked_station(cabinet)
        ev.timescale = minutes
        if isinstance(ev, DCEV):
            try:
                stored = self.dc_model.stored_kwh(
                    self._battery_state(vehicle_id, ev), output_kw, minutes, self.efficiency
                )
            except ValueError as exc:
                raise ConstraintViolationError(f"DC response evaluation failed for {vehicle_id}: {exc}") from exc
            if isinstance(stored, bool) or not isinstance(stored, Real) or not isfinite(stored) or stored < 0:
                raise ConstraintViolationError(f"Invalid DC energy response for {vehicle_id}")
            ev.record_charge(stored)
        else:
            volts = station.voltage * sqrt(station.phases)
            stored, _ = ev.step(output_kw * 1000 / volts, station.voltage, phases=station.phases, type="AC")
        # EV.step reports battery-side kWh. Its actual_current also reflects battery losses,
        # so derive output upstream of battery losses from the response, not the setpoint.
        return Delivered(float(stored * 60 / minutes / self.efficiency), float(stored))
