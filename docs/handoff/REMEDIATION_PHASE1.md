# Remediation Governance Phase 1 — bản ghi bằng chứng (P1-12b)

- Người làm: Claude Code (`claude-opus-5-5`), vai **Implementation Agent** (cùng agent soạn tài liệu Phase 1) ⇒ đây
  **không** phải kiểm chứng độc lập. Cần Codex Re-review (P1-12c).
- Giao việc: Human Supervisor duyệt chính thức trong phiên Claude Code 2026-11-25 ("chưa giao Remediation trước đó;
  không có workspace / báo cáo Remediation nào khác"; phạm vi: chỉ sửa tài liệu).
- Code kiểm: `feature/unified-core` @ `ce23136`. Không sửa `src/`, `tests/`, `config/`, `frontend/`, `migrations/`,
  `.github/`, `eval/evidence/`. Không commit / push / merge / deploy. Không duyệt ADR.
- Đầu vào: `docs/handoff/REVIEW_PHASE1_RESULT.md` (Codex 24/11, F1–F5, K1–K15),
  `docs/handoff/AUDIT_BACKEND_SIMULATOR_ALIGNMENT.md` (tự audit Claude 24/11, B1–B4, U1–U3).

## 1. Tóm tắt

| Mục | Kết quả |
|---|---|
| Phát hiện F1–F5 | 5/5 kiểm chứng lại trực tiếp: **cả 5 đúng**, không có kết luận nào bị bác. 2 điểm được **bổ sung bằng chứng** (F1, F2) và 1 điểm (F3) có thêm số đo làm rõ |
| Thiếu sót K liên quan | K2, K8, K9, K14, K15 (MỘT PHẦN) đã sửa tài liệu; K1, K3–K7, K10–K13 ĐÚNG, không cần sửa |
| Sửa governance (làm ngay) | Registry, sơ đồ 4 tầng, triage ADR, `ARCHITECTURE.md`, `CLAUDE.md` (số bảng), brief review |
| Chuyển task kỹ thuật riêng | 6 task R-1…R-6 (§5) — **chưa giao**, không tự làm |
| Cần Human quyết | Thêm D-6 (consent B1) và hướng xử lý R-1…R-6; các mục cũ ở HANDOFF §1.5 giữ nguyên |

## 2. Kiểm chứng từng phát hiện (trước khi sửa)

Lệnh tái tính dùng Python stdlib đọc `eval/evidence/2026-11-24-unified-core-frozen-baseline/benchmark.json` (chỉ đọc);
generator đọc qua `src.services.simulation_service.generate_bookings` (không ghi file). Ngày 2026-11-25 @ `ce23136`.

### F1 — baseline không kiểm đủ sự cố · **XÁC NHẬN + BỔ SUNG**

- Tái cộng `incidents`: planned 160 / applied 120 / skipped 40. Theo kịch bản: `connector_failure` 40/0/40 (cả
  `connector_fault@420'` và `connector_restored@660'` của `A05`); `power_drop` 40/40/0; `hybrid_power_drop` 80/80/0;
  `peak_evening`, `hybrid_evening` không có sự cố.
- `config/scenarios/{peak_evening,connector_failure,power_drop}.yaml` dòng 1–3: `legacy_ac_only`, "KHÔNG dùng cho nghiệm
  thu / benchmark"; ghi chú run: "giới hạn nguồn 35 kW" chạy trên trạm hybrid.
- **Bổ sung (mới):** 20 run `connector_failure` có KPI **trùng hoàn toàn** 20 run `peak_evening` cùng policy + seed, chỉ
  khác `replan_p95_seconds`. Tức 20/100 run là bản lặp của kịch bản không sự cố.
- Kết luận: 0 vi phạm đúng cho tải đã chạy; baseline **không** chứng minh phản ứng hỏng cổng. 60/100 run dùng kịch bản
  legacy. Chỉ 40/100 run (`hybrid_*`) đúng topology `mvp1`.

### F2 — "khả thi từng xe" ≠ khả thi cả bãi · **XÁC NHẬN + BỔ SUNG**

- `src/services/simulation_service.py:162–164` `_is_feasible`: chỉ `max_charge_power_kw × giờ ≥ requested_kwh`.
- `compute_kpis:130–145`: mẫu số đúng hạn = outcome có cờ `feasible`; không có xe feasible ⇒ `on_time_rate = 1.0`.
- Chờ (`waits`) gồm cả xe chưa cắm tới deadline (censored, dòng 132–134).
- Generator tạo booking `CONFIRMED` không qua admission (`generate_bookings:71–117`).
- Tái tính `peak_evening` seed 1: 30 xe, pin cần **1378,6713 kWh**, AC **1183,1725 kWh** — khớp Codex. Nguồn 35 kW × 24 h
  = 840 kWh; 2 cổng AC × 11 kW × 24 h = 528 kWh.
- **Bổ sung (mới):** `hybrid_evening` seed 1 (topology đúng, lưới 106 kW): 16 xe, AC cần **676,1576 kWh** > 528 kWh trần
  vật lý hai cổng AC trong 24 h. Vậy cả kịch bản hybrid cũng vượt năng lực AC ở seed này — làm rõ phản biện của Codex
  ("hybrid vẫn thấp dù 106 kW"): nhu cầu AC của workload này vượt cận năng lượng hai cổng AC. Đây là dữ kiện về năng lực; việc nó **gây ra** bao nhiêu phần tỷ lệ thấp là INFERRED, chưa định lượng *(hạ nhãn ở lượt N2, 25/11)*.
- Kết luận: tỷ lệ 29–32% **không** đo được MT1. VERIFIED: hai workload ví dụ (seed 1) cần nhiều kWh hơn cận năng lực.
  INFERRED: quá tải là một yếu tố. UNVERIFIED: đóng góp định lượng của quá tải, hàng chờ, giữ cổng, chi phí, DC taper
  *(hạ nhãn ở lượt N2, 25/11)*.

### F3 — rẻ hơn chưa phải hiệu quả kinh tế tốt hơn · **XÁC NHẬN + LÀM RÕ**

Trung bình macro 25 run / policy (tái tính, khớp đúng bảng Codex):

| Policy | Đúng hạn | Chi phí VND | Điện giao kWh | Điện thiếu kWh | **VND / kWh giao** (mới) |
|---|---:|---:|---:|---:|---:|
| B0 | 30,26% | 722 143 | 282,90 | 681,23 | 2 552,6 |
| M2b | 30,70% | 729 863 | 286,46 | 677,67 | 2 547,8 |
| M3a | 29,11% | 685 208 | 286,82 | 677,31 | 2 389,0 |
| M3b | 32,09% | 774 705 | 332,77 | 631,36 | **2 328,0** |

Chỉ 40 run hybrid (10 / policy): đúng hạn B0 46,25% · M2b 46,25% · M3a 43,71% · M3b 44,33%; VND / kWh giao 2 569,9 ·
2 568,1 · 2 359,8 · 2 364,0.
- **Làm rõ (mới):** tính theo kWh đã giao, M3b **rẻ nhất** trên toàn baseline; trên tập hybrid M3a và M3b gần như
  bằng nhau. "M3a rẻ nhất" chỉ đúng với **tổng tiền**, vốn thấp một phần vì giao ít điện hơn.
- Chưa có kiểm định ghép cặp / khoảng tin cậy. Không đổi policy (Q3 vẫn chờ Human).

### F4 — registry bỏ sót bằng chứng · **XÁC NHẬN**

- `tests/test_services/test_service_contracts.py:162` `test_profile_update_and_unknown_vehicle` (hồ sơ: cập nhật, đọc lại,
  từ chối xe lạ) — registry ghi "chưa tìm thấy test" (sai).
- `src/simulator/tests/test_hybrid.py:28` `test_9ev_queue_occupancy_order_and_unplug` (AC `completed_at < departed_at`,
  xe kế tiếp chỉ vào khi xe trước rời; DC rút sau +5 phút); `tests/test_simulator/test_hybrid_station.py:110`
  `test_dc_unplugs_after_delay_ac_holds_until_departure` — registry ghi "không tìm thấy" (sai).
- `src/db/tables.py`: 10 `__tablename__`; `CLAUDE.md:157` và `ARCHITECTURE.md:110` ghi 9.
- FR17 / FR18 dẫn "test FE (30)": thực tế 5 file `frontend/src/test/*` — không file nào kiểm màn cư dân; màn vận hành chỉ
  có `site-map.test.tsx` (S5 / S9) và `simulation-policies.test.tsx` (S8).
- Ánh xạ FR10–11 cũ, AC, MT chưa từng dòng (K2) — xác nhận.

### F5 — sơ đồ và phạm vi Guard · **XÁC NHẬN**

- `src/services/control_loop.py:66–137` thứ tự thật: fail-safe vi phạm đã báo → `advance_clock` → đóng trace cũ → ghi
  sự kiện → `_emergency` (chỉ `POWER_LIMIT_CHANGED`) → fail-safe vi phạm mới → đồng bộ booking → `scheduler.plan`
  (propose + Guard vật lý + bước consent B1 + approve) → `diff_commands` → bỏ lệnh của booking đang giữ an toàn →
  `dispatcher.submit` (7 luật → phê duyệt → `apply_commands`) → **mở** trace mới. Vật lý của lệnh mới chạy ở lần
  `advance` sau. Sơ đồ B cũ vẽ advance ngay sau apply rồi mới ghi trace — sai.
- `src/services/charging_service.py:235–304` `book`: chạy lại admission với consent thật **ngoài** khoá, rồi kiểm
  fingerprint dưới `booking_lock`, lệch ⇒ chạy lại (tối đa `BOOKING_COMMIT_ATTEMPTS`). Sơ đồ A cũ bỏ bước này.
- `simulation_service.inject_incident:375–389` + `control_loop._emergency:343`: chỉ giảm nguồn đi đường cắt giảm khẩn
  cấp; hỏng cổng do kernel `fault_port` xử lý rồi tính lại. Sơ đồ C cũ gộp hai đường.
- `apply_commands(` chỉ được gọi ở `src/guard/dispatcher.py:125,184`. `HybridSimulator` standalone / `benchmark_mvp3`
  dùng `kernel.apply_approved` trực tiếp (chỉ Guard vật lý, không 7 luật / HITL). `CLAUDE.md:174` "kể cả benchmark" đúng
  cho benchmark backend (`/simulation/run`), không đúng cho benchmark R&D standalone.

### Đối chiếu với audit Backend ↔ Simulator (tự audit, chưa review)

| Mục audit | Kiểm lại 25/11 | Ghi nhận trong tài liệu |
|---|---|---|
| B1 consent sau Planning Core | `hybrid_planner.py:138–149` (`_start_minimums` → `_fit_with_minimums` → `kernel.approve`); `HybridSimulator.step` (`hybrid.py:139`) gọi `approve(proposal)` không chỉnh; `test_differential.py:106` bỏ qua `decide` — **đúng** | Registry §4 (FR9a chỉ đúng ở Planning Core), §6 **D-6** chờ Human; **không** sửa code |
| B2 ETA heuristic | `_queue_etas` (`hybrid_planner.py:287`) tồn tại — đúng | Registry §5 I-7; task R-5 |
| B3 connector thật / dự kiến | không kiểm lại frontend | Giữ AMBIGUOUS, I-7 |
| B4 hai định nghĩa đúng hạn | khớp F2 (`compute_kpis` vs `evaluation/extended.py`) | Registry §3.1 MT1, gộp vào R-2 |
| U1–U3 | không tái hiện | Giữ UNVERIFIED, I-7 |

## 3. Phản biện Codex

Không bác kết luận nào. Ba điểm chỉ **thu hẹp / bổ sung**, không đảo ngược:
1. F2, phản biện "hybrid thấp dù 106 kW": bằng chứng mới cho thấy kịch bản hybrid (seed 1) cũng vượt năng lực AC.
2. F3: thêm chỉ số VND / kWh; ủng hộ kết luận của Codex mạnh hơn.
3. K14 "Không ADR nào đã duyệt là sai nếu hiểu tuyệt đối": câu gốc ở README có ý "Agent không duyệt ADR nào", nhưng viết
   mơ hồ — chấp nhận, đã sửa câu và thêm cột lịch sử duyệt.

## 4. Thay đổi đã làm (chỉ tài liệu)

| Phát hiện | File | Thay đổi |
|---|---|---|
| F1, F2, F3 | `docs/FEATURE_REGISTRY.md` §2 (F2, F9), §3.1 (MT1–MT4, MT6), §6 (D-2, D-4) | Diễn giải lại benchmark: mẫu số, kịch bản legacy, sự cố bị bỏ, VND / kWh; MT4 thu hẹp phạm vi |
| F2 / B4 | registry §3.1, §4 | Hai định nghĩa đúng hạn; workload vượt năng lực |
| F3 | `docs/adr/README.md` Q3 | Thêm VND / kWh, tập hybrid; bỏ "rẻ nhất" không điều kiện |
| F4 | registry §2 (F10, F14), §3.2 (FR17, FR18, FR42–44), §3.4 (mới: AC1–AC17), §1.1 (FR4/5/10–11 cũ, AC cũ), §5 (I-2, I-3 đóng) | Sửa bằng chứng; truy vết AC / MT từng dòng; mục chưa truy vết ghi rõ |
| F4 | `CLAUDE.md:157`, `ARCHITECTURE.md:110` | 9 → 10 bảng (thêm `decision_traces`) |
| F5, K15 | `docs/architecture_diagram.md` §2.1, §2.4, §2.5, §1.3, Tầng 4 | Vẽ lại luồng A / B / C theo thứ tự code; tách giảm nguồn / hỏng cổng; phạm vi "một cửa" = đường backend |
| F5 | registry §3.1 MT6 | "100% lệnh qua Guard" chỉ cho đường backend; R&D standalone chỉ Guard vật lý |
| K14 | `docs/adr/README.md` triage | Câu "không duyệt" viết lại; cột lịch sử duyệt theo file ADR; 014 / 018 phần C chưa review |
| K14 | `docs/handoff/REVIEW_PHASE1.md` §4 mục 4 | Ghi chú: nhóm C gồm cả phần C của 014, 018 |
| B1–B4, U1–U3 | registry §4, §5 (I-7), §6 (D-6) | Ghi đúng trạng thái AMBIGUOUS / UNVERIFIED, không tự giải |
| Checkpoint | `docs/handoff/HANDOFF.md` §1 | P1-12b, bằng chứng, khoá, việc tiếp |

Không sửa: `docs/PRD.md` (là nguồn yêu cầu; số R&D trong PRD §7 có nhãn riêng), C-3 ("F6 forecast" trong `CLAUDE.md`,
chờ Human), HACP.

## 5. Governance sửa ngay vs task kỹ thuật riêng

**Governance (đã sửa trong lượt này):** mọi mục ở §4.

**Task kỹ thuật sản phẩm — đề xuất, CHƯA GIAO, cần Human duyệt (sửa code / dữ liệu / evidence ngoài phạm vi Phase 1):**

| # | Task | Nguồn | Ghi chú |
|---|---|---|---|
| R-1 | Dataset nghiệm thu sự cố trên topology `mvp1` (hỏng cổng thật sự áp; `strict_incidents`) | F1 | Baseline cũ giữ làm regression |
| R-2 | Định nghĩa "kịch bản khả thi" + kiểm khả thi cả bãi (năng lượng, cổng, nguồn) + thống nhất định nghĩa đúng hạn backend / simulator; báo mẫu số | F2, B4, D-4 | Phụ thuộc Human quyết D-4 |
| R-3 | So sánh policy ghép cặp theo scenario / seed, cùng mức phục vụ, có khoảng tin cậy | F3, Q3 | Cung cấp bằng chứng cho Q3 |
| R-4 | Quyết định + hiện thực vị trí consent (Planning Core hay backend) | B1, D-6 | Chờ Human D-6; B0–M3b đóng băng |
| R-5 | ETA hàng chờ (B2), cổng thật / dự kiến (B3) | audit | Chưa ưu tiên |
| R-6 | Test tái hiện U1 (tiến đồng hồ ngoài `rt.lock`), U3 (khôi phục sau restart) | audit | Chỉ test, không đổi hành vi |

### 5.1 Tiêu chí hoàn tất và phụ thuộc (bổ sung lượt N4, 2026-11-25)

Mọi task: trạng thái **CHƯA GIAO, chưa phân công**. Đây là hồ sơ để Human quyết có giao hay không — **không** phải
phê duyệt, **không** triển khai trong Governance Phase 1. Tiêu chí dựa trên đề xuất của reviewer (REREVIEW §R7), viết
lại thành điều kiện kiểm được. Điều kiện chung cho mọi task: không sửa B0–M3b version `"1"`; baseline đóng băng
`eval/evidence/2026-11-24-unified-core-frozen-baseline/` giữ nguyên; evidence mới nằm ở thư mục `eval/evidence/<ngày>-…/`
có `manifest.json` (commit, config SHA, seed, policy); kết quả kèm commit; có review độc lập trước khi dùng làm căn cứ
quyết định (G6).

| # | Tiêu chí hoàn tất (kiểm được) | Phụ thuộc trước khi bắt đầu | Không thuộc task |
|---|---|---|---|
| R-1 | (1) Mọi kịch bản sự cố trong bộ mới dùng mã cổng có trong `config/station.yaml` hiện hành; (2) chạy với `--strict-incidents`: `incidents.skipped = 0` ở mọi run, hoặc mỗi sự cố bị loại có lý do ghi trong manifest; (3) có ít nhất một kịch bản hỏng cổng DC và một hỏng cổng AC **đã áp** (`applied > 0`) với xe đang cắm; (4) báo cáo tách `applied_constraint_violation_count`, `rejected_allocation_count`, lệnh bị chặn; (5) baseline cũ không đổi (SHA-256 file trước = sau) | Q2 (mô hình bãi); Human chốt danh sách sự cố cần nghiệm thu (gợi ý: AC4, FR10) | Đổi Guard / fail-safe; chọn policy |
| R-2 | (1) Tài liệu định nghĩa **khả thi từng xe** và **khả thi cả workload** (năng lượng ≤ năng lực nguồn / vùng / cổng theo thời gian, cạnh tranh cổng, giữ cổng sau đầy, DC taper, sự cố); (2) một định nghĩa "đúng hạn" duy nhất cho backend và simulator, hoặc hai định nghĩa có tên khác nhau, báo song song; (3) mọi báo cáo KPI in **mẫu số** và xử lý mẫu rỗng (không ngầm = 100%); (4) bộ workload nghiệm thu có bằng chứng khả thi cả bãi (vd. cận năng lượng + kiểm cổng) theo từng seed; (5) test cho hàm kiểm khả thi và cho KPI mẫu rỗng | **D-4** (Human chốt định nghĩa), Q2 | Đạt ≥ 95% (MT1 là đo, không phải điều kiện xong task) |
| R-3 | (1) Cùng workload / seed / config cho mọi policy, kết quả **ghép cặp** theo (kịch bản, seed); (2) báo đúng hạn, chờ (tách xe được phục vụ / censored), điện giao, điện thiếu, tổng tiền, VND / kWh giao, kèm độ bất định (khoảng tin cậy hoặc phân bố chênh lệch ghép cặp); (3) so chi phí **ở mức phục vụ tương đương** theo PRD MT3, hoặc nói rõ không đạt được mức tương đương; (4) không đổi `planning.policy_id` | R-2 (workload khả thi); Human chốt tiêu chí ưu tiên (đúng hạn / chi phí / chờ) — R-3 **cung cấp** bằng chứng cho Q3, không chờ Q3 | Quyết định Q3 (Human) |
| R-4 | (1) Quyết định D-6 ghi thành ADR mới (Proposed → người có thẩm quyền duyệt); (2) phạm vi ghi rõ: backend, admission, benchmark, simulator standalone dùng / không dùng consent; (3) test đi **qua** `SimulatorScheduler.decide` với consent có hiệu lực và không có, so với đường standalone, ghi khác biệt mong đợi; (4) test trường hợp năng lực không đủ để thoả mọi consent: hành vi được ghi (không ngầm hứa thoả); (5) nếu đưa vào Planning Core: policy mới đăng ký qua registry, B0–M3b không đổi | **D-6**; review kỹ thuật B1 (Tech Lead); nếu chạm policy: thiết kế policy mới được duyệt | Đổi nghĩa consent trong PRD |
| R-5 | (1) API / UI phân biệt `connector_id` thật (đã cắm) và dự kiến (theo plan), hoặc quyết định giữ một trường kèm nhãn; (2) ETA hàng chờ ghi nguồn (heuristic `_queue_etas` hay fork) và giả định; (3) assertion test cho hành vi đã chọn (backend + một test frontend hiển thị); (4) nếu đổi API: cập nhật OpenAPI + `npm run gen:api` (ADR-009) | Quyết định nghiệp vụ hiển thị; nếu đổi contract: duyệt đổi API riêng | Đổi thuật toán dispatch |
| R-6 | (1) Test U1 dựng lịch xen kẽ rõ: `sync_clock` (đường đọc) chạy giữa `scheduler.plan` và `dispatcher.submit`, với `SIM_TIME_SCALE` nêu rõ; (2) test U3: restart giữa phiên, so trạng thái booking / năng lượng sau khôi phục với DB; (3) mỗi test kết luận **tái hiện** hoặc **không tái hiện trong điều kiện đã nêu**; (4) không đổi hành vi sản phẩm trong task này; nếu tái hiện ⇒ mở task sửa riêng | Kịch bản được duyệt; môi trường một worker hiện hành | Hỗ trợ nhiều worker (U2); sửa lỗi |

Thứ tự gợi ý theo phụ thuộc: D-4 → R-2 → R-3 (→ Q3); Q2 → R-1; D-6 → R-4. R-5, R-6 độc lập.

## 6. Kiểm sau khi sửa

- G1 (test được dẫn tồn tại): kiểm bằng `grep -rn "def <tên>" tests src/simulator/tests` cho mọi tên test **mới** thêm vào
  registry / sơ đồ trong lượt này — xem HANDOFF §1.4.
- `scripts/check_docs.py`: xem HANDOFF §1.4.
- Không chạy lại pytest: `src/`, `tests/` không đổi từ `ce23136` (bằng chứng 24/11 còn hiệu lực theo HANDOFF §0).

## 7. Việc cho Codex (Re-review P1-12c)

Kiểm lại F1–F5 và K2, K8, K9, K14, K15 trên bản sửa ở §4; xác nhận hoặc bác các bổ sung ở §2 (connector_failure trùng
peak_evening; AC hybrid seed 1 vượt 528 kWh; VND / kWh); kiểm G1 trên registry §3.2 / §3.4. Ghi kết quả vào
`docs/handoff/REREVIEW_PHASE1_RESULT.md` (file hiện có là lượt dừng ở cổng — Codex tự quyết ghi tiếp hay thêm mục).

## 8. Lượt 2 — Targeted Remediation N2 / N3 / N4 (P1-12e, 2026-11-25)

- Người làm: Claude Code (`claude-opus-5-5`), Implementation Agent (không độc lập). Human duyệt lượt giới hạn N2 / N3 / N4
  theo `REREVIEW_PHASE1_RESULT.md` §R6. Code vẫn `ce23136`; chỉ sửa tài liệu governance.
- F1 / F3 / F4 (reviewer xác nhận RESOLVED): **giữ nguyên**, không thấy bằng chứng mâu thuẫn mới.

| N | Kết quả | Thay đổi |
|---|---|---|
| N2 | Sửa | Registry §3.1 MT2: bỏ "chủ yếu đo quá tải", chỉ mô tả cách đo (censored) + nguyên nhân UNVERIFIED. MT1: tách VERIFIED (cận năng lượng hai workload ví dụ) / INFERRED (quá tải là một yếu tố) / UNVERIFIED (đóng góp từng nguyên nhân; 95% số xe không bị bác). Báo cáo này §2 F2: hạ nhãn tương tự |
| N3 | Sửa sơ đồ; **render CHƯA KIỂM CHỨNG** | `docs/architecture_diagram.md` §2.5: A vẽ vòng `loop` thử lại (admission ngoài khoá → `booking_lock` → so dấu vân tay → quay lại hoặc lưu, hết lượt ⇒ `PROPOSAL_EXPIRED`), quote ghi giả định consent mặc định. B: bỏ khẳng định "gộp mọi sự kiện cùng thời điểm"; ghi rõ phạm vi gộp (batch + outbox của một lần `on_event`), `event_bus.publish` gọi từng sự kiện, `on_minute` tách mỗi `POWER_LIMIT_CHANGED`. C: trạng thái trạm đổi (`inject_incident` / `fault_port` dưới `rt.lock`) **trước** khi phát sự kiện; nhả khoá rồi `on_event`; chỉ nguồn giảm có `curtail_to_limit`; ghi khoảng giữa đổi trạng thái và phản ứng là chưa có test (U1, R-6), không kết luận lỗi |
| N4 | Sửa | §5.1 báo cáo này: tiêu chí hoàn tất kiểm được + phụ thuộc + phần không thuộc task cho R-1…R-6, trạng thái CHƯA GIAO; registry §6.1 trỏ tới đây và tóm tắt chuỗi phụ thuộc |

**Đối chiếu source cho N3** (đọc 25/11 @ `ce23136`): `charging_service.py:221–232` (quote, `assume_consent=True`),
`:235–305` (vòng `for _attempt`, `continue` rời `booking_lock`, lưu + `upsert_vehicle` dưới `rt.lock`, hết lượt
⇒ `PROPOSAL_EXPIRED`, rồi `event_bus.publish`); `control_loop.py:66–137` (`on_event`), `:146–160` (`on_minute`),
`:163–195` (`run_forever` → `on_minute`), `:357–368` (`deliver_pending` → `on_minute`); `event_bus.py:34–42` (gọi handler
từng sự kiện); `simulation_service.py:375–389`; `hybrid_station.py:373–409`; `kernel.py:503–515`.

**Mermaid render — BLOCKER, không giả định đạt.** Không có renderer trong môi trường: không có `mmdc` trên PATH, không có
gói `mermaid` trong `frontend/node_modules`, npm global hoặc cache `npx`, không có gói Python tương ứng. Không tải thêm
dependency (ngoài phạm vi, cần mạng). Không dùng dịch vụ render ngoài (sẽ gửi tài liệu ra bên ngoài). **Chỉ** chạy kiểm
cú pháp thủ công (script tạm, không lưu): 3 `sequenceDiagram` — mọi dòng parse được thành participant / message /
`alt|loop|else|end|Note`, khối cân bằng, alias đã khai báo và không trùng từ khoá, không có `;` / `#` trong dòng. Hai
`flowchart` không được lint. Đây **không** thay cho render; điều kiện đóng: một người / agent có renderer (`mmdc` hoặc
xem trên GitHub) xác nhận 5 sơ đồ hiển thị.

**Kiểm sau khi sửa:** G1 / G2 (script tạm) trên registry, sơ đồ, báo cáo này — 17 tên test, 109 đường dẫn; chỉ thiếu các
mục cố ý ghi "không tồn tại" (4 test cũ, `scripts/check_registry.py`, `src/simulator/base.py`). `scripts/check_docs.py`:
PASS (50 file, 131 link). `git diff --check`: không lỗi khoảng trắng. Không chạy pytest (`src/`, `tests/` không đổi).

**Snapshot SHA-256** của tài liệu sau sửa: ghi ở `docs/handoff/HANDOFF.md` §1.4 (file này không tự chứa hash của chính
nó).
