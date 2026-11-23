"""Benchmark B0 / M2b / M3a / M3b (AC7) — mọi policy chạy trên CÙNG kịch bản, cùng seed, cùng biểu giá.

Policy = registry của Planning Core (`src/optimizer/registry.py`, version 1), chạy trên `HybridStation` qua đúng đường
production (control_loop → Guard → kernel). A–D (LP backend) đã bỏ: ADR-019 Phase 3 xoá code, Phase 4 xoá khỏi
`StrategyName`. Bảng A–D cũ là archive deprecated ở `eval/results/archive/2026-11-22-pre-refactor/`.

Chạy từ repo root:
    python eval/run_benchmark.py
    python eval/run_benchmark.py --scenarios peak_evening,power_drop --strategies B0,M3a --seeds 1,2,3,4,5

Xuất: `RESULTS_DIR/benchmark.md` + `RESULTS_DIR/benchmark.json` (mặc định `eval/results/`), kèm `source` (kind
`generated`: kịch bản, policy, seed, TimeConfig, thư viện, commit). `GET /simulation/benchmark` KHÔNG đọc file này mà
đọc baseline có version (`simulation_service.BENCHMARK_BASELINE_DIR`); muốn dùng số mới làm baseline thì chép thành thư
mục `eval/evidence/<ngày>-...-baseline/` có `manifest.json` (xem `2026-11-23-refactor-phase3-baseline/`).
Exit 2 khi pipeline chưa implement (in rõ task còn thiếu).
Owner: TV1. Task: T3.4 (bảng đầu tiên), T4.1 (tập chưa thấy).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Bootstrap import từ repo root khi chạy `python eval/run_benchmark.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.charging import StrategyName  # noqa: E402
from src.models.simulation import BenchmarkReport  # noqa: E402
from src.services import catalog, simulation_service  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
ALL_STRATEGIES = ",".join(s.value for s in StrategyName)  # B0, M2b, M3a, M3b


def render_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# Benchmark B0 / M2b / M3a / M3b — ChargePilot",
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
    if report.source is not None:
        src = report.source
        lines += [
            "",
            f"Nguồn: `{src.kind.value}` · commit `{src.code_commit or '?'}` · seed {src.seeds} · "
            f"TimeConfig {src.time_config} · thư viện {src.libraries}. {src.note}",
        ]
    return "\n".join(lines) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark B0 / M2b / M3a / M3b trên cùng kịch bản (AC7)")
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
    if report.source is not None:
        report.source.code_commit = _git_commit()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "benchmark.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (RESULTS_DIR / "benchmark.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"==> Đã ghi {RESULTS_DIR / 'benchmark.md'}")
    return 0


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):  # console Windows (cp1258) không in được tiếng Việt có dấu
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
