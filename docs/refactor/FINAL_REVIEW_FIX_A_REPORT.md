# FINAL_REVIEW_FIX_A_REPORT — nhánh `feature/unified-core-review-a` (claude2)

> Brief: `docs/refactor/tasks/FINAL_REVIEW_FIX_BRIEF.md`. Nguồn: `docs/refactor/raw/final-review/FINAL_REVIEW_2026-11-24.md`
> §4.1, §4.2, §4.7. Gốc nhánh `7294803`. Log cổng kiểm: `docs/refactor/raw/final-review-a/`.
> Không push / merge / rebase. Không sửa `CLAUDE.md`, ADR, `REFACTOR_REPORT.md`, `FINAL_MAP.md` (đề xuất ở §7).

## 1. Tóm tắt

| Mục | Kết quả | Commit |
|---|---|---|
| 4.1 Policy lấy từ registry | Backend (planner, runtime, simulation_service, API, CLI benchmark) tra `registry.POLICIES` trực tiếp. Policy mới đăng ký bằng `register_policy` chạy trên `HybridStation` / control loop / Guard / API mà không sửa orchestration. `GET /api/v1/simulation/policies`. Khối `planning:` tuỳ chọn trong `station.yaml`. | `8e7e72d`, `56de0ea`, `3481f2c` |
| 4.2 DC model ở backend | `HybridStation(dc_charging_model=<tên DC_MODELS>)`. `with_vinfast_profiles` chạy được. Provider resolve profile khi xe được upsert (xe đến động). Backend trùng offline từng phút. | `a2bb8eb`, `e5e32b9` → `89fae6c` |
| 4.7 Benchmark fail-fast | Thêm `strict_incidents` cho service, API và `run_benchmark.py --strict-incidents` (exit 3). Mọi chế độ đều ghi `incidents` (planned / applied / skipped). Mặc định vẫn bỏ qua sự cố + ghi note như cũ. | `8e7e72d`, `4ed0b7d`, `63dfd77` |

So với baseline: **0 chênh lệch**, chỉ khác latency.
- Benchmark: 100 / 100 run, 0 problems.
- Golden simulator: 0 unexpected.
- AST: 114 compared, 0 undeclared.

Test: 554 passed / 8 skipped (trước: 521 / 8). Simulator: 163 passed. Không assertion cũ nào bị đổi: `git diff --numstat 7294803 HEAD -- tests` chỉ có dòng thêm.

## 2. Mục 4.1 — Registry / policy

### Đã làm

- **`src/optimizer/registry.py`**: chỉ thêm, các định nghĩa cũ giữ nguyên AST (cổng AST 114/114 vẫn trùng).
  - `FROZEN_POLICY_IDS`, `POLICY_VERSIONS` (B0 / M2b / M3a / M3b có version `"1"`), `POLICY_DESCRIPTIONS`.
  - `PolicySpec` gồm id, version và bốn thành phần.
  - `policy_spec(id)` và `policy_specs()` đọc thẳng `POLICIES`, nên cấu hình monkeypatch của `test_registry_extension.py` vẫn được thấy.
  - `register_policy(spec)`:
    - từ chối id đã có, kể cả B0–M3b: không ghi đè M2b / M3a;
    - từ chối thành phần chưa đăng ký.
  - `unregister_policy`: không gỡ được policy đóng băng.
  - `POLICIES` vẫn là bảng thành phần duy nhất, nên `benchmark_mvp3` cũng thấy policy mới.
- **`src/services/hybrid_planner.py`**:
  - `SimulatorScheduler(name: StrategyName | str, …, parameters=…)`:
    - kiểm `is_registered` trên `registry.POLICIES`, không dùng danh sách cứng;
    - `policy_id` / `policy_version` lấy từ registry;
    - `name` giữ kiểu `StrategyName` cho B0–M3b (tương thích), và là chuỗi cho policy mới.
  - `selection()` nhận thêm tham số theo thành phần và tên DC model (tuỳ chọn). Thiếu thì trả đúng selection cũ.
  - `POLICIES` / `SIMULATOR_STRATEGIES` / `POLICY_VERSION` giữ nguyên để tương thích.
- **`src/services/runtime.py`**:
  - `make_scheduler` nhận id chuỗi; id lạ trả `DomainError(NOT_FOUND)`.
  - `make_station` đọc `planning.dc_charging_model`.
  - `live_policy(config)`:
    - lấy `planning.policy_id` nếu có, không thì env `LIVE_STRATEGY` như cũ;
    - `planning.version` phải khớp version trong registry;
    - trả cả `planning.parameters`.
  - `fork_runtime` mang theo `parameters`.
- **Config**: `StationConfig.planning: PlanningPolicyConfig | None`.
  - Các khoá: `policy_id`, `version`, `dc_charging_model`, `parameters` theo `dispatch_dc` / `optimizer_ac` / `optimizer_dc` / `coordinator`.
  - `config/station.yaml` chỉ thêm ví dụ dạng comment, nên giá trị không đổi (test catalog vẫn pass).
- **API**: `GET /api/v1/simulation/policies` → `list[PolicyInfo]`, đọc từ registry qua `simulation_service.list_policies()`. `POST /simulation/runs` nhận `policy_id`.
- **Phần còn lại**:
  - `simulation_service`, `admission` (`policy` của Admission), `control_loop` (lý do lệnh `Lịch vN (<policy_id>)`, chuỗi y hệt cho B0–M3b) và `eval/run_benchmark.py` dùng `policy_id`.
  - `--strategies` của CLI nhận mọi id có trong registry. Id lạ cho exit 2.

### Đường tương thích (enum `StrategyName` giữ nguyên)

`StrategyName` vẫn nằm trong hợp đồng, giữ đúng 4 giá trị. Khi enum không nhận được id mới, dùng các trường chuỗi tuỳ chọn:

- **`SimulationRunRequest`**:
  - `strategy` thành tuỳ chọn; thêm `policy_id` (chuỗi) và `strict_incidents` (tuỳ chọn).
  - Validator: phải có một trong hai trường; `policy_id` mặc định bằng `strategy.value`; hai trường mâu thuẫn thì 422.
  - Body cũ `{scenario_id, strategy}` vẫn validate y như trước.
- **`SchedulePlan`, `SimulationRunResult`**: thêm `policy_id`, `policy_version`.
  - `strategy` vẫn mang đúng giá trị cũ cho B0–M3b, và chỉ là `None` khi chạy policy đăng ký mới.
  - Payload cũ trong DB chỉ có `strategy` vẫn đọc được: `policy_id` tự điền (có test).
- **Cột DB `schedule_plans.strategy` (`String(8)`)**:
  - B0–M3b ghi như cũ.
  - Policy mới có id dài hơn 8 ký tự ghi `"custom"`. Id đầy đủ nằm trong `payload` (mà `row_to_plan` đọc).
  - **Không đổi schema / Alembic.** Lý do: cột này chỉ là tóm tắt. Thêm một revision `0004` song song với nhánh B (4.6 có thể cần migration) sẽ sinh hai head khi gộp.
- **Frontend**:
  - `openapi.json` và `schema.d.ts` sinh lại.
  - Màn S8 hiển thị `policy_id ?? strategy`.

### Test chứng minh — `tests/test_refactor/test_policy_registry.py`, 16 test

- `test_planner_and_station_run_a_new_policy_end_to_end`:
  - đăng ký `T41-edf` (EDF + equal share AC + `deadline_first` DC + fixed share, version `test-2`) — tổ hợp không có trong B0–M3b;
  - `build_sim_runtime(…, "T41-edf")` chạy 9 giờ control loop thật;
  - metadata cho thấy đúng `deadline_first` và `edf`; kernel mang `policy_id` / `version` mới;
  - mọi `SchedulePlan` có `policy_id = T41-edf`, `strategy = None`;
  - có điện được cấp, 0 vi phạm, có DecisionTrace;
  - B0–M3b không đổi.
- `test_simulation_service_runs_new_and_old_policy_side_by_side`: M3a chạy trước và sau khi chạy policy mới cho KPI và notes y hệt (bỏ qua `replan_p95_seconds`).
- `test_registering_an_existing_id_is_refused[B0|M2b|M3a|M3b]`, `test_registering_unknown_components_is_refused`, `test_frozen_policies_keep_id_version_and_components`.
- API:
  - `test_policies_endpoint_reads_the_registry`: danh sách = `registry.POLICIES`, M3a đủ trường;
  - `test_policies_endpoint_needs_operator`;
  - `test_run_endpoint_accepts_a_new_policy_id`: id mới trả 200; id lạ trả 404 với envelope `not_found`.
- Config:
  - `test_missing_planning_block_keeps_live_strategy`;
  - `test_planning_block_selects_policy_version_and_parameters`: version sai thì lỗi;
  - `test_planning_parameters_reach_the_optimizer`: `horizon_minutes` 60 tới được `RollingHorizonLP.config`, mặc định 120.
- `test_policy_fields_are_backward_compatible`: payload / body cũ, mâu thuẫn, cột DB `custom`.
- `tests/test_refactor/test_registry_extension.py` (cũ) vẫn pass, không sửa.

## 3. Mục 4.2 — DC vehicle profile ở backend

### Đã làm

- **`src/simulator/core/charging_models/live_profiles.py`** (file mới; không sửa class model sạc cũ):
  - `DynamicVehicleProfilesDCModel.register_vehicle(vehicle, scenario)` resolve profile bằng **đúng** `VehicleProfilesDCModel.from_scenario` chạy trên scenario chỉ có xe đó. Nhờ vậy dùng cùng bảng model và cùng kiểm dung lượng pin với offline.
  - `acceptance_kw`, `stored_kwh`, `metadata_for`, `_profile` là **chính các function** của `VehicleProfilesDCModel` gán lại làm method. Thân hàm không bị chép, nên chỉ có một implementation vật lý.
  - Có `forget_vehicle`, `clear` (khi reset) và `fork()` (bản fork admission tách bảng profile). `__deepcopy__` cũng gọi `fork`.
- **`src/simulator/core/algorithms.py`**: `station_dc_model(name, scenario)` tra cùng `DC_MODELS` với offline.
  - `vinfast_profiles_v0_1` dựng provider động (`STATION_DC_MODELS`).
  - Model không cần danh sách xe được dựng thẳng từ `DC_MODELS`.
  - Tên lạ thì lỗi.
- **`src/simulator/hybrid_station.py`**:
  - tham số `dc_charging_model` (mặc định `None`, tức `SyntheticTaperV1()` như cũ; không được truyền cùng `dc_model`);
  - `with_vinfast_profiles(...)` thay cho `NotImplementedError`;
  - `upsert_vehicle` / `_update_present` gọi `register_vehicle`, `_forget` gỡ profile;
  - `fork()` tách provider cho bản fork (trạm live không đổi).
- **Backend**:
  - `planning.dc_charging_model` → `make_station`, áp cho live, benchmark và fork admission.
  - `SimulatorScheduler` ghi metadata `dc_charging_model` theo tên của trạm, và `algorithms.dc_charging_model` trỏ đúng đối tượng vật lý của trạm.
  - Trạm mặc định đi đúng đường cũ.

### Test chứng minh

Các test nằm cuối `tests/test_refactor/test_differential.py`, thêm 10 test, không sửa test cũ trong file.

**Vì sao không để file riêng.** Bản đầu nằm ở `test_dc_profiles_backend.py` (`e5e32b9`). File đó import nội bộ simulator ngoài danh sách consumer khai báo, nên `test_architecture.py::test_only_declared_consumers_reach_into_simulator_internals` đỏ. Brief cấm nới danh sách đó, nên test được chuyển vào `test_differential.py`: file này đã là consumer khai báo cho đúng loại so sánh offline ↔ backend (`89fae6c`).

- `test_backend_vinfast_profiles_match_offline_minute_by_minute[B0-1, M2b-5]`. Đội xe gồm VF3, VF8_NEW_2026, VF9_123, một xe DC không nhãn và một xe AC.
  - Offline là `HybridSimulator` + `vinfast_profiles_v0_1` (profile từ danh sách xe). Backend là `HybridStation.with_vinfast_profiles` (profile resolve lúc upsert).
  - Hai phía có cùng bảng profile.
  - Mỗi quyết định khớp: gán cổng, setpoint, budget, interval.
  - Sau mỗi quyết định khớp: năng lượng, SOC và mốc hoàn thành từng xe (≤ 1e-9).
  - Với timestep 1': `AppliedResult` từng phút trùng công suất thực ≤ 1e-9.
  - **Không có chênh lệch nào cần giải thích.**
  - Kiểm mutation thủ công: cho `with_vinfast_profiles` trả trạm synthetic thì `_run` fail ngay phút 0 (setpoint VF3 24 kW so với 21,12 kW). Test này không vô nghĩa.
- `test_profiles_change_the_physics_compared_to_synthetic`: đối chứng, VinFast ≠ synthetic.
- `test_vehicle_arriving_later_gets_its_profile_on_upsert`:
  - trạm chạy 30' rồi mới nhận VF8: profile đúng `resolve_dc_profile`;
  - xe lạ nhận profile `UNKNOWN` như offline;
  - xe sai dung lượng pin rơi về fallback và được ghi vào `unresolved`;
  - huỷ xe thì profile bị gỡ.
- `test_strict_provider_refuses_a_mismatched_profile`.
- `test_fork_registers_what_if_vehicles_without_touching_live`.
- `test_default_station_keeps_synthetic_taper`, `test_unknown_model_name_and_double_choice_are_refused`.
- `test_config_planning_block_selects_the_dc_model_for_backend_runs`: booking sinh thật qua `visit_of`, dung lượng pin lấy từ `config/vehicles.yaml`; mọi xe DC nhận profile VinFast, `unresolved` rỗng.

### [GIẢ ĐỊNH] / giới hạn

- **Xe không resolve được profile** (sai dung lượng pin với model đã biết):
  - mặc định dùng fallback synthetic, ghi `unresolved` + log warning. Lý do: trạm live không được chết vì một booking;
  - `strict=True` thì raise;
  - offline thì raise ngay khi dựng scenario.
- **Bản fork của `fork_runtime`**:
  - nhận `algorithms` của scheduler live, nên `kernel.algorithms.dc_charging_model` của bản fork trỏ provider live;
  - trường này chỉ dùng cho metadata / nhãn: vật lý và observation dùng `adapter.dc_model`, đã được tách ở `HybridStation.fork`;
  - đã ghi lại để nhánh B (4.4 fork isolation) xem khi gộp.

## 4. Mục 4.7 — Benchmark nghiên cứu fail-fast

### Đã làm

- **`simulation_service.run_scenario` / `run_benchmark` thêm `strict_incidents` (mặc định `False`)**:
  - strict:
    - kiểm mọi sự cố trỏ đầu nối **trước khi dựng trạm**, trỏ đầu nối không tồn tại thì `InvalidIncidentError` (`DomainError` mã `not_found`);
    - sự cố bị trạm từ chối lúc bơm cũng là lỗi;
  - mặc định: bỏ qua + note **đúng định dạng cũ** (baseline so note từng ký tự: khớp).
- **Mọi chế độ**: `SimulationRunResult.incidents = {planned, applied, skipped, skipped_details, strict}` là trường mới, tuỳ chọn, nằm ngoài `kpis` / `notes`, nên cổng so baseline không đổi.
- **API**: `POST /simulation/runs` nhận `strict_incidents` (tuỳ chọn); lỗi trả 404 envelope.
- **CLI**: `eval/run_benchmark.py --strict-incidents` (exit 3).
- Không sửa evidence cũ, không tạo suite / scenario mới.

### Test chứng minh — `tests/test_services/test_strict_incidents.py`, 8 test

- `test_strict_mode_fails_fast_on_a_missing_connector`: `connector_failure` trỏ A05 → lỗi, và `build_sim_runtime` không được gọi lần nào.
  - Test này bắt được một lỗi thật ở bản đầu: kiểm tra nằm sau bước dựng trạm. Đã sửa ở `4ed0b7d`.
- `test_default_mode_keeps_skip_and_note_and_counts_incidents`: note cũ y hệt; planned 2, applied 0, skipped 2.
- `test_valid_incidents_are_all_applied_in_both_modes[False|True]`: `hybrid_power_drop` cho 4 / 4 / 0.
- `test_incident_that_fails_while_injecting_is_an_error_in_strict_mode`: lưới an toàn thứ hai.
- `test_benchmark_cli_exits_3_in_strict_mode`, `test_benchmark_cli_rejects_unknown_policy`, `test_run_endpoint_strict_incidents`.
- Benchmark 100 run mặc định (`benchmark_compare.txt`): mỗi kịch bản 20 run, số đếm (planned, applied, skipped) như sau:

  | Kịch bản | planned | applied | skipped |
  |---|---|---|---|
  | `connector_failure` | 2 | 0 | 2 |
  | `power_drop` | 2 | 2 | 0 |
  | `hybrid_power_drop` | 4 | 4 | 0 |
  | `peak_evening` | 0 | 0 | 0 |
  | `hybrid_evening` | 0 | 0 | 0 |

  Hai kịch bản `legacy_ac_only` (A05) giờ hiện rõ "sự cố không diễn ra" trong dữ liệu.

## 5. Cổng kiểm (log trong `docs/refactor/raw/final-review-a/`)

| Cổng | Kết quả | Log |
|---|---|---|
| `ruff check` + `ruff format --check` `src tests scripts/refactor eval/run_benchmark.py` | pass (214 file) | `ruff.txt` |
| `ruff check scripts` (toàn bộ) | 8 lỗi **có sẵn**, chỉ ở hook `scripts/log_*.py`, `submit_log.py`; nhánh này không đụng (`git diff 7294803 -- scripts` rỗng) — xem §6 | `ruff.txt` |
| `pytest tests -q` | **554 passed, 8 skipped** (≥ 521) | `pytest_tests.txt` |
| `pytest src/simulator/tests -q` | **163 passed** | `pytest_simulator.txt` |
| AST `compare_ast_manifest.py … -- src` | **114 compared, 0 undeclared**, exit 0 | `ast_gate.txt` |
| Golden simulator: `run_sim_kpi_gate.py run` + `compare_sim_output.py` với `eval/evidence/2026-11-22/raw/sim-hardware/` | **0 unexpected** ở cả 7 cặp; số allowed trùng `phase4-final/kpi_gate.txt`: MVP3 20, MVP2 0, MVP1 9, mvp3cfg 13, VinFast 10, script 9, DecisionTrace 0 | `sim_run.txt`, `kpi_gate.txt` |
| `eval/run_benchmark.py --seeds 1,2,3,4,5` + `compare_backend_benchmark.py` với baseline final | **OK — 100 / 100 run, 0 problems** | `eval_run_benchmark.txt`, `benchmark_compare.txt` |
| `export_openapi.py --check` (sau khi sinh lại) | khớp | `openapi_check.txt` |
| `check_docs.py` | pass (50 file, 131 link) | `check_docs.txt` |
| `eval/run_agent_eval.py --offline` | pass | `eval_agent_offline.txt` |
| Frontend `gen:api`, `npm ci`, `lint`, `typecheck`, `test`, `build` | pass, 28 test | `web_checks.txt` |

`eval/results/` (benchmark và output simulator `final-review-a-sim/`, script tạm) không commit.

## 6. ESCALATION

1. **`ruff check scripts` (cả thư mục) không sạch** do 8 lỗi có sẵn trong hook ghi log AI (`scripts/log_antigravity.py`, `log_hook.py`, `log_manual.py`, `submit_log.py`).
   - Baseline `phase4-final/ruff.txt` cũng chỉ chạy `scripts/refactor`.
   - CLAUDE.md cấm can thiệp hook log, và việc này ngoài phạm vi. Không sửa.
   - Điều phối quyết định có sửa riêng không.
2. **Ba cặp golden "vs phase0"** (MVP1 DecisionTrace / replay / events của `phase4-final/kpi_gate.txt`) không so lại được: output Phase 0 không nằm trong repo.
   - Hành vi này được phủ bởi golden test của `src/simulator/tests` (163 pass).
   - Các cặp so với evidence 2026-11-22 đều 0 unexpected.
3. **Cột `schedule_plans.strategy` `String(8)`**: không đổi schema (lý do ở §2). Nếu muốn lọc theo id policy mới ở mức DB thì cần một revision Alembic nới cột, nên làm **sau** khi gộp nhánh B để giữ một head.
4. Không có test cũ nào phải đổi assertion. Không thêm dependency.

## 7. Đề xuất sửa tài liệu (điều phối cập nhật khi gộp)

- **`docs/refactor/FINAL_MAP.md` §3**: bỏ câu "Policy mới dùng được qua API cần thêm giá trị vào `StrategyName`". Thay bằng:
  - đăng ký policy mới bằng `registry.register_policy(PolicySpec(...))`;
  - chọn policy qua `policy_id` (API / CLI / `planning.policy_id`);
  - `GET /simulation/policies` là danh sách hợp lệ.
  - Thêm `station_dc_model` / `live_profiles.py` vào đường tiêm.
- **`docs/refactor/REFACTOR_REPORT.md`**:
  - §6: thêm test policy mới hoàn toàn (`test_policy_registry.py`) bên cạnh `test_registry_extension.py`;
  - §8: bỏ ý "Chưa có … hiệu chuẩn DC taper" khỏi phần backend, vì profile VinFast đã chạy được ở backend; hiệu chuẩn phần cứng thì vẫn chưa có.
- **`CLAUDE.md`** (Quick Rehydrate / Commands):
  - khối `planning:` tuỳ chọn trong `config/station.yaml`;
  - `GET /api/v1/simulation/policies`;
  - `run_benchmark.py --strict-incidents` cho benchmark nghiên cứu MVP-3.5.
- **ADR-019** (hoặc ADR mới nhỏ):
  - ghi đường tương thích `strategy` (enum đóng băng) ↔ `policy_id` (chuỗi registry);
  - quy ước model DC có trạng thái phải có `fork()` (khớp hướng 4.4 của nhánh B).
- **`docs/handoff/HANDOFF.md:43`**: bỏ "profile DC VinFast cho xe đến dần (`with_vinfast_profiles` TODO)", vì việc này đã làm ở nhánh này.
- **`docs/refactor/PHASE0_FINDINGS.md:67`** (#14): giữ nguyên vì là lịch sử. Có thể thêm ghi chú "đã xử lý ở Final Review 4.2".
