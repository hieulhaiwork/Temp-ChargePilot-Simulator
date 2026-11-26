# Architecture Decision Records — ChargePilot

Mỗi quyết định kiến trúc lớn có một file `ADR-XXX-<tên>.md` theo cấu trúc
**Bối cảnh → Lựa chọn → Quyết định → Hệ quả** (Technical Book chương 3).
Trạng thái: `Proposed` (đề xuất, chờ nhóm/mentor), `Accepted`, `Superseded by ADR-YYY`.

| ADR | Quyết định | Trạng thái |
|---|---|---|
| [ADR-001](ADR-001-giu-langgraph-cho-f1.md) | Giữ LangGraph ReAct harness của template cho Agent F1 | Proposed — chờ mentor (PRD §11); sửa đổi một phần bởi ADR-013 |
| [ADR-002](ADR-002-guard-chokepoint.md) | Guard dispatcher là cửa duy nhất tới simulator; tách StationReader/StationActuator | Proposed — sửa đổi một phần bởi ADR-011 |
| [ADR-003](ADR-003-tham-so-trong-config.md) | Tham số mô phỏng nằm trong `config/*.yaml`, validate bằng Pydantic | Proposed — sửa đổi một phần bởi ADR-010, ADR-012 |
| [ADR-004](ADR-004-contract-first-501.md) | Skeleton contract-first: đủ schema, stub trả HTTP 501 kèm mã task | Proposed |
| [ADR-005](ADR-005-persistence-sqlalchemy-alembic.md) | Persistence: SQLAlchemy 2 + Alembic sau `services/repository.py`; SQLite local, Neon Postgres khi deploy | Proposed — nhóm đã duyệt; sửa đổi một phần bởi ADR-014 |
| [ADR-006](ADR-006-danh-tinh-jwt-resident-id-server-side.md) | Danh tính: JWT, `resident_id` phía server, WebSocket xác thực bằng bản tin đầu | Proposed — nhóm đã duyệt; sửa đổi một phần bởi ADR-014 |
| [ADR-007](ADR-007-station-runtime-va-control-loop.md) | `StationRuntime` là composition root; sự kiện xử lý ngay trong request | Proposed — nhóm đã duyệt; sửa đổi một phần bởi ADR-011, ADR-014 |
| [ADR-008](ADR-008-quy-uoc-api.md) | Quy ước API: error envelope, idempotency, versioning, `/ready` | Proposed — nhóm đã duyệt; sửa đổi một phần bởi ADR-014, ADR-020 |
| [ADR-009](ADR-009-frontend-nextjs.md) | Frontend Next.js trong `frontend/`, chỉ nhận `openapi.json` từ backend | Proposed — nhóm đã duyệt |
| [ADR-010](ADR-010-bai-hybrid-ac-dc.md) | Bãi hybrid AC + DC; fixture nền `mvp1`; ràng buộc ba tầng; `supply_mode` shared / independent | Proposed — chờ nhóm và mentor |
| [ADR-011](ADR-011-mot-simulator-sau-be-mat-cong-khai.md) | Một `HybridSimulator` sau `src/simulator/base.py` + `SimulatorGateway`; một bộ `Algorithms` cho live / benchmark / what-if; Guard hai lớp | Proposed — sửa đổi một phần bởi ADR-016, ADR-019 |
| [ADR-012](ADR-012-mot-danh-muc-xe-va-kich-ban.md) | Một danh mục xe (provenance theo từng trường) và mọi kịch bản trong `config/scenarios/` | Proposed — chờ nhóm |
| [ADR-018](ADR-018-backend-chay-engine-simulator.md) | Backend chạy engine simulator R&D: `HybridStation` + thuật toán B0 / M2b / M3a / M3b; simulator là gốc | Proposed — chờ nhóm; thay phần quyết định của ADR-016; điểm 4 sửa đổi bởi ADR-019 |
| [ADR-019](ADR-019-unified-core-hop-dong-dung-chung.md) | Unified Core: hợp đồng core thuần ở `src/models`, một lõi vật lý + một nguồn thuật toán cho backend và standalone; di chuyển theo phase có shim + hash AST | Proposed — người phụ trách duyệt Phase 0–1 |
| [ADR-013](ADR-013-workflow-xac-dinh-llm-hai-dau.md) | Workflow xác định là xương sống; LLM chỉ ở hai đầu; LangGraph cho hội thoại + HITL | Proposed — chờ nhóm |
| [ADR-014](ADR-014-decision-trace-counterfactual-hitl.md) | DecisionTrace, counterfactual không bao giờ apply, vòng đời đề nghị HITL (AI-4, AI-1), Copilot theo role, job nền | Proposed — chờ nhóm |
| [ADR-015](ADR-015-pham-vi-mvp4-va-quy-tac-bang-chung.md) | Phạm vi MVP-4, hạng mục hoãn (F6/F12, F13, HOW-TO, AI-2 ML, AI-3) và quy tắc bằng chứng | Proposed — chờ nhóm |
| [ADR-016](ADR-016-livestation-cho-backend.md) | `LiveStation` — simulator chạy liên tục cho backend; HybridSimulator giữ vai trò R&D offline | Proposed — chờ nhóm; sửa đổi một phần ADR-011; **bị thay bởi ADR-018, rồi ADR-019 (LiveStation đã xoá)** |
| [ADR-017](ADR-017-guard-theo-hop-dong-an-toan-simulator.md) | Guard backend dùng cùng hợp đồng an toàn vật lý với HybridSimulator (trần vùng thiết bị, nguồn độc lập, chỉ cấp điện / gán xe hợp lệ) | Proposed — chờ nhóm; sửa đổi bởi ADR-019 (Guard → `src/guard/physical/`) |
| [ADR-020](ADR-020-chuan-hoa-restful-api.md) | Chuẩn hoá RESTful API trên `/api/v1` (HTTP methods, danh từ số nhiều, `201`/`Location`, `204`, pagination envelope) | Proposed — sửa đổi một phần ADR-008 |

Quy tắc: đổi một quyết định thì viết ADR mới đánh dấu `Superseded`, không sửa lịch sử.
Sửa đổi một phần thì ghi rõ ở đầu ADR cũ, trỏ tới ADR mới; phần quyết định gốc giữ nguyên.
Mọi con số trong ADR phải trỏ tới `eval/evidence/` (ADR-015).
Nới ranh giới trong `tests/test_architecture.py` cũng phải có ADR.

---

## Phân loại quyết định (triage 2026-11-24)

> Soạn bởi Implementation Agent; review độc lập lần 1: `docs/handoff/REVIEW_PHASE1_RESULT.md` (K14 MỘT PHẦN); sửa
> 2026-11-25 theo review (`docs/handoff/REMEDIATION_PHASE1.md`), **chưa Re-review**. **Agent không duyệt ADR nào.**
> Cả 19 ADR có header `Proposed`; không ADR nào `Accepted`. Tuy vậy một số ADR **có ghi lịch sử duyệt một phần** trong
> chính file (cột "Lịch sử duyệt" dưới đây) — chưa xác thực với hội thoại gốc, không tự chuyển thành `Accepted`, cũng
> không được xoá. Code đã chạy theo ADR **không** có nghĩa ADR đã được duyệt. Đối chiếu code tại commit `ce23136`.

Nhóm: **A** quyết định nghiệp vụ, cần Human Supervisor · **B** kỹ thuật thường, có thể uỷ quyền Tech Lead ·
**C** kỹ thuật ảnh hưởng lớn, cần review độc lập trước khi duyệt · **D** lỗi thời / bị thay · **E** đã chạy trong code
nhưng chưa duyệt chính thức (cờ phụ, đi kèm nhóm chính).

| ADR | Nội dung (dễ hiểu) | Nhóm | E? | Lịch sử duyệt ghi trong file ADR | Ghi chú đối chiếu code |
|---|---|---|---|---|---|
| 015 | Phạm vi sprint: làm gì, hoãn gì | **A** | một phần | **Human 25/11 (Q1):** APPROVED ưu tiên AI-4 WHY; DEFERRED AI-1 đầy đủ | Phần hoãn đang có hiệu lực; phần "Làm" (AI-1, AI-4) chưa có code |
| 010 | Mô hình bãi: 2 AC 11 kW + 2 DC 60 kW, lưới 106 kW, giả định nguồn | **A** | ✓ | **Human 25/11 (Q2):** APPROVED như giả định mô phỏng có nhãn | Đúng với `config/station.yaml`; mọi KPI phụ thuộc |
| 018 | Backend chạy engine simulator; **policy mặc định M3a** | **A** (chọn policy) + **C** (kỹ thuật, **chưa review độc lập**) | ✓ | "nhóm chốt hướng 23/11"; **Human 25/11 (Q3):** M3a PROVISIONAL, xét lại sau R-2 / R-3; (D-6) consent ở backend PROVISIONAL | Mặc định M3a đúng trong code |
| 013 | LLM chỉ ở hai đầu; số liệu không đến từ LLM | **A** | một phần | **Human 25/11 (Q4):** APPROVED nguyên tắc | Đầu vào có; kiểm số kWh / cổng có; đầu ra AI-4 chưa |
| 014 | Trace lý do, thử giả định không bao giờ áp, vòng đời đề nghị AI-1, quyền theo vai trò | **A** (vòng đời, quyền) + **C** (**chưa review độc lập**) | một phần | **Human 25/11 (Q4):** APPROVED nguyên tắc quyền / vòng đời; chi tiết kỹ thuật chưa duyệt | Trace có; đề nghị / bảng AI-1 chưa |
| 002 | Một cửa duy nhất gửi lệnh tới trạm | **C** | ✓ | — | Test kiến trúc khoá |
| 017 | Hợp đồng an toàn vật lý của Guard (trần vùng 22 / 120 kW, không cấp điện sai) | **C** | ✓ | — | Đúng với `src/guard/physical/` |
| 019 | Unified Core: một lõi cho backend và simulator | **C** | ✓ | người phụ trách duyệt hướng + Phase 0–1 (23/11); Phase 2+ theo từng phase | Đã nghiệm thu nội bộ, Tech Lead (Codex) review; chưa ghi duyệt Phase 2+ |
| 006 | Danh tính JWT, `resident_id` phía server | **C** (bảo mật) | ✓ | nhóm duyệt 17/11, chờ mentor | Có test 401 / 403 |
| 001 | Giữ LangGraph cho chat | B | ✓ | — | Chờ mentor về template |
| 003 | Tham số trong `config/*.yaml` | B | ✓ | — | |
| 004 | Contract-first, chưa làm thì trả 501 | B | ✓ | — | Chỉ còn dự báo dùng 501 |
| 005 | SQLAlchemy + Alembic | B | ✓ | nhóm duyệt 17/11, chờ mentor | Nhóm duyệt 17/11 (chưa mentor) |
| 007 | `StationRuntime` nối mọi phần | B | ✓ | nhóm duyệt 17/11, chờ mentor | Nội dung `LiveStation` trong ghi chú đã lỗi thời |
| 008 | Quy ước API, envelope lỗi | B | ✓ | nhóm duyệt 17/11, chờ mentor | Mã lỗi AI-1 (ADR-014 §8) chưa có |
| 009 | Frontend Next.js | B | ✓ | nhóm duyệt 17/11, chờ mentor | |
| 012 | Một danh mục xe + kịch bản | B | ✓ | — | |
| 011 | Một simulator sau `base.py` + `SimulatorGateway` | **D** (phần lớn) | — | — | `base.py`, `SimulatorGateway` không tồn tại; thay bằng `StationKernel` (ADR-019). Phần "một bộ thuật toán cho live / benchmark / what-if" đúng ở Planning Core; backend thêm bước consent sau đó (registry §4, D-6) |
| 016 | `LiveStation` cho backend | **D** | — | người phụ trách chọn 22/11; bị thay | Đã xoá; bị thay bởi 018 → 019 |

Nhóm C gồm **6** ADR: 002, 006, 017, 019 (đã review kỹ thuật lần 1, SUPPORTED / VERIFIED — `REVIEW_PHASE1_RESULT.md`) và
phần C của 014, 018 (**chưa** review). Đề xuất xử lý: B → Tech Lead duyệt một lượt, báo kết quả. C → review độc lập theo
[`docs/handoff/REVIEW_PHASE1.md`](../handoff/REVIEW_PHASE1.md) rồi mới duyệt. D → Tech Lead ghi `Superseded` (011 một
phần, 016 toàn phần), không cần Human Supervisor. A → bốn quyết định dưới đây.

### Quyết định của Human Supervisor (2026-11-25)

Ghi theo chỉ thị của Human trong phiên Claude Code 2026-11-25, sau Technical Acceptance PASS
(`docs/handoff/REREVIEW_PHASE1_RESULT.md` §T0–T5). **Không đổi header của file ADR nào**: cả 19 ADR vẫn `Proposed`;
quyết định dưới đây là quyết định về **nội dung / hướng**, chưa phải chuyển trạng thái file ADR sang `Accepted`.
Nhãn: **APPROVED** đã duyệt · **PROVISIONAL** tạm giữ, có điều kiện xét lại · **DEFERRED** hoãn, có điều kiện mở lại.

| # | ADR | Quyết định | Nhãn | Điều kiện xét lại / mở lại |
|---|---|---|---|---|
| Q1 | 015 | Ưu tiên AI-4 WHY | APPROVED | — |
| Q1 | 015 | AI-1 Negotiation đầy đủ: hoãn, **không** loại khỏi roadmap | DEFERRED | Khi phạm vi và năng lực triển khai được đánh giá |
| Q2 | 010 | Giữ bãi 2 AC 11 kW + 2 DC 60 kW, lưới 106 kW như **giả định mô phỏng có nhãn**; không tuyên bố là dữ liệu VinFast / Vinhomes | APPROVED | Khi có thông số thật hoặc đổi topology |
| Q3 | 018 | M3a là policy mặc định **tạm thời**; giữ B0 / M2b / M3a / M3b version `"1"` | PROVISIONAL | Sau R-2 và R-3 |
| Q4 | 013, 014 | Nguyên tắc: AI dựa trên facts / trace; quyền kiểm phía server; không tự thay đổi cam kết; không apply kết quả sandbox khi chưa được phép | APPROVED (nguyên tắc) | Chi tiết kỹ thuật ADR-013 / 014 chưa duyệt |
| D-6 | 018 (Hệ quả) | Consent tạm giữ ở backend; không đổi frozen policies | PROVISIONAL | Sau R-4 |

Các quyết định khác cùng ngày (D-3, D-4, D-5, C-3, G-auto, backlog R-1…R-6): `docs/FEATURE_REGISTRY.md` §6, §6.1 và
`docs/handoff/HANDOFF.md` §1.5. Brief Q1–Q4 dưới đây giữ nguyên làm **lịch sử** căn cứ quyết định.

### Quyết định cần Human Supervisor (lịch sử brief 24/11 — đã quyết 25/11, xem mục trên)

Thứ tự theo phụ thuộc: Q1 quyết định phạm vi, Q4 chỉ có ý nghĩa nếu Q1 giữ AI-1 / AI-4; Q3 phụ thuộc Q2 và việc làm
rõ kịch bản (registry I-1).

**Q1 — Phạm vi sprint (ADR-015)**
- *Vấn đề:* sprint kết thúc 26/11. ADR-015 ghi hai tính năng AI chính (AI-4 giải thích, AI-1 thương lượng) là "Làm",
  nhưng chưa có dòng code nào (`src/agents/` rỗng, chưa có bảng dữ liệu cho AI-1).
- *Quyết định hiện tại:* làm cả hai; hoãn dự báo, mô hình mức linh hoạt, HOW-TO tối ưu, AI-2 ML, AI-3.
- *Vì sao từng chọn:* nghiên cứu SC-16 kết luận giá trị AI nằm ở giải thích + thương lượng, không ở dự báo.
- *Phương án:* (a) giữ nguyên; (b) thu hẹp: chỉ AI-4 "vì sao" trên trace đã có, AI-1 hoãn; (c) dời mốc sprint.
- *Tác động:* (a) rủi ro cao không kịp, demo thiếu AI; (b) có một tính năng AI chạy thật, mất phần thương lượng;
  (c) lệch lịch BTC.
- *Hoàn tác:* dễ (quyết định phạm vi, chưa có code).
- *Agent đề xuất:* (b). Căn cứ: trace lý do đã có và đã test (`tests/test_services/test_decision_trace.py`), nên AI-4
  "vì sao" dựng trên nền có sẵn; AI-1 cần bảng mới, vòng đời phê duyệt và nhiều lần mô phỏng mỗi đề xuất.

**Q2 — Mô hình bãi và giả định nguồn (ADR-010)**
- *Vấn đề:* mọi con số (đúng hạn, chi phí, an toàn) tính trên một bãi giả định. Bãi này chưa được nhóm / mentor duyệt.
- *Quyết định hiện tại:* 2 AC × 11 kW + 1 tủ DC 2 × 60 kW (trần tủ 120 kW), lưới 106 kW; đánh dấu [GIẢ ĐỊNH].
- *Vì sao:* bám loại trụ quan sát được; tạo tình huống thiếu điện thật sự (142 kW > 106 kW).
- *Phương án:* (a) duyệt như "giả định mô phỏng có nhãn"; (b) quay về bãi cũ 8 × 7 kW / 35 kW (PRD v0.2);
  (c) chờ thông số thật.
- *Tác động:* (b) / (c) phải chạy lại toàn bộ benchmark, sửa config và test.
- *Hoàn tác:* tốn công (baseline, golden test, tài liệu).
- *Agent đề xuất:* (a). Căn cứ: code, config, 100 run baseline đã nhất quán với bãi này
  (`eval/evidence/2026-11-24-unified-core-frozen-baseline/`).

**Q3 — Chính sách điều phối mặc định (ADR-018 §2)**
- *Vấn đề:* trạm chạy policy M3a. Trên baseline đóng băng (LỊCH SỬ @`a9def2f`, trung bình 25 run / policy): M3a có
  **tổng tiền** thấp nhất (~685k VND) và đúng hạn thấp nhất (29,1%); M3b đúng hạn cao nhất (32,1%), tổng tiền cao nhất
  (~775k) nhưng giao nhiều điện hơn, nên **tính theo kWh đã giao M3b rẻ nhất** (2 328 vs M3a 2 389 VND/kWh). Trên 40 run
  đúng bãi hiện tại (`hybrid_*`) M3a và M3b gần bằng nhau (~2 360 VND/kWh; đúng hạn 43,7% vs 44,3%).
  Baseline này có tải vượt năng lực vật lý và bỏ sót sự cố hỏng cổng (registry §3.1) ⇒ **chưa đủ căn cứ chọn policy**.
  Lý do gốc trong HANDOFF so với A_edf, mà A_edf đã bị xoá.
- *Quyết định hiện tại:* M3a.
- *Phương án:* (a) giữ M3a (ưu tiên chi phí); (b) M3b (ưu tiên đúng hạn); (c) giữ M3a tạm, quyết lại sau khi có bộ
  kịch bản khả thi (registry I-1, D-4).
- *Tác động:* đổi một khoá cấu hình (`planning.policy_id`), không đổi code.
- *Hoàn tác:* dễ.
- *Agent đề xuất:* (c). Căn cứ: so sánh hiện có không cùng mức phục vụ, không ghép cặp, trên workload không khả thi;
  cần đo trên kịch bản khả thi, ghép cặp theo kịch bản / seed (task R-2, R-3 — chưa giao).

**Q4 — Nguyên tắc tin cậy của AI (ADR-013, ADR-014 phần vòng đời / quyền)**
- *Vấn đề:* quy định AI được làm gì với người dùng: LLM không tạo số liệu, thử giả định không bao giờ tự áp, đề xuất
  thay đổi phải qua người đồng ý, cư dân chỉ thấy xe của mình.
- *Quyết định hiện tại:* như trên; đã thực thi một phần ở chat (kiểm số kWh / cổng).
- *Phương án:* (a) duyệt nguyên tắc ngay, chi tiết kỹ thuật để Tech Lead; (b) duyệt sau khi có AI-1 / AI-4.
- *Tác động:* (a) là ràng buộc rõ cho agent khi viết AI-4 / AI-1.
- *Hoàn tác:* dễ trước khi có code; khó sau khi giao diện hiển thị cho người dùng.
- *Agent đề xuất:* (a), chỉ phần nguyên tắc. Liên quan: mâu thuẫn chế độ offline ở production (registry D-3).
