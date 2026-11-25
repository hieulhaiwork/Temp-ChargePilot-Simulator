#!/usr/bin/env bash
# From P-019 root. Pass a new scratch directory and an evidence directory containing candidate.patch.
set -euo pipefail
root=$PWD
scratch=$(realpath -m "$1")
raw=$(realpath "$2")
ev=$root/eval/evidence/2026-11-24-ai4-4-2a
p0=$root/eval/evidence/2026-11-24-ai4-p0
venv=${P0_VENV:-"$root/.simulator"}
base=4658b1f068350c130ed5ed1a744c19a7b8cd522c
patch=$raw/candidate.patch
test -s "$patch"
test ! -e "$raw/exit-codes.tsv"
mkdir "$scratch"
printf 'gate\texit\texpected\tresult\tstart_utc\tend_utc\n' > "$raw/exit-codes.tsv"
finish() {
    local rc=$? result=PASS
    if (( rc != 0 )); then result=FAIL; fi
    printf 'overall\t%s\t0\t%s\t-\t%s\n' "$rc" "$result" "$(date -u +%FT%TZ)" >> "$raw/exit-codes.tsv"
}
trap finish EXIT

record() {
    local name=$1 expected=$2 rc=0 start result
    shift 2
    start=$(date -u +%FT%TZ)
    { printf 'cwd=%s\n$ ' "$PWD"; printf '%q ' "$@"; printf '\n'; } > "$raw/$name.stdout.txt"
    "$@" >> "$raw/$name.stdout.txt" 2> "$raw/$name.stderr.txt" || rc=$?
    case "$expected" in
        "$rc") result=PASS ;;
        pending) result=PENDING ;;
        *) result=FAIL ;;
    esac
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$rc" "$expected" "$result" "$start" "$(date -u +%FT%TZ)" \
        >> "$raw/exit-codes.tsv"
    [[ $result != FAIL ]]
}
isolated() {
    env -i PATH="$venv/bin:/usr/bin:/bin" LANG=C.UTF-8 TZ=UTC PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 "$@"
}

# Independent groups finish even if a check mismatches its expected code. Prerequisites fail their group.
fail_before() (
    record fail-before-clone 0 git clone --quiet --no-hardlinks --no-checkout "$root" "$scratch/fail-before"
    record fail-before-checkout 0 git -C "$scratch/fail-before" checkout --quiet --detach "$base"
    record fail-before-apply 0 git -C "$scratch/fail-before" apply "$ev/raw/fail-before-test.patch"
    cd "$scratch/fail-before"
    record fail-before-f01 1 isolated timeout -k 5s 90s python -m pytest tests/test_services/test_g3_runtime_readiness.py -q
    record fail-before-f01-count 0 rg -q '^3 failed' "$raw/fail-before-f01.stdout.txt"
)

checks() (
    cd "$scratch/code"
    local failed=0
    record focused-g3 0 isolated timeout -k 5s 180s python -m pytest \
        tests/test_services/test_g3_runtime_readiness.py \
        tests/test_services/test_counterfactual_foundation.py \
        tests/test_services/test_fork_isolation.py \
        tests/test_services/test_admission.py \
        tests/test_services/test_admission_consistency.py \
        tests/test_services/test_safety_event_delivery.py \
        tests/test_services/test_decision_trace.py \
        tests/test_services/test_why_engine.py \
        tests/test_services/test_why_temporal_and_auth.py \
        tests/test_services/test_why_g2_remediation.py \
        tests/test_services/test_why_g2_final_fix.py \
        tests/test_db/test_migrations.py \
        tests/test_refactor/test_registry_extension.py \
        tests/test_architecture.py -q || failed=1
    record g3-eval 0 isolated timeout -k 5s 180s env PYTHONPATH=. python \
        eval/evidence/2026-11-24-ai4-4-2a/run_g3_eval.py "$raw/g3-eval" || failed=1
    record backend-tests 0 isolated timeout -k 5s 300s python -m pytest tests/ -q -rs || failed=1
    record simulator-tests 0 isolated timeout -k 5s 180s python -m pytest src/simulator/tests/ -q || failed=1
    return "$failed"
)

quality() (
    cd "$scratch/code"
    local failed=0
    record ruff-lint 0 isolated ruff check src tests scripts/refactor eval || failed=1
    record ruff-format 0 isolated ruff format --check src tests scripts/refactor eval || failed=1
    record docs 0 isolated python scripts/check_docs.py || failed=1
    record openapi 0 isolated python scripts/export_openapi.py --check || failed=1
    record agent-offline 0 isolated python eval/run_agent_eval.py --offline --out "$raw/agent-offline" || failed=1
    record ast-parity 0 isolated python scripts/refactor/compare_ast_manifest.py \
        docs/refactor/raw/phase4-final/preserved_baseline_manifest.txt -- src || failed=1
    record postgres-runtime pending bash -c '
        for exe in postgres pg_isready initdb; do command -v "$exe" || true; done
        if command -v docker >/dev/null; then timeout -k 2s 10s docker info --format "{{.ServerVersion}}" || true; fi
        printf "PostgreSQL runtime verification is pending.\n"
        exit 77
    '
    return "$failed"
)

benchmark() (
    cd "$scratch/code"
    record benchmark 0 isolated timeout -k 5s 600s python eval/run_benchmark.py --seeds 1,2,3,4,5
    mkdir "$raw/backend-benchmark"
    record benchmark-artifacts 0 cp eval/results/{manifest.json,benchmark.json,benchmark.md} "$raw/backend-benchmark/"
    frozen=eval/evidence/2026-11-24-unified-core-frozen-baseline
    record benchmark-compare 0 isolated python scripts/refactor/compare_backend_benchmark.py \
        "$frozen/benchmark.json" "$raw/backend-benchmark/benchmark.json"
    record benchmark-provenance 0 isolated python "$p0/check_benchmark_provenance.py" "$frozen" "$raw/backend-benchmark"
)

golden() (
    record golden-clone 0 git clone --quiet --no-hardlinks --no-checkout "$root" "$scratch/crlf"
    record golden-checkout 0 git -C "$scratch/crlf" -c core.autocrlf=true checkout --quiet --detach "$base"
    record golden-apply 0 git -C "$scratch/crlf" -c core.autocrlf=true apply "$patch"
    record golden-scenario-hashes 0 sha256sum "$scratch/crlf"/src/simulator/scenario/{mvp1,vinfast_dc_2port_120kw}.json
    record golden-scenario-provenance 0 bash -c 'cd "$1"
        printf "%s\n" \
            "c5ad0f748df618cc1c1e7b8d2ec1b90d005d368c538acb5d22a785ed20ff57e3  mvp1.json" \
            "c05e3251f5956dabb6d45211025b69d70e8af587e6db60c1918603abb11353c5  vinfast_dc_2port_120kw.json" |
            sha256sum --check' _ "$scratch/crlf/src/simulator/scenario"
    ref=$p0/raw/golden-crlf-outputs.tar.gz
    record golden-reference-sha256 0 sha256sum "$ref"
    record golden-reference-provenance 0 bash -c 'printf "%s  %s\n" \
        2b442feb6c443bad9ae17aef66e90d849b256c719ea49b84fdca9c25261fe2bd "$1" | sha256sum --check' _ "$ref"
    record golden-reference-extract 0 tar -xzf "$ref" -C "$scratch" crlf-golden-reference
    cd "$scratch/crlf"
    record golden-run 0 isolated timeout -k 5s 240s python scripts/refactor/run_sim_kpi_gate.py run "$scratch/golden-candidate"
    record golden-compare 0 isolated python scripts/refactor/run_sim_kpi_gate.py compare "$scratch/crlf-golden-reference" \
        "$scratch/golden-candidate" --evidence eval/evidence/2026-11-22/raw/sim-hardware \
        --module-map docs/refactor/raw/phase4-final/module_map.txt
    record golden-archive 0 tar -czf "$raw/golden-crlf-candidate.tar.gz" -C "$scratch" golden-candidate
)

record workspace-head 0 git rev-parse HEAD
record gate-clone 0 git clone --quiet --no-hardlinks --no-checkout "$root" "$scratch/code"
record gate-checkout 0 git -C "$scratch/code" checkout --quiet --detach "$base"
record gate-apply 0 git -C "$scratch/code" apply "$patch"
record gate-code 0 git -C "$scratch/code" status --short --branch --untracked-files=all
record gate-patch-sha256 0 sha256sum "$patch"
record environment 0 isolated bash -c 'uname -srmo; cat /etc/os-release; lscpu; python -VV; python -m pip list --format=freeze'

fail_before & fail_before_pid=$!
checks & checks_pid=$!
quality & quality_pid=$!
benchmark & benchmark_pid=$!
golden & golden_pid=$!
overall=0
for job in "$fail_before_pid" "$checks_pid" "$quality_pid" "$benchmark_pid" "$golden_pid"; do
    wait "$job" || overall=1
done
exit "$overall"
