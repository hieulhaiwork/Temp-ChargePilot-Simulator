"""Baseline benchmark có version (Phase 4 quyết định 8): chép đúng số Phase 3, manifest khớp dữ liệu."""

import json
from pathlib import Path

from src.services.simulation_service import BENCHMARK_BASELINE_DIR

ROOT = Path(__file__).resolve().parents[1]
PHASE3_RAW = ROOT / "eval" / "evidence" / "2026-11-23-refactor-phase3" / "raw" / "backend_benchmark_seeds1-5.json"


def test_baseline_is_a_byte_copy_of_phase3_evidence():
    """Không chạy lại khác điều kiện: số của baseline = số evidence Phase 3."""
    assert (BENCHMARK_BASELINE_DIR / "benchmark.json").read_bytes() == PHASE3_RAW.read_bytes()


def test_manifest_matches_the_runs_it_describes():
    manifest = json.loads((BENCHMARK_BASELINE_DIR / "manifest.json").read_text(encoding="utf-8"))
    data = json.loads((BENCHMARK_BASELINE_DIR / "benchmark.json").read_text(encoding="utf-8"))
    runs = data["runs"]
    assert manifest["copied_from"] == PHASE3_RAW.relative_to(ROOT).as_posix()
    assert manifest["generated_at"] == data["generated_at"]
    assert manifest["runs"] == len(runs)
    assert sorted({r["scenario_id"] for r in runs}) == manifest["scenarios"]
    assert sorted({r["strategy"] for r in runs}) == sorted(manifest["policies"])
    seeds = sorted({int(r["notes"].split("(seed ")[1].split(")")[0]) for r in runs})
    assert seeds == manifest["seeds"]
    assert len(runs) == len(manifest["scenarios"]) * len(manifest["policies"]) * len(manifest["seeds"])


def test_archived_ad_table_is_not_served():
    """Bảng A–D cũ đã chuyển sang archive (deprecated); API đọc baseline có version, không đọc archive."""
    archive = ROOT / "eval" / "results" / "archive" / "2026-11-22-pre-refactor"
    assert (archive / "benchmark.json").exists()
    assert "DEPRECATED" in (archive / "README.md").read_text(encoding="utf-8")
    assert "archive" not in BENCHMARK_BASELINE_DIR.parts
