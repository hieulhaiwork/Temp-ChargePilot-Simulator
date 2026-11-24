#!/usr/bin/env bash
# From repository root, use scratch directory printed by run.sh (parent of evidence/).
set -eu
root=$PWD
ev=$1
logs=$ev/evidence
venv=${P0_VENV:-"$root/.simulator"}
driver=$root/eval/evidence/2026-11-24-ai4-p0
source <(sed -n '/^run() {/,/^}/p' "$driver/run.sh")
initial=$ev/checkout
head=$(git -C "$initial" rev-parse HEAD)
historical=$(git -C "$initial" rev-parse 70d0eaf)
reference=$ev/crlf-reference-checkout
candidate=$ev/crlf-candidate-checkout
isolated() {
    env -i PATH="$venv/bin:/usr/bin:/bin" LANG=C.UTF-8 TZ=UTC PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 "$@"
}
run crlf-candidate-clone git clone --no-hardlinks --quiet --no-checkout "$initial" "$candidate"
run crlf-reference-clone git clone --no-hardlinks --quiet --no-checkout "$initial" "$reference"
run crlf-candidate-checkout git -C "$candidate" -c core.autocrlf=true checkout --quiet --detach "$head"
run crlf-reference-checkout git -C "$reference" -c core.autocrlf=true checkout --quiet --detach "$historical"
for tree in "$candidate" "$reference"; do
    run "${tree##*/}-tracked-diff" git -C "$tree" -c core.autocrlf=true diff --exit-code HEAD --
    run "${tree##*/}-scenario-hashes" sha256sum "$tree"/src/simulator/scenario/{mvp1,vinfast_dc_2port_120kw}.json
done
mkdir -p "$reference/scripts/refactor"
cp "$candidate/scripts/refactor/run_sim_kpi_gate.py" "$reference/scripts/refactor/"
(
    cd "$reference"
    run crlf-golden-reference isolated python scripts/refactor/run_sim_kpi_gate.py run "$ev/crlf-golden-reference"
) &
ref_task=$!
(
    cd "$candidate"
    run crlf-golden-candidate isolated python scripts/refactor/run_sim_kpi_gate.py run "$ev/crlf-golden-candidate"
) &
candidate_task=$!
wait "$ref_task"
wait "$candidate_task"
cd "$initial"
run crlf-golden-compare isolated python scripts/refactor/run_sim_kpi_gate.py compare "$ev/crlf-golden-reference"     "$ev/crlf-golden-candidate" --evidence eval/evidence/2026-11-22/raw/sim-hardware     --module-map docs/refactor/raw/phase4-final/module_map.txt
run crlf-golden-archive tar -czf "$logs/golden-crlf-outputs.tar.gz" -C "$ev" crlf-golden-reference crlf-golden-candidate
