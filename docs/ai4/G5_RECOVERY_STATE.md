# AI-4.3 — Checkpoint phục hồi Gate 5

Tech Lead quyết định **G5 APPROVED** tại mirror `42438430ee49f404e90080c49a76e4c6446530da`. Candidate SHA-256 `7dd32a1903aa67b9548ad30da21739a6b9a9b220d3ca681853d267027b4fc534`, bundle SHA-256 `ea90e5ca90452ac105683b6630de6f579bfddb33f8ec4f4a10839f55db1f1dc9`. Tech Lead xác nhận 6/6 blob, 6/6 source hash, 26/26 checksum nội dung, oracle M3a/M3b, hai trường hợp có cải thiện và không cải thiện, G5-F01–F04 đã xử lý, 30 G5, 137 hồi quy G2/G3/G4/G6A, 43 architecture, 838 backend + 8 forecast skips, 180 standalone và 10/10 cổng exit 0. G5 đóng, chỉ xử lý blocker tích hợp đã xác nhận nếu có.

## Candidate sau targeted remediation

- Review `9ecb1af` yêu cầu G5-F01–F04. Patch đã review `f6ae745b…` giữ nguyên cùng raw evidence lịch sử.
- Candidate cuối dựa trên local merged develop `0f877f1`. Patch đầy đủ có SHA-256
  `7dd32a1903aa67b9548ad30da21739a6b9a9b220d3ca681853d267027b4fc534`.
- Tái hiện từ bản xuất sạch local develop. Kiểm `sha256sum -c SHA256SUMS` trong thư mục artifact, rồi
  `git apply --check <candidate.patch>` và áp patch vào bản xuất tạm. Patch đầy đủ đã gồm năm file candidate ban đầu.
- Chạy `bash <remediation/verify.sh> <candidate-export> <raw-dir> <venv-bin>`. Kiểm `executed-files.sha256`
  từ cây candidate. Đọc `verification-exits.tsv`, `g5-results.xml` và `numerical-oracles.json` trong bundle.
- Để tái tạo candidate trước remediation trong cây tạm, kiểm `git apply --reverse --check` với patch cuối, rồi
  reverse và áp patch lịch sử `f6ae745b…`. Chỉ thay đổi working tree chung khi có chỉ thị phù hợp.
- 10/10 cổng exit 0, gồm 30 G5, 137 hồi quy, 43 architecture, 838 backend + 8 skip, standalone 180. Tech Lead review cuối. PostgreSQL và real LLM smoke tiếp tục PENDING.

[Verification bundle](../../eval/evidence/2026-11-26-ai4-g5/remediation/verification-bundle.zip) ·
[Patch cuối](../../eval/evidence/2026-11-26-ai4-g5/remediation/candidate.patch) ·
[Checksum patch](../../eval/evidence/2026-11-26-ai4-g5/remediation/SHA256SUMS)

## Checkpoint trước remediation

Phần dưới lưu đường dẫn và số liệu của candidate ban đầu.

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

**G5 — CLOSED.** Gate tiếp theo đã được giao là G6B.
