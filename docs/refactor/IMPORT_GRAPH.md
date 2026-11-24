# IMPORT_GRAPH — Phase 0 (trước refactor)

> Đo trên `feature/unified-core` = `origin/develop` @ `68692ee` (2026-11-23). Chỉ đọc, chưa sửa code.
> Cách đo: phân tích AST mọi file `.py` trong `src/ tests/ eval/ scripts/ migrations/` (1263 câu import), gom theo
> tầng. "lazy" = import nằm trong thân hàm (import trễ). Script: `docs/refactor/raw/phase0/{imports,layers}.py`;
> lệnh tái tạo ở cuối file.

## 1. Đồ thị tầng hiện tại (production code, không tính tests/eval)

```text
api ─────────► services ─► models
 │  └────────► agents ──► services, models, config      (agents KHÔNG import optimizer/guard/simulator/db)
 │
services ─► optimizer (6: base, assignment, lp_model, get_scheduler)
         ─► guard (5)            ─► db (3) ─► forecast (1)
         ─► simulator.base (1), simulator.live (1), simulator.hybrid_station (1, lazy)
         ─► simulator.src(core) (6: CHỈ src/services/hybrid_planner.py)
guard ───► models (13), services.errors (1: approval.py → DomainError)
       ─► simulator.base (1), simulator.src(core) (7: CHỈ src/guard/physical.py)
optimizer ► models (9)                                  (sạch: không import simulator/guard)
simulator.hybrid_station ► simulator.src(core) (10), simulator.base, models
simulator.live ──────────► simulator.base, models
simulator.base ──────────► models
simulator.src(core) ─────► (chỉ import tương đối nội bộ + numpy/scipy/ev2gym)
```

Số cạnh đầy đủ (kể cả tests/eval): `docs/refactor/raw/phase0/import_edges.txt`.

## 2. Ai import `src.simulator.src.*` từ bên ngoài core

Ngoài `src/simulator/src/` và `src/simulator/tests/` (40 import nội bộ của bộ test simulator), chỉ có **4 file**:

| File | Import từ core | Vai trò |
|---|---|---|
| `src/simulator/hybrid_station.py` | `charging_models.{base,synthetic_dc}`, `dispatch.base`, `engine.{ev2gym_adapter,queue}`, `observations`, `safety.{constraints,guard,limits}`, `scenario` | Adapter trạm + **vòng vật lý thứ hai** (`_charge_one_minute`) |
| `src/services/hybrid_planner.py` | `algorithms.resolve_algorithms`, `observations`, `optimizers.base.PowerProposal`, `safety.{constraints,guard}`, `scenario.Tariff` | **Ghép lại** `HybridSimulator.step` (`_decide`) |
| `src/guard/physical.py` | `dispatch.base`, `observations`, `safety.{constraints,guard,limits}`, `scenario` | Adapter mỏng: map DTO backend → gọi Guard simulator (không chép logic) |
| `tests/test_simulator/test_hybrid_station.py` | `engine.hybrid.HybridSimulator`, `scenario` | Test replay parity mvp1 |

Con số "63" trong guide là tổng mọi tham chiếu `src.simulator.src` kể cả test nội bộ của simulator.

## 3. Đồ thị phụ thuộc NỘI BỘ của core (`src/simulator/src/`) — quyết định thiết kế Phase 1

| Module | Phụ thuộc nội bộ | Ghi chú cho đích §1.1 |
|---|---|---|
| `scenario.py` | — | thuần → `src/models/simulation_core.py` |
| `safety/constraints.py` | — | thuần (`TOL`, `ConstraintViolationError`) → models |
| `charging_models/base.py` | — | thuần Protocol (`VehicleBatteryState`, `DCChargingModel`, `energy_to_target`) → `models/charging_physics.py` |
| `safety/limits.py` | scenario | `EffectiveLimits` (dữ liệu) + `effective_limits()` + `environment_boundary()` (hàm thuần của Scenario) |
| `observations.py` | charging_models.base, safety.limits, scenario | DTO → `models/scheduling.py`; kéo theo `EffectiveLimits` + `DCChargingModel` |
| `dispatch/base.py` | observations | `DispatchObservation` (DTO) + `DispatchPolicy` (Protocol) |
| `coordination/base.py` | observations, safety.constraints | `ZoneBudgets` (DTO) + `GlobalCoordinator` (Protocol) |
| `optimizers/base.py` | observations | `PowerProposal` (DTO) + Protocols |
| `safety/guard.py` | coordination.base, dispatch.base, observations, scenario, constraints, limits | **Guard phụ thuộc kiểu của optimizer** (`ZoneBudgets`, `DispatchObservation`) |
| `coordination/fixed_budget.py` | observations, constraints, **safety.guard** (`valid_kw`) | **optimizer → guard** |
| `optimizers/rolling_lp.py` | charging_models.base, observations, constraints, **safety.guard** (`valid_kw`), scenario, equal_share | **optimizer → guard** |
| `optimizers/ac_lp.py` | observations, constraints, limits, scenario, equal_share | |
| `evaluation/trace.py` | **dispatch.least_laxity**, constraints, scenario | evaluation → optimizer (hợp lệ nếu evaluation ở tầng simulator) |
| `charging_models/vehicle_profiles.py` | scenario, base, dc_charging_models, synthetic_dc | |
| `engine/ev2gym_adapter.py` | charging_models.{base,synthetic_dc}, constraints, scenario | + `ev2gym` |
| `engine/queue.py` | scenario, ev2gym_adapter | |
| `engine/hybrid.py` | gần như mọi module | orchestration |
| `algorithms.py` | mọi dispatch/optimizer/coordinator/dc model + safety.guard | registry thành phần + composition |

**Hệ quả:** chuyển thẳng `safety/` → `src/guard/physical/` và `optimizers/`,`coordination/` → `src/optimizer/` sẽ tạo
vòng `optimizer ↔ guard` vì:
1. `safety/guard.py` cần `ZoneBudgets` (coordination.base) và `DispatchObservation` (dispatch.base).
2. `fixed_budget.py` và `rolling_lp.py` cần `valid_kw` từ `safety/guard.py`.

Lời giải không cần đổi logic: đưa các DTO/Protocol (`ZoneBudgets`, `DispatchObservation`, `PowerProposal`,
`Candidate`, `VehicleObservation`, `SchedulingObservation`, `EffectiveLimits`, `Scenario`/`Cabinet`/`Vehicle`/
`Tariff`/`LimitEvent`, `TOL`, `ConstraintViolationError`, `valid_kw`, `DCChargingModel`) xuống `src/models/`.
`valid_kw` là một hàm số học 3 dòng. Chuyển nó đi là đổi chỗ, không đổi thân hàm, nhưng vẫn cần ghi vào change note.

## 4. Ràng buộc hiện tại của `tests/test_architecture.py`

| Package | Cấm import |
|---|---|
| agents | simulator, guard, optimizer, forecast, db, api |
| api | guard, optimizer, simulator, forecast, db |
| guard | agents, services.llm, api, db, optimizer, forecast — **được phép import simulator** |
| optimizer | agents, api, services, simulator, guard, db, forecast |
| simulator | agents, api, services, optimizer, guard, db, forecast |
| models | mọi tầng + sqlalchemy/fastapi/langchain/langgraph/openai/yaml |

Ngoài ra còn các luật: chỉ `guard/dispatcher.py` gọi `apply_commands`, ORM chỉ ở `db/` + `repository.py`, agent không
dựng `Command`, tool agent chỉ gọi `services/models/agents/config`, frontend chỉ dùng type sinh.

Luật đích (§1.1 của guide) đảo chiều `simulator ↛ optimizer/guard` thành `simulator → optimizer, guard.physical`.
Phase 1 phải viết lại bảng này kèm ADR mới, không xoá test.

## 5. Phụ thuộc ngoài Python cần sửa khi đổi đường dẫn

- `.github/workflows/ci.yml:99-107`: job `simulator` chạy `pytest src/simulator/tests`, cache `src/simulator/requirements-ci.txt`.
- `requirements-runtime.txt:32-34`: chú thích đường dẫn engine.
- `eval/build_simulator_evidence.py:52-61`: đọc output từ `src/simulator/outputs/...`.
- `src/simulator/run.py:19-27`: **chạy được ở 2 chế độ import**. Có `from .src.…` (chạy dạng package) và nhánh dự phòng
  `from src.…` (chạy standalone từ thư mục `src/simulator/`, xem `src/simulator/requirements.txt` và `AGENTS.md`
  riêng). Nếu tách core ra `src/optimizer` và `src/guard`, chế độ standalone sẽ hỏng. **Cần chủ simulator xác nhận có
  còn dùng chế độ này không.**
- `render.yaml`, `render.test.yaml`, `.env.example`: `STATION_ENGINE=hybrid`, `LIVE_STRATEGY=M3a`.

## 6. LLM chat (`src/agents/`): import ra ngoài

- `src/agents` → `services` (catalog, charging_demo, charging_service, energy, errors, llm), `models` (api, charging,
  schemas), `config`. Không import optimizer/guard/simulator/db. `services` **không** import ngược `agents`.
- Bên ngoài vào `src.agents`: `src/api/routes.py` (1), `eval/run_agent_eval.py`, `eval/run_eval.py`,
  `tests/conftest.py`, `tests/__init__.py` (chú thích), 11 file `tests/test_agents/*`, `tests/test_api/test_flows.py`
  (monkeypatch chuỗi `"src.agents.mock_llm._now_local"`), `tests/test_architecture.py` (tên package).
- `prompts/` được nạp bằng đường dẫn cố định `src/agents/prompts.py:18` (`parent.parent.parent / "prompts"`). Đổi
  độ sâu thư mục sẽ hỏng loader.

## Tái tạo

```bash
.venv/Scripts/python.exe docs/refactor/raw/phase0/imports.py . /tmp/imports.json
.venv/Scripts/python.exe docs/refactor/raw/phase0/layers.py /tmp/imports.json      # = import_edges.txt
.venv/Scripts/python.exe scripts/refactor/ast_manifest.py src/simulator/src            # hash nội dung/AST
rg -n 'src\.simulator\.src' src tests eval scripts --glob '!src/simulator/**'
```
