# PHASE3_REPORT — Unified Runtime + Booking Migration (ADR-019)

> Nhánh `feature/unified-core-p3`, từ `749c042`. Thiết kế: `PHASE3_DESIGN.md`. Xoá: `DELETION_MANIFEST.md`.
> Tạm hỏng: `EXPECTED_FAILURES.md`. Log: `docs/refactor/raw/phase3/`. Evidence: `eval/evidence/2026-11-23-refactor-phase3/`.
> Dừng ở đây để Tech Lead review; **chưa** bắt đầu Phase 4.

## 1. Commit

| Commit | Bước | Nội dung |
|---|---|---|
| `27beea9` | 1 | `PHASE3_DESIGN.md` (trước khi code) |
| `f947b22` | 2 | Physical Core: `StationKernel` + `src/models/decisions.py`; `HybridSimulator` là kernel; `HybridStation.step` gọi `kernel.advance`; xoá `_charge_one_minute` |
| `ddfeb41` | 3 | Planning Core: `SimulatorScheduler.decide` = `kernel.propose` → consent → `kernel.approve`; xoá `_decide`; `PlanningContext` → `src/models/planning.py` |
| `0658fc2` | 4 | Replan: boundary của kernel làm mốc TICK, `REPLAN_REQUESTED` khi sạc xong / vượt budget, gộp sự kiện cùng phút |
| `d00ad0c` | 5 | Admission trên bản fork (`services/admission.py`); xoá LP backend A–D, `LiveStation` |
| `8fd6a02` | 6 | Differential (`tests/test_refactor/test_differential.py`) + admission ↔ thực thi (`tests/test_services/test_admission.py`) |
| `c5632cb` | 4 (sửa) | Sai lệch budget tính theo độ phân giải lệnh 0,01 kW / cổng (`POWER_TOL_KW`); log một lần / quyết định. Không đụng hard cap |
| (commit này) | 7 | Report, evidence, ADR-019 / CLAUDE.md |

## 2. Kiến trúc thực tế

```text
                    src/models/decisions.py  (TimeConfig, ProposedDecision, ApprovedDecision, AppliedResult, ReasonCode)
                                    ▲
 src/simulator/src/engine/hybrid.py │
   StationKernel ── observe() ── propose() ──────────── approve() ── apply_approved() ── advance()
        │            queue.advance  dispatch→coord→opt→guard  guard lại nếu bị chỉnh   connect+hold   tích phân + guard sau
        │            boundary() = queue.next_boundary + environment_boundary (một hàm)
        ├── HybridSimulator(StationKernel)     CLI, benchmark MVP-1/2/3, golden, DecisionTrace  (TimeConfig() = ZOH)
        └── HybridStation.kernel               backend (TimeConfig(1, 15)); fork() cho admission
                │ step(1) → advance + observe ; apply_commands → connect / hold_setpoint   (CHỈ guard/dispatcher gọi)
 src/services/hybrid_planner.py  SimulatorScheduler.decide: propose → consent (_start_minimums/_fit_with_minimums) → approve
 src/services/control_loop.py    on_event / on_minute: TICK ở mốc boundary, sự cố nguồn trước, gộp sự kiện cùng phút
                                 diff_commands → guard/dispatcher.submit (7 luật Business Guard → HITL) → apply_commands
 src/services/admission.py       fork_runtime → upsert xe giả định → on_minute + step(1) tới deadline (cùng đường trên)
 src/services/charging_service   quote / book / change = admission.evaluate → ScheduleProposal (+ phương án thay thế FR4)
```

Vị trí consent / Business Guard / HITL: sau `propose`, trước khi lệnh tới trạm. Consent là bước của `decide`
(plan đã chỉnh qua lại `guard(...)` trong `approve`); 7 luật + HITL nằm ở `guard/dispatcher.py` như cũ.

## 3. Moved / deleted / kept

- **Moved:** `src/optimizer/base.py` → `src/models/planning.py` (`git mv`, đổi docstring). Planning + execution của
  `HybridSimulator.step` cũ tách thành method của `StationKernel` cùng file (`engine/hybrid.py` được phép tách).
- **Deleted:** xem `DELETION_MANIFEST.md` (7 file xoá + 1 file `git mv`, 6 định nghĩa, 24 test LP / A–D kèm test thay thế).
- **Kept nguyên (cổng AST):** `src/optimizer/{dispatch,zones,coordination}`, `registry.py` (POLICIES đóng băng),
  `guard/physical/validator.py`, `charging_models/`, `engine/{ev2gym_adapter,queue}.py`,
  `src/models/{simulation_core,physical_constraints,physical_limits,charging_physics}.py`.
- **Kept, đổi nhỏ:** `HybridStation` (adapter trên kernel; thêm `fork`, `apply_approved` chỉ cho fork, `configure`,
  `next_decision_at`), `SimulatorScheduler` (`decide`), `runtime.py` (`make_station` chỉ hybrid, `fork_runtime`,
  `_memory_runtime`), `simulation_service._run` (dùng `on_minute`), `station_service._at_risk_bookings` (một định nghĩa).
- **Shim:** không thêm shim mới. Đã xoá `optimizer/__init__.__getattr__`. Shim Phase 1–2 trong `src/simulator/src/`
  giữ nguyên (Phase 4).

## 4. Bằng chứng "một engine"

- **Một vòng tích phân.** Trong `src/` chỉ còn **một** lời gọi `adapter.step(` (`StationKernel.advance`), một
  `validate_budgets(` + `coordinator(` (`StationKernel.propose`), một `queue.connect(` (`StationKernel.connect`), một
  `queue.next_boundary` + `environment_boundary(` (`StationKernel.boundary`). `_charge_one_minute`, `_decide`, LP backend,
  LiveStation đã xoá.
- **Golden giữ nguyên** ở chế độ tương thích: 163/163 test chủ simulator (không sửa test), `compare_sim_output.py` 39/39
  OK (§6), CSV trùng byte.
- **Backend dùng đúng code đó**: ở commit bước 2 (chỉ đổi Physical Core) benchmark backend 225/225 run giống hệt Phase 2
  (`raw/physical_core_step_backend_gate_f947b22.txt`).
- **Differential** (`tests/test_refactor/test_differential.py`, 10 test): offline `HybridSimulator` (vật lý 1') và
  `HybridStation` cho **cùng** gán cổng / setpoint / budget / interval ở mọi quyết định và **cùng** năng lượng / SOC /
  trạng thái / mốc hoàn thành (≤ 1e-9) — B0, M2b, M3a, M3b, mặc định; nguồn chung / độc lập; cắt nguồn (LimitEvent ↔
  sự cố); DC taper; xe đến / rời; xe đầy giữa interval; deadline bất khả thi; cổng lỗi / khôi phục; fallback solver.
  Thêm một test chứng minh hai cấu hình thời gian P1 cho số khác nhau (lý do không so benchmark chéo).
- **Admission = thực thi** (`tests/test_services/test_admission.py`, 4 test): quote trên fork rồi chấp nhận và chạy
  runtime thật → cùng cổng, lúc cắm, lúc bắt đầu / kết thúc, năng lượng (1e-9); ca bất khả thi quote báo thiếu; trạm live
  không đổi sau quote. Độ trễ đo trên máy này (`hybrid_evening`, M3a, 3 xe sẵn): DC 2 h 0,19 s (12 quyết định), AC 6 h
  0,30 s (23), AC 12 h 0,70 s (51).

## 5. Số phận A–D (đề xuất cho Tech Lead)

**Đề xuất: bỏ** (đã xoá code trong Phase 3 theo brief; khôi phục được từ blob SHA ở `DELETION_MANIFEST.md`).
- A_fcfs ≈ B0 (FCFS + equal share + fixed share) — B0 đã là baseline có version trong `registry.POLICIES`.
- A_edf: không có policy tương ứng. Nếu cần, thêm `Registration` dispatch `edf` + equal share thành policy mới (ví
  dụ `B0e`), không khôi phục LP backend.
- B / C: LP backend không DC taper, không coordinator; C = B vì F6 hoãn (ADR-015). Không cùng mô hình thực thi.
- D (oracle): cận trên lý tưởng dùng thông tin tương lai; muốn giữ phải viết lại thành optimizer có registration
  (được phép đọc `oracle_bookings`) — việc mới, không phải di chuyển.
- `StrategyName` / OpenAPI / dropdown S8 còn giá trị A–D (Phase 4 mục 3); chọn A–D trả 404 `not_found`.

## 6. Cổng kiểm

| Kiểm | Kết quả | Log |
|---|---|---|
| Cổng AST trên đường dẫn được bảo toàn (manifest Phase 2 lọc theo đường dẫn) | **rc=0**: 91 định nghĩa SAME, 0 đổi, 0 khai báo | `raw/phase3/ast_gate.txt`, `preserved_manifest.txt` |
| `pytest src/simulator/tests` | **163 passed** (test chủ simulator không sửa) | `raw/phase3/pytest_simulator.txt` |
| `pytest tests` | **468 passed, 8 skipped** | `raw/phase3/pytest_tests.txt` |
| Cổng KPI `compare_sim_output.py` (module map Phase 2, không thêm cặp: không có module thuật toán nào di chuyển) | **39/39 OK, rc=0**: 32 file so output HEAD `749c042` (MVP-1, MVP-1+mvp3cfg, VinFast, script mode: report / replay / events / DecisionTrace / CSV; MVP-2; MVP-3 + 8 DecisionTrace) + 7 so evidence 2026-11-22 | `raw/phase3/kpi_gate.txt` |
| MVP-3 / MVP-2 in ra | MVP-3 (AC/55 · DC/215): B0 45 · 58, M2b 45 · 82, M3a 45 · 82 TOU 896.13 USD, M3b 35 · 89; MVP-2 M2b DC 100/180 — giống Phase 0–2 | `raw/phase3/benchmark_mvp{2,3}.txt` |
| Benchmark backend sau bước 2 (`compare_backend_benchmark.py`) | **225/225 OK** | evidence `physical_core_step_backend_gate_f947b22.txt` |
| ruff check + format (`src tests eval scripts/refactor`) | pass | `raw/phase3/ruff.txt` |
| `export_openapi.py --check` | khớp (OpenAPI không đổi) | `raw/phase3/openapi_check.txt` |
| `scripts/check_docs.py` | pass | — |
| Standalone probe (`test_simulator_imports_without_the_backend_stack`, script mode) | pass, `src.models.decisions` trong `CORE_CONTRACTS` | `pytest_tests.txt` |

**Chưa chạy:** `make web-check`, E2E Postgres, LLM thật (OpenAPI không đổi).

## 7. Benchmark backend (semantics mới — không so "tốt / tệ")

Evidence: `eval/evidence/2026-11-23-refactor-phase3/` (100 run = 5 scenario × B0/M2b/M3a/M3b × seed 1–5, 128 s).
Trích trung bình 5 seed (đầy đủ ở `raw/backend_benchmark_seeds1-5_mean_vs_phase2.md`):

| scenario | policy | on_time P2 → sau bước 3 → P3 | unmet kWh P2 → P3 | cost VND P2 → P3 | peak kW P2 → P3 | vi phạm |
|---|---|---|---|---|---|---|
| hybrid_evening | B0 | 0.450 → 0.475 → 0.475 | 302.65 → 301.93 | 862,896 → 866,649 | 88.80 → 88.74 | 0 |
| hybrid_evening | M2b | 0.438 → 0.475 → 0.475 | 303.66 → 300.26 | 860,318 → 869,417 | 88.80 → 88.74 | 0 |
| hybrid_evening | **M3a** | 0.398 → 0.463 → 0.463 | 312.58 → 300.43 | 770,938 → 796,053 | 84.90 → 83.37 | 0 |
| hybrid_evening | M3b | 0.386 → 0.463 → 0.463 | 313.11 → 300.43 | 769,672 → 796,177 | 86.20 → 84.51 | 0 |
| hybrid_power_drop | B0 | 0.411 → 0.450 → 0.450 | 325.62 → 325.87 | 770,918 → 770,933 | 78.94 → 78.88 | 0 |
| hybrid_power_drop | **M3a** | 0.347 → 0.412 → 0.412 | 339.58 → 326.15 | 684,297 → 710,449 | 77.11 → 75.59 | 0 |
| hybrid_power_drop | M3b | 0.347 → 0.424 → 0.424 | 335.65 → 322.05 | 695,053 → 722,652 | 77.02 → 74.58 | 0 |
| peak_evening | M3a | 0.089 → — → 0.198 | 925.83 → 912.28 | 627,245 → 661,041 | 31.79 → 33.25 | 0 |

`power_limit_violations` = 0 ở cả 100 run; replan p95 ≤ 0,03 s. `blocked_commands` B0 / M2b (kịch bản AC-only legacy)
giảm 74.6 → 63.4 / 30.2 → 25.4 vì ít lần tính lại thừa hơn.

**Nguồn chênh lệch (theo PHASE0_FINDINGS §2):**
- Bước 2 (#1, #2, #12, #16, #17 — Physical Core): **0** chênh (225/225 giống hệt).
- Bước 3 (#3, #5, #7, #8, #14): gần như toàn bộ chênh lệch. Interval quyết định / planning = tới boundary kế tiếp (trần
  15') thay vì 15' cố định: `Candidate.allowed_kw`, block đầu của Rolling LP, `need_kw` của consent tính trên khoảng
  đúng; online observation dùng mốc đã biết; mốc TOU cắt interval. Ở snapshot `ddfeb41` on_time đã bằng số cuối (cột
  giữa). M3a / M3b nhận lại phần SLA đã mất ở backend Phase 0 (0.398 → 0.463), đổi lại chi phí cao hơn ~3 %, và khoảng
  cách M3a ↔ M2b về SLA thu hẹp như offline MVP-3. Đây là **quan sát**, không phải kết luận so sánh.
- Bước 4 (#4 replan khi sạc xong, TICK theo boundary, gộp sự kiện cùng phút): chênh nhỏ ở unmet / delivered (≤ ~1 kWh
  trung bình), on_time không đổi.
- Bước 5 (admission, xoá A–D): không ảnh hưởng benchmark (benchmark không gọi quote).
- Log ghi 2 lần sai lệch budget thật (AC +1,97 kW, cùng phút 560 ở hai run có kết quả trùng nhau — `peak_evening` và
  `connector_failure` cho số giống hệt vì sự cố của kịch bản legacy bị bỏ qua). Nguyên nhân **chưa xác minh**, nhiều khả
  năng là setpoint cũ còn giữ khi lệnh mới bị Business Guard (anti_flapping) chặn. Được ghi + replan một lần, không phải
  vi phạm vật lý (0 `power_limit_violations`).

## 8. Khác biệt PHASE0_FINDINGS §2 sau Phase 3

| # | Trạng thái | Ghi chú |
|---|---|---|
| 1 Độ phân giải vật lý | **Hợp nhất code**, khác cấu hình (P1) | Cùng `advance`; offline tương thích = ZOH, backend = 1'. Differential ở 1' trùng 1e-9 |
| 2 Thời điểm hoàn thành | Cùng quy tắc "cuối bước vật lý" | ZOH: cuối interval; 1': phút + 1 |
| 3 Interval quyết định | **Đổi semantics backend** | Tới boundary kế tiếp, trần 15' (trước: 15' cố định). Nguồn chênh benchmark chính |
| 4 Không replan khi sạc xong | **Sửa** | `REPLAN_REQUESTED` khi sạc xong; offline 1' dừng interval sớm |
| 5 Mốc TOU | **Sửa** | Boundary có mốc giá; TICK ở mốc đó |
| 6 Cắt nguồn | Còn khác cơ chế | Backend: sự cố có hiệu lực ngay (= LimitEvent công bố = hiệu lực); differential chứng minh cùng kết quả ở trường hợp này. Backend chưa có sự cố "báo trước" |
| 7 Thiếu `_online_observation` | **Sửa** | Cùng `propose` |
| 8 Quan sát sau dispatch dựng giả | **Sửa** | Dựng ảo trong kernel, cùng thứ tự với `queue.connect` (golden + differential) |
| 9 Consent giữa optimizer và guard | **Tách** | `decide`: propose → consent → `approve` (guard lại) |
| 10 Fail-safe khác nhau | Giữ chủ ý, có mã | `REJECTED_BEFORE_APPLY`; offline dừng, backend lịch 0 kW |
| 11 Post-check | **Tách hai loại** | Offline strict (budget); backend hard cap + `budget_deviation_kw` |
| 12 Setpoint thực thi | Cùng quy tắc `min(setpoint, allowed)` | Golden giữ (ZOH dùng setpoint đã qua guard) |
| 13 DecisionTrace backend | Chưa | `last_diagnostics` có policy / state_version / reason codes; chưa ghi trace đầy đủ (Phase 4) |
| 14 DC model | **Sửa** | Quan sát dùng `adapter.dc_model` (model đang thực thi) ở cả hai phía |
| 15 Dựng Vehicle từ booking | Giữ | Nghiệp vụ backend |
| 16 Đơn vị năng lượng | Giữ, nằm trong kernel | `kernel.output_kwh` (đầu ra) cạnh `Session.delivered_grid_kwh` (phía lưới) |
| 17 Cổng lỗi | **Primitive chung** | `kernel.fault_port / restore_port`; differential phủ |
| 18 Policy selection | Giữ | `selection()` chỉ truyền dispatch DC, AC dùng mặc định registry |

## 9. Câu hỏi cho Tech Lead

1. **A–D:** đồng ý bỏ hẳn (§5)? Nếu giữ A_edf / D làm baseline thì phải viết lại thành `Registration` mới — có cần
   trong Phase 4 không? Phase 4 có bỏ giá trị A–D khỏi `StrategyName` / OpenAPI / S8 không?
2. **Sự kiện sạc xong / vượt budget** đang dùng `REPLAN_REQUESTED` (detail ghi lý do) để không đổi OpenAPI. Có muốn
   thêm `EventType.CHARGE_COMPLETED` (đổi OpenAPI + `npm run gen:api` + nhãn S6) ở Phase 4 không?
3. **Độ phân giải lệnh** 0,01 kW / cổng được coi là không phải sai lệch budget (vì `diff_commands` không gửi lệnh nhỏ
   hơn). Hard cap vẫn kiểm với TOL 1e-7. Đồng ý ngưỡng này?
4. **Cắt nguồn báo trước** (#6): backend chỉ có sự cố hiệu lực ngay. Có cần API sự cố "công bố trước" ánh xạ thành
   `LimitEvent` để optimizer online thấy trước như offline không?
5. **Admission bỏ qua HITL**: lệnh cần duyệt trong fork coi như chưa thực thi (như benchmark), nên quote có thể bi quan
   hơn thực tế khi cư dân đồng ý. Chấp nhận, hay mô phỏng "đồng ý" theo consent mặc định?
6. **DecisionTrace backend** (#13): backend mới có `last_diagnostics` (policy, state_version, reason codes, interval).
   Có cần ghi DecisionTrace đầy đủ như offline (đưa vào DB / evidence) ở Phase 4?
7. **Vị trí kernel**: kernel ở `src/simulator/src/engine/hybrid.py` vì test chủ simulator monkeypatch `hybrid.guard`.
   Phase 4 có muốn đổi tên / tách gói công khai (ví dụ `src/simulator/core/`) khi dọn shim không?
8. **Bản số backend mới** (§7) có được dùng làm baseline cho Phase 4 (`compare_backend_benchmark.py`) không?
