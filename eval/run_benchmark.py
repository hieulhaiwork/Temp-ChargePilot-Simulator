"""Benchmark A–D (AC7) — mọi chiến lược chạy trên CÙNG kịch bản, cùng seed, cùng biểu giá.

Chiến lược (PRD §8): A_fcfs / A_edf (quy tắc), B (tối ưu không ML), C (tối ưu + dự báo
rút đầu nối), D (oracle — cận trên). Nguyên tắc: nếu C không tốt hơn B thì KHÔNG tuyên
bố AI cải thiện tối ưu — báo cáo trung thực.

Chạy từ repo root:
    python eval/run_benchmark.py
    python eval/run_benchmark.py --scenarios peak_evening,power_drop --strategies A_fcfs,B,C

Xuất: eval/results/benchmark.md (báo cáo) + eval/results/benchmark.json (API /simulation/benchmark).
Exit 2 khi pipeline chưa implement (in rõ task còn thiếu).
Owner: TV1. Task: T3.4 (bảng đầu tiên), T4.1 (tập chưa thấy).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Bootstrap import từ repo root khi chạy `python eval/run_benchmark.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.charging import StrategyName  # noqa: E402
from src.models.simulation import BenchmarkReport  # noqa: E402
from src.services import catalog, simulation_service  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
ALL_STRATEGIES = ",".join(s.value for s in StrategyName)


def render_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# Benchmark A–D — ChargePilot",
        "",
        f"> Sinh bởi `eval/run_benchmark.py` lúc {report.generated_at:%Y-%m-%d %H:%M %Z}. Chạy lại: `make benchmark`.",
        "",
        "| Kịch bản | Chiến lược | Đúng hạn | Chờ TB / p90 (phút) | Điện thiếu (kWh) | Phục vụ | Chi phí (VND)"
        " | Tải đỉnh (kW) | Vượt giới hạn | Tính lại p95 (s) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for run in report.runs:
        k = run.kpis
        p95 = "—" if k.replan_p95_seconds is None else f"{k.replan_p95_seconds:.2f}"
        lines.append(
            f"| {run.scenario_id} | {run.strategy.value} | {k.on_time_rate:.1%} | "
            f"{k.wait_mean_minutes:.1f} / {k.wait_p90_minutes:.1f} | {k.unmet_energy_kwh:.1f} | "
            f"{k.service_rate:.1%} | {k.energy_cost_vnd:,.0f} | {k.peak_load_kw:.1f} | "
            f"{k.power_limit_violations} | {p95} |"
        )
    lines += ["", *[f"- {note}" for note in report.notes]]
    return "\n".join(lines) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark các chiến lược A–D trên cùng kịch bản (AC7)")
    parser.add_argument("--scenarios", default="", help="scenario_id, phân cách bằng dấu phẩy (mặc định: tất cả)")
    parser.add_argument("--strategies", default=ALL_STRATEGIES, help=f"Mặc định: {ALL_STRATEGIES}")
    parser.add_argument("--seeds", default="", help="Danh sách seed, vd 1,2,3,4,5 (mặc định: seed của từng kịch bản)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    ids = [s for s in args.scenarios.split(",") if s]
    scenarios = [catalog.load_scenario(i) for i in ids] if ids else catalog.list_scenarios()
    strategies = [StrategyName(s) for s in args.strategies.split(",") if s]
    seeds = [int(s) for s in args.seeds.split(",") if s] or None
    try:
        report = simulation_service.run_benchmark(scenarios, strategies, seeds)
    except NotImplementedError as exc:
        print(f"Chưa chạy được benchmark — phần còn thiếu: {exc}", file=sys.stderr)
        return 2
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "benchmark.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (RESULTS_DIR / "benchmark.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"==> Đã ghi {RESULTS_DIR / 'benchmark.md'}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):  # console Windows (cp1258) không in được tiếng Việt có dấu
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
