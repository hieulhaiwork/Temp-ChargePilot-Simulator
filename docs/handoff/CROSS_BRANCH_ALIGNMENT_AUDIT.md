# Cross-branch Architecture Alignment Audit — `feature/ai-4`, `feature/be-fe-integration`

- Người làm: Claude Code (`claude-opus-5-5`), 2026-11-25, theo yêu cầu Human. Vai trò: auditor chỉ đọc. Claude là tác giả
  phần lớn `feature/unified-core` (baseline) ⇒ **không độc lập** với baseline; cần Codex kiểm lại (§8).
- Baseline: `feature/unified-core` @ `ce23136` + tài liệu governance **chưa commit** trong workspace `D:\VIN\P-019`
  (Phase 1 Technical Acceptance PASS — `REREVIEW_PHASE1_RESULT.md` §T0–T5; quyết định Human 25/11 — `HANDOFF.md` §1.5).
- Không sửa code của ai, không checkout / merge / rebase / commit / push / deploy. Working tree không đổi (chỉ thêm file
  này và các ô trạng thái HANDOFF). Đã `git fetch` 4 nhánh (chỉ cập nhật ref `origin/*`).

## 0. Kết luận

| Nhánh | HEAD | Verdict | Lý do chính |
|---|---|---|---|
| `feature/ai-4` | `4658b1f` | **READY_WITH_CONDITIONS** (chỉ phần nền + WHY service) | Dựa đúng Unified Core (base = `ce23136`, 0 behind), merge thử không xung đột code, test đạt. Nhưng sửa lõi an toàn đang đóng băng, Gate 2 chưa nghiệm thu, bằng chứng review trỏ tới mirror không truy cập được, phạm vi HOW-TO chưa được Human duyệt, chưa có API / LLM / UI |
| `feature/be-fe-integration` | `b92e61a` | **NOT_READY** | Dựng trên `develop` @ `68692ee` — **trước** Unified Core (81 commit behind). Dùng kiến trúc / contract đã bỏ (`src.agents`, `StrategyName` A–D, admission đồng bộ). 9 file xung đột; có xung đột ngữ nghĩa với lõi an toàn và với `feature/ai-4` |

Không có bằng chứng làm mất hiệu lực Technical Acceptance Phase 1. Có **bằng chứng mới** (tái hiện độc lập trên
`ce23136`, §3 X-AI4-01) cho thấy một số mô tả trong registry về sandbox / trace còn thiếu — đề xuất cập nhật có duyệt (§7).

## 1. Git và phân kỳ (A)

| Ref | SHA | Ngày / tác giả commit cuối | Merge base với `ce23136` | Ahead / behind `ce23136` |
|---|---|---|---|---|
| `feature/unified-core` | `ce23136d50ad08abb7c9fdc98eff791875d24516` | 24/11 12:08 | — | — |
| `feature/ai-4` | `4658b1f068350c130ed5ed1a744c19a7b8cd522c` | 24/11 22:49 | `ce23136` | 3 / 0 |
| `feature/be-fe-integration` | `b92e61a10d6c086c06d9e32939f08ca3a5ffec0e` | 23/11 17:25 | `68692ee` (= `develop`) | 12 / 81 |
| `develop` | `68692ee6c8e3d71a83aebefa95610d71840e3728` | 23/11 03:10 | — | `ce23136` ahead 81 |

**Ref chỉ đọc cho Codex** (trong `.git`, không đổi working tree): `refs/audit/2026-11-25/{unified-core,ai-4,be-fe-integration,develop}`.
Kiểm: `git for-each-ref refs/audit`. Xuất nguồn không checkout: `git archive refs/audit/2026-11-25/<nhánh> | tar -x -C <thư mục tạm>`.

Commit:
- `feature/ai-4`: `d2b5d48` docs plan AI-4 · `490f433` "Approved phase 4.1" (tên lịch sử; **không** có nghĩa đã nghiệm thu — tự ghi trong `docs/ai4/PROJECT_STATE.md`) · `4658b1f` "Complete phase 4.1".
  37 file ngoài evidence (+10 486 / −228) + 516 file evidence (`eval/evidence/2026-11-24-ai4-*`) + PDF research 18 MB.
- `feature/be-fe-integration`: 12 commit `6cfb42c`…`b92e61a` (hợp đồng G1–G24, FE screens, merge `fe-screens` + `be-contract`).
  46 file (+4 171 / −568): 28 file frontend, 13 file backend `src/`, 3 file test backend, `config/site_layout.yaml`.

**Thử merge (`git merge-tree --write-tree`, không đụng working tree):**
- `ai-4` → `unified-core`: **sạch** (exit 0).
- `be-fe` → `unified-core`: **9 file xung đột**: `frontend/openapi.json`, `frontend/src/lib/api/schema.d.ts`, `src/api/routes.py`,
  `src/guard/dispatcher.py`, `src/models/schemas.py`, `src/models/station.py`, `src/services/charging_service.py`,
  `src/services/control_loop.py`, `tests/test_api/test_flows.py`.
- `ai-4` ↔ `be-fe`: cùng 9 file.
- Tài liệu governance chưa commit ↔ `ai-4`: `CLAUDE.md` **xung đột** (`git merge-file`, cả hai sửa vùng DecisionTrace /
  invariants). `be-fe` không sửa tài liệu governance.

**Test (tự chạy 25/11, Windows, SQLite tạm, LLM giả, bản `git archive` trong thư mục tạm):**
| Nhánh | Backend + simulator | Frontend |
|---|---|---|
| `ai-4` | 843 đạt + 21 đạt khi chạy lại trên bản export đầy đủ (lần đầu lỗi do export thiếu `eval/`, `scripts/`) ⇒ 864 đạt, 8 bỏ qua | không đổi FE |
| `be-fe` | 612 đạt + 11 đạt khi chạy lại trên export đầy đủ ⇒ 623 đạt, 8 bỏ qua (trên nền cũ của chính nó) | `vitest` 11 file / 44 test đạt |
Không chạy: lint / typecheck / build FE, Postgres thật, LLM thật, CI, deploy. Test đạt trên nền riêng **không** chứng minh tương thích sau tích hợp.

## 2. Thành viên đang làm gì (hiện trạng thực)

| | `feature/ai-4` | `feature/be-fe-integration` |
|---|---|---|
| Mục tiêu | AI-4 Decision Copilot theo kế hoạch 8 gate (P0, G1…G7) — `docs/ai4/AI-4_MASTER_IMPLEMENTATION_PLAN.md` | Nối 24 hạng mục G1–G24 giữa màn hình và backend (đổi lịch, phê duyệt, sơ đồ bãi, tầng công suất, chat resume…) |
| Đã làm | P0 (baseline + issue ledger R01–R11), G1 "Foundation hardening" (sửa lỗi fork / trace / safety delivery, migration `0004`), G2 WHY engine **deterministic, chỉ đọc** (`src/services/copilot/{trace_reader,evidence,why}.py`, `src/models/copilot.py`) | 4 endpoint mới, mở rộng `StationOverview`, `Approval`, `ChatResponse`, sự kiện `SITE_OCCUPANCY`, FE: `ChangeBookingDialog`, `PowerTiers`, `SiteMap` dùng dữ liệu live (bỏ `fixture.ts`) |
| Chưa làm | WHAT-IF, HOW-TO, NL / LLM, HTTP API `/copilot`, UI, eval độc lập (G3–G7) | Rebase lên Unified Core |
| Trạng thái theo trục bằng chứng | WHY: **Implemented + Tested** (service), **chưa Integrated** (không có API / UI), **chưa Validated** | **Implemented + Tested trên nền cũ**, **chưa Integrated** với Unified Core |
| Mức hoàn thành (theo kế hoạch của chính nhánh) | 2 / 8 gate đã được Tech Lead của nhánh duyệt, gate 3 (G2) chờ; tính năng người dùng nhìn thấy: **chưa có** | 24 / 24 hạng mục có code trên nền cũ; **0** đã chạy trên Unified Core |

## 3. Phát hiện — `feature/ai-4` (B)

**X-AI4-01 · Lỗi an toàn / sandbox có thật ở baseline (xác nhận lại độc lập) · Severity: Cao (ảnh hưởng baseline, không phải lỗi của nhánh)**
- Commit: phát hiện ở `d2b5d48` (P0), sửa ở `490f433` (G1). Source baseline: `src/services/runtime.py:435` (`fork_runtime`),
  `src/services/decision_trace.py:82,177,232`, `src/services/control_loop.py:117,458`.
- Evidence: chạy lại `eval/evidence/2026-11-24-ai4-p0/probe_issues.py` (lấy từ nhánh) trên export `ce23136`:
  `R01 fork_holds=[] fork_output_kw=33.0, live_holds=["dc-a"] live_output_kw=0.0` (bản sao báo giá **mất Safety Hold**, cấp lại
  33 kW cho xe lỗi; live an toàn); `R03 nested_guard_status="pass"` dù có `charging_model` hard violation; `R04` gắn nhãn
  "chờ duyệt" cho xe đang bị giữ an toàn; `R05` approved 11 kW ghi dưới nhãn requested; `R02` trace đầy đủ không lưu bền
  mặc định. Khớp đúng `raw/issue-probe-final.stdout.txt` của nhánh.
- Impact: báo giá / admission có thể dự kiến sạc cho xe đang bị giữ an toàn; trace hiện tại chưa đủ làm bằng chứng WHY.
  Live không bị cấp điện sai (probe: 0 kW).
- Counterargument: R01 chỉ ảnh hưởng bản sao ước tính, không phải lệnh thật; registry đã ghi FR20 "MỘT PHẦN".
- Action: coi sửa G1 là **sửa lỗi lõi an toàn**, cần review độc lập + Human duyệt trước khi vào `unified-core` (§7).
  Đề xuất cập nhật registry FR19 / FR20 sau khi được duyệt.

**X-AI4-02 · Sửa lõi an toàn đang đóng băng mà chưa qua cổng Human / review độc lập của dự án · Severity: Cao (governance)**
- Commit `490f433`, `4658b1f`. Source: `src/services/control_loop.py` (+327), `src/simulator/hybrid_station.py` (+310),
  `src/services/runtime.py` (+107), `src/guard/dispatcher.py` (+32: `execute_approved(..., safety_holds, safety_pending)`),
  `src/services/decision_trace.py`, `src/services/repository.py`, migration `0004_full_decision_traces.py`.
- Evidence: hành vi mới — tạm dừng đồng hồ khi còn hard event chưa xử lý, tối đa 3 lần dispatch, `rt.decision_lock()` thay
  `rt.lock`, `queue_events` thay `outbox.extend`; ADR-019 / `CLAUDE.md` ghi Unified Core "đã đóng băng, không refactor thêm".
  Kernel, optimizer, registry, policy B0–M3b **không** bị sửa (diff không chạm `src/simulator/core`, `src/optimizer`).
- Impact: thay đổi chạm F3 / F4 (an toàn) và DB schema ⇒ thuộc G6 (review độc lập bắt buộc) và đổi schema cần ADR-005 quy trình.
- Counterargument: đây là sửa lỗi có test tái hiện fail-before / pass-after, không phải refactor; "Tech Lead" của nhánh đã
  duyệt G1.
- Action: Codex review riêng diff lõi (`git diff ce23136 refs/audit/2026-11-25/ai-4 -- src/services src/guard src/simulator src/db migrations`);
  Human quyết cho phép sửa lõi đóng băng dưới dạng bug-fix.

**X-AI4-03 · Bằng chứng review trỏ tới "mirror" không truy cập được · Severity: Trung bình (provenance)**
- Source: `docs/ai4/PROJECT_STATE.md`, `PHASE_4_1_REPORT.md` dòng 5–7: duyệt tại `d520ffb`, `fed2c5e`, `6ba13b8`, `2d15ca1`.
- Evidence: `git cat-file -t` cả 4 SHA ⇒ "Not a valid object name" trong repo này; không có remote mirror.
- Impact: không kiểm được "APPROVED / CONDITIONAL PASS" của Tech Lead nhánh; không biết Tech Lead đó là ai.
- Counterargument: báo cáo có mapping local → mirror và evidence thô trong repo.
- Action: người phụ trách nhánh đẩy mirror hoặc ghi người duyệt + kết quả trên SHA của `origin`.

**X-AI4-04 · Phạm vi AI-4 rộng hơn quyết định Human · Severity: Trung bình (cần quyết)**
- Source: `docs/ai4/ADR_AI4_SCOPE.md` ("Approved tại G0"): WHY + WHAT-IF + **HOW-TO hữu hạn**, NL cho cả hai vai trò.
- Evidence: ADR-015 hoãn HOW-TO; Human 25/11 Q1 chỉ duyệt "ưu tiên AI-4 WHY". ADR nằm ngoài `docs/adr/`, ghi "Approved"
  trong khi quyết định phạm vi là nhóm A (Human).
- Counterargument: HOW-TO "hữu hạn một biến" nhỏ hơn HOW-TO bị hoãn; WHY vẫn là việc đầu tiên trong lộ trình nhánh.
- Action: Human quyết có giữ WHAT-IF / HOW-TO trong phạm vi AI-4 không; chuyển ADR về `docs/adr/` dạng `Proposed`.

**X-AI4-05 · WHY đúng nguyên tắc nhưng chưa tới người dùng · Severity: Thông tin**
- Source: `src/services/copilot/why.py:137` `explain_why(query, actor, ...)`; `src/models/copilot.py:100` `ActorContext`
  ("derived from JWT, never from LLM"), `WhyStatus {ok, partial, no_data, forbidden, unsupported}`, `WhyFact`
  (`correlation_id`, `stage`, evidence refs), `WhyReason`.
- Evidence: copilot chỉ import `repository`, `catalog`, models — **không** có LLM, không ghi repository (grep `repository.save|update|delete` rỗng).
  Không có route `src/api/copilot.py`; OpenAPI `ai-4` = `unified-core`. `ActorContext` chỉ được tạo trong test.
- Đánh giá theo yêu cầu: grounding — facts có ref tới trace, thiếu dữ kiện trả `partial / no_data` (đúng Q4); quyền — thiết
  kế đúng (server-side, allowlist resident) nhưng **chưa nối JWT** vì chưa có endpoint; WHAT-IF / fork — chưa làm; consent —
  không chạm; tương thích kernel — đọc trace của `HybridStation`, standalone serializer giữ nguyên.
- Action: giữ; G6 (API + JWT) là điểm cần review quyền thật.

**X-AI4-06 · `CLAUDE.md` xung đột với tài liệu governance chưa commit · Severity: Thấp**
- Commit `490f433`/`4658b1f` sửa bullet DecisionTrace; workspace sửa vùng lân cận (chưa commit). `git merge-file` ⇒ 1 xung đột.
- Action: khi commit governance (C-1) hoặc tích hợp `ai-4`, gộp tay; nội dung `ai-4` mô tả trace v2 backend đúng hơn nếu G1 được duyệt.

## 4. Phát hiện — `feature/be-fe-integration` (C)

**X-BF-01 · Dựng trên kiến trúc trước Unified Core · Severity: Cao**
- Commit base `68692ee`. Evidence (`git cat-file -e`): nhánh **có** `src/agents/graph.py`, `src/simulator/base.py`,
  `src/simulator/src/`, `src/optimizer/lp_model.py`; **không có** `src/llm_chat/`, `src/simulator/core/kernel.py`,
  `src/optimizer/registry.py`, `src/services/admission.py`, `src/services/decision_trace.py`, `src/guard/physical/`,
  `src/models/station_protocols.py`. Code mới import `src.agents.nodes.act_node`, `src.agents.tools.charging` (`src/api/routes.py`).
- Impact: mọi thay đổi backend phải viết lại trên Unified Core, không merge cơ học được.
- Counterargument: nhánh tạo trước khi Unified Core xong (23/11 vs 24/11); phần lớn giá trị nằm ở FE và contract, vẫn dùng lại được.
- Action: port lại lên `unified-core` (không merge `develop` cũ); giữ FE và ý tưởng contract.

**X-BF-02 · Contract API không tương thích · Severity: Cao**
- Source: `frontend/openapi.json` hai nhánh (so tự động 25/11).
- Evidence: `StrategyName` be-fe còn `A_fcfs, A_edf, B, C, D` (unified chỉ `B0, M2b, M3a, M3b`); thiếu `GET /simulation/policies`,
  `SchedulePlan.policy_id/policy_version`, `ScheduleProposal.certainty/assumptions/approvals_pending_*`, `Command.correlation_id`,
  `EventType.charge_completed/hard_limit_violated`, `StationEvent.violation_kinds/violation_booking_ids`, `BenchmarkReport.source`.
  Màn S8 `frontend/src/app/operator/simulation/page.tsx:30,118` còn `"A_edf"`, mặc định `"C"`. Ngược lại be-fe thêm 4 endpoint
  (`/resident/approvals`, `/resident/site-map`, `/resident/bookings/{id}/quote`, `/resident/notifications/read-all`) và trường
  `StationOverview.zones/grid_input_kw`, `Approval.executed/current_power_kw/effective_*`, `ChatResponse.request/booking`, `DecisionLogEntry.seq`.
- Impact: FE be-fe gọi backend Unified Core sẽ lỗi ở S8 và không thấy sự kiện an toàn mới; backend Unified Core thiếu 4 endpoint FE cần.
- Action: hợp nhất contract trên `unified-core` → `make openapi` → `npm run gen:api`; dùng `lib/policies.ts` đã có ở unified-core cho S8.

**X-BF-03 · Đọc DB toàn cục và phát WebSocket bên trong vòng quyết định · Severity: Cao (phá bất biến Unified Core nếu merge nguyên)**
- Commit `a32541d`. Source: be-fe `src/services/control_loop.py` `on_event` gọi `_broadcast_site_map(rt)` → `repository.list_bookings(...)`
  và `station_service.site_map_for(rt, …)` (đọc `repository.active_booking`).
- Evidence: ở Unified Core, **cùng** `on_event` chạy cho trạm live, bản sao admission và benchmark (runtime dùng `rt.store` trong RAM).
  Hàm này đọc `repository` toàn cục thay vì `rt.store` ⇒ trong bản sao / benchmark sẽ đọc booking **live**, và thêm I/O DB mỗi lần tính lại.
  HANDOFF 24/11 đã cảnh báo đúng điểm này ("đọc `rt.store`, không phát trong bản fork / benchmark").
- Counterargument: trên nền cũ (chưa có admission fork) không có vấn đề.
- Action: khi port, chỉ phát khi `rt.live`, đọc `rt.store`, đặt ngoài đường quyết định.

**X-BF-04 · Phê duyệt: ghi đè đường kiểm an toàn của `ai-4` · Severity: Cao (xung đột ngữ nghĩa giữa hai nhánh)**
- Commit `4894c5e`. Source: be-fe `control_loop.resolve_approval` gọi `dispatcher.execute_approved(decided, ctx, sim, sinks)` dưới `rt.lock`;
  `ai-4` gọi với `safety_holds=…, safety_pending=…` dưới `rt.decision_lock()`.
- Evidence: hai bản cùng sửa hàm này (xung đột văn bản). Tham số mới có giá trị mặc định ⇒ nếu giải xung đột theo bản be-fe,
  code **vẫn chạy** nhưng **mất** chặn Safety Hold khi thực thi lệnh đã duyệt (lỗi G1-F03 của `ai-4` quay lại).
- Action: khi tích hợp, giữ chữ ký `ai-4`; thêm `executed` + broadcast của be-fe; test hồi quy G1-F03 phải đạt.

**X-BF-05 · Consent / admission của đổi lịch · Severity: Trung bình**
- Commit `a912576`. Source: be-fe `charging_service.quote_change` → `_what_if(rt, ..., exclude=booking_id)` đồng bộ.
- Evidence: Unified Core: admission async, `quote` gắn `assume_consent=True` + `assumptions` / `certainty`; `change` dùng consent thật và
  fingerprint dưới `booking_lock`. be-fe không có các trường này (contract cũ).
- Action: port `quote_change` thành preview dùng admission hiện hành, ghi giả định consent như `quote`.

**X-BF-06 · `budget_kw` thực ra là trần vật lý; FE có số cứng · Severity: Trung bình**
- Commit `c7acb77`, `ddd0026`. Source: be-fe `station_service._zone_usage` dùng `rt.config.zone_cap_kw(zone)` — hàm này trả
  `physical_zone_cap_kw` (22 / 120) khi có, **không** phải ngân sách optimizer (22 / 78); `frontend/src/components/station/PowerTiers.tsx:75`
  fallback cứng `22 / 78`.
- Impact: màn vận hành hiển thị "ngân sách" DC = 120 kW (sai nghĩa, ADR-017 tách hai khái niệm).
- Action: trả cả `budget_kw` (zone_budgets) và `physical_cap_kw`; bỏ số cứng.

**X-BF-07 · Phần làm đúng · Severity: Thông tin**
- `cancel` idempotent; `Approval.executed` = kết quả kiểm Guard lần 2 (G10); sơ đồ bãi cư dân chỉ có `public_status`,
  `mine`, vị trí hàng của chính mình (G24, có test privacy); FINISHED tính là "busy" (khớp F14); bỏ `fixture.ts` sang dữ liệu live;
  `manual_assign` chuyển kiểm hợp lệ cho Guard (rule `assign_requires_vehicle_waiting_at_station` có trong Unified Core).
  44 test FE + 199 dòng test luồng backend.
- Chưa kiểm: toàn bộ màn hình khi chạy thật, `login` / trang demo có dữ liệu cứng hay không (grep thấy chuỗi "demo/mock" ở 10 file
  — chưa đọc từng file), KPI trên màn S8 (dùng KPI backend cũ).

## 5. Tương thích chéo (D)

| Chủ đề | Tình trạng |
|---|---|
| Logic trùng | Không thấy optimizer / kernel thứ hai ở cả hai nhánh. Trùng sửa: `control_loop.resolve_approval`, `dispatcher.execute_approved`, `charging_service` (X-BF-04) |
| Kiến trúc lỗi thời | be-fe: toàn bộ nền (X-BF-01). ai-4: không |
| Contract không tương thích | be-fe ↔ unified (X-BF-02). ai-4 ↔ unified: OpenAPI giống hệt; thêm bảng `decision_trace_bookings` + cột `full_payload` (migration `0004`) — be-fe không có migration, không đụng |
| Yêu cầu đã đổi | Q1 (ưu tiên WHY, AI-1 hoãn) khớp ai-4 về thứ tự, nhưng ai-4 còn ôm WHAT-IF / HOW-TO (X-AI4-04). D-6 consent ở backend: be-fe chưa biết consent parity; ai-4 không đụng |
| KPI | ai-4 ghi nhận lỗi KPI baseline (R11: `outcomes()` bỏ NOT_ARRIVED, mẫu rỗng = 1.0) — trùng R-2 / D-4 của governance; be-fe dùng KPI cũ |

**Thứ tự tích hợp đề xuất (không tự thực hiện):**
1. Human quyết C-1 (commit tài liệu governance) để các thành viên thấy baseline mới; gộp tay `CLAUDE.md` với `ai-4`.
2. Codex review độc lập riêng phần **sửa lõi an toàn G1** của `ai-4` (X-AI4-01/02); Human duyệt ⇒ đưa vào `unified-core` trước.
3. WHY service (G2) vào sau khi Tech Lead nghiệm thu G2 trên SHA của `origin`.
4. be-fe **port lại** lên `unified-core` (sau bước 2): giữ FE + contract G1–G24, viết lại backend theo admission / policy registry / sự
   kiện an toàn mới, sửa X-BF-03…06, giữ chữ ký `execute_approved` của `ai-4`.
5. AI-4 API / UI (G6) làm trên contract đã hợp nhất ở bước 4.

**Giữ / sửa / thiết kế lại:**
- Giữ: ai-4 G1 fixes (sau review), WHY service, `ActorContext`; be-fe FE screens, test FE, contract G1–G24 về ý tưởng, privacy sơ đồ bãi.
- Sửa: be-fe S8 + `StrategyName`, `budget_kw`, `quote_change`, phát WS trong `on_event`; ai-4 provenance mirror, vị trí ADR.
- Thiết kế lại: be-fe backend trên Unified Core (không merge `develop`).

## 6. Rủi ro khi tích hợp ba nhánh

1. Giải xung đột `resolve_approval` theo be-fe ⇒ mất chặn Safety Hold (X-BF-04) mà test be-fe vẫn đạt.
2. Phát WS / đọc DB trong `on_event` ⇒ bản sao admission đọc dữ liệu live (X-BF-03).
3. Merge `develop` cũ vào `unified-core` ⇒ kéo lại `src/agents`, LP A–D đã xoá.
4. FE be-fe gửi `strategy` A–D ⇒ lỗi 422 ở S8.
5. Sửa lõi an toàn của ai-4 vào mà chưa review ⇒ thay đổi hành vi an toàn chưa ai trong dự án duyệt.
6. Sprint kết thúc 26/11: AI-4 chưa có tính năng người dùng; be-fe cần port lại — không kịp cả hai nếu không ưu tiên.

## 7. Đối chiếu governance (đề xuất — không tự sửa tài liệu đã nghiệm thu)

| Mục | Đề xuất | Cần ai |
|---|---|---|
| Registry F8 (AI-4) | "CHƯA LÀM" ⇒ "ĐANG LÀM — WHY service Implemented + Tested trên nhánh `feature/ai-4` @ `4658b1f`, chưa tích hợp" | Human cho phép sửa registry |
| Registry FR19 / FR20 | Thêm giới hạn đã tái hiện: bản sao mất Safety Hold (R01), trạng thái Guard trong trace (R03), trace đầy đủ không lưu bền (R02) | như trên |
| Registry F5 | Ghi "24 hạng mục G1–G24 trên nhánh `feature/be-fe-integration` @ `b92e61a`, nền cũ, chưa tích hợp" | như trên |
| `CLAUDE.md` invariant "Không bỏ sự kiện trạm" | `ai-4` G1-F01 báo mất hard event khi drain / tràn ở baseline — **auditor chưa tự tái hiện**; cần Codex kiểm | Codex |
| Ownership | `feature/ai-4`: người phụ trách nhánh (git author) — AI-4; `feature/be-fe-integration`: người phụ trách nhánh — F5 integration; Tech Lead (Codex) — review lõi an toàn | Human xác nhận |
| Backlog | R-2 trùng ai-4 R11 (outcome ledger / KPI) ⇒ gộp, tránh hai người làm hai định nghĩa; R-6 liên quan ai-4 R07 / G1-F01 | Human |

**Quyết định Human còn chờ (mới):** H-1 cho phép đưa sửa lõi an toàn của `ai-4` vào `unified-core` sau review (X-AI4-02);
H-2 phạm vi AI-4 có gồm WHAT-IF / HOW-TO không (X-AI4-04); H-3 be-fe port lại trên `unified-core` (khuyến nghị) hay merge;
H-4 C-1 commit governance (đã chờ); H-5 cho phép cập nhật registry theo §7.

## 8. Phạm vi đã đọc / chưa đọc và giới hạn kiểm chứng độc lập

- Đã đọc: toàn bộ diff `ai-4` ngoài evidence ở mức danh sách; đọc kỹ `docs/ai4/{ADR_AI4_SCOPE,FOUNDATION_CONTRACT,PROJECT_STATE,ISSUES}.md`,
  phần đầu Master Plan và Phase 4.1 report, `dispatcher.py` diff, `charging_service.py` diff, chữ ký / import / model của `copilot/`.
  be-fe: diff `charging_service`, `control_loop`, `dispatcher`, `approval`, `station_service`, `routes.py`, `resident.py`, `zone_cap_kw`, OpenAPI hai nhánh, S8 và `PowerTiers`.
- Chưa đọc: thân `why.py` (3 216 dòng), `evidence.py`, `trace_reader.py` chi tiết; diff đầy đủ `hybrid_station.py`, `runtime.py`,
  `decision_trace.py`, `repository.py` của `ai-4`; 516 file evidence; PDF research; từng màn FE của be-fe.
- Chưa tự tái hiện: G1-F01 (mất hard event), G1-F02, R07 race.
- Codex kiểm được: dùng `refs/audit/2026-11-25/*` + `git archive` (không cần GitHub). Lệnh đã chạy:
  `git fetch origin feature/ai-4 feature/be-fe-integration develop feature/unified-core` ·
  `git merge-base` · `git rev-list --left-right --count` · `git merge-tree --write-tree --name-only` ·
  `git archive <ref> | tar -x` rồi `python -m pytest tests src/simulator/tests -q -p no:cacheprovider` (PYTHONUTF8=1, venv của repo) ·
  `npx vitest run` (be-fe, `node_modules` mượn qua junction tạm, đã gỡ) · probe `probe_issues.py` trên export `ce23136`.
- Không chứa credential / secret. Không gửi tài liệu ra dịch vụ ngoài (chỉ `git fetch` từ `origin`).
