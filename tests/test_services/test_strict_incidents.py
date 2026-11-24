"""Final Review 4.7 — benchmark nghiên cứu fail-fast khi sự cố không hợp lệ; mọi chế độ đếm sự cố.

`connector_failure` (legacy_ac_only) có sự cố trỏ A05 — không có trong topology `mvp1` hiện hành. Mặc định (baseline):
bỏ qua + note y như cũ. `strict_incidents=True`: lỗi ngay, trước khi chạy. `hybrid_power_drop`: mọi sự cố hợp lệ ⇒ strict
chạy được và số thực thi = số dự kiến.
"""

import pytest

from src.models.charging import StrategyName
from src.models.control import Role
from src.services import catalog, simulation_service

LEGACY_NOTE = " Bỏ qua sự cố không khớp topology: connector_fault@420' (A05), connector_restored@660' (A05)."


def _short(scenario_id: str, hours: int, vehicles: int = 4):
    return catalog.load_scenario(scenario_id).model_copy(update={"duration_hours": hours, "n_vehicles": vehicles})


def test_strict_mode_fails_fast_on_a_missing_connector(monkeypatch):
    scenario = _short("connector_failure", 12)
    started = []
    monkeypatch.setattr(
        simulation_service, "build_sim_runtime", lambda *a, **k: started.append(1) or pytest.fail("không được chạy")
    )
    with pytest.raises(simulation_service.InvalidIncidentError, match="A05") as caught:
        simulation_service.run_scenario(scenario, StrategyName.SIM_B0, strict_incidents=True)
    assert caught.value.code == "not_found"
    assert "connector_fault@420' (A05)" in caught.value.detail
    assert not started  # fail-fast: không mô phỏng phút nào


def test_default_mode_keeps_skip_and_note_and_counts_incidents():
    result = simulation_service.run_scenario(_short("connector_failure", 12), StrategyName.SIM_B0)
    assert result.notes.endswith(LEGACY_NOTE)  # đúng định dạng note cũ (baseline so notes từng ký tự)
    counts = result.incidents
    assert (counts.planned, counts.applied, counts.skipped, counts.strict) == (2, 0, 2, False)
    assert counts.skipped_details == ["connector_fault@420' (A05)", "connector_restored@660' (A05)"]


@pytest.mark.parametrize("strict", [False, True])
def test_valid_incidents_are_all_applied_in_both_modes(strict):
    result = simulation_service.run_scenario(
        _short("hybrid_power_drop", 11), StrategyName.SIM_B0, strict_incidents=strict
    )
    counts = result.incidents
    assert (counts.planned, counts.applied, counts.skipped, counts.strict) == (4, 4, 0, strict)
    assert "Bỏ qua sự cố" not in result.notes


def test_incident_that_fails_while_injecting_is_an_error_in_strict_mode(monkeypatch):
    """Lưới an toàn thứ hai: trạm từ chối sự cố lúc bơm (dù qua kiểm tra trước) ⇒ strict lỗi, mặc định bỏ qua."""
    from src.simulator.hybrid_station import HybridStation

    def refuse(self, incident):
        raise ValueError("trạm từ chối")

    monkeypatch.setattr(HybridStation, "inject_incident", refuse)
    scenario = _short("hybrid_power_drop", 11)
    with pytest.raises(simulation_service.InvalidIncidentError, match="trạm từ chối"):
        simulation_service.run_scenario(scenario, StrategyName.SIM_B0, strict_incidents=True)
    lenient = simulation_service.run_scenario(scenario, StrategyName.SIM_B0)
    assert (lenient.incidents.applied, lenient.incidents.skipped) == (0, 4)


def test_benchmark_cli_exits_3_in_strict_mode(capsys):
    from eval import run_benchmark

    code = run_benchmark.main(["--scenarios", "connector_failure", "--strategies", "B0", "--strict-incidents"])
    assert code == 3
    assert "A05" in capsys.readouterr().err


def test_benchmark_cli_rejects_unknown_policy(capsys):
    from eval import run_benchmark

    assert run_benchmark.main(["--scenarios", "hybrid_evening", "--strategies", "khong-co"]) == 2
    assert "khong-co" in capsys.readouterr().err


async def test_run_endpoint_strict_incidents(client, as_role):
    as_role(Role.OPERATOR)
    body = {"scenario_id": "connector_failure", "strategy": "B0", "n_vehicles": 2, "strict_incidents": True}
    response = await client.post("/api/v1/simulation/runs", json=body)
    assert response.status_code == 404
    assert response.json()["code"] == "not_found" and "A05" in response.json()["detail"]
