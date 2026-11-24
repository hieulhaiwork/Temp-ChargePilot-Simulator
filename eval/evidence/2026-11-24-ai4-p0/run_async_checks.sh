#!/usr/bin/env bash
# From repository root, pass the scratch directory printed by run.sh (parent of evidence/).
set -eu
root=$PWD
ev=$1
logs=$ev/evidence
venv=${P0_VENV:-"$root/.simulator"}
driver=$root/eval/evidence/2026-11-24-ai4-p0
source <(sed -n '/^run() {/,/^}/p' "$driver/run.sh")
cd "$ev/checkout"
isolated() {
    env -i PATH="$venv/bin:/usr/bin:/bin" LANG=C.UTF-8 TZ=UTC PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$@"
}
run socketpair-outside isolated python -c 'import socket; a,b=socket.socketpair(); print(a.send(b"x"), b.recv(1))'
run backend-tests-retry isolated timeout 300s python -m pytest tests/ -q -rs || :
run issue-probe-retry isolated timeout 45s python "$driver/probe_issues.py" || :
run benchmark-retry isolated timeout 600s python eval/run_benchmark.py --seeds 1,2,3,4,5
mkdir -p "$logs/backend-benchmark"
cp eval/results/{manifest.json,benchmark.json,benchmark.md} "$logs/backend-benchmark/"
frozen=eval/evidence/2026-11-24-unified-core-frozen-baseline
run benchmark-provenance isolated python "$driver/check_benchmark_provenance.py" "$frozen" "$logs/backend-benchmark" || :
run benchmark-compare-retry isolated python scripts/refactor/compare_backend_benchmark.py "$frozen/benchmark.json" "$logs/backend-benchmark/benchmark.json" || :
run checkout-final-diff-retry git diff --exit-code HEAD -- || :
