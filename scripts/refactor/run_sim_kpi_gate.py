"""Chạy lại output simulator standalone và so với một bộ output gốc bằng `compare_sim_output.py` (ADR-019).

Dùng:
    python scripts/refactor/run_sim_kpi_gate.py run <thư_mục_out>
    python scripts/refactor/run_sim_kpi_gate.py compare <thư_mục_gốc> <thư_mục_mới> [--evidence DIR] [--module-map FILE]

`run` sinh: MVP-1 (+ DecisionTrace), MVP-1 với `algorithms_mvp3.json`, VinFast, MVP-1 chế độ script, MVP-2, MVP-3.
`compare` so từng file JSON (report, replay, events, DecisionTrace, benchmark) và so byte các file CSV; với
`--evidence` so thêm các file của `eval/evidence/2026-11-22/raw/sim-hardware/`. Exit 1 khi có bất kỳ cặp nào lệch.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPARE = ROOT / "scripts" / "refactor" / "compare_sim_output.py"
RUNS = {
    "mvp1": ["-m", "src.simulator.run", "--scenario", "mvp1", "--decision-trace"],
    "mvp1_m3": [
        "-m",
        "src.simulator.run",
        "--scenario",
        "mvp1",
        "--algorithms",
        "src/simulator/config/algorithms_mvp3.json",
        "--decision-trace",
    ],
    "vf": ["-m", "src.simulator.run", "--scenario", "vinfast_dc_2port_120kw"],
    "script": ["src/simulator/run.py", "--scenario", "mvp1"],
    "mvp2": ["-m", "src.simulator.benchmark", "--vinfast-sensitivity"],
    "mvp3": ["-m", "src.simulator.benchmark_mvp3"],
}
EVIDENCE = {
    ("mvp1", "report.json"): "mvp1_default_report.json",
    ("mvp1_m3", "report.json"): "mvp1_mvp3_report.json",
    ("mvp1_m3", "decision_trace.json"): "mvp1_mvp3_decision_trace.json",
    ("vf", "report.json"): "vinfast_dc_120kw_report.json",
    ("mvp2", "benchmark.json"): "mvp2_benchmark.json",
    ("mvp3", "benchmark.json"): "mvp3_benchmark.json",
}
SKIP = {"latency_records.json", "decision_latency_ms.json", "viewer.html"}


def run(out: Path) -> int:
    for name, args in RUNS.items():
        result = subprocess.run(
            [sys.executable, "-X", "utf8", *args, "--output-dir", str(out / name)], cwd=ROOT, check=False
        )
        if result.returncode:
            print(f"{name}: exit {result.returncode}")
            return 1
    return 0


def _run_dir(base: Path, name: str) -> Path:
    dirs = sorted(path for path in (base / name).iterdir() if path.is_dir())
    if len(dirs) != 1:
        raise SystemExit(f"{base / name}: expected exactly one run directory, found {len(dirs)}")
    return dirs[0]


def compare(base: Path, new: Path, evidence: Path | None, module_map: list[str]) -> int:
    flags = [arg for item in module_map for arg in ("--module-map", item)]
    failures = total = 0
    for name in RUNS:
        old_dir, new_dir = _run_dir(base, name), _run_dir(new, name)
        for old_file in sorted(old_dir.iterdir()):
            if old_file.name in SKIP:
                continue
            new_file = new_dir / old_file.name
            label = f"{name}/{old_file.name}"
            total += 1
            if not new_file.exists():
                print(f"{label}: FAIL - missing")
                failures += 1
            elif old_file.suffix == ".csv":
                same = old_file.read_bytes() == new_file.read_bytes()
                print(f"{label}: {'OK - byte-identical' if same else 'FAIL - bytes differ'}")
                failures += not same
            else:
                rc = subprocess.run(
                    [sys.executable, str(COMPARE), str(old_file), str(new_file), label, *flags], check=False
                ).returncode
                failures += rc != 0
        if evidence is not None:
            for (run_name, file_name), golden in EVIDENCE.items():
                if run_name != name:
                    continue
                total += 1
                label = f"{name}/{file_name} vs evidence {golden}"
                rc = subprocess.run(
                    [sys.executable, str(COMPARE), str(evidence / golden), str(new_dir / file_name), label, *flags],
                    check=False,
                ).returncode
                failures += rc != 0
    print(f"\nOVERALL: {total - failures}/{total} OK, rc={1 if failures else 0}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run").add_argument("out", type=Path)
    cmp = sub.add_parser("compare")
    cmp.add_argument("base", type=Path)
    cmp.add_argument("new", type=Path)
    cmp.add_argument("--evidence", type=Path)
    cmp.add_argument("--module-map", type=Path, help="file: one OLD.module=NEW.module per line")
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return run(args.out)
    module_map = []
    if args.module_map:
        module_map = [line.strip() for line in args.module_map.read_text(encoding="utf-8").splitlines() if "=" in line]
    return compare(args.base, args.new, args.evidence, module_map)


if __name__ == "__main__":
    raise SystemExit(main())
