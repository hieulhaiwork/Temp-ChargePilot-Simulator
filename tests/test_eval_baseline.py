"""Baseline benchmark có version (Phase 4 quyết định 8).

- Baseline Phase 3 (tạm): bản chép đúng byte số evidence Phase 3, giữ làm lịch sử.
- Baseline chính thức cuối refactor: thứ `/simulation/benchmark` trả; manifest khớp dữ liệu (sha256, kịch bản, policy, seed).
"""

import hashlib
import json
from pathlib import Path

import pytest

from src.services.simulation_service import BENCHMARK_BASELINE_DIR

ROOT = Path(__file__).resolve().parents[1]
PHASE3_RAW = ROOT / "eval" / "evidence" / "2026-11-23-refactor-phase3" / "raw" / "backend_benchmark_seeds1-5.json"
PHASE3_BASELINE = ROOT / "eval" / "evidence" / "2026-11-23-refactor-phase3-baseline"
FINAL_BASELINE = ROOT / "eval" / "evidence" / "2026-11-24-unified-core-final-baseline"
FROZEN_BASELINE = ROOT / "eval" / "evidence" / "2026-11-24-unified-core-frozen-baseline"


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")  # checkout Windows có thể đổi xuống dòng; so nội dung


def test_phase3_baseline_is_a_byte_copy_of_phase3_evidence():
    """Không chạy lại khác điều kiện: số của baseline Phase 3 = số evidence Phase 3."""
    assert _lf((PHASE3_BASELINE / "benchmark.json").read_bytes()) == _lf(PHASE3_RAW.read_bytes())
    manifest = json.loads((PHASE3_BASELINE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["copied_from"] == PHASE3_RAW.relative_to(ROOT).as_posix()


def test_endpoint_serves_the_frozen_baseline():
    """Final Acceptance: API trả baseline đóng băng; baseline final trước vẫn nguyên (lịch sử), sha256 vẫn khớp."""
    assert BENCHMARK_BASELINE_DIR == FROZEN_BASELINE
    for baseline in (FINAL_BASELINE, FROZEN_BASELINE):
        manifest = json.loads((baseline / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "final"
        assert hashlib.sha256(_lf((baseline / "benchmark.json").read_bytes())).hexdigest() == manifest["copy_sha256"]


def test_frozen_baseline_has_same_kpis_as_final_and_records_provenance():
    final = json.loads((FINAL_BASELINE / "benchmark.json").read_text(encoding="utf-8"))["runs"]
    frozen = json.loads((FROZEN_BASELINE / "benchmark.json").read_text(encoding="utf-8"))["runs"]
    timing = {"replan_p95_seconds"}

    def strip(runs):
        return [
            (r["scenario_id"], r["strategy"], r["notes"], {k: v for k, v in r["kpis"].items() if k not in timing})
            for r in runs
        ]

    assert strip(final) == strip(frozen)
    manifest = json.loads((FROZEN_BASELINE / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["experiment_fingerprints"]) == {"B0", "M2b", "M3a", "M3b"}
    assert all(r["experiment"] and r["policy_version"] == "1" for r in frozen)


@pytest.mark.parametrize(
    "baseline", [PHASE3_BASELINE, FINAL_BASELINE, FROZEN_BASELINE], ids=["phase3", "final", "frozen"]
)
def test_manifest_matches_the_runs_it_describes(baseline):
    manifest = json.loads((baseline / "manifest.json").read_text(encoding="utf-8"))
    data = json.loads((baseline / "benchmark.json").read_text(encoding="utf-8"))
    runs = data["runs"]
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
