#!/usr/bin/env bash
# From P-019 root. Pass an empty/new scratch directory.
set -eu
root=$PWD
scratch=$1
ev=$root/eval/evidence/2026-11-24-ai4-4-0-remediation
raw=${G1_EVIDENCE_OUT:-"$ev/raw"}
mkdir -p "$raw"
p0=$root/eval/evidence/2026-11-24-ai4-p0
venv=${P0_VENV:-"$root/.simulator"}
base=d2b5d4869bff35ad9e417bee504c6dbf652258b1
patch=$raw/candidate.patch
mkdir -p "$scratch"
log() {
    local name=$1 rc=0 start
    shift
    start=$(date -u +%FT%TZ)
    { printf 'cwd=%s\n$ ' "$PWD"; printf '%q ' "$@"; printf '\n'; } > "$raw/$name.stdout.txt"
    "$@" >> "$raw/$name.stdout.txt" 2> "$raw/$name.stderr.txt" || rc=$?
    printf '%s\t%s\t%s\t%s\n' "$name" "$rc" "$start" "$(date -u +%FT%TZ)" >> "$raw/exit-codes.tsv"
    return "$rc"
}
isolated() {
    env -i PATH="$venv/bin:/usr/bin:/bin" LANG=C.UTF-8 TZ=UTC PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 "$@"
}
log gate-clone git clone --quiet --no-hardlinks --no-checkout "$root" "$scratch/code"
log gate-checkout git -C "$scratch/code" checkout --quiet --detach "$base"
log gate-apply git -C "$scratch/code" apply "$patch"
log gate-code git -C "$scratch/code" status --short --branch
log gate-patch-sha256 sha256sum "$patch"
log environment isolated bash -c 'uname -srmo; cat /etc/os-release; lscpu; python -VV; python -m pip list --format=freeze'
log workspace-head git rev-parse HEAD
log mirror-reviewed git -C "$root/../P-019-chatgpt" rev-parse '6667dead49d047c4971f73a95ff47229dc8dc4e9^{tree}'
log reviewed-g1-patch-sha256 sha256sum "$root/eval/evidence/2026-11-24-ai4-4-0/raw/candidate.patch"
log workspace-base-product-diff git diff --exit-code ce23136d "$base" -- src tests config migrations frontend
cd "$scratch/code"

(
    log backend-tests isolated timeout 300s python -m pytest tests/ -q -rs || :
    log focused-tests isolated timeout 90s python -m pytest tests/test_services/test_safety_event_delivery.py         tests/test_services/test_decision_trace.py tests/test_services/test_fork_isolation.py tests/test_db/test_migrations.py         tests/test_architecture.py -q || :
    log simulator-tests isolated timeout 120s python -m pytest src/simulator/tests/ -q || :
    log postgres-availability bash -c '
        for exe in postgres pg_isready initdb; do command -v "$exe" || :; done
        if [[ -n ${TEST_DATABASE_URL:-} ]]; then printf "TEST_DATABASE_URL is set\n"; fi
        if command -v docker >/dev/null; then timeout 20s docker info --format "{{.ServerVersion}}"; else exit 127; fi
    ' || :
) &
tests_pid=$!
(
    log ruff-lint isolated ruff check src tests scripts/refactor eval migrations/versions/0004_full_decision_traces.py || :
    log ruff-format isolated ruff format --check src tests scripts/refactor eval migrations/versions/0004_full_decision_traces.py || :
    log docs isolated python scripts/check_docs.py || :
    log openapi isolated python scripts/export_openapi.py --check || :
    log agent-offline isolated python eval/run_agent_eval.py --offline --out "$raw/agent-offline" || :
    log ast-parity isolated python scripts/refactor/compare_ast_manifest.py         docs/refactor/raw/phase4-final/preserved_baseline_manifest.txt -- src || :
) &
checks_pid=$!
(
    log benchmark isolated timeout 600s python eval/run_benchmark.py --seeds 1,2,3,4,5
    mkdir -p "$raw/backend-benchmark"
    cp eval/results/{manifest.json,benchmark.json,benchmark.md} "$raw/backend-benchmark/"
    frozen=eval/evidence/2026-11-24-unified-core-frozen-baseline
    log benchmark-compare isolated python scripts/refactor/compare_backend_benchmark.py         "$frozen/benchmark.json" "$raw/backend-benchmark/benchmark.json" || :
    log benchmark-provenance isolated python "$p0/check_benchmark_provenance.py" "$frozen" "$raw/backend-benchmark" || :
) &
bench_pid=$!
(
    log golden-clone git clone --quiet --no-hardlinks --no-checkout "$root" "$scratch/crlf"
    log golden-checkout git -C "$scratch/crlf" -c core.autocrlf=true checkout --quiet --detach "$base"
    log golden-apply git -C "$scratch/crlf" -c core.autocrlf=true apply "$patch"
    log golden-scenario-hashes sha256sum "$scratch/crlf"/src/simulator/scenario/{mvp1,vinfast_dc_2port_120kw}.json
    ref=$p0/raw/golden-crlf-outputs.tar.gz
    log golden-reference-sha256 sha256sum "$ref"
    log golden-reference-extract tar -xzf "$ref" -C "$scratch" crlf-golden-reference
    (
        cd "$scratch/crlf"
        log golden-run isolated timeout 240s python scripts/refactor/run_sim_kpi_gate.py run "$scratch/golden-candidate"
    )
    log golden-compare isolated python scripts/refactor/run_sim_kpi_gate.py compare "$scratch/crlf-golden-reference"         "$scratch/golden-candidate" --evidence eval/evidence/2026-11-22/raw/sim-hardware         --module-map docs/refactor/raw/phase4-final/module_map.txt || :
    log golden-archive tar -czf "$raw/golden-crlf-candidate.tar.gz" -C "$scratch" golden-candidate
) &
golden_pid=$!
for job in "$tests_pid" "$checks_pid" "$bench_pid" "$golden_pid"; do
    wait "$job" || :
done
