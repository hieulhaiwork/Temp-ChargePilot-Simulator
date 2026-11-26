# Audit căn chỉnh Backend ↔ Simulator (chỉ đọc)

- Người làm: Claude Code (`claude-opus-5-5`), vai **Implementation Agent** (chính agent đã viết phần lớn backend) ⇒ đây
  là **tự audit**, chưa phải review độc lập. Cần Codex kiểm lại (mục 9).
- Thời điểm: 2026-11-24. Code: `feature/unified-core` @ `ce23136`. Không có thay đổi nào trong `src/`, `tests/`,
  `config/`, `frontend/`, `migrations/`, `.github/`.
- `git status --short` lúc kiểm: khớp HANDOFF §1.8, cộng `docs/handoff/REVIEW_PHASE1_RESULT.md` (Codex đã ghi kết quả
  review Phase 1) và file này. **Không sửa** tài liệu Phase 1 đang khoá (HANDOFF §1.9); checkpoint §1.11 chưa ghi lần
  audit này vì HANDOFF đang khoá — chờ người giám sát cho phép.
- Phạm vi: đọc code, grep, chạy test. Không sửa code / thuật toán / policy / API / DB / test / CI; không commit.

Nhãn: **ALIGNED** đúng ý định · **MISALIGNED** lệch có bằng chứng · **AMBIGUOUS** yêu cầu / kiến trúc chưa rõ ·
**UNVERIFIED** chưa đủ bằng chứng.

## 1. Kết luận

- Không tìm thấy **MISALIGNED** có bằng chứng. Backend không có optimizer riêng; mọi quyết định công suất / gán cổng đi
  qua Planning Core của `StationKernel` với policy từ `src/optimizer/registry.py`; vật lý đi qua Physical Core của
  cùng kernel.
- Có 4 điểm **AMBIGUOUS** và 3 điểm **UNVERIFIED**. Quan trọng nhất: backend có một **bước consent riêng** chỉnh setpoint
  sau optimizer (B1). Bước này không có ở simulator standalone và không nằm trong differential test.
- Tự đánh giá: câu trả lời trước của tôi trong phiên này ("dùng chung đúng một bộ thuật toán") đúng ở tầng Planning
  Core nhưng **nói quá**. Nó bỏ sót bước consent B1, nên kết quả backend có thể khác simulator khi ràng buộc consent
  có hiệu lực.

## 2. Sơ đồ luồng gọi thực tế

```
API (FastAPI router) ─► services (charging_service / station_service / simulation_service)
        │                         │
        │                 get_runtime() ─► StationRuntime (1 instance live, RAM)
        │                         │            ├─ simulator = HybridStation ─► kernel = StationKernel  ◄── TRẠNG THÁI VẬT LÝ
        │                         │            ├─ scheduler = SimulatorScheduler(policy từ registry)
        │                         │            └─ store = repository (DB: booking, plan, approval, log, event, load, trace)
        │                         ▼
        │       control_loop.on_event  (tuần tự dưới rt.lock — vòng QUYẾT ĐỊNH duy nhất)
        │          1. failsafe nếu HARD_LIMIT_VIOLATED ─► guard.emergency ─► dispatcher
        │          2. rt.advance_clock() ─► HybridStation.step ─► kernel.advance (Physical Core, bước 1')
        │          3. scheduler.plan ─► kernel.propose (dispatch → coordinator → optimizer AC/DC → Physical Guard)
        │                             ─► bước consent backend (B1) ─► kernel.approve (Physical Guard lại nếu bị chỉnh)
        │          4. diff_commands ─► guard/dispatcher.submit (7 luật + HITL) ─► HybridStation.apply_commands
        │          5. _sync_booking_status (DB ← trạng thái vật lý), WebSocket
        ▼
Frontend ◄─ REST (overview = rt.simulator.state(); plan = rt.plan; booking/event/load = DB) + WebSocket

Bản sao tách biệt (không đụng trạng thái live):
  admission (quote/book/change): fork_runtime(rt) ─► HybridStation.fork ─► StationKernel.fork ─► cùng control_loop + Guard
  benchmark (/simulation/run):   build_sim_runtime ─► HybridStation mới cho mỗi run
  CLI / benchmark_mvp3:          HybridSimulator(StationKernel).step = observe → propose → approve → apply_approved → advance
```

## 3. Quyền sở hữu trạng thái

| Câu hỏi | Trả lời theo code | Nguồn |
|---|---|---|
| Ai sở hữu trạng thái vật lý có thẩm quyền | `StationKernel` bên trong **một** `HybridStation` của runtime live (`_live`, singleton trong process) | `src/services/runtime.py:313-398`, `src/simulator/hybrid_station.py:198` |
| Nơi khởi tạo kernel | (a) `HybridStation._init` → `StationKernel(...)`; (b) `HybridSimulator` **là** `StationKernel` (kế thừa); (c) `StationKernel.fork` | `hybrid_station.py:198`, `hybrid.py:26`, `kernel.py:121` |
| Backend và `SimulatorScheduler` dùng chung instance? | Có. Scheduler nhận `lambda: station` và gọi `station.kernel.propose` trên **chính** trạm live | `runtime.py:236-239`, `hybrid_planner.py` `decide()` |
| Các instance khác và vòng đời | live: sống theo process · fork admission: mỗi lần quote / book / change, bỏ sau khi đọc kết quả · benchmark: mỗi run một trạm mới · `HybridSimulator`: mỗi lần chạy CLI / benchmark | `runtime.py:416-445`, `admission.py` `evaluate`, `simulator/run.py:207`, `benchmark_mvp3.py:134` |
| SOC, hàng chờ, gán cổng, deadline, trạng thái xe | kernel: `adapter` (EV2Gym: SOC), `queue` (`QueueController`: waiting / occupied / sessions), `setpoints`, `faults`. Deadline nằm trong `Vehicle.departure` của kernel, lấy từ booking qua `visit_of` | `kernel.py`, `runtime.py:259` |
| DB lưu gì | Trạng thái **nghiệp vụ**: users, bookings, idempotency, schedule_plans, approvals, decision_log, notifications, station_events, load_points, decision_traces. **Không** lưu SOC / setpoint | `src/db/tables.py` |
| Trạng thái lưu trùng | `Booking.status` / `connector_id` (DB) phản chiếu trạng thái kernel, đồng bộ một chiều kernel → DB ở `_sync_booking_status` sau mỗi lần tính lại. Xem B3 | `control_loop.py:482-502` |
| Frontend đọc từ đâu | overview / connector: `rt.simulator.state()` (kernel) · lịch: `rt.plan` (RAM) hoặc `latest_plan` (DB) · booking / sự kiện / tải: DB · WebSocket từ control_loop | `station_service.py:76-115` |
| Mất trạng thái khi restart | Trạng thái vật lý mất; nạp lại booking hiệu lực và lịch gần nhất, xe coi như đang chờ (có ghi log cảnh báo) | `runtime.py:383-393` |

**Kết luận §3: ALIGNED.** Có nhiều instance kernel nhưng mỗi instance có mục đích và vòng đời riêng, và không chia sẻ
trạng thái có thể thay đổi. Bằng chứng: `tests/test_services/test_fork_isolation.py`,
`src/simulator/tests/test_fork_isolation.py`, `tests/test_refactor/test_differential.py::test_fork_registers_what_if_vehicles_without_touching_live`.

## 4. Vòng điều khiển

| Câu hỏi | Trả lời | Nguồn |
|---|---|---|
| Ai kích hoạt chu kỳ | Sự kiện qua `event_bus` → `control_loop.on_event` (đăng ký ở `get_runtime`). Nguồn sự kiện: booking / change / cancel, incident, nút replan, `deliver_pending` (outbox), `run_forever` (TICK ở mốc quyết định kernel) | `runtime.py:394`, `control_loop.py:66,163,357` |
| Liên kết Scheduler ↔ control loop | `on_event` gọi `solver.run_async(rt.scheduler.plan, ctx)` | `control_loop.py:101` |
| Hai vòng cùng **quyết định**? | Không. Chỉ `on_event` ra quyết định, tuần tự dưới `rt.lock` (asyncio). `run_forever` chỉ tiến đồng hồ và chuyển sự kiện cho `on_event` / `on_minute` | `control_loop.py:66-137,163-195` |
| Ai quản lý thời gian | `rt.clock` (live: giờ thật × `SIM_TIME_SCALE`; benchmark / fork: `simulator.now`). Kernel tiến tới đồng hồ đó qua `advance_clock`. Mọi thao tác trạm khoá bằng `HybridStation.lock` (RLock) | `runtime.py:138-160,296-307`, `hybrid_station.py:71-83` |
| Xe đến / rời / sạc xong / sự cố | Kernel phát sự kiện (`_emit`) khi `step` → `rt.outbox` → `on_event` gộp thành **một** lần tính lại / phút; `POWER_LIMIT_CHANGED` và `HARD_LIMIT_VIOLATED` xử lý khẩn cấp trước | `hybrid_station.py:713-733`, `control_loop.py:78-97,146-160` |
| Guard vật lý | (1) `kernel.propose` → `guard(...)` trước khi trả đề xuất; (2) `kernel.approve` kiểm lại nếu bị chỉnh; (3) luật `total_power_limit` của Business Guard dùng `src/guard/physical/adapter.py` → validator gốc; (4) `kernel.advance` ghi vi phạm sau khi áp ⇒ fail-safe | `kernel.py:352-467`, `src/guard/rules.py:139`, `hybrid_station.py:316-358` |
| Guard nghiệp vụ | `guard/dispatcher.submit`: 7 luật + HITL (`approval.py`) + kiểm lại lệnh tăng trong lô áp một phần | `src/guard/dispatcher.py` |
| Có đường bỏ qua Guard? | Trạm live: không. `apply_approved` (ghi thẳng vào kernel) ném `RuntimeError` nếu không phải bản fork. Fork của admission **cũng** đi qua dispatcher (`on_minute` → `on_event`). Chỉ `HybridSimulator` standalone dùng `apply_approved` trực tiếp (đúng thiết kế: CLI không có tầng nghiệp vụ). `tests/test_architecture.py` khoá import `apply_commands` | `hybrid_station.py:500-505`, `admission.py` |
| Đầu vào "thế giới" không qua dispatcher | `upsert_vehicle` / `remove_vehicle` (xe đến / huỷ), `inject_incident` (lỗi cổng, giảm nguồn) đổi kernel trực tiếp. Đây là **sự kiện môi trường**, không phải lệnh điều khiển; ADR-002 chỉ áp cho `Command` | `charging_service.py` (book / change / cancel dưới `rt.lock`), `simulation_service.py:375-390` |

**Kết luận §4: ALIGNED**, trừ U1 (tiến đồng hồ ngoài `rt.lock`).

## 5. Trùng lặp optimizer

| Kiểm | Kết quả | Nhãn |
|---|---|---|
| Thuật toán LP / EDF / LLF / equal-share ngoài `src/optimizer`, `src/simulator` | grep `linprog|pulp|cvxpy|highspy|scipy.optimize|least_laxity|earliest_deadline|equal_share` ⇒ chỉ có `src/services/solver.py`, là thread wrapper cho HiGHS, không có thuật toán | ALIGNED |
| Bảng policy riêng của backend | `hybrid_planner.POLICIES` **dẫn xuất** từ `registry.POLICIES`; `make_scheduler` / `is_registered` tra thẳng registry | ALIGNED |
| Bộ phân bổ AC/DC riêng | Không có; coordinator lấy từ registry, chạy trong `kernel.propose` | ALIGNED |
| Bộ xếp hàng / ưu tiên riêng | Gán cổng = `kernel._dispatch` (dispatch policy của registry); `diff_commands` chỉ dịch kết quả thành lệnh | ALIGNED |
| Bước chỉnh setpoint ngoài Planning Core | `_start_minimums` + `_fit_with_minimums` (consent `max_start_delay_minutes`), có co công suất theo tủ → vùng → lưới | **AMBIGUOUS (B1)** |
| Ước tính ETA hàng chờ | `_queue_etas` là heuristic riêng, không dùng đường sạc DC | **AMBIGUOUS (B2)** |
| Fail-safe co đều | `guard.emergency.curtail_to_hard_limits` co đều bằng chia đôi trên `physical.check_site_allocation`. Đây là cơ chế an toàn, không phải optimizer, và không viết lại công thức trần | ALIGNED |
| KPI | `simulation_service.compute_kpis` (đúng hạn = năng lượng tới deadline trên booking "khả thi") khác `simulator/evaluation/extended.py` (đúng hạn = `completed_at ≤ departure`) | **AMBIGUOUS (B4)** |
| Policy đóng băng B0–M3b | Không sửa; `tests/test_refactor/test_policy_registry.py::test_frozen_policies_keep_id_version_and_components` đạt | ALIGNED |

## 6. Truy vết 5 tình huống

| # | Entry point | Service | Kernel | Quyết định | Kiểm soát | Cập nhật trạng thái | Trả về FE | Test |
|---|---|---|---|---|---|---|---|---|
| 1 Đặt lịch | `POST` booking (`src/api/resident.py`) / tool chat `confirm_booking` | `charging_service.book` → `admission.evaluate` trên fork → commit dưới `booking_lock` + fingerprint | fork (what-if), rồi live (`upsert_vehicle`) | Planning Core trên fork; sau đó `on_event(BOOKING_CREATED)` trên live | dispatcher (cả trên fork) | DB `bookings`; kernel live thêm `Vehicle` | `Booking` (status, connector dự kiến, giờ, chi phí ước tính) | `test_api/test_flows.py::test_form_booking_works_without_llm`, `test_admission.py::test_accepted_booking_is_executed_exactly_as_quoted`, `test_booking_concurrency.py` |
| 2 Vào hàng chờ, phân cổng | sự kiện `VEHICLE_ARRIVED` / TICK | `control_loop.on_event` | live | `kernel._dispatch` (dispatch policy) | dispatcher (`ASSIGN_CONNECTOR`, luật conflicts / permission) | `apply_commands` → `kernel.connect`; `_sync_booking_status` → QUEUED / CHARGING | overview, plan, WS `SCHEDULE_CHANGED` | `test_flows.py::test_walk_in_when_full_gets_queue_position`, `test_admission.py::test_quote_queue_position_comes_from_the_execution_policy`, `test_hybrid_station.py::test_connector_fault_sends_vehicle_to_queue_head` |
| 3 Phân bổ AC/DC | mọi lần `on_event` | `SimulatorScheduler.decide` | live | `algorithms.coordinator` → optimizer AC / DC (trong `propose`); consent B1 có thể chỉnh | Physical Guard (propose / approve) + 7 luật | `hold_setpoint` qua `apply_commands`; vật lý ở `advance` | plan, overview | `test_differential.py::test_same_state_gives_the_same_proposal_and_the_same_execution[B0..M3b]`, `test_replan_events.py::test_budget_deviation_*`, `test_config_parity.py` |
| 4 Đầy pin vẫn chiếm cổng | kernel phát `CHARGE_COMPLETED` | `on_event` | live | AC: giữ cổng tới giờ rời; DC: rút sau `delay` (`UNPLUGGED`) | Guard không cấp điện cho xe đầy (ADR-017) | kernel queue; booking → COMPLETED khi rời | WS event, overview | `test_hybrid_station.py::test_dc_unplugs_after_delay_ac_holds_until_departure`, `test_replan_events.py::test_charge_completion_is_its_own_event_once_and_not_a_replan_request` |
| 5 Sự cố cổng / nguồn | `POST /simulation/incident` (`src/api/simulation.py:49`) | `simulation_service.inject_incident` (dưới `rt.lock`) | live | nguồn: `emergency.curtail_to_limit` trước, rồi tính lại; cổng: `kernel.fault_port` đưa xe về đầu hàng | dispatcher (lệnh EMERGENCY không chờ HITL) | kernel (`grid_input_override_kw` / `faults`) | WS event + snapshot | `test_flows.py::test_power_drop_is_curtailed_before_replan`, `test_differential.py::test_connector_fault_uses_the_same_kernel_primitive_on_both_sides`, `test_failsafe_after_apply.py` |

## 7. Báo giá và booking

| Câu hỏi | Trả lời | Nhãn |
|---|---|---|
| Fork độc lập với live? | Có: `HybridStation.fork` (lock mới, `_visits` chép, `kernel.fork` sao sâu EV2Gym / queue / setpoint / thành phần có trạng thái), store và sinks trong bộ nhớ, `apply_approved` chỉ cho fork | ALIGNED (`test_fork_isolation.py` ×2) |
| Cùng policy và vật lý? | Cùng `policy_id`, `parameters`, `metadata`, `algorithms` (bản đã cô lập), cùng `control_loop` + dispatcher, cùng DC model | ALIGNED (`test_config_parity.py::test_admission_fork_keeps_the_parameters`, `test_non_default_parameters_give_the_same_results_in_live_benchmark_and_admission`) |
| Xác nhận booking cập nhật gì | DB `bookings` (status, connector **dự kiến**, giờ, chi phí), `booking_version += 1`, kernel live `upsert_vehicle`, rồi `BOOKING_CREATED` → tính lại trên live | ALIGNED; xem B3 |
| Trạng thái đổi giữa quote và xác nhận | `book` **chạy lại admission** (không tái dùng quote), so `admission_fingerprint` (booking, nguồn, cổng lỗi, policy, từ chối / giữ an toàn) khi commit; đổi ⇒ chạy lại, tối đa `BOOKING_COMMIT_ATTEMPTS`, hết lượt ⇒ `PROPOSAL_EXPIRED`; không khả thi ⇒ `PROPOSAL_EXPIRED` | ALIGNED (`test_admission_consistency.py` 9 test) |
| Kết quả dự kiến = kết quả vận hành? | **Không bảo đảm**. Đây là ước tính có điều kiện, có `ASSUMPTIONS`: không biết xe chưa đặt, sự cố tương lai, phê duyệt HITL. Fingerprint không gồm phút trôi / xe cắm-rút bình thường. Chỉ đảm bảo trong một worker | ALIGNED với ý định (không hứa SLA); `test_accepted_booking_is_executed_exactly_as_quoted` chỉ chứng minh cho kịch bản tất định không có biến động |

## 8. Danh sách phát hiện

### AMBIGUOUS

**B1. Bước consent của backend chỉnh setpoint sau Planning Core.**
- Bằng chứng: `src/services/hybrid_planner.py` `SimulatorScheduler.decide` → `_start_minimums` (xe phải bắt đầu sạc theo
  `consent.max_start_delay_minutes`) → `_fit_with_minimums` (nâng xe đó lên mức tối thiểu, co xe khác theo tủ → vùng →
  lưới) → `kernel.approve` (Physical Guard kiểm lại). `HybridSimulator.step` gọi `approve(proposal)` không chỉnh.
  `test_differential.py` gọi `station.kernel.approve(backend)` trực tiếp, **không** qua `SimulatorScheduler.decide`.
- Tác động: khi ràng buộc consent có hiệu lực, cùng kịch bản có thể cho kết quả khác giữa backend (live / benchmark /
  admission, cả ba nhất quán với nhau) và `HybridSimulator` CLI. Phần "co công suất" là một quy tắc phân bổ thứ hai,
  đơn giản (co đều), nằm ngoài optimizer.
- Nguyên nhân: consent là khái niệm nghiệp vụ của cư dân; simulator standalone không biết cư dân. HANDOFF (mục 22/11)
  đã ghi việc còn lại "consent cư dân trong thuật toán simulator".
- Câu hỏi cần quyết: consent có phải ràng buộc của Planning Core (khi đó simulator cũng phải có, bằng policy mới vì
  B0–M3b đóng băng) hay là business rule của backend (giữ như hiện tại, ghi rõ trong ADR và loại khỏi khẳng định
  "backend = simulator")? Chưa nên sửa code trước khi có quyết định này.

**B2. ETA hàng chờ là heuristic riêng của backend** (`_queue_etas`, ghi `[GIẢ ĐỊNH]`, không tính đường sạc DC). Chỉ dùng
cho slot ETA trong `SchedulePlan` hiển thị; báo giá dùng fork thật. Tác động: ETA trên lịch S6 / hàng chờ có thể khác
ETA trong báo giá. Cần quyết có giữ hay không.

**B3. `Booking.connector_id` trộn cổng thật và cổng dự kiến.** `book` ghi connector của kết quả admission;
`_sync_booking_status` ghi cổng thật khi xe đã cắm, còn không thì ghi cổng trong plan. Frontend không phân biệt được hai
loại. Chưa kiểm frontend hiển thị thế nào.

**B4. Hai định nghĩa "đúng hạn".** Backend `compute_kpis` (năng lượng tới deadline, mẫu là booking "khả thi" theo
`_is_feasible`) khác simulator `evaluation/extended.py` (`completed_at ≤ departure`, mọi xe). Không phải trùng
optimizer, nhưng con số so sánh giữa hai phía có thể không cùng nghĩa. Liên quan quyết định D-4 (registry §6) và kết
luận của Codex về baseline 29–32%.

### UNVERIFIED

**U1. Tiến đồng hồ ngoài `rt.lock`.** `rt.sync_clock()` ở các đường đọc (`quote`, `overview`, `session_view`…) chạy
`HybridStation.step` **ngoài** `rt.lock`, chỉ dưới `HybridStation.lock`. Vì vậy vật lý có thể tiến giữa
`scheduler.plan` (khoá trạm) và `dispatcher.submit`. Khi đó lệnh mang `based_on_state_at` cũ. Luật `stale_state`
(`max_state_age_seconds: 60`) và `schedule_version` sẽ **chặn**, tức là hỏng theo hướng an toàn (không cấp điện sai).
Nhưng với `SIM_TIME_SCALE` lớn, lần tính lại có thể bị chặn lặp lại. Không thấy test cho trường hợp đồng thời này.
Cần một test tái hiện trước khi kết luận có lỗi.

**U2. Một worker.** Khoá, fingerprint, trạng thái kernel nằm trong RAM. Đã ghi là giới hạn (CLAUDE.md), chưa kiểm nhiều
worker.

**U3. Hệ quả khôi phục sau restart** (xe đang cắm coi như chờ, mất năng lượng đã giao trong kernel) mới được ghi log, chưa
có test đối chiếu với DB.

### MISALIGNED

Không có phát hiện nào có đủ bằng chứng.

## 9. Tự đánh giá (Implementation Agent)

- Có hiểu sai vai trò simulator khi xây backend không? Ở code hiện tại: **không thấy bằng chứng**. Simulator / kernel là
  "thế giới vật lý + Planning Core"; backend chỉ điều phối, nghiệp vụ, Guard. Kiến trúc cũ (`LiveStation`, LP backend
  A–D, trước 23/11) **đúng là** đã có optimizer và vật lý riêng của backend. Phần đó đã bị xoá ở Unified Core
  (`docs/refactor/DELETION_MANIFEST.md`, `docs/refactor/PHASE0_FINDINGS.md`). Đó là bằng chứng nhóm (và agent) từng
  làm lệch, nay đã sửa.
- Thành phần dư thừa: không thấy trong `src/` hiện tại.
- Logic có thể cần hợp nhất: B1 (consent), B4 (KPI), có thể B2 (ETA). Mỗi việc cần quyết định trước khi sửa.
- Giải thích trước đó: câu "dùng chung đúng một bộ thuật toán" **nói quá**, vì bỏ sót B1.

## 10. Lệnh đã chạy (để reviewer chạy lại)

```bash
git status --short && git diff --stat && git rev-parse --short HEAD          # ce23136
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_refactor \
  tests/test_services/test_admission.py tests/test_services/test_admission_consistency.py \
  tests/test_services/test_fork_isolation.py tests/test_services/test_booking_concurrency.py \
  tests/test_services/test_config_parity.py tests/test_services/test_hybrid_planner.py \
  tests/test_services/test_failsafe_after_apply.py tests/test_services/test_safety_event_delivery.py \
  tests/test_simulator tests/test_architecture.py tests/test_api/test_flows.py src/simulator/tests/test_fork_isolation.py
# 2026-11-24 @ce23136: 203 passed (Windows, SQLite tạm, LLM giả)
grep -rln "linprog\|pulp\|cvxpy\|highspy\|scipy.optimize\|least_laxity\|earliest_deadline\|equal_share" src --include=*.py
```

Gợi ý cho reviewer độc lập: (1) kiểm B1 bằng cách so `SimulatorScheduler.decide` với `HybridSimulator.step` trên kịch
bản có `max_start_delay_minutes` nhỏ; (2) tìm đường nào khác ghi vào kernel live ngoài dispatcher và các sự kiện môi
trường ở §4; (3) thử tái hiện U1.
