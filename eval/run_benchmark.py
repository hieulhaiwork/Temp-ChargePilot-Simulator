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
Kèm `RESULTS_DIR/manifest.json` (Final Acceptance §3.3): manifest nháp cùng khoá với baseline + `experiments`
(cấu hình đã resolve + fingerprint của từng policy); mỗi run trong JSON có `experiment`.
Exit 2 khi pipeline chưa implement (in rõ task còn thiếu) hoặc policy không có trong registry.
`--strict-incidents` (benchmark nghiên cứu, Final Review 4.7): sự cố không áp được vào topology ⇒ exit 3 ngay. Mặc
định giữ hành vi cũ (bỏ qua + note). Mọi chế độ ghi `incidents` (dự kiến / thực thi / bỏ qua) vào từng run của JSON.
Owner: TV1. Task: T3.4 (bảng đầu tiên), T4.1 (tập chưa thấy).
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
        " | Tải đỉnh (kW) | Phút vượt giới hạn (lấy mẫu) | Vi phạm cứng (kernel) | Tính lại p95 (s) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for run in report.runs:
        k = run.kpis
        p95 = "—" if k.replan_p95_seconds is None else f"{k.replan_p95_seconds:.2f}"
        hard = "—" if run.violations is None else str(run.violations.applied_constraint_violation_count)
        lines.append(
            f"| {run.scenario_id} | {run.policy_id} | {k.on_time_rate:.1%} | "
            f"{k.wait_mean_minutes:.1f} / {k.wait_p90_minutes:.1f} | {k.unmet_energy_kwh:.1f} | "
            f"{k.service_rate:.1%} | {k.energy_cost_vnd:,.0f} | {k.peak_load_kw:.1f} | "
            f"{k.power_limit_violations} | {hard} | {p95} |"
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
    parser.add_argument(
        "--strict-incidents",
        action="store_true",
        help="Benchmark nghiên cứu: sự cố trỏ đầu nối không tồn tại ⇒ dừng ngay (exit 3) thay vì bỏ qua + ghi note",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from src.optimizer import registry
    from src.services.hybrid_planner import as_policy_ref

    args = _parse_args(argv)
    ids = [s for s in args.scenarios.split(",") if s]
    scenarios = [catalog.load_scenario(i) for i in ids] if ids else catalog.list_scenarios()
    # Id policy tra thẳng registry: B0 / M2b / M3a / M3b (StrategyName) hoặc policy đăng ký mới.
    unknown = [s for s in args.strategies.split(",") if s and s not in registry.POLICIES]
    if unknown:
        print(
            f"Policy không có trong registry: {', '.join(unknown)} (có: {', '.join(registry.POLICIES)})",
            file=sys.stderr,
        )
        return 2
    strategies = [as_policy_ref(s) for s in args.strategies.split(",") if s]
    seeds = [int(s) for s in args.seeds.split(",") if s] or None
    try:
        report = simulation_service.run_benchmark(scenarios, strategies, seeds, strict_incidents=args.strict_incidents)
    except NotImplementedError as exc:
        print(f"Chưa chạy được benchmark — phần còn thiếu: {exc}", file=sys.stderr)
        return 2
    except simulation_service.InvalidIncidentError as exc:
        print(f"Benchmark nghiên cứu dừng (--strict-incidents): {exc.detail}", file=sys.stderr)
        return 3
    if report.source is not None:
        report.source.code_commit = _git_commit()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    data = report.model_dump_json(indent=2)
    (RESULTS_DIR / "benchmark.json").write_text(data, encoding="utf-8")
    (RESULTS_DIR / "benchmark.md").write_text(render_markdown(report), encoding="utf-8")
    manifest = build_manifest(report, data, argv if argv is not None else sys.argv[1:])
    (RESULTS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"==> Đã ghi {RESULTS_DIR / 'benchmark.md'} (+ benchmark.json, manifest.json)")
    return 0


def build_manifest(report: BenchmarkReport, benchmark_json: str, argv: list[str]) -> dict:
    """Manifest NHÁP của bảng vừa sinh (Final Acceptance §3.3) — cùng khoá với manifest baseline có version, thêm
    `experiments` (policy → cấu hình đã resolve + fingerprint). Thành baseline thì điều phối điền `baseline_id` /
    `version` / `status` và chép cả thư mục vào `eval/evidence/<ngày>-...-baseline/`."""
    src = report.source
    experiments = {pid: exp.model_dump(mode="json") for pid, exp in (src.experiments if src else {}).items()}
    return {
        "kind": "generated",
        "baseline_id": None,
        "version": None,
        "status": "generated",
        "code_commit": src.code_commit if src else None,
        "generated_at": report.generated_at.isoformat(),
        "command": " ".join(["eval/run_benchmark.py", *argv]),
        "benchmark_sha256": hashlib.sha256(benchmark_json.encode("utf-8")).hexdigest(),
        "scenarios": src.scenarios if src else [],
        "policies": src.policies if src else [],
        "seeds": src.seeds if src else [],
        "runs": len(report.runs),
        "time_config": src.time_config if src else {},
        "libraries": src.libraries if src else {},
        "experiments": experiments,
        "experiment_fingerprints": {pid: exp["fingerprint"] for pid, exp in experiments.items()},
    }


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
