# AI-4.3 — Checkpoint phục hồi Gate 5

**READY_FOR_REVIEW · HANDOFF_READY.** Codex (implementation, tự kiểm) · 2026-11-26.

## Baseline và phạm vi

- Local P-019 là nguồn thực thi. `feature/ai-4-how-to`, `develop` và `origin/develop` bắt đầu tại `0f877f196db7b89759af08aab825f0fff82f7c3c`. Git sạch trước khi nhận khoá. Checkpoint governance Phase 1 cũ là chênh lệch RECOVERABLE.
- Mirror `20bb246477a9ffa9b8a7b222bd430ba4a7d92b25` trùng blob/path của source, config, tests, script refactor, frontend và research PDF. So với mirror `8493dd058cf4713a4b58fe9aee68ea72930c6e0f`, diff xác nhận các deterministic engines và integration module AI-4 giữ nguyên. Shared runtime, Guard, charging, repository, API, chat và frontend có thay đổi.
- Scope đang được giao gồm merged baseline readiness và G5. G6B chỉ design handoff. [Master Plan](AI-4_MASTER_IMPLEMENTATION_PLAN.md)

## Trạng thái checkpoint

| Checkpoint | Trạng thái và nơi khôi phục |
|---|---|
| A | Baseline full backend 808 pass / 8 forecast skips, standalone 180, frontend 59, Golden 38/38, frozen benchmark 100/100. Focused native 399 pass. |
| B | `RecommendationGoal`, `CandidateSet`, `RecommendationResult` và feasibility/evidence trong `src/models/recommendation.py`. |
| C | `run_recommendation(snapshot, actor, goal, ...)` là entry point service. Dùng chung `run_sandbox_branch`, patch preparation, replay, ledger và solver. |
| D | 24 oracle và lifecycle/safety tests pass. Ba mục tiêu có positive/negative actual simulator. |
| E | 11/11 cổng exit 0. Backend 832 pass / 8 forecast skips, standalone 180, focused regression 180. |

## Khôi phục và tái hiện

1. Đối chiếu `git status --short`, `git diff --stat`, nhánh, HEAD. Giữ thay đổi đồng đội và thư mục R&D bị Git bỏ qua.
2. Kiểm mã băm patch từ thư mục evidence với `sha256sum -c SHA256SUMS`. Trên bản xuất sạch đúng base, dùng `git apply --check <candidate.patch>` rồi áp patch vào bản tạm. Patch bao gồm mã và tests G5.
3. Chạy `bash eval/evidence/2026-11-26-ai4-g5/verify.sh <baseline-export> <candidate-export> <raw-dir> <venv-bin>`. Khi chạy pytest qua sandbox có thể gặp future của solver đã hoàn tất mà event loop chưa được đánh thức. Lượt xác minh native dùng môi trường tối thiểu, SQLite tạm, fixture LLM và không gọi provider thật.
4. Đối chiếu `raw/verified/candidate-executed-files.sha256` với tree chạy test. Đọc `raw/verified/g5-results.xml` để thấy candidate, mốc đạt target, release, số nhánh, latency theo test. `raw/baseline-frozen-manifest.json` giữ tham số và fingerprint của run develop.
5. Chỉ Tech Lead quyết định G5 sau review. Real LLM smoke và PostgreSQL runtime PENDING. Commit, merge và push cần chỉ thị riêng.

[Raw evidence](../../eval/evidence/2026-11-26-ai4-g5/raw) · [Gate runner](../../eval/evidence/2026-11-26-ai4-g5/verify.sh)

[Report](PHASE_4_3_REPORT.md) · [Candidate patch](../../eval/evidence/2026-11-26-ai4-g5/candidate.patch) · [SHA-256](../../eval/evidence/2026-11-26-ai4-g5/SHA256SUMS)

**STOP — WAITING_FOR_TECH_LEAD_REVIEW (GATE 5)**
