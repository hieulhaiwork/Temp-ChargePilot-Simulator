#!/usr/bin/env bash
# From the P-019 root. Set MIRROR_CLONE if the mirror is elsewhere.
set -eu
root=$PWD
ev=$(mktemp -d /tmp/chargepilot-p0.XXXXXX)
logs=$ev/evidence
mkdir -p "$logs"
mirror=${MIRROR_CLONE:-"$root/../P-019-chatgpt"}
baseline=4f1477e84ac818549a69a74eb00e4b827fae230e
head=$(git rev-parse "${P0_BASELINE_HEAD:-HEAD}")
venv=${P0_VENV:-"$root/.simulator"}
historical=70d0eaf
umask 077
printf 'Evidence directory %s\n' "$logs"
printf 'check\texit_code\tutc_start\tutc_end\n' > "$logs/exit-codes.tsv"

run() {
    local name=$1 begun rc=0
    shift
    begun=$(date -u +%FT%TZ)
    { printf 'cwd=%s\n$ ' "$PWD"; printf '%q ' "$@"; printf '\n'; } > "$logs/$name.stdout.txt"
    "$@" >> "$logs/$name.stdout.txt" 2> "$logs/$name.stderr.txt" || rc=$?
    printf '%s\t%s\t%s\t%s\n' "$name" "$rc" "$begun" "$(date -u +%FT%TZ)" >> "$logs/exit-codes.tsv"
    return "$rc"
}

run initial-status git status --short --branch || :
run initial-head git rev-parse HEAD || :
run initial-branch git branch --show-current || :
run initial-log git log -5 --oneline || :
run initial-tracked-diff git diff --exit-code HEAD -- || :
run local-tree git ls-tree -r "$head" || :
run mirror-tree git -C "$mirror" ls-tree -r "$baseline" || :
run mirror-origin git -C "$mirror" remote get-url origin || :
run mirror-tracking git -C "$mirror" rev-parse origin/main || :
run mirror-tree-diff diff -u "$logs/local-tree.stdout.txt" "$logs/mirror-tree.stdout.txt" || :
run bootstrap git clone --no-hardlinks --quiet --no-checkout "$root" "$ev/checkout"
cd "$ev/checkout"
run checkout git checkout --quiet --detach "$head"
run checkout-status git status --short --branch
mkdir "$ev/historical"
run historical-export bash -o pipefail -c 'git archive "$1" | tar -x -C "$2"' _ "$historical" "$ev/historical"
run historical-id git rev-parse "$historical"
run environment env -i PATH="$venv/bin:/usr/bin:/bin" LANG=C.UTF-8 TZ=UTC bash -c '
    uname -srmo
    cat /etc/os-release
    lscpu
    python -VV
    python -m pip list --format=freeze
    ruff --version
'
run pip-check env -i PATH="$venv/bin:/usr/bin:/bin" LANG=C.UTF-8 python -m pip check || :
run config-hashes bash -c 'sha256sum config/*.yaml config/scenarios/*.yaml requirements*.txt scripts/refactor/run_sim_kpi_gate.py docs/refactor/raw/phase4-final/module_map.txt eval/evidence/2026-11-24-unified-core-frozen-baseline/{manifest,benchmark}.json' || :

isolated() {
    env -i PATH="$venv/bin:/usr/bin:/bin" LANG=C.UTF-8 TZ=UTC PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 "$@"
}

# Run the common checks and the two independent simulation tracks concurrently.
(
    if [[ ${P0_SKIP_ASYNC:-0} != 1 ]]; then
        run backend-tests isolated timeout 300s python -m pytest tests/ -q -rs || :
    fi
) &
p_backend=$!
(
    run simulator-tests isolated python -m pytest src/simulator/tests/ -q || :
) &
p_sim=$!
(
    run ruff-check isolated ruff check src tests scripts/refactor eval || :
    run ruff-format isolated ruff format --check src tests scripts/refactor eval || :
    run docs-check isolated python scripts/check_docs.py || :
    run openapi-check isolated python scripts/export_openapi.py --check || :
    run agent-offline isolated python eval/run_agent_eval.py --offline --out "$logs/agent-offline" || :
) &
p_checks=$!
(
    run golden-candidate isolated python scripts/refactor/run_sim_kpi_gate.py run "$ev/golden-candidate" || :
    # Reuse the unchanged gate driver with ROOT pointing at the historical tree.
    mkdir -p "$ev/historical/scripts/refactor"
    cp scripts/refactor/run_sim_kpi_gate.py "$ev/historical/scripts/refactor/run_sim_kpi_gate.py"
    (
        cd "$ev/historical"
        run golden-reference isolated python scripts/refactor/run_sim_kpi_gate.py run "$ev/golden-reference" || :
    )
    run golden-compare isolated python scripts/refactor/run_sim_kpi_gate.py compare "$ev/golden-reference"         "$ev/golden-candidate" --evidence eval/evidence/2026-11-22/raw/sim-hardware         --module-map docs/refactor/raw/phase4-final/module_map.txt || :
    run golden-archive tar -czf "$logs/golden-outputs.tar.gz" -C "$ev" golden-reference golden-candidate || :
) &
p_golden=$!
(
    if [[ ${P0_SKIP_ASYNC:-0} == 1 ]]; then
        exit 0
    fi
    run benchmark isolated timeout 600s python eval/run_benchmark.py --seeds 1,2,3,4,5 || exit $?
    mkdir -p "$logs/backend-benchmark"
    cp eval/results/{manifest.json,benchmark.json,benchmark.md} "$logs/backend-benchmark/"
    run benchmark-compare isolated python scripts/refactor/compare_backend_benchmark.py         eval/evidence/2026-11-24-unified-core-frozen-baseline/benchmark.json "$logs/backend-benchmark/benchmark.json" || :
) &
p_bench=$!
for job in "$p_backend" "$p_sim" "$p_checks" "$p_golden" "$p_bench"; do
    wait "$job" || :
done
run checkout-final-diff git diff --exit-code HEAD -- || :
