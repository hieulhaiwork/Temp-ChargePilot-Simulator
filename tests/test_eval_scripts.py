import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_judge_script_imports_from_repo_root():
    # Chạy đúng như docstring hướng dẫn: `python eval/judge.py` từ repo root.
    proc = subprocess.run([sys.executable, "eval/judge.py"], cwd=ROOT, capture_output=True, text=True)
    assert "ModuleNotFoundError" not in proc.stderr
    assert proc.returncode == 2  # thiếu argument -> in Usage


def test_benchmark_script_runs_from_repo_root():
    # `python eval/run_benchmark.py --help` phải import được src/ khi chạy từ repo root.
    proc = subprocess.run(
        [sys.executable, "eval/run_benchmark.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert "ModuleNotFoundError" not in proc.stderr
    assert proc.returncode == 0
    assert "--strategies" in proc.stdout


def test_agent_eval_offline_validates_dataset_without_llm(tmp_path):
    """PRD §8: bộ câu có nhãn phải hợp lệ; chế độ offline không gọi LLM và không ghi file được track."""
    proc = subprocess.run(
        [sys.executable, "eval/run_agent_eval.py", "--offline", "--out", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "OPENAI_API_KEY": ""},
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "summary.json").is_file()
    assert "extract" in proc.stdout


def test_agent_eval_offline_rejects_bad_labels(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"id": "x", "category": "extract", "now": "2026-11-16T19:00:00+07:00", "utterance": "u", '
        '"expected_action": "propose_plan", "expected": null}',
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "eval/run_agent_eval.py", "--offline", "--dataset", str(bad)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 1
    assert "expected" in proc.stderr


def test_agent_eval_online_reports_missing_task():
    proc = subprocess.run(
        [sys.executable, "eval/run_agent_eval.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "LLM_PROVIDER": "openai", "OPENAI_API_KEY": ""},
    )
    assert proc.returncode == 2
    assert "T4.2" in proc.stderr


def test_agent_eval_online_passes_thresholds_with_mock_llm(tmp_path):
    proc = subprocess.run(
        [sys.executable, "eval/run_agent_eval.py", "--out", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "LLM_PROVIDER": "mock", "AGENT_DEMO_SERVICES": "true"},
    )
    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    assert (tmp_path / "summary.json").is_file()
    assert (tmp_path / "report.md").is_file()


def test_run_eval_accepts_out_argument():
    """I10: `--out` cho phép chạy eval mà không ghi đè eval/results/report.md (file được track)."""
    proc = subprocess.run(
        [sys.executable, "eval/run_eval.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 0
    assert "--out" in proc.stdout
