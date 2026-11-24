# Evidence AI-4.1 Remediation — Deterministic WHY Engine (Gate 2 Re-Review)

Reviewed mirror `6ba13b8021998e03e15b0ec26cec93d484b70a05` returned `CHANGES REQUIRED` (G2-F01–G2-F09).

- **Local base:** `490f43300afb05ef7e809099a77e0c7174e272fb` (Tech Lead–approved G1 mirror `fed2c5e395c3a6ac3e1798ce52d0e4b4e4abd009`).
- **Fail-before evidence:** [remediation-before.stdout.txt](raw/remediation-before.stdout.txt) ran [regression-before.patch](raw/regression-before.patch) (SHA-256 `3162fc0f198c0c40ec9bc8a3f941b142b9d902bcc5755c45b3ba5b23cc671479`) against the reviewed G2 candidate (`fe89fc04...`), yielding **14/14 FAILED (exit 1)** and confirming G2-F01–G2-F07 empirically.
- **Reviewed Gate 2 remediation mirror (`CONDITIONAL PASS`):** `2d15ca167f9ee48fa24f777206aabb0450266bc8` (only `G2-F05a` & `G2-F05b` residual fixes requested).
- **Final fail-before evidence (`G2-F05a`/`G2-F05b`):** [final-fix-before.stdout.txt](raw/final-fix-before.stdout.txt) ran [final-fix-before.patch](raw/final-fix-before.patch) (SHA-256 `b6bd79699e9888a3aaf9ada36c3bb72d958fa4ba93bc9aead3169a5c04a6434f`) on `2d15ca1`, yielding **7/7 FAILED (exit 1)**.
- **Final full candidate patch:** [candidate.patch](raw/candidate.patch) (SHA-256 `97ffb4758af2c0721b5a35bb19b30da0b4c18f0aebc4c03f24554f79748fc528`).
- **Final delta patch (`2d15ca1` → final fix):** [remediation-to-final-fix.patch](raw/remediation-to-final-fix.patch) (SHA-256 `c970bfb00a96cd8d56d11d9c2420b28f0ef49392b1797ded6c44923c37d834ef`), touching ONLY `src/services/copilot/{why,evidence}.py`, `tests/test_services/test_why_g2_final_fix.py`, and `run_why_eval.py` ([diff scope](raw/final-fix-diff-scope.stdout.txt)) — zero changes to Unified Core, simulator, trace producer, repository, or frozen paths (golden 38/38 & frozen benchmark 100/100 inherited from `2d15ca1`).
- **Independent WHY evaluation (31 cases, 9 separated metrics, 8/8 oracle mutations, zero LLM judge):** [why-eval-summary.json](raw/why-eval/why-eval-summary.json).
- **Clean isolated execution:** [final-fix-exit-codes.tsv](raw/final-fix-exit-codes.tsv) · [initial remediation exit-codes.tsv](raw/exit-codes.tsv). PostgreSQL runtime remains PENDING (G6/G7 backlog).

## Reproducing from P-019 root

```bash
scratch=$(mktemp -d /tmp/chargepilot-g2-remediation-repro.XXXXXX)
G2R_EVIDENCE_OUT="$scratch/evidence" \
  bash eval/evidence/2026-11-24-ai4-4-1-remediation/run_gate.sh "$scratch"
```

[Exit codes](raw/exit-codes.tsv) · [Checksums](CHECKSUMS.sha256) · [Phase 4.1 Report](../../../docs/ai4/PHASE_4_1_REPORT.md)
