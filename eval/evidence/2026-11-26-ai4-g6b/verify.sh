#!/usr/bin/env bash
# Usage from a clean candidate export: verify.sh RAW_DIR
set -euo pipefail
raw=$(realpath "$1")
mkdir -p "$raw"
ledger="$raw/backend-exits.tsv"
printf 'check\texit\n' > "$ledger"
failed=0

check() {
    local name=$1 rc=0
    shift
    { printf '$ '; printf '%q ' "$@"; printf '\n'; } > "$raw/$name.log"
    "$@" >> "$raw/$name.log" 2>&1 || rc=$?
    printf '%s\t%s\n' "$name" "$rc" >> "$ledger"
    if (( rc )); then failed=1; fi
}

export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 LANG=C.UTF-8 TZ=UTC
check g6b timeout -k 3s 120s python -m pytest -q -o junit_family=legacy --junitxml="$raw/focused.xml" \
    tests/test_api/test_unified_copilot.py
check g2-g5-g6a timeout -k 3s 180s python -m pytest -q \
    tests/test_services/test_why*.py tests/test_services/test_counterfactual_foundation.py \
    tests/test_services/test_g3_runtime_readiness.py tests/test_services/test_what_if.py \
    tests/test_services/test_recommendation{,_hybrid}.py tests/test_api/test_copilot.py
check legacy-f1 timeout -k 3s 90s python -m pytest -q tests/test_llm_chat tests/test_api/test_chat_response.py tests/test_api/test_routes.py
check architecture timeout -k 3s 90s python -m pytest -q tests/test_architecture.py
check backend timeout -k 3s 240s python -m pytest -q -rs tests
check simulator timeout -k 3s 90s python -m pytest -q src/simulator/tests
check ruff-lint ruff check src tests scripts/refactor eval --extend-exclude eval/evidence/2026-11-26-ai4-g5/raw
check ruff-format ruff format --check src tests scripts/refactor eval --extend-exclude eval/evidence/2026-11-26-ai4-g5/raw
check docs python scripts/check_docs.py
check openapi python scripts/export_openapi.py --check
check offline-f1 python eval/run_agent_eval.py --offline --out "$raw/offline-f1"

exit "$failed"
