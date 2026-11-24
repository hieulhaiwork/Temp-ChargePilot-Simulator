# Evidence AI-4.1 — Deterministic WHY Engine (Gate 2)

Gate 2 candidate applies [candidate.patch](raw/candidate.patch) (SHA-256 `fe89fc04bef12180a10333050770dd64764484fdc56d5accee720427a230c36c`) on top of local base `490f43300afb05ef7e809099a77e0c7174e272fb` (corresponding to Tech Lead–approved G1 mirror `fed2c5e395c3a6ac3e1798ce52d0e4b4e4abd009`).

- All gates ran inside a clean `git clone --detach` checkout isolated from workspace `.env` and gitignored local directories (`src/simulator/claude_rd/`).
- Deterministic WHY evaluation (`run_why_eval.py`, zero LLM judge) produced [why-eval-summary.json](raw/why-eval/why-eval-summary.json) plus concrete Resident/Operator `WhyAnswer` JSON examples (`example-resident_queue.json`, `example-resident_power.json`, `example-operator_overview.json`).
- Standalone golden used `core.autocrlf=true` and the hash-verified P0 historical CRLF reference archive (`38/38 OK`, CSV byte-identical).
- Frozen backend benchmark ran all 100 runs (`5 scenarios × 4 policies × 5 seeds`), matching all 4 policy experiment fingerprints with `0` problems and `0` hard violations.
- PostgreSQL availability probe exited `127` (no local PostgreSQL server, `TEST_DATABASE_URL`, or Docker daemon); PostgreSQL runtime remains **PENDING**.

## Reproducing from P-019 root

```bash
scratch=$(mktemp -d /tmp/chargepilot-g2-repro.XXXXXX)
G2_EVIDENCE_OUT="$scratch/evidence" \
  bash eval/evidence/2026-11-24-ai4-4-1/run_gate.sh "$scratch"
```

[Exit codes](raw/exit-codes.tsv) · [Checksums](CHECKSUMS.sha256) · [Phase 4.1 Report](../../../docs/ai4/PHASE_4_1_REPORT.md)
