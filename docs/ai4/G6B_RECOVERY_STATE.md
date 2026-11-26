# G6B — Trạng thái phục hồi và khắc phục sau review

**READY_FOR_FINAL_ACCEPTANCE · HANDOFF_READY · Carbon (tiếp quản từ Codex) · 2026-11-26.**

- **Baseline local**: `feature/ai-4-how-to` tại `64c85f1624ee2893eff776a1e82fbdd893d3fe4d`, cha trực tiếp là `develop` / `origin/develop` `0f877f196db7b89759af08aab825f0fff82f7c3c`. Toàn bộ 6/6 mã băm SHA-256 mã nguồn/test của G5 khớp tuyệt đối với G5 đã nghiệm thu (`42438430ee49f404e90080c49a76e4c6446530da`, patch `7dd32a1903aa67b9548ad30da21739a6b9a9b220d3ca681853d267027b4fc534`).
- **Bảo toàn phần việc của Codex**: Tại thời điểm Carbon tiếp nhận sau quyết định `CONDITIONAL PASS — TARGETED REMEDIATION REQUIRED` (mirror `2c72e2b901815ef3a63513d576db9182b785c6f8`), toàn bộ 48 tệp delta trên cây làm việc được chụp nguyên trạng thành `codex-interrupted-candidate.patch` (`85ba2959dbbc0a4ccc6e23be0ad5a6277885e80b44a1109c9199e34c8e064ee6`) cùng bản sao lưu đầy đủ thư mục `/tmp/p019-g6b-evidence` (bao gồm cả `browser-ranked.log` ghi nhận đúng lỗi strict-mode locator khi Codex hết token). Không ghi đè hay xóa log lịch sử của Codex.
- **Đối chiếu nhánh FE của đồng đội**: `origin/develop` (`0f877f1`, ngày 25/11) đã hợp nhất đầy đủ `feature/unified-fullstack` (#17), `feature/voice-input` (#22), `fix/voice-security-review` (#23) và `feature/unified-core` (#24). Nhánh `origin/feature/be-fe-integration` (`b92e61a`, ngày 23/11) là nhánh lịch sử trước khi port sang `unified-core`; không có thay đổi chưa commit hay nhánh FE mới nào của đồng đội bị ghi đè. Giữ nguyên giao diện, bố cục, quick replies, luồng booking/HITL và cơ chế thế hệ phiên (`generation`) dùng chung.
- **Nhả khóa bàn giao**: Carbon đã hoàn thành F01–F05, chạy đạt toàn bộ cổng bắt buộc trên cây xuất sạch, đóng gói `verification-bundle.zip` và nhả khóa chỉnh sửa G6B để chờ Tech Lead nghiệm thu độc lập. G7, commit/push/merge và đồng bộ PRD/ADR-015 chờ quyết định riêng.

## Audit baseline và phạm vi kế thừa

- `graph.py`, `state.py`, `nodes/`, `tools/` và `guardrails.py` giữ vòng ReAct hữu hạn, `MemorySaver` và HITL đặt lịch. Nhánh phân tích dùng render tất định từ typed claims; `explain_schedule` chuyển sang WHY có `DecisionTrace` trong phiên xác thực.
- `src/simulator/claude_rd/` bị Git bỏ qua và giữ nguyên cho nghiên cứu R&D của thành viên khác; mọi cổng kiểm chứng kiến trúc và kiểm thử chạy trên cây xuất sạch từ `HEAD` (`64c85f1`) phủ `candidate.patch`.
- **Không chạm core đã đóng băng**: `0 byte diff` trên `src/simulator/**`, `src/optimizer/**`, `src/guard/**`, `src/services/{runtime,control_loop,solver}.py`, `src/services/copilot/{why,evidence,trace_reader,snapshot,outcome_ledger,counterfactual,what_if,recommendation}.py`, `config/**` và `migrations/**`.

## Trạng thái Checkpoints A–F sau Remediation

| Checkpoint | Trạng thái | Kết quả xác minh cuối cùng |
|---|---|---|
| A · typed tools | **Tested** | Giữ 4 adapter `copilot_why`, `copilot_what_if`, `copilot_how_to`, `copilot_job` theo vai trò; không tạo Agent hay LLM parser lồng nhau. |
| B · shared jobs & workload (F04) | **Tested** | Hàng đợi dùng chung (1 chạy, 4 chờ, 64 giữ lại, TTL 300s), kiểm tra `check_admission` **trước** `capture_atomic_snapshot`, đồng bộ hạn ngạch `max_active_per_actor=1` và cooldown 15s giữa Chat và G6A fallback, giới hạn lượt chat đồng thời toàn cục (`8`) và theo người dùng (`3`) trên cả `/chat`, `/chat/stream` và `/chat/sessions/{id}`. |
| C · vai trò và phiên | **Tested** | Danh tính/vai trò do server cấp, khóa phiên băm `user_id + role + credential + session_id`, kiểm quyền sở hữu job và cách ly giữa các phiên đăng nhập. |
| D · input binding & grounding (F01) | **Tested** | Server đối chiếu đầy đủ target, deadline (relative/local/ISO + múi giờ trạm), connector/booking ID, thời lượng/thời điểm sự cố, horizon, site kW, khoảng thử HOW-TO, ngưỡng SLA %, bảo vệ xe AC và cờ hy sinh/hạ tầng giả định; lịch sử nhiều lượt chỉ đọc tin nhắn `role="user"` trong cùng phiên, bỏ qua hoàn toàn văn bản của assistant. |
| E · giao diện & cô lập voice (F02) | **Tested** | Giữ nguyên thiết kế UI; gắn `voiceEpoch` và `session.generation` ngay lúc bắt đầu ghi âm, kiểm tra trước/sau mọi `await`, hủy `AbortController` khi đổi phiên, đóng `MediaStream` tracks và gỡ handler recorder khi logout/unmount mà không phát sinh transcribe mới; `66/66` Vitest tests (18 tệp), ESLint, TypeScript, Webpack & Turbopack build đều `exit 0`. |
| F · kiểm chứng & đóng gói (F03, F05) | **Tested** | Sửa selector ranked HOW-TO sang `ol > li > strong` (giữ nguyên cả danh sách ứng viên `details ul > li`), sạch `git diff --check`, `11/11` cổng backend (`855 passed, 8 forecast skips`, `180` standalone), cả 2 kịch bản Chromium smoke (`two-roles` và `--ranked`) `exit 0`, hoàn tất `candidate.patch`, `SHA256SUMS` và `verification-bundle.zip`. |

[Báo cáo G6B](PHASE_4_4B_REPORT.md) · [Hợp đồng công cụ](G6B_TOOL_CONTRACTS.md) · [Demo](G6B_DEMO.md)
