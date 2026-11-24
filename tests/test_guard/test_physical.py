"""Lớp vật lý của Guard backend phải ĐI QUA Guard của HybridSimulator (ADR-017), không phải bản viết lại."""

import subprocess
import sys

from src.guard.physical import adapter as physical
from src.models.control import CommandType, GuardRule
from tests.test_guard.test_rules import _cmd, _ctx, _rules_hit, _state


def test_power_and_dispatch_checks_call_the_simulator_guard(monkeypatch):
    calls = []
    real_guard, real_dispatch = physical.simulator_guard, physical.validate_dispatch
    monkeypatch.setattr(physical, "simulator_guard", lambda *a, **k: calls.append("guard") or real_guard(*a, **k))
    monkeypatch.setattr(
        physical, "validate_dispatch", lambda *a, **k: calls.append("dispatch") or real_dispatch(*a, **k)
    )
    _rules_hit(_cmd("AC-01-1", 7), _ctx())
    _rules_hit(_cmd("AC-01-1", None, ctype=CommandType.ASSIGN_CONNECTOR, booking_id="b-new"), _ctx())
    assert "guard" in calls and "dispatch" in calls


def test_violation_detail_carries_the_simulator_reason():
    ctx = _ctx(_state(available=200, DC_01_1=60, DC_01_2=60))
    cfg = ctx.config.model_copy(update={"physical_zone_cap_kw": {"AC": 22.0, "DC": 100.0}})
    from dataclasses import replace

    from src.guard.checker import check

    verdict = check(_cmd("AC-01-1", 7), replace(ctx, config=cfg, batch=(_cmd("AC-01-1", 7),)))
    total = [v for v in verdict.violations if v.rule == GuardRule.TOTAL_POWER]
    assert total and "Zone limit exceeded: DC" in total[0].detail


def test_physical_layer_does_not_import_ev2gym():
    """Image Render không cài ev2gym: lớp vật lý chỉ dùng phần thuần Python của simulator."""
    code = "import sys; import src.guard.physical.adapter; print('ev2gym' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
