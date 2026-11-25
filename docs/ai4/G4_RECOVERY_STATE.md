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
