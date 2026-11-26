# G6B — Trạng thái phục hồi và khắc phục sau review

**READY_FOR_FINAL_ACCEPTANCE · HANDOFF_READY · Carbon (tiếp quản từ Codex) · 2026-11-26.**

- **Baseline local**: `feature/ai-4-how-to` tại `64c85f1624ee2893eff776a1e82fbdd893d3fe4d`, cha trực tiếp là `develop` / `origin/develop` `0f877f196db7b89759af08aab825f0fff82f7c3c`. Toàn bộ 6/6 mã băm SHA-256 mã nguồn/test của G5 khớp tuyệt đối với G5 đã nghiệm thu (`42438430ee49f404e90080c49a76e4c6446530da`, patch `7dd32a1903aa67b9548ad30da21739a6b9a9b220d3ca681853d267027b4fc534`).
- **Bảo toàn phần việc lịch sử**:
  - Bản vá gián đoạn của Codex (`2c72e2b`): `codex-interrupted-candidate.patch` (`85ba2959dbbc0a4ccc6e23be0ad5a6277885e80b44a1109c9199e34c8e064ee6`) cùng bản sao lưu đầy đủ `/tmp/p019-g6b-evidence`.
  - Bản vá và bundle vòng 1 của Carbon (`de82afe7`): `round1-candidate.patch` (`dab76e3216f0d9fb1453862fb7f3343fa7acf249c4c8f32e26cb420b2ddae7e2`) và `round1-verification-bundle.zip` (`9073d093a65c1583ed36543d3e4da7ab92b9eb4738d5679a5025c98fbd6a49c1`).
  - Bản vá và bundle vòng 2 của Carbon (`c519845`): `round2-candidate.patch` (`fff02f47d8d62cd4b4f3dc258b40985b7703016489989645ae986d7900fdd36f`) và `round2-verification-bundle.zip` (`eb752042d140ffddac1726155cd98297d99cb465431981622a0b0eed1b5a858a`).
  - Đối chiếu `.env.example` và `.gitignore`: `.env.example` có sẵn tại `HEAD` (`64c85f1`, blob `a96d656...`, SHA-256 `7104c9eb...`); `.gitignore` giữ quy tắc bỏ qua `/docs/ai4/collaboration_chat.md` và `/eval/evidence/2026-11-26-ai4-g6b/raw/` để tránh đưa log thô/nội bộ lên nhánh sản phẩm.
- **Đối chiếu nhánh FE của đồng đội**: `origin/develop` (`0f877f1`, ngày 25/11) đã hợp nhất đầy đủ `feature/unified-fullstack` (#17), `feature/voice-input` (#22), `fix/voice-security-review` (#23) và `feature/unified-core` (#24). Nhánh `origin/feature/be-fe-integration` (`b92e61a`, ngày 23/11) là nhánh lịch sử trước khi port sang `unified-core`; không có thay đổi chưa commit hay nhánh FE mới nào của đồng đội bị ghi đè. Giữ nguyên giao diện, bố cục, quick replies, luồng booking/HITL và cơ chế thế hệ phiên (`generation`) dùng chung (`0 byte diff` trên `frontend/**` và `prompts/**` ở V3).
- **Nhả khóa bàn giao**: Carbon đã hoàn thành toàn bộ F01–F05 (kể cả `F01-R1`..`F01-R3` và ràng buộc ngữ cảnh đa lượt V3 `F01-R1-MT`/`F01-R2-MT`), chạy đạt toàn bộ cổng bắt buộc trên cây xuất sạch, đóng gói `verification-bundle.zip` và nhả khóa chỉnh sửa G6B để chờ Tech Lead nghiệm thu độc lập. G7, commit/push/merge và đồng bộ PRD/ADR-015 chờ quyết định riêng.

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
| D · input binding & grounding (F01 + R1..R3 + V3 MT) | **Tested** | Server đối chiếu đối xứng toàn bộ ràng buộc của yêu cầu đang mở qua trạng thái làm rõ gắn theo tác vụ (`pending_copilot_clarification`, tối đa 3 lượt, TTL 300s, tự dọn dẹp khi hoàn tất/timeout/SSE disconnect/HITL và hỗ trợ `WHY + clarify` hỗn hợp): kiểm tra target, deadline (tách `sau N phút` tính từ `now` với độ lệch theo hạn gốc, chỉ giải tỏa `clarify("time")` khi có mốc hợp lệ tường minh), connector/booking ID, chủ thể nguồn lưới toàn trạm, mốc thời gian tương lai không biểu diễn được, không cho câu trả lời slot làm đổi sang thao tác mô phỏng khác, và chỉ re-anchor khi lượt trước đã đóng hoặc có yêu cầu hủy/đặt lại tường minh. |
| E · giao diện & cô lập voice (F02) | **Tested** | Giữ nguyên thiết kế UI; gắn `voiceEpoch` và `session.generation` ngay lúc bắt đầu ghi âm, kiểm tra trước/sau mọi `await`, hủy `AbortController` khi đổi phiên, đóng `MediaStream` tracks và gỡ handler recorder khi logout/unmount mà không phát sinh transcribe mới; `66/66` Vitest tests (18 tệp), ESLint, TypeScript, Webpack & Turbopack build đều `exit 0`. |
| F · kiểm chứng & đóng gói (F03, F05) | **Tested** | Sửa selector ranked HOW-TO sang `ol > li > strong` (giữ nguyên cả danh sách ứng viên `details ul > li`), sạch `git diff --check`, `11/11` cổng backend (`861 passed, 8 forecast skips` toàn bộ backend — gồm tập con `23` focused G6B; cùng `180` standalone), cả 2 kịch bản Chromium smoke (`two-roles` và `--ranked`) `exit 0`, hoàn tất `candidate.patch`, `SHA256SUMS` và `verification-bundle.zip`. |

[Báo cáo G6B](PHASE_4_4B_REPORT.md) · [Hợp đồng công cụ](G6B_TOOL_CONTRACTS.md) · [Demo](G6B_DEMO.md)
