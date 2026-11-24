# PHASE2_REPORT — di chuyển thuật toán + Physical Guard gốc (ADR-019)

> Nhánh `feature/unified-core`, từ `b3d8ecc` (Phase 1 đã duyệt + đính chính công cụ). Không đổi thuật toán,
> objective, tham số solver, charging physics, event/interval. LP backend cũ chưa xoá.
> Log: `docs/refactor/raw/phase2/`. Evidence: `eval/evidence/2026-11-23-refactor-phase2/`.

## 1. Bốn vấn đề của review Phase 1

| # | Vấn đề | Đã làm | Bằng chứng |
|---|---|---|---|
| 1 | `compare_manifest.py` luôn exit 0 | Công cụ chuyển sang `scripts/refactor/` (`git mv`): `ast_manifest.py`, `compare_ast_manifest.py`, `compare_sim_output.py`, thêm `compare_backend_benchmark.py`. Cả bốn fail (exit 1) khi lệch. Manifest hash thêm hằng số cấp module (`DISPATCH`, `POLICIES`…). Thay đổi chủ ý phải khai báo kèm lý do (`--allow-changed`); khai báo mà không thật sự đổi cũng fail. | `tests/test_refactor_tools.py`: 13 test, gồm ca âm cho đổi thân hàm, đổi hằng số, mất định nghĩa, trùng tên, khai báo không lý do / stale, KPI lệch, `rejected_solver_plan_count` lệch, module-map sai, run backend thiếu / KPI lệch |
| 2 | `src/guard/physical.py` trùng tên package `src/guard/physical/` | Thành package: `validator.py` (Guard gốc), `adapter.py` (file cũ, `git mv`), `__init__.py` (chỉ nạp validator). Tên cũ `check_dispatch`, `check_site_allocation`, `check_connector_allocation`, `effective_limits`, `EMPTY_PREFIX`, `simulator_guard` vẫn import được qua `__getattr__`. | `test_physical_guard_package_keeps_the_old_public_api_without_loading_the_backend`; `tests/test_guard` pass |
| 3 | `src/optimizer/__init__.py` nặng | `git mv __init__.py → strategies.py`. `__init__` mới không import gì; `from src.optimizer import get_scheduler` vẫn chạy qua `__getattr__`. | `import src.optimizer` không nạp pydantic; probe standalone import `src.optimizer.{dispatch,zones,coordination,registry}` khi chặn backend stack |
| 4 | Test kiến trúc bỏ qua import tương đối | `_imported_modules` resolve `ImportFrom.level` (kể cả `__init__.py`, `from . import x`, nhiều chấm). Đồ thị tầng và luật ranh giới tính cả import tương đối. | `test_relative_imports_are_resolved_to_absolute_modules`, `test_cycle_detector_finds_a_cycle_made_only_of_relative_imports` (vòng optimizer↔guard giả bị bắt), `test_boundary_checker_sees_relative_imports` |

## 2. File đã di chuyển (`git mv`, `docs/refactor/raw/phase2/moves.txt`)

| Từ | Sang | Thay đổi nội dung |
|---|---|---|
| `src/simulator/src/dispatch/{arrival_order,edf,least_laxity}.py` | `src/optimizer/dispatch/` | chỉ import → `src.models.*` |
| `src/simulator/src/optimizers/{ac_lp,rolling_lp,equal_share,deadline_first}.py` | `src/optimizer/zones/` | chỉ import; `valid_kw` từ `src.models.physical_constraints`; `.equal_share` giữ tương đối |
| `src/simulator/src/coordination/{fixed_budget,dynamic_slack}.py` | `src/optimizer/coordination/` | chỉ import |
| `src/simulator/src/safety/guard.py` | `src/guard/physical/validator.py` | chỉ import |
| `src/guard/physical.py` | `src/guard/physical/adapter.py` | 2 import → `validator`; dòng đầu docstring |
| `src/simulator/base.py` | `src/models/station_protocols.py` | không. Lý do: `guard/dispatcher.py` import `StationActuator` từ simulator, nên khi simulator dùng `guard.physical` sẽ tạo vòng guard ↔ simulator |
| `src/optimizer/__init__.py` | `src/optimizer/strategies.py` | docstring |

**Định nghĩa chuyển giữa file** (cắt nguyên văn theo vị trí AST, cùng hash):
- `Registration`, `_fixed_budget`, `_fixed_share`, `_dynamic_slack`, `_rolling_lp`, `_llf`, `_ac_rolling_lp`,
  `DISPATCH`, `OPTIMIZERS`, `COORDINATORS`: `src/simulator/src/algorithms.py` → `src/optimizer/registry.py`.
- `POLICIES` (B0/M2b/M3a/M3b): `src/simulator/benchmark_mvp3.py` → `src/optimizer/registry.py`.

`algorithms.py` giữ phần ghép với vật lý: `Algorithms`, `default_algorithms`, `DC_MODELS`, `_synthetic_taper`,
`_vehicle_profiles`, `algorithm_labels`, `_choice`, `_metadata`, `resolve_algorithms`. Lý do: chọn DC charging model
là việc của lõi vật lý, và optimizer không được import simulator.

**Một thay đổi chủ ý** (`raw/phase2/declared_changes.txt`): `src/services/hybrid_planner.py::POLICIES` thôi chép tay,
chuyển sang ánh xạ `StrategyName → registry.POLICIES`. Giá trị là chính các tuple của registry (`is`).

`src/simulator/benchmark.py::POLICIES` (MVP-2: B0/M2a/M2b/M2c, 2 cột) **chưa gộp**. Bảng này khác schema và là bộ
benchmark lịch sử; gộp vào registry phải đổi schema, nên để Phase 4 quyết định.

## 3. Import đã sửa

- Production simulator: `algorithms.py`, `evaluation/trace.py`, `engine/hybrid.py` dùng `src.optimizer.*` và
  `src.guard.physical.validator`.
- Backend: `services/hybrid_planner.py` (validator, registry), `simulator/hybrid_station.py` (validator,
  station_protocols), `services/runtime.py` (`strategies`, `station_protocols`), `guard/dispatcher.py`
  (`station_protocols`), `guard/rules.py` (`physical.adapter`), `simulator/live.py` (`station_protocols`).
- Test backend: `test_optimizer/{test_optimizer_contracts,test_strategies}.py`, `test_guard/test_physical.py`,
  `test_simulator/{test_hybrid_station,test_simulator_contracts}.py`.
- **Không sửa** test của chủ simulator (`src/simulator/tests/*`). Các test này dùng đường dẫn cũ qua shim, nên đồng
  thời chứng minh shim tương thích.

## 4. Shim còn lại (xoá ở Phase 6 khi hết caller, ghi vào deletion manifest)

**Alias `sys.modules`** (cùng object module; monkeypatch như `rolling_lp.linprog`, `ac_lp.linprog` trong
`test_mvp2/3` vẫn tác động đúng implementation):

| Shim | → | Caller còn lại |
|---|---|---|
| `src/simulator/src/dispatch/{arrival_order,edf,least_laxity}.py` | `src.optimizer.dispatch.*` | không còn caller |
| `src/simulator/src/optimizers/ac_lp.py` | `src.optimizer.zones.ac_lp` | `sim/tests/test_mvp3.py` |
| `src/simulator/src/optimizers/rolling_lp.py` | `src.optimizer.zones.rolling_lp` | `sim/benchmark.py`, `sim/tests/test_mvp2.py` |
| `src/simulator/src/optimizers/equal_share.py` | `src.optimizer.zones.equal_share` | `sim/tests/test_hardening.py` |
| `src/simulator/src/optimizers/deadline_first.py` | `src.optimizer.zones.deadline_first` | không còn caller |
| `src/simulator/src/coordination/fixed_budget.py` | `src.optimizer.coordination.fixed_budget` | `sim/tests/test_modular.py` |
| `src/simulator/src/coordination/dynamic_slack.py` | `src.optimizer.coordination.dynamic_slack` | không còn caller |
| `src/simulator/src/safety/guard.py` | `src.guard.physical.validator` | không còn caller |
| `src/simulator/base.py` | `src.models.station_protocols` | không còn caller |

**Re-export** (Phase 1, hợp đồng):

| Shim | Caller còn lại |
|---|---|
| `src/simulator/src/scenario.py` | 18 file trong simulator (engine, evaluation, CLI, test chủ simulator) |
| `src/simulator/src/safety/constraints.py` | 13 |
| `src/simulator/src/charging_models/base.py` | 6 |
| `src/simulator/src/coordination/base.py` | 4 |
| `src/simulator/src/dispatch/base.py`, `optimizers/base.py`, `safety/limits.py` | 2 mỗi file |
| `src/simulator/src/observations.py` | 1 |

**Tương thích `__getattr__`**: `src/optimizer/__init__.py` (`get_scheduler`, `PlanningContext`, `Scheduler`),
`src/guard/physical/__init__.py` (tên cũ của adapter). Trong repo không còn caller nào dùng các tên cũ này.

Ngoài `src/simulator/` không còn file nào dùng đường dẫn cũ (đã kiểm bằng `_imported_modules`, có tính import tương
đối). Danh sách adapter chuyển tiếp được chạm `src.simulator.src.*` đã bỏ `src/guard/physical.py`; còn
`hybrid_station.py`, `hybrid_planner.py`, `test_hybrid_station.py`. Ba file này thuộc Phase 3.

## 5. Ranh giới mới (`tests/test_architecture.py`, không xoá luật cũ)

- simulator: bỏ cấm `src.optimizer` / `src.guard` cho cả gói; thay bằng hai luật hẹp hơn.
  - `test_simulator_uses_only_algorithm_packages_of_the_optimizer`: chỉ `src.optimizer.{dispatch,zones,coordination,registry}`.
  - `test_simulator_uses_only_the_physical_validator_of_the_guard`: chỉ `src.guard.physical.validator`.
- guard: **thêm** cấm `src.simulator`.
- `test_optimizer_algorithm_packages_depend_only_on_contracts`: gói thuật toán chỉ import hợp đồng core + chính nhóm.
- `test_policy_bundles_have_a_single_source`.
- Probe standalone import thêm `src.optimizer.{dispatch,zones,coordination,registry}`, các module LP,
  `src.guard.physical`, `src.guard.physical.validator` khi chặn backend stack.
- Đồ thị `models / optimizer / guard / simulator` không vòng (tính cả import tương đối).

## 6. Nghiệm thu

| Kiểm | Kết quả | Log |
|---|---|---|
| Cổng AST (345 định nghĩa: hàm, lớp, hằng số cấp module) so baseline Phase 2 | **exit 0**: 0 thay đổi chưa khai báo, 1 thay đổi khai báo (§2), 11 định nghĩa MOVED-SAME → registry | `raw/phase2/ast_gate.txt` |
| `pytest` | **468 passed, 8 skipped** (+21 test so với Phase 1: 13 công cụ, 8 kiến trúc) | `raw/phase2/pytest_tests.txt` |
| `pytest src/simulator/tests …` (golden regression) | **163 passed**, test chủ simulator không sửa | `raw/phase2/pytest_simulator.txt` |
| ruff `src tests scripts/refactor` (check + format) | pass | `raw/phase2/ruff.txt` |
| OpenAPI `--check` | khớp | `raw/phase2/openapi_check.txt` |
| Cổng KPI (`compare_sim_output.py` + module map 4 cặp) | **11/11 OK, rc=0**: MVP-3, MVP-2 + VinFast sensitivity, mvp1, mvp1+mvp3cfg, vinfast, mvp1 script mode (so evidence 2026-11-22); DecisionTrace mvp1 (so Phase 0) và mvp1+mvp3cfg (so evidence); replay.json, events.json (so Phase 0) | `raw/phase2/kpi_gate.txt` |
| Benchmark backend 225 run (`compare_backend_benchmark.py`) | **OK**: 225/225, 0 vấn đề (trừ `replan_p95_seconds`) | như trên |

**Metadata được phép khác** (danh sách đầy đủ ở cuối `kpi_gate.txt`):
- `/metadata/{run_id, command, command[i]}` và `/metadata/algorithms/*/config_source`: định danh lần chạy và đường
  dẫn cấu hình.
- `.../implementation` của dispatch / optimizers / coordinator / physical_guard: chỉ khi khớp **đúng** module map
  (`raw/phase2/module_map.txt`: `src.simulator.src.{dispatch,optimizers,coordination,safety.guard}` →
  `src.optimizer.{dispatch,zones,coordination}`, `src.guard.physical.validator`). `implementation` của
  `dc_charging_model` không đổi, vì charging model chưa di chuyển.

**Một lần nới tiêu chí, ghi rõ:** cổng KPI ban đầu FAIL ở `replay.json` vì `/metadata/command[3..5]`. Đây là argv của
CLI, lần này truyền `--decision-trace` sau `--output-dir`. Regex cho phép trước đó chỉ khớp khi độ dài `command`
khác nhau. Mình đổi để khớp thêm từng phần tử `command[i]`, và thêm test chứng minh metadata khác (ví dụ `engine`) vẫn
fail. Không có KPI nào được nới.

**Chưa chạy:** `npm run build`, E2E Postgres, LLM thật. OpenAPI không đổi, `make web-check` không bị ảnh hưởng.

## 7. Chưa làm / để phase sau

- Hai runtime (`HybridSimulator.step` ↔ `HybridStation._charge_one_minute` + `SimulatorScheduler._decide`), cùng các
  thay đổi event / interval / replan: Phase 3, chờ duyệt.
- `src/simulator/src/{engine,charging_models,evaluation}` chưa đổi chỗ (ngoài phạm vi Phase 2).
- LP backend A–D (`base, baselines, mpc, lp_model, horizon, assignment`) giữ nguyên vì quote/booking còn dùng: Phase 4.
- `CLAUDE.md`: đã cập nhật mục "Simulator là gốc" và cây kiến trúc theo ADR-019 (được phép). Không đổi chính sách an
  toàn hay quyền Git.
