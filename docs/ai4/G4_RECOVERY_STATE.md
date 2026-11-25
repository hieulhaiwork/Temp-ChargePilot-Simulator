# Gate 4 recovery

- **Baseline verified.** Local HEAD `4658b1f068350c130ed5ed1a744c19a7b8cd522c` plus accepted Gate 3 patch `59a92d326cfaae6cd8bb3d2b94b4124765b3efdcb3551b2c48d36e60ca73dc5d` matches each working product/test path. Accepted mirror `d0fcf5d11cfd75b677eeaed00e5b5264ab828744` is the Tech Lead review identifier. G3 approvals recorded in the four handoff docs.
- **Checkpoint A.** Existing `.simulator` reused. Gate verification will use clean temporary trees and an empty inherited environment. PostgreSQL remains PENDING.
- **In progress.** Implement typed operations, fork-only edits and same-window comparison, then bounded in-process jobs and focused oracles.
- **Pending.** Candidate SHA and full regression.

## Checkpoints B and C

- **Completed.** Added strict WHAT-IF contracts, authorized sandbox-only revisions, shared announced-source replay, site and connector interventions, original/revised SLA, observed-window gating and bounded owner-scoped jobs.
- **Focused.** 105 pass across WHAT-IF oracles, G3 foundation and architecture. Initial oracle expectations incorrectly assumed full AC power for a small target and assigned all reduced source power to AC under B0. The corrected oracle takes account of the 15-minute acceptance interval, quantization and the configured 22% fixed share.
- **Initial candidate.** SHA-256 `7bcdbda22a1c27a68dbe46863d05254a0a270124c0553e9c7db68dcf03ad90e7` is the G4 delta over the approved G3 patch. Both patches apply in order from the documented local HEAD.
- **Commands.** `bash eval/evidence/2026-11-25-ai4-4-2b/run_gate.sh /tmp/chargepilot-g4-gate-01 eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-01`.
- **In progress.** Full mandatory gate and P0 Golden CRLF/frozen parity in clean clones. [Logs and candidate](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-01/)
- **Next.** Validate the full gate and finalize phase handoff.

## Checkpoint C update

- **Gate 01 completed.** Overall 0, backend 750 pass và 8 forecast skips, Golden CRLF 38/38, Frozen 100/100.
- **Confirmed edge case.** A site cap matching current supply incorrectly became a no-op before an announced supply increase. Stored the failed oracle. The fix keeps the cap over the increase. Added native job cancellation and resolved hard violation probes. G4 focused final probes 32 passed.
- **Gate 02 candidate.** SHA-256 `ec99050de22414c7f3b964c6ae898458db15a169119bc05ae5ba5abaa92491bf`. Full gate launched from the same accepted G3 baseline. [Candidate and logs](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/)

## Checkpoint D

- **Last verified candidate SHA-256.** `ec99050de22414c7f3b964c6ae898458db15a169119bc05ae5ba5abaa92491bf`.
- **Completed.** Gate 02 overall exit 0. 169 focused, 32 G4 tests, 753 full backend với 8 forecast skips, 180 standalone. G3 evaluation 8/8 và mutations 6/6. AST 114/114, golden 38/38, frozen 100/100. Verified reverse patch check trong clone candidate.
- **Pending.** PostgreSQL runtime và Tech Lead review.
- **Next.** Tech Lead review Gate 4. [Phase Report](PHASE_4_2B_REPORT.md) · [Exit ledger](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/exit-codes.tsv)

## Final remediation checkpoint 1

- **CONDITIONAL PASS — FINAL REMEDIATION REQUIRED.** Tech Lead reviewed mirror `343cddce2e7c22e8753945589a94d2ad7ed48042` and Gate 02 patch `ec99050de22414c7f3b964c6ae898458db15a169119bc05ae5ba5abaa92491bf`. Only G4-F01–F03 are open for this round.
- Local `feature/ai-4` at `4658b1f068350c130ed5ed1a744c19a7b8cd522c`; both reviewed patches verified and applied in a scratch clone. All 245 tracked or unignored product/test files match the reconstructed candidate byte-for-byte. The two mirror IDs are review provenance supplied by Tech Lead. PostgreSQL runtime remains PENDING. [Workspace evidence](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/workspace-provenance.txt)

## Final remediation checkpoint 2 — G4-F01

- Reproduced explicit T+7:30 releasing the only available AC connector at T+8. The revised slot changed battery delivery for both bookings and moved the second booking's plug-in from T+15 to T+8. Validation now rejects explicit off-grid deadlines relative to snapshot T. Offset normalization, a fractional-minute grid, target-only revisions and typed job submission are covered. [Before](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/final-fail-before.stdout.txt) · [Oracle](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/oracle-calculations.md)

## Final remediation checkpoint 3 — G4-F02

- Reproduced the misleading −15-minute wait delta and the equal-count booking swap. Branch aggregates stay visible. Delta uses exact sample membership and supplies a typed reason for null metrics. The projection keeps wait observed/censored/unknown counts, SLA met counts, unserved counts and additive measurements. Booking membership stays internal. [Before](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/final-fail-before.stdout.txt) · [Oracle](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/oracle-calculations.md)

## Final remediation checkpoint 4 — G4-F03 and candidate

- Mixed-load site increase, hardware caps and future/cabinet series are numerically verified. Confirmed an additional replay bug at T when the runtime override masked a lower announced source limit. The sandbox now keeps both constraints at T and transitions to the next announced regime at its effective minute. The full gate includes standalone and frozen parity because this touched `HybridStation` and the kernel. [Oracle calculations](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/oracle-calculations.md)
- Focused pass-after completed with 47 passed. The final candidate includes the event delivery assertions and runs a fresh mandatory gate. Candidate SHA-256 `e8ae5cedbbe5af0a0a05d63f3dbb4ea6ac22fda40a4628a2cf7abca82be10d0f` over G3. The five-file remediation delta over Gate 02 is `1cdb630cc10a4bfd1fb96d1ac2264dbd4a9515f3dbfe7153780f0c6fd33160bf`. Rebuilt product/test files match local bytes and both reverse patch checks pass in scratch. [Candidate provenance](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/candidate-provenance.txt) · [Gate ledger](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/exit-codes.tsv)

## Final remediation checkpoint 5 — Mandatory verification complete

- **G4 — READY_FOR_FINAL_ACCEPTANCE.** Gate overall exit 0. G4 47, combined focused 184, G3 foundation 37, architecture 43 and full backend 768 passed with 8 forecast skips. Ruff, docs and OpenAPI pass. G3 evaluator 8/8 and mutation checks 6/6, AST 114/114, standalone 180, Golden CRLF 38/38 and frozen benchmark 100/100 with non-timing KPI, fingerprint and safety counter parity. [Phase Report](PHASE_4_2B_REPORT.md) · [Gate ledger](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/exit-codes.tsv)
- **Resume from.** The final Git source of truth is the local working tree at the stated HEAD, with the final G4 diff stored over the accepted G3 patch. Fail-before used the final test file against Gate 02 source. Wait for Tech Lead final acceptance and separate G6A authorization.

## Roadmap handoff

G6A follows G4 final acceptance and a separate Tech Lead authorization. It covers the shared integration foundation and WHY/WHAT-IF end-to-end. G5, G6B and G7 follow in that order, with full HOW-TO scope and acceptance criteria. PostgreSQL runtime remains PENDING. [Master Plan](AI-4_MASTER_IMPLEMENTATION_PLAN.md)

**STOP — WAITING_FOR_TECH_LEAD_FINAL_ACCEPTANCE (GATE 4)**
