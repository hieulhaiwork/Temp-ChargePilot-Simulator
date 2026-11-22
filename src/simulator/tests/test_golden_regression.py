"""Golden compatibility for MVP-1 and the locked DC optimizer from MVP-2."""

import json
from pathlib import Path

import pytest

from src.simulator.src.algorithms import resolve_algorithms
from src.simulator.src.engine.hybrid import HybridSimulator
from src.simulator.src.scenario import Scenario
from src.simulator.tests.golden_util import canonical_parts

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / "tests/golden/v1_2_outputs.json").read_bytes())
MVP2_GOLDEN = json.loads((ROOT / "tests/golden/mvp2_outputs.json").read_bytes())
CASES = {
    "mvp1": ("mvp1", None),
    "mvp1_edf_demo": ("mvp1", "config/algorithms_edf_demo.json"),
    "vinfast_dc_2port_120kw": ("vinfast_dc_2port_120kw", None),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_outputs_match_v1_2_golden(name):
    scenario_name, selection_path = CASES[name]
    config = json.loads((ROOT / f"scenario/{scenario_name}.json").read_bytes())
    scenario = Scenario.parse(config)
    selection = json.loads((ROOT / selection_path).read_bytes()) if selection_path else config.get("algorithms", {})
    algorithms, _ = resolve_algorithms(selection, scenario, "golden")
    result = HybridSimulator(scenario, algorithms=algorithms).run()
    assert canonical_parts(result) == GOLDEN[name]["hashes"]


@pytest.mark.parametrize("name", sorted(MVP2_GOLDEN))
def test_mvp2_control_matches_pre_mvp3_golden(name):
    config = json.loads((ROOT / f"scenario/{name}.json").read_bytes())
    scenario = Scenario.parse(config)
    selection = config.get("algorithms", {}) | json.loads((ROOT / "config/algorithms_mvp2.json").read_bytes())
    algorithms, _ = resolve_algorithms(selection, scenario, "golden_mvp2")
    result = HybridSimulator(scenario, algorithms=algorithms, record_decisions=True).run()
    assert canonical_parts(result) == MVP2_GOLDEN[name]
