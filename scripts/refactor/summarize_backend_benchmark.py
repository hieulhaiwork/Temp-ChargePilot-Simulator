"""Bảng trung bình 5 seed (kịch bản × policy) của hai file benchmark backend, trước → sau (ADR-019 báo cáo khác biệt).

Dùng: python scripts/refactor/summarize_backend_benchmark.py <trước.json> <sau.json> [nhãn_trước] [nhãn_sau]
In Markdown. Không phải cổng kiểm (không exit 1): dùng để báo cáo khác biệt có chủ ý cùng lý do.
"""

import json
import statistics
import sys

KPIS = (
    ("on_time_rate", "{:.3f}"),
    ("unmet_energy_kwh", "{:.2f}"),
    ("delivered_energy_kwh", "{:.2f}"),
    ("energy_cost_vnd", "{:,.0f}"),
    ("peak_load_kw", "{:.2f}"),
    ("wait_mean_minutes", "{:.1f}"),
    ("power_limit_violations", "{:.0f}"),
    ("blocked_commands", "{:.1f}"),
)


def _means(path: str) -> dict:
    with open(path, encoding="utf-8") as stream:
        runs = json.load(stream)["runs"]
    groups: dict = {}
    for run in runs:
        groups.setdefault((run["scenario_id"], run["strategy"]), []).append(run["kpis"])
    return {key: {k: statistics.fmean(r[k] for r in rows) for k, _ in KPIS} for key, rows in groups.items()}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:] if argv is None else argv
    before, after = _means(argv[0]), _means(argv[1])
    label_a = argv[2] if len(argv) > 2 else "trước"
    label_b = argv[3] if len(argv) > 3 else "sau"
    print(f"| kịch bản | policy | {' | '.join(f'{k} {label_a} → {label_b}' for k, _ in KPIS)} |")
    print("|---|---|" + "---|" * len(KPIS))
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        cells = []
        for name, fmt in KPIS:
            left = fmt.format(a[name]) if a else "—"
            right = fmt.format(b[name]) if b else "—"
            cells.append(left if left == right else f"{left} → **{right}**")
        print(f"| {key[0]} | {key[1]} | {' | '.join(cells)} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
