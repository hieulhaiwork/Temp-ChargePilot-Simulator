# EXPECTED_FAILURES — test / consumer tạm hỏng trong refactor Unified Core

> Quy tắc (PLAN.md): không xoá test, không làm yếu safety check để che lỗi. Mỗi mục ghi test / consumer nào, vì sao,
> commit nào sẽ sửa. Test bị xoá cùng code đã xoá nằm ở `DELETION_MANIFEST.md`, không ở đây.

## Phase 3 (nhánh `feature/unified-core-p3`, tới commit của `PHASE3_REPORT.md`)

**Test tự động:** không có test fail. `pytest` backend 468 passed + 8 skipped; `pytest src/simulator/tests` 163 passed
(log ở `docs/refactor/raw/phase3/`).

**Consumer biết là hỏng / lệch (chưa có test bắt), sửa ở Phase 4 mục 3:**

| Consumer | Hiện tượng | Vì sao | Sửa |
|---|---|---|---|
| Frontend S8 (`frontend/src/app/operator/simulation/page.tsx`) | Dropdown còn A_fcfs / A_edf / B / C / D; chọn thì `POST /simulation/runs` trả 404 `not_found` ("đã bỏ ở Phase 3") | LP backend A–D đã xoá; enum `StrategyName` + OpenAPI cố ý chưa đổi để không đụng hợp đồng API trong Phase 3 | Phase 4: bỏ giá trị A–D khỏi `StrategyName`, `export_openapi.py`, `npm run gen:api`, dropdown |
| `GET /simulation/benchmark` | Trả `eval/results/benchmark.json` cũ (có dòng A–D, số trước refactor) | Phase 3 không được ghi `eval/results/` | Phase 4: sinh lại sau nghiệm thu cuối (cần chủ dự án duyệt) |
| `STATION_ENGINE=live` | App không khởi động (pydantic từ chối giá trị) | LiveStation đã xoá; `render*.yaml`, `.env.example` đều là `hybrid` | Không cần sửa; ghi để người deploy biết |
| `eval/build_simulator_evidence.py`, `eval/run_manual_agent_evidence.py` | Chuỗi mô tả còn nhắc LiveStation / A–D | Script sinh evidence lịch sử, không chạy trong CI | Phase 4 (dọn tài liệu lỗi thời) |
| `make web-check` | Chưa chạy trong Phase 3 | OpenAPI không đổi (`export_openapi.py --check` OK) nên type frontend không đổi | Phase 4 nghiệm thu E2E |

## Phase 4 — nhánh `feature/unified-core-p4-api` (quyết định 1, 5, 8, 9)

**Test tự động:** không có test fail. `pytest tests` 493 passed + 8 skipped; `pytest src/simulator/tests` 163 passed;
frontend lint / typecheck / test (28) / build pass (log ở `docs/refactor/raw/phase4-p4-api/`).

Trạng thái các mục Phase 3 ở trên:

| Consumer (Phase 3) | Trạng thái | Commit / bằng chứng |
|---|---|---|
| Frontend S8 còn A–D | **Đã sửa**: `StrategyName` chỉ B0 / M2b / M3a / M3b; OpenAPI + `gen:api`; dropdown S8 4 policy, mặc định M3a; A–D → 422 | `79236e7`; `test_strategy_enum_is_exactly_the_registry_policies`, `test_simulation_run_rejects_removed_lp_strategies` |
| `GET /simulation/benchmark` trả bảng cũ | **Đã sửa**: đọc baseline có version `eval/evidence/2026-11-23-refactor-phase3-baseline/`, trả `source` (baseline, version, commit, seed, `TimeConfig`, thư viện). Bảng A–D chuyển sang `eval/results/archive/` (deprecated) | `eaf8842`; `test_benchmark_returns_versioned_baseline_without_removed_strategies`, `tests/test_eval_baseline.py` |
| `STATION_ENGINE=live` | **Đã rà**: không file vận hành nào còn `live`; `render*.yaml` / `.env.example` = `hybrid`, chú thích cập nhật; `LIVE_STRATEGY` chỉ nhận B0–M3b | `952313f` |
| `eval/build_simulator_evidence.py`, `eval/run_manual_agent_evidence.py` | **Đã sửa**: script thứ nhất gắn nhãn archive (đọc bảng A–D từ archive, từ chối ghi đè evidence); script thứ hai mô tả `HybridStation` | `eaf8842` |
| `make web-check` chưa chạy | **Đã chạy** trên nhánh này: lint / typecheck / test / build pass | `raw/phase4-p4-api/web_*.txt` |

**Còn lại / cần xử lý khi gộp (không phải test hỏng):**

| Mục | Vì sao còn | Ai / khi nào |
|---|---|---|
| `oracle_bookings` (chỉ chiến lược D dùng) còn trong `services/runtime.py::build_sim_runtime`, `StationRuntime`, `control_loop` (`PlanningContext`) | File thuộc phạm vi nhánh core (brief: "Không đụng"); giá trị luôn rỗng sau khi bỏ D, không ảnh hưởng hành vi | Nhánh core hoặc lúc gộp |
| `runtime.make_scheduler` còn nhánh `DomainError` "A–D đã bỏ ở Phase 3" | Không còn với tới được qua enum (chỉ khi truyền chuỗi); file của nhánh core | Nhánh core hoặc lúc gộp |
| Chú thích `tests/test_architecture.py` ("benchmark A–D cùng interface"), `services/hybrid_planner.py` (nhắc `optimizer/horizon.py`) | File của nhánh core (brief giao core cập nhật `test_architecture.py`) | Nhánh core |
| Alembic `0002_drop_lp_strategy_plans` (`down_revision = "0001"`) | Nếu nhánh core cũng thêm revision từ `0001` (tóm tắt DecisionTrace trong DB) thì khi gộp có **hai head** → đổi `down_revision` của một bên / `alembic merge` | Lúc gộp |
| `frontend/openapi.json`, `schema.d.ts` | Cả hai nhánh sinh lại | Sinh lại một lần sau gộp (brief) |
| Tài liệu nhắc đường dẫn kernel `src/simulator/src/engine/hybrid.py` (PROJECT_CONTEXT, ARCHITECTURE) | Nhánh core chuyển kernel sang `src/simulator/core/` | Sửa đường dẫn sau gộp |
| `docs/PRD.md`, `docs/business-overview.md`, phần thân `docs/plan/21-ui-spec.md` / `30-ai.md` còn mô tả A–D | Tài liệu yêu cầu / plan lịch sử; đã có banner hiện trạng ở `docs/plan/*`. PRD là mục tiêu nghiệp vụ — chủ dự án quyết định có sửa PRD §8 hay không | Chủ dự án |

## Sau vòng tích hợp cuối (nhánh `feature/unified-core-p4-final`, 2026-11-24)

Test tự động: **không có test fail** (`pytest` 516 passed / 8 skipped, simulator 163, frontend 28;
`docs/refactor/raw/phase4-final/`).

| Mục còn lại ở trên | Trạng thái |
|---|---|
| `oracle_bookings` | **Đã xoá** khỏi `PlanningContext`, `StationRuntime`, `build_sim_runtime`, `_memory_runtime`, `control_loop` (merge `157f403`) |
| `make_scheduler` nhánh "A–D đã bỏ" | **Đã sửa**: lỗi chung "không có trong registry policy" (giữ chốt chặn) |
| Chú thích A–D / `optimizer/horizon.py` | **Đã sửa** (`tests/test_architecture.py`, `services/hybrid_planner.py`) |
| Alembic hai head | **Đã nối**: `0001 → 0002 (decision_traces) → 0003 (drop_lp_strategy_plans)`, một head; `tests/test_db` pass |
| `openapi.json` / `schema.d.ts` | Sinh lại sau gộp: `export_openapi.py --check` khớp, `gen:api` không đổi nội dung |
| Đường dẫn kernel trong tài liệu vận hành | **Đã sửa**: `PROJECT_CONTEXT.md`, `CLAUDE.md` dùng `src/simulator/core/` |
| `/simulation/benchmark` | Trả **baseline chính thức** `eval/evidence/2026-11-24-unified-core-final-baseline/` |
| PRD §8 / `docs/business-overview.md` còn mô tả A–D | **Còn mở: chờ chủ dự án** (mục tiêu nghiệp vụ, không sửa trong refactor) |
