"""Cổng kiểm benchmark backend (eval/run_benchmark.py JSON): mọi run phải có KPI + notes giống baseline (ADR-019).

Dùng: python scripts/refactor/compare_backend_benchmark.py <baseline.json> <candidate.json>
Khoá run = (scenario_id, strategy, seed trong notes). Bỏ qua đúng `replan_p95_seconds` (thời gian tường).
Exit 1 nếu tập run khác nhau, hoặc bất kỳ KPI / notes nào lệch.
"""

import json
import re
import sys

TIMING_KPIS = {"replan_p95_seconds"}


def _key(run: dict) -> tuple[str, str, str]:
    match = re.search(r"seed (\d+)", run["notes"])
    return run["scenario_id"], run["strategy"], match.group(1) if match else "?"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    baseline_path, candidate_path = (sys.argv[1:] if argv is None else argv)[:2]
    with open(baseline_path, encoding="utf-8") as fa, open(candidate_path, encoding="utf-8") as fb:
        a = {_key(r): r for r in json.load(fa)["runs"]}
        b = {_key(r): r for r in json.load(fb)["runs"]}
    problems = [f"missing run {k}" for k in sorted(a.keys() - b.keys())]
    problems += [f"extra run {k}" for k in sorted(b.keys() - a.keys())]
    for key in sorted(a.keys() & b.keys()):
        ka, kb = a[key]["kpis"], b[key]["kpis"]
        for name in sorted((ka.keys() | kb.keys()) - TIMING_KPIS):
            if ka.get(name) != kb.get(name):
                problems.append(f"{key} {name}: {ka.get(name)!r} != {kb.get(name)!r}")
        if a[key]["notes"] != b[key]["notes"]:
            problems.append(f"{key} notes differ")
    status = "OK" if not problems else "FAIL"
    print(f"backend benchmark: {status} - {len(a)} baseline runs, {len(b)} candidate runs, {len(problems)} problems")
    for line in problems[:30]:
        print("   ", line)
    return 1 if problems or not a else 0


if __name__ == "__main__":
    raise SystemExit(main())
