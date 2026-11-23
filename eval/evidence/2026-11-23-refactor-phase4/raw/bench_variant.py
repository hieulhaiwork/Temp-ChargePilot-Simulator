"""Benchmark với MỘT trong hai sửa đổi của quyết định 3 bị tắt — để quy khác biệt KPI cho từng sửa đổi.

variant=round_nearest : lệnh lại làm tròn gần nhất 3 chữ số (như Phase 3), giữ ưu tiên giảm tải
variant=no_reduction  : giữ lượng tử hoá xuống, tắt ưu tiên giảm tải (luật tổng công suất xét cả lệnh giảm như Phase 3)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import run_benchmark  # noqa: E402

from src.guard import dispatcher, rules  # noqa: E402
from src.services import control_loop, hybrid_planner  # noqa: E402

variant = sys.argv[2]
if variant == "round_nearest":
    control_loop.quantize_kw = hybrid_planner.quantize_kw = lambda kw: round(max(kw, 0.0), 3)
elif variant == "no_reduction":
    rules.is_load_reduction = dispatcher.is_load_reduction = lambda cmd, ctx: False
    dispatcher.is_safety_reduction = lambda cmd, ctx: False
else:
    raise SystemExit(f"unknown variant {variant}")
run_benchmark.RESULTS_DIR = Path(sys.argv[1]).resolve()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
raise SystemExit(run_benchmark.main(sys.argv[3:]))
