"""Verify experiment comparability before interpreting the repository's KPI comparator."""

import hashlib
import itertools
import json
import re
import statistics
import sys
from pathlib import Path


def load(folder, baseline):
    path = folder / "benchmark.json"
    report = json.loads(path.read_bytes())
    manifest = json.loads((folder / "manifest.json").read_bytes())
    digest_key = "copy_sha256" if baseline else "benchmark_sha256"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest[digest_key]
    assert report["source"]["code_commit"] == manifest["code_commit"]
    assert len(report["runs"]) == manifest["runs"] == 100
    expected = set(itertools.product(manifest["scenarios"], manifest["policies"], manifest["seeds"]))
    actual = {}
    for run in report["runs"]:
        seed = int(re.search(r"seed (\d+)", run["notes"]).group(1))
        key = (run["scenario_id"], run["strategy"], seed)
        assert key not in actual, key
        assert run["experiment"] == manifest["experiments"][run["strategy"]], key
        actual[key] = run
    assert actual.keys() == expected
    return manifest, actual


def summarize(runs):
    timings = sorted(r["kpis"]["replan_p95_seconds"] for r in runs.values())
    return {
        "runs": len(timings),
        "replan_p95_seconds_across_runs": {
            "min": timings[0],
            "median": statistics.median(timings),
            "max": timings[-1],
            "runs_above_2_seconds": sum(v > 2 for v in timings),
        },
        "violation_counts": {
            key: sum(r["violations"][key] for r in runs.values()) for key in next(iter(runs.values()))["violations"]
        },
    }


if __name__ == "__main__":
    frozen, original = load(Path(sys.argv[1]), baseline=True)
    candidate, rerun = load(Path(sys.argv[2]), baseline=False)
    fields = ("scenarios", "policies", "seeds", "time_config", "experiments", "experiment_fingerprints")
    for field in fields:
        assert frozen[field] == candidate[field], field
    assert original.keys() == rerun.keys()
    assert all(original[key]["violations"] == rerun[key]["violations"] for key in original)
    print(
        json.dumps(
            {
                "matched_manifest_fields": fields,
                "experiment_fingerprints": candidate["experiment_fingerprints"],
                "frozen": {"libraries": frozen["libraries"], **summarize(original)},
                "candidate": {"libraries": candidate["libraries"], **summarize(rerun)},
            },
            indent=2,
        )
    )
