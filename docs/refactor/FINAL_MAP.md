# FINAL_MAP — bản đồ đường dẫn sau refactor Unified Core (ADR-019)

> Trạng thái: nhánh `feature/unified-core-p4-final` (final acceptance, chờ Tech Lead review).
> Danh sách xoá chi tiết + test thay thế: `DELETION_MANIFEST.md`. Bằng chứng: `REFACTOR_REPORT.md`.

## 1. Old path → new path

| Trước (`68692ee`) | Sau | Owner logic | Phase |
|---|---|---|---|
| `src/simulator/src/scenario.py` | `src/models/simulation_core.py` | simulator (gốc) | 1 |
| `src/simulator/src/observations.py`, `dispatch/base.py`, `coordination/base.py`, `optimizers/base.py` | `src/models/scheduling/{observations,dispatch,coordination,optimization}.py` | simulator (gốc) | 1 |
| `src/simulator/src/safety/{constraints,limits}.py` (+ `valid_kw` từ `safety/guard.py`) | `src/models/{physical_constraints,physical_limits}.py` | simulator (gốc) | 1 |
| `src/simulator/src/charging_models/base.py` | `src/models/charging_physics.py` | simulator (gốc) | 1 |
| `src/simulator/src/dispatch/{arrival_order,edf,least_laxity}.py` | `src/optimizer/dispatch/` | simulator (gốc) | 2 |
| `src/simulator/src/optimizers/{ac_lp,rolling_lp,equal_share,deadline_first}.py` | `src/optimizer/zones/` | simulator (gốc) | 2 |
| `src/simulator/src/coordination/{fixed_budget,dynamic_slack}.py` | `src/optimizer/coordination/` | simulator (gốc) | 2 |
| registry trong `src/simulator/src/algorithms.py` + `POLICIES` của `benchmark_mvp3.py` / `hybrid_planner.py` | `src/optimizer/registry.py` (một nguồn) | simulator (gốc) | 2 |
| phần ghép vật lý của `algorithms.py` (`Algorithms`, `DC_MODELS`, `resolve_algorithms`) | `src/simulator/core/algorithms.py` | simulator (gốc) | 2 → 4 |
| `src/simulator/src/safety/guard.py` | `src/guard/physical/validator.py` | simulator (gốc) | 2 |
| `src/guard/physical.py` | `src/guard/physical/adapter.py` | backend | 2 |
| `src/simulator/base.py` (StationReader / StationActuator / VehicleVisit) | `src/models/station_protocols.py` | backend | 2 |
| `src/optimizer/base.py` (PlanningContext, Scheduler) | `src/models/planning.py` | backend | 3 |
| `HybridSimulator.step` (engine/hybrid.py) | `StationKernel` `src/simulator/core/kernel.py` + facade `src/simulator/hybrid.py` | simulator (gốc, tách theo trách nhiệm) | 3 → 4 |
| `src/simulator/src/engine/{queue,ev2gym_adapter}.py`, `charging_models/*` | `src/simulator/core/{queue,ev2gym_adapter}.py`, `src/simulator/core/charging_models/` | simulator (gốc) | 4 |
| `src/simulator/src/evaluation/*` | `src/simulator/evaluation/*` | simulator (gốc) | 4 |
| `src/agents/*` (chat cư dân) | `src/llm_chat/*`; `AgentDecision / FinalAnswer / AgentAnswer` → `src/llm_chat/schemas.py` | backend | 4 |
| `src/agents/` | dành cho AI-1 / AI-4 (chỉ `__init__.py`) | — | 4 |
| `charging_service._what_if` (LP backend) | `src/services/admission.py` (fork trạm + cùng kernel / policy / Guard) | backend | 3 |
| `src/optimizer/__init__.py::get_scheduler` | `src/services/runtime.make_scheduler` (chỉ policy của registry) | backend | 2 → 3 |

**Đã xoá, không có đường dẫn mới:**
- LP backend A–D: `optimizer/{assignment,lp_model,horizon,mpc,baselines,strategies}.py`.
- `src/simulator/live.py` (`LiveStation`).
- `HybridStation._charge_one_minute`, `SimulatorScheduler._decide`.
- Gói shim `src/simulator/src/**`, `__getattr__` tương thích.
- Template chat `retrieve_node`, `synthesize_node`.
- `PlanningContext.oracle_bookings`.

## 2. Chiều import thực tế (khoá bằng `tests/test_architecture.py`)

```text
models (hợp đồng thuần stdlib + DTO pydantic)
  ▲   ▲            ▲                    ▲
optimizer ─────────┘ (dispatch/zones/coordination/registry: chỉ models)
  ▲                guard/physical/validator (chỉ models)      guard/* nghiệp vụ (rules, approval, dispatcher)
  │                  ▲                                          │ (cấm import simulator)
simulator (core/kernel, hybrid, evaluation) ── chỉ optimizer.{dispatch,zones,coordination,registry} + guard.physical.validator
  ▲
services (runtime, control_loop, hybrid_planner, admission, decision_trace, charging_service…) → tất cả
  ▲
api ──► services ; llm_chat ──► services, models, config (chỉ api import llm_chat.graph) ; agents (AI-1/AI-4) ──► services
```

Không vòng giữa `models / optimizer / guard / simulator`, tính cả import tương đối. Simulator standalone import được
khi chặn pydantic / fastapi / sqlalchemy / langchain / langgraph / openai.

## 3. Đường tiêm policy (thay optimizer không viết lại backend)

`config` / `LIVE_STRATEGY` → `StrategyName` (B0 / M2b / M3a / M3b) → `src/optimizer/registry.py POLICIES` (dispatch DC,
optimizer AC, optimizer DC, coordinator) → `resolve_algorithms` (`src/simulator/core/algorithms.py`, gắn DC charging
model) → `StationKernel.propose` → consent → `approve` (Physical Guard) → `guard/dispatcher` (Business Guard / HITL) →
`apply_commands` → `StationKernel.advance`.

Thêm optimizer: viết class đúng Protocol trong `src/models/scheduling`, đăng ký ở `registry.OPTIMIZERS` /
`COORDINATORS` / `DISPATCH`, thêm policy mới vào `POLICIES` (B0–M3b đóng băng). Có test chứng minh:
`tests/test_refactor/test_registry_extension.py`.

Cập nhật Final Review 4.1 / 4.2 (`FINAL_REVIEW_FIX_REPORT.md`): policy mới đăng ký bằng
`registry.register_policy(PolicySpec(...))` (B0–M3b đóng băng, version `"1"`) là chạy được trên backend mà không sửa
orchestration — chọn qua `policy_id` (API / CLI / khoá tuỳ chọn `planning.policy_id` trong `config/station.yaml`);
`StrategyName` giữ nguyên làm đường tương thích. `GET /api/v1/simulation/policies` trả danh sách hợp lệ từ registry.
Test: `tests/test_refactor/test_policy_registry.py`. DC model của backend chọn theo tên `DC_MODELS`
(`station_dc_model`, `src/simulator/core/charging_models/live_profiles.py` cho xe đến động).

## 4. Gotchas

- Hai cấu hình thời gian P1: golden / CLI dùng `TimeConfig()` (ZOH cả interval), backend dùng vật lý 1'. **Không so
  benchmark chéo cấu hình.**
- Đổi model / endpoint: `scripts/export_openapi.py`, rồi `npm run gen:api`.
- Alembic một head: `0001 → 0002 (decision_traces) → 0003 (xoá lịch lưu A–D, dữ liệu dẫn xuất)`. Deploy cần
  `alembic upgrade head`.
- `STATION_ENGINE` chỉ còn `hybrid`. Image cần `ev2gym` (`--no-deps`).
- `eval/results/archive/` và `eval/evidence/2026-11-2{1,2}` là archive (A–D / LiveStation). Baseline hiện hành (đóng
  băng): `eval/evidence/2026-11-24-unified-core-frozen-baseline/`; `…-final-baseline/` giữ làm lịch sử (cùng KPI).
- Baseline mới: chép `benchmark.json` + `manifest.json` nháp do `run_benchmark.py` sinh (có `experiments`,
  fingerprint), điền `baseline_id` / `version` / `status`, rồi đổi `BENCHMARK_BASELINE_DIR`.
- Fork: `isolation.STATELESS` / `__stateless__`, `NESTED`, `StatefulComponentError`; `HybridSimulator.fork` tách bản ghi.
- Sự kiện trạm: `StationRuntime.outbox` / `advance_clock` / `take_events`, `control_loop.deliver_pending`,
  `runtime.register_app_loop` (lifespan). Fail-safe: `AppliedResult.hard_violations`, `guard/emergency.py`
  (`curtail_to_hard_limits`, `stop_faulty_vehicles`). Admission: `StationRuntime.admission_fingerprint`.
- Frontend S8 đọc policy từ `GET /simulation/policies`, gửi `policy_id` (không còn danh sách cứng).
