# MODULE_PROVENANCE — Phase 0 (trước refactor)

> Nhánh `feature/unified-core` = `origin/develop` @ `68692ee`. Chỉ đọc, chưa sửa logic.
> Nguồn: `git log --follow`, `git diff`, so AST (bỏ docstring/format). Hash từng file + từng hàm/lớp ở
> `docs/refactor/raw/phase0/code_hash_manifest.txt` (script `astmanifest.py`). Phase 2 dùng manifest này để chứng minh
> "chỉ di chuyển".

## 0. Xác nhận source of truth

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| `origin/develop` sau PR #15 so với `feature/hybrid-backend` (`a88f821`) | `a88f821` là tổ tiên của develop. Develop có thêm **4 commit, chỉ eval evidence**: `39bc5ba` docs(eval) simulator evidence, `207b273` fix(eval) `build_simulator_evidence.py`, 2 merge. `git diff a88f821 origin/develop` gồm 13 file, toàn bộ nằm trong `eval/`. **Không thiếu thay đổi Backend nào.** | `git log a88f821..origin/develop`, `git diff --stat` |
| Code simulator gốc so với commit cuối của chủ simulator (`8c4c14e`, Le Hien Hieu, 2026-11-21, "MVP-3") | **40/40 file `src/simulator/src/**` có AST trùng khớp** (khác biệt duy nhất là format của `b95b840 style: ruff format`). `run.py`, `benchmark.py`, `benchmark_mvp3.py` cũng trùng AST. | `astcmp.py 8c4c14e origin/develop src/simulator` |
| Test simulator so với `8c4c14e` | 8/11 file trùng AST. 3 file (`test_hybrid`, `test_modular`, `test_vehicle_profiles`) chỉ thêm `read_text(encoding="utf-8")` (commit `700c4b8`, sửa lỗi Windows). | `git diff 8c4c14e origin/develop -- src/simulator/tests` |
| Golden / scenario / config simulator | Không đổi kể từ `8c4c14e` (`tests/golden/*`, `scenario/*.json`, `config/*.json`) | `git diff --stat` rỗng |
| Tái lập số MVP-1/2/3 | Chạy lại hôm nay **khớp 100% KPI không phụ thuộc thời gian** với raw evidence `eval/evidence/2026-11-22/raw/sim-hardware/*` (MVP-3: 0 khác biệt, MVP-2: 0, mvp1/vinfast: chỉ khác `run_id`/`command`/đường dẫn tuyệt đối) | `BASELINE.md` §3 |
| Nhánh nào có commit simulator chưa vào develop? | Chỉ có `feature/chargepilot-fullstack-ai` và `experiment/claude-chargepilot-fullstack-ai` (2 commit của LufkyMama, 2026-11-19: `8cfa279`, `c91476e` "R&D MVP-2/3"). Đây là **nhánh thử nghiệm cũ, độc lập**, có `lp_mpc.py`/`workloads.py` riêng và xoá `ac_lp.py`/`rolling_lp.py`/`test_mvp2/3`. Hai nhánh này **không phải** code của chủ simulator, đã bị MVP-2/3 của Le Hien Hieu thay thế. **Không merge, không dùng.** | `git log origin/develop..<branch> -- src/simulator` |
| Mirror `hieulhaiwork/Temp-ChargePilot-Simulator` @ `7e1eb613511da7b0323b8544250fc371cbdb9640` (Le Hien Hieu, "Update 12h50 23/11") | Lần đầu `gh api` trả 404. Sau đó mirror đã public và được clone (chỉ đọc, ngoài repo). So `git ls-tree -r` từng file: **568/568 file của mirror có cùng blob hash với `68692ee`**. Không file nào khác nội dung, không file nào chỉ có ở mirror. `68692ee` chỉ có thêm 12 file cấu hình tool/CI (`.agents/*`, `.ai-log/.gitkeep`, `.claude/settings.json`, `.codex/`, `.cursor/`, `.gemini/`, `.github/{CODEOWNERS,PULL_REQUEST_TEMPLATE.md,hooks/hooks.json,workflows/ci.yml}`). Mirror chỉ có 2 commit dạng snapshot (`3ee006c` 11-22, `7e1eb61` 11-23). | `git ls-tree -r 7e1eb61` ⋈ `git ls-tree -r 68692ee` |

**Kết luận:** implementation Simulator MVP-1/2/3 trong develop **đầy đủ, trùng từng byte** với mirror `7e1eb61` do
người phụ trách chỉ định (2026-11-23), và trùng AST với commit cuối của chủ simulator trong repo chính thức
(`8c4c14e`). Không phát hiện hai phiên bản khác nhau.

## 1. Bảng provenance theo module

Ký hiệu loại:
- **G** = gốc (thuật toán/vật lý đã kiểm chứng MVP-1/2/3)
- **A** = adapter/wrapper (map kiểu, không chép logic)
- **D** = bản ghép/chép một phần logic của G (nguồn drift)
- **I** = implementation độc lập (logic riêng, cùng bài toán)
- **B** = nghiệp vụ backend (giữ nguyên)
- **O** = lỗi thời/dự phòng
- **T** = mẫu template chưa nối vào graph

### 1.1 Simulator core — chủ: Le Hien Hieu (G)

| File | Blob | Tạo | Sửa cuối | Loại | Đích (guide §2) |
|---|---|---|---|---|---|
| `src/simulator/src/engine/hybrid.py` | `af002ad` | `326a34d` 11-19 | `b95b840` (format) | G | `src/simulator/engine/` + trích core |
| `src/simulator/src/engine/queue.py` | `e013a2d` | `326a34d` | `781c3f0` 11-21 | G | `src/simulator/engine/` |
| `src/simulator/src/engine/ev2gym_adapter.py` | `2fdca8c` | `94cbbc9` | `326a34d` | G | `src/simulator/engine/` |
| `src/simulator/src/charging_models/{base,synthetic_dc}.py` | `16b29c5`/`7ba2036` | `326a34d` | `326a34d` | G | `src/simulator/charging_models/` (+ Protocol → models) |
| `src/simulator/src/charging_models/{dc_charging_models,vehicle_profiles}.py` | `76283a5`/`0575979` | `d15871a` | `d15871a` | G | `src/simulator/charging_models/` |
| `src/simulator/src/dispatch/{base,arrival_order,edf}.py` | | `326a34d` | `781c3f0` | G | `src/optimizer/dispatch/` |
| `src/simulator/src/dispatch/least_laxity.py` | `7399a83` | `781c3f0` | `781c3f0` | G | `src/optimizer/dispatch/` |
| `src/simulator/src/optimizers/{base,equal_share,deadline_first}.py` | | `326a34d` | `781c3f0` | G | `src/optimizer/zones/` |
| `src/simulator/src/optimizers/rolling_lp.py` (DC LP) | `be83d69` | `781c3f0` | `b95b840` (format) | G | `src/optimizer/zones/` |
| `src/simulator/src/optimizers/ac_lp.py` (AC 2-stage LP) | `857785e` | `8c4c14e` | `b95b840` (format) | G | `src/optimizer/zones/` |
| `src/simulator/src/coordination/{base,fixed_budget}.py` | | `326a34d` | `8c4c14e`/`b95b840` | G | `src/optimizer/coordination/` |
| `src/simulator/src/coordination/dynamic_slack.py` | `1e05266` | `8c4c14e` | `b95b840` | G | `src/optimizer/coordination/` |
| `src/simulator/src/safety/{constraints,guard}.py` | `a8ed320`/`9afdd9a` | `326a34d` | `8c4c14e` | G | `src/guard/physical/` (+ DTO → models) |
| `src/simulator/src/safety/limits.py` | `53eb75a` | `8c4c14e` | `b95b840` | G | `src/guard/physical/` hoặc models (xem IMPORT_GRAPH §3) |
| `src/simulator/src/observations.py` | `a3d5124` | `326a34d` | `b95b840` | G (DTO) | `src/models/scheduling.py` |
| `src/simulator/src/scenario.py` | `8ff7374` | `94cbbc9` | `b95b840` | G (DTO + parser) | `src/models/simulation_core.py` + `src/simulator/scenario.py` |
| `src/simulator/src/algorithms.py` | `6bca88f` | `326a34d` | `b95b840` | G (registry thành phần) | `src/optimizer/registry.py` + factory DC model |
| `src/simulator/src/evaluation/{metrics,extended,trace}.py` | | `326a34d`/`781c3f0` | `b95b840` | G | `src/simulator/evaluation/` |
| `src/simulator/{run,benchmark,benchmark_mvp3}.py` | | `94cbbc9`/`781c3f0`/`8c4c14e` | `b95b840` | G (CLI) | giữ tại `src/simulator/` |
| `src/simulator/{tests,scenario,config,docs}/` | | | `700c4b8` | G (golden/fixture) | giữ, chỉ sửa import |

### 1.2 Lớp tích hợp backend ↔ simulator — chủ: LufkyMama

| File | Blob | Tạo | Sửa cuối | Loại | Ghi chú |
|---|---|---|---|---|---|
| `src/simulator/hybrid_station.py` | `708da7b` | `098877a` 11-23 | `0a97a9f` | **A + D** | A: map `VehicleVisit`/`Incident`/`Command`/`datetime` ↔ Scenario. **D: `_charge_one_minute()`** là bản chép bước vật lý của `HybridSimulator.step` (tích phân năng lượng, `validate_response`, hoàn thành SOC, post-guard). Cũng chép `_observed_vehicles`, `_candidates`, `dispatch_observation`. |
| `src/services/hybrid_planner.py` | `b5e3472` | `098877a` 11-23 | `0a97a9f` | **D + B** | **D: `_decide()`** ghép lại dispatch → coordinator → optimizer → guard của `HybridSimulator.step`/`_power_plan` (thiếu `_online_observation`). **D: `POLICIES`** là bản chép `benchmark_mvp3.POLICIES`. B: consent `_start_minimums`/`_fit_with_minimums`, `_to_plan`, `_queue_etas`, `_sim_tariff`. |
| `src/guard/physical.py` | `f754dd0` | `1e8f43f` 11-23 | `1e8f43f` | **A** | Map `StationConfig`/`StationState`/`Command` → gọi `safety.guard.guard` + `validate_dispatch`. Không chép logic kiểm. Có hàm riêng `effective_limits(config, state)` dựng `EffectiveLimits` từ config backend. |
| `src/simulator/base.py` | `9cf0fff` | `3228cfa` 11-17 | `098877a` | B (Protocol) | `StationReader`/`StationActuator`/`VehicleVisit` → Protocol ở `src/models` |
| `src/simulator/live.py` | `99993fa` | `e32f384` 11-22 | `e32f384` | **O / I** | `LiveStation`: mô hình vật lý **độc lập** đơn giản (không taper DC). Dự phòng `STATION_ENGINE=live`. Còn được dùng ở: `runtime.make_station`, `tests/test_simulator/test_simulator_contracts.py`, `tests/test_optimizer/test_strategies.py`, `tests/test_api/test_flows.py`, `eval/build_simulator_evidence.py`, `eval/run_manual_agent_evidence.py`. Evidence lịch sử `eval/evidence/2026-11-22` đo bằng engine này. |
| `src/services/runtime.py` | `706e931` | `3228cfa` | `098877a` | B | `make_station`, `make_scheduler` (chọn A–D hay simulator), `visit_of` (Booking → VehicleVisit, SOC % → fraction) |
| `src/services/control_loop.py` | `52e2158` | `3228cfa` | `e32f384` | B | `on_event` → `scheduler.plan` → `diff_commands` → `dispatcher.submit`; `run_forever` tick mỗi `planning_step_minutes` |

### 1.3 Backend Optimizer A–D — chủ: LufkyMama (I)

| File | Blob | Tạo | Sửa cuối | Loại | Đang dùng ở |
|---|---|---|---|---|---|
| `src/optimizer/base.py` | `323acbb` | `3228cfa` | `92d9509` | B (Protocol `Scheduler`, `PlanningContext`) | control_loop, hybrid_planner, runtime |
| `src/optimizer/assignment.py` | `fa0514b` | `3228cfa` | `5af5b74` | **I** (gán cổng FCFS/EDF) | strategies A–D **và `charging_service._what_if` (quote/booking, mọi chiến lược)** |
| `src/optimizer/lp_model.py` | `e49ba39` | `3228cfa` | `3171cb8` | **I** (LP backend, `solve_with_unmet`) | B/C/D **và `_what_if`** |
| `src/optimizer/horizon.py` | `c3ba7db` | `5af5b74` | `3171cb8` | **I** | lp_model (consent `_start_requirement`) |
| `src/optimizer/mpc.py` | `a3596c8` | `3228cfa` | `5af5b74` | **I** | B/C/D |
| `src/optimizer/baselines.py` | `113f806` | `3228cfa` | `5af5b74` | **I** (A_fcfs, A_edf) | A |

Đây **không phải** bản chép simulator: mô hình khác (bước 15', không có DC taper/acceptance, gán cổng EDF thay vì LLF,
không có coordinator). Theo guide §2 và §3 Phase 4, **không xoá** cho tới khi quote/booking đã chuyển sang planner chung.

### 1.4 Guard nghiệp vụ — chủ: LufkyMama (B)

`src/guard/{rules,checker,approval,dispatcher,emergency}.py` (tạo `3228cfa` 11-17). Giữ nguyên. `rules.py` gọi
`physical.py` cho luật vật lý. `approval.py` import `src.services.errors.DomainError` (guard → services: đây là
cạnh duy nhất đi ngược chiều, test kiến trúc hiện cho phép).

### 1.5 LLM chat — template `phoenix-mentor[bot]` 11-05, phát triển: HaiVuu, LufkyMama

| File | Loại | Ghi chú |
|---|---|---|
| `src/agents/graph.py`, `state.py`, `guardrails.py`, `prompts.py`, `mock_llm.py` | B | Graph ReAct: entry → guardrail_check → reason → act → human_review → assess → finalize(/_with_partial) |
| `src/agents/nodes/{act,assess,finalize,human_review,reason}_node.py` | B | Được nối vào graph |
| `src/agents/nodes/{retrieve,safety,synthesize,validate}_node.py` | **T** | **Không nối vào graph**. Chỉ `tests/test_agents/test_agent_patterns.py` dùng (`safety_node`, `validate_node`). `synthesize_node` gọi `services.llm.get_llm`. |
| `src/agents/personas.py` | T | Chỉ dùng ở `test_agent_patterns.py` |
| `src/agents/tools/charging.py` | B | 6 tool nghiệp vụ, gọi `services.charging_service/catalog/energy/charging_demo` |
| `src/agents/tools/{knowledge,mcp_tool,risky_tools}.py` | **T** | `TEMPLATE_DEMO_TOOL_NAMES` (search_knowledge, calculate, mcp_knowledge_lookup, send_email). Vẫn nằm trong `TOOL_REGISTRY` và được test_graph/test_hitl/test_routes/eval/run_eval.py dùng. `reason_node` có lọc `TEMPLATE_DEMO_TOOL_NAMES`. |
| `src/services/llm.py` | B | Caller: `nodes/{reason,finalize,synthesize}_node.py`, `src/api/routes.py`, `eval/{judge,run_eval}.py`, `tests/test_services/test_llm_cascade.py`, `tests/test_architecture.py` |
| `src/models/schemas.py` | B | `ChatRequest`/`ChatResponse` (API, có trong OpenAPI); `AgentDecision`/`FinalAnswer`/`AgentAnswer` (nội bộ agent) |

## 2. Phân loại phần trùng lặp

| Nhóm | Bản gốc | Bản trùng / song song | Loại | Hướng xử lý (đề xuất, chưa làm) |
|---|---|---|---|---|
| Bước vật lý (tích phân kW→kWh, SOC, hoàn thành, post-guard) | `HybridSimulator.step` (hybrid.py:269-304) | `HybridStation._charge_one_minute` (hybrid_station.py:511-548) | D | Phase 3: trích `apply/advance` dùng chung, xoá bản trong HybridStation sau khi có test parity |
| Quan sát (`_observed_vehicles`, candidates, dispatch observation) | hybrid.py:110-144, 209-235 | hybrid_station.py:386-440 | D | Phase 3: core `observe()` |
| Ghép quyết định (dispatch → coordinator → optimizer → guard) | `HybridSimulator.step`/`_power_plan` (hybrid.py:161-256) | `SimulatorScheduler._decide` (hybrid_planner.py:90-162) | D | Phase 3: core `propose()`; `_decide` thành facade |
| Bảng policy B0/M2b/M3a/M3b | `benchmark_mvp3.POLICIES` | `hybrid_planner.POLICIES` (chép), `benchmark.POLICIES` (MVP-2: B0/M2a/M2b/M2c, chỉ có 2 cột, **không cùng nghĩa**), `config/algorithms_mvp{2,3}.json` | D | Phase 2: một registry policy có version |
| Registry thành phần | `algorithms.py` (DISPATCH/OPTIMIZERS/COORDINATORS/DC_MODELS + `resolve_algorithms`) | — (backend gọi lại đúng hàm này) | G | Chuyển nguyên, không tạo registry thứ hai |
| Mô hình vật lý trạm | HybridSimulator + EV2GymAdapter | `LiveStation` (live.py) | I/O | Phase 4/6: xoá khi hết caller (6 nơi ở trên); giữ evidence |
| Kiểm vật lý | `safety/guard.py` | `guard/physical.py` | A | Không phải bản trùng. Thành `guard/physical/adapter.py` |
| Lập lịch/feasibility | M3a (simulator) cho lịch thật | `optimizer/{assignment,lp_model,horizon,mpc,baselines}` cho A–D **và cho quote** | I | Phase 4: AdmissionService dùng planner chung; A–D chuyển sang `optimizer/baselines/` nếu còn dùng cho benchmark |
| Nút/tool agent template | — | `nodes/{retrieve,safety,synthesize,validate}`, `personas`, 4 tool demo | T | Phase 5: phân loại; không xoá khi chưa chuyển test sang tool sạc |

## 3. Không được xoá / sửa (theo guide §7 và kết quả kiểm)

- Toàn bộ G ở §1.1, golden `src/simulator/tests/golden/*`, `src/simulator/docs/MVP{2,3}_BENCHMARK.md`.
- `eval/evidence/**` (2026-11-22 đo bằng LiveStation + simulator offline; 2026-11-23 đo bằng HybridStation).
- `src/forecast/` (F6 hoãn, có test contract skip).
- `eval/results/benchmark.{json,md}`: file được track, API `/simulation/benchmark` đọc. Bản hiện tại sinh ở `098877a`
  (**trước** hai bản sửa `0a97a9f` và `a88f821`). Chạy `make benchmark` sẽ ghi đè file này. Phase 0 đã chạy rồi khôi
  phục lại (xem BASELINE §4).
