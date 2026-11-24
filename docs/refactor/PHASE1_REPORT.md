# PHASE1_REPORT — tách hợp đồng/DTO, chuẩn bị dependency graph

> Nhánh `feature/unified-core`, tính từ `dad6e6b` (tài liệu Phase 0). Quyết định: ADR-019.
> **Không đổi hành vi nghiệp vụ, objective, công thức vật lý; không xoá implementation.** Log thô:
> `docs/refactor/raw/phase1/`. Evidence benchmark: `eval/evidence/2026-11-23-refactor-phase1/`.

## 1. Đã di chuyển (`git mv`, lịch sử rename giữ nguyên)

| Từ | Sang | Thay đổi nội dung |
|---|---|---|
| `src/simulator/src/scenario.py` | `src/models/simulation_core.py` | không (file không có import nội bộ) |
| `src/simulator/src/charging_models/base.py` | `src/models/charging_physics.py` | không |
| `src/simulator/src/safety/constraints.py` | `src/models/physical_constraints.py` | thêm `valid_kw` (chuyển nguyên văn từ `safety/guard.py`) + import `isfinite`, `Real` |
| `src/simulator/src/safety/limits.py` | `src/models/physical_limits.py` | 1 import: `..scenario` → `src.models.simulation_core` |
| `src/simulator/src/observations.py` | `src/models/scheduling/observations.py` | 3 import → `src.models.*` |
| `src/simulator/src/dispatch/base.py` | `src/models/scheduling/dispatch.py` | 1 import |
| `src/simulator/src/coordination/base.py` | `src/models/scheduling/coordination.py` | 2 import |
| `src/simulator/src/optimizers/base.py` | `src/models/scheduling/optimization.py` | 1 import |

Mới: `src/models/scheduling/__init__.py` (re-export các hợp đồng scheduling, kèm docstring "stdlib only").

**Provenance (commit `0287fe3`).** Vì shim được tạo lại ở đường dẫn cũ, git ghi các file mới là copy. `git log --follow`
vẫn lần ngược về commit của chủ simulator cho 7/8 file (ví dụ `simulation_core.py` → `b95b840`, `8c4c14e`, `d15871a`…).
Riêng `physical_constraints.py` (có thêm `valid_kw`) cần `git blame -C -C src/models/physical_constraints.py`: các
dòng gốc được gán về `326a34d` và `94cbbc9` (Le Hien Hieu).

## 2. Shim ở vị trí cũ (re-export, cùng đối tượng)

8 file mới tại đúng đường dẫn cũ: `scenario.py`, `charging_models/base.py`, `safety/constraints.py`,
`safety/limits.py`, `observations.py`, `dispatch/base.py`, `coordination/base.py`, `optimizers/base.py`. Mỗi file chỉ
có `from src.models.… import …` + `__all__`. Test `test_core_contract_shims_reexport_the_same_objects` kiểm `is`.
`safety/constraints.py` re-export thêm `valid_kw` để `safety/guard.py` và hai optimizer (`fixed_budget`,
`rolling_lp`, vẫn import `..safety.guard.valid_kw`) chạy mà không phải sửa.

## 3. File gốc bị sửa (chỉ import / entrypoint)

| File | Sửa | Lý do |
|---|---|---|
| `src/simulator/src/safety/guard.py` | bỏ `def valid_kw` + import `isfinite`, `Real`; `valid_kw` lấy từ `.constraints` | để Phase 2 optimizer không phải import guard; thân hàm giữ nguyên (cùng hash AST) |
| `src/simulator/run.py` | nhánh script-mode: thêm gốc repo vào đầu `sys.path`, import `src.simulator.src.*` | chế độ `python src/simulator/run.py` phải thấy `src.models` (yêu cầu standalone) |

Không file thuật toán nào khác trong `src/simulator/src/` bị sửa (dispatch, optimizers, coordination, engine,
charging_models, evaluation, algorithms).

## 4. Import đã sửa phía backend (trỏ thẳng `src.models`)

| File | Trước | Sau |
|---|---|---|
| `src/guard/physical.py` | 7 import `src.simulator.src.*` | 5 import `src.models.*`; còn 2 import `safety.guard.{guard, validate_dispatch}` (implementation) |
| `src/services/hybrid_planner.py` | 6 | 4 `src.models.*`; còn `algorithms.resolve_algorithms`, `safety.guard.*` |
| `src/simulator/hybrid_station.py` | 10 | 6 `src.models.*`; còn `synthetic_dc`, `engine.{ev2gym_adapter,queue}`, `safety.guard` |
| `tests/test_simulator/test_hybrid_station.py` | 2 | `Scenario` từ `src.models.simulation_core`; còn `engine.hybrid.HybridSimulator` |

Cạnh import vào `simulator.src(core)` từ ngoài giảm: guard 7→2, services 6→2, hybrid_station 10→4, tests 2→1
(`raw/phase1/import_edges.txt` so với `raw/phase0/import_edges.txt`).

## 5. Test kiến trúc mới (`tests/test_architecture.py`, nhóm 7; không xoá / nới luật cũ)

| Test | Khoá điều gì |
|---|---|
| `test_core_contracts_are_pure_stdlib` | hợp đồng core chỉ import stdlib + chính nhóm hợp đồng |
| `test_core_contract_shims_reexport_the_same_objects` | shim trả đúng đối tượng |
| `test_contracts_are_imported_from_models_outside_the_simulator` | ngoài `src/simulator/` không dùng đường dẫn shim |
| `test_only_transitional_adapters_reach_into_simulator_internals` | chỉ 4 adapter chuyển tiếp + CLI simulator chạm `src.simulator.src.*` |
| `test_core_layers_have_no_import_cycle` | đồ thị `models/optimizer/guard/simulator` không vòng |
| `test_simulator_imports_without_the_backend_stack` | CLI, benchmark, engine, evaluation, hợp đồng import được khi chặn pydantic/fastapi/sqlalchemy/langchain/langgraph/openai |
| `test_simulator_script_mode_entrypoint_runs` | `python src/simulator/run.py --list-scenarios` |
| `test_standalone_probe_really_blocks_the_backend_stack` | tự kiểm: bộ chặn thật sự chặn |

Mutation check (đã hoàn tác): thêm `import pydantic` vào hợp đồng thì 2 test fail; import shim từ `src/services`
thì 2 test fail; `src.models` import `src.guard` thì test vòng fail.

## 6. Bằng chứng không đổi hành vi

| Kiểm | Phase 0 | Phase 1 |
|---|---|---|
| Hash AST từng hàm/lớp top-level (198 định nghĩa: simulator core, guard, optimizer, hybrid_station, live, base, CLI, hybrid_planner) | manifest Phase 0 | **198/198 trùng** (197 cùng chỗ, `valid_kw` cùng hash ở file mới), `raw/phase1/manifest_compare.txt` |
| `pytest` | 440 passed, 8 skipped | **448 passed, 8 skipped** (+8 test kiến trúc) |
| `pytest src/simulator/tests …` | 163 passed | **163 passed** (gồm golden regression) |
| MVP-3 benchmark vs evidence 2026-11-22 | 0 khác biệt KPI | **0** |
| MVP-2 benchmark (+ VinFast sensitivity) | 0 | **0** |
| `run mvp1` / `mvp1 + algorithms_mvp3` / `vinfast` | chỉ khác metadata | **chỉ khác metadata** (`run_id`, `command`, đường dẫn) |
| `python src/simulator/run.py` (script mode) | chạy | **chạy**, KPI = mvp1 mặc định |
| OpenAPI | `9f01b5f…` | **`9f01b5f…`** (không đổi) |
| ruff `src tests` | pass | **pass** |
| Benchmark backend 225 run (5 scenario × 9 chiến lược × 5 seed) | `raw/phase0/eval_benchmark_seeds1-5.json` | **225/225 run KPI giống hệt** (trừ `replan_p95_seconds`), `eval/evidence/2026-11-23-refactor-phase1/` |

`eval/results/benchmark.{json,md}` **không bị ghi**: lần này benchmark chạy với `RESULTS_DIR` trỏ ra thư mục tạm.

## 7. Giới hạn / việc chưa làm trong Phase 1

- `BOUNDARIES` chưa đổi. `simulator ↛ optimizer/guard` vẫn còn, nên thuật toán chưa thể chuyển. Phase 2 mở luật này
  cùng lúc với việc di chuyển thuật toán.
- Code gốc trong `src/simulator/src/` vẫn import hợp đồng qua shim (cố ý, để diff nhỏ). Phase 2 sẽ đổi sang
  `src.models` khi di chuyển từng module.
- Chưa có `ProposedDecision`/`ApprovedDecision`/`AppliedResult` (guide Phase 1.3). Các kiểu này gắn với thiết kế kernel
  và ba tham số thời gian, nên sẽ đề xuất ở đầu Phase 3 để review chung, không tạo trước khi có caller.
- Kiểu dataclass đổi `__module__`. Không có golden/report/API nào chứa trường này (đã kiểm bằng golden + OpenAPI).
- `CLAUDE.md` (Current Invariants) vẫn ghi "KHÔNG sửa `src/simulator/src/`". ADR-019 đã sửa đổi điểm này, nhưng chưa sửa
  `CLAUDE.md` vì cần bạn duyệt trước.
- Chưa chạy: `npm run build`, E2E Postgres, LLM thật (giống Phase 0). Frontend không bị ảnh hưởng vì OpenAPI không đổi.

## 8. Đề xuất bước kế (chờ duyệt, chưa làm)

**Phase 2 (di chuyển cơ học thuật toán + physical guard):**
1. `git mv` dispatch, zones, coordination sang `src/optimizer/…`.
2. `safety/guard.py` sang `src/guard/physical/`.
3. `algorithms.py` sang `src/optimizer/registry.py`.
4. Mở `BOUNDARIES` thành `simulator → optimizer, guard.physical` và cập nhật ADR-019.

Cần giải quyết trước một việc: `src/optimizer/__init__.py` hiện import `get_scheduler`, kéo theo LP backend và
pydantic. Khi simulator import `src.optimizer.dispatch`, chế độ standalone sẽ hỏng. Đề xuất cho `src/optimizer/__init__.py`
nạp trễ hoặc chuyển `get_scheduler` sang `src/optimizer/backend/…`. Đây là đổi public import path, nên cần bạn quyết.

## 9. Đính chính sau review (2026-11-23)

Review chỉ ra `compare_manifest.py` luôn `return 0`. Kiểm lại thì có **ba lỗi trong công cụ kiểm chứng**:

| # | Lỗi | Ảnh hưởng tới kết luận đã báo | Sửa |
|---|---|---|---|
| 1 | `compare_manifest.py` in số định nghĩa khác nhưng luôn exit 0 | Con số "198/198 trùng" đọc từ output in ra là đúng (chạy lại vẫn ra 198/0). Nhưng script **không dùng được làm cổng tự động**, và báo cáo đã không nói điều này. | Exit 1 khi có định nghĩa khác/mất hoặc không so được gì; fail nếu một file có hai tên trùng (đã kiểm: manifest Phase 0/1 không có tên trùng). Mutation đổi hash `ACRollingLP` cho exit 1. |
| 2 | `cmpbench.py` luôn exit 0 | Như trên: kết luận lấy từ output, không có cổng. | Exit 1 khi lệch ngoài danh sách cho phép. |
| 3 | Regex "timing" của `cmpbench.py` khớp theo **chuỗi con** (`solver`, `path`, `created`, `python`…) | Đã **không so** `rejected_solver_plan_count` (KPI) và `algorithm_metadata/*/solver` (cấu hình). Câu "0 khác biệt KPI ngoài timing" ở BASELINE và mục 6 **chưa được kiểm đủ** cho các trường đó. | Chỉ bỏ đúng tên trường thời gian tường (`decision_latency_ms`, `solver_latency_ms`, `solver_latency_by_zone_ms`, `latency_p95_target_ms`, `solver_ms`, `decision_ms`, `software`, `platform`, `python`); chỉ cho phép khác ở `/metadata/{run_id,command,algorithms/*/config_source}`. |

**Kiểm lại** bằng công cụ đã sửa, trên đúng các output đã chạy ở Phase 0 và Phase 1:
- 11/11 cặp OK (MVP-3, MVP-2, mvp1, mvp1+mvp3cfg, vinfast × Phase 0/1, cộng mvp1 script mode).
- 0 khác biệt ngoài danh sách cho phép.
- Kết quả: `raw/phase1/recheck_strict_cmpbench.txt`. Mutation `rejected_solver_plan_count += 1` bị bắt, exit 1.

`compare_manifest.py` chạy lại cho exit 0 với 198 định nghĩa so được, 0 khác (`raw/phase1/manifest_compare.txt`).

**Kết luận của Phase 0/1 không đổi, nhưng trước lần kiểm lại này, một phần chưa có bằng chứng đầy đủ.** Từ nay mọi
script so sánh dùng làm bằng chứng phải trả exit khác 0 khi lệch, và phải có mutation test trước khi trích kết quả.

Phần **không** bị ảnh hưởng: so benchmark backend 225 run dùng so sánh trực tiếp mọi KPI (trừ `replan_p95_seconds`),
không qua regex. pytest/golden regression của simulator là test thật có assert.
