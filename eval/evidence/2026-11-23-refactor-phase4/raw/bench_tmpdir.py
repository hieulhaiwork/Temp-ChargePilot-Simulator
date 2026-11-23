"""Chạy eval/run_benchmark.py với RESULTS_DIR trỏ ra thư mục tạm (không ghi eval/results/)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import run_benchmark  # noqa: E402

run_benchmark.RESULTS_DIR = Path(sys.argv[1]).resolve()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
raise SystemExit(run_benchmark.main(sys.argv[2:]))
