"""Công cụ kiểm chứng refactor (ADR-019) phải FAIL khi có khác biệt — không chỉ in ra.

Mỗi công cụ có ca dương (khớp → exit 0) và ca âm (lệch → exit 1), để kết quả trích trong báo cáo là cổng kiểm thật.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "scripts" / "refactor"

ORIGINAL = '''"""doc"""
from math import isfinite

LIMIT = {"AC": 22, "DC": 78}


def valid(x):
    return isfinite(x) and x >= 0


class Plan:
    def total(self):
        return 1 + 2
'''


def _run(tool: str, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / tool), *map(str, args)], capture_output=True, text=True, check=False, cwd=ROOT
    )


def _manifest(tmp: Path, *roots) -> Path:
    out = tmp / "manifest.txt"
    out.write_text(_run("ast_manifest.py", *roots).stdout, encoding="utf-8")
    return out


def _module(tmp: Path, name: str, source: str) -> Path:
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


# ---- compare_ast_manifest.py ---------------------------------------------------------------


def test_manifest_identical_code_passes(tmp_path):
    mod = _module(tmp_path, "pkg/a.py", ORIGINAL)
    manifest = _manifest(tmp_path, mod)
    result = _run("compare_ast_manifest.py", manifest, "--", mod)
    assert result.returncode == 0, result.stdout
    assert "not identical: 0" in result.stdout


def test_manifest_ignores_imports_docstrings_and_format(tmp_path):
    mod = _module(tmp_path, "pkg/a.py", ORIGINAL)
    manifest = _manifest(tmp_path, mod)
    mod.write_text(
        ORIGINAL.replace("from math import isfinite", "from cmath import isfinite  # moved")
        .replace('"""doc"""', '"""other doc"""')
        .replace("1 + 2", "1+2"),
        encoding="utf-8",
    )
    assert _run("compare_ast_manifest.py", manifest, "--", mod).returncode == 0


def test_manifest_detects_changed_function_body(tmp_path):
    mod = _module(tmp_path, "pkg/a.py", ORIGINAL)
    manifest = _manifest(tmp_path, mod)
    mod.write_text(ORIGINAL.replace("x >= 0", "x > 0"), encoding="utf-8")
    result = _run("compare_ast_manifest.py", manifest, "--", mod)
    assert result.returncode == 1
    assert "CHANGED" in result.stdout and "::valid" in result.stdout


def test_manifest_detects_changed_module_constant(tmp_path):
    mod = _module(tmp_path, "pkg/a.py", ORIGINAL)
    manifest = _manifest(tmp_path, mod)
    mod.write_text(ORIGINAL.replace('"DC": 78', '"DC": 80'), encoding="utf-8")
    result = _run("compare_ast_manifest.py", manifest, "--", mod)
    assert result.returncode == 1 and "::LIMIT" in result.stdout


def test_manifest_detects_missing_definition(tmp_path):
    mod = _module(tmp_path, "pkg/a.py", ORIGINAL)
    manifest = _manifest(tmp_path, mod)
    mod.write_text(ORIGINAL.split("class Plan")[0], encoding="utf-8")
    result = _run("compare_ast_manifest.py", manifest, "--", mod)
    assert result.returncode == 1 and "MISSING" in result.stdout


def test_manifest_accepts_declared_move_and_moved_definition(tmp_path):
    old = _module(tmp_path, "old/a.py", ORIGINAL)
    manifest = _manifest(tmp_path, old)
    new = _module(tmp_path, "new/a.py", ORIGINAL.split("class Plan")[0])
    _module(tmp_path, "new/plan.py", "class Plan:\n    def total(self):\n        return 1 + 2\n")
    old.unlink()
    moves = _module(tmp_path, "moves.txt", f"{old.as_posix()} -> {new.as_posix()}\n")
    result = _run("compare_ast_manifest.py", manifest, "--moves", moves, "--", tmp_path / "new")
    assert result.returncode == 0, result.stdout
    assert "MOVED-SAME" in result.stdout


def test_manifest_rejects_empty_and_duplicate_names(tmp_path):
    empty = _module(tmp_path, "empty.txt", "# header only\n")
    mod = _module(tmp_path, "pkg/a.py", ORIGINAL)
    assert _run("compare_ast_manifest.py", empty, "--", mod).returncode == 1
    manifest = _manifest(tmp_path, mod)
    mod.write_text(ORIGINAL + "\n\ndef valid(x):\n    return False\n", encoding="utf-8")
    result = _run("compare_ast_manifest.py", manifest, "--", mod)
    assert result.returncode == 1 and "duplicate" in result.stdout


# ---- compare_sim_output.py -----------------------------------------------------------------

BASE = {
    "metadata": {
        "run_id": "r1",
        "command": ["a"],
        "algorithms": {"optimizers": {"DC": {"config_source": "/x/a.json", "implementation": "old.pkg.lp.LP"}}},
    },
    "cases": [{"policies": {"M3a": {"on_time": 9, "rejected_solver_plan_count": 0, "decision_latency_ms": 1.0}}}],
}


def _json(tmp: Path, name: str, data: dict) -> Path:
    path = tmp / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _variant(**changes) -> dict:
    data = json.loads(json.dumps(BASE))
    for dotted, value in changes.items():
        node = data
        *parents, leaf = dotted.split(".")
        for key in parents:
            node = node[int(key)] if key.isdigit() else node[key]
        node[leaf] = value
    return data


def test_sim_output_allows_timing_and_run_metadata_only(tmp_path):
    other = _variant(
        **{
            "metadata.run_id": "r2",
            "metadata.command": ["b", "c"],
            "metadata.algorithms.optimizers.DC.config_source": "/y/a.json",
            "cases.0.policies.M3a.decision_latency_ms": 9.9,
        }
    )
    result = _run("compare_sim_output.py", _json(tmp_path, "a.json", BASE), _json(tmp_path, "b.json", other), "t")
    assert result.returncode == 0, result.stdout


def test_sim_output_fails_on_kpi_change(tmp_path):
    for field, value in (("on_time", 8), ("rejected_solver_plan_count", 1)):
        other = _variant(**{f"cases.0.policies.M3a.{field}": value})
        result = _run("compare_sim_output.py", _json(tmp_path, "a.json", BASE), _json(tmp_path, "b.json", other), "t")
        assert result.returncode == 1, field
        assert field in result.stdout


def test_sim_output_implementation_path_needs_declared_module_map(tmp_path):
    moved = _variant(**{"metadata.algorithms.optimizers.DC.implementation": "new.zones.lp.LP"})
    a, b = _json(tmp_path, "a.json", BASE), _json(tmp_path, "b.json", moved)
    assert _run("compare_sim_output.py", a, b, "t").returncode == 1
    assert _run("compare_sim_output.py", a, b, "t", "--module-map", "old.pkg.lp=new.zones.lp").returncode == 0
    assert _run("compare_sim_output.py", a, b, "t", "--module-map", "old.pkg.lp=elsewhere.lp").returncode == 1
