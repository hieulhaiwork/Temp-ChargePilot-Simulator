# Brief review độc lập — Governance Giai đoạn 1 (2026-11-24)

> Gửi: Codex (Tech Lead) hoặc một agent **không** tham gia soạn tài liệu Giai đoạn 1.
> Người soạn bản cần review: Implementation Agent (Claude). Người duyệt cuối: Human Supervisor.

## 1. Mục tiêu

Kiểm xem bộ tài liệu Giai đoạn 1 có **mô tả đúng hệ thống thật** không, để Human Supervisor dùng chúng quản lý dự án
mà không phải đọc code.

**Nguyên tắc:**
- Không mặc định kết luận của audit là đúng. Mỗi khẳng định phải đối chiếu **trực tiếp** với source code, test, git,
  evidence. Không chỉ đọc lại báo cáo của Implementation Agent.
- Chỉ đọc. Không sửa code, test, CI, schema, API; không duyệt ADR; không commit / push.
- Được chạy test và lệnh kiểm tra chỉ đọc.

## 2. Đầu vào

| Tài liệu cần review | Vai trò |
|---|---|
| `docs/FEATURE_REGISTRY.md` | Nguồn hiện trạng: ánh xạ mã, registry, truy vết, triển khai khác tài liệu, cần điều tra, cần quyết |
| `docs/architecture_diagram.md` | Hiểu hệ thống 4 tầng, sơ đồ hiện trạng, 3 luồng |
| `docs/adr/README.md` §"Phân loại quyết định" | Triage 19 ADR + 4 quyết định cần Human Supervisor |
| `ARCHITECTURE.md`, `docs/PRD.md` (đầu file), `docs/communication/HUMAN_AGENT_COMMUNICATION.md` §10 | Phần đã sửa để trỏ về registry |
| `docs/handoff/HANDOFF.md` §0–§1, `CLAUDE.md` "Tiếp nhận công việc", `AGENTS.md` | Cơ chế chuyển giao: kiểm xem có mâu thuẫn quy tắc, có khẳng định sai về trạng thái git / test không |

Đối chiếu với: `src/`, `tests/`, `src/simulator/tests/`, `frontend/`, `config/`, `migrations/`, `eval/evidence/`,
`docs/PRD.md` (toàn bộ yêu cầu), `docs/adr/ADR-*.md`, `git log`, `gh run list`.

Code tham chiếu: commit `ce23136` trên `feature/unified-core`. Các thay đổi Giai đoạn 1 chỉ chạm file `.md` (xem
`git status` / `git diff --stat`).

## 3. Khẳng định cần kiểm (cố gắng bác bỏ từng cái)

| # | Khẳng định | Nguồn trong tài liệu | Cách kiểm gợi ý |
|---|---|---|---|
| K1 | Mã F6 / F7 / F8 trong code mang nghĩa khác PRD v0.4 | registry §1.1 | `git grep -nE "\bF[678]\b" -- src tests docs/plan`; so PRD §5 |
| K2 | Bảng ánh xạ FR cũ → mới đúng (FR6–FR18, AC, MT) | registry §1.1 | So `git show 8f6f08a:ARCHITECTURE.md` + `docs/plan/*` với PRD §6 |
| K3 | 4 test được bảng truy vết cũ dẫn không tồn tại | registry §3.3 | `grep -rn "def <tên>" tests src` |
| K4 | Kết quả test: backend 604 đạt / 8 bỏ qua; simulator 180 đạt; frontend 30 đạt @ `ce23136` | registry đầu file | Tự chạy: `pytest tests -q`, `PYTHONUTF8=1 pytest src/simulator/tests -q`, `cd frontend && npx vitest run` |
| K5 | AI-1 (F7), AI-4 (F8) chưa có code; chưa có bảng `proposals` / `consents` / `vehicle_revisions` / `audit_log` | registry §2, §3.2 | `src/agents/`, `src/db/tables.py`, `migrations/versions/` |
| K6 | Kiểm dữ kiện của LLM (FR32) chỉ kiểm số kWh và mã cổng | registry §3.2 | `src/llm_chat/guardrails.py`, `src/llm_chat/nodes/` |
| K7 | FR4a (mục đích chuyến đi → ràng buộc) chưa có code | registry §3.2 | tìm xử lý quãng đường / mục đích trong `src/llm_chat/`, `src/services/` |
| K8 | F14: chưa rõ simulator có giữ xe "đầy nhưng còn cắm" | registry §5 I-2 | `src/simulator/core/kernel.py`, `queue.py`, test simulator |
| K9 | Baseline đóng băng: 0 vi phạm áp dụng / 100 run; đúng hạn TB 29–32% / policy; M3a rẻ nhất, M3b đúng hạn cao nhất | registry §3.1, ADR triage Q3 | Tự tính lại từ `eval/evidence/2026-11-24-unified-core-frozen-baseline/benchmark.json` |
| K10 | CI gần nhất trên `develop` thất bại; `feature/unified-core` chưa có lần CI nào | registry §0 | `gh run list` |
| K11 | `src/simulator/base.py`, `SimulatorGateway` không tồn tại; thay bằng `StationKernel` | registry §4 | tìm file / tên |
| K12 | Ranh giới import trong `ARCHITECTURE.md` (đã sửa) khớp `tests/test_architecture.py` | ARCHITECTURE "Ranh giới module" | so từng dòng |
| K13 | Chế độ offline (FR33) bị cấm ở production | registry §4, §6 D-3 | `src/config.py` |
| K14 | Phân loại A–E của 19 ADR hợp lý; không ADR nào bị coi là đã duyệt | `docs/adr/README.md` | đọc từng ADR; nêu ADR bị xếp sai nhóm |
| K15 | Ba sơ đồ tuần tự phản ánh đúng thứ tự gọi trong code | architecture_diagram §2.5 | `src/services/charging_service.py`, `admission.py`, `control_loop.py`, `src/guard/dispatcher.py`, `emergency.py` |

## 4. Việc tìm thêm (không chỉ kiểm cái đã viết)

1. Chức năng / endpoint có trong code nhưng **không có** trong registry.
2. Ô trạng thái bị **phóng đại** (vd. ghi `ĐẠT` nhưng test không kiểm đúng yêu cầu đó, hoặc chỉ kiểm với mock).
3. Rủi ro mà audit bỏ sót, nhất là về an toàn (Guard, fail-safe), dữ liệu, bảo mật (JWT, `resident_id`).
4. Review độc lập kỹ thuật cho 4 ADR nhóm C (002, 006, 017, 019): mỗi ADR một kết luận "khớp code / lệch ở …".
   *(Ghi chú Remediation 25/11, theo K14: nhóm C còn gồm phần C của ADR-014 và ADR-018 — chưa review.)*

## 5. Định dạng kết quả

Ghi vào `docs/handoff/REVIEW_PHASE1_RESULT.md` (hoặc gửi lại cho Human Supervisor nếu không được ghi file):

1. **Tóm tắt ≤ 10 dòng**, tiếng Việt dễ hiểu: tài liệu có dùng được để quản lý không, sai nghiêm trọng nhất là gì.
2. Bảng K1–K15: `ĐÚNG` / `SAI` / `MỘT PHẦN` / `KHÔNG KIỂM ĐƯỢC` + bằng chứng (lệnh đã chạy, file:dòng, commit).
3. Phát hiện mới (§4), xếp theo mức ảnh hưởng.
4. Ghi rõ phần nào reviewer **tự chạy / tự đọc**, phần nào chỉ suy luận.

## 6. Phân vai (áp dụng từ Giai đoạn 1)

| Vai | Ai | Được | Không được |
|---|---|---|---|
| Human Supervisor | chủ dự án | duyệt phạm vi, ADR nhóm A, thay đổi production / CI | — |
| Tech Lead / Architect | Codex | duyệt ADR nhóm B, D; review kỹ thuật nhóm C | tự duyệt nhóm A |
| Implementation Agent | Claude (phiên viết code / tài liệu) | viết code, tài liệu, chạy test | tự gọi kết quả của mình là "kiểm chứng độc lập" |
| Independent Reviewer | agent khác người viết | đối chiếu code, chạy test, báo sai | sửa phần đang review |
| QA | agent hoặc người, khác Implementation | chạy test / eval / benchmark, ghi evidence có commit | sửa code để test qua |
| Reporting | bất kỳ agent | tóm tắt cho Human theo HACP | thêm khẳng định không có bằng chứng |
