#!/usr/bin/env bash
# Run with a clean export of merged develop with the final G5 candidate patch applied.
# Usage: verify.sh CANDIDATE_TREE RAW_DIR VENV_BIN
set -euo pipefail
candidate=$(realpath "$1")
raw=$(realpath "$2")
venv=$(realpath "$3")
ledger="$raw/verification-exits.tsv"
printf 'check\texit\n' > "$ledger"
failed=0

check() {
    local name=$1 rc=0
    shift
    { printf 'cwd=%s\n$ ' "$PWD"; printf '%q ' "$@"; printf '\n'; } > "$raw/$name.log"
    "$@" >> "$raw/$name.log" 2>&1 || rc=$?
    printf '%s\t%s\n' "$name" "$rc" >> "$ledger"
    if (( rc )); then failed=1; fi
}
offline() {
    env -i PATH="$venv:/usr/bin:/bin" LANG=C.UTF-8 TZ=UTC PYTHONDONTWRITEBYTECODE=1 \
        OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$@"
}

cd "$candidate"
check focused-g5 offline timeout -k 3s 120s python -m pytest -q -o junit_family=legacy \
    --junitxml="$raw/g5-results.xml" tests/test_services/test_recommendation{,_hybrid}.py
check g2-g3-g4-g6a offline timeout -k 3s 180s python -m pytest -q \
    tests/test_services/test_why*.py tests/test_services/test_counterfactual_foundation.py \
    tests/test_services/test_g3_runtime_readiness.py tests/test_services/test_what_if.py tests/test_api/test_copilot.py
check architecture offline timeout -k 3s 90s python -m pytest -q tests/test_architecture.py
check backend offline timeout -k 3s 240s python -m pytest -q -rs tests/
check standalone offline timeout -k 3s 90s python -m pytest -q src/simulator/tests/
check ruff-check offline ruff check src tests scripts/refactor eval
check ruff-format offline ruff format --check src tests scripts/refactor eval
check docs offline python scripts/check_docs.py
check openapi offline python scripts/export_openapi.py --check
check offline-f1 offline python eval/run_agent_eval.py --offline --out "$raw/offline-f1"
exit "$failed"
