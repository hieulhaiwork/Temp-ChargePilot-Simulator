"""Capability probe for the installed upstream objects (no ChargePilot dynamics)."""

import hashlib
from collections import deque
from importlib.metadata import distribution
from pathlib import Path

import pytest
from ev2gym.models.ev import EV
from ev2gym.models.ev_charger import EV_Charger


def vehicle(vehicle_id):
    return EV(vehicle_id, 0, 20, 0, 0, charge_efficiency=0.98, timescale=1)


def charger(zone):
    return EV_Charger(0, 0, 0, n_ports=1, charger_type=zone, timescale=1)


def test_native_ac_reports_energy_before_soc_rounding():
    ev = vehicle("AC-A")
    ev.time_of_departure = 10
    station = charger("AC")
    station.spawn_ev(ev)
    before = ev.current_capacity
    station.step([0.25], 0, 0)
    assert ev.current_energy > 0
    assert station.current_power_output == pytest.approx(ev.current_energy * 60)
    assert ev.current_capacity - before > ev.current_energy
    print(f"Native AC: returned {ev.current_energy:.9f} kWh, SOC capacity delta {ev.current_capacity - before:.9f} kWh")


def test_native_dc_raises():
    for operation in (
        lambda: vehicle("DC-A").step(16, 400, type="DC"),
        lambda: dc.step([0.25], 0, 0),
    ):
        dc = charger("DC")
        dc.spawn_ev(vehicle("DC-A"))
        with pytest.raises(NotImplementedError):
            operation()
    package = distribution("ev2gym")
    print(f"EV2Gym {package.version}; direct_url={package.read_text('direct_url.json')}")
    for name in ("ev", "ev_charger"):
        path = Path(package.locate_file(f"ev2gym/models/{name}.py"))
        print(f"{name}.py sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")


def test_full_port_rejects_spawn_then_can_admit_external_queue():
    ac = charger("AC")
    first, second = vehicle("AC-A"), vehicle("AC-B")
    ac.spawn_ev(first)
    with pytest.raises(AssertionError):
        ac.spawn_ev(second)
    waiting = deque([("AC-B", second)])
    assert ac.evs_connected == [first] and second.id == "AC-B"
    _, _, _, departed = ac.step([0], 0, 0)
    assert departed == [first] and ac.n_evs_connected == 0
    stable_id, next_ev = waiting.popleft()
    assert ac.spawn_ev(next_ev) == 0
    assert stable_id == "AC-B" and next_ev.id == 0
    assert ac.evs_connected == [second] and not waiting
