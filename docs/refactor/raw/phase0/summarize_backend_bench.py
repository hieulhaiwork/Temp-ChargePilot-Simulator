"""Tóm tắt eval/run_benchmark JSON: trung bình 5 seed theo (scenario, strategy)."""

import collections
import json
import statistics
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
groups = collections.defaultdict(list)
for r in d["runs"]:
    groups[(r["scenario_id"], r["strategy"])].append(r["kpis"])
keys = list(next(iter(groups.values()))[0])
print("| scenario | strategy | n | " + " | ".join(keys) + " |")
print("|---" * (3 + len(keys)) + "|")
for (sc, st), rows in groups.items():
    vals = []
    for k in keys:
        xs = [x[k] for x in rows if isinstance(x.get(k), (int, float))]
        vals.append(f"{statistics.mean(xs):.3f}" if xs else "-")
    print(f"| {sc} | {st} | {len(rows)} | " + " | ".join(vals) + " |")
