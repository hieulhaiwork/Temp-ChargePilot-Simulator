# Evidence AI-4.1 Remediation — Deterministic WHY Engine (Gate 2 Re-Review)

Reviewed mirror `6ba13b8021998e03e15b0ec26cec93d484b70a05` returned `CHANGES REQUIRED` (G2-F01–G2-F09).

- **Local base:** `490f43300afb05ef7e809099a77e0c7174e272fb` (Tech Lead–approved G1 mirror `fed2c5e395c3a6ac3e1798ce52d0e4b4e4abd009`).
- **Fail-before evidence:** [remediation-before.stdout.txt](raw/remediation-before.stdout.txt) ran [regression-before.patch](raw/regression-before.patch) (SHA-256 `3162fc0f198c0c40ec9bc8a3f941b142b9d902bcc5755c45b3ba5b23cc671479`) against the reviewed G2 candidate (`fe89fc04...`), yielding **14/14 FAILED (exit 1)** and confirming G2-F01–G2-F07 empirically.
- **Full remediation candidate patch:** [candidate.patch](raw/candidate.patch) (SHA-256 `fb424d5c87028cc01952757062067c3c302eaa5cef2c0b1332a758e941437832`).
- **Delta patch (reviewed G2 → remediation):** [reviewed-to-remediation.patch](raw/reviewed-to-remediation.patch) (SHA-256 `e3abc16b445eb5982e95e994f33ec867f4f1cea1ff93ba8449fc1b24a3889083`).
- **Independent WHY evaluation (zero LLM judge, 9 separated metrics, 7/7 oracle mutations):** [why-eval-summary.json](raw/why-eval/why-eval-summary.json).
- **Clean isolated execution:** All gates ran in a detached `git clone` isolated from workspace `.env` and gitignored `src/simulator/claude_rd/`. PostgreSQL probe exited `127` (PENDING).

## Reproducing from P-019 root

```bash
scratch=$(mktemp -d /tmp/chargepilot-g2-remediation-repro.XXXXXX)
G2R_EVIDENCE_OUT="$scratch/evidence" \
  bash eval/evidence/2026-11-24-ai4-4-1-remediation/run_gate.sh "$scratch"
```

[Exit codes](raw/exit-codes.tsv) · [Checksums](CHECKSUMS.sha256) · [Phase 4.1 Report](../../../docs/ai4/PHASE_4_1_REPORT.md)
