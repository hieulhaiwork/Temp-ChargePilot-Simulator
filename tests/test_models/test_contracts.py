"""Hợp đồng dữ liệu — validator ở src/models/ chặn dữ liệu sai NGAY tại ranh giới."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.models.charging import (
    Alternative,
    AlternativeKind,
    ChargeMode,
    ChargeRequest,
    EnergyEstimate,
    ScheduleProposal,
)
from src.models.control import (
    Approval,
    ApprovalKind,
    Command,
    CommandSource,
    CommandType,
    GuardRule,
    GuardVerdict,
    Violation,
)
from src.models.simulation import Incident, IncidentType

VN = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 16, 19, 30, tzinfo=VN)


def _request(**overrides) -> ChargeRequest:
    data = {
        "vehicle_model": "DEMO-60",
        "soc_now": 32,
        "soc_target": 80,
        "arrival_time": NOW,
        "deadline": NOW + timedelta(hours=11),
        "mode": ChargeMode.RESERVATION,
    }
    return ChargeRequest(**(data | overrides))


def _command(**overrides) -> Command:
    data = {
        "type": CommandType.SET_POWER,
        "connector_id": "A07",
        "power_kw": 3.5,
        "source": CommandSource.OPTIMIZER,
        "issued_by": "optimizer",
        "based_on_schedule_version": 1,
        "based_on_state_at": NOW,
        "created_at": NOW,
    }
    return Command(**(data | overrides))


def _energy() -> EnergyEstimate:
    return EnergyEstimate(
        vehicle_model="DEMO-60",
        soc_now=32,
        soc_target=80,
        battery_energy_kwh=28.8,
        grid_energy_kwh=32.0,
        efficiency=0.9,
    )


# ---- ChargeRequest (FR2) -------------------------------------------------


def test_valid_charge_request_passes():
    assert _request().soc_target == 80


def test_target_not_above_current_soc_is_rejected():
    with pytest.raises(ValidationError, match="soc_target"):
        _request(soc_now=80, soc_target=80)


def test_reservation_requires_arrival_time():
    with pytest.raises(ValidationError, match="arrival_time"):
        _request(arrival_time=None)


def test_walk_in_may_omit_arrival_time():
    assert _request(mode=ChargeMode.WALK_IN, arrival_time=None).arrival_time is None


def test_deadline_before_arrival_is_rejected():
    with pytest.raises(ValidationError, match="deadline"):
        _request(deadline=NOW - timedelta(minutes=1))


def test_naive_datetime_is_rejected():
    """Dữ liệu Na Uy / ACN khác múi giờ — bắt buộc có tzinfo để không lệch giờ âm thầm."""
    with pytest.raises(ValidationError):
        _request(deadline=datetime(2026, 11, 17, 7, 0))


# ---- ScheduleProposal (FR4) ---------------------------------------------


def test_infeasible_proposal_must_offer_alternative():
    with pytest.raises(ValidationError, match="FR4"):
        ScheduleProposal(feasible=False, energy=_energy())


def test_infeasible_proposal_with_alternative_passes():
    alt = Alternative(kind=AlternativeKind.LOWER_TARGET, description="Sạc tới 70%", soc_target=70)
    assert ScheduleProposal(feasible=False, energy=_energy(), alternatives=[alt]).alternatives


# ---- Command / GuardVerdict / Approval (F4) -------------------------------


def test_set_power_command_requires_power():
    with pytest.raises(ValidationError, match="power_kw"):
        _command(power_kw=None)


def test_assign_command_requires_booking():
    with pytest.raises(ValidationError, match="booking_id"):
        _command(type=CommandType.ASSIGN_CONNECTOR, power_kw=None)


def test_verdict_passed_must_match_violations():
    with pytest.raises(ValidationError):
        GuardVerdict(
            command_id="c1",
            passed=True,
            checked_at=NOW,
            violations=[Violation(rule=GuardRule.TOTAL_POWER, detail="36 kW > 35 kW")],
        )
    with pytest.raises(ValidationError):
        GuardVerdict(command_id="c1", passed=False, checked_at=NOW)


def test_blocked_command_can_never_go_to_approval():
    cmd = _command()
    blocked = GuardVerdict(
        command_id=cmd.command_id,
        passed=False,
        checked_at=NOW,
        violations=[Violation(rule=GuardRule.STALE_STATE, detail="state cũ 5 phút")],
    )
    with pytest.raises(ValidationError, match="Guard chặn"):
        Approval(
            kind=ApprovalKind.RESIDENT_CONSENT,
            command=cmd,
            verdict=blocked,
            requested_from="resident-1",
            impact_summary="-",
            created_at=NOW,
        )


# ---- Incident (FR18, AC5) --------------------------------------------------


def test_incident_payload_matches_type():
    with pytest.raises(ValidationError, match="connector_id"):
        Incident(type=IncidentType.CONNECTOR_FAULT)
    with pytest.raises(ValidationError, match="new_power_limit_kw"):
        Incident(type=IncidentType.POWER_LIMIT_CHANGE)
    assert Incident(type=IncidentType.POWER_LIMIT_CHANGE, new_power_limit_kw=20).new_power_limit_kw == 20
