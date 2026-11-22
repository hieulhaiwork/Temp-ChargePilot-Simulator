# ADR-011: Một `HybridSimulator` sau một bề mặt công khai; một bộ `Algorithms` cho live, benchmark và what-if

> **Sửa đổi một phần bởi [ADR-016](ADR-016-livestation-cho-backend.md) (2026-11-22):** backend live + benchmark
> backend chạy trên `LiveStation`; `HybridSimulator` giữ vai trò R&D offline. Phần còn lại giữ nguyên.

- Trạng thái: Proposed — chờ nhóm duyệt
- Ngày: 2026-11-21
- Sửa đổi một phần: ADR-002 (nội dung `src/simulator/base.py`; hệ quả "benchmark đi chung đường Guard"),
  ADR-007 (`StationRuntime.simulator`, chế độ benchmark)
- Liên quan: ADR-010, ADR-012, ADR-014
- Nguồn: master context v1.0 §5, §10.3; simulator v1.2 (`feature/simulator` @ `d15871a`)

## Bối cảnh

Simulator của skeleton (`src/simulator/{ev2gym_adapter,acnsim_adapter,parking_queue,sessions,kpi}.py`) là stub cho bãi
chỉ AC. Nhánh `feature/simulator` đã có **EV2Gym Hybrid Simulator v1.2**: vùng AC/DC, tủ, hàng chờ theo vùng, đường sạc
DC theo mẫu xe, Guard vật lý, replay, golden regression. Nhóm chốt **một** simulator duy nhất là `HybridSimulator`
(EV2Gym-first: AC dùng `EV.step` của EV2Gym; DC là extension tự viết vì EV2Gym 2.0.0 không có động học DC).

Đã kiểm trong code v1.2:

- `HybridSimulator(scenario, policy=None, *, algorithms=Algorithms(...))` nhận chính sách qua tiêm phụ thuộc.
  `Algorithms` gồm `dispatch[AC|DC]`, `optimizers[AC|DC]`, `coordinator`, `dc_charging_model`.
- Trong `step()`, simulator tự chạy dispatch → coordinator → optimizer → `safety/guard.py` → EV2Gym. Guard vật lý luôn chạy.
- Commit v1.2 xoá `src/simulator/base.py` nhưng `src/guard/dispatcher.py` và `src/services/runtime.py` vẫn import nó.

Hai yêu cầu kéo ngược nhau:

- ADR-002: mọi lệnh tới simulator đi qua `src/guard/dispatcher.py` (Guard chính sách: HITL, quyền, dữ liệu cũ, nhật ký).
- Master context §8.2B: WHAT-IF chạy lại bằng **cùng engine, cùng charging model, cùng chính sách, cùng seed**, chỉ đổi
  biến được hỏi.

Bản nháp ADR-011 trước (20/11) đề xuất chế độ sản phẩm dùng `ExternalCommandPolicy` và `control_loop` tự gọi chính
sách, còn chế độ nghiên cứu để simulator tự gọi. Nếu hai đường gọi chính sách bằng code khác nhau, kết quả live và
counterfactual có thể lệch mà không ai biết.

## Các lựa chọn

1. App gọi thẳng `HybridSimulator`: nhanh, nhưng bỏ qua Guard chính sách, phá ADR-002.
2. Hai đường quyết định riêng (control_loop cho live, registry cho research/what-if): đúng ADR-002 nhưng không bảo đảm
   "cùng chính sách".
3. **Một bộ `Algorithms` duy nhất, dùng chung mọi chế độ; Guard chính sách là cổng duyệt trước khi apply ở chế độ sản
   phẩm; tất cả đi sau một bề mặt công khai `src/simulator/base.py` và một `SimulatorGateway`.**

## Quyết định

Chọn (3).

### 1. Bề mặt công khai

Ngoài `src/simulator/` chỉ được import `src.simulator.base`. `base.py` cung cấp:

| Thành phần | Vai trò |
|---|---|
| `StationReader` | `reset`, `step`, `state() -> StationState` (đổi snapshot v1.2 sang `src/models`) |
| `StationActuator` | `apply_commands(commands)`: nhận kế hoạch **đã qua Guard chính sách** cho bước kế tiếp |
| `HybridStation` | Adapter cài hai interface trên bằng `HybridSimulator` |
| `build_algorithms(selection)` | Dựng `Algorithms` từ registry; cùng một object dùng cho live, benchmark, what-if |
| `check_power_plan(plan, limits)` | Hàm thuần kiểm ba tầng (ADR-010), dùng lại `safety/guard.py`; `src/guard/rules.py` gọi lại, không cài lần hai |
| `build_station(scenario, vehicles, algorithms)` | Factory nhận dữ liệu đã nạp (ADR-012); simulator không tự đọc `config/` |

ADR-002 giữ nguyên: chỉ `src/guard/dispatcher.py` dùng `StationActuator` / gọi `apply_commands`.

### 2. `SimulatorGateway` (hợp đồng tầng ứng dụng, trong `src/services/`)

`create_session`, `get_state`, `submit_request`, `advance`, `replan`, `get_decision_trace`, `simulate_what_if`,
`apply_approved_revision`, `get_kpis`. Bất biến: `simulate_what_if` không bao giờ mutate live session; `replan` luôn qua
Guard; mọi kết quả mang `scenario_id`, `session_id`, `policy_id`, `config_hash` / `state_version`.
`FixtureSimulatorGateway` được phép trong lúc phát triển, nhưng phải gắn nhãn `fixture` trong response và **không xuất
hiện trong luồng demo nghiệm thu**. Cùng bộ contract test chạy trên cả fixture lẫn `HybridSimulatorGateway`.

### 3. Ba cách chạy, một bộ chính sách

| | Live (sản phẩm) | Benchmark nghiệm thu | Research / golden / what-if |
|---|---|---|---|
| Chính sách | `Algorithms` từ `build_algorithms` | như live | như live (cùng object / cùng selection) |
| Ai gọi chính sách | `SimulatorGateway.replan` tính kế hoạch → `guard.dispatcher.submit` → `HybridStation.apply_commands`; simulator áp kế hoạch đã duyệt (dispatch + setpoint) qua policy "đã duyệt" | như live, sinks gom vào bộ nhớ | `HybridSimulator.step()` tự gọi `Algorithms` |
| Guard chính sách | Có | Có | Không (sandbox không có actuation); trace ghi `policy_guard: not_applied` |
| Guard vật lý | Có, fail-stop | Có | Có |

**Tiêu chí đúng** (test bắt buộc trước khi dùng live): với `mvp1` và Guard chính sách cho qua mọi lệnh hợp lệ, đường
live phải tái tạo **đúng** kết quả research (cùng hash report / events / power trace của golden regression). Lệch là
lỗi, không phải "khác biệt chấp nhận được".

Khi Guard chính sách chặn một lệnh ở live, live sẽ khác research; khác biệt đó phải hiện trong DecisionTrace (ADR-014).

### 4. Vị trí code chính sách

Trong sprint 20–26/11, dispatch / coordinator / optimizer chạy thật nằm ở `src/simulator/src/{dispatch,coordination,
optimizers}/` và chỉ được expose qua `base.build_algorithms`. `src/optimizer/` của skeleton giữ là stub. Việc chuyển sang
`src/optimizer/` **HOÃN** tới sau sprint; khi chuyển phải giữ golden hash.

### 5. Dependency

Chỉ gói mà adapter thật sự import (`ev2gym==2.0.0` và phụ thuộc bắt buộc) vào `requirements-runtime.txt`, sau khi đo RAM
và thời gian build image. Gói smoke test upstream (`pandapower`, `matplotlib`, `numba`…) ở `requirements.txt`. Danh sách
nhóm runtime **chưa kiểm** (cần chạy import adapter trong môi trường chỉ có `ev2gym`).

## Bằng chứng

- 21/11, `feature/simulator` @ `d15871a`: `pytest src/simulator/tests` = **112 passed** với `PYTHONUTF8=1`;
  **109 passed / 3 failed** với encoding mặc định Windows (cp1258) — 3 test CLI đọc file không ghi `encoding`. Log:
  `eval/evidence/2026-11-21/raw/sim-v12-pytest*.txt`. Cần sửa test (ghi `encoding="utf-8"`) trước khi merge.
- Golden regression `mvp1` khớp số bàn giao (ADR-010 §Bằng chứng).
- Tiêu chí "live = research" ở §3 **chưa có code**, là [MỤC TIÊU] của Integration Gate 1.

## Hệ quả

- Việc phải làm (T1.4 / T1.10): viết lại `base.py`; `HybridStation`; `build_algorithms`; `SimulatorGateway` +
  `FixtureSimulatorGateway`; `rules.py` gọi `check_power_plan`; sửa `runtime.py`; contract test của adapter và gateway;
  test "live = research"; sửa 3 test encoding.
- `tests/test_architecture.py`: thêm luật "ngoài `src/simulator/` chỉ import `src.simulator.base`"; giữ luật
  `apply_commands` chỉ ở `dispatcher.py`; giữ `simulator ↛ optimizer`.
- Không thay đổi: ADR-004, ADR-006 (ngoài phần ADR-014 sửa), ADR-008, ADR-009.
- Rủi ro: semantic bước (tách interval tại sự kiện, fail-stop không rollback) phải khớp `control_loop`; không khớp thì ghi
  trong contract test, không vá ngầm. Rollback khi hậu kiểm lỗi là câu hỏi mở (master context §15.3 #8).
