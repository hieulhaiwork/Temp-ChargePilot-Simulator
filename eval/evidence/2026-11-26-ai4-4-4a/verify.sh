#!/usr/bin/env bash
# Usage: bash verify.sh <backend|frontend> <source-tree> <raw-dir> <toolkit-bin>
set -euo pipefail
group=$1
tree=$(realpath "$2")
raw=$(realpath "$3")
toolkit=$(realpath "$4")
ledger="$raw/$group-exits.tsv"
printf 'check\texit\tstatus\n' > "$ledger"

check() {
    local name=$1 rc=0 verdict=PASS
    shift
    { printf 'cwd=%s\n$ ' "$PWD"; printf '%q ' "$@"; printf '\n'; } > "$raw/$name.stdout.txt"
    "$@" >> "$raw/$name.stdout.txt" 2> "$raw/$name.stderr.txt" || rc=$?
    if (( rc )); then verdict=FAIL; fi
    printf '%s\t%s\t%s\n' "$name" "$rc" "$verdict" >> "$ledger"
    return "$rc"
}

isolated() {
    env -i PATH="$toolkit:/usr/bin:/bin" LANG=C.UTF-8 TZ=UTC PYTHONDONTWRITEBYTECODE=1 "$@"
}

if [[ $group == backend ]]; then
    cd "$tree"
    check focused-g6a isolated timeout -k 3s 100s python -m pytest -vv tests/test_api/test_copilot.py
    failed=0
    check demo-fallback isolated timeout -k 3s 60s python \
        eval/evidence/2026-11-26-ai4-4-4a/run_demo.py --out "$raw/demo-output.json" || failed=1
    check legacy-f1 isolated timeout -k 3s 100s python -m pytest -q tests/test_llm_chat tests/test_api/test_routes.py || failed=1
    check regression-g2-g3-g4 isolated timeout -k 3s 150s python -m pytest -q \
        tests/test_services/test_why_engine.py tests/test_services/test_why_temporal_and_auth.py \
        tests/test_services/test_why_g2_remediation.py tests/test_services/test_why_g2_final_fix.py \
        tests/test_services/test_counterfactual_foundation.py \
        tests/test_services/test_g3_runtime_readiness.py tests/test_services/test_what_if.py || failed=1
    check g3-eval isolated timeout -k 3s 100s env PYTHONPATH=. python \
        eval/evidence/2026-11-24-ai4-4-2a/run_g3_eval.py "$raw/g3-eval" || failed=1
    check architecture isolated timeout -k 3s 100s python -m pytest -q tests/test_architecture.py || failed=1
    check backend-tests isolated timeout -k 5s 300s python -m pytest tests/ -q -rs || failed=1
    check ruff-lint isolated ruff check src tests scripts/refactor eval || failed=1
    check ruff-format isolated ruff format --check src tests scripts/refactor eval || failed=1
    check docs isolated python scripts/check_docs.py || failed=1
    check openapi isolated python scripts/export_openapi.py --check || failed=1
    check f1-offline isolated python eval/run_agent_eval.py --offline --out "$raw/f1-offline" || failed=1
    exit "$failed"
fi

[[ $group == frontend ]]
cd "$tree/frontend"
export PATH="$toolkit:$PATH" NEXT_TELEMETRY_DISABLED=1
failed=0
check frontend-lint timeout -k 5s 180s npm run lint || failed=1
check frontend-typecheck timeout -k 5s 180s npm run typecheck || failed=1
check frontend-tests timeout -k 5s 180s npm test || failed=1
build_args=()
if [[ ${G6A_WEBPACK:-0} == 1 ]]; then
    build_args=(-- --webpack)
fi
check frontend-build timeout -k 5s 240s npm run build "${build_args[@]}" || failed=1
generated=$(mktemp /tmp/p019-g6a-schema.XXXXXX)
if check frontend-api-types timeout -k 5s 90s \
    node_modules/.bin/openapi-typescript ./openapi.json -o "$generated"; then
    check frontend-api-compare cmp "$generated" src/lib/api/schema.d.ts || failed=1
else
    failed=1
fi
exit "$failed"
