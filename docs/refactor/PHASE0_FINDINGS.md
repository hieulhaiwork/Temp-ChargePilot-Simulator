# PHASE0_FINDINGS — khác biệt engine, phân tích interval, luồng LLM chat, đề xuất migration

> Nhánh `feature/unified-core` @ `68692ee`. Chỉ phân tích, **chưa sửa logic**. Số dòng tham chiếu theo commit này.
> Đi kèm: `BASELINE.md`, `MODULE_PROVENANCE.md`, `IMPORT_GRAPH.md`.

## 1. Ba đường thực thi đang tồn tại

| | Offline `HybridSimulator` | Backend `SimulatorScheduler` + `HybridStation` (B0/M2b/M3a/M3b) | Backend Optimizer A–D + quote |
|---|---|---|---|
| Ai quyết định | `step()` tự ghép dispatch → coordinator → optimizer → guard (hybrid.py:194-256) | `_decide()` chép lại các bước trên (hybrid_planner.py:90-162) | `optimizer/{assignment,lp_model,mpc,baselines}` |
| Ai thực thi vật lý | `step()` gọi `adapter.step(…, minutes)` (hybrid.py:272-304) | `HybridStation._charge_one_minute()` lặp 1 phút (hybrid_station.py:511-548) | Cùng `HybridStation` (hoặc `LiveStation` nếu `STATION_ENGINE=live`) |
| Thuật toán | registry `algorithms.py` | gọi lại đúng `resolve_algorithms` | LP backend riêng (không có DC taper, không coordinator) |
| Dùng cho | MVP-1/2/3 benchmark, replay, golden | lịch chạy thật (mặc định `LIVE_STRATEGY=M3a`) | chiến lược A–D **và `_what_if` cho quote/booking ở mọi chiến lược** |

## 2. Khác biệt cụ thể: `HybridSimulator` ↔ `HybridStation` / `SimulatorScheduler`

Đánh số để Phase 3 viết test differential cho từng điểm.

**Thời gian và vật lý**

1. **Độ phân giải vật lý.** Offline tích phân một lần cho cả interval `[now, end)` với công suất giữ nguyên
   (`adapter.step(vid, cab, setpoint, minutes)`). DC dùng `min(setpoint, acceptance(SOC đầu interval))` cho **cả**
   interval (`synthetic_dc.stored_kwh`). Backend tích phân **từng phút**, tính lại taper mỗi phút. Với `timestep=1`
   (mvp1, MVP-2) hai cách cho kết quả giống nhau. Với `timestep=5` (MVP-3 workloads) chúng **khác nhau**: offline giữ
   acceptance đầu interval trong 5'.
2. **Thời điểm hoàn thành.** Offline: `completed_at = end` của interval (hybrid.py:297). Backend: `minute + 1`
   (hybrid_station.py:542). Mốc rút DC (`completed_at + delay`) vì vậy lệch tối đa 1 interval.
3. **Interval quyết định.** Offline: `end = min(now + timestep, xe đến/rời, mốc rút DC, đổi giá TOU, mốc công bố/hiệu
   lực LimitEvent)` (`queue.next_boundary` + `environment_boundary`). Backend: optimizer nhận `interval=15`
   (`planning_step_minutes`). Lịch tính lại khi có TICK 15' hoặc sự kiện. Interval này quyết định `Candidate.allowed_kw`
   (`acceptance_kw(v, 15)`), block đầu của Rolling LP (`first_end = now + interval_minutes`, rolling_lp.py:71) và
   `need_kw` của consent.
4. **Không tính lại lịch khi xe sạc xong.** `HybridStation._emit` bỏ `CHARGE_COMPLETED`/`PLUGGED_IN`
   (hybrid_station.py:564-565), nên công suất xe AC vừa đầy để lại chỉ được chia lại ở TICK kế tiếp (tối đa 15'). Offline
   chia lại ngay ở interval sau (≤ `timestep`).
5. **Mốc TOU.** Offline tách interval đúng mốc đổi giá. TICK backend tính từ lúc khởi động, không căn theo mốc giá.
6. **Cắt nguồn.** Offline: `LimitEvent` có `announced_minute`/`effective_minute`, optimizer online chỉ thấy sự kiện
   đã công bố. Backend: `Incident POWER_LIMIT_CHANGE` có hiệu lực ngay, đi qua `guard/emergency.curtail_to_limit`, rồi
   ghi đè `EffectiveLimits.grid_input_kw` bằng `available_power_kw` (hybrid_station.py:189). Scenario của trạm không có
   `limit_events`.

**Quyết định**

7. **Thiếu `_online_observation`.** Offline cắt interval của optimizer theo mốc đã biết khi có tariff/coordinated
   limits/optimizer online, và tách `planning`/`observation` theo cờ `uses_online_interval` (hybrid.py:146-159,
   236-246, 168). `_decide` dùng một `observation` với interval cố định cho mọi optimizer, và đặt tariff lên mọi lần
   chạy (`_sim_tariff`) nhưng không đi kèm việc cắt interval.
8. **Quan sát sau dispatch được dựng giả.** Offline gọi `queue.connect` thật rồi dựng quan sát. `_decide` tự dựng
   `VehicleObservation(... "CHARGING", port, base.minute ...)` cho xe vừa gán (hybrid_planner.py:108-123), còn lệnh
   ASSIGN chỉ được áp sau đó qua dispatcher.
9. **Consent sửa đề xuất SAU optimizer, TRƯỚC guard vật lý.** `_start_minimums` + `_fit_with_minimums`
   (hybrid_planner.py:152-155, 165-235) nâng công suất xe bắt buộc rồi co theo tủ → vùng → lưới. Đây là logic nghiệp vụ
   nằm giữa planning core và physical guard. Guide §3 Phase 3.4 yêu cầu tách rõ.
10. **Fail-safe khác nhau.** Offline: `ConstraintViolationError` thì đếm `rejected_allocation_count` và **dừng run**.
    Backend: `plan()` bắt lỗi rồi trả lịch 0 kW, giữ gán cổng (hybrid_planner.py:82-85). Không có bộ đếm reject.
11. **Post-check sau khi áp.** Offline: `guard(cfg, candidates, actual, budgets.output_kw)` với **ngân sách
    coordinator**, sai thì raise. Backend: `guard(cfg, candidates, actual, limits.zone_output_kw)` với **trần vùng vật
    lý** (hybrid_station.py:546), sai thì chỉ đếm + log và tiếp tục. Backend kiểm lỏng hơn (ADR-017 cố ý: ngân sách chỉ
    là phân bổ của optimizer).
12. **Setpoint thực thi.** Offline: `requested[vid]`. Backend: `min(_setpoint, allowed(1'))` và `_setpoint` giữ tới
    lệnh sau. `apply_commands` kẹp `[0, port_kw]`, `power_kw=None` thì lấy `port_kw`. Lệnh bị HITL giữ lại thì setpoint
    cũ vẫn chạy.
13. **Không ghi DecisionTrace/latency** ở backend (`record_decisions`). `last_diagnostics` chỉ giữ lần gần nhất.

**Mô hình và dữ liệu**

14. **DC model.** Backend luôn dùng `SyntheticTaperV1` (`with_vinfast_profiles` raise `NotImplementedError`).
    `resolve_algorithms` vẫn dựng `dc_charging_model` theo selection, nhưng quan sát lấy `station.adapter.dc_model`.
    Hai thứ trùng nhau chỉ vì đều mặc định là synthetic.
15. **Dựng `Vehicle` từ booking.** `runtime.visit_of`: SOC % → fraction. `HybridStation._vehicle`: thiếu pin thì
    `battery = required_kwh × η`, SOC 0→1. Giờ đến/rời làm tròn LÊN phút.
16. **Đơn vị năng lượng.** `SessionProgress.delivered_grid_kwh` (backend) = năng lượng **đầu ra cổng**, khác
    `Session.delivered_grid_kwh` (simulator) = phía lưới (÷ conversion). `outcomes()` coi đạt SOC target là giao đủ
    `required_kwh`.
17. **Cổng lỗi.** Chỉ backend có (`_faults`, xe về đầu hàng). Offline không có sự cố cổng.
18. **Policy selection.** Backend chỉ truyền `dispatch: {"DC": …}`, AC dùng mặc định của registry. Bảng `POLICIES`
    chép từ `benchmark_mvp3.py`.

**Phạm vi test parity hiện có:** `tests/test_simulator/test_hybrid_station.py::test_replay_mvp1_matches_hybrid_simulator`
phát lại quyết định của offline (`default_algorithms`, mvp1, `timestep=1`, mọi interval 1') vào `HybridStation` và
so năng lượng/SOC từng xe ở mức 1e-6/1e-9. Test này **chỉ phủ trường hợp interval = physics step = 1'**, không phủ
M3a/M3b, TOU, cắt nguồn, `timestep>1` hay quyết định của chính `SimulatorScheduler`.

## 3. Khác biệt `SimulatorScheduler` (lịch thật) ↔ `_what_if` (quote/booking)

`charging_service._what_if` (charging_service.py:98-150) luôn dùng `assign_connectors(ctx, "edf")` +
`lp_model.solve_with_unmet` (LP backend, bước 15', không có DC taper/acceptance, không coordinator, gán cổng EDF).
Lịch thật mặc định là M3a: dispatch DC theo LLF, AC/DC Rolling LP có taper, Fixed Share. Hệ quả: `feasible`,
`planned_start/end`, `queue_position`, `estimated_cost_vnd` của quote được tính bởi **mô hình khác** với mô hình sẽ
thực thi. Đây là blocker của Phase 4 (guide §2) và là rủi ro sản phẩm: có thể hứa SLA mà M3a không đạt.

## 4. Phân tích interval: event-driven ↔ 15 phút ↔ thời gian vật lý (chưa quyết định)

Hiện có **ba khái niệm thời gian** dính vào nhau:

| Khái niệm | Offline | Backend |
|---|---|---|
| (a) Bước vật lý: độ dài một lần tích phân với công suất giữ nguyên | = interval quyết định (1' hoặc 5') | 1' |
| (b) Interval quyết định: khoảng giữa hai lần chạy dispatch/coordinator/optimizer | event-driven, ≤ `timestep` | TICK 15' + sự kiện (đến/rời/booking/cổng/nguồn/replan), **không** có sự kiện sạc xong / mốc TOU |
| (c) Interval lập kế hoạch: `interval_minutes` mà optimizer thấy (acceptance, block đầu LP) | = (b), cắt theo mốc đã biết ở chế độ online | cố định 15' |

**Tác động khi (a) = (b) (offline hiện nay):**
- Kết quả vật lý **phụ thuộc** cách chia interval. Đổi `timestep` 5→1 sẽ đổi kWh/SOC dù cùng thuật toán. Golden
  MVP-3 (timestep 5) gắn với ZOH 5'.
- Tái lập tốt, nhanh (ít bước), nhưng DC taper thô hơn và mốc hoàn thành bị làm tròn lên cuối interval.

**Tác động khi (b) = (c) = 15' còn (a) = 1' (backend hiện nay):**
- Optimizer hứa theo acceptance tính tại SOC đầu khoảng 15', còn vật lý cắt taper từng phút. Với xe DC đang ở vùng
  taper, `actual < setpoint` trong phần cuối khoảng và phần chênh **không được chia lại** cho xe khác cho tới lần tính
  sau.
- Xe AC/DC đầy giữa chừng để lại công suất tối đa 15' (điểm 4).
- Block đầu LP dài 15' làm thay đổi bài toán LP so với offline (block 5', `block_minutes=5`). Cùng thuật toán nhưng
  input khác thì nghiệm khác. Vì vậy số M3a backend (`eval/results`) **không so trực tiếp được** với MVP-3 offline.
- Ưu điểm: số lần giải LP ít (p95 tính lại khoảng 0.02 s, xem `eval/results`), lệnh trạm ít dao động (anti-flapping),
  hợp với HITL (mỗi lần tính lại có thể sinh approval).

**Tiêu chí cho phương án thống nhất (đề xuất, chưa chọn):**
1. Tách (a) khỏi (b): kernel `advance(minutes)` tích phân theo `physics_step` riêng. Bước vật lý và nhịp quyết định
   là hai tham số khác nhau.
2. Một hàm `boundary()` duy nhất cho mốc event: xe đến/rời, rút DC, **sạc xong**, TOU, LimitEvent đã công bố. Offline
   và backend cùng dùng; backend thêm TICK như một mốc trần (`max_decision_interval`).
3. (c) = khoảng tới mốc kế tiếp đã biết, chặn trên bởi `max_decision_interval`, giống `_online_observation`.

**Các phương án Phase 3 phải chọn (cần quyết định của chủ simulator + Tech Lead):**

| Phương án | Mô tả | Golden MVP-1/2/3 | Rủi ro |
|---|---|---|---|
| **P1 (khuyến nghị)** | Kernel có tham số `physics_step`. Offline giữ `physics_step = interval` (ZOH như hiện tại). Backend dùng `physics_step = 1`. Test differential ở cùng tham số. | **Giữ nguyên** | Còn hai cấu hình vật lý (cùng code). Phải ghi `physics_step` vào trace/report. |
| P2 | Mọi chế độ dùng `physics_step = 1` | MVP-3 (timestep 5) **đổi số**, cần policy/benchmark version mới | Đổi semantics, phải escalate (guide §8) |
| P3 | Backend theo offline: vật lý = interval quyết định (15') | Giữ | Live thô (hoàn thành trễ tới 15'), xấu cho demo; không khuyến nghị |

Dù chọn phương án nào, backend nên phát mốc "sạc xong" và mốc TOU làm điểm tính lại (điểm 4, 5). Đây là đổi hành vi
nghiệp vụ, cần duyệt, không làm trong Phase 1-2.

## 5. Luồng LLM chat hiện tại (chuẩn bị `src/llm_chat/`)

```text
POST /api/v1/chat | /chat/stream (SSE) | /chat/resume         src/api/routes.py
  └─ JWT → resident_id → config["configurable"]  (ADR-006, không qua LLM)
  └─ src.agents.graph.agent (StateGraph + MemorySaver: checkpoint trong RAM, một worker)
       entry → guardrail_check ─(chặn)→ finalize
                 └→ reason (LLM structured AgentDecision | mock_reason) ─(xong)→ finalize
                       └→ act (TOOL_REGISTRY) ─(risky: confirm_booking, send_email)→ human_review (interrupt HITL) → assess
                                               └→ assess ─(lặp / max-iter)→ reason | finalize_with_partial
       finalize: LLM structured FinalAnswer | mock_generate, guardrails hậu kiểm
  tools/charging.py → services.charging_service (quote/_what_if, book) · catalog · energy · charging_demo
LLM provider: src/services/llm.py (openai | local | mock; get_llm, get_structured_llm, cascade)
Prompts: prompts/{reason,finalize,charging_domain,charging_safeguards,...}.md ← src/agents/prompts.py:18 (đường dẫn cố định)
Schemas: src/models/schemas.py (ChatRequest/ChatResponse trong OpenAPI; AgentDecision/FinalAnswer/AgentAnswer nội bộ)
```

**Checklist di chuyển (Phase 5):**
- 21 file trong `src/agents/`. Nối vào graph: `graph, state, guardrails, prompts, mock_llm, nodes/{act,assess,finalize,
  human_review,reason}, tools/{__init__,charging}`. Template chưa nối: `nodes/{retrieve,safety,synthesize,validate}`,
  `personas`, `tools/{knowledge,mcp_tool,risky_tools}`. Các file này vẫn có test dùng, nên phải chuyển test trước khi
  bàn chuyện bỏ.
- `prompts.py:18` dùng `parent.parent.parent / "prompts"`. Nếu `src/llm_chat/` cùng độ sâu thì vẫn đúng. Nếu chuyển
  `prompts/` vào package thì phải sửa loader và test.
- Caller cần đổi import: `src/api/routes.py`, `eval/run_agent_eval.py`, `eval/run_eval.py`, `tests/conftest.py`,
  `tests/__init__.py` (chú thích), 11 file `tests/test_agents/*`, `tests/test_api/test_flows.py` (monkeypatch **chuỗi**
  `"src.agents.mock_llm._now_local"`: `rg` theo dạng import không bắt được), `tests/test_architecture.py`
  (`BOUNDARIES["agents"]`, `test_agent_package_cannot_construct_station_commands`, `test_agent_tools_only_call_the_services_layer`).
- `src/services/llm.py` có caller ngoài chat: `eval/judge.py` (LLM-judge), `routes.py`. Đề xuất: **giữ provider ở
  `src/services/llm.py`** hoặc tách thành provider trung lập. Không nên nhét vào `llm_chat/` vì eval judge và
  AI-1/AI-4 sau này cũng cần.
- `ChatRequest`/`ChatResponse` nằm trong `frontend/openapi.json`. Tên schema trong OpenAPI lấy theo **tên class**,
  không theo module, nên đổi module không đổi hash nếu giữ tên class. Phase 5 phải chạy `export_openapi.py --check`.
- Không có Dockerfile/CI/yaml nào trỏ tới `src/agents` (chỉ `.dockerignore` có `.agents/`, là thư mục khác).

## 6. Đề xuất migration cụ thể (chờ review trước Phase 1)

**Phase 1: contracts (không đổi logic, không đổi số).**
1. Tạo `src/models/simulation_core.py` (`Scenario`, `Cabinet`, `Vehicle`, `Tariff`, `LimitEvent`, `clock`), `src/models/scheduling.py`
   (`Candidate`, `VehicleObservation`, `SchedulingObservation`, `DispatchObservation`, `ZoneBudgets`, `PowerProposal`,
   `EffectiveLimits`, Protocols `DispatchPolicy`/`ZonePowerOptimizer`/`GlobalCoordinator`/`SchedulingPolicy`),
   `src/models/charging_physics.py` (`VehicleBatteryState`, `DCChargingModel`, `energy_to_target`), và chỗ cho
   `TOL`, `ConstraintViolationError`, `valid_kw`.
2. Ở bước này **file gốc giữ nguyên chỗ và re-export** từ models (shim). Golden và hash AST của từng hàm phải giữ
   nguyên (so với `code_hash_manifest.txt`).
   - Cần quyết định: `Scenario.parse` (parser JSON) có tách khỏi dataclass không? Đề xuất: dataclass sang models,
     parser ở lại `src/simulator/scenario.py` dưới dạng hàm. Nhưng `Scenario.parse` hiện là classmethod và được gọi ở
     nhiều nơi, nên **giữ classmethod** trong models để không đổi API. Parser chỉ dùng stdlib nên models vẫn thuần.
3. ADR-019 "Unified Core": boundary mới + viết lại `BOUNDARIES` trong `tests/test_architecture.py`. Thêm luật: cấm
   `src.simulator.src.*` ngoài simulator, `llm_chat` chỉ được gọi `services/models/config`.
4. Thêm test import graph: không có vòng, `src/models` không import ev2gym/scipy/numpy.

**Phase 2: di chuyển cơ học** theo bảng guide §2. Mỗi batch là một commit, chạy 163 test simulator + golden + 440 test
backend sau mỗi batch, so hash AST theo hàm. Một registry policy `src/optimizer/registry.py` với `B0/M2b/M3a/M3b`
đóng băng (+ `M2a/M2c` của MVP-2), `benchmark_mvp3.py`, `benchmark.py` và backend cùng đọc. Riêng `run.py` cần chủ
simulator trả lời có giữ chế độ standalone không (IMPORT_GRAPH §5).

**Phase 3: kernel.** Trích `observe/propose/apply_approved/advance` từ `HybridSimulator.step` (giữ facade `run()`).
`HybridStation` và `SimulatorScheduler` thành adapter. Chọn P1/P2/P3 ở §4 trước khi code. Consent (§2 điểm 9) chuyển
thành bước business giữa `propose` và physical guard, có kiểm lại bằng **cùng** guard. Test differential theo 18 điểm
ở §2.

**Phase 4-6:** theo guide; `_what_if` là blocker cho việc xoá `optimizer/*` cũ.

## 7a. Quyết định của người phụ trách sau review Phase 0 (2026-11-23)

1. Baseline chính thức: `origin/develop @ 68692ee`. Đã đối chiếu mirror `7e1eb61`: trùng 568/568 file.
2. **Bắt buộc giữ chạy standalone** (CLI scenario, benchmark MVP-1/2/3, golden, DecisionTrace) mà không cần
   FastAPI/DB/LLM. Standalone và backend dùng **cùng** Planning Core + Physical Core.
3. Tạm chọn **P1**: một kernel có cấu hình với ba tham số độc lập `physics_step_minutes`, `decision_interval_minutes`,
   `planning_horizon_minutes`. Backend dùng vật lý 1'. Standalone có chế độ tương thích để giữ golden. Tài liệu thiết
   kế phải nêu giới hạn của P1 và so với P2/P3. Không so benchmark giữa hai cấu hình thời gian khác nhau.
4. Replan bắt buộc khi: sạc xong/phiên đổi trạng thái làm đổi tài nguyên; xe đến/rời/huỷ/đổi yêu cầu; nguồn/tủ
   đổi, mất, khôi phục; mốc TOU đã công bố; tick định kỳ. Không replan trùng, có thứ tự sự kiện, không dùng thông tin
   chưa công bố.
5. Tách hai loại ràng buộc: **hard physical** (cổng, tủ, vùng vật lý, nguồn chung/độc lập, acceptance; Physical
   Guard kiểm trước + sau) và **assigned budget** (Coordinator; kiểm ở planning và trước khi gửi lệnh; vượt thì ghi
   sai lệch và xử lý/replan). Không đánh đồng hai loại.
6. Giữ `src/services/llm.py` làm provider dùng chung. Chat cư dân chuyển sang `src/llm_chat/`. `src/agents/` để dành cho AI-1/AI-4.
7. Quote/Admission, Backend Scheduling, Standalone và WHAT-IF phải dùng cùng nguồn logic tối ưu. Không xoá
   `lp_model`/`assignment` khi `_what_if` còn dùng. Cần test chứng minh booking được chấp nhận không mâu thuẫn với policy thực thi.
8. Không ghi đè `eval/results/benchmark.json` trong các phase di chuyển. Evidence mới để ở thư mục riêng, có
   commit/policy/seed/môi trường.

## 7. Câu hỏi đã nêu trước khi vào Phase 1/3 (đã được trả lời ở §7a)

1. Chủ simulator: `8c4c14e` ("MVP-3 but not the final version") đã phải bản MVP-3 cuối chưa? Bản `8d7731c` trên
   mirror có khác không? (MODULE_PROVENANCE §0)
2. Chủ simulator: còn cần chạy `src/simulator/` standalone (nhánh `from src.…` trong `run.py`) không?
3. Tech Lead: chọn P1/P2/P3 cho interval (§4). Có cho backend tính lại lịch khi xe sạc xong và ở mốc TOU không?
4. Tech Lead: post-check sau khi áp ở backend dùng trần vật lý (ADR-017) hay ngân sách coordinator như offline (§2 điểm 11)?
5. `src/services/llm.py` giữ làm provider trung lập (đề xuất) hay chuyển vào `src/llm_chat/provider.py` như guide?
