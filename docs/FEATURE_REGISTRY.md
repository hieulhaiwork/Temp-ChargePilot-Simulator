# Feature Registry — ChargePilot (nguồn tham chiếu chính thức cho chức năng)

> **Vai trò:** đây là bảng duy nhất trả lời "chức năng X đã làm tới đâu, bằng chứng nào". Bảng truy vết cũ trong
> `ARCHITECTURE.md` và phần "hiện trạng" của `docs/PRD.md` trỏ về đây. PRD vẫn là nguồn **yêu cầu** (cần làm gì);
> registry là nguồn **hiện trạng** (đã làm gì, chứng minh bằng gì). Khi registry mâu thuẫn với code: code đúng, sửa
> registry.
>
> **Hệ mã:** dùng mã của PRD v0.4 (F1–F15, FR1–FR46, MT, AC). Mã cũ chỉ còn trong code / test / kế hoạch cũ; tra ở §1.
> **Chỉ chuẩn hoá trong tài liệu** — tên trong source code, API, database, test giữ nguyên (chưa được duyệt đổi).
>
> **Mốc bằng chứng:** code tại commit `ce23136` (nhánh `feature/unified-core`; cây làm việc chỉ khác ở tài liệu).
> Chạy lại ngày 2026-11-24 bởi agent soạn registry: backend 604 đạt / 8 bỏ qua / 0 lỗi; simulator 180 đạt;
> frontend 30 đạt. Môi trường: Windows, SQLite tạm, LLM giả lập (mock) — xem §0.
>
> **Người soạn:** Implementation Agent (Claude), 2026-11-24. Review độc lập lần 1 (Codex, 24/11):
> [`docs/handoff/REVIEW_PHASE1_RESULT.md`](handoff/REVIEW_PHASE1_RESULT.md) — chưa đủ điều kiện đóng (F1–F5).
> **Remediation 2026-11-25** (Claude, chỉ sửa tài liệu, code vẫn `ce23136`): bằng chứng từng phát hiện ở
> [`docs/handoff/REMEDIATION_PHASE1.md`](handoff/REMEDIATION_PHASE1.md). **Bản sửa chưa được Re-review.**

## 0. Cách đọc nhãn

**Trạng thái công việc:** `CHƯA LÀM` · `ĐANG LÀM` · `MỘT PHẦN` (có code cho một phần yêu cầu) · `ĐANG HOÃN` · `BỊ CHẶN`
· `XONG`.

**Mức bằng chứng** (tối đa mà chức năng đạt được): `Planned` → `Implemented` → `Tested` → `Validated` → `Deployed`.
- `Tested` = có test tự động chạy đạt. **Không** có nghĩa là đáp ứng yêu cầu nghiệp vụ.
- `Validated` = đã đối chiếu với tiêu chí nghiệm thu PRD §8 trên điều kiện nghiệm thu (dữ liệu / dịch vụ thật nếu tiêu
  chí đòi). **Hiện chưa chức năng nào đạt `Validated`**: chưa có lần nghiệm thu nào theo PRD §8 có người duyệt.

**Loại bằng chứng test:**

| Nhãn | Nghĩa |
|---|---|
| `ĐẠT 24/11` | Test tồn tại và chạy đạt trong lần chạy 2026-11-24 @ `ce23136` |
| `MOCK` | Chạy đạt nhưng với thành phần giả: LLM giả lập (`tests/conftest.py`), SQLite tạm thay Postgres |
| `THẬT` | Chạy với dịch vụ / dữ liệu thật (LLM thật, Postgres thật, bản deploy). **Hiện: không có** |
| `CHƯA CHẠY` | Test / kiểm tra tồn tại nhưng không chạy trong lần kiểm chứng này (vd. job Postgres chỉ chạy trên CI) |
| `BỎ QUA` | Test bị `skip` có lý do |
| `KHÔNG TEST` | Có code, không tìm thấy test kiểm đúng yêu cầu |
| `KHÔNG CODE` | Chưa có implementation |
| `LỊCH SỬ @<commit>` | Số liệu lấy từ báo cáo / evidence cũ, **không** chạy lại hôm nay |

Lưu ý phạm vi: sản phẩm là **mô phỏng** (PRD §2). "Trạm" trong mọi test là trạm mô phỏng — đó là đúng phạm vi, không
tính là mock. Mock chỉ nói về LLM và database.

CI: lần chạy CI gần nhất trên `develop` (`68692ee`, 22/11) **thất bại** ở job frontend, các job khác bị huỷ theo.
Nhánh `feature/unified-core` chưa có lần chạy CI nào. Kiểm tra bằng `gh run list` ngày 24/11.

---

## 1. Ánh xạ hệ mã

Ba hệ mã đang tồn tại song song:
- **PRD v0.4** (21/11, `docs/PRD.md`): F1–F15, FR1–FR46. Đây là hệ chuẩn.
- **Skeleton / plan cũ** (16–19/11, `docs/plan/*`, bảng truy vết cũ của `ARCHITECTURE.md`, docstring trong code và
  test): dùng lại một số số F / FR với nghĩa khác.
- **Task ID** `T1.1`…`T4.5` (`docs/plan/00-overview.md`): mã công việc, vẫn xuất hiện trong code (`NotImplementedError`,
  `skip`). Không phải mã chức năng.

### 1.1 Mã trùng nhưng khác nghĩa (nguy cơ hiểu sai cao)

| Mã | Nghĩa trong PRD v0.4 (chuẩn) | Nghĩa cũ (còn trong code / plan / test) | Nơi còn nghĩa cũ |
|---|---|---|---|
| **F6** | DecisionTrace + Counterfactual sandbox | Dự báo giờ rút đầu nối (LightGBM) = **F12** mới | `src/forecast/*`, `tests/test_forecast/*`, `docs/plan/00-overview.md`, `docs/plan/30-ai.md`, `src/main.py` |
| **F7** | AI-1 thương lượng xung đột | Màn benchmark / kịch bản S8 = **F9** mới | `docs/plan/21-ui-spec.md`, docstring `src/api/simulation.py`, `src/services/simulation_service.py`, `src/models/simulation.py`, `src/models/charging.py` |
| **F8** | AI-4 Decision Copilot | Hồ sơ cư dân (xe mặc định, mức pin, đồng ý trước) = **F10** mới | `src/db/tables.py`, `src/models/api.py`, `src/api/resident.py`, `src/services/{auth,charging_service,repository}.py`, `docs/plan/10-backend.md`, `20-frontend.md`, `21-ui-spec.md`, `40-database.md` |
| **FR12** | Simulator | 7 luật Guard = **FR13** mới | `ARCHITECTURE.md` (đã thay bảng), `docs/plan/*` |
| **FR13** | Guard hai lớp | Phê duyệt / "đồng ý trước" = **FR15** mới | như trên |
| **FR14** | Bảo vệ khẩn cấp | Nhật ký quyết định = **FR16** mới | như trên |
| **FR15–16** | HITL ba mức · Nhật ký | Web hai vai trò + WebSocket = **FR17–18** mới | như trên |
| **FR17** | Web cư dân | Dự báo F6 = **FR34–37** mới (đã hoãn) | `ARCHITECTURE.md` cũ, `src/forecast/` |
| **FR18** | Web vận hành | Sự cố + đối chứng = **FR10 + F9** mới | như trên |
| **FR4** | Tiếp nhận bằng lời | Phương án thay thế khi không kịp = nay nằm trong **FR4** mới (ScheduleProposal) | `ARCHITECTURE.md` cũ |
| **FR5** | Tách dispatch khỏi lập lịch | Agent không ra lệnh trạm (ranh giới import) = **FR31** mới + ADR-002 | `ARCHITECTURE.md` cũ, ranh giới `src/agents` |
| **FR6** | AC Optimizer | "tối ưu công suất" chung = **FR6 + FR7** mới | như trên |
| **FR7** | DC Optimizer | Gán đầu nối, hàng chờ = **FR5** mới | như trên |
| **FR8** | Global Coordinator | Tính lại khi có sự kiện = **FR11** mới | `docs/architecture_diagram.md` cũ ("Luồng FR8") |
| **FR9** | Chỉ dùng thông tin đã biết tại T | Deadline là ràng buộc cứng (vẫn đúng, nay nằm trong FR9 + FR35) | `tests/test_forecast/test_forecast_contracts.py` (skip `[T2.1] FR9`) |
| **FR10–11** | Giới hạn động / sự cố · Tính lại khi có sự kiện | "Cân bằng tải, simulator" = **FR8 + FR12** mới | `ARCHITECTURE.md` cũ (dòng truy vết FR10–11), `docs/plan/*` |
| **AC1–AC8** | Tiêu chí nghiệm thu PRD §8 (AC1–AC17) | AC1 cũ đặt lịch qua chat = AC1 mới · AC2 cũ hết đầu nối = AC2 mới · AC3 cũ cao điểm 35 kW = AC3 mới (topology khác) · AC4 cũ phê duyệt = FR15 (không có AC riêng) · AC5 cũ khẩn cấp = **AC4** mới · AC6 cũ 7 luật Guard = **AC11** mới · AC7 cũ sự cố + đối chứng = **AC13** mới · AC8 cũ deploy = **AC14** mới | `docs/architecture_diagram.md` cũ, `docs/plan/*`, header `config/scenarios/*.yaml` |
| **MT5 / MT7** | MT5 quyết định nhanh · MT7 AI-1 | MT7 cũ = giá trị dự báo F6 (= MT10 mới, đã hoãn) | `ARCHITECTURE.md` cũ |

**Quy tắc từ nay:** tài liệu mới chỉ dùng mã PRD v0.4. Khi buộc phải nhắc mã cũ (vì code còn dùng), ghi dạng
"F6 cũ (= F12)". Đổi tên trong code / test: **DEFERRED** (Human 25/11, §6 D-5).

### 1.2 Task ID → chức năng (các task còn xuất hiện trong code)

| Task | Nội dung | Chức năng PRD v0.4 | Trạng thái |
|---|---|---|---|
| T1.3 | Tải, chuẩn hoá dữ liệu phiên sạc | F12 (dự báo) | ĐANG HOÃN (ADR-015, chưa duyệt) |
| T2.3 | Feature, train, evaluate dự báo | F12 | ĐANG HOÃN |
| T2.1 | Tối ưu công suất | F2 (FR6–FR8) | XONG ở mức Tested (thuật toán MVP-2/3) |
| T2.2 | Gán cổng, hàng chờ, quote / book / cancel, idempotency | F1, F2 (FR4, FR5) | Tested |
| T2.5 | Agent chat sạc | F1 (FR4) | Tested với LLM giả lập |
| T2.6 | Vòng sự kiện, tính lại | F3 (FR11) | Tested |
| T2.8 | Đổi yêu cầu, hồ sơ cư dân | F1, F10 | Tested (API) |
| T3.1–T3.2 | Luật Guard, phê duyệt, khẩn cấp | F4 (FR13–FR15) | Tested |
| T3.4–T3.5 | Benchmark, kịch bản sự cố | F9, F3 (FR10) | Tested + LỊCH SỬ |
| T3.6 | API vận hành, WebSocket, dashboard | F5 (FR18) | MỘT PHẦN |
| T3.7 | Đo thời gian tính lại | MT5 | LỊCH SỬ (benchmark) |
| T4.2 | Eval Agent ≥ 50 câu | MT9 | Chỉ offline / mock |

---

## 2. Registry chức năng

| ID | Chức năng (dễ hiểu) | Ưu tiên PRD | Trạng thái | Mức bằng chứng | Rủi ro / giới hạn chính |
|---|---|---|---|---|---|
| **F1** | Cư dân gửi yêu cầu sạc (form hoặc chat), hệ thống tính điện cần nạp | Must | MỘT PHẦN | Tested (`MOCK` LLM) | Chưa từng chạy với LLM thật; FR4a (nói mục đích chuyến đi) chưa có code |
| **F2** | Xếp xe vào cổng và chia công suất tối ưu (AC, DC, điều phối hai vùng) | Must | XONG (theo yêu cầu kỹ thuật) | Tested | Tỷ lệ đúng hạn 29–32% trên baseline (LỊCH SỬ) **không đo được MT1**: workload vượt năng lực vật lý (đã chứng minh cho seed 1), 60/100 run là kịch bản legacy — xem §3.1, I-1 |
| **F3** | Phản ứng khi giới hạn điện thay đổi / sự cố, tính lại ngay | Must | XONG (theo yêu cầu kỹ thuật) | Tested | Chỉ mô phỏng; nhiều worker chưa hỗ trợ |
| **F4** | Cổng kiểm soát an toàn (Guard) + phê duyệt của người + nhật ký | Must | MỘT PHẦN | Tested | Phê duyệt theo phạm vi đồng ý đã có; vòng đời đề nghị của AI-1 và bảng audit đầy đủ (FR16) chưa có |
| **F5** | Web cho cư dân và vận hành | Must | MỘT PHẦN | Tested (30 test đơn vị FE) | Nhánh nối giao diện chưa gộp; CI frontend trên `develop` đỏ (22/11); thiếu thẻ đề nghị AI-1, ô Copilot |
| **F6** | Ghi lại lý do mỗi quyết định (DecisionTrace) + thử giả định cách ly (sandbox) | Must | MỘT PHẦN | Tested (phần trace) | Trace có; sandbox chỉ dùng nội bộ cho báo giá; Patch có schema (FR21) chưa có |
| **F7** | AI-1: phát hiện xe sắp trễ, đề xuất thay đổi, xin chủ xe đồng ý | Must | **ĐANG HOÃN** (Human 25/11, Q1 — không loại khỏi roadmap) | Planned | Mở lại khi phạm vi và năng lực triển khai được đánh giá (§6) |
| **F8** | AI-4: trả lời "vì sao" và "nếu… thì sao" dựa trên trace | Must | CHƯA LÀM — **ưu tiên WHY** (Human 25/11, Q1) | Planned | Chỉ có API giải thích đơn giản từ nhật ký (`/resident/explanation`), không phải Copilot |
| Lớp LLM | LLM chỉ ở hai đầu, kiểm từng câu với dữ kiện, chạy được khi không có LLM | Must | MỘT PHẦN | Tested (`MOCK`) | Kiểm dữ kiện (FR32) mới kiểm số kWh / mã cổng, chưa kiểm từng câu; chế độ offline mâu thuẫn với cấu hình production (§6, D-3) |
| **F9** | Benchmark so sánh chính sách trên kịch bản sự cố | Should | XONG (công cụ) | Tested + LỊCH SỬ @`a9def2f` | Baseline đóng băng 100 run = **regression refactor**, không phải nghiệm thu: 40/160 sự cố bị bỏ (toàn bộ hỏng cổng), 3/5 kịch bản legacy, `connector_failure` trùng KPI `peak_evening` (§3.1) |
| **F10** | Cá nhân hoá (xe mặc định, mức pin, phạm vi đồng ý) | Could | MỘT PHẦN | Tested (service) | `test_service_contracts.py::test_profile_update_and_unknown_vehicle` ĐẠT 24/11; màn hồ sơ trên web chưa kiểm |
| **F11** | AI-2 cảnh báo dữ liệu bất thường (luật) | Could | CHƯA LÀM | — | — |
| **F12** | Dự báo hành vi (giờ rời, đỗ quá giờ) — "F6 cũ" | Hoãn | ĐANG HOÃN | Planned (8 stub, 8 test bỏ qua) | Quyết định hoãn (ADR-015) chưa được duyệt chính thức |
| **F13** | Mô hình mức linh hoạt theo người | Hoãn | ĐANG HOÃN | — | — |
| **F14** | Hiển thị cổng bị chiếm sau khi sạc xong | Should | MỘT PHẦN | Tested (mô phỏng) | Simulator giữ xe đầy trên cổng: AC tới giờ rời, DC rút sau độ trễ (test ở §3.2 FR42–44). Tên `FINISHED_PLUGGED` chỉ có ở model; kernel dùng `FINISHED`. Hiển thị cho vận hành (FR43) và đo MT12 **chưa kiểm** |
| **F15** | Cảm biến ô đỗ (mô phỏng) | Could | CHƯA LÀM | — | — |

Ngoài PRD nhưng có trong code (có mục đích rõ, ghi để không bị coi là "thừa"): đăng ký policy mới cho nghiên cứu
MVP-3.5 (`src/optimizer/registry.py`); chọn mô hình sạc DC (`DC_MODELS`); fail-safe sau khi áp lệnh; khoá đặt chỗ đồng
thời. Các phần này phục vụ F2 / F4 / F9.

---

## 3. Truy vết yêu cầu nghiệp vụ → chức năng → code → test → bằng chứng

### 3.1 Mục tiêu nghiệp vụ (PRD §7) → chức năng → bằng chứng hiện có

| Mục tiêu | Chức năng | Ngưỡng PRD | Bằng chứng hiện có | Kết luận |
|---|---|---|---|---|
| MT1 đủ pin đúng hạn | F2, F3 | ≥ 95% trong kịch bản khả thi | LỊCH SỬ @`a9def2f`: đúng hạn TB 29,1–32,1% / policy (macro-average tỷ lệ từng run, 25 run / policy). Theo kịch bản: legacy 18,5–24,6%; hybrid 41,2–47,5% | **Không đo được MT1 bằng baseline này.** (1) Mẫu số chỉ là xe "khả thi từng xe" (`_is_feasible`: công suất tối đa × giờ ≥ kWh), không xét cạnh tranh cổng / nguồn / DC taper; không có xe nào khả thi ⇒ tỷ lệ = 100%. (2) Workload vượt năng lực: `peak_evening` seed 1 cần 1 183 kWh AC > 840 kWh (35 kW × 24 h); `hybrid_evening` seed 1 cần 676 kWh AC > 528 kWh (2 × 11 kW × 24 h). (3) Booking tổng hợp `CONFIRMED` không qua admission. (4) Định nghĩa đúng hạn của backend (năng lượng tới deadline) khác simulator (`completed_at ≤ departure`, audit B4). **Nguyên nhân** tỷ lệ thấp: chưa phân rã. Cận năng lượng chỉ chứng minh không thể giao đủ **mọi kWh** của hai workload ví dụ; quá tải là yếu tố INFERRED (hợp lý, chưa định lượng); không chứng minh MT1 95% số xe là không đạt được. Đóng góp từng nguyên nhân: UNVERIFIED (I-1, task R-2) |
| MT2 giảm chờ | F2, F14 | thấp hơn FCFS mỗi vùng | LỊCH SỬ: chờ TB ~392 phút, gần như bằng nhau giữa các policy | Chưa kết luận. Cách đo: xe **chưa từng cắm** được tính chờ tới deadline (censored, `compute_kpis:132–134`), nên con số **không** phải thời gian chờ của riêng xe được phục vụ. Chưa phân rã đóng góp của quá tải, hàng chờ, giữ cổng, mục tiêu chi phí — **không** kết luận nguyên nhân (UNVERIFIED, task R-2) |
| MT3 chi phí | F2 | so với B0 **ở mức phục vụ tương đương** (PRD §7.1) | LỊCH SỬ: tổng tiền TB M3a 685k < B0 722k < M2b 730k < M3b 775k VND; **theo kWh đã giao**: M3b 2 328 < M3a 2 389 < M2b 2 548 < B0 2 553 VND/kWh (M3b giao nhiều điện nhất: 333 vs 287 kWh) | **Chưa so được** theo đúng ngưỡng PRD: các policy giao lượng điện khác nhau. "M3a rẻ nhất" chỉ đúng cho tổng tiền; không dùng để chọn policy (D-2, task R-3) |
| MT4 an toàn công suất | F3, F4 | 0 vi phạm áp dụng, **mọi kịch bản** | LỊCH SỬ: 0 vi phạm áp dụng, 0 phút vượt trần, 0 phân bổ bị từ chối / 100 run; 14 lệnh bị Guard chặn. **Nhưng** sự cố: 160 kế hoạch / 120 áp / **40 bị bỏ** (mọi hỏng cổng `A05` của `connector_failure`, không khớp topology). ĐẠT 24/11: test Guard + fail-safe | Đạt **cho tải đã thực chạy** trên mô phỏng. **Chưa** chứng minh phản ứng hỏng cổng trong benchmark (task R-1); chỉ có test đơn vị / tích hợp |
| MT5 quyết định nhanh | F2 | p95 ≤ 2 s | LỊCH SỬ: p95 tính lại 1,5–15,9 ms trên 100 run | Đạt trên mô phỏng, máy dev |
| MT6 mọi lệnh qua Guard | F4 | 100% | ĐẠT 24/11: test kiến trúc khoá — chỉ `src/guard/dispatcher.py` gọi `apply_commands` | Đạt **trên đường backend** (live, admission fork, `/simulation/run`). Simulator R&D standalone (`HybridSimulator`, `benchmark_mvp3`) áp qua `kernel.apply_approved`: chỉ Guard vật lý, không 7 luật / phê duyệt — đúng thiết kế ADR-002, nhưng không nằm trong "100%". AST test không bắt alias / `getattr` động |
| MT7 AI-1 | F6, F7 | PRD §7.2 | KHÔNG CODE | Chưa có |
| MT8 AI-4 | F6, F8 | PRD §7.2 | KHÔNG CODE | Chưa có |
| MT9 lớp LLM | F1, Lớp LLM | intent ≥ 90% với LLM thật | Chỉ eval offline / mock (LỊCH SỬ `eval/evidence/2026-11-23-refactor-llmchat/`); `eval/results/report.md` là bản mẫu template 2026-09-18 | **Chưa đo** |
| MT12 chiếm cổng | F14 | báo số phút | Chưa đo | Chưa có |

MT7–MT9 (AI-1, AI-4, LLM): xem PRD §7.2 cho số R&D [`RD_RERUN.md`]; sản phẩm chưa có code AI-1 / AI-4, MT9 chưa đo.
MT7b, MT7c, MT8b: KHÔNG CODE. MT10, MT11, MT13: ĐANG HOÃN (ADR-015).

Nguồn số LỊCH SỬ: `eval/evidence/2026-11-24-unified-core-frozen-baseline/benchmark.json` (100 run = 5 kịch bản × 4 policy
× 5 seed, code `a9def2f`). Trung bình tự tính 24/11, **tính lại 25/11** (Remediation, khớp Codex). Tập kịch bản:
`hybrid_evening`, `hybrid_power_drop` (topology `mvp1`, 106 kW) + `peak_evening`, `connector_failure`, `power_drop`
(`legacy_ac_only`, header ghi "KHÔNG dùng cho nghiệm thu / benchmark", chạy với nguồn 35 kW trên trạm hybrid).
**Dùng baseline này làm regression** (refactor không làm đổi kết quả), **không** dùng làm nghiệm thu MT1 / MT4 / chọn
policy. Chi tiết: [`docs/handoff/REMEDIATION_PHASE1.md`](handoff/REMEDIATION_PHASE1.md) §2.

### 3.2 Yêu cầu chức năng → code → test

| FR | Chức năng | Code chính | Test | Bằng chứng |
|---|---|---|---|---|
| FR1 đăng nhập 2 vai trò | F1 | `src/services/auth.py`, `src/api/auth.py` | `tests/test_api/test_contract.py`, `tests/test_api/test_errors.py`, `tests/test_services/test_service_contracts.py` | ĐẠT 24/11 |
| FR2 phiếu yêu cầu | F1 | `src/models/charging.py` | `tests/test_models/test_contracts.py` | ĐẠT 24/11 |
| FR3 kWh do code tính | F1 | `src/services/energy.py` | `tests/test_services/test_energy.py`, `tests/test_api/test_flows.py` | ĐẠT 24/11 |
| FR4 tiếp nhận bằng lời | F1 | `src/llm_chat/` | `tests/test_llm_chat/*` | ĐẠT 24/11 · `MOCK` · LLM thật: CHƯA CHẠY |
| FR4a mục đích → ràng buộc | F1 | — | — | KHÔNG CODE |
| FR5 dispatch tách khỏi lập lịch | F2 | `src/optimizer/dispatch/` | `src/simulator/tests/test_modular.py`, `src/simulator/tests/test_hybrid.py` | ĐẠT 24/11 |
| FR6 AC optimizer (LP) | F2 | `src/optimizer/zones/` | `src/simulator/tests/test_mvp3.py` | ĐẠT 24/11 |
| FR7 DC optimizer (LP theo hàng chờ) | F2 | `src/optimizer/zones/` | `src/simulator/tests/test_mvp2.py` | ĐẠT 24/11 |
| FR8 điều phối ngân sách hai vùng | F2 | `src/optimizer/coordination/` | `src/simulator/tests/test_mvp3.py`, `tests/test_refactor/test_policy_registry.py` | ĐẠT 24/11 |
| FR9 chỉ dùng thông tin đã biết | F2 | `src/simulator/core/kernel.py` (observation model) | `src/simulator/tests/test_observation_layers.py`; hạn sạc chặt: `test_mvp2.py`, `test_mvp3.py` | ĐẠT 24/11 · 1 test liên quan BỎ QUA (`test_forecast_only_changes_queue_start_never_deadline`) |
| FR9a một bộ thuật toán cho live / benchmark / what-if | F2 | `src/simulator/core/kernel.py`, `src/optimizer/registry.py` | `tests/test_refactor/test_differential.py`, `tests/test_services/test_config_parity.py` | ĐẠT 24/11 · **khác tài liệu** (§4) |
| FR10 giới hạn động, sự cố | F3 | `config/scenarios/`, `src/services/simulation_service.py` | `tests/test_services/test_strict_incidents.py`, `tests/test_simulator/test_replan_events.py` | ĐẠT 24/11 · baseline: 40 sự cố hỏng cổng bị bỏ (§3.1 MT4) |
| FR11 tính lại khi có sự kiện | F3 | `src/services/control_loop.py` | `tests/test_simulator/test_replan_events.py`, `tests/test_services/test_control_and_charging.py` | ĐẠT 24/11 |
| FR12 simulator | F2, F3 | `src/simulator/` (`StationKernel`, `HybridStation`) | `src/simulator/tests/*`, `tests/test_simulator/*` | ĐẠT 24/11 · **khác tài liệu** (§4) |
| FR13 Guard hai lớp | F4 | `src/guard/` | `tests/test_guard/*` | ĐẠT 24/11 |
| FR14 bảo vệ khẩn cấp | F4 | `src/guard/emergency.py` | `tests/test_guard/test_load_reduction.py`, `tests/test_services/test_failsafe_after_apply.py`, `tests/test_services/test_safety_event_delivery.py` | ĐẠT 24/11 |
| FR15 ba mức can thiệp | F4 | `src/guard/approval.py` | `tests/test_guard/test_dispatcher.py`, `tests/test_llm_chat/test_hitl.py` | ĐẠT 24/11 · MỘT PHẦN (chưa có đề nghị AI-1) |
| FR16 nhật ký | F4 | `src/services/repository.py`, `src/services/decision_trace.py`, bảng `decision_log`, `decision_traces` | `tests/test_services/test_repository.py`, `tests/test_services/test_decision_trace.py` | ĐẠT 24/11 (SQLite) · Postgres: CHƯA CHẠY · MỘT PHẦN (thiếu `proposals`, `consents`, `audit_log`) |
| FR17 web cư dân | F5 | `frontend/src/app/resident/` | Không có test màn cư dân. Chỉ phần dùng chung: `frontend/src/test/site-map.test.tsx` (chế độ cư dân không lộ xe người khác), `ws-client.test.ts`, `api-client.test.ts`, `not-implemented.test.tsx` | KHÔNG TEST (màn hình) · thành phần dùng chung ĐẠT 24/11 · MỘT PHẦN |
| FR18 web vận hành | F5 | `frontend/src/app/operator/` | `frontend/src/test/site-map.test.tsx` (S5 ConnectorGrid, S9 SiteMap), `simulation-policies.test.tsx` (S8) | ĐẠT 24/11 cho S5 / S8 / S9 · các màn khác KHÔNG TEST · MỘT PHẦN · CI develop đỏ |
| FR19 DecisionTrace | F6 | `src/services/decision_trace.py`, migration `0002` | `tests/test_services/test_decision_trace.py` | ĐẠT 24/11 |
| FR20 sandbox cách ly | F6 | `src/services/admission.py` (fork), `src/simulator/core/isolation.py` | `tests/test_services/test_fork_isolation.py`, `src/simulator/tests/test_fork_isolation.py` | ĐẠT 24/11 · MỘT PHẦN (chưa có WHAT-IF cho người dùng) |
| FR21 Patch có schema | F6 | — | — | KHÔNG CODE |
| FR22–FR27 AI-1 | F7 | — (`src/agents/` rỗng) | — | KHÔNG CODE |
| FR28–FR30b AI-4 | F8 | — (có `charging_service.explain` đơn giản) | — | KHÔNG CODE |
| FR31 LLM chỉ ở hai đầu | Lớp LLM | `src/llm_chat/`, `src/services/llm.py` | `tests/test_architecture.py`, `tests/test_llm_chat/*` | ĐẠT 24/11 · MỘT PHẦN (đầu ra chưa có grounding) |
| FR32 grounding gate | Lớp LLM | `src/llm_chat/guardrails.py` (`check_grounded_numbers`: chỉ kiểm số kWh và mã đầu nối trong câu trả lời chat) | `tests/test_llm_chat/test_agent_modes.py` (`test_check_grounded_numbers_validates_kwh_and_connector`, `test_finalize_node_enforces_grounded_numbers`) | ĐẠT 24/11 · MỘT PHẦN (PRD đòi kiểm từng câu với `facts` / `reason_codes` / `evidence_refs`) |
| FR33 chế độ offline xác định | Lớp LLM | `src/llm_chat/mock_llm.py` | `tests/test_llm_chat/test_agent_modes.py` | ĐẠT 24/11 · mâu thuẫn production (D-3) |
| FR33a chống prompt injection | Lớp LLM | `src/llm_chat/guardrails.py` | `tests/test_llm_chat/test_guardrails.py` | ĐẠT 24/11 · `MOCK` |
| FR34–FR41 dự báo, mức linh hoạt | F12, F13 | `src/forecast/` (stub) | `tests/test_forecast/test_forecast_contracts.py` | 8 BỎ QUA · ĐANG HOÃN |
| FR42 trạng thái đầy nhưng còn cắm | F14 | `src/simulator/core/queue.py` (AC rời ở giờ rời; DC rút sau `completed_at` + độ trễ), `src/simulator/core/kernel.py` (`FINISHED`, không tự rút); tên `FINISHED_PLUGGED` chỉ ở `src/models/station.py` | `src/simulator/tests/test_hybrid.py::test_9ev_queue_occupancy_order_and_unplug`, `tests/test_simulator/test_hybrid_station.py::test_dc_unplugs_after_delay_ac_holds_until_departure` | ĐẠT 24/11 (mô phỏng) · tên trạng thái khác PRD |
| FR43 vận hành thấy cổng bị chiếm + thời lượng | F14 | chưa xác định màn hiển thị | không tìm thấy | KHÔNG TEST · CHƯA XÁC MINH |
| FR44 dispatch coi cổng bị chiếm là không dùng được | F14 | `src/simulator/core/queue.py` | `test_9ev_queue_occupancy_order_and_unplug` (xe kế tiếp chỉ vào khi xe trước rời) | ĐẠT 24/11 (mô phỏng) · MT12 chưa đo |
| FR45–FR46 cảm biến ô đỗ | F15 | — | — | KHÔNG CODE |

### 3.3 Bằng chứng không còn dùng được (đã gỡ khỏi truy vết)

Bảng truy vết cũ trong `ARCHITECTURE.md` dẫn **4 test không tồn tại**: `test_each_rule_blocks_its_violation`,
`test_peak_evening_respects_limit_and_meets_deadlines`, `test_waiting_cars_are_ordered_by_earliest_deadline`,
`test_no_energy_is_scheduled_after_declared_deadline`. Bảng đó cũng ghi ~12 test là "đang skip", trong khi thực tế
chúng đang chạy và đạt. Bảng cũ còn dẫn module đã xoá (`optimizer/assignment.py`, `simulator/parking_queue.py`). Từ
nay chỉ dùng bảng §3.2.

### 3.4 Tiêu chí nghiệm thu PRD §8 (AC1–AC17) → bằng chứng

Thêm ngày 25/11 (Remediation F4 / K2). Có test **không** có nghĩa AC đạt: AC cần điều kiện nghiệm thu (dữ liệu, LLM,
deploy) và người duyệt. Mọi test dưới đây: ĐẠT 24/11 @ `ce23136`, SQLite tạm, LLM giả.

| AC | Nội dung ngắn | Test liên quan (một phần) | Chưa có / chưa truy vết | Kết luận |
|---|---|---|---|---|
| AC1 | Đặt lịch form / chat, kWh khớp FR3 | `tests/test_api/test_flows.py::test_form_booking_works_without_llm`, `::test_chat_booking_kwh_matches_fr3` | LLM thật; "≤ 2 s" của bước quyết định trên luồng này | Tested (`MOCK`) |
| AC2 | Hết cổng → hàng chờ đúng vùng | `test_flows.py::test_walk_in_when_full_gets_queue_position` | "Đúng vùng" và thời gian chờ ước tính chưa có assertion riêng đã đối chiếu | Tested một phần |
| AC3 | Cao điểm, nhiều seed: 0 vi phạm, golden không lệch, đúng hạn theo kịch bản | Baseline LỊCH SỬ (§3.1); golden MVP-1/2/3 ở `src/simulator/tests/` | Kịch bản khả thi (I-1); baseline chỉ regression | Chưa nghiệm thu |
| AC4 | Nguồn giảm → giảm ngay, không chờ duyệt | `test_flows.py::test_power_drop_is_curtailed_before_replan`, `tests/test_guard/test_dispatcher.py::test_emergency_command_is_never_held_for_approval` | Mức 106 → 50 kW đúng như AC chưa đối chiếu | Tested |
| AC5–AC7 | AI-1 đề nghị / áp dụng / an toàn | — | KHÔNG CODE | Chưa có |
| AC8 | WHY có `reason_code` + `evidence_ref` | — (`/resident/explanation` đơn giản, không theo trace) | KHÔNG CODE (AI-4) | Chưa có |
| AC9 | WHAT-IF cách ly | `tests/test_services/test_fork_isolation.py` (cách ly fork cho báo giá) | WHAT-IF cho người dùng chưa có | Chưa có (chỉ nền) |
| AC10 | Gợi ý có điều kiện | — | KHÔNG CODE | Chưa có |
| AC11 | 100% lệnh vi phạm bị chặn | `tests/test_guard/test_rules.py` (từng luật), `test_dispatcher.py::test_blocked_command_never_reaches_actuator`, `test_flows.py::test_blocked_commands_show_up_for_operator` | "Hiện dashboard" chưa kiểm trên web | Tested |
| AC12 | Không LLM vẫn chạy mọi luồng | `test_flows.py::test_form_booking_works_without_llm`; `tests/test_llm_chat/test_agent_modes.py` | Production cấm `mock` (D-3); nhãn UI "LLM chưa cấu hình" chưa kiểm | Mâu thuẫn chờ D-3 |
| AC13 | Báo cáo benchmark gắn commit | `eval/evidence/2026-11-24-unified-core-frozen-baseline/` (manifest) | Eval AI-1 / AI-4 / LLM; ca thắng / hoà / thua | MỘT PHẦN |
| AC14 | Demo 2 vai trò, engine thật | — | Chưa kiểm deploy sau refactor; CI nhánh chưa chạy | Chưa xác minh |
| AC15 | Chiếm cổng hiển thị + WHY | test mô phỏng ở FR42 / FR44 | Màn vận hành, WHY | MỘT PHẦN |
| AC16 | Dự báo | — | ĐANG HOÃN | — |
| AC17 | Mục đích → ràng buộc | — | KHÔNG CODE (FR4a) | Chưa có |

---

## 4. Triển khai khác với tài liệu

| Tài liệu nói | Code thực tế | Ảnh hưởng nghiệp vụ |
|---|---|---|
| FR12 / ADR-011: simulator sau bề mặt `src/simulator/base.py` + `SimulatorGateway` | Không có hai thành phần này. Dùng `StationKernel` chung (ADR-019), giao diện trạm ở `src/models/station_protocols.py` | Không — hành vi tương đương; tài liệu cần cập nhật (Tech Lead) |
| `ARCHITECTURE.md` ranh giới: simulator không được import optimizer / guard | Simulator import optimizer và Guard vật lý (được `tests/test_architecture.py` cho phép) | Không — tài liệu cũ |
| PRD header: backend chạy `LiveStation` | `LiveStation` đã xoá; backend chạy `HybridStation` | Không — tài liệu cũ |
| PRD §11.1: MVP-2 / MVP-3 là "mục tiêu" | Đã có code và test (`test_mvp2.py`, `test_mvp3.py`) | Tiến độ tốt hơn tài liệu ghi |
| PRD F6: DecisionTrace là lõi cho AI-4 / AI-1 | Trace có, nhưng chưa có AI-4 / AI-1 nào đọc nó | Giá trị AI chưa hiện thực |
| PRD FR33: chế độ offline chạy đủ luồng trong demo | Provider offline (`mock`) bị cấm khi `APP_ENV=production` | Có thể ảnh hưởng demo (D-3) |
| HANDOFF: M3a "rẻ hơn nhưng đúng hạn thấp hơn" so với A_edf | A_edf đã xoá; so sánh hiện tại chỉ giữa B0 / M2b / M3a / M3b | Lý do chọn mặc định M3a cần xem lại (D-2) |
| PRD FR9a / `CLAUDE.md`: live, benchmark, what-if dùng **cùng một bộ thuật toán** | Đúng ở Planning Core (`kernel.propose`, policy từ registry). Backend thêm **bước consent** sau Planning Core: `SimulatorScheduler.decide` → `_start_minimums` → `_fit_with_minimums` (co công suất xe khác theo tủ → vùng → lưới) → `kernel.approve` (`src/services/hybrid_planner.py:138–149`). `HybridSimulator.step` không có bước này; `test_differential.py` không đi qua `decide` (audit B1) | Khi consent có hiệu lực, backend có thể khác simulator standalone. D-6: consent ở backend PROVISIONAL (25/11), xét lại sau R-4 |
| PRD MT1 / AC3: "tỷ lệ đúng hạn" một nghĩa | Backend `compute_kpis` (năng lượng tới deadline, mẫu = xe "khả thi từng xe") ≠ simulator `evaluation/extended.py` (`completed_at ≤ departure`, mọi xe) (audit B4) | Số đúng hạn backend và R&D không so trực tiếp được (D-4, R-2) |

Chức năng bị **loại / hoãn** (đều theo ADR-015 — chưa duyệt): F12, F13, HOW-TO tối ưu, FR30a, AI-2 ML, AI-3. Chức năng
bị **thu hẹp**: F14 chỉ hiển thị trạng thái (bỏ nhắc dời xe, phí).

---

## 5. Cần điều tra (không xoá)

| # | Điều | Vì sao cần điều tra |
|---|---|---|
| I-1 | Kịch bản benchmark có phải "kịch bản khả thi" theo MT1 không | **Đã trả lời một phần (25/11):** không — seed 1 của `peak_evening` và cả `hybrid_evening` đều vượt năng lực AC (§3.1 MT1). Còn mở: đóng góp định lượng của hàng chờ, giữ cổng, mục tiêu chi phí, DC taper; MT1 cần bộ kịch bản khả thi riêng (D-4, task R-2) |
| I-2 | F14: simulator có thật sự giữ xe "đã đầy nhưng còn cắm" không | **ĐÓNG 25/11:** có, ở mức mô phỏng (§3.2 FR42, FR44; Codex K8). Còn mở: màn vận hành (FR43), MT12 |
| I-3 | F10: có test cho hồ sơ cư dân không | **ĐÓNG 25/11:** có — `test_service_contracts.py::test_profile_update_and_unknown_vehicle` (Codex F4) |
| I-4 | `src/simulator/AGENTS.md`, `src/simulator/docs/*` | Bộ tài liệu riêng của simulator, có thể lệch với tài liệu dự án |
| I-5 | 5 worktree trong `.claude/worktrees/` (3 cái ở commit skeleton `8f6f08a`) và 9 worktree ở `D:\VIN\P-019-wt\` | Có thể là đồ cũ của đợt refactor; chiếm chỗ, dễ gây nhầm khi agent tìm file |
| I-6 | `presentation/README.md` liệt kê `pitch_deck.pptx`, `video_demo.mp4` nhưng file chưa có | Deliverable BTC |
| I-7 | Kết quả tự audit backend ↔ simulator (`docs/handoff/AUDIT_BACKEND_SIMULATOR_ALIGNMENT.md`, chưa review độc lập) | AMBIGUOUS: B1 consent (→ §4, D-6), B2 ETA hàng chờ là heuristic riêng, B3 `Booking.connector_id` trộn cổng thật / dự kiến, B4 hai định nghĩa đúng hạn (→ §4). UNVERIFIED: U1 tiến đồng hồ ngoài `rt.lock` (nếu xảy ra thì hỏng theo hướng an toàn — lệnh bị chặn `stale_state`), U2 nhiều worker, U3 khôi phục sau restart. Không có MISALIGNED có bằng chứng. Không tự sửa |

---

## 6. Mâu thuẫn ảnh hưởng phạm vi / hành vi nghiệp vụ — Human Supervisor đã quyết 2026-11-25

**Quyết định Human 2026-11-25** (chỉ thị trong phiên Claude Code, sau Technical Acceptance PASS — `docs/handoff/REREVIEW_PHASE1_RESULT.md`
§T0–T5). Nhãn: **APPROVED** · **PROVISIONAL** (tạm giữ, có điều kiện xét lại) · **DEFERRED** (hoãn, có điều kiện mở lại).
Không ADR nào chuyển sang `Accepted` (xem `docs/adr/README.md` §"Quyết định của Human Supervisor").

| # | Quyết định | Nhãn | Điều kiện xét lại / mở lại |
|---|---|---|---|
| D-1 = Q1 | Ưu tiên AI-4 WHY (F8). AI-1 Negotiation đầy đủ (F7) hoãn, **không** loại khỏi roadmap | APPROVED (AI-4 ưu tiên) · DEFERRED (AI-1) | AI-1: khi phạm vi và năng lực triển khai được đánh giá |
| Q2 | Bãi hiện tại là **giả định mô phỏng có nhãn**, không phải dữ liệu VinFast / Vinhomes | APPROVED | Có thông số thật / đổi topology |
| D-2 = Q3 | M3a tạm giữ làm mặc định; B0 / M2b / M3a / M3b version `"1"` giữ nguyên | PROVISIONAL | Sau R-2, R-3 |
| Q4 | Nguyên tắc AI: dựa trên facts / trace; quyền kiểm phía server; không tự đổi cam kết; không apply kết quả sandbox khi chưa được phép | APPROVED (nguyên tắc) | Chi tiết kỹ thuật review riêng |
| D-3 | Demo offline **có nhãn** ở dev / test; **giữ cấm** `mock` ở production | APPROVED | Nếu cần offline tại production: duyệt thay đổi riêng |
| D-4 | Hướng chuẩn hoá: workload feasibility, request fulfillment, accepted booking on-time rate, admission rate; báo rõ mẫu số, điều kiện khả thi, trường hợp mẫu số = 0 | APPROVED (hướng) · PROVISIONAL (định nghĩa chính xác) | Định nghĩa chính xác review trong R-2 |
| D-5 | Hoãn đổi mã định danh trong source / test; tiếp tục dùng §1.1 | DEFERRED | Khi Human lên lịch task đổi mã riêng |
| D-6 | Consent tạm giữ ở backend; không đổi frozen policies | PROVISIONAL | Sau R-4 |
| C-3 | Sửa nhãn forecast trong tài liệu thành "F12 (= F6 cũ)" | APPROVED — **đã làm 25/11** (`CLAUDE.md`, `ARCHITECTURE.md`) | — |
| G-auto | Đưa Agent Command Protocol, Shared Skill Pack, Skill Observability, Automated Governance (gồm §7 tự động hoá) vào **kế hoạch Phase 2** | APPROVED (lập kế hoạch) · DEFERRED (implementation chưa duyệt) | Khi Human duyệt implementation Phase 2 |
| C-1 | Commit tài liệu Phase 1 | Chưa cho phép | Chỉ thị riêng của Human |
| P1-14 | Đóng Phase 1 chính thức | Chưa cho phép trong lượt 25/11 | Chỉ thị riêng của Human |

Bảng dưới đây là **lịch sử** câu hỏi và phương án trước khi quyết (giữ nguyên để truy vết).

| # | Mâu thuẫn | Lựa chọn | Agent đề xuất |
|---|---|---|---|
| D-1 | Phạm vi sprint: ADR-015 ghi AI-1 và AI-4 là "Làm", nhưng chưa có code, còn 2 ngày | Giữ phạm vi · thu hẹp (AI-4 WHY trên trace có sẵn, AI-1 tối thiểu hoặc hoãn) · dời mốc | Xem `docs/adr/README.md` §Triage, quyết định Q1 |
| D-2 | Chính sách điều phối mặc định M3a: tổng tiền thấp nhất nhưng đúng hạn thấp nhất trong 4 policy, và **không** rẻ nhất theo kWh đã giao (M3b rẻ hơn) — LỊCH SỬ, trên baseline không khả thi (§3.1 MT3) | Giữ M3a · đổi sang M3b · giữ M3a tạm có nhãn, quyết sau khi so ghép cặp trên kịch bản khả thi (R-2, R-3) | Quyết định Q3; số hiện có **không đủ** để chọn |
| D-3 | Demo có cần chạy khi không có LLM không (PRD FR33) trong khi production cấm chế độ offline | Cho phép offline có nhãn ở production · bắt buộc LLM thật khi demo | Cần anh/chị chọn; ảnh hưởng độ tin cậy demo |
| D-4 | MT1 "≥ 95% trong kịch bản khả thi" chưa định nghĩa kịch bản khả thi; code hiện chỉ kiểm "khả thi từng xe" | Định nghĩa khả thi **cả bãi** (năng lượng, cổng, nguồn, sự cố) + bộ kịch bản nghiệm thu + một định nghĩa đúng hạn | Gắn I-1, task R-2 |
| D-5 | Đổi tên mã cũ trong code / test (F6 cũ, F7 cũ, F8 cũ) sang mã PRD | Đổi ngay · để sau demo · giữ nguyên + ghi chú | Để sau demo; registry §1.1 là cầu nối |
| D-6 | Consent cư dân (`max_start_delay_minutes`) là ràng buộc của Planning Core hay quy tắc nghiệp vụ của backend? (audit B1) | (a) Planning Core: simulator cũng phải có, qua **policy mới** vì B0–M3b đóng băng · (b) business rule backend: giữ code, ghi ADR, bỏ khẳng định "backend = simulator" tuyệt đối | Chưa đề xuất: cần Tech Lead review B1 trước. Không sửa code trước quyết định |

### 6.1 Backlog sản phẩm từ review (DEFERRED — chưa giao thực thi)

Human 2026-11-25: giữ R-1…R-6 trong backlog, **chưa giao thực thi**, ưu tiên đề xuất P0 / P1 / P2. Cột "Vai trò theo
dõi" là vai trò (theo `docs/handoff/REVIEW_PHASE1.md` §6) chịu trách nhiệm theo dõi điều kiện và báo Human khi đủ điều
kiện giao — **không** phải người thực hiện; Human có thể đổi. Tiêu chí hoàn tất: `REMEDIATION_PHASE1.md` §5.1.

| Task | Ưu tiên | Trạng thái | Vai trò theo dõi | Phụ thuộc (trạng thái 25/11) | Điều kiện mở lại = giao thực thi |
|---|---|---|---|---|---|
| R-1 dataset sự cố `mvp1` | P0 | DEFERRED | Tech Lead | Q2 ✔ APPROVED; danh sách sự cố cần nghiệm thu: **chưa chốt** | Human chốt danh sách sự cố + chỉ định người thực hiện |
| R-2 khả thi workload + KPI | P0 | DEFERRED | Tech Lead (định nghĩa: Human duyệt) | D-4 ✔ hướng APPROVED; Q2 ✔ | Human chỉ định người thực hiện; định nghĩa chính xác qua review độc lập |
| R-6 test tái hiện U1 / U3 | P0 | DEFERRED | Tech Lead (QA kiểm) | Kịch bản test: **chưa duyệt**; môi trường một worker | Human duyệt kịch bản + chỉ định người thực hiện |
| R-3 so policy ghép cặp | P1 | DEFERRED | Tech Lead | **R-2 xong** (workload khả thi); tiêu chí ưu tiên đúng hạn / chi phí / chờ: **chưa chốt** | R-2 hoàn tất và được review; Human chốt tiêu chí. Kết quả dùng để xét lại Q3 |
| R-4 consent | P1 | DEFERRED | Tech Lead | D-6 ✔ PROVISIONAL (backend); review kỹ thuật B1 | Human chỉ định người thực hiện; nếu chạm Planning Core: policy mới được duyệt. Kết quả dùng để xét lại D-6 |
| R-5 ETA / cổng dự kiến | P2 | DEFERRED | Human / Product | Quyết định hiển thị; đổi API cần duyệt riêng | Có nhu cầu hiển thị được Human ưu tiên |

Chuỗi phụ thuộc: D-4 → R-2 → R-3 → xét lại Q3; D-6 → R-4 → xét lại D-6; Q2 → R-1.

Ghi chú cũ (giữ):

R-1 dataset nghiệm thu sự cố trên `mvp1` · R-2 khả thi cả bãi + một định nghĩa đúng hạn · R-3 so policy ghép cặp cùng
mức phục vụ · R-4 vị trí consent (sau D-6) · R-5 ETA hàng chờ / cổng dự kiến · R-6 test tái hiện U1, U3. Tiêu chí
hoàn tất kiểm được + phụ thuộc từng task:
[`docs/handoff/REMEDIATION_PHASE1.md`](handoff/REMEDIATION_PHASE1.md) §5.1. Phụ thuộc chính: D-4 → R-2 → R-3; Q2 → R-1; D-6 → R-4.

---

## 7. Cổng kiểm soát tối thiểu (áp dụng thủ công từ nay)

Mỗi lần cập nhật registry hoặc tuyên bố trạng thái, người cập nhật (agent hoặc người) tự kiểm 6 tiêu chí:

| # | Tiêu chí | Cách kiểm thủ công |
|---|---|---|
| G1 | Test được dẫn phải tồn tại | `grep -rn "def <tên_test>" tests src` ra đúng một kết quả |
| G2 | Đường dẫn trong tài liệu phải tồn tại | mở được file; với link markdown: `python scripts/check_docs.py` (hiện chỉ quét `docs/guide/`) |
| G3 | Mã chức năng không mâu thuẫn | chỉ dùng mã PRD v0.4; mã cũ ghi kèm "= mã mới" (§1.1) |
| G4 | Trạng thái phải có bằng chứng | mỗi ô trạng thái ≥ `Tested` có ít nhất một test `ĐẠT <ngày>` hoặc nhãn `LỊCH SỬ @<commit>` |
| G5 | Không `Validated` chỉ vì đã viết code | `Validated` cần tham chiếu tiêu chí PRD §8 + điều kiện nghiệm thu + người duyệt |
| G6 | Thay đổi quan trọng có review độc lập | thay đổi chạm F2 / F4 / F6 / dữ liệu / bảo mật: PR có reviewer khác agent viết code, ghi trong mô tả PR |

**Tự động hoá — chưa làm, cần duyệt riêng.** Phạm vi đề xuất:
1. Thêm `scripts/check_registry.py` (~100 dòng, chỉ đọc): kiểm G1 (tên test trong registry tồn tại và không bị
   `skip`), G2 (đường dẫn trong registry và `ARCHITECTURE.md` tồn tại), G3 (không dùng F6 / F7 / F8 theo nghĩa cũ trong
   tài liệu mới).
2. Gọi script đó trong `make check` và một bước trong job `backend` của `.github/workflows/ci.yml`.
3. Mẫu PR riêng của dự án (`.github/PULL_REQUEST_TEMPLATE.md`) có mục G6 và 7 câu hỏi chuyển giao kiến thức; sửa
   `.github/CODEOWNERS` về nhóm dự án.

Mục 2–3 sửa CI / cấu hình repo — ngoài phạm vi Giai đoạn 1 đã duyệt.

---

## 8. Cập nhật registry

- Cập nhật cùng PR với thay đổi làm đổi trạng thái chức năng. Ghi ngày + commit ở dòng "Mốc bằng chứng".
- Không ghi `ĐẠT <ngày>` nếu không tự chạy test trong lần cập nhật đó; dùng `LỊCH SỬ @<commit>`.
- Khi sửa registry, trả lời 7 câu hỏi chuyển giao kiến thức trong
  [`docs/communication/HUMAN_AGENT_COMMUNICATION.md`](communication/HUMAN_AGENT_COMMUNICATION.md) §10.
