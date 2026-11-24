# FINAL_REVIEW_FIX_B_REPORT — nhánh `feature/unified-core-review-b` (claude3)

> Brief: `docs/refactor/tasks/FINAL_REVIEW_FIX_BRIEF.md` (nhánh B). Nguồn: `docs/refactor/raw/final-review/FINAL_REVIEW_2026-11-24.md` §4.3,
> §4.4, §4.5 (phần b), §4.6. Gốc nhánh: `7294803`. Log cổng kiểm: `docs/refactor/raw/final-review-b/`.
> Không push / merge / rebase. Không sửa `CLAUDE.md`, ADR, `REFACTOR_REPORT.md`, `FINAL_MAP.md` (đề xuất ở §7).

## 1. Tóm tắt

| Mục | Commit | Mặc định | Kết quả |
|---|---|---|---|
| 4.3 Ground truth vs observed / estimated | `dcaa7ed` | `PerfectObservation` (identity) | lớp quan sát cắm vào kernel, test chống leakage |
| 4.4 Fork isolation | `dcaa7ed` | thành phần hiện có khai báo stateless ⇒ vẫn dùng chung | quy tắc share / fork / copy, test đột biến kernel + admission |
| 4.5b Fail-safe sau khi áp + negative test dispatcher | `74700d7` | `guard.after_apply_failsafe: false` | sự kiện `hard_limit_violated` → lệnh EMERGENCY qua dispatcher; bất biến lô áp một phần |
| 4.6 Booking concurrency + consent parity | `3b25130` | luôn bật (sửa lỗi đúng đắn) | optimistic concurrency, không overbook, consent parity |

Chênh lệch so baseline: **0** (benchmark backend 100 run 0 problems; golden simulator 0 unexpected; AST 114/0).

## 2. 4.3 — Ground truth / declared / observation / estimated

**Làm gì**
- `src/models/scheduling/observations.py` (thuần stdlib, CHỈ thêm định nghĩa mới; `VehicleObservation`,
  `SchedulingObservation`, `Candidate` giữ nguyên byte ⇒ AST gate không đổi):
  - `SocEstimate(value, measured_at, uncertainty, source)` — giá trị ước lượng + thời điểm mẫu + độ bất định;
  - `EstimatedVehicleObservation(VehicleObservation)` — trường tuỳ chọn `estimate`, ràng buộc `soc == estimate.value`;
  - `estimated(row, estimate)` — chỉ thay SOC;
  - `ObservationModel` (Protocol `observe(minute, truth) -> rows`), `PerfectObservation` (identity, trả CÙNG object).
  - Docstring module định nghĩa 4 lớp: ground truth (EV2Gym SOC, queue, năng lượng — vật lý, Physical Guard sau áp,
    KPI) / declared (`Vehicle`) / observation (điểm cắm noise / delay / missing / stale) / estimated (planner thấy).
- `src/simulator/core/kernel.py`: tham số `observation_model` (mặc định `PerfectObservation()`); `_view()` = nơi DUY
  NHẤT dựng dòng xe cho dispatch / coordinator / optimizer (`dispatch_observation`, `propose`,
  `HybridStation.scheduling_observation`) → đi qua `observation_model`; `_truth_view()` = ground truth. Kernel kiểm:
  mô hình chỉ được đổi SOC (cùng xe / trạng thái / cổng), nếu không `ValueError`. Vật lý (`advance`), hoàn thành phiên,
  KPI vẫn đọc `adapter.soc`.
- `HybridSimulator` / `HybridStation`: tham số tuỳ chọn `observation_model` (truyền thẳng vào kernel).
- Không cài mô hình nhiễu thật (MVP-3.5).

**Kênh còn lại (ghi rõ trong docstring kernel):** `Candidate.allowed_kw` = acceptance vật lý (EVSE / BMS) tính từ SOC
thật; Physical Guard cần đúng số này. Acceptance "quan sát được" là việc MVP-3.5.

**Test** — `src/simulator/tests/test_observation_layers.py` (5 test):
- `test_planner_receives_only_the_observed_soc`: mô hình lệch −0,1, mẫu trễ 5' ⇒ MỌI lần dispatch (LLF) và optimizer
  được gọi đều nhận `EstimatedVehicleObservation` với SOC = thật − 0,1, 0 lần nhận SOC thật;
- `test_physics_and_kpi_keep_using_ground_truth`: SOC trong báo cáo = SOC EV2Gym; hoàn thành đo bằng SOC thật;
- `test_perfect_observation_is_identity_and_keeps_results`: `run()` có / không `PerfectObservation` bằng nhau;
- `test_observation_model_may_only_change_the_soc`, `test_soc_estimate_is_validated`.

## 3. 4.4 — Fork isolation

**Làm gì**
- `src/simulator/core/isolation.py` (mới): quy tắc
  - **share**: chỉ thành phần khai báo stateless — `STATELESS` (hàm theo identity, lớp theo ĐÚNG type) hoặc
    `__stateless__ = True`. Danh sách là sự thật đã kiểm của code hiện tại: mọi dispatch / optimizer / coordinator đã
    đăng ký (hàm thuần, frozen dataclass, `DynamicSlackCoordinator` không thuộc tính), `SyntheticTaperV1`,
    `VehicleProfilesDCModel` (frozen), `PerfectObservation`;
  - **fork**: thành phần có `fork()` → gọi `fork()`;
  - **copy**: còn lại → `copy.deepcopy` (mặc định an toàn). Ghi chú: hàm / closure không copy được (Python trả lại
    chính nó) ⇒ thành phần có trạng thái trong closure phải là object có `fork()`.
  - `memo` chung ⇒ một object dùng ở hai chỗ (DC model trong `algorithms` và adapter; một optimizer cho AC + DC) thành
    MỘT bản copy. Mọi thành phần share ⇒ trả lại CÙNG `Algorithms` (không đổi hành vi).
- `StationKernel.fork()`: áp quy tắc cho `algorithms`, `policy`, DC model của adapter, `observation_model`; docstring ghi
  rõ cái gì share / fork / copy.
- `src/services/runtime.fork_runtime`: scheduler của bản fork dùng `fork.kernel.algorithms` (bản đã cô lập) thay vì
  `algorithms()` của scheduler live — trước đây `SimulatorScheduler.configure` sẽ gắn lại bản live vào fork. Thành phần
  stateless ⇒ cùng object như cũ.
- `HybridStation.fork()`: `_algorithms` / `_observation_model` của bản fork trỏ bản đã cô lập (chỉ khi live có cấu hình).

**Test**
- `src/simulator/tests/test_fork_isolation.py` (6 test, kernel thật trên mvp1): mọi policy B0 / M2b / M3a / M3b + 2 DC
  model ⇒ fork dùng CÙNG object (hành vi cũ); optimizer đếm lần gọi (không `fork()`) ⇒ deep copy, live không đổi sau
  60' chạy trên fork; coordinator có `fork()` ⇒ dùng snapshot riêng; DC model có trạng thái ⇒ một bản copy cho adapter
  + algorithms, live không đổi; mô hình quan sát có `random.Random` ⇒ RNG / cache live không đổi, fork bắt đầu đúng
  trạng thái RNG; thành phần lạ ⇒ copy.
- `tests/test_services/test_fork_isolation.py` (2 test): optimizer "warm start" có trạng thái gắn vào M3a của runtime;
  `admission.evaluate` chạy tới deadline trên bản fork ⇒ lịch sử của optimizer live không đổi; policy stateless vẫn
  dùng chung.

## 4. 4.5b — Fail-safe sau khi áp + negative test dispatcher

**Làm gì** (opt-in, ADR-003)
- `GuardSettings.after_apply_failsafe: bool = False` + khoá `guard.after_apply_failsafe: false` trong
  `config/station.yaml` (tắt = như cũ: kernel non-strict chỉ đếm + log ở `_after_apply_violation`).
- `EventType.HARD_LIMIT_VIOLATED = "hard_limit_violated"` (chỉ thêm enum). Bật cờ ⇒ `HybridStation.step` phát MỘT sự
  kiện / lần step khi `AppliedResult.violations` không rỗng (kernel không tự hạ setpoint, không gọi actuator).
- `src/guard/emergency.curtail_to_hard_limits(state, config, now, detail)`: co ĐỀU mọi cổng đang cấp điện tới hệ số lớn
  nhất mà `physical.check_site_allocation` (đúng luật `total_power_limit`: tủ, vùng, lưới / nguồn độc lập) còn qua —
  chia đôi 40 bước, làm tròn xuống 3 chữ số, nguồn `EMERGENCY`. Không viết lại công thức giới hạn.
- `src/services/control_loop.on_event`: sự kiện `HARD_LIMIT_VIOLATED` (chính hoặc trong lô cùng phút) ⇒ `_failsafe` →
  `dispatcher.submit` (Business Guard; là giảm tải an toàn nên không chờ HITL / anti-flapping) → log warning, thông báo
  cư dân, lệnh nằm trong `DecisionTrace.emergency_commands` (cùng `correlation_id`), rồi tính lại lịch như mọi sự kiện.
  Phần thông báo của `_emergency` tách thành `_notify_curtailed` (hành vi giữ nguyên).
- Strict (`HybridSimulator`) giữ nguyên: raise.

**Test**
- `tests/test_services/test_failsafe_after_apply.py`: nguồn tụt "im lặng" (không có `POWER_LIMIT_CHANGED`) ⇒ vi phạm sau
  áp ⇒ `hard_limit_violated` ⇒ lệnh EMERGENCY executed, có `correlation_id`, log "fail-safe sau khi áp", trace có
  `emergency_commands`; phút sau 0 vi phạm, Σ/η ≤ nguồn. Cờ tắt ⇒ không có sự kiện, chỉ đếm + log như cũ; config gốc
  có cờ = false.
- `tests/test_guard/test_partial_batch_safety.py` (bổ sung `test_increase_that_relies_on_a_reduction_blocked_by_guard…`):
  - lệnh giảm bị chặn vì `stale_state` ⇒ lệnh tăng phụ thuộc không áp;
  - lệnh giảm bị chặn vì `schedule_version` ⇒ không áp gì;
  - lệnh giảm chờ duyệt rồi HẾT HẠN ⇒ không duyệt được, lệnh tăng gửi lại riêng vẫn bị `total_power` chặn;
  - **bất biến 400 lô ngẫu nhiên** (seed cố định: chặn / chờ duyệt AGENT + consent / cũ / xung đột / chống bật-tắt):
    nhật ký executed = đúng tập tới actuator; mọi lệnh áp ≤ cổng / xe; trạm trong trần ⇒ sau lô vẫn trong trần; trạm đã
    vượt ⇒ về trong trần hoặc chỉ giảm. Kiểm đột biến: thay `_without_unsafe_increases` bằng identity ⇒ test fail;
  - `curtail_to_hard_limits` đưa trạm vượt cả lưới về trong mọi trần, co vừa đủ; lệnh qua dispatcher dù cư dân không cho
    giảm công suất và cổng đang bị chống bật-tắt.

## 5. 4.6 — Booking concurrency + consent parity

**Làm gì** — `src/services/charging_service.book`, `src/services/runtime.StationRuntime`
- `StationRuntime.booking_lock` (asyncio) + `booking_version` (int). Thứ tự khoá: `booking_lock` rồi `lock`
  (`on_event` chỉ lấy `lock`) ⇒ không deadlock.
- `book`: kiểm nhanh idempotency + booking hiệu lực → vòng tối đa `BOOKING_COMMIT_ATTEMPTS = 3`: đọc `booking_version`,
  admission NGOÀI khoá, rồi dưới `booking_lock` kiểm lại idempotency, booking hiệu lực của cư dân (BOOKING_CONFLICT) và
  `booking_version`; đổi ⇒ chạy lại admission (trạng thái mới có booking kia); không còn khả thi / hết lượt ⇒
  `PROPOSAL_EXPIRED`. Commit = lưu booking + `booking_version += 1` + đưa xe vào trạm; `BOOKING_CREATED` phát sau khi nhả
  khoá (replan không nằm trong khoá commit).
- `cancel` / `change`: lưu + tăng `booking_version` dưới `booking_lock` (booking đang tính phải kiểm lại).
- Consent parity: admission của `book` chạy trên candidate mang ĐÚNG consent sẽ lưu (`consent` truyền vào hoặc consent
  hồ sơ cư dân). `quote` giữ consent mặc định như cũ.
- Không thêm ràng buộc DB: một worker (CLAUDE.md), khoá trong process đủ (xem ESCALATION 5).

**Test** — `tests/test_services/test_booking_concurrency.py` (5 test, `asyncio.gather`, barrier quanh
`admission.evaluate` để cả hai yêu cầu tính admission trên trạng thái chưa có booking của nhau):
- cùng cư dân ⇒ đúng 1 booking, yêu cầu kia `BOOKING_CONFLICT`, admission không chạy dưới khoá commit;
- cùng idempotency key ⇒ cùng một booking;
- hai cư dân tranh cổng AC cuối (cổng kia bị xe ở lại 10 h giữ, hạn 1 h) ⇒ 1 booking, người sau chạy lại admission
  (3 lượt admission) và nhận `PROPOSAL_EXPIRED`. Kiểm đột biến: bỏ kiểm `booking_version` ⇒ test fail (overbook);
- consent parity: admission nhận đúng consent được lưu (truyền vào / mặc định hồ sơ); `quote` vẫn consent mặc định.

## 6. Cổng kiểm (log ở `docs/refactor/raw/final-review-b/`)

| Kiểm | Kết quả | Log |
|---|---|---|
| `ruff check` + `ruff format --check` `src tests scripts/refactor` | pass (216 file) | `ruff.txt` |
| `ruff` toàn `scripts/` | lỗi CÓ SẴN ở `scripts/log_*.py`, `submit_log.py`, `check_docs.py` (không sửa — xem ESCALATION 2) | `ruff_full_scripts.txt`, `ruff_format_full_scripts.txt` |
| `pytest tests -q` | **536 passed, 8 skipped** (trước: 521) | `pytest_tests.txt`, `pytest_tests_before.txt` |
| `pytest src/simulator/tests -q` | **174 passed** (trước: 163) | `pytest_simulator.txt` |
| AST gate (`compare_ast_manifest.py … -- src`) | **114 compared, 0 undeclared, 0 declared** | `ast_gate.txt` |
| Golden simulator (`run_sim_kpi_gate.py run` + `compare --evidence eval/evidence/2026-11-22/raw/sim-hardware`) | **38/38 OK, 0 unexpected**; MVP-1/2/3, VinFast, DecisionTrace mvp1_m3 khớp evidence | `sim_run.txt`, `kpi_gate.txt` |
| Benchmark backend `--seeds 1,2,3,4,5` + `compare_backend_benchmark.py` | **100/100 run, 0 problems** | `eval_run_benchmark.txt`, `benchmark_compare.txt` |
| Như trên, tạm bật `after_apply_failsafe: true` (không commit) | **0 problems** | `benchmark_compare_failsafe_on.txt` |
| `export_openapi.py --check` (sau khi sinh lại) | khớp | `openapi_check.txt` |
| `check_docs.py` | pass | `check_docs.txt` |
| `eval/run_agent_eval.py --offline` | pass | `eval_agent_offline.txt` |
| Frontend (`npm ci`, `gen:api`, `lint`, `typecheck`, `test`, `build`) — OpenAPI đổi | pass, 28 test | `npm ci` / `gen:api` chạy trực tiếp (không ghi file log), `web_lint.txt`, `web_typecheck.txt`, `web_test.txt`, `web_build.txt` |

Đổi API (chỉ thêm, ADR-009): enum `EventType.hard_limit_violated`, trường tuỳ chọn `GuardSettings.after_apply_failsafe`
(mặc định false). `frontend/openapi.json` + `frontend/src/lib/api/schema.d.ts` sinh lại. Bảng nhãn sự kiện của trang
vận hành là `Partial<Record<EventType,…>>` ⇒ không cần sửa UI. Không đổi schema DB.

## 7. ESCALATION

1. **Bật fail-safe sau khi áp là quyết định của chủ dự án.** Luật bất biến 1 của brief (cơ chế mới opt-in) ⇒ code và
   `config/station.yaml` để `after_apply_failsafe: false`. Bằng chứng để quyết: benchmark 100 run với cờ bật = 0
   problems so baseline (KPI trùng baseline; `power_limit_violations` của baseline là 0). Đề xuất: bật ở deploy.
2. **Ruff trên toàn `scripts/`** báo lỗi có sẵn ở các script logging hook (`log_antigravity.py`, `log_hook.py`,
   `log_manual.py`, `submit_log.py`) và format của `check_docs.py` — nhánh này không chạm (`git diff 7294803 -- scripts`
   rỗng), CLAUDE.md cấm can thiệp hook. Cổng chạy trên `src tests scripts/refactor` như `phase4-final/ruff.txt`.
3. **Cổng golden**: thư mục output Phase 0 dùng ở `phase4-final/kpi_gate.txt` (DecisionTrace / replay / events mvp1
   "vs phase0") không còn trong repo. Đã so output mới với MỌI file evidence 2026-11-22 (6 cặp) + `test_golden_regression`
   trong `pytest src/simulator/tests`; các cặp "tự so" trong `kpi_gate.txt` chỉ kiểm cấu trúc chạy, không phải bằng chứng.
4. **Kênh leakage còn lại** (4.3): `Candidate.allowed_kw` tính từ SOC thật (acceptance EVSE / BMS, Physical Guard cần).
   Không đổi để giữ hành vi; MVP-3.5 cần acceptance quan sát được cho optimizer tách khỏi acceptance vật lý của Guard.
5. **Booking**: (a) `change()` mới chỉ tăng `booking_version` dưới khoá, chưa dùng vòng kiểm lại như `book` (brief chỉ
   giao `book`) — một `change` đồng thời với `book` vẫn có thể tính trên trạng thái cũ; đề xuất dùng cùng vòng.
   (b) Khoá trong process: đúng với "một worker"; nếu chạy nhiều worker cần ràng buộc DB (partial unique index booking
   hiệu lực theo `resident_id`, qua Alembic).
6. **Sự kiện bị bỏ ở đường đọc**: `quote`, `session_view`, `queue_status`, `book` gọi `rt.sync_clock()` và bỏ sự kiện trạm
   trả về (có sẵn từ trước, với mọi loại sự kiện). Với fail-safe: vi phạm còn kéo dài thì phút sau phát lại, nên chỉ trễ.
   Đề xuất: đường đọc đẩy sự kiện qua `event_bus` thay vì bỏ.
7. **`HybridSimulator.fork()`** (offline không dùng) chia sẻ list ghi `events` / `frames` / `trace` qua `copy.copy` —
   có sẵn, ngoài phạm vi; test fork dùng `StationKernel` trực tiếp.
8. **Xung đột khi gộp với nhánh A** có thể ở `HybridStation.__init__` / `fork()` (A thêm DC model / vehicle-profile
   provider) và `runtime.fork_runtime` / `make_scheduler` (A tra policy qua registry). Ý định của nhánh B ở đó: tham số
   `observation_model`; fork dùng `fork.kernel.algorithms`; provider có trạng thái của A phải có `fork()` hoặc chấp
   nhận deep copy (không nằm trong `isolation.STATELESS`).

## 8. Đề xuất sửa tài liệu (điều phối cập nhật khi gộp)

- `CLAUDE.md` — Current Invariants:
  - "Optimizer chỉ nhận trạng thái ước lượng: `StationKernel._view` → `observation_model` (mặc định `PerfectObservation`);
    vật lý / KPI đọc ground truth (`src/models/scheduling/observations.py`)";
  - "Fork chỉ dùng chung thành phần khai báo stateless (`src/simulator/core/isolation.py`); thành phần có trạng thái
    phải có `fork()`";
  - "Booking: admission ngoài khoá, commit dưới `rt.booking_lock` + `booking_version`";
  - "`guard.after_apply_failsafe`: vi phạm cứng sau áp → `hard_limit_violated` → giảm tải qua dispatcher".
- `docs/adr/ADR-019`: thêm mục "Final Review 2026-11-24 (nhánh B)" gồm 4 điểm trên; `ADR-002`: fail-safe sau áp vẫn đi
  dispatcher (chokepoint giữ nguyên); `ADR-017`: `curtail_to_hard_limits` dùng `check_site_allocation`.
- `FINAL_MAP.md` §3 / §4: `fork_runtime` dùng thuật toán đã cô lập của bản fork; thành phần mới phải khai báo stateless
  hoặc có `fork()`; `EventType` có thêm `hard_limit_violated`.
- `REFACTOR_REPORT.md` §4 số test (536 / 174), §8 giới hạn: bỏ "chưa phân biệt ground truth / observed" (đã có điểm cắm,
  chưa có mô hình nhiễu), thêm ESCALATION 4–6.
