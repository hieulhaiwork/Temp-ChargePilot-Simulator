# Documentation Rationalization Audit — P-019 (chỉ đọc)

> **Checkpoint cần đồng bộ** (HANDOFF §0): lúc tạo file này Codex đang giữ khoá các ô checkpoint §1.3 / §1.8–§1.11
> cho X-02, nên **không** sửa HANDOFF. Agent nhận khoá kế tiếp chép vào HANDOFF:
> - §1.3: thêm dòng `D-01 | Documentation Rationalization Audit (Human giao 25/11, chỉ đọc) | XONG, HANDOFF_READY (Claude, 25/11) | docs/handoff/DOCUMENTATION_RATIONALIZATION_AUDIT.md`.
> - §1.8: file mới `docs/handoff/DOCUMENTATION_RATIONALIZATION_AUDIT.md` (Claude 25/11). Không sửa / xoá / di chuyển tài liệu nào khác.
> - §1.5 chờ Human: HD-1…HD-7 (§8 file này).
> - §1.11: `2026-11-25 | Claude Code (opus-5-5) | D-01 audit tài liệu chỉ đọc xong; không chạm khoá X-02`.

- Người làm: Claude Code (`claude-opus-5-5`), 2026-11-25. Chỉ đọc. Code `feature/unified-core` @ `ce23136`; snapshot nhánh
  `refs/audit/2026-11-25/{ai-4,be-fe-integration}`. Claude là tác giả nhiều tài liệu được audit ⇒ **không độc lập**.
- Không xoá / di chuyển / sửa tài liệu nào; không sửa source, test, CI; không commit. Không đụng tài liệu của X-02.
- Phương pháp: liệt kê `git ls-files` + untracked; đo dòng / byte / token (ước tính ký tự ÷ 3,2 — tiếng Việt, sai số ±30%);
  đếm tham chiếu bằng tìm tên file trong mọi file text của repo (trừ `eval/evidence`, `node_modules`, `openapi.json`);
  tìm cụm lỗi thời (`LiveStation`, A–D, `src/agents/{graph,nodes,tools}`, `base.py` / `SimulatorGateway`, "9 bảng") rồi
  **đọc dòng** để tách "nhắc như lịch sử" với "trình bày như hiện hành"; đối chiếu với code (file có / không tồn tại, hàm có
  được gọi không).

## 1. Kết luận

| Loại | Số file `.md` | Ghi chú |
|---|---:|---|
| ACTIVE | 91 | gồm 50 file `docs/guide/` (sách template AI20K, chỉ tham khảo) |
| EVIDENCE | 37 | review / audit độc lập, raw refactor, `eval/evidence/*` (có baseline đóng băng) |
| HISTORICAL | 37 | báo cáo refactor đã đóng, brief, mockup, journal / worklog |
| UPDATE_REQUIRED | 12 | đang được dùng nhưng có nội dung sai so với code |
| SUPERSEDED | 6 | `plan/00, 10, 30`, `business-overview`, ADR-011, ADR-016 |
| OBSOLETE | 4 | `README_boilerplate.md` + 3 prompt template không được graph dùng |
| DUPLICATE | 2 | `PROJECT_CONTEXT.md`, `src/simulator/docs/PROJECT_STATE.md` |
| UNVERIFIED | 2 | `CONTRIBUTING.md`, `notebooks/README.md` (template) |
| GENERATED | 1 | `eval/results/benchmark.md` (untracked) |
| **Tổng** | **192** | 32 794 dòng, ~2,3 MB. 11 file untracked (governance Phase 1 + 1 generated) |

Ngoài `.md`: 417 file tài liệu / artifact khác (224 `.txt` raw refactor, ~99 file evidence JSON / DOCX, 47 file
`eval/results` gồm 28 MB `merged-sim/` untracked, 30 file mockup HTML / JS / SVG, `frontend/openapi.json` GENERATED từ
`scripts/export_openapi.py`, 5 kịch bản `config/scenarios/` — 3 legacy nhưng nằm trong baseline đóng băng ⇒ giữ).

**Năm nguồn context nguy hiểm nhất** (agent dễ đọc phải và tin là hiện hành):
1. `src/simulator/AGENTS.md` — **tự nạp** khi agent làm việc trong `src/simulator/`; ghi "backend app runs on `LiveStation`
   (`src/simulator/live.py`, ADR-016)" (file không tồn tại ở `ce23136`) và "MVP-4 … not yet selected. Do not choose" (trái quyết
   định Human Q1 25/11: ưu tiên AI-4 WHY). Root `AGENTS.md` còn bảo "áp thêm khi làm việc ở đó".
2. `src/simulator/docs/SIMULATOR_INTEGRATION_CONTRACT.md` — header "backend **chưa** tích hợp theo hợp đồng này … dùng
   `LiveStation`"; được `src/config.py`, ADR-017, ADR-018, `config/station.yaml` trỏ tới.
3. Bốn nguồn "trạng thái dự án" cạnh tranh: `docs/handoff/HANDOFF.md` (chuẩn), `PROJECT_CONTEXT.md` (tự gọi là "file agent
   đọc ĐẦU TIÊN"; còn trỏ baseline Phase 3 đã thay, coi ADR-011 `base.py` là hiện hành), `src/simulator/docs/PROJECT_STATE.md`
   (cho Codex), và `docs/ai4/PROJECT_STATE.md` trên nhánh `ai-4` (sẽ thành nguồn thứ tư khi tích hợp).
4. Nhánh `feature/be-fe-integration` mang **bản cũ** của ~40 tài liệu (từ `develop`): agent làm trên nhánh đó đọc kiến trúc
   `LiveStation` / A–D như hiện hành (giải thích một phần vì sao nhánh đó dựng trên kiến trúc cũ — `CROSS_BRANCH_ALIGNMENT_AUDIT.md`).
5. `docs/plan/21-ui-spec.md` S8 (5 chiến lược A_fcfs…D, dòng 83, 246) và `README.md` ("9 bảng") — spec / deliverable còn
   hiệu lực nhưng sai contract; banner đầu `plan/*` có cảnh báo, nhưng thân bài vẫn đọc như yêu cầu.

**Footprint context mặc định:** hiện ~18 400 token (CLAUDE 5 300 + AGENTS 500 + HANDOFF §0 1 600 + §1 11 000), tới
~25 000 khi làm trong `src/simulator/` hoặc agent theo lời `PROJECT_CONTEXT.md`. Đề xuất: ~6 000 (giảm ~65–75%) — §6.

## 2. Inventory chi tiết (từng file)

Cột: T = tracked, U = untracked; "Dòng / token" là số dòng / token ước tính; "Ref" = số file khác nhắc tên file.
| Đường dẫn | T/U | Dòng / token | Mục đích | Trạng thái | Nguồn thay thế | Ref (số, ví dụ) | Giá trị | Rủi ro nếu xoá | Hành động |
|---|---|---|---|---|---|---|---|---|---|
| `.agents/rules/ai-log-hook.md` | T | 44 / ~0k | Quy tắc hook ai-log | **ACTIVE** | — | 0 | Cao (chương trình) | Vi phạm logging BTC | KEEP, không sửa (invariant logging hooks) |
| `.agents/workflows/log.md` | T | 37 / ~0k | Workflow ai-log | **ACTIVE** | — | 2 (ai-log-hook.md, chapter-13.md) | Cao (chương trình) | như trên | KEEP, không sửa |
| `.github/PULL_REQUEST_TEMPLATE.md` | T | 23 / ~0k | Mẫu PR | **UPDATE_REQUIRED** | — | 3 (50-devops.md, MODULE_PROVENANCE.md…) | Trung bình | Mất checklist PR | KEEP; UPDATE trong G-auto (G6, 7 câu hỏi) |
| `AGENTS.md` | U | 25 / ~0k | Lối vào cho Codex | **ACTIVE** | — | 11 (PROJECT_CONTEXT.md, HANDOFF.md…) | Cao | Codex không biết giao thức | KEEP; UPDATE: cảnh báo `src/simulator/AGENTS.md` lỗi thời cho tới khi sửa |
| `ARCHITECTURE.md` | T | 346 / ~8k | Sườn thư mục, ranh giới module | **ACTIVE** | — | 12 (CLAUDE.md, PROJECT_CONTEXT.md…) | Cao | Mất bản đồ ranh giới | KEEP; CONSOLIDATE cây thư mục của CLAUDE / README về đây |
| `CLAUDE.md` | T | 203 / ~5k | Hướng dẫn agent mặc định (tự nạp) | **UPDATE_REQUIRED** | — | 33 (PROJECT_CONTEXT.md, chapter-14.md…) | Cao | Mất quy tắc dự án | UPDATE: rút còn router + invariants; chuyển cây thư mục / ADR tóm tắt sang ARCHITECTURE / adr README |
| `CODE_OF_CONDUCT.md` | T | 39 / ~0k | Chuẩn cộng đồng (template) | **ACTIVE** | — | 1 (CONTRIBUTING.md) | Thấp | Thấp | KEEP |
| `CONTRIBUTING.md` | T | 56 / ~0k | Hướng dẫn đóng góp (template) | **UNVERIFIED** | CLAUDE.md quy ước git | 0 | Thấp | Thấp | KEEP; xem lại khi làm G-auto |
| `JOURNAL.md` | T | 120 / ~2k | Nhật ký nhóm (deliverable BTC) | **HISTORICAL** | — | 6 (README.md, README_boilerplate.md…) | Cao (bắt buộc) | Thiếu deliverable | KEEP; chỉ ghi thêm, không sửa lịch sử |
| `PROJECT_CONTEXT.md` | T | 137 / ~3k | Quick Rehydrate cũ (C5) | **DUPLICATE** | CLAUDE.md Quick Rehydrate + HANDOFF §1 | 7 (README.md, context-management.md…) | Thấp | Nếu là deliverable C5 của chương trình | CONSOLIDATE → thu còn 5–10 dòng trỏ về CLAUDE / HANDOFF (cần Human: có phải deliverable?) |
| `README.md` | T | 222 / ~3k | Deliverable BTC, giới thiệu repo | **UPDATE_REQUIRED** | — | 25 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Cao (bắt buộc) | Thiếu deliverable | UPDATE: "9 bảng" → 10; trỏ registry thay vì kể trạng thái |
| `README_boilerplate.md` | T | 107 / ~0k | Mẫu README của template | **OBSOLETE** | README.md | 1 (common-mistakes.md) | Không | Thấp (1 ref trong docs/guide) | DELETE_CANDIDATE (cần Human: template có bắt buộc giữ?) |
| `SECURITY.md` | T | 40 / ~0k | Chính sách bảo mật (template) | **ACTIVE** | — | 2 (CONTRIBUTING.md, 50-devops.md) | Trung bình | Trung bình | KEEP |
| `WORKLOG.md` | T | 111 / ~1k | Worklog (deliverable BTC) | **HISTORICAL** | — | 5 (README.md, README_boilerplate.md…) | Cao (bắt buộc) | Thiếu deliverable | KEEP; chỉ ghi thêm |
| `docs/FEATURE_REGISTRY.md` | U | 353 / ~11k | Nguồn hiện trạng chức năng (đã nghiệm thu) | **ACTIVE** | — | 11 (ARCHITECTURE.md, PRD.md…) | Rất cao | Mất nguồn sự thật | KEEP; UPDATE theo H-5 khi Human duyệt |
| `docs/PRD.md` | T | 872 / ~22k | Nguồn yêu cầu | **UPDATE_REQUIRED** | — | 16 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Rất cao | Mất yêu cầu | KEEP; UPDATE FR9a / FR12 (base.py, SimulatorGateway) theo registry §4 — cần duyệt |
| `docs/adr/ADR-001-giu-langgraph-cho-f1.md` | T | 34 / ~0k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 2 (ARCHITECTURE.md, README.md) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-002-guard-chokepoint.md` | T | 46 / ~0k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 2 (ARCHITECTURE.md, README.md) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-003-tham-so-trong-config.md` | T | 36 / ~0k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 2 (ARCHITECTURE.md, README.md) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-004-contract-first-501.md` | T | 35 / ~0k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 2 (ARCHITECTURE.md, README.md) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-005-persistence-sqlalchemy-alembic.md` | T | 46 / ~0k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 2 (ARCHITECTURE.md, README.md) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-006-danh-tinh-jwt-resident-id-server-side.md` | T | 43 / ~0k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 2 (ARCHITECTURE.md, README.md) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-007-station-runtime-va-control-loop.md` | T | 47 / ~1k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 2 (ARCHITECTURE.md, README.md) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-008-quy-uoc-api.md` | T | 36 / ~0k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 2 (ARCHITECTURE.md, README.md) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-009-frontend-nextjs.md` | T | 30 / ~0k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 3 (ARCHITECTURE.md, README.md…) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-010-bai-hybrid-ac-dc.md` | T | 102 / ~1k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 8 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-011-mot-simulator-sau-be-mat-cong-khai.md` | T | 118 / ~2k | ADR (lịch sử quyết định) | **SUPERSEDED** | ADR-019 | 8 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Cao (lịch sử) | Mất lịch sử ADR | KEEP; Tech Lead ghi Superseded (một phần) |
| `docs/adr/ADR-012-mot-danh-muc-xe-va-kich-ban.md` | T | 83 / ~1k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 5 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-013-workflow-xac-dinh-llm-hai-dau.md` | T | 51 / ~0k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 6 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-014-decision-trace-counterfactual-hitl.md` | T | 112 / ~2k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 15 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-015-pham-vi-mvp4-va-quy-tac-bang-chung.md` | T | 74 / ~1k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 10 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-016-livestation-cho-backend.md` | T | 49 / ~1k | ADR (lịch sử quyết định) | **SUPERSEDED** | ADR-018 → ADR-019 | 8 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Cao (lịch sử) | Mất lịch sử ADR | KEEP; Tech Lead ghi Superseded |
| `docs/adr/ADR-017-guard-theo-hop-dong-an-toan-simulator.md` | T | 54 / ~1k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 2 (ARCHITECTURE.md, README.md) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-018-backend-chay-engine-simulator.md` | T | 46 / ~1k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 4 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/ADR-019-unified-core-hop-dong-dung-chung.md` | T | 226 / ~5k | ADR (Proposed; triage ở adr/README) | **ACTIVE** | — | 10 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Cao | Mất lịch sử quyết định | KEEP, không sửa nội dung lịch sử |
| `docs/adr/README.md` | T | 145 / ~4k | Chỉ mục ADR + triage + quyết định Human | **ACTIVE** | — | 9 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Rất cao | Mất lịch sử quyết định | KEEP |
| `docs/architecture_diagram.md` | T | 380 / ~7k | Hiểu hệ thống 4 tầng (đã nghiệm thu) | **ACTIVE** | — | 15 (ARCHITECTURE.md, CLAUDE.md…) | Cao | Mất tài liệu 4 tầng | KEEP |
| `docs/business-overview.md` | T | 472 / ~9k | Tổng quan nghiệp vụ 20–22/11 | **SUPERSEDED** | PRD + architecture_diagram Tầng 1 | 6 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Thấp | Thấp (4 ref) | ARCHIVE; còn ghi "backend dùng LiveStation" như hiện trạng |
| `docs/communication/HUMAN_AGENT_COMMUNICATION.md` | U | 189 / ~3k | HACP — giao tiếp với Human | **ACTIVE** | — | 6 (CLAUDE.md, HANDOFF.md…) | Cao | Mất quy tắc báo cáo | KEEP; nguồn nạp theo task, không mặc định |
| `docs/communication/RESPONSE_TEST_CASES.md` | U | 364 / ~5k | Bộ test cho HACP | **ACTIVE** | — | 2 (HANDOFF.md, HUMAN_AGENT_COMMUNICATION.md) | Trung bình | Mất kiểm thử HACP | KEEP; chỉ đọc khi sửa HACP |
| `docs/design/kien-truc-tra-loi-3-tang.md` | T | 142 / ~2k | Đề xuất 20/11 trả lời dựa dự báo (F12 đã hoãn) | **HISTORICAL** | ADR-015, AI-4 WHY | 2 (ARCHITECTURE.md, 10-backend.md) | Thấp | Thấp (2 ref) | ARCHIVE |
| `docs/handoff/AUDIT_BACKEND_SIMULATOR_ALIGNMENT.md` | U | 198 / ~6k | Tự audit backend ↔ simulator | **EVIDENCE** | registry §4, I-7 | 4 (HANDOFF.md, FEATURE_REGISTRY.md…) | Trung bình | Mất chi tiết B1–B4 | KEEP |
| `docs/handoff/CROSS_BRANCH_ALIGNMENT_AUDIT.md` | U | 242 / ~6k | Audit chéo nhánh X-01 (đang được X-02 kiểm) | **EVIDENCE** | — | 1 (HANDOFF.md) | Cao | Mất đầu vào X-02 | KEEP, không sửa khi X-02 đang chạy |
| `docs/handoff/HANDOFF.md` | T | 514 / ~15k | Checkpoint + giao thức (bắt buộc đọc §0–§1) | **UPDATE_REQUIRED** | — | 17 (ARCHITECTURE.md, CLAUDE.md…) | Rất cao | Mất trạng thái bền | UPDATE: §1 chỉ giữ việc đang mở; chuyển bản ghi đã đóng sang mục lịch sử cuối file |
| `docs/handoff/REMEDIATION_PHASE1.md` | U | 215 / ~6k | Bằng chứng remediation F1–F5, N2–N4, tiêu chí R-1…R-6 | **EVIDENCE** | — | 4 (README.md, HANDOFF.md…) | Cao | Mất tiêu chí backlog | KEEP |
| `docs/handoff/REREVIEW_PHASE1_RESULT.md` | U | 449 / ~16k | Re-review (T0–T5 hiện hành + lịch sử) | **EVIDENCE** | — | 5 (README.md, HANDOFF.md…) | Rất cao | Mất bằng chứng nghiệm thu | KEEP, không sửa |
| `docs/handoff/REVIEW_PHASE1.md` | U | 80 / ~1k | Brief review độc lập Phase 1 (đã dùng) | **HISTORICAL** | — | 7 (README.md, HANDOFF.md…) | Trung bình (truy vết) | Mất brief review | KEEP (EVIDENCE); không nạp mặc định |
| `docs/handoff/REVIEW_PHASE1_RESULT.md` | U | 196 / ~5k | Kết quả review độc lập lần 1 | **EVIDENCE** | — | 8 (README.md, HANDOFF.md…) | Rất cao | Mất bằng chứng độc lập | KEEP, không sửa |
| `docs/mockups/cu-dan/HUONG-DAN.md` | T | 215 / ~3k | Hướng dẫn mockup cư dân | **HISTORICAL** | frontend/, plan/21-ui-spec | 3 (00-overview.md, 21-ui-spec.md…) | Thấp | Code FE trỏ tới mockup | KEEP (tham khảo) |
| `docs/mockups/van-hanh/HUONG-DAN.md` | T | 67 / ~1k | Hướng dẫn mockup vận hành | **HISTORICAL** | như trên | 4 (HUONG-DAN.md, 00-overview.md…) | Thấp | như trên | KEEP (tham khảo) |
| `docs/plan/00-overview.md` | T | 357 / ~9k | Kế hoạch tổng 16–19/11 (banner đã cảnh báo) | **SUPERSEDED** | HANDOFF, registry, ADR-019 | 10 (ARCHITECTURE.md, PROJECT_CONTEXT.md…) | Thấp | Ref từ registry §1 (mã task T*) | ARCHIVE; giữ bảng task ID qua registry §1.2 |
| `docs/plan/10-backend.md` | T | 470 / ~9k | Kế hoạch backend (SimulatorGateway là "đích") | **SUPERSEDED** | ARCHITECTURE, ADR-019 | 17 (ADR-006-danh-tinh-jwt-resident-id-server-side.md, ADR-007-station-runtime-va-control-loop.md…) | Thấp | 17 ref (đa số lịch sử) | ARCHIVE |
| `docs/plan/20-frontend.md` | T | 257 / ~5k | Kế hoạch frontend | **HISTORICAL** | frontend/, 21-ui-spec | 8 (ARCHITECTURE.md, ADR-009-frontend-nextjs.md…) | Thấp | Thấp | ARCHIVE |
| `docs/plan/21-ui-spec.md` | T | 1491 / ~40k | Spec UI hiện hành (S1–S9) | **UPDATE_REQUIRED** | — | 6 (JOURNAL.md, business-overview.md…) | Cao | Mất spec UI | KEEP; UPDATE S8 (A–D → policy registry) |
| `docs/plan/22-ui-work-split.md` | T | 155 / ~3k | Chia việc UI | **HISTORICAL** | frontend/ | 6 (HANDOFF.md, page.tsx…) | Thấp | Code FE trỏ tới | KEEP (tham khảo) |
| `docs/plan/30-ai.md` | T | 513 / ~10k | Kế hoạch AI / optimizer cũ (LP A–D, F6 cũ) | **SUPERSEDED** | ADR-019, docs/ai4 (khi tích hợp) | 13 (station.yaml, ADR-006-danh-tinh-jwt-resident-id-server-side.md…) | Thấp | 13 ref | ARCHIVE |
| `docs/plan/40-database.md` | T | 377 / ~5k | Thiết kế DB + bảng dự kiến | **UPDATE_REQUIRED** | src/db/tables.py | 10 (ARCHITECTURE.md, alembic.ini…) | Trung bình | Mất kế hoạch bảng AI-1 | UPDATE (ai-4 cũng sửa — gộp khi tích hợp) |
| `docs/plan/50-devops.md` | T | 248 / ~5k | DevOps / CI | **UPDATE_REQUIRED** | — | 8 (Dockerfile, architecture_diagram.md…) | Trung bình | Trung bình | KEEP; UPDATE phần LiveStation |
| `docs/plan/55-ci-runner.md` | T | 161 / ~2k | Runner VM tự host | **ACTIVE** | — | 3 (JOURNAL.md, WORKLOG.md…) | Trung bình | Mất cách bật runner | KEEP |
| `docs/plan/56-deploy-render-image.md` | T | 193 / ~3k | Hiện trạng deploy | **ACTIVE** | — | 6 (ci.yml, CLAUDE.md…) | Cao | Mất hướng dẫn deploy | KEEP |
| `docs/refactor/BASELINE.md` | T | 122 / ~2k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 3 (MODULE_PROVENANCE.md, PHASE0_FINDINGS.md…) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/DELETION_MANIFEST.md` | T | 108 / ~3k | Danh sách đã xoá ở refactor | **EVIDENCE** | — | 23 (ARCHITECTURE.md, CLAUDE.md…) | Cao | CLAUDE.md trỏ tới | KEEP |
| `docs/refactor/EXPECTED_FAILURES.md` | T | 63 / ~1k | Lỗi dự kiến trong refactor | **HISTORICAL** | — | 9 (PHASE3_DESIGN.md, PHASE3_REPORT.md…) | Thấp | 9 ref | KEEP (archive) |
| `docs/refactor/FINAL_ACCEPTANCE_A_REPORT.md` | T | 228 / ~5k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 1 (FINAL_ACCEPTANCE_REPORT.md) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/FINAL_ACCEPTANCE_B_REPORT.md` | T | 175 / ~4k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 2 (FINAL_ACCEPTANCE_REPORT.md, test_failsafe_after_apply.py) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/FINAL_ACCEPTANCE_REPORT.md` | T | 68 / ~1k | Nghiệm thu Unified Core | **EVIDENCE** | — | 6 (CLAUDE.md, ADR-019-unified-core-hop-dong-dung-chung.md…) | Cao | CLAUDE / ADR-019 trỏ tới | KEEP |
| `docs/refactor/FINAL_MAP.md` | T | 92 / ~2k | Bản đồ module sau refactor | **ACTIVE** | ARCHITECTURE | 11 (ARCHITECTURE.md, ADR-019-unified-core-hop-dong-dung-chung.md…) | Trung bình | 11 ref | KEEP |
| `docs/refactor/FINAL_REVIEW_FIX_A_REPORT.md` | T | 240 / ~5k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 2 (FINAL_REVIEW_FIX_REPORT.md, FINAL_ACCEPTANCE_PATCH_BRIEF.md) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/FINAL_REVIEW_FIX_B_REPORT.md` | T | 194 / ~5k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 2 (FINAL_REVIEW_FIX_REPORT.md, FINAL_ACCEPTANCE_PATCH_BRIEF.md) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/FINAL_REVIEW_FIX_REPORT.md` | T | 58 / ~1k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 5 (ADR-019-unified-core-hop-dong-dung-chung.md, HANDOFF.md…) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/IMPORT_GRAPH.md` | T | 121 / ~2k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 1 (PHASE0_FINDINGS.md) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/LLMCHAT_REPORT.md` | T | 95 / ~2k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 3 (REFACTOR_REPORT.md, LLMCHAT_BRIEF.md…) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/MODULE_PROVENANCE.md` | T | 127 / ~4k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 1 (PHASE0_FINDINGS.md) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/PHASE0_FINDINGS.md` | T | 227 / ~5k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 5 (FINAL_REVIEW_FIX_A_REPORT.md, PHASE3_DESIGN.md…) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/PHASE1_REPORT.md` | T | 137 / ~3k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 2 (ADR-019-unified-core-hop-dong-dung-chung.md, PLAN.md) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/PHASE2_REPORT.md` | T | 137 / ~3k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 4 (ADR-019-unified-core-hop-dong-dung-chung.md, PHASE3_DESIGN.md…) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/PHASE3_DESIGN.md` | T | 222 / ~4k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 10 (ADR-019-unified-core-hop-dong-dung-chung.md, DELETION_MANIFEST.md…) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/PHASE3_REPORT.md` | T | 178 / ~4k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 6 (ADR-019-unified-core-hop-dong-dung-chung.md, EXPECTED_FAILURES.md…) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/PHASE4_P4-API_REPORT.md` | T | 117 / ~3k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 2 (ADR-019-unified-core-hop-dong-dung-chung.md, PHASE4_FINAL_BRIEF.md) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/PHASE4_P4-CORE_REPORT.md` | T | 81 / ~1k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 2 (REFACTOR_REPORT.md, PHASE4_FINAL_BRIEF.md) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/PLAN.md` | T | 93 / ~1k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 8 (ADR-019-unified-core-hop-dong-dung-chung.md, EXPECTED_FAILURES.md…) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/REFACTOR_REPORT.md` | T | 139 / ~2k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 10 (ADR-019-unified-core-hop-dong-dung-chung.md, FINAL_ACCEPTANCE_A_REPORT.md…) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/TECHLEAD_PHASE4_DECISIONS.md` | T | 83 / ~1k | Báo cáo / thiết kế refactor Unified Core (đã đóng) | **HISTORICAL** | FINAL_ACCEPTANCE_REPORT, ADR-019 | 6 (ADR-019-unified-core-hop-dong-dung-chung.md, HANDOFF.md…) | Thấp–TB | Mất truy vết refactor | KEEP trong `docs/refactor/` (coi cả thư mục là archive) |
| `docs/refactor/tasks/FINAL_ACCEPTANCE_PATCH_BRIEF.md` | T | 87 / ~1k | Brief giao việc refactor (đã xong) | **HISTORICAL** | báo cáo tương ứng | 3 (FINAL_ACCEPTANCE_A_REPORT.md, FINAL_ACCEPTANCE_B_REPORT.md…) | Thấp | Mất truy vết giao việc | KEEP trong thư mục refactor (đã đóng băng) |
| `docs/refactor/tasks/FINAL_REVIEW_FIX_BRIEF.md` | T | 108 / ~2k | Brief giao việc refactor (đã xong) | **HISTORICAL** | báo cáo tương ứng | 5 (FINAL_ACCEPTANCE_A_REPORT.md, FINAL_REVIEW_FIX_A_REPORT.md…) | Thấp | Mất truy vết giao việc | KEEP trong thư mục refactor (đã đóng băng) |
| `docs/refactor/tasks/LLMCHAT_BRIEF.md` | T | 74 / ~1k | Brief giao việc refactor (đã xong) | **HISTORICAL** | báo cáo tương ứng | 2 (LLMCHAT_REPORT.md, PLAN.md) | Thấp | Mất truy vết giao việc | KEEP trong thư mục refactor (đã đóng băng) |
| `docs/refactor/tasks/PHASE3_BRIEF.md` | T | 88 / ~1k | Brief giao việc refactor (đã xong) | **HISTORICAL** | báo cáo tương ứng | 1 (PLAN.md) | Thấp | Mất truy vết giao việc | KEEP trong thư mục refactor (đã đóng băng) |
| `docs/refactor/tasks/PHASE4_BRIEF.md` | T | 75 / ~1k | Brief giao việc refactor (đã xong) | **HISTORICAL** | báo cáo tương ứng | 2 (PHASE4_P4-API_REPORT.md, PHASE4_FINAL_BRIEF.md) | Thấp | Mất truy vết giao việc | KEEP trong thư mục refactor (đã đóng băng) |
| `docs/refactor/tasks/PHASE4_FINAL_BRIEF.md` | T | 57 / ~1k | Brief giao việc refactor (đã xong) | **HISTORICAL** | báo cáo tương ứng | 0 | Thấp | Mất truy vết giao việc | KEEP trong thư mục refactor (đã đóng băng) |
| `eval/README.md` | T | 72 / ~1k | Hướng dẫn eval | **ACTIVE** | — | 1 (PHASE4_P4-API_REPORT.md) | Trung bình | Trung bình | KEEP |
| `eval/results/archive/2026-11-22-pre-refactor/README.md` | T | 14 / ~0k | Ghi chú archive A–D | **HISTORICAL** | — | 1 (README.md) | Thấp | Mất ngữ cảnh archive | KEEP |
| `eval/results/archive/2026-11-22-pre-refactor/benchmark.md` | T | 118 / ~3k | Bảng A–D trước refactor | **HISTORICAL** | frozen baseline | 25 (HANDOFF.md, 00-overview.md…) | Thấp | Mất lịch sử | KEEP (archive đã có nhãn) |
| `eval/results/benchmark.md` | U | 132 / ~3k | Đầu ra `run_benchmark.py` (untracked) | **GENERATED** | eval/evidence/…frozen-baseline | 25 (HANDOFF.md, 00-overview.md…) | Thấp | Không (sinh lại được) | Giữ nguyên; Human quyết `.gitignore` (thuộc G-auto) |
| `eval/results/report.md` | T | 62 / ~0k | Báo cáo eval Agent — đang là mẫu template | **UPDATE_REQUIRED** | — | 15 (ci.yml, Makefile…) | Cao (deliverable) | CI / Makefile trỏ tới | KEEP; UPDATE khi có eval LLM thật |
| `frontend/AGENTS.md` | T | 10 / ~0k | Quy tắc agent cho Next.js | **ACTIVE** | — | 4 (PROJECT_CONTEXT.md, HANDOFF.md…) | Cao | Agent viết sai Next 16 | KEEP |
| `frontend/README.md` | T | 55 / ~0k | Chạy frontend | **ACTIVE** | — | 1 (ARCHITECTURE.md) | Trung bình | Thấp | KEEP |
| `notebooks/README.md` | T | 25 / ~0k | Notebook (template) | **UNVERIFIED** | — | 2 (30-ai.md, datasets.py) | Thấp | Thấp | KEEP |
| `presentation/README.md` | T | 27 / ~0k | Deliverable thuyết trình; liệt kê file chưa có | **UPDATE_REQUIRED** | — | 2 (checklist.md, FEATURE_REGISTRY.md) | Cao (bắt buộc) | Thiếu deliverable | KEEP; UPDATE khi có pitch deck / video |
| `prompts/README.md` | T | 53 / ~0k | Chỉ mục prompt | **ACTIVE** | — | 1 (LLMCHAT_REPORT.md) | Trung bình | Thấp | KEEP |
| `prompts/charging_domain.md` | T | 30 / ~0k | Prompt chat (nạp bởi reason_node) | **ACTIVE** | — | 7 (ARCHITECTURE.md, CLAUDE.md…) | Rất cao | Chat hỏng | KEEP |
| `prompts/charging_safeguards.md` | T | 13 / ~0k | Guardrail prompt | **ACTIVE** | — | 6 (ARCHITECTURE.md, CLAUDE.md…) | Rất cao | Chat hỏng | KEEP |
| `prompts/citation_rules.md` | T | 12 / ~0k | Như trên | **OBSOLETE** | — | 5 (ARCHITECTURE.md, prompts.md…) | Thấp | như trên | DELETE_CANDIDATE — cùng task code |
| `prompts/finalize.md` | T | 47 / ~0k | Prompt finalize | **ACTIVE** | — | 6 (ARCHITECTURE.md, CLAUDE.md…) | Rất cao | Chat hỏng | KEEP |
| `prompts/reason.md` | T | 78 / ~0k | Prompt reason | **ACTIVE** | — | 7 (ARCHITECTURE.md, CLAUDE.md…) | Rất cao | Chat hỏng | KEEP |
| `prompts/safeguards.md` | T | 12 / ~0k | Như trên | **OBSOLETE** | charging_safeguards.md | 11 (ARCHITECTURE.md, CLAUDE.md…) | Thấp | như trên | DELETE_CANDIDATE — cùng task code |
| `prompts/system_prompt.md` | T | 44 / ~0k | Prompt template; chỉ `build_system_prompt()` (không được graph gọi) + 1 test dùng | **OBSOLETE** | reason.md… | 6 (ARCHITECTURE.md, prompts.md…) | Thấp | Test `test_agent_patterns.py` vỡ | DELETE_CANDIDATE — chỉ cùng task code (ngoài phạm vi audit) |
| `src/forecast/artifacts/README.md` | T | 12 / ~0k | Chỗ để model F12 (hoãn) | **ACTIVE** | — | 0 | Thấp | Thấp | KEEP |
| `src/simulator/AGENTS.md` | T | 97 / ~3k | Quy tắc agent riêng simulator (tự nạp khi làm trong thư mục) | **UPDATE_REQUIRED** | — | 2 (AGENTS.md, FEATURE_REGISTRY.md) | Cao | Mất quy tắc simulator | **UPDATE gấp**: còn "backend chạy LiveStation (`src/simulator/live.py`)" và "MVP-4 chưa chọn" |
| `src/simulator/README.md` | T | 296 / ~4k | Chạy simulator standalone | **ACTIVE** | — | 0 | Trung bình | Trung bình | KEEP |
| `src/simulator/docs/DESIGN_DECISIONS.md` | T | 144 / ~2k | Quyết định R&D simulator | **HISTORICAL** | ADR-010/018/019 | 2 (ADR-017-guard-theo-hop-dong-an-toan-simulator.md, README.md) | Trung bình | Mất lý do thiết kế | KEEP |
| `src/simulator/docs/MVP2_BENCHMARK.md` | T | 89 / ~3k | Kết quả MVP-2 R&D | **EVIDENCE** | — | 2 (README.md, PROJECT_STATE.md) | Trung bình | Mất bằng chứng R&D | KEEP |
| `src/simulator/docs/MVP3_BENCHMARK.md` | T | 93 / ~3k | Kết quả MVP-3 R&D | **EVIDENCE** | — | 4 (README.md, DESIGN_DECISIONS.md…) | Trung bình | như trên | KEEP |
| `src/simulator/docs/PROJECT_STATE.md` | T | 54 / ~3k | Trạng thái dự án cho Codex (song song HANDOFF) | **DUPLICATE** | HANDOFF §1 | 0 | Thấp | Thấp (0 ref) | CONSOLIDATE vào HANDOFF; để lại 1 dòng trỏ |
| `src/simulator/docs/SIMULATOR_INTEGRATION_CONTRACT.md` | T | 352 / ~7k | Hợp đồng simulator ↔ backend | **UPDATE_REQUIRED** | ADR-019, models/station_protocols | 4 (station.yaml, ADR-017-guard-theo-hop-dong-an-toan-simulator.md…) | Trung bình | Code `src/config.py` và ADR trỏ tới | **UPDATE**: header ghi "backend chưa tích hợp, dùng LiveStation" |

| Nhóm | Số file | Dòng | Trạng thái | Hành động |
|---|---|---|---|---|
| `docs/guide/` | 50 md | 12628 | ACTIVE (tài liệu tham khảo của template AI20K; `check_docs.py` quét) | KEEP; không bao giờ nạp mặc định (Human xác nhận có bắt buộc giữ) |
| `docs/refactor/raw/` | 6 md | 880 | EVIDENCE (raw output refactor) | KEEP, không sửa |
| `eval/evidence/2026-11-21/` | 2 md | 172 | EVIDENCE | KEEP, không sửa |
| `eval/evidence/2026-11-22/` | 5 md | 413 | EVIDENCE | KEEP, không sửa |
| `eval/evidence/2026-11-23/` | 2 md | 179 | EVIDENCE | KEEP, không sửa |
| `eval/evidence/2026-11-23-refactor-phase1/` | 3 md | 386 | EVIDENCE | KEEP, không sửa |
| `eval/evidence/2026-11-23-refactor-phase2/` | 3 md | 351 | EVIDENCE | KEEP, không sửa |
| `eval/evidence/2026-11-23-refactor-phase3/` | 3 md | 92 | EVIDENCE | KEEP, không sửa |
| `eval/evidence/2026-11-23-refactor-phase3-baseline/` | 1 md | 23 | EVIDENCE | KEEP, không sửa |
| `eval/evidence/2026-11-23-refactor-phase4/` | 1 md | 18 | EVIDENCE | KEEP, không sửa |
| `eval/evidence/2026-11-24-unified-core-final-baseline/` | 1 md | 11 | EVIDENCE | KEEP, không sửa |
| `eval/evidence/2026-11-24-unified-core-frozen-baseline/` | 1 md | 13 | EVIDENCE | KEEP, không sửa — **baseline đóng băng, bảo vệ** |

## 3. Mâu thuẫn và trùng lặp (đối chiếu code)

| # | Tài liệu | Nói gì | Code thực tế (`ce23136`) | Mức |
|---|---|---|---|---|
| C-01 | `src/simulator/AGENTS.md:50` | Backend chạy `LiveStation` (`src/simulator/live.py`) | Không có file; backend = `HybridStation` + `StationKernel` | Cao (tự nạp) |
| C-02 | `src/simulator/AGENTS.md` mục milestone | MVP-4 chưa chọn, không được chọn | Human 25/11 Q1: ưu tiên AI-4 WHY; nhánh `ai-4` đang làm | Cao |
| C-03 | `src/simulator/docs/SIMULATOR_INTEGRATION_CONTRACT.md:10` | Backend chưa tích hợp, dùng `LiveStation` | Backend dùng chung kernel (ADR-019) | Cao |
| C-04 | `PROJECT_CONTEXT.md:50,71,109` + banner | ADR-011 `base.py` + `SimulatorGateway` là bề mặt; contract freeze `SimulatorGateway`; S8 = baseline Phase 3 | Không có hai thành phần; S8 = frozen baseline | Cao (tự xưng "đọc đầu tiên") |
| C-05 | `docs/business-overview.md:195` | "Hiện trạng 22/11: backend dùng `LiveStation`" | Đã xoá | Trung bình |
| C-06 | `README.md:153` | DB 9 bảng | 10 `__tablename__` | Thấp |
| C-07 | `docs/plan/21-ui-spec.md:83,246` | S8 có 5 chiến lược A–D | `StrategyName` = B0 / M2b / M3a / M3b; `GET /simulation/policies` | Trung bình |
| C-08 | `docs/plan/00-overview.md:34,58`, `10-backend.md:21–22`, `30-ai.md:117,321` | 9 bảng; `SimulatorGateway` / `FixtureSimulatorGateway` là đích; `test_lp_model.py`; chiến lược D | Không có; LP A–D đã xoá | Trung bình (có banner đầu file) |
| C-09 | `docs/PRD.md` FR9a, FR12 | Một `HybridSimulator` sau `base.py` + `SimulatorGateway` | Kernel chung; đã ghi ở registry §4 | Trung bình (đã có cầu nối) |
| C-10 | `JOURNAL.md:42,87,98`, `WORKLOG.md` | 9 bảng, `LiveStation`, ADR-016 | Đúng tại thời điểm viết | Không (HISTORICAL, không sửa) |
| C-11 | `docs/adr/ADR-011`, `ADR-016` | Quyết định cũ, header `Proposed` | Bị thay (triage nhóm D) | Thấp — chờ Tech Lead ghi `Superseded` |
| C-12 | `prompts/system_prompt.md`, `safeguards.md`, `citation_rules.md` | Prompt hệ thống | Chỉ `build_system_prompt()` dùng; hàm này **không** được graph gọi; 1 test dùng | Thấp (gây nhầm "prompt nào đang chạy") |
| C-13 | `CLAUDE.md` + `ARCHITECTURE.md` + `README.md` | Ba bản cây thư mục / kiến trúc | Lệch nhau (README 9 bảng) | Trung bình (trùng ⇒ trôi) |
| C-14 | `CLAUDE.md` "Quyết định kỹ thuật" + `docs/adr/README.md` | Hai bản tóm tắt ADR | Trôi theo thời gian | Thấp |
| C-15 | HANDOFF §1.12–§1.13, dòng §1.3 / §1.4 đã đóng, lịch sử 22–24/11 | Bản ghi đã đóng nằm trong vùng bắt buộc đọc | — | Trung bình (vd. dòng P1-12e "Render Mermaid: BLOCKER" phải đọc kèm ghi chú đã gỡ) |

**Nguồn cạnh tranh với Feature Registry** (trạng thái chức năng): `PROJECT_CONTEXT.md` (bảng hiện trạng), `README.md`
(tiến độ), `ARCHITECTURE.md` (✅ / 🧩 theo file), `docs/plan/00-overview.md` (bảng việc), `src/simulator/docs/PROJECT_STATE.md`,
và trên nhánh `ai-4`: `docs/ai4/PROJECT_STATE.md` + `ISSUES.md` (backlog R01–R11 trùng một phần R-1…R-6 của governance).

**Trùng nội dung chấp nhận được:** báo cáo refactor theo cặp A / B + bản tổng (`FINAL_ACCEPTANCE_{A,B,}_REPORT`,
`FINAL_REVIEW_FIX_{A,B,}_REPORT`) là evidence của luồng làm song song — giữ nguyên.

## 4. Dự báo khi tích hợp nhánh

| Nhánh | Tài liệu mang theo | Nguy cơ | Đề xuất |
|---|---|---|---|
| `feature/ai-4` | `docs/ai4/` 10 file (ADR_AI4_SCOPE 31 dòng, Master Plan 261, BASELINE 39, FOUNDATION_CONTRACT 60, ISSUES 67, 3 report 338, PROJECT_STATE 7, `collaboration_chat.md` **rỗng**); `docs/research/RESEARCH-SC-16.pdf` 18 MB; sửa `CLAUDE.md`, `docs/plan/40-database.md`; 516 file evidence | ADR ngoài `docs/adr/` ghi "Approved"; nguồn trạng thái thứ tư; `ISSUES.md` trùng backlog; `CLAUDE.md` xung đột với bản governance chưa commit | ADR → `docs/adr/ADR-020-…` dạng `Proposed`; `PROJECT_STATE.md` → HANDOFF; bảng ánh xạ R01–R11 ↔ R-1…R-6 trong registry §6.1; xoá file rỗng; reports + evidence giữ; PDF: HD-7 |
| `feature/be-fe-integration` | Không thêm tài liệu riêng; mang bản cũ của ~40 tài liệu từ `develop`; `frontend/openapi.json`, `schema.d.ts` GENERATED xung đột | Agent trên nhánh đọc kiến trúc cũ; giải xung đột kiểu "theirs" đưa tài liệu cũ trở lại | Port lại trên `unified-core` (khuyến nghị X-01); khi giải xung đột: tài liệu lấy bản `unified-core`, OpenAPI sinh lại (`make openapi`, `npm run gen:api`) |

## 5. Danh sách hành động

**KEEP (không đổi):** mọi `docs/adr/ADR-*.md` (kể cả 011 / 016), `docs/adr/README.md`, `docs/FEATURE_REGISTRY.md`,
`docs/architecture_diagram.md`, `ARCHITECTURE.md`, mọi EVIDENCE (`REVIEW_PHASE1_RESULT`, `REREVIEW_PHASE1_RESULT`,
`REMEDIATION_PHASE1`, `AUDIT_BACKEND_SIMULATOR_ALIGNMENT`, `CROSS_BRANCH_ALIGNMENT_AUDIT`, báo cáo X-02 khi xong,
`docs/refactor/**`, `eval/evidence/**` — đặc biệt `2026-11-24-unified-core-frozen-baseline/`), `JOURNAL.md`, `WORKLOG.md`,
`prompts/{reason,finalize,charging_domain,charging_safeguards}.md`, `.agents/**`, `frontend/AGENTS.md`, `docs/plan/55`, `56`,
HACP + test cases, `docs/guide/**` (template, không nạp mặc định), mockups.

**UPDATE (sửa nội dung, không xoá):**

| Ưu tiên | File | Sửa |
|---|---|---|
| P0 | `src/simulator/AGENTS.md` | Bỏ `LiveStation`; milestone MVP-4 theo Q1; trỏ ADR-019 / registry; chỉ giữ quy tắc riêng simulator |
| P0 | `src/simulator/docs/SIMULATOR_INTEGRATION_CONTRACT.md` | Header theo ADR-019 (hoặc đánh dấu HISTORICAL + trỏ `src/models/station_protocols.py`) |
| P0 | `docs/handoff/HANDOFF.md` | §1 chỉ còn việc mở / khoá / việc tiếp / 5 dòng log gần nhất; §1.12–§1.13 và task đã đóng chuyển xuống mục lịch sử cuối file |
| P1 | `CLAUDE.md` | Rút còn Quick Rehydrate ~10 dòng, Tiếp nhận, Giao tiếp (trỏ HACP), Invariants (chỉ quy tắc); bỏ "Kiến trúc", "Quyết định kỹ thuật" (trỏ `ARCHITECTURE.md`, `docs/adr/README.md`) |
| P1 | `README.md` | 10 bảng; trạng thái trỏ registry |
| P1 | `docs/plan/21-ui-spec.md` | S8 theo policy registry |
| P2 | `docs/PRD.md` FR9a / FR12 | Theo registry §4 (cần Human — PRD là nguồn yêu cầu) |
| P2 | `docs/plan/40-database.md`, `50-devops.md` | Bỏ `LiveStation`; gộp sửa của `ai-4` |
| P2 | `eval/results/report.md`, `presentation/README.md`, `.github/PULL_REQUEST_TEMPLATE.md` | Khi có eval LLM thật / deliverable / G-auto |

**CONSOLIDATE:**

| Nguồn | Gộp về | Cách |
|---|---|---|
| `PROJECT_CONTEXT.md` | `CLAUDE.md` Quick Rehydrate + HANDOFF §1 | Thu còn ≤ 10 dòng trỏ (giữ file nếu là deliverable — HD-1) |
| `src/simulator/docs/PROJECT_STATE.md` | HANDOFF §1 | Một dòng trỏ; lịch sử giữ trong git |
| `docs/ai4/PROJECT_STATE.md`, `ISSUES.md` (khi tích hợp) | HANDOFF §1, registry §6.1 | Như trên + bảng ánh xạ ID |
| Cây thư mục trong `CLAUDE.md`, `README.md` | `ARCHITECTURE.md` | Hai file kia chỉ trỏ |
| Tóm tắt ADR trong `CLAUDE.md` | `docs/adr/README.md` | Trỏ |

**ARCHIVE** (đánh dấu HISTORICAL; mặc định **banner tại chỗ**, chỉ di chuyển khi Human duyệt HD-2, vì nhiều file được code /
tài liệu khác trỏ tới): `docs/plan/00-overview.md` (10 ref), `10-backend.md` (17), `20-frontend.md` (8), `30-ai.md` (13),
`docs/business-overview.md` (6), `docs/design/kien-truc-tra-loi-3-tang.md` (2), `docs/handoff/REVIEW_PHASE1.md` (sau khi đóng
Phase 1), `docs/refactor/` (coi cả thư mục là archive; điểm vào `FINAL_ACCEPTANCE_REPORT.md`).

**DELETE_CANDIDATE** (chỉ sau Human duyệt; đã kiểm ref):

| File | Ref | Mất bằng chứng? | Điều kiện |
|---|---|---|---|
| `README_boilerplate.md` | 1 (`docs/guide/anti-patterns/common-mistakes.md`, nhắc như ví dụ) | Không | HD-1: template không bắt buộc giữ |
| `docs/ai4/collaboration_chat.md` (nhánh `ai-4`) | 0, file rỗng | Không | Khi tích hợp `ai-4` |
| `prompts/system_prompt.md`, `safeguards.md`, `citation_rules.md` | `src/llm_chat/prompts.py`, `tests/test_llm_chat/test_agent_patterns.py` | Không | **Phải** đi cùng task code (bỏ `build_system_prompt` + test) — ngoài phạm vi audit |
| `eval/results/benchmark.{json,md}`, `manifest.json`, `merged-sim/` (untracked, 28 MB) | `eval/run_benchmark.py` ghi ra | Không (sinh lại được; baseline thật ở `eval/evidence/`) | Không xoá tay — Human quyết `.gitignore` (G-auto) |

## 6. Cấu trúc đề xuất — một nguồn cho mỗi loại thông tin (Progressive Disclosure)

| Loại thông tin | Nguồn chính thức duy nhất | Nạp khi |
|---|---|---|
| Quy tắc agent + invariants | `CLAUDE.md` (≤ ~2 000 token) | Mặc định (tự nạp) |
| Lối vào Codex | `AGENTS.md` (~500 token) | Mặc định cho Codex |
| Trạng thái Phase, khoá, việc tiếp | HANDOFF §0–§1 (≤ ~3 500 token) | Mặc định |
| Lịch sử checkpoint, RCA, task đã đóng | HANDOFF mục "Lịch sử" + git | Khi cần truy vết |
| Hiện trạng chức năng + bằng chứng | `docs/FEATURE_REGISTRY.md` | Khi hỏi trạng thái / sửa chức năng |
| Yêu cầu | `docs/PRD.md` | Khi làm chức năng |
| Kiến trúc, ranh giới, cây thư mục | `ARCHITECTURE.md` + `docs/architecture_diagram.md` | Khi sửa cấu trúc |
| Quyết định | `docs/adr/` + `docs/adr/README.md` (triage + quyết định Human) | Khi đụng quyết định |
| Giao tiếp với Human | `docs/communication/HUMAN_AGENT_COMMUNICATION.md` | Khi báo cáo (CLAUDE giữ ~5 dòng tóm tắt) |
| Quy tắc theo thư mục | `src/simulator/AGENTS.md`, `frontend/AGENTS.md` (ngắn) | Tự nạp theo thư mục |
| Evidence | `eval/evidence/`, `docs/handoff/*_RESULT.md`, `docs/refactor/` | Chỉ khi review |
| Template AI20K | `docs/guide/` | Không bao giờ mặc định |
| Shared Agent Skills (Phase 2) | Skill đọc các nguồn trên theo task, **không** chép nội dung | Theo skill |

**Footprint trước / sau (token ước tính):**

| Thành phần | Trước | Sau |
|---|---:|---:|
| `CLAUDE.md` | 5 300 | ~2 000 |
| `AGENTS.md` (Codex) | 500 | ~500 |
| HANDOFF §0 | 1 600 | ~1 000 |
| HANDOFF §1 | 11 000 | ~2 500 |
| **Mặc định** | **~18 400** | **~6 000** |
| + `src/simulator/AGENTS.md` khi làm ở đó | +3 400 | +~1 200 |
| + `PROJECT_CONTEXT.md` / `PROJECT_STATE.md` nếu agent theo lời file | +3 600 / +3 400 | 0 (chỉ còn dòng trỏ) |

## 7. Thứ tự thực hiện cleanup (sau khi Human duyệt)

1. Chờ X-02 xong và nhả khoá; Human quyết HD-1…HD-7 (và C-1 nếu muốn các thành viên thấy bản mới).
2. P0 sửa nguồn nguy hiểm (không xoá gì): `src/simulator/AGENTS.md`, `SIMULATOR_INTEGRATION_CONTRACT.md`, `PROJECT_CONTEXT.md` → dòng trỏ.
3. Rút gọn HANDOFF §1 (chuyển bản ghi đã đóng xuống lịch sử cùng file — không tạo file mới), rồi `CLAUDE.md`.
4. P1 / P2 UPDATE (`README`, `21-ui-spec`, `plan/40`, `50`); banner HISTORICAL cho các file ARCHIVE.
5. Gộp nguồn trạng thái (`src/simulator/docs/PROJECT_STATE.md`).
6. Khi tích hợp `ai-4`: theo §4.
7. DELETE_CANDIDATE chỉ sau duyệt riêng từng file; prompt template đi cùng task code.
8. Phase 2 (G-auto): mở rộng `scripts/check_docs.py` (hiện chỉ quét `docs/guide/`) để quét toàn repo và chặn cụm lỗi thời
   được trình bày như hiện hành; làm hàng rào cho Shared Agent Skills.

Mỗi bước: một Agent giữ khoá, review độc lập khi chạm file ACTIVE / EVIDENCE, ghi checkpoint.

## 8. Quyết định cần Human

| # | Quyết định | Phương án đề xuất |
|---|---|---|
| HD-1 | Tài liệu bắt buộc của chương trình: `PROJECT_CONTEXT.md` (C5?), `README_boilerplate.md`, `docs/guide/`, `notebooks/`, `CONTRIBUTING.md` | Xác nhận danh sách; file bắt buộc giữ nhưng thu gọn thành trỏ |
| HD-2 | Archive: banner tại chỗ hay chuyển vào `docs/archive/` | Banner tại chỗ (không vỡ ref); chỉ di chuyển file ≤ 2 ref |
| HD-3 | Cho phép sửa tài liệu đã nghiệm thu (registry — đã có H-5; PRD FR9a / FR12) | Duyệt từng lượt, có review độc lập |
| HD-4 | HANDOFF là nguồn trạng thái **duy nhất** (bỏ `PROJECT_STATE.md` simulator, `docs/ai4/PROJECT_STATE.md`) | Duyệt; ảnh hưởng quy trình Codex và người phụ trách `ai-4` |
| HD-5 | Rút gọn `CLAUDE.md` / HANDOFF theo §6 | Duyệt, làm sau X-02 |
| HD-6 | Bỏ 3 prompt template (cần sửa code + test) | Task code riêng, không gấp |
| HD-7 | `docs/research/RESEARCH-SC-16.pdf` (18 MB, nhánh `ai-4`) giữ trong repo? | Giữ nếu là tài liệu nghiên cứu gốc bắt buộc; nếu không, lưu ngoài repo + link |

## 9. Giới hạn

- Đếm ref theo tên file (có thể khớp nhầm khi tên trùng; tên chung như `README.md` dùng đường dẫn đầy đủ).
- Không đọc toàn văn mọi file: đọc header + dòng khớp cụm lỗi thời cho ~40 file nghi vấn; 50 file `docs/guide/` chỉ phân loại theo nhóm.
- Token là ước tính (ký tự ÷ 3,2); chưa đo `~/.claude/CLAUDE.md` cá nhân (ngoài repo).
- Không kiểm hiển thị mockup, không đọc DOCX / PDF.

---

# Phần II — Ownership, mục đích và đóng góp của thành viên (D-02, 2026-11-25)

- Người làm: Claude Code (`claude-opus-5-5`), chỉ đọc. Mở rộng Phần I (D-01), dùng lại inventory 192 `.md` / 417 artifact.
  Claude là agent viết phần lớn tài liệu dưới tài khoản `LufkyMama` ⇒ **không độc lập** khi đánh giá phần đó.
- Checkpoint: "Checkpoint cần đồng bộ" của D-01 (đầu file) đã chép vào HANDOFF ở lượt này. X-02 đã xong và nhả khoá trước
  khi bắt đầu.
- Đính chính Phần I / X-01: X-02 (`CROSS_BRANCH_INDEPENDENT_REVIEW.md`) chứng minh `develop` là ancestor của `unified-core`,
  nên **merge** `develop` không khôi phục code / tài liệu đã xoá. Rủi ro ở Phần I §4 chỉ còn đúng cho việc **giải xung đột
  chọn bản cũ** hoặc cherry-pick / port tay.
- Nguồn: `git log --all`, `git log --follow` và `git blame` từng tài liệu; `gh pr list` (16 PR, author, merged-by, reviewer);
  `README.md` mục Team; `WORKLOG.md`; `docs/plan/00-overview.md` §owner; mô tả PR #16; tài liệu trên ref
  `refs/audit/2026-11-25/*`. `git fetch --prune` ở lượt này đã gỡ 3 ref theo dõi của nhánh đã bị xoá trên remote
  (`origin/feature/hybrid-backend`, `origin/fix/booking-charging-state`, `origin/fix/review-issues`; đều đã merge, PR #15, #13, #12/#14) —
  không đụng working tree.
- Nhãn: **VERIFIED** (đọc trực tiếp từ git / GitHub / file), **INFERRED** (suy từ nhiều dấu hiệu), **UNVERIFIED** (chưa đủ
  bằng chứng), **PROPOSED** (đề xuất, chưa có hiệu lực). Không suy đoán động cơ cá nhân; không đánh giá năng lực theo số
  commit / dòng / tài liệu. Không ghi email.

## II.1 Định danh thành viên và tác nhân

| Thành viên (tên commit) | GitHub | Vai trò ghi nhận | Nhánh / PR | Tác nhân AI dùng | Nhãn |
|---|---|---|---|---|---|
| LufkyMama | `LufkyMama` | README Team: "Kế hoạch, kiến trúc, backend (DB, auth, Guard, optimizer, services), CI / deploy" | `feature/unified-core` (HEAD `ce23136`); PR #1, #2, #5, #8, #9, #10, #13, #15 — **tự merge cả 8**; merge mọi PR của người khác (#4, #6, #7, #12, #14) | Claude Code (nhiều phiên song song "claude2 / claude3" — `docs/refactor/FINAL_ACCEPTANCE_REPORT.md`), Codex làm reviewer độc lập (Phase 1), "Tech Lead" review trên mirror (refactor) | VERIFIED. Tài khoản này là `git config user` của workspace governance ⇒ Human Supervisor **INFERRED** là người dùng tài khoản này |
| LamBui | `lam-bui-tech` | README Team: "Frontend (màn cư dân / vận hành), hook ghi log AI" | `feature/be-fe-integration` (PR #16 **OPEN**), PR #4 (merged), #3 (closed) | Claude Code: 8 commit có trailer `Co-Authored-By: Claude Haiku 5.5`; thân PR #16 ghi "Generated with Claude Code" | VERIFIED |
| Le Hien Hieu ("Hieu") | `hieulhaiwork` | README Team: "Simulator R&D (HybridSimulator, EV2Gym), optimizer AC / DC MVP-2 / 3" | PR #7 (merged); `feature/ai-4` (`4658b1f`, **chưa có PR**) | `src/simulator/AGENTS.md` (Hieu viết) quy định Codex là agent và "**Tech Lead (ChatGPT)**" do người dùng chuyển lời; `docs/ai4/*` ghi review "Tech Lead" trên mirror không có trong repo | Quy định VERIFIED; việc dùng thực tế trên `ai-4` INFERRED |
| HaiVuu | `HaiVuuu` | README Team: "Agent F1 (LangGraph, streaming chat), eval Agent" | PR #6, #12, #14 (merged), #11 (closed); không có nhánh hoạt động sau 22/11 trên `origin` | UNVERIFIED | VERIFIED vai trò; hoạt động sau 22/11 UNVERIFIED |
| `phoenix-mentor[bot]` | — | Template AI20K (commit `71011d6`, 05/11) | `main` | — | VERIFIED |

**Phát hiện về vai trò (VERIFIED):** chữ "Tech Lead" mang ba nghĩa khác nhau trong repo — Codex (`docs/handoff/REVIEW_PHASE1.md`
§6), ChatGPT do người dùng chuyển lời (`src/simulator/AGENTS.md:10`, `docs/ai4/*`), và reviewer trên mirror trong
`docs/refactor/*`. Các nhãn "APPROVED bởi Tech Lead" (`docs/ai4/ADR_AI4_SCOPE.md`, `PROJECT_STATE.md`, refactor) là **review
của AI**, không phải phê duyệt của Human Supervisor; không SHA mirror nào có trong repo (X-01 X-AI4-03).
**Không có PR nào có review của con người**: reviewer duy nhất là `copilot-pull-request-reviewer` (PR #3, #4, #16).
`PRD.md` v0.4 vẫn ghi "Bản nháp chờ nhóm + mentor duyệt".

## II.2 Ownership inventory (bổ sung cho bảng Phần I §2)

"Tác giả gốc" = commit tạo file (`git log --follow`); "Trách nhiệm duy trì" là **PROPOSED** trừ khi ghi khác — không có tài
liệu phân công nào nêu owner theo file. Tài liệu untracked do agent viết trong workspace theo giao việc của Human (HANDOFF §1.11).

| Đường dẫn | Commit đầu → cuối (tác giả) | Tác giả gốc | Contributors (số commit) | Trách nhiệm duy trì | Feature / task | Loại mục đích | Audience | Thẩm quyền |
|---|---|---|---|---|---|---|---|---|
| `.agents/rules/ai-log-hook.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | Chương trình AI20K (template; `docs/guide` = Technical Book, book-maintainers) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `.agents/workflows/log.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | Chương trình AI20K (template; `docs/guide` = Technical Book, book-maintainers) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `.github/PULL_REQUEST_TEMPLATE.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `AGENTS.md` | untracked (workspace, `feature/unified-core`) | Claude Code (TK LufkyMama), 24/11 | Human giao việc; agent viết | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | AGENT_INSTRUCTION | Agent | Tham khảo |
| `ARCHITECTURE.md` | `71011d6` 2026-11-05 → 2026-11-23 (LufkyMama) | Template AI20K (`phoenix-mentor[bot]`) | LufkyMama 7, bot 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | kiến trúc | ARCHITECTURE | Dev + Agent | Tham khảo |
| `CLAUDE.md` | `71011d6` 2026-11-05 → 2026-11-24 (LufkyMama) | Template AI20K (`phoenix-mentor[bot]`) | LufkyMama 11, bot 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | AGENT_INSTRUCTION | Agent | Nguồn chính thức: quy tắc agent |
| `CODE_OF_CONDUCT.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | Chương trình AI20K (template; `docs/guide` = Technical Book, book-maintainers) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `CONTRIBUTING.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | Chương trình AI20K (template; `docs/guide` = Technical Book, book-maintainers) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `JOURNAL.md` | `71011d6` 2026-11-05 → 2026-11-22 (LufkyMama) | Template AI20K (`phoenix-mentor[bot]`) | LufkyMama 1, bot 1 | Cả nhóm; người cập nhật hiện tại LufkyMama (VERIFIED git) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `PROJECT_CONTEXT.md` | `71011d6` 2026-11-05 → 2026-11-24 (LufkyMama) | Template AI20K (`phoenix-mentor[bot]`) | LufkyMama 5, Hieu 1, bot 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | HANDOFF | Agent + Human | **Cạnh tranh** với HANDOFF |
| `README.md` | `71011d6` 2026-11-05 → 2026-11-24 (LufkyMama) | Template AI20K (`phoenix-mentor[bot]`) | LufkyMama 4, bot 1 | Cả nhóm; người cập nhật hiện tại LufkyMama (VERIFIED git) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `README_boilerplate.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | Chương trình AI20K (template; `docs/guide` = Technical Book, book-maintainers) | — | NO_CLEAR_PURPOSE | — | Tham khảo |
| `SECURITY.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | Chương trình AI20K (template; `docs/guide` = Technical Book, book-maintainers) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `WORKLOG.md` | `71011d6` 2026-11-05 → 2026-11-22 (LufkyMama) | Template AI20K (`phoenix-mentor[bot]`) | LufkyMama 1, bot 1 | Cả nhóm; người cập nhật hiện tại LufkyMama (VERIFIED git) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `docs/FEATURE_REGISTRY.md` | untracked (workspace, `feature/unified-core`) | Claude Code, 24–25/11 | Human giao việc; agent viết | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | mọi F | HUMAN_REPORT | Human | Nguồn chính thức: hiện trạng |
| `docs/PRD.md` | `a90f5cd` 2026-11-21 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 3 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | mọi F | REQUIREMENT | Human + Dev | Nguồn chính thức: yêu cầu (bản nháp v0.4) |
| `docs/adr/ADR-001-giu-langgraph-cho-f1.md` | `3228cfa` 2026-11-17 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 2 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-002-guard-chokepoint.md` | `3228cfa` 2026-11-17 → 2026-11-22 (LufkyMama) | LufkyMama | LufkyMama 3 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | F4 | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-003-tham-so-trong-config.md` | `3228cfa` 2026-11-17 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 2 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-004-contract-first-501.md` | `3228cfa` 2026-11-17 → 2026-11-17 (LufkyMama) | LufkyMama | LufkyMama 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-005-persistence-sqlalchemy-alembic.md` | `3228cfa` 2026-11-17 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 2 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-006-danh-tinh-jwt-resident-id-server-side.md` | `3228cfa` 2026-11-17 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 2 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | FR1 | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-007-station-runtime-va-control-loop.md` | `3228cfa` 2026-11-17 → 2026-11-22 (LufkyMama) | LufkyMama | LufkyMama 3 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-008-quy-uoc-api.md` | `3228cfa` 2026-11-17 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 2 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-009-frontend-nextjs.md` | `3228cfa` 2026-11-17 → 2026-11-17 (LufkyMama) | LufkyMama | LufkyMama 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | F5, FR17–18 | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-010-bai-hybrid-ac-dc.md` | `2d290b7` 2026-11-19 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 2 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | Q2 bãi | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-011-mot-simulator-sau-be-mat-cong-khai.md` | `e2df690` 2026-11-21 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 3 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-012-mot-danh-muc-xe-va-kich-ban.md` | `e2df690` 2026-11-21 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-013-workflow-xac-dinh-llm-hai-dau.md` | `e2df690` 2026-11-21 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | Lớp LLM | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-014-decision-trace-counterfactual-hitl.md` | `e2df690` 2026-11-21 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | F6–F8 | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-015-pham-vi-mvp4-va-quy-tac-bang-chung.md` | `e2df690` 2026-11-21 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | phạm vi | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-016-livestation-cho-backend.md` | `e26655c` 2026-11-22 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 3 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-017-guard-theo-hop-dong-an-toan-simulator.md` | `1e8f43f` 2026-11-23 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 2 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | F4 | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-018-backend-chay-engine-simulator.md` | `098877a` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 3 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | F2, Q3 | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/ADR-019-unified-core-hop-dong-dung-chung.md` | `e6037f4` 2026-11-23 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 7 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | Unified Core | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/adr/README.md` | `3228cfa` 2026-11-17 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 7 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | DECISION | Human + Dev | Nguồn chính thức: quyết định |
| `docs/architecture_diagram.md` | `71011d6` 2026-11-05 → 2026-11-23 (LufkyMama) | Template AI20K (`phoenix-mentor[bot]`) | LufkyMama 5, bot 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | kiến trúc | ARCHITECTURE | Dev + Agent | Tham khảo |
| `docs/business-overview.md` | `a90f5cd` 2026-11-21 → 2026-11-22 (LufkyMama) | LufkyMama | LufkyMama 2 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | REQUIREMENT | Human + Dev | Tham khảo |
| `docs/communication/HUMAN_AGENT_COMMUNICATION.md` | untracked (workspace, `feature/unified-core`) | Claude Code, 24/11 | Human giao việc; agent viết | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | Governance | AGENT_INSTRUCTION | Agent | Tham khảo |
| `docs/communication/RESPONSE_TEST_CASES.md` | untracked (workspace, `feature/unified-core`) | Claude Code, 24/11 | Human giao việc; agent viết | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | Governance | AGENT_INSTRUCTION | Agent | Tham khảo |
| `docs/design/kien-truc-tra-loi-3-tang.md` | `a90f5cd` 2026-11-21 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | ARCHITECTURE | Dev + Agent | Tham khảo |
| `docs/handoff/AUDIT_BACKEND_SIMULATOR_ALIGNMENT.md` | untracked (workspace, `feature/unified-core`) | Claude Code, 24/11 | Human giao việc; agent viết | Không cần owner (EVIDENCE / báo cáo đóng) | Governance P1 | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/handoff/CROSS_BRANCH_ALIGNMENT_AUDIT.md` | untracked (workspace, `feature/unified-core`) | Claude Code, 25/11 | Human giao việc; agent viết | Không cần owner (EVIDENCE / báo cáo đóng) | Governance P1 | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/handoff/HANDOFF.md` | `3228cfa` 2026-11-17 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 11 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | Governance P1 | HANDOFF | Agent + Human | Nguồn chính thức: trạng thái |
| `docs/handoff/REMEDIATION_PHASE1.md` | untracked (workspace, `feature/unified-core`) | Claude Code, 25/11 | Human giao việc; agent viết | Không cần owner (EVIDENCE / báo cáo đóng) | Governance P1 | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/handoff/REREVIEW_PHASE1_RESULT.md` | untracked (workspace, `feature/unified-core`) | Codex, 25/11 | Human giao việc; agent viết | Không cần owner (EVIDENCE / báo cáo đóng) | Governance P1 | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/handoff/REVIEW_PHASE1.md` | untracked (workspace, `feature/unified-core`) | Claude Code, 24/11 | Human giao việc; agent viết | Không cần owner (EVIDENCE / báo cáo đóng) | Governance P1 | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/handoff/REVIEW_PHASE1_RESULT.md` | untracked (workspace, `feature/unified-core`) | Codex, 24/11 | Human giao việc; agent viết | Không cần owner (EVIDENCE / báo cáo đóng) | Governance P1 | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/mockups/cu-dan/HUONG-DAN.md` | `2d290b7` 2026-11-19 → 2026-11-19 (LufkyMama) | LufkyMama | LufkyMama 2 | LamBui (đề xuất; Frontend theo README Team) — tác giả gốc LufkyMama | F5 | HISTORICAL_RECORD | Truy vết | Bằng chứng / tham khảo |
| `docs/mockups/van-hanh/HUONG-DAN.md` | `5cf00bf` 2026-11-19 → 2026-11-19 (LufkyMama) | LufkyMama | LufkyMama 1 | LamBui (đề xuất; Frontend theo README Team) — tác giả gốc LufkyMama | F5 | HISTORICAL_RECORD | Truy vết | Bằng chứng / tham khảo |
| `docs/plan/00-overview.md` | `3228cfa` 2026-11-17 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 6 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | T1.x–T4.x | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/plan/10-backend.md` | `3228cfa` 2026-11-17 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 4 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | T1.x–T4.x | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/plan/20-frontend.md` | `3228cfa` 2026-11-17 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 3 | LamBui (đề xuất; Frontend theo README Team) — tác giả gốc LufkyMama | F5, FR17–18 | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/plan/21-ui-spec.md` | `f10d596` 2026-11-17 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 6 | LamBui (đề xuất; Frontend theo README Team) — tác giả gốc LufkyMama | F5 | REQUIREMENT | Human + Dev | Tham khảo |
| `docs/plan/22-ui-work-split.md` | `104293a` 2026-11-17 → 2026-11-21 (LufkyMama) | LufkyMama | LufkyMama 4 | LamBui (đề xuất; Frontend theo README Team) — tác giả gốc LufkyMama | F5 | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/plan/30-ai.md` | `3228cfa` 2026-11-17 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 6 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | T1.x–T4.x | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/plan/40-database.md` | `3228cfa` 2026-11-17 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 3 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | T1.x–T4.x | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/plan/50-devops.md` | `3228cfa` 2026-11-17 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 4 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | T1.x–T4.x | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/plan/55-ci-runner.md` | `cb81cb2` 2026-11-17 → 2026-11-17 (LufkyMama) | LufkyMama | LufkyMama 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | T1.x–T4.x | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/plan/56-deploy-render-image.md` | `7147cc6` 2026-11-22 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 4 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | T1.x–T4.x | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/refactor/BASELINE.md` | `dad6e6b` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 2 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/DELETION_MANIFEST.md` | `4139ab9` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 6 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/EXPECTED_FAILURES.md` | `ddab921` 2026-11-23 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 3 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/FINAL_ACCEPTANCE_A_REPORT.md` | `13f25ff` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/FINAL_ACCEPTANCE_B_REPORT.md` | `5ba797b` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/FINAL_ACCEPTANCE_REPORT.md` | `ce23136` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/FINAL_MAP.md` | `6f8b7e4` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 3 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | ARCHITECTURE | Dev + Agent | Tham khảo |
| `docs/refactor/FINAL_REVIEW_FIX_A_REPORT.md` | `eef9e8b` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/FINAL_REVIEW_FIX_B_REPORT.md` | `6332c05` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/FINAL_REVIEW_FIX_REPORT.md` | `3e47d13` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/IMPORT_GRAPH.md` | `dad6e6b` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 2 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/LLMCHAT_REPORT.md` | `0f425a5` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/MODULE_PROVENANCE.md` | `dad6e6b` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/PHASE0_FINDINGS.md` | `dad6e6b` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/PHASE1_REPORT.md` | `e6037f4` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 2 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/PHASE2_REPORT.md` | `6e61acd` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/PHASE3_DESIGN.md` | `27beea9` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/refactor/PHASE3_REPORT.md` | `ddab921` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/PHASE4_P4-API_REPORT.md` | `e76fefb` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/PHASE4_P4-CORE_REPORT.md` | `90f79c2` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/PLAN.md` | `749c042` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/refactor/REFACTOR_REPORT.md` | `6f8b7e4` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 3 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/TECHLEAD_PHASE4_DECISIONS.md` | `70d0eaf` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `docs/refactor/tasks/FINAL_ACCEPTANCE_PATCH_BRIEF.md` | `6d99661` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/refactor/tasks/FINAL_REVIEW_FIX_BRIEF.md` | `7294803` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/refactor/tasks/LLMCHAT_BRIEF.md` | `749c042` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/refactor/tasks/PHASE3_BRIEF.md` | `749c042` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/refactor/tasks/PHASE4_BRIEF.md` | `70d0eaf` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `docs/refactor/tasks/PHASE4_FINAL_BRIEF.md` | `3db3b98` 2026-11-24 → 2026-11-24 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | IMPLEMENTATION_PLAN | Dev (lịch sử) | Tham khảo |
| `eval/README.md` | `71011d6` 2026-11-05 → 2026-11-23 (LufkyMama) | Template AI20K (`phoenix-mentor[bot]`) | LufkyMama 3, bot 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | ARCHITECTURE | Dev + Agent | Tham khảo |
| `eval/results/archive/2026-11-22-pre-refactor/README.md` | `eaf8842` 2026-11-23 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 1 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | HISTORICAL_RECORD | Truy vết | Bằng chứng / tham khảo |
| `eval/results/archive/2026-11-22-pre-refactor/benchmark.md` | `e26655c` 2026-11-22 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 3 | Không cần owner cá nhân (EVIDENCE, bất biến) | Unified Core | HISTORICAL_RECORD | Truy vết | Bằng chứng / tham khảo |
| `eval/results/benchmark.md` | untracked (workspace, `feature/unified-core`) | `eval/run_benchmark.py` (sinh) | Human giao việc; agent viết | Không (GENERATED) | — | GENERATED_ARTIFACT | Công cụ | Tham khảo |
| `eval/results/report.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | UNASSIGNED (deliverable chưa có người nhận) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `frontend/AGENTS.md` | `3228cfa` 2026-11-17 → 2026-11-17 (LufkyMama) | LufkyMama | LufkyMama 1 | LamBui (đề xuất; Frontend theo README Team) — tác giả gốc LufkyMama | F5, FR17–18 | AGENT_INSTRUCTION | Agent | Tham khảo |
| `frontend/README.md` | `3228cfa` 2026-11-17 → 2026-11-17 (LufkyMama) | LufkyMama | LufkyMama 1 | LamBui (đề xuất; Frontend theo README Team) — tác giả gốc LufkyMama | F5, FR17–18 | ARCHITECTURE | Dev + Agent | Tham khảo |
| `notebooks/README.md` | `3228cfa` 2026-11-17 → 2026-11-17 (LufkyMama) | LufkyMama | LufkyMama 1 | Chương trình AI20K (template; `docs/guide` = Technical Book, book-maintainers) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `presentation/README.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | UNASSIGNED (deliverable chưa có người nhận) | — | PROGRAM_DELIVERABLE | AI20K / BTC | Tham khảo |
| `prompts/README.md` | `71011d6` 2026-11-05 → 2026-11-23 (LufkyMama) | Template AI20K (`phoenix-mentor[bot]`) | LufkyMama 2, bot 1 | HaiVuu (đề xuất; Agent F1 theo README Team) | F1, FR4, FR31–33 | AGENT_INSTRUCTION | Agent | Tham khảo |
| `prompts/charging_domain.md` | `3228cfa` 2026-11-17 → 2026-11-23 (LufkyMama) | LufkyMama | LufkyMama 2, HaiVuu 1 | HaiVuu (đề xuất; Agent F1 theo README Team) | F1, FR4, FR31–33 | AGENT_INSTRUCTION | Agent | Tham khảo |
| `prompts/charging_safeguards.md` | `3228cfa` 2026-11-17 → 2026-11-17 (LufkyMama) | LufkyMama | LufkyMama 1 | HaiVuu (đề xuất; Agent F1 theo README Team) | F1, FR4, FR31–33 | AGENT_INSTRUCTION | Agent | Tham khảo |
| `prompts/citation_rules.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | UNASSIGNED (template, code phải bỏ cùng) | F1, FR4, FR31–33 | NO_CLEAR_PURPOSE | — | Tham khảo |
| `prompts/finalize.md` | `3228cfa` 2026-11-17 → 2026-11-21 (HaiVuu) | LufkyMama | HaiVuu 3, LufkyMama 1 | HaiVuu (đề xuất; Agent F1 theo README Team) | F1, FR4, FR31–33 | AGENT_INSTRUCTION | Agent | Tham khảo |
| `prompts/reason.md` | `3228cfa` 2026-11-17 → 2026-11-21 (HaiVuu) | LufkyMama | HaiVuu 3, LufkyMama 1 | HaiVuu (đề xuất; Agent F1 theo README Team) | F1, FR4, FR31–33 | AGENT_INSTRUCTION | Agent | Tham khảo |
| `prompts/safeguards.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | UNASSIGNED (template, code phải bỏ cùng) | F1, FR4, FR31–33 | NO_CLEAR_PURPOSE | — | Tham khảo |
| `prompts/system_prompt.md` | `71011d6` 2026-11-05 → 2026-11-05 (AI20K-bot) | Template AI20K (`phoenix-mentor[bot]`) | bot 1 | UNASSIGNED (template, code phải bỏ cùng) | F1, FR4, FR31–33 | NO_CLEAR_PURPOSE | — | Tham khảo |
| `src/forecast/artifacts/README.md` | `3228cfa` 2026-11-17 → 2026-11-17 (LufkyMama) | LufkyMama | LufkyMama 1 | Human Supervisor duyệt; maintainer: agent governance được giao (đề xuất) | — | ARCHITECTURE | Dev + Agent | Tham khảo |
| `src/simulator/AGENTS.md` | `2fdc78c` 2026-11-19 → 2026-11-22 (LufkyMama) | Hieu | LufkyMama 1, Hieu 2 | Hieu (đề xuất; tác giả module, README Team) | F2, FR5–FR12 (simulator / optimizer gốc) | AGENT_INSTRUCTION | Agent | Tham khảo |
| `src/simulator/README.md` | `f7e6e54` 2026-11-19 → 2026-11-23 (LufkyMama) | Hieu | LufkyMama 1, Hieu 6 | Hieu (đề xuất; tác giả module, README Team) | F2, FR5–FR12 (simulator / optimizer gốc) | ARCHITECTURE | Dev + Agent | Tham khảo |
| `src/simulator/docs/DESIGN_DECISIONS.md` | `6bcd45b` 2026-11-19 → 2026-11-21 (Hieu) | Hieu | Hieu 2 | Hieu (đề xuất; tác giả module, README Team) | F2, FR5–FR12 (simulator / optimizer gốc) | ARCHITECTURE | Dev + Agent | Tham khảo |
| `src/simulator/docs/MVP2_BENCHMARK.md` | `781c3f0` 2026-11-21 → 2026-11-21 (Hieu) | Hieu | Hieu 1 | Hieu (đề xuất; tác giả module, README Team) | F2, FR5–FR12 (simulator / optimizer gốc) | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `src/simulator/docs/MVP3_BENCHMARK.md` | `8c4c14e` 2026-11-21 → 2026-11-21 (Hieu) | Hieu | Hieu 1 | Hieu (đề xuất; tác giả module, README Team) | F2, FR5–FR12 (simulator / optimizer gốc) | VALIDATION_EVIDENCE | Reviewer | Bằng chứng / tham khảo |
| `src/simulator/docs/PROJECT_STATE.md` | `2fdc78c` 2026-11-19 → 2026-11-24 (LufkyMama) | Hieu | LufkyMama 2, Hieu 6 | Hieu (đề xuất; tác giả module, README Team) | F2, FR5–FR12 (simulator / optimizer gốc) | HANDOFF | Agent + Human | **Cạnh tranh** với HANDOFF |
| `src/simulator/docs/SIMULATOR_INTEGRATION_CONTRACT.md` | `ff5a6aa` 2026-11-21 → 2026-11-23 (LufkyMama) | Hieu | LufkyMama 3, Hieu 1 | Hieu (đề xuất; tác giả module, README Team) | F2, FR5–FR12 (simulator / optimizer gốc) | ARCHITECTURE | Dev + Agent | Tham khảo |

| Nhóm | Số file | Loại mục đích | Tác giả gốc | Trách nhiệm |
|---|---|---|---|---|
| `docs/guide/` | 50 | PROGRAM_DELIVERABLE | Template AI20K | Chương trình AI20K |
| `docs/refactor/` | 6 | VALIDATION_EVIDENCE | LufkyMama (agent Claude / Codex, theo báo cáo trong thư mục); 2 file HaiVuu (`2026-11-22`) | Không cần owner (EVIDENCE) |
| `eval/evidence/` | 22 | VALIDATION_EVIDENCE | LufkyMama (agent Claude / Codex, theo báo cáo trong thư mục); 2 file HaiVuu (`2026-11-22`) | Không cần owner (EVIDENCE) |

**Tổng hợp loại mục đích (192 `.md`):** PROGRAM_DELIVERABLE 62 (50 là Technical Book `docs/guide/` — PR template ghi nội dung
này đồng bộ lên trang Technical Book của chương trình và cần book-maintainers duyệt) · VALIDATION_EVIDENCE 56 · DECISION 20 ·
IMPLEMENTATION_PLAN 17 · AGENT_INSTRUCTION 11 · ARCHITECTURE 10 · HISTORICAL_RECORD 4 · NO_CLEAR_PURPOSE 4 · HANDOFF 3 ·
REQUIREMENT 3 · HUMAN_REPORT 1 · GENERATED_ARTIFACT 1.

**Tác giả gốc (tracked, 181 file):** LufkyMama 101 · template AI20K 71 (11 đã được nhóm sửa) · Hieu 7 · HaiVuu 2 · LamBui 0.
11 file untracked do Claude Code / Codex viết trong phiên governance. Nhánh `feature/ai-4` thêm 10 file `docs/ai4/` (Hieu) và
516 file evidence; `feature/be-fe-integration` không thêm tài liệu.

## II.3 Từng thành viên: làm gì, vì sao, tài liệu, giá trị, phạm vi

### LufkyMama (kiêm tài khoản của Human Supervisor — INFERRED)

| Câu hỏi | Trả lời | Nhãn |
|---|---|---|
| Được giao gì | Kế hoạch, kiến trúc, backend, CI / deploy (README Team); thực tế còn làm PRD v0.4, ADR-010…019, refactor Unified Core, governance Phase 1 | VERIFIED |
| Vì sao cần | PRD / ADR: căn chỉnh hướng nghiên cứu SC-16 (PR #5 "bãi hybrid AC/DC theo ADR-010 + ADR-011…015, PRD v0.4"); Unified Core: backend và simulator lệch nhau (`docs/refactor/PHASE0_FINDINGS.md`); governance: Human mất khả năng kiểm soát hệ thống (HANDOFF §1.1) | VERIFIED (lý do ghi trong tài liệu) |
| Tài liệu | 101 tracked: 20 / 20 ADR, PRD, `business-overview`, `docs/plan/*`, `docs/refactor/*` (35 md + 224 raw), mockup guides, `eval/evidence/2026-11-2x*` (trừ 2 file HaiVuu); 11 untracked governance | VERIFIED (git); phần lớn do agent viết — VERIFIED cho refactor / governance (báo cáo ghi tên agent), INFERRED cho phần còn lại |
| Vì sao tạo file mới | Refactor: mỗi phase một báo cáo + brief giao cho agent song song (A / B); governance: Human yêu cầu file kết quả riêng cho review độc lập (HANDOFF §0) | VERIFIED |
| Kỹ thuật | Contract-first (ADR-004), Guard chokepoint (ADR-002), một `StationKernel` dùng chung (ADR-019), LP HiGHS receding horizon (từ MVP của Hieu) | VERIFIED |
| Implementation / bằng chứng | `src/` backend; frozen baseline `eval/evidence/2026-11-24-unified-core-frozen-baseline/`; 604 + 180 test @ `ce23136`; Phase 1 Technical Acceptance PASS | VERIFIED |
| Giá trị thực | Backend chạy thật + bản test đã deploy (`docs/plan/56`); một kernel cho live / benchmark / what-if; kiểm soát governance | VERIFIED |
| Lệch / trùng | Tự merge 8 / 8 PR của mình, không review người; 2 dòng lỗi thời nguy hiểm nhất (`LiveStation`) trong `src/simulator/AGENTS.md:50` và `SIMULATOR_INTEGRATION_CONTRACT.md:10` do commit `c801084` (22/11) của tài khoản này chèn và chưa sửa sau refactor; sửa nhiều tài liệu của module simulator (32 commit `src/simulator` vs 14 của Hieu); PRD v0.4 chưa được duyệt | VERIFIED |
| Còn cần không | ACTIVE: CLAUDE, ARCHITECTURE, PRD, ADR, registry, HANDOFF; HISTORICAL: plan, refactor | PROPOSED |

### Hieu (Le Hien Hieu)

| Câu hỏi | Trả lời | Nhãn |
|---|---|---|
| Được giao gì | Simulator R&D, optimizer AC / DC MVP-2 / 3 (README Team); nghiên cứu nền "master context v1.0 của Hiếu" là nguồn của PRD v0.4 (`docs/plan/00-overview.md:17`, `business-overview.md` header; file không có trong repo); AI-4 trên `feature/ai-4` | VERIFIED vai trò; ai giao AI-4 UNVERIFIED (ADR_AI4_SCOPE ghi "Approved tại G0" bởi Tech Lead AI) |
| Vì sao cần | Simulator là "gốc" của thuật toán (ADR-018 / 019); AI-4 là tính năng AI trục chính (PRD F8; Human Q1 25/11 ưu tiên WHY) | VERIFIED |
| Tài liệu | 7 tracked trong `src/simulator/` (`AGENTS.md`, `README.md`, `docs/{DESIGN_DECISIONS,MVP2_BENCHMARK,MVP3_BENCHMARK,PROJECT_STATE,SIMULATOR_INTEGRATION_CONTRACT}.md`); trên `ai-4`: 10 file `docs/ai4/` + 516 evidence + PDF research 18 MB | VERIFIED |
| Vì sao tạo file mới | `SIMULATOR_INTEGRATION_CONTRACT.md`: commit `ff5a6aa` "Upload integration guide for Claude backend" (hướng dẫn cho người làm backend); `docs/ai4/ADR_AI4_SCOPE.md`: "ghi ADR bổ sung … không âm thầm sửa lịch sử" (Master Plan §0); `PROJECT_STATE.md`: handoff giữa các phiên Codex | VERIFIED (lý do ghi trong file / commit) |
| Kỹ thuật | EV2Gym hybrid, LP AC / DC + Coordinator `fixed_share` / `dynamic_slack`; AI-4: WHY deterministic, không LLM, evidence ref + `ActorContext` | VERIFIED |
| Implementation / bằng chứng | Thuật toán MVP-1/2/3 nay ở `src/optimizer/` + `src/simulator/core/` (registry B0–M3b đóng băng, "chỉ di chuyển" — CLAUDE.md); `ai-4`: 864 test đạt (X-01), X-02: G1 / G2 **CHANGES_REQUIRED** (S02, S03, W01) | VERIFIED |
| Giá trị thực | Thuật toán đang chạy trong backend; phát hiện lỗi an toàn có thật ở baseline (bản sao báo giá cấp 33 kW cho xe bị giữ an toàn — X-01 + X-02 tái hiện) | VERIFIED |
| Lệch / trùng | `ai-4` sửa lõi an toàn đóng băng (thuộc phần LufkyMama dựng); phạm vi WHAT-IF / HOW-TO vượt Q1; nguồn trạng thái riêng (`PROJECT_STATE.md` ×2) và backlog riêng (`ISSUES.md` R01–R11) trùng R-1…R-6 | VERIFIED |
| Còn cần không | Simulator docs ACTIVE (cần sửa dòng lỗi thời — do người khác chèn); `docs/ai4/` khi tích hợp: gộp theo Phần I §4 | PROPOSED |

### LamBui

| Câu hỏi | Trả lời | Nhãn |
|---|---|---|
| Được giao gì | Frontend màn cư dân / vận hành, hook ghi log AI (README Team, WORKLOG); nối BE ↔ FE 24 hạng mục G1–G24 (PR #16) | VERIFIED |
| Vì sao cần | Mô tả PR #16: FE cần các contract BE còn thiếu (đổi lịch, phê duyệt, sơ đồ bãi, tầng công suất, chat resume) | VERIFIED (lý do ghi trong PR) |
| Tài liệu | **Không** có `.md` nào trong repo. PR #16 dẫn plan `docs/superpowers/plans/2026-11-23-be-fe-implementation.md` — **không có** trong bất kỳ ref nào | VERIFIED vắng; nội dung plan UNVERIFIED |
| Kỹ thuật | Next.js + OpenAPI typed client; WS riêng từng cư dân; Claude Code (Haiku) sinh phần lớn PR | VERIFIED |
| Implementation / bằng chứng | 15 commit `frontend/src` trên các nhánh; `be-fe`: 623 test backend + 44 test FE đạt trên nền cũ; X-01 / X-02: **NOT_READY** (nền trước Unified Core, contract lệch, phát WS trong vòng quyết định, nguy cơ mất Safety Hold khi giải xung đột) | VERIFIED |
| Giá trị thực | Màn hình vận hành / cư dân, sơ đồ bãi có kiểm quyền riêng tư; contract G1–G24 dùng lại được khi port | VERIFIED |
| Lệch / trùng | Sửa backend lõi (`control_loop`, `dispatcher`, `charging_service`) ngoài phạm vi "frontend"; FE S8 còn A–D; frontend cũng do LufkyMama sửa song song (23 commit `frontend/src`) | VERIFIED |
| Còn cần không | Plan G1–G24 nên đưa vào repo hoặc mô tả trong PR là nguồn duy nhất | PROPOSED |

### HaiVuu

| Câu hỏi | Trả lời | Nhãn |
|---|---|---|
| Được giao gì | Agent F1 (LangGraph, streaming chat), eval Agent (README Team) | VERIFIED |
| Vì sao cần | F1 là đầu vào mọi quyết định (PRD F1); eval là bằng chứng MT9 | VERIFIED (PRD) |
| Tài liệu | 2 file `eval/evidence/2026-11-22/{AGENT_MANUAL_EVAL,SIMULATOR_EVAL_EVIDENCE}.md` (+ 2 DOCX); sửa `prompts/reason.md`, `finalize.md` (3 commit mỗi file), `charging_domain.md` | VERIFIED |
| Vì sao tạo file mới | Commit `39bc5ba` "simulator hardware eval evidence (ADR-015)" — quy tắc bằng chứng của ADR-015 đòi file evidence | VERIFIED |
| Implementation / bằng chứng | Streaming SSE, gợi ý trả lời, prompt bãi hybrid (PR #6); sửa review Agent / DB (PR #12); code chat nay ở `src/llm_chat/` sau refactor (người đổi tên: LufkyMama) | VERIFIED |
| Giá trị thực | Chat F1 chạy với LLM giả / offline; đánh giá thủ công có bằng chứng | VERIFIED; với LLM thật **chưa** (MT9 chưa đo) |
| Lệch / trùng | Không thấy lệch. Hai commit message "update" / "test" không mô tả được nội dung | VERIFIED |
| Hiện đang làm gì | Không có nhánh / PR sau 22/11 trên `origin` | UNVERIFIED (có thể làm ở local) |

## II.4 Yêu cầu → thành viên → tài liệu → code → test

| Yêu cầu | Thành viên (bằng chứng) | Tài liệu chính | Code | Test | Trạng thái (registry) |
|---|---|---|---|---|---|
| F1 / FR1–FR4 tiếp nhận | HaiVuu (agent, eval), LufkyMama (service, rename) | PRD §6.2, `prompts/*`, `eval/evidence/2026-11-22/AGENT_MANUAL_EVAL.md` | `src/llm_chat/`, `src/services/charging_service.py`, `energy.py` | `tests/test_llm_chat/*`, `test_api/test_flows.py` | Tested (MOCK) |
| F2 / FR5–FR9 tối ưu | Hieu (thuật toán gốc), LufkyMama (tích hợp, refactor) | ADR-010 / 018 / 019, `src/simulator/docs/*` | `src/optimizer/`, `src/simulator/core/` | `src/simulator/tests/*`, `tests/test_refactor/*` | Tested |
| F3 / FR10–FR12 | LufkyMama; Hieu (simulator) | ADR-019, `architecture_diagram` luồng B / C | `control_loop.py`, `hybrid_station.py` | `test_replan_events.py`, `test_strict_incidents.py` | Tested |
| F4 / FR13–FR16 Guard | LufkyMama; **Hieu sửa trên `ai-4`** | ADR-002 / 017, `docs/ai4/FOUNDATION_CONTRACT.md` (nhánh) | `src/guard/` | `tests/test_guard/*`, `test_failsafe_after_apply.py` | Tested; lỗi baseline R01 đã tái hiện |
| F5 / FR17–FR18 web | LamBui, LufkyMama | `docs/plan/21-ui-spec.md`, mockups | `frontend/src/app/*` | `frontend/src/test/*` | MỘT PHẦN; `be-fe` NOT_READY |
| F6 / FR19–FR21 trace, sandbox | LufkyMama; Hieu (`ai-4` v2 trace) | ADR-014, FOUNDATION_CONTRACT (nhánh) | `decision_trace.py`, `admission.py` | `test_decision_trace.py`, `test_fork_isolation.py` | MỘT PHẦN |
| F7 AI-1 | — (DEFERRED, Q1) | PRD §6.8, ADR-014 | — | — | ĐANG HOÃN |
| F8 AI-4 | Hieu (`ai-4`) | `docs/ai4/*` (nhánh) | `src/services/copilot/*` (nhánh) | `test_why_*.py` (nhánh) | Implemented + Tested trên nhánh; CHANGES_REQUIRED |
| F9 benchmark | LufkyMama; HaiVuu (evidence 22/11) | `eval/README.md`, frozen baseline | `simulation_service.py`, `eval/run_benchmark.py` | `test_config_parity.py` | Tested; chỉ regression |
| Lớp LLM / MT9 | HaiVuu (eval), LufkyMama (guardrail) | `eval/results/report.md` (**còn mẫu template, không owner**) | `guardrails.py`, `mock_llm.py` | `test_agent_modes.py` | Chưa đo LLM thật |
| Governance | LufkyMama (Human), Claude Code (viết), Codex (review) | HANDOFF, registry, HACP, review / remediation | — | — | Technical Acceptance PASS |

## II.5 Responsibility matrix

R = làm · A = chịu trách nhiệm cuối · C = tham vấn · I = được báo. "Hiện tại" chỉ ghi khi có bằng chứng git / PR / README;
"Đề xuất" là PROPOSED, **không có hiệu lực** tới khi Human duyệt.

| Nhóm chức năng | Hiện tại (bằng chứng) | Đề xuất R / A / C | Vấn đề |
|---|---|---|---|
| Unified Core (kernel, registry) | LufkyMama + agent (refactor), Hieu (code gốc) | R: LufkyMama · A: Human · C: Hieu | Đóng băng; nhưng `ai-4` sửa `hybrid_station` / runtime |
| AC / DC Optimizer | Hieu (MVP-2/3), LufkyMama (di chuyển) | R: Hieu · A: Human · C: LufkyMama | B0–M3b đóng băng; policy mới qua registry |
| Simulator | Hieu (tác giả), LufkyMama (sửa 32 commit) | R: Hieu · C: LufkyMama | Tài liệu simulator do hai người sửa, dòng sai do người không phải owner chèn |
| Backend services | LufkyMama; LamBui (`be-fe`); Hieu (`ai-4`) | R: LufkyMama · C: LamBui, Hieu | **Ba người cùng sửa** `control_loop.py`, `dispatcher.py`, `charging_service.py` |
| Safety / Guard | LufkyMama; Hieu sửa trên `ai-4` | R: một owner (Human chọn) · A: Human · review độc lập bắt buộc (G6) | Hai owner cạnh tranh; X-02 CHANGES_REQUIRED |
| Frontend | LamBui (README), LufkyMama (23 commit) | R: LamBui · C: LufkyMama | Hai người cùng sửa |
| AI-1 | Không ai (DEFERRED) | UNASSIGNED tới khi mở lại | — |
| AI-4 | Hieu (`ai-4`) | R: Hieu · A: Human · C: LufkyMama (Guard / trace) | Phạm vi WHAT-IF / HOW-TO chờ H-2 |
| AI Infrastructure (LLM, chat) | HaiVuu (F1), LufkyMama (rename, guardrail) | R: HaiVuu · C: LufkyMama | Hoạt động HaiVuu sau 22/11 UNVERIFIED |
| Benchmark / Evaluation | LufkyMama (baseline), HaiVuu (eval 22/11), Hieu (ai-4 oracle) | R: QA độc lập · C: tác giả | R-2 trùng `ai-4` R11; `report.md` không owner |
| Governance | LufkyMama (Human) + Claude (viết) + Codex (review) | A: Human · R: agent được giao · reviewer ≠ người viết | Đã tách vai trong Phase 1 |
| DevOps / CI / deploy | LufkyMama | R: LufkyMama · A: Human | Runner VM tắt; CI nhánh chưa chạy |
| Product requirements (PRD) | LufkyMama (viết), Hieu (master context nguồn) | A: Human (+ mentor) · R: LufkyMama · C: Hieu | PRD v0.4 **chưa duyệt** |

**Tự nghiệm thu (VERIFIED):** LufkyMama tự merge 8 / 8 PR, không reviewer người; "Tech Lead" của refactor và `ai-4` là AI
(ChatGPT qua người dùng) và kết quả review nằm ở mirror không truy cập được. Governance Phase 1 là phần duy nhất có reviewer
độc lập được ghi lại trong repo (Codex).

## II.6 Tài liệu không có người duy trì (UNASSIGNED)

| File | Vì sao cần owner | Đề xuất (PROPOSED) |
|---|---|---|
| `presentation/README.md` | Deliverable BTC; liệt kê pitch deck / video chưa có | Human chỉ định |
| `eval/results/report.md` | CI / Makefile trỏ tới; còn là mẫu template | HaiVuu (eval Agent theo README) |
| `README.md` mục Student ID | "[cần điền]" cho cả 4 người | Mỗi thành viên tự điền |
| `prompts/{system_prompt,safeguards,citation_rules}.md` | Template không được graph dùng | Không cần owner — bỏ cùng task code (HD-6) |
| `README_boilerplate.md`, `CONTRIBUTING.md`, `notebooks/README.md` | Template | Chương trình AI20K / HD-1 |
| Plan BE–FE `docs/superpowers/plans/2026-11-23-be-fe-implementation.md` | Được PR #16 dẫn nhưng không có trong repo | LamBui đưa vào repo hoặc PR là nguồn |

## II.7 Trách nhiệm trùng lặp

1. **Lõi an toàn / runtime** (`control_loop.py`, `dispatcher.py`, `charging_service.py`, `runtime.py`, `hybrid_station.py`):
   unified-core (LufkyMama), `ai-4` (Hieu), `be-fe` (LamBui) cùng sửa — 9 file xung đột (X-01), xung đột ngữ nghĩa Safety Hold (X-02).
2. **Nguồn trạng thái:** HANDOFF (governance), `src/simulator/docs/PROJECT_STATE.md` (Hieu + Codex), `docs/ai4/PROJECT_STATE.md`
   (Hieu, nhánh), `PROJECT_CONTEXT.md` (LufkyMama).
3. **Backlog / issue:** registry §6.1 R-1…R-6 ↔ `docs/ai4/ISSUES.md` R01–R11 (R11 outcome ledger ≈ R-2; R07 race ≈ R-6).
4. **Frontend:** LamBui và LufkyMama; S8 đã được unified-core sửa theo policy registry nhưng `be-fe` giữ bản A–D.
5. **"Tech Lead":** ba thực thể khác nhau cùng tên (II.1).
6. **Hợp đồng simulator ↔ backend:** `SIMULATOR_INTEGRATION_CONTRACT.md` (Hieu) ↔ ADR-019 / `station_protocols.py` (LufkyMama) ↔
   `FOUNDATION_CONTRACT.md` (Hieu, nhánh).

## II.8 Tài liệu thiếu mục đích rõ / trường hợp đặc biệt

| Trường hợp | Tài liệu |
|---|---|
| Không rõ phục vụ task nào | `README_boilerplate.md`; `docs/ai4/collaboration_chat.md` (rỗng, nhánh) |
| Không người duy trì | II.6 |
| Cạnh tranh nguồn chính thức | `PROJECT_CONTEXT.md`, `src/simulator/docs/PROJECT_STATE.md`, `docs/ai4/PROJECT_STATE.md` (nhánh) |
| Nhiều agent tạo trùng | Báo cáo refactor A / B / tổng (chấp nhận — evidence song song); X-01 (Claude) và X-02 (Codex) — chủ đích (tác giả vs reviewer) |
| Yêu cầu chưa được Human duyệt | `docs/PRD.md` v0.4 (bản nháp); `docs/ai4/ADR_AI4_SCOPE.md` ("Approved" bởi Tech Lead AI, gồm HOW-TO mà ADR-015 hoãn); `docs/plan/21-ui-spec.md` |
| Mô tả feature không tồn tại | `SimulatorGateway` / `base.py` (PRD FR12, `plan/10-backend.md`, `PROJECT_CONTEXT.md`); `src/simulator/live.py` (`src/simulator/AGENTS.md`) |
| Implementation lỗi thời | `src/simulator/AGENTS.md`, `SIMULATOR_INTEGRATION_CONTRACT.md`, `docs/business-overview.md`, `docs/plan/00 / 10 / 30` |
| Nhiều phiên bản, không rõ bản hiện hành | baseline `2026-11-23-refactor-phase3-baseline` / `2026-11-24-unified-core-final-baseline` / `…-frozen-baseline` (hiện hành = frozen, ghi trong code `BENCHMARK_BASELINE_DIR` — nhưng `PROJECT_CONTEXT.md` vẫn trỏ phase3); `eval/results/benchmark.md` (untracked) vs baseline; ba file `PROJECT_STATE` |

## II.9 Đề xuất thay đổi ownership (PROPOSED — không có hiệu lực)

1. Mỗi file ACTIVE ghi một **maintainer** (người hoặc vai): simulator docs → Hieu; FE spec / mockup / `frontend/*.md` → LamBui;
   `prompts/*` + `eval/results/report.md` → HaiVuu; governance + ADR + PRD → Human (A) với agent được giao (R).
2. Lõi an toàn / runtime: **một** owner kỹ thuật; nhánh khác sửa qua change request + review độc lập (G6).
3. Một nghĩa cho "Tech Lead"; phê duyệt nhóm A / phạm vi chỉ do Human; review AI ghi là "review", không phải "approved".
4. Nguồn trạng thái duy nhất = HANDOFF; backlog duy nhất = registry §6.1 (ánh xạ R01–R11 của `ai-4`).
5. PR: không tự merge thay đổi chạm F2 / F4 / F6 / dữ liệu khi chưa có reviewer khác tác giả (người hoặc agent độc lập).

## II.10 Chính sách tạo tài liệu mới (đề xuất)

Trước khi tạo file `.md` mới, agent / thành viên phải trả lời được (ghi trong mô tả PR hoặc dòng §1.11 HANDOFF):
1. Phục vụ task / quyết định nào (ID trong HANDOFF §1.3, registry, ADR hoặc issue)?
2. Ai đọc (Human / Agent / Dev / Reviewer / AI20K)?
3. Đã có tài liệu tương đương chưa (tra §6 Phần I "một nguồn cho mỗi loại")? Có ⇒ **sửa file đó**.
4. Nguồn chính thức nào sẽ trỏ tới file mới?
5. Ai duy trì, khi nào hết hiệu lực / review lại?
6. Không mở rộng phạm vi; không tạo báo cáo chỉ để chứng minh agent đã làm việc (kết quả nhỏ ghi thẳng vào checkpoint).

**Metadata tối thiểu** (chỉ cho tài liệu kỹ thuật / quyết định / báo cáo mới; **không** áp cho raw evidence, template, file sinh):

```text
Mục đích: <một câu> · Task: <ID> · Audience: <...>
Nguồn chính thức: <file> (file này là: nguồn | tham khảo | bằng chứng)
Maintainer: <người / vai> · Trạng thái: ACTIVE | HISTORICAL | EVIDENCE · Review lại / hết hiệu lực: <điều kiện>
Code / commit tham chiếu: <SHA>
```

Kiểm tự động (thuộc G-auto Phase 2): file mới thiếu các dòng trên ⇒ cảnh báo trong `scripts/check_docs.py`.

## II.11 Quyết định cần Human (bổ sung HD-1…HD-7 ở Phần I)

| # | Quyết định | Đề xuất |
|---|---|---|
| HD-8 | Xác nhận bảng phân trách nhiệm II.5 (người phụ trách từng nhóm chức năng) | Xác nhận hoặc sửa; tới lúc đó mọi ô "Đề xuất" không có hiệu lực |
| HD-9 | Một nghĩa cho "Tech Lead"; review AI không được ghi "Approved" cho quyết định nhóm A / phạm vi | Duyệt |
| HD-10 | Cấm tự merge thay đổi lõi (F2 / F4 / F6 / dữ liệu) khi chưa có reviewer khác tác giả | Duyệt (gắn G6, G-auto) |
| HD-11 | Giao owner cho deliverable chưa có người: `presentation/`, `eval/results/report.md` (MT9), Student ID | Chỉ định |
| HD-12 | Một owner kỹ thuật cho lõi an toàn / runtime; `ai-4` và `be-fe` sửa qua change request | Chọn người |
| HD-13 | PRD v0.4 "chờ nhóm + mentor duyệt": duyệt, hay giữ là nháp và lấy quyết định 25/11 làm căn cứ | Quyết |
| HD-14 | Xác nhận việc hiện tại của HaiVuu (không có hoạt động trên `origin` sau 22/11) | Hỏi trực tiếp thành viên |

## II.12 Giới hạn

- Tác giả commit ≠ người viết: nhiều commit của LufkyMama, LamBui (và có thể Hieu) do agent sinh; tỉ lệ thật UNVERIFIED.
- Không đọc nội dung `.ai-log/` (log prompt có thể chứa dữ liệu cá nhân) và không dùng nó để quy trách nhiệm.
- Không có tài liệu phân công chính thức theo file; README Team và WORKLOG do tài khoản LufkyMama viết (WORKLOG ghi "tên thành
  viên = tên trong commit", tức suy từ commit, không phải tự khai).
- Không xem được mirror và "master context v1.0", plan BE–FE của PR #16; không truy cập kênh chat với "Tech Lead".
- Không đánh giá năng lực / hiệu suất cá nhân.

---

# Phần III — Bản phân công đề xuất: sứ mệnh, trách nhiệm, việc trước mắt (D-03, 2026-11-25)

> **Trạng thái: PROPOSED.** Không có hiệu lực tới khi Human Supervisor **và** từng thành viên liên quan xác nhận (HD-8).
> Dựng từ D-01, D-02, X-01, X-02 (`CROSS_BRANCH_INDEPENDENT_REVIEW.md`) và HANDOFF hiện hành; không lặp audit. Không giao
> implementation. PRD v0.4 vẫn là **Draft**. Người soạn: Claude Code — **không độc lập** với phần việc của LufkyMama.
> Dùng được trực tiếp trong buổi họp nhóm: §III.2 (thẻ sứ mệnh), §III.5 (việc trước mắt), §III.9 (cần thống nhất).

**Bối cảnh thời gian (VERIFIED, HANDOFF §1.7):** sprint kết thúc **26/11**. AI-4 chưa có tính năng người dùng nhìn thấy;
BE–FE chưa chạy trên Unified Core. Phân công dưới đây vì vậy tách **việc cần cho demo** và **việc sau sprint**.

## III.1 Đối chiếu vai trò đề xuất với bằng chứng

| Thành viên | Vai trò đề xuất (Human) | Bằng chứng năng lực / việc đang làm | Xung đột / phụ thuộc | Khối lượng | Kết luận |
|---|---|---|---|---|---|
| LufkyMama | Kiến trúc, Backend, Safety / Runtime, Governance, DevOps | Dựng backend, Unified Core, CI / deploy, governance (VERIFIED D-02) | Là tác giả lõi ⇒ không tự review lõi; đồng thời là tài khoản Human (INFERRED) ⇒ dễ nhập vai owner và approver | **Quá tải**: 5 mảng, có cả review mọi PR | Phù hợp **có điều kiện**: tách approver (Human) khỏi owner; cân nhắc chuyển DevOps hoặc governance thường ngày cho agent được giao |
| Hieu | Simulator, AC / DC Optimizer, Decision Intelligence, AI-4 WHY | Thuật toán MVP-1/2/3 đang chạy trong backend; nhánh `ai-4` (WHY + safety fixes) (VERIFIED) | Nhánh `ai-4` sửa lõi an toàn thuộc owner khác ⇒ cần Change Request | Cao (G1 / G2 còn CHANGES_REQUIRED) | Phù hợp. Giới hạn: safety / runtime chỉ là **người sửa theo yêu cầu**, owner vẫn là LufkyMama |
| LamBui | Product Experience, Frontend, BE–FE Integration | Frontend + 24 hạng mục G1–G24 (VERIFIED); code chủ yếu do Claude Haiku sinh (VERIFIED trailer / PR) | Port BE–FE phụ thuộc contract và lõi an toàn sau remediation | Cao (port lại trên nền mới) | Phù hợp. Điều kiện: backend chỉ sửa qua contract đã thống nhất với owner backend |
| HaiVuu | Conversational AI F1, LLM Infrastructure, Prompt Engineering, AI Evaluation, phối hợp AI-4 | Chat F1 streaming, prompt hybrid, eval thủ công 22/11 (VERIFIED). **Không có hoạt động trên `origin` sau 22/11** | Phần "phối hợp AI-4" phụ thuộc AI-4 có API (G6) — chưa có | **UNVERIFIED** | **Cần xác nhận trực tiếp** khả năng nhận việc trước khi giao (HD-14). Mọi việc dưới đây của HaiVuu là đề xuất mở |

## III.2 Thẻ sứ mệnh (Member Mission Cards)

### LufkyMama — Kiến trúc hệ thống, Backend, Safety / Runtime, DevOps

| Mục | Nội dung |
|---|---|
| Sứ mệnh | Giữ cho hệ thống **chạy đúng và an toàn** như một khối: một kernel, một cửa gửi lệnh, một contract API |
| Bài toán | Ba nhánh đang cùng sửa lõi (`control_loop`, `dispatcher`, `charging_service`); lỗi an toàn thật ở baseline (bản sao báo giá mất Safety Hold); contract FE–BE lệch |
| Giá trị sản phẩm | Không cấp điện sai xe, không vượt giới hạn (MT4, MT6); báo giá phản ánh đúng trạng thái an toàn (FR20); một contract cho FE và AI-4 |
| Chức năng sở hữu | F2 (tích hợp), F3, F4, F6 (trace / sandbox phía backend), FR1 auth, API contract (ADR-008 / 009) |
| Module sở hữu | `src/services/` (trừ `copilot/`), `src/guard/`, `src/simulator/hybrid_station.py`, `src/api/`, `src/db/`, `migrations/`, `.github/`, `Dockerfile`, deploy |
| Tài liệu duy trì | `ARCHITECTURE.md`, `docs/architecture_diagram.md`, `docs/plan/56`, `55`, `50`, `docs/adr/` (soạn; Human duyệt) |
| Việc đang làm | Governance Phase 1 (chờ P1-14); chưa có task implementation đang giao |
| Bàn giao | Quyết định owner-review cho S02 / S03 (patch của Hieu); contract API hợp nhất cho port BE–FE; một bản `unified-core` có remediation để tích hợp |
| Tiêu chí | Phản ví dụ S01 / S02 / S03 / G1-F03 của X-02 chạy **đạt** trên cùng candidate; `tests/test_architecture.py` đạt; OpenAPI sinh lại khớp; reviewer độc lập (không phải LufkyMama) xác nhận |
| Phụ thuộc | Hieu (patch S02 / S03, tham vấn optimizer / vật lý), LamBui (yêu cầu contract), Codex (review) |
| Quyền | Duyệt kỹ thuật thay đổi vào module mình sở hữu (sau review độc lập); từ chối Change Request thiếu impact analysis |
| Không được tự quyết | Phê duyệt Human (ADR nhóm A, phạm vi, PRD, đóng Phase, commit / merge lõi khi chưa có reviewer khác); sửa B0–M3b version `"1"` |
| Reviewer | Codex (agent độc lập) cho lõi; Hieu tham vấn optimizer |
| Phải giải thích được | Vòng `on_event` (luồng B), Safety Hold / fail-safe, fork admission, ba loại sai lệch công suất, vì sao chỉ dispatcher gọi `apply_commands` |

### Hieu — Simulator, AC / DC Optimizer, Decision Intelligence, AI-4 WHY

| Mục | Nội dung |
|---|---|
| Sứ mệnh | Làm cho **quyết định sạc tối ưu và giải thích được** bằng dữ kiện thật |
| Bài toán | Tỉ lệ đúng hạn baseline không đo được MT1 (R-2); policy mặc định M3a chỉ tạm (Q3); cư dân cần biết "vì sao" (F8, Q1) |
| Giá trị sản phẩm | Thuật toán đang chạy trong backend; AI-4 WHY là tính năng AI được Human ưu tiên (Q1); WHY dựa trên trace, không bịa (Q4) |
| Chức năng sở hữu | F2 thuật toán (FR5–FR9), F8 AI-4 WHY; tham vấn F9 benchmark |
| Module sở hữu | `src/simulator/` (trừ `hybrid_station.py`), `src/optimizer/` (policy mới qua registry; B0–M3b đóng băng), `src/services/copilot/` và `src/models/copilot.py` (khi tích hợp) |
| Tài liệu duy trì | `src/simulator/{AGENTS,README}.md`, `src/simulator/docs/*`, `docs/ai4/*` (khi tích hợp — gộp theo Phần I §4) |
| Việc đang làm | `feature/ai-4` G2 (WHY) chờ nghiệm thu — X-02: **CHANGES_REQUIRED** |
| Bàn giao | Patch S02, S03 (theo Change Request vào lõi của LufkyMama); sửa W01; WHY service đạt review; sửa tài liệu simulator lỗi thời (P0, Phần I) |
| Tiêu chí | Phản ví dụ S02 (fork mang hard-pending), S03 (timeline còn lưu / retry sau ack), W01 (tách requested minimum vs approved allocation) chuyển từ FAIL sang PASS; WHY không dùng LLM, trả `partial / no_data` khi thiếu dữ kiện; không chạm B0–M3b |
| Phụ thuộc | LufkyMama (owner lõi duyệt patch), HaiVuu (lớp LLM / NL khi lên G6), LamBui (UI WHY khi có API) |
| Quyền | Quyết định kỹ thuật trong simulator / optimizer / copilot; đề xuất policy mới qua registry |
| Không được tự quyết | Mở rộng phạm vi AI-4 sang WHAT-IF / HOW-TO (chờ H-2); sửa lõi an toàn không qua Change Request; ghi "Approved" từ review AI |
| Reviewer | Codex (độc lập); LufkyMama cho phần chạm lõi |
| Phải giải thích được | LP AC / DC + Coordinator, khác biệt backend consent (B1 / D-6) với standalone, DecisionTrace v2 và cách WHY dẫn chứng |

### LamBui — Trải nghiệm sản phẩm, Frontend, BE–FE Integration

| Mục | Nội dung |
|---|---|
| Sứ mệnh | Để cư dân và vận hành **dùng được** hệ thống: thấy đúng trạng thái, đặt / đổi lịch, duyệt đề nghị |
| Bài toán | 24 hạng mục G1–G24 đã làm trên nền cũ; contract FE–BE lệch (S8 A–D, thiếu sự kiện an toàn, `budget_kw` sai nghĩa) |
| Giá trị sản phẩm | F5 (FR17–FR18) cho demo; sơ đồ bãi không lộ dữ liệu người khác; đổi lịch có xem trước |
| Chức năng sở hữu | F5, phần hiển thị của F14 (FR43), UI của F8 khi có API |
| Module sở hữu | `frontend/` (mọi màn hình, client, test FE) |
| Tài liệu duy trì | `docs/plan/21-ui-spec.md`, `22-ui-work-split.md`, `docs/mockups/*`, `frontend/README.md`, `frontend/AGENTS.md`; plan G1–G24 (đưa vào repo hoặc mô tả PR là nguồn) |
| Việc đang làm | PR #16 `feature/be-fe-integration` (OPEN) — X-01 / X-02: NOT_READY |
| Bàn giao | Port G1–G24 lên `unified-core` theo X-02 §7 (giữ UI, port hành vi, không chép backend cũ); S8 theo policy registry |
| Tiêu chí | FE chạy trên OpenAPI sinh từ backend `unified-core`; X-BF-03…06 không tái xuất (WS chỉ live, đọc `rt.store`; quote-change qua admission async + consent; tách cap vs budget); giữ chữ ký `execute_approved(..., safety_holds, safety_pending)`; test FE + test luồng backend đạt trên cùng candidate; chạy được với backend thật (không chỉ mock) |
| Phụ thuộc | LufkyMama (contract, lõi sau S02 / S03), Hieu (dữ liệu WHY khi có API) |
| Quyền | Quyết định UI / UX, cấu trúc frontend; đề xuất endpoint mới |
| Không được tự quyết | Sửa `control_loop` / `dispatcher` / `charging_service` / Guard (gửi Change Request); merge nhánh nền cũ; hardcode số cấu hình (22 / 78) |
| Reviewer | Codex hoặc thành viên khác cho phần backend; HaiVuu / Hieu cho UX luồng chat / WHY |
| Phải giải thích được | Báo giá là ước tính có điều kiện; consent thật vs giả định; vì sao không phát WS trong vòng quyết định; cap vật lý vs ngân sách vùng |

### HaiVuu — Conversational AI F1, LLM Infrastructure, Prompt, AI Evaluation (**cần xác nhận**)

| Mục | Nội dung |
|---|---|
| Sứ mệnh | Để cư dân **nói chuyện tự nhiên** với hệ thống mà số liệu vẫn do code tính, và **đo được** chất lượng lớp LLM |
| Bài toán | MT9 chưa đo với LLM thật; `eval/results/report.md` còn mẫu template; D-3 cho phép offline có nhãn ở dev / test; AI-4 sẽ cần lớp NL (G6) |
| Giá trị sản phẩm | F1 cho demo; bằng chứng MT9; lớp LLM dùng chung cho AI-4 không phá nguyên tắc Q4 (facts / trace) |
| Chức năng sở hữu | F1 (FR4, FR4a khi mở), Lớp LLM (FR31–FR33a), MT9 |
| Module sở hữu | `src/llm_chat/`, `src/services/llm.py`, `prompts/`, `eval/run_agent_eval.py`, `eval/datasets/` |
| Tài liệu duy trì | `prompts/*`, `eval/README.md` (phần Agent), `eval/results/report.md` |
| Việc đang làm | **UNVERIFIED** (không có nhánh / PR sau 22/11) |
| Bàn giao | Eval MT9 với LLM thật (khi có key) hoặc báo cáo offline có nhãn theo D-3; `report.md` thật; nhãn "LLM chưa cấu hình" trong UI (AC12) phối hợp LamBui |
| Tiêu chí | Bộ câu có nhãn chạy với provider thật, báo intent đúng / grounding / tỉ lệ bị gate loại theo PRD MT9; không có số do LLM tạo; production vẫn cấm `mock` |
| Phụ thuộc | API key (Human), LamBui (UI chat), Hieu (khi WHY cần lớp NL) |
| Quyền | Quyết định prompt, cấu hình provider, bộ eval |
| Không được tự quyết | Cho LLM tạo số / quyết định công suất; nới production cho `mock`; đổi `resident_id` sang phía LLM (ADR-006) |
| Reviewer | Codex hoặc Hieu (grounding); LufkyMama (guardrail chạm Guard / API) |
| Phải giải thích được | Graph ReAct + HITL `confirm_booking`, guardrail hai lớp, vì sao kWh do code tính, giới hạn kiểm grounding hiện tại (chỉ kWh / mã cổng) |

## III.3 Ma trận trách nhiệm (R làm · A chịu cuối · C tham vấn · I được báo) — PROPOSED

| Nhóm | LufkyMama | Hieu | LamBui | HaiVuu | Human | Reviewer độc lập |
|---|---|---|---|---|---|---|
| Unified Core (kernel, registry) | R / A kỹ thuật | C (vật lý, thuật toán) | I | I | A cuối cho thay đổi đóng băng | Codex |
| AC / DC Optimizer | C | R / A kỹ thuật | I | — | A (policy mặc định, Q3) | Codex |
| Simulator | C (`hybrid_station.py` là R) | R / A | — | — | — | Codex |
| Backend services / API contract | R / A | C | C (yêu cầu contract) | C (chat API) | I | Codex |
| Safety / Guard / Runtime | **R / A (owner duy nhất)** | R theo Change Request (S02 / S03) | không sửa trực tiếp | — | A cho exception lõi đóng băng | **Bắt buộc** |
| Frontend | C | — | R / A | C (chat UI) | I | thành viên khác hoặc agent |
| AI-1 | — | — | — | — | DEFERRED | — |
| AI-4 WHY | C (trace, quyền) | R / A | C (UI) | C (NL, G6) | A (phạm vi H-2) | Codex |
| AI infrastructure (LLM, chat) | C (guardrail, API) | C | C | R / A | A (D-3, key) | Codex / Hieu |
| Benchmark / Evaluation | R (backend baseline) | R (R-2, R-3 thuật toán) | — | R (MT9) | A (D-4, chọn policy) | QA độc lập |
| Governance | R (soạn, qua agent) | C | C | C | **A** | Codex |
| DevOps / CI / deploy | R / A | — | C (FE build) | — | A (production) | — |
| Product requirements (PRD) | R (soạn) | C (nghiên cứu nền) | C (UX) | C (F1) | **A** (+ mentor) | — |

## III.4 Sở hữu module và tài liệu ACTIVE (maintainer) — PROPOSED

| Module / tài liệu ACTIVE | Maintainer | Ghi chú |
|---|---|---|
| `src/services/` (trừ `copilot/`), `src/guard/`, `src/api/`, `src/db/`, `migrations/`, `src/simulator/hybrid_station.py`, `.github/`, deploy | LufkyMama | Lõi an toàn: thay đổi từ người khác qua Change Request |
| `src/simulator/` (còn lại), `src/optimizer/`, `src/services/copilot/`, `src/models/copilot.py` | Hieu | B0–M3b đóng băng |
| `frontend/` | LamBui | |
| `src/llm_chat/`, `src/services/llm.py`, `prompts/`, `eval/run_agent_eval.py`, `eval/datasets/` | HaiVuu (chờ xác nhận) | Nếu HaiVuu không nhận: tạm LufkyMama |
| `src/models/` (hợp đồng dùng chung) | LufkyMama (A) + owner module dùng field đó (C) | Đổi hợp đồng = liên module |
| `CLAUDE.md`, `AGENTS.md`, HANDOFF, registry, ADR, PRD, HACP | Human (A), soạn bởi agent / LufkyMama (R) | Không tạo nguồn song song |
| `ARCHITECTURE.md`, `docs/architecture_diagram.md`, `docs/plan/50`, `55`, `56` | LufkyMama | |
| `src/simulator/*.md`, `src/simulator/docs/*`, `docs/ai4/*` (khi tích hợp) | Hieu | Dòng `LiveStation` sai do người khác chèn — Hieu sửa với C LufkyMama |
| `docs/plan/21`, `22`, `docs/mockups/*`, `frontend/*.md` | LamBui | |
| `prompts/*`, `eval/README.md` (Agent), `eval/results/report.md` | HaiVuu (chờ xác nhận) | |
| `README.md`, `JOURNAL.md`, `WORKLOG.md`, `presentation/` | Cả nhóm; điều phối: Human chỉ định (HD-11) | Mỗi người tự điền phần mình |
| EVIDENCE, template AI20K, file sinh | Không cần owner cá nhân | Bất biến / chương trình / công cụ |

**Change Request (không tạo tài liệu mới):** khi sửa module của người khác, mô tả PR (hoặc dòng HANDOFF §1.3) phải có: lý do,
file chạm, tác động tới an toàn / contract / dữ liệu, test chứng minh, người owner đồng ý, reviewer độc lập. Owner **không** tự
phê duyệt thay đổi của chính mình vào lõi.

## III.5 Việc trước mắt — gán theo owner đề xuất (không giao implementation)

| ID | Việc | Nguồn | Owner đề xuất (R) | A / reviewer | Phụ thuộc | Trùng lặp đã gộp |
|---|---|---|---|---|---|---|
| W-S02 | Fork admission giữ / xử lý hard event pending trước planning (hoặc từ chối có nhãn) | X-02 S02 | Hieu (trên `ai-4`) | A: LufkyMama · Codex | Human cho phép exception sửa lõi đóng băng | ≈ `ai-4` G3 backlog "pending safety registry"; ≈ R-6 một phần |
| W-S03 | Tách ack an toàn khỏi ack giao sự kiện; timeline không mất sau readback | X-02 S03 | Hieu | A: LufkyMama · Codex | như trên | ≈ `ai-4` G1-F01 |
| W-W01 | WHY tách "minimum đề nghị" khỏi "công suất được duyệt" | X-02 W01 | Hieu | Codex | — | — |
| W-G1 | Chốt phạm vi patch an toàn (bắt buộc) vs trace persistence / migration `0004` (gate riêng) | X-02 §3 bảng phân loại | LufkyMama | Human (schema, exception) | W-S02, W-S03 | |
| W-CT | Hợp nhất contract API trên `unified-core` (4 endpoint mới, field mới, sự kiện an toàn) | X-BF-02, X-02 §7 | LufkyMama | Codex | W-G1 | |
| W-BF | Port G1–G24 lên `unified-core` theo X-02 §7 | X-BF-01…06 | LamBui | A: LufkyMama (phần backend) · reviewer khác LamBui | W-CT | |
| W-MT9 | Eval lớp LLM (MT9) + `report.md` thật; nhãn offline theo D-3 | registry MT9, D-3 | HaiVuu (**chờ xác nhận**) | Codex | API key (Human) | |
| W-DOC0 | P0 tài liệu: `src/simulator/AGENTS.md`, `SIMULATOR_INTEGRATION_CONTRACT.md`, `PROJECT_CONTEXT.md` → trỏ | D-01 Phần I §5 | Hieu (2 file simulator), LufkyMama (`PROJECT_CONTEXT`) | Human (HD-1, HD-5) | — | |
| W-DOC1 | Rút gọn HANDOFF / `CLAUDE.md`; gộp nguồn trạng thái | D-01 HD-4, HD-5 | LufkyMama (qua agent) | Codex | sau X-02 (đã xong) | gộp `PROJECT_STATE` ×2 |
| W-GOV | Phân phối governance tới thành viên: C-1 commit tài liệu; họp nhóm dùng Phần III | C-1, D-03 | Human | — | C-1 | |
| R-1 / R-2 / R-6 (P0) | Dataset sự cố / khả thi + KPI / test U1, U3 | registry §6.1 | R-1: LufkyMama · R-2: Hieu (định nghĩa) + LufkyMama (KPI backend) · R-6: LufkyMama | Codex / QA | Q2 ✔, D-4 ✔ hướng | R-2 = `ai-4` R11; R-6 ⊃ `ai-4` R07 |
| R-3 / R-4 (P1) | So policy ghép cặp / consent | registry §6.1 | R-3: Hieu · R-4: LufkyMama (backend) + Hieu (nếu vào Planning Core) | Human (Q3, D-6) | R-2 | |
| R-5 (P2) | ETA / cổng dự kiến | registry §6.1 | LamBui (hiển thị) + LufkyMama (API) | — | — | ≈ X-BF-06 |

Không mở thêm backlog: `docs/ai4/ISSUES.md` R01–R11 ánh xạ vào bảng trên và registry §6.1 khi tích hợp.

## III.6 Phụ thuộc giữa thành viên (thứ tự)

```text
Human: exception lõi đóng băng + C-1 ─┐
                                      ▼
Hieu: W-S02, W-S03, W-W01 ──► LufkyMama: duyệt owner (W-G1) ──► Codex: review phản ví dụ
                                      │
                                      ▼
                         LufkyMama: W-CT (contract hợp nhất, OpenAPI)
                                      │
                    ┌─────────────────┴──────────────────┐
                    ▼                                    ▼
          LamBui: W-BF (port FE / BE)         Hieu + HaiVuu: AI-4 API / NL (G6, sau sprint)
                    │                                    │
                    └────────► tích hợp trên CÙNG candidate, test chung ◄──┘
HaiVuu: W-MT9 độc lập (chỉ cần API key)
```

Điểm nghẽn: LufkyMama nằm trên đường găng của mọi nhánh (owner lõi + contract). Nếu không giảm tải (HD-8a), tích hợp sẽ chờ.

## III.7 Tiêu chí hoàn thành (không dùng số commit / dòng / test làm KPI)

- Một việc "xong" khi: (1) tiêu chí chức năng trong III.2 / III.5 có bằng chứng gắn commit; (2) reviewer khác tác giả kiểm;
  (3) tài liệu owner cập nhật đúng nguồn; (4) HANDOFF ghi trạng thái (HANDOFF_READY).
- Không tính "test đạt trên nền riêng" là tích hợp (X-01 / X-02). Không tính nhãn "Approved" của AI là phê duyệt.
- Giá trị được đánh giá theo: chức năng chạy được cho người dùng, an toàn giữ nguyên, bằng chứng tái lập được.

## III.8 Quy tắc tài liệu áp cho mỗi người (tái dùng II.10)

Trước khi tạo file mới: mục đích, task, audience, owner, nguồn chính thức, điều kiện hết hiệu lực (metadata II.10). Ưu tiên sửa
tài liệu mình đang duy trì (III.4). Không tạo báo cáo chỉ để chứng minh đã làm việc; kết quả nhỏ ghi vào mô tả PR hoặc HANDOFF.

## III.9 Cần nhóm / Human thống nhất (HD-8…HD-14, có phương án)

| # | Câu hỏi | Phương án A (khuyến nghị) | Phương án B | Hệ quả nếu chưa quyết |
|---|---|---|---|---|
| HD-8 | Xác nhận phân công III.2–III.4 | Duyệt như đề xuất, mỗi thành viên xác nhận thẻ của mình trong họp | Sửa từng thẻ | Không ai chịu trách nhiệm chính thức; ba người tiếp tục cùng sửa lõi |
| HD-8a | Giảm tải LufkyMama | Giao governance thường ngày cho agent được giao (Human duyệt), LufkyMama giữ lõi + contract | Chuyển DevOps cho LamBui (FE build / deploy Vercel đã gần) | LufkyMama là điểm nghẽn mọi tích hợp |
| HD-9 | Nghĩa "Tech Lead" | Chỉ dùng "Reviewer (AI)"; "Approved" chỉ khi Human ghi | Giữ "Tech Lead" = Codex | Nhãn "Approved" của AI tiếp tục bị hiểu là phê duyệt |
| HD-10 | Cấm tự merge thay đổi lõi | Bắt buộc reviewer khác tác giả cho F2 / F4 / F6 / dữ liệu / contract | Chỉ cho lõi an toàn | Tiếp tục 8 / 8 PR tự merge |
| HD-11 | Owner deliverable | `presentation/` + video: LamBui (UX) với cả nhóm; `report.md`: HaiVuu; Student ID: mỗi người | Human tự điều phối | Thiếu deliverable BTC khi kết thúc sprint |
| HD-12 | Owner lõi an toàn / runtime | LufkyMama (owner), Hieu sửa theo Change Request, Codex review | Hieu làm owner tạm thời trong lúc sửa S02 / S03 | Ba nhánh sửa cùng file, rủi ro mất Safety Hold (X-BF-04) |
| HD-13 | PRD v0.4 | Giữ Draft; quyết định 25/11 (Q1–Q4, D-x) là căn cứ hiện hành; duyệt PRD sau sprint với mentor | Duyệt ngay phần không xung đột | Yêu cầu vẫn không có bản được duyệt |
| HD-14 | HaiVuu | Hỏi trực tiếp khả năng nhận F1 / MT9; nếu không nhận, LufkyMama tạm giữ `src/llm_chat` | Gán AI-4 NL (G6) cho HaiVuu sau sprint | Thẻ HaiVuu không có hiệu lực, MT9 tiếp tục chưa đo |
| (mới) | Exception sửa lõi đóng băng cho W-S02 / W-S03 | Cho phép, phạm vi chỉ patch an toàn tối thiểu (X-02 §3) | Chờ sau sprint | AI-4 và BE–FE không tích hợp được |
| (mới) | Ưu tiên cho demo 26/11 | Demo trên `unified-core` hiện tại + UI có sẵn; AI-4 / BE–FE trình bày là "đang tích hợp" | Cố gộp gấp `be-fe` | Gộp gấp vi phạm X-02 integration gate |
