# DELETION_MANIFEST — code / test bị xoá trong refactor Unified Core

> Mỗi dòng: đường dẫn cũ, lý do, thay thế, test chứng minh, SHA. "SHA" = blob của file ở commit cuối còn file
> (`git show <commit>:<path>` để xem lại). Phase 3 bắt đầu từ `749c042`.

## Phase 3 (ADR-019, `docs/refactor/PHASE3_DESIGN.md`)

### Định nghĩa trong file còn giữ

| Đã xoá | Lý do | Thay thế | Test | Commit cuối còn / commit xoá |
|---|---|---|---|---|
| `src/simulator/hybrid_station.py::HybridStation._charge_one_minute` (+ `_candidates`, `_observed_vehicles`, `_violation`) | Bản chép thứ hai của vòng tích phân `HybridSimulator.step` (PHASE0 §1) | `StationKernel.advance` (Physical Core, `engine/hybrid.py`), `HybridStation.step` gọi với `physics_step=1` | `tests/test_simulator/test_hybrid_station.py` (gồm replay mvp1 khớp 1e-6); benchmark backend 225/225 trùng Phase 2 ở commit `f947b22` | `749c042` / `f947b22` |
| `src/services/hybrid_planner.py::SimulatorScheduler._decide` | Bản chép dispatch → coordinator → optimizer → guard, thiếu `_online_observation`, quan sát sau-dispatch dựng tay (PHASE0 §2 #7, #8) | `StationKernel.propose` + consent + `StationKernel.approve` (`SimulatorScheduler.decide`) | `tests/test_services/test_hybrid_planner.py`, `tests/test_refactor/test_differential.py` | `f947b22` / `ddfeb41` |
| `src/services/charging_service.py::_what_if` (bản LP: `assign_connectors(ctx, "edf")` + `lp_model.solve_with_unmet`) | Quote / booking tính bằng mô hình khác mô hình thực thi (PHASE0 §3) | `services/admission.py::evaluate` (fork trạm + cùng policy, control_loop, Guard) | `tests/test_services/test_admission.py`, `tests/test_api/test_flows.py` | `0658fc2` / `d00ad0c` |
| `src/services/simulation_service.py::_run_sync` | Trùng helper | `services/admission.py::run_sync` | `tests/test_optimizer/test_strategies.py` | `0658fc2` / `d00ad0c` |
| `src/optimizer/__init__.py::_COMPAT`, `__getattr__` | Tương thích tạm cho `get_scheduler` / `PlanningContext` / `Scheduler` (Phase 2) — đích đã xoá / chuyển | `src.models.planning` (`PlanningContext`, `Scheduler`); `services.runtime.make_scheduler` | `tests/test_architecture.py` | `0658fc2` / `d00ad0c` |
| `src/services/station_service.py::_at_risk_bookings` nhánh LP ("lịch giao thiếu") | Chỉ có nghĩa với lịch nhiều bước của LP backend | Nhánh laxity (một định nghĩa cho mọi policy còn lại) | `test_at_risk_simulator_strategy_flags_only_tight_sessions` | `0658fc2` / `d00ad0c` |

### File

| File đã xoá | Dòng | Lý do | Thay thế | Blob SHA (commit `0658fc2`) |
|---|---|---|---|---|
| `src/optimizer/assignment.py` | 113 | Gán cổng EDF của LP backend; chỉ quote / A–D dùng | Dispatch của policy (`optimizer/dispatch`, qua `kernel.propose`) | `77df757ab8` |
| `src/optimizer/lp_model.py` | 153 | LP một bước MPC (không DC taper, không coordinator) | Zone optimizers (`optimizer/zones`) qua Planning Core | `cab77bffb5` |
| `src/optimizer/horizon.py` | 163 | Lưới thời gian / ràng buộc của LP backend | `StationKernel.boundary` + `TimeConfig` | `c0f8604494` |
| `src/optimizer/mpc.py` | 31 | Chiến lược B / C | — (đề xuất bỏ, PHASE3_REPORT §5) | `564b7e97c0` |
| `src/optimizer/baselines.py` | 133 | Chiến lược A_fcfs / A_edf / D | B0 (FCFS + equal share) là baseline có version trong registry | `8de2006fe4` |
| `src/optimizer/strategies.py` | 36 | `get_scheduler` A–D | `services/runtime.make_scheduler` (B0 / M2b / M3a / M3b; A–D → `DomainError`) | `9ddf5e13ab` |
| `src/optimizer/base.py` | — | **Không xoá: `git mv`** sang `src/models/planning.py` (PlanningContext, Scheduler) | `src/models/planning.py` | `323acbb34f` (ở `749c042`) |
| `src/simulator/live.py` (`LiveStation`) | 312 | Trạm dự phòng không DC taper; hết caller khi STATION_ENGINE chỉ còn `hybrid` | `HybridStation` | `e7e732e82e` |

### Test

| Test đã xoá | Lý do | Thay thế |
|---|---|---|
| `tests/test_optimizer/test_optimizer_contracts.py` — 22 test LP (T2.1–T2.4: `test_total_power_never_exceeds_limit` … `test_oracle_uses_future_bookings_only_in_strategy_d`) | Kiểm hợp đồng của `lp_model` / `assignment` / A–D đã xoá | Giữ 3 test PlanningContext / config. Hành vi tương ứng trên Planning Core: Physical Guard trước + sau (`src/simulator/tests`, differential), cổng lỗi không được gán (`test_connector_fault_sends_vehicle_to_queue_head`, differential), consent không cho lùi giờ (`test_m3a_starts_charging_when_resident_did_not_allow_delay`), tất định (`test_same_state_gives_the_same_proposal`) |
| `tests/test_optimizer/test_strategies.py::test_every_benchmark_strategy_is_registered[A–D]`, `test_forecast_never_relaxes_declared_deadline` | A–D / C đã bỏ | `test_every_runtime_strategy_is_a_planning_core_policy`, `test_removed_lp_strategies_fail_loudly`; AC3/AC5/MT4/MT5 chạy lại trên B0 + M3a |
| `tests/test_services/test_hybrid_planner.py::test_at_risk_backend_lp_keeps_planned_shortfall_definition` | Định nghĩa "nguy cơ" của LP đã bỏ | `test_at_risk_simulator_strategy_flags_only_tight_sessions` |

**Test được sửa (không xoá):** `test_simulator_contracts.py` (T1.4) chạy trên `HybridStation` thay `LiveStation`; hai test
chờ tới khi xe đầy thay vì giả định công suất hằng (`test_vehicle_power_is_capped_and_finishes`,
`test_dc_vehicle_unplugs_after_delay_when_full`), vì HybridStation có mô hình pin EV2Gym / DC taper.
`test_control_and_charging.py::test_only_first_step_becomes_commands` bỏ điều kiện "lịch > 1 bước" (đặc thù LP).
`_sim_runtime` của file này dùng M3a thay B.

## Phase 4 mục 1 — chat cư dân sang `src/llm_chat/` (nhánh `feature/unified-core-llmchat`)

| Đã xoá | Lý do | Thay thế / bằng chứng |
|---|---|---|
| `src/agents/nodes/retrieve_node.py` (`retrieve_node`, `_retrieve_chunks`, `_MOCK_KB`) | Template AI20K (RAG mock với 3 chunk demo về AI20K, không liên quan sạc EV). Không nối vào `graph.py`; không test, eval, script hay module nào import (đã `rg` trên `src tests eval scripts`). | Không cần thay: chat cư dân lấy dữ liệu qua tool `src/llm_chat/tools/charging.py` → `src/services`. Toàn bộ test giữ nguyên số lượng (475 passed, 8 skipped trước và sau xoá). |
| `src/agents/nodes/synthesize_node.py` (`synthesize_node`, `_get_structured_answer`, `_parse_answer`, `_render_answer`) | Template AI20K (gọi `get_llm()` rồi parse `AgentAnswer`). Không nối vào `graph.py`; không có caller hay test. Node `finalize` của graph đã làm việc này với `FinalAnswer` + guardrail hậu kiểm. | `src/llm_chat/nodes/finalize_node.py`; test `tests/test_llm_chat/test_graph.py`, `test_agent_modes.py`, `test_guardrails.py`. |

Giữ lại (vẫn có test dùng, chưa đủ điều kiện xoá): `nodes/safety_node.py`, `nodes/validate_node.py`, `personas.py`,
`prompts.build_system_prompt`, `schemas.AgentAnswer` (`tests/test_llm_chat/test_agent_patterns.py`);
`tools/{knowledge,mcp_tool,risky_tools}.py` (nằm trong `TOOL_REGISTRY`, ẩn khỏi prompt qua
`TEMPLATE_DEMO_TOOL_NAMES`; `send_email` là tool risky mà `test_hitl.py`, `test_routes.py`, `eval/run_eval.py` dùng để
kiểm HITL). Muốn xoá các file này phải chuyển những test đó sang tool sạc trước.

## Phase 4 — nhánh `feature/unified-core-p4-core` (quyết định 7: kernel vào `src/simulator/core/`, xoá shim)

Commit cuối còn mọi file dưới đây: `70d0eaf` (`git show 70d0eaf:<path>`).

### Shim đã xoá (không có logic; đích đã có từ Phase 1–3)

| Đã xoá | Loại | Đích (import thẳng) |
|---|---|---|
| `src/simulator/src/scenario.py` | re-export Phase 1 | `src.models.simulation_core` |
| `src/simulator/src/observations.py` | re-export Phase 1 | `src.models.scheduling.observations` |
| `src/simulator/src/charging_models/base.py` | re-export Phase 1 | `src.models.charging_physics` |
| `src/simulator/src/safety/{constraints,limits}.py` | re-export Phase 1 | `src.models.physical_{constraints,limits}` |
| `src/simulator/src/{dispatch,coordination,optimizers}/base.py` | re-export Phase 1 | `src.models.scheduling.{dispatch,coordination,optimization}` |
| `src/simulator/src/dispatch/{arrival_order,edf,least_laxity}.py` | alias `sys.modules` Phase 2 | `src.optimizer.dispatch.*` |
| `src/simulator/src/optimizers/{ac_lp,deadline_first,equal_share,rolling_lp}.py` | alias `sys.modules` Phase 2 | `src.optimizer.zones.*` |
| `src/simulator/src/coordination/{dynamic_slack,fixed_budget}.py` | alias `sys.modules` Phase 2 | `src.optimizer.coordination.*` |
| `src/simulator/src/safety/guard.py` | alias `sys.modules` Phase 2 | `src.guard.physical.validator` |
| `src/simulator/base.py` | alias `sys.modules` Phase 2 | `src.models.station_protocols` |
| `src/simulator/src/{,engine,dispatch,coordination,optimizers,safety}/__init__.py` | gói rỗng | — |
| `src/guard/physical/__init__.py::_ADAPTER_NAMES`, `__getattr__` | tương thích Phase 2 | `src.guard.physical.adapter` (consumer trong repo đã import thẳng) |
| `tests/test_architecture.py::test_core_contract_shims_reexport_the_same_objects`, `test_contracts_are_imported_from_models_outside_the_simulator`, `test_physical_guard_package_keeps_the_old_public_api_without_loading_the_backend` | test của shim | `test_compatibility_shims_are_gone`, `test_nobody_imports_removed_compatibility_paths`, `test_physical_guard_package_exports_only_the_validator_without_loading_the_backend` (chặt hơn) |

### Di chuyển (`git mv`, chỉ đổi import; cổng AST `raw/phase4-p4core/ast_gate_step7.txt`)

| Cũ | Mới |
|---|---|
| `src/simulator/src/engine/hybrid.py` (`StationKernel`) | `src/simulator/core/kernel.py` |
| `src/simulator/src/engine/hybrid.py` (`HybridSimulator`, `ZERO_POWER`) | `src/simulator/hybrid.py` |
| `src/simulator/src/engine/{queue,ev2gym_adapter}.py` | `src/simulator/core/{queue,ev2gym_adapter}.py` |
| `src/simulator/src/algorithms.py` | `src/simulator/core/algorithms.py` |
| `src/simulator/src/charging_models/{__init__,dc_charging_models,synthetic_dc,vehicle_profiles}.py` | `src/simulator/core/charging_models/…` |
| `src/simulator/src/evaluation/{__init__,extended,metrics,trace}.py` | `src/simulator/evaluation/…` |

Test của chủ simulator (`src/simulator/tests/*.py`), `tests/test_refactor/test_differential.py`,
`tests/test_simulator/test_hybrid_station.py`: chỉ đổi dòng import; `test_mvp3.py` monkeypatch `hybrid.guard` giờ trỏ
`src.simulator.core.kernel` (import `kernel as hybrid`), không đổi assert.
