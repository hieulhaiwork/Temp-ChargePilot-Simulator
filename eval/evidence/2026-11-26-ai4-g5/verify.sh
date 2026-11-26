#!/usr/bin/env bash
# Run from the repository root with two clean exports, one with the G5 code/test patch applied.
# Usage: verify.sh BASELINE_TREE CANDIDATE_TREE RAW_DIR VENV_BIN
set -euo pipefail
base=$(realpath "$1")
candidate=$(realpath "$2")
raw=$(realpath "$3")
venv=$(realpath "$4")
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

regression=(
    tests/test_architecture.py
    tests/test_services/test_why*.py
    tests/test_services/test_counterfactual_foundation.py
    tests/test_services/test_g3_runtime_readiness.py
    tests/test_services/test_what_if.py
    tests/test_api/test_copilot.py
)
shared=(
    tests/test_services/test_admission*.py
    tests/test_services/test_booking_concurrency.py
    tests/test_services/test_control_and_charging.py
    tests/test_services/test_repository*.py
    tests/test_services/test_decision_trace.py
    tests/test_services/test_safety_event_delivery.py
    tests/test_services/test_failsafe_after_apply.py
    tests/test_services/test_fork_isolation.py
    tests/test_services/test_populate_contract_fields.py
    tests/test_guard
    tests/test_api/test_review_fixes.py
    tests/test_api/test_chat_response.py
    tests/test_api/test_routes.py
)
cd "$base"
check baseline-focused-native offline timeout -k 3s 180s python -m pytest -q "${regression[@]}" "${shared[@]}"
cd "$candidate"
check candidate-g5 offline timeout -k 3s 90s python -m pytest -q -o junit_family=legacy \
    --junitxml="$raw/g5-results.xml" tests/test_services/test_recommendation.py
check candidate-g2-g3-g4-g6a offline timeout -k 3s 180s python -m pytest -q "${regression[@]}"
check candidate-g3-eval offline timeout -k 3s 90s env PYTHONPATH=. python \
    eval/evidence/2026-11-24-ai4-4-2a/run_g3_eval.py "$raw/candidate-g3-eval"
check candidate-backend offline timeout -k 3s 240s python -m pytest -q -rs tests/
check candidate-standalone offline timeout -k 3s 90s python -m pytest -q src/simulator/tests/
check candidate-ruff-lint offline ruff check src tests scripts/refactor eval
check candidate-ruff-format offline ruff format --check src tests scripts/refactor eval
check candidate-docs offline python scripts/check_docs.py
check candidate-openapi offline python scripts/export_openapi.py --check
check candidate-offline-f1 offline python eval/run_agent_eval.py --offline --out "$raw/candidate-offline-f1"
exit "$failed"
