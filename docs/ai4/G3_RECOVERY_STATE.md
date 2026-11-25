# Gate 3 recovery

Checkpoint A captured on 2026-11-25. Local branch `feature/ai-4` and HEAD `4658b1f068350c130ed5ed1a744c19a7b8cd522c` correspond to the documented G2 baseline. GitHub compare identifies reviewed G3 `49b6fec00e90c1f5c6f504abfb038969f2d6c64c` as one commit ahead of approved G2 `aa37ca55978f99009c6d4b25c0676d87eac7fa7b`. The mirror object's SHA is absent from local Git. Applied each mirror product/test diff to an archive of local HEAD and byte-compared all nine outputs with the starting workspace. The 18 initial changed paths and their diff sizes match the mirror compare. SHA-256 for the nine reviewed files is in [reviewed-product.sha256](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/reviewed-product.sha256).

- Starting tree had nine modified tracked files and nine untracked files, all within the reviewed change list. No staged changes. No prior test process was visible and the residual test scratch directory was empty.
- Recovered the original three-case fail-before log and test patch, the evaluator, and the gate shell. No pass-after log, candidate patch, regression runs, or G3 phase report was present.
- Reused `.simulator` with Python 3.12.3, EV2Gym 2.0.0, NumPy 2.4.6, SciPy 1.18.1, pytest 9.2.0, Ruff 0.17.5, SQLAlchemy 2.1.9, FastAPI 0.163.2 and Pydantic 2.14.3. A direct socketpair probe succeeded.
- Focused reviewed-candidate pytest launched from an isolated archival tree. Command `python -m pytest tests/test_services/test_g3_runtime_readiness.py tests/test_services/test_counterfactual_foundation.py -q`. Result pending at checkpoint A. Last verified candidate hash is pending.
- Pending targeted recovery for G3-F02–F08 and all mandatory regression runs. PostgreSQL verification remains pending.
- Historical ADR-014 starts from replay in a separate simulator. The approved AI-4 plan and final Unified Core ADR use a detached fork of the shared kernel. The approved AI-4 scope includes bounded HOW-TO after Gate 4 and defers AI-1.
- Next checkpoint is targeted reproduction and remediation, starting with safety interlock and snapshot integrity.

## Checkpoint B và C

- **Completed.** Giữ G3-F01 của Neon. Sửa interlock rollout/admission, snapshot integrity và cohort, timestamps và censoring, cleanup của paired runner, gate harness và backlog G4. Kiểm tra registry reload và focused G3 sau sửa đạt 39 test.
- **Evidence trước sửa.** Baseline G2 với test patch G3-F01 có ba lỗi đúng kỳ vọng, exit 1. Candidate Neon có 17 lỗi và một ca qua trong nhóm probe mới. Source/test Neon đã lưu kèm SHA-256 để replay.
- **Lỗi môi trường.** Sandbox tạo được socketpair nhưng lượt async bị treo khi worker đã rảnh. Diagnostic đã lưu. Các lượt dùng làm evidence chạy ngoài sandbox theo quyền được cấp, với môi trường tối giản và cây cách ly.
- **Lượt đầu.** Patch `85469c0fcacaff8e6ca64dcd3d029bb9935d8c87122c9b24ca3da8e426197060` qua golden, benchmark và focused, full backend có 26 lỗi vì snapshot giữ class scheduler cũ sau registry reload. Đã sửa và lưu ledger thất bại.
- **Completed.** Candidate `59a92d326cfaae6cd8bb3d2b94b4124765b3efdcb3551b2c48d36e60ca73dc5d` đã chạy Gate 3 từ clone baseline đã apply patch với overall exit 0. Mọi source/test path byte-match workspace. PostgreSQL runtime đang PENDING.
- **Commands.** `bash eval/evidence/2026-11-24-ai4-4-2a/run_gate.sh /tmp/chargepilot-g3-gate-02 eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02`. Lệnh riêng, stdout/stderr và mã thoát lưu theo gate.
- **Evidence.** [Recovery](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/) · [Gate 01](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-01/exit-codes.tsv) · [Gate 02](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/exit-codes.tsv)
- **Next.** Tech Lead review Gate 3.

## Checkpoint D

- **Last verified candidate SHA-256.** `59a92d326cfaae6cd8bb3d2b94b4124765b3efdcb3551b2c48d36e60ca73dc5d`.
- **Completed.** Focused 213 pass. Backend 721 pass và 8 forecast skips. Simulator 180 pass. Evaluator 8/8 và mutation 6/6. Golden CRLF 38/38, frozen backend 100/100, preserved AST 114/114. Probe bổ sung xác nhận live stop/readback/ACK trong lúc sandbox giữ solver worker.
- **Pending.** PostgreSQL runtime và Tech Lead review. Docker CLI không kết nối được daemon trong lượt này.
- **Evidence và handoff.** [Phase Report](PHASE_4_2A_REPORT.md) · [Exit ledger](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/exit-codes.tsv) · [Live safety probe](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/live-safety-under-load.stdout.txt)
