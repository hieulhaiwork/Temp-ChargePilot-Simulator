# G6A Recovery & Final Verification State

## 1. Baseline và điểm tiếp quản từ Codex

- **Baseline được duyệt:** G4 `APPROVED` tại mirror `eb5967ae720b46b089b09e03063aa2c727ca5fd8` (local branch `feature/ai-4`, `HEAD` `4658b1f068350c130ed5ed1a744c19a7b8cd522c`, G3 patch `59a92d326cfaae6cd8bb3d2b94b4124765b3efdcb3551b2c48d36e60ca73dc5d` + G4 final patch `e8ae5cedbbe5af0a0a05d63f3dbb4ea6ac22fda40a4628a2cf7abca82be10d0f` → baseline tree `5f7e86292514ed9c19d9a7f43e3d436b0b5a9bb0`).
- **Điểm dừng của Codex (`1a07b5ea0fbd4b9dc8a4a1a76a989f8356f2268c`):**
  - Đã hoàn thành phần lớn AI-4.4A (contracts, `copilot_intent.py`, `copilot_grounding.py`, `integration.py`, `/api/v1/copilot`, OpenAPI/types, `CopilotPanel.tsx`, tests và demo).
  - Đã tạo patch lịch sử `eb773daf282482e67adce09689ff5f6559db1ea4f82143bec31f39daf5014048` (14/19 tệp khớp), sau đó sửa thêm 5 tệp (`copilot_intent.py`, `test_copilot.py`, `CopilotPanel.tsx`, `copilot.test.tsx`, `verify.sh`) và thêm `browser_smoke.mjs` trước khi hết quota.
  - Không còn tiến trình nền nào của Codex đang chạy khi Carbon tiếp quản.

## 2. Các bước hoàn thiện của Carbon

1. **Bảo tồn bằng chứng lịch sử:** Sao lưu nguyên vẹn patch lịch sử tại [codex-interrupted-candidate.patch](../../eval/evidence/2026-11-26-ai4-4-4a/raw/codex-interrupted-candidate.patch) ([SHA-256](../../eval/evidence/2026-11-26-ai4-4-4a/raw/codex-interrupted-candidate.sha256)); giữ nguyên toàn bộ log cũ trong `eval/evidence/2026-11-26-ai4-4-4a/raw/`.
2. **Gia cố cô lập phiên & phản hồi trễ trên Copilot UI (Priority 3):**
   - Trong [CopilotPanel.tsx](../../frontend/src/components/copilot/CopilotPanel.tsx): gắn `actorKey = "${role}:${session.userId}:${sessionToken}"`, truyền `{ signal }` cho context query, dọn sạch/hủy queries `["copilot"]` khi logout hoặc unmount, và dùng `mountedRef` + `submitEpochRef` chặn phản hồi `submit`/`cancel` trễ từ phiên cũ cập nhật state hoặc cache của phiên mới.
   - Trong [copilot.test.tsx](../../frontend/src/test/copilot.test.tsx): thêm regression test kiểm chứng phản hồi `POST /query` và `DELETE /jobs/{id}` bị trễ qua bước logout/đổi tài khoản/đăng nhập lại không rò rỉ dữ liệu (`35/35` Vitest tests PASS).
   - Trong [browser_smoke.mjs](../../eval/evidence/2026-11-26-ai4-4-4a/browser_smoke.mjs): bổ sung kiểm tra đăng xuất và đăng nhập tài khoản cư dân thứ hai trên cùng một tab trình duyệt.
3. **Hoàn tất Provenance ứng viên cuối (Priority 1):**
   - Xuất final [candidate.patch](../../eval/evidence/2026-11-26-ai4-4-4a/candidate.patch) gồm đủ 20 đường dẫn G6A với SHA-256 **`218ef89b033a155542deccb7cfbeb9f8380c9ed97ff402cfb6ff05b81d91f706`** ([candidate-provenance.log](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/candidate-provenance.log)).
   - Đối chiếu 356/356 tệp khớp từng byte trên `/tmp/p019-g6a-clean-verify`, `git apply --reverse --check` PASS, và xác nhận 0 thay đổi trên Unified Core / G2–G4 engines.
4. **Hoàn tất cổng xác minh cuối (Priorities 2–5):**
   - Backend ([backend-exits.tsv](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/backend-exits.tsv)): **12/12 PASS** (`777 passed, 8 skipped`, `9/9` G6A API, `91` F1 legacy, `128` G2–G4 regressions, `8/8` G3 eval).
   - Frontend ([frontend-exits.tsv](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/frontend/frontend-exits.tsv)): **6/6 PASS** (`lint`, `typecheck`, `35/35` tests, Webpack build `og6lswycxJFfzwMckocBx`, OpenAPI types parity; đồng thời xác nhận `next build` Turbopack tại workspace gốc cũng đạt `exit 0`).
   - Real LLM provider ([provider-status.json](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/provider-status.json)): **`PENDING_NO_AUTHORIZED_KEY`**.
   - Final Chromium smoke ([browser-smoke.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/browser-smoke.stdout.txt)): **PASS (`exit 0`)**.

**Trạng thái hiện tại:** **G6A — READY_FOR_REVIEW** (chưa nghiệm thu). Xem báo cáo đầy đủ tại [PHASE_4_4A_REPORT.md](PHASE_4_4A_REPORT.md) và hướng dẫn demo tại [G6A_DEMO.md](G6A_DEMO.md).
