# AI-4.4B — Tích hợp công cụ vào Chat Agent (Gate 6B)

**G6B — READY_FOR_FINAL_ACCEPTANCE · HANDOFF_READY.**
Báo cáo hoàn thiện sau lượt review độc lập của Tech Lead (`CONDITIONAL PASS — TARGETED REMEDIATION REQUIRED` tại mirror `2c72e2b901815ef3a63513d576db9182b785c6f8`). Chưa tự đánh dấu `APPROVED`, chưa chuyển sang G7.

## 1. Baseline, Provenance và Bảo toàn phần việc của Codex

- **Local baseline**: nhánh `feature/ai-4-how-to` tại `64c85f1624ee2893eff776a1e82fbdd893d3fe4d`, cha trực tiếp là `develop` / `origin/develop` `0f877f196db7b89759af08aab825f0fff82f7c3c`. Sáu tệp mã nguồn và kiểm thử G5 khớp 6/6 mã băm SHA-256 đã được Tech Lead nghiệm thu tại `42438430ee49f404e90080c49a76e4c6446530da` (patch `7dd32a1903aa67b9548ad30da21739a6b9a9b220d3ca681853d267027b4fc534`, bundle `ea90e5ca90452ac105683b6630de6f579bfddb33f8ec4f4a10839f55db1f1dc9`).
- **Lưu trữ nguyên trạng công việc của Codex**: trước khi chỉnh sửa bất kỳ tệp nào, toàn bộ 48 tệp delta của Codex được xuất thành `codex-interrupted-candidate.patch` (`85ba2959dbbc0a4ccc6e23be0ad5a6277885e80b44a1109c9199e34c8e064ee6`) và toàn bộ log thực thi tại `/tmp/p019-g6b-evidence` được bảo tồn nguyên vẹn trong `eval/evidence/2026-11-26-ai4-g6b/raw/codex-interrupted/` (cũng như đính kèm bản trích yếu trong `verification-bundle.zip`).
- **Không chạm Unified Core và các engine đã nghiệm thu**: kiểm tra `git diff HEAD` xác nhận **0 byte thay đổi** trên `src/simulator/**`, `src/optimizer/**`, `src/guard/**`, `src/services/{runtime,control_loop,solver}.py`, `src/services/copilot/{why,evidence,trace_reader,snapshot,outcome_ledger,counterfactual,what_if,recommendation}.py`, `config/**` và `migrations/**`.
- **Phối hợp nhánh Frontend**: `origin/develop` (`0f877f1`) đã bao gồm các PR #17 (`unified-fullstack`), #22 (`voice-input`), #23 (`voice-security-review`) và #24 (`unified-core`). Nhánh `origin/feature/be-fe-integration` (`b92e61a`, 23/11) là nhánh cũ trước khi port sang `unified-core`; không có thay đổi chưa gộp của đồng đội FE bị ghi đè. Không thay đổi thiết kế giao diện, CSS hay cấu hình gói.

[Nghiệm thu G5](PHASE_4_3_REPORT.md) · [Phục hồi & Checkpoint G6B](G6B_RECOVERY_STATE.md) · [Hợp đồng công cụ](G6B_TOOL_CONTRACTS.md) · [Demo](G6B_DEMO.md)

## 2. Xử lý các Finding F01–F05 (Tái hiện Fail-Before → Khắc phục Pass-After)

Mọi finding đều được tái hiện trực tiếp trên cây ứng viên chưa sửa của Codex (`85ba2959...`) trước khi viết bản vá; log fail-before được đóng gói trong `verification-bundle.zip` (`diagnostics/`).

| Finding | Bằng chứng Fail-Before (trên `85ba2959...`) | Bản sửa khu trú & Bằng chứng Pass-After |
|---|---|---|
| **G6B-F01** (HIGH / Blocker) — Ràng buộc tham số đầu vào với yêu cầu người dùng | `diagnostics/f01-f04-fail-before.log`: 2 ca E2E HTTP (`deadline +100p` thay vì `+35p`; site goal `50–80 kW, SLA 50%, protect_ac=false` thay vì `22–106 kW, 95%, giữ xe AC`) chạy tới `succeeded` trên engine thật; 3 ca direct `conflicts_with_simulation` (`horizon=120` vs `30p`, `DC-01-2` vs `DC-01-1`, `target=90%` vs `còn 75%`) đều trả `None`. | Mở rộng `src/agents/copilot_intent.py` (`conflicts_with_simulation`, `why_conflicts_with_message`, `resolve_selection_utc`) và `src/services/copilot/integration.py`: đối chiếu đầy đủ target SOC (tách rõ SOC hiện tại/gốc với mức mới), deadline (relative/local/ISO theo đồng hồ và múi giờ trạm), connector/booking ID, thời lượng và mốc bắt đầu outage, horizon, site kW, khoảng thử HOW-TO (`bounds`), ngưỡng SLA %, cờ bảo vệ xe AC và cờ hy sinh/hạ tầng giả định. Hỗ trợ nối ngữ cảnh nhiều lượt **chỉ từ tin nhắn `role="user"`** trong cùng phiên xác thực (`act_node.py`), bỏ qua hoàn toàn đầu ra của assistant. Spy `capture_atomic_snapshot` xác nhận 0 lần chụp trạng thái ở mọi ca sai/mơ hồ (`test_f01_*` PASS). |
| **G6B-F02** (HIGH / Blocker) — Cô lập phiên cho voice input | `diagnostics/f02-voice-race-fail-before.log`: Vitest tái hiện Resident A dừng ghi âm khi `FileReader` đang chờ, logout rồi đăng nhập Resident B; khi `FileReader` hoàn tất, `/api/v1/chat/transcribe` bị gọi với audio của A nhưng gắn `Authorization: Bearer token-resident-B`. | Gia cố `frontend/src/components/resident/ChatPanel.tsx` (không đổi UI) và `useStream.ts`: chụp `capturedSession` + `capturedGeneration` + `voiceEpoch` ngay khi bắt đầu ghi âm; kiểm tra `isVoiceCurrent()` trước và sau mọi `await` (`getUserMedia`, `blobToBase64`, `fetch`); truyền `AbortSignal` để hủy transcribe đang bay khi đổi phiên; dừng ngay `MediaStream` tracks (kể cả khi `getUserMedia` trả về trễ) và gỡ `ondataavailable`/`onstop` trước khi `recorder.stop()` lúc unmount/logout để không phát sinh transcribe mới; lỗi `401` chỉ gọi `clearSessionIfCurrent(capturedGeneration)`. Kiểm chứng qua 5 bài test mới trong `voice-session-isolation.test.tsx` (`66/66` Vitest PASS). |
| **G6B-F03** (MEDIUM / Verification Blocker) — Selector Chromium `--ranked` | `diagnostics/f03-ranked-fail-before.log` (và `codex-browser-ranked.log` lịch sử): Playwright strict mode báo `exit=1` do `94 kW đầu vào lưới · Khả thi` khớp đồng thời thẻ xếp hạng `<strong>` trong `<ol>` và dòng ứng viên `<li>` trong `<details>`. | Giữ nguyên giao diện `ChatAdvisory.tsx` (bảo toàn cả danh sách xếp hạng lẫn danh sách ứng viên/bằng chứng); cập nhật `eval/evidence/2026-11-26-ai4-g6b/browser_smoke.mjs` định vị tường minh `ol > li > strong` cho phương án xếp hạng và kiểm tra bổ sung `details ul > li` vẫn hiện diện. Chạy lại cả hai chế độ `two-roles` và `--ranked` đều đạt `exit 0`. |
| **G6B-F04** (HIGH / Workload Controls) — Kiểm soát tải tầng tích hợp | `diagnostics/f01-f04-fail-before.log`: lượt chat mô phỏng thứ 2 trong vòng 15s vẫn gọi `capture_atomic_snapshot` (`captures=2`) trước khi bị từ chối ở hàng đợi; gọi G6A `/api/v1/copilot/what-if` (`session=None`) lách hoàn toàn cooldown 15s (`202 Accepted`). Ngoài ra `/chat` chưa áp trần theo user và toàn tiến trình. | Trong `jobs.py` & `integration.py`: bổ sung `check_admission()` chạy **trước** `capture_atomic_snapshot`, bật `max_active_per_actor=1` cho instance ứng dụng và áp dụng kiểm tra active job + cooldown 15s xuyên suốt giữa Chat và G6A fallback (vẫn cho phép các lần thử tuần tự hợp lệ ở G6A khi không vướng cooldown chat). Trong `src/api/routes.py`: áp dụng thống nhất trần theo người dùng (`MAX_CONCURRENT_STREAMS_PER_USER=3`) và trần toàn cục (`MAX_GLOBAL_CONCURRENT_TURNS=8`) cho cả `/chat`, `/chat/stream` và `/chat/sessions/{id}`, fail-fast `429` và giải phóng permit an toàn trong `finally` kể cả khi `TimeoutError`/ngắt kết nối (`test_f04_*` PASS). |
| **G6B-F05** (Gate Blocker) — Bằng chứng cuối, khoảng trắng và gói bàn giao | `prompts/booking_reason.md:12` thừa dòng trống cuối file; thiếu `candidate.patch`, `SHA256SUMS` và `verification-bundle.zip` hoàn chỉnh. | Xóa dòng trống cuối `prompts/booking_reason.md` (`git diff --check` sạch tuyệt đối), bổ sung `/eval/evidence/2026-11-26-ai4-g6b/raw/` vào `.gitignore` để không đẩy hàng nghìn file log thô lên PR, kiểm tra loại trừ chuỗi JWT khỏi log, dựng `candidate.patch` từ `64c85f1`, xác minh `apply`/`reverse` trên cây sạch và đóng gói `verification-bundle.zip` kèm đầy đủ mã băm. |

## 3. Tách biệt Bằng chứng Lịch sử (Codex) và Bằng chứng Cuối cùng (Carbon)

| Cổng kiểm tra | Kết quả lịch sử của Codex (`85ba2959...` / mirror `2c72e2b`) | Kết quả xác minh cuối cùng của Carbon (trên cây xuất sạch từ `64c85f1` + `candidate.patch`) |
|---|---|---|
| Focused G6B (`test_unified_copilot.py`) | `11 passed` | **`17 passed` (`exit 0`, lưu JUnit `focused.xml`)** |
| Hồi quy G2–G5 + G6A | `167 passed` | **`167 passed` (`exit 0`)** |
| Legacy booking Agent & HITL | `97 passed` | **`97 passed` (`exit 0`)** |
| Architecture (`test_architecture.py`) | `43 passed` | **`43 passed` (`exit 0`)** |
| Full Backend (`pytest -q -rs tests`) | `849 passed, 8 skipped` | **`855 passed, 8 forecast skips` (`exit 0`, 98.77s, bỏ biến môi trường proxy)** |
| Simulator độc lập (`src/simulator/tests`) | `180 passed` | **`180 passed` (`exit 0`)** |
| Unified Core / G2–G5 engine diff | `0 diff` | **`0 byte diff` so với `64c85f1` (kế thừa Golden 38/38, Frozen 100/100, 253 AST)** |
| Ruff lint & format | `PASS` | **`PASS / PASS` (`exit 0`)** |
| Docs (`scripts/check_docs.py`) | `PASS` local (mirror thiếu `.env.example`) | **`PASS` (`exit 0`, 50 tệp md, 131 liên kết nội bộ; `.env.example` có sẵn ở local)** |
| OpenAPI (`export_openapi.py --check`) | `PASS` | **`PASS` (`exit 0`)** |
| Offline F1 (`run_agent_eval.py --offline`) | `55/55` hợp lệ | **`55/55` câu/ngưỡng hợp lệ (`exit 0`)** |
| Frontend Vitest | `61 passed` (17 tệp) | **`66 passed` (18 tệp, `exit 0`, gồm 5 ca cô lập voice/WS/HOW-TO UI mới)** |
| Frontend ESLint / TypeScript / `gen:api` parity | `PASS` | **`PASS / PASS / PASS` (`exit 0`, `schema.d.ts` khớp byte)** |
| Frontend Production Build (Webpack) | `PASS` (17/17 trang) | **`PASS` (`exit 0`, 17/17 trang trên cây xuất sạch)** |
| Frontend Production Build (Turbopack) | Lỗi bind cổng ở sandbox cũ | **`PASS` (`exit 0` với `npm run build` trực tiếp trên `P-019/frontend` dùng `node_modules` thật)** |
| Chromium smoke — hai vai trò (`two-roles`) | `PASS` | **`PASS` (`exit 0`, Chromium `159.0.8154.6`, Resident WHY/WHAT-IF/WHY+HOW-TO + logout/second-resident + Operator WHY+HOW-TO/WHAT-IF, `0` nút Áp dụng)** |
| Chromium smoke — xếp hạng M3b (`--ranked`) | `FAIL` (`exit=1`, strict-mode locator) | **`PASS` (`exit 0`, Chromium `159.0.8154.6`, `options[0].value=94`, `search_status="partial"`, `applied=false`, khớp cả `<ol>` lẫn `<details>`)** |
| Real LLM provider smoke | `PENDING_NO_AUTHORIZED_KEY` | **`PENDING_NO_AUTHORIZED_KEY`** (`openai` / `gpt-4o-mini` / `gpt-4o`, chưa cấu hình API key, `127.0.0.1:11434` đóng) |
| PostgreSQL live runtime | `PENDING` | **`PENDING`** (kiểm thử dùng SQLite tạm qua Alembic migrations `0001 -> 0004`) |

## 4. Giới hạn Phạm vi & Các Mục Dành Riêng cho G7 / Production Readiness

- **Không suy diễn độ chính xác ngữ nghĩa LLM tổng quát**: các bài kiểm thử E2E hiện dùng provider kịch bản/mock để kiểm chứng biên giới phân quyền, ràng buộc tham số phía server, grounding, hàng đợi và giao diện trên engine thật. Bộ đánh giá held-out tiếng Việt ≥60 câu với LLM thật thuộc **Gate 7 (AI-4.5)**.
- **Kiểm thử tải lớn & quản trị bộ nhớ dài hạn (thuộc G7, chưa triển khai ở G6B)**: kiểm thử 1.000 người dùng đồng thời end-to-end, phân phối p95 latency/replan dưới tải cao, đo CPU/RAM, định mức rate/cost của nhà cung cấp LLM thật và cơ chế tỉa/TTL hoặc chuyển đổi `MemorySaver` sang persistent checkpointer thuộc phạm vi G7/production readiness.
- **Đồng bộ tài liệu nghiệp vụ**: đề xuất cập nhật câu chữ PRD §5/§6/§8 và ADR-015 cho HOW-TO hữu hạn hai vai trò vẫn giữ nguyên trạng chờ nhóm và Human Supervisor phê duyệt.

## 5. Hồ sơ Bàn giao & Hướng dẫn Kiểm chứng / Rollback

- Bản vá cuối cùng (lấy `64c85f1` làm base): [candidate.patch](../../eval/evidence/2026-11-26-ai4-g6b/candidate.patch)
- Mã băm SHA-256 của bản vá: [SHA256SUMS](../../eval/evidence/2026-11-26-ai4-g6b/SHA256SUMS)
- Gói bằng chứng nén (chứa `candidate.patch`, `codex-interrupted-candidate.patch`, `CONTENTS.sha256`, `executed-files.sha256`, `diagnostics/` fail-before, `raw/` backend/frontend/browser logs đã kiểm tra không chứa JWT, JUnit `focused.xml` và `collaboration_chat.md`): [verification-bundle.zip](../../eval/evidence/2026-11-26-ai4-g6b/verification-bundle.zip) · [BUNDLE.sha256](../../eval/evidence/2026-11-26-ai4-g6b/BUNDLE.sha256)
- Runner tự động trên cây xuất sạch: [verify.sh](../../eval/evidence/2026-11-26-ai4-g6b/verify.sh) · [browser_smoke.mjs](../../eval/evidence/2026-11-26-ai4-g6b/browser_smoke.mjs) · [run_demo.py](../../eval/evidence/2026-11-26-ai4-g6b/run_demo.py)
- Rollback khi cần trên bản sao thử nghiệm: `git apply --reverse --check eval/evidence/2026-11-26-ai4-g6b/candidate.patch`.

**READY_FOR_FINAL_ACCEPTANCE**

**STOP — WAITING_FOR_TECH_LEAD_FINAL_ACCEPTANCE (GATE 6B)**
