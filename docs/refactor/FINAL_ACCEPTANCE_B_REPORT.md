# FINAL_ACCEPTANCE_B_REPORT — nhánh `feature/unified-core-accept-b` (claude3)

> Brief: `docs/refactor/tasks/FINAL_ACCEPTANCE_PATCH_BRIEF.md` (nhánh B: §1 P0 Safety event delivery, §2 P1 Admission
> consistency). Gốc nhánh: `6d99661`. Log cổng kiểm: `docs/refactor/raw/final-acceptance-b/`.
> Không push / merge / rebase. Không sửa `CLAUDE.md`, ADR, `FINAL_MAP`, `README`, `PROJECT_STATE.md` (đề xuất ở §6).

## 1. Tóm tắt

| Mục | Commit | Kết quả |
|---|---|---|
| §1.1 Bật `guard.after_apply_failsafe: true` trong `config/station.yaml` | `a6695ea` | ngoại lệ được duyệt; thiếu khoá vẫn = tắt (`GuardSettings`) |
| §1.3 + §1.4 (trạm / kernel) Phân loại vi phạm cứng, dừng catch-up ở phút vi phạm | `674123c` | `HardViolation` + `ViolationKind`, sự kiện có loại + xe |
| §1.2 + §1.4 + §1.5 (runtime / control_loop) Giao sự kiện của mọi consumer, fail-safe theo loại | `7e7733f` | outbox + `deliver_pending`; fail-safe trước khi tiến đồng hồ |
| §2 Admission consistency (`change` / `cancel` / fingerprint / consent) | `1981c50` | optimistic concurrency cho `change`, kiểm lại dưới khoá |
| Báo cáo + log | (commit cuối) | |

Chênh lệch so baseline: benchmark backend 100 run **0 problems** (với cờ fail-safe BẬT), golden simulator 38/38 OK,
AST 114 / 0 undeclared. Test cũ: một assertion phải đổi (ESCALATION 1).

## 2. §1 P0 — Safety event delivery

**§1.1 — Bật mặc định** (`a6695ea`). `config/station.yaml`: `after_apply_failsafe: true`. `GuardSettings` giữ
`default=False` (config không có khoá = hành vi cũ); chỉ đổi mô tả. Test cũ dựa trên `false` đã truyền tường minh
(`_charging_runtime(failsafe=False)`), riêng một assertion kiểm giá trị trong yaml phải đổi (ESCALATION 1).

**§1.2 — Một đường dùng chung, không consumer nào bỏ sự kiện** (`7e7733f`, `src/services/runtime.py`,
`src/services/control_loop.py`)
- `StationRuntime.outbox` (deque, tối đa 10 000): mọi sự kiện trạm phát sinh khi tiến đồng hồ.
- `advance_clock()` = step + đưa sự kiện vào outbox (chỉ control_loop gọi trực tiếp); `take_events()` lấy và xoá.
- `sync_clock()` (đường của MỌI consumer — `quote`, `book`, `cancel`, `change`, `session_view`, `queue_status`,
  `station_service.overview` / `connector_detail` / `manual_assign`, `simulation_service.inject_incident`, …) =
  `advance_clock()` + `request_delivery()`: lên lịch `control_loop.deliver_pending(rt)` trên vòng sự kiện của runtime
  (`create_task` nếu đang ở đúng vòng; `run_coroutine_threadsafe` nếu gọi từ threadpool của router đồng bộ). Chưa biết
  vòng sự kiện ⇒ outbox chờ lần `on_event` / `run_forever` kế tiếp. Giá trị trả về giữ cho tương thích.
- `rt.loop` ghi ở `get_runtime()` (nếu đang trong vòng) và ở `on_event` / `run_forever`; `rt.deliver` chỉ đặt cho runtime
  live (benchmark / admission giữ như cũ: đồng hồ = đồng hồ trạm, không có sự kiện từ `sync_clock`).
- `on_event` lấy outbox vào lô (bỏ trùng theo `event_id` với sự kiện / lô truyền vào — người gọi tự giao như
  `test_flows` không bị ghi hai lần); `run_forever` dùng `advance_clock` + `take_events`; `resolve_approval` để sự kiện
  ở outbox cho `on_event(REPLAN_REQUESTED)` ngay sau đó.
- Sự kiện của `upsert_vehicle` / `remove_vehicle` trong `book` / `change` / `cancel` (trước đây cũng bị bỏ) vào outbox.

**§1.3 — Catch-up dừng ở phút vi phạm** (`674123c`, `src/simulator/hybrid_station.py`)
- Cờ bật: `HybridStation.step(n)` dừng ngay sau phút có vi phạm cứng MỚI, trả `HARD_LIMIT_VIOLATED`; các phút còn lại
  chưa tích phân — lần `sync_clock` sau chạy tiếp.
- `on_event`: vi phạm đã báo (sự kiện / lô / outbox) ⇒ `_failsafe` chạy TRƯỚC `advance_clock`; vi phạm phát sinh trong
  lần tiến đồng hồ đó ⇒ `_failsafe` lần nữa. Lệnh fail-safe dùng thời điểm của TRẠM (`state.timestamp`) cho lệnh +
  `GuardContext.now` — trạm đang dừng ở phút vi phạm, lệnh không bị `stale_state` coi là cũ so với đồng hồ runtime
  (benchmark: hai thời điểm trùng nhau ⇒ không đổi).
- Chống treo đồng hồ: vi phạm Y HỆT (loại + xe + thông điệp) với vi phạm đã dừng ở phút liền trước (fail-safe đã có
  một lượt mà không sửa được) ⇒ không dừng lại, vẫn phát sự kiện mỗi lần step. Cờ tắt ⇒ hành vi cũ (chỉ đếm + log).

**§1.4 — Hai loại vi phạm** (`674123c` + `7e7733f`)
- `src/models/decisions.py` (thuần stdlib, chỉ thêm): `HardViolationKind` (`aggregate_power` / `charging_model` /
  `acceptance`), `HardViolation(kind, message, vehicle_ids)`, trường tuỳ chọn `AppliedResult.hard_violations` (cùng thứ
  tự với `violations`). `src/models/events.py`: `ViolationKind` + trường tuỳ chọn `StationEvent.violation_kinds`,
  `violation_booking_ids` (API chỉ thêm).
- `StationKernel.advance` (non-strict và strict đều ghi; strict vẫn raise như cũ): `validate_response` lỗi ⇒
  `charging_model` của xe đó; `candidates()` lỗi ⇒ `acceptance` (xe lỗi tìm bằng thử `acceptance_kw` từng xe — chỉ ở
  đường lỗi non-strict); Physical Guard sau thực thi: cổng ngoài [0, allowed] ⇒ `charging_model`, còn lại (tủ / vùng /
  lưới) ⇒ `aggregate_power`. Không đổi logic tích phân / kiểm tra.
- `control_loop._failsafe`: `aggregate_power` (hoặc chưa phân loại) ⇒ `curtail_to_hard_limits` như cũ;
  `charging_model` / `acceptance` ⇒ `guard.emergency.stop_faulty_vehicles` (SET_POWER 0 nguồn EMERGENCY đúng cổng xe
  lỗi, qua dispatcher) + `rt.safety_hold_booking_ids` (`_filter_held` bỏ mọi lệnh không phải ngắt cho booking đó) + log
  ERROR "cần vận hành kiểm tra"; không co các xe khác. Sự kiện (có loại) tới WebSocket vận hành và DecisionTrace.
- `HybridStation._connector_state`: acceptance lỗi ⇒ cổng hiển thị `FAULT`, 0 kW (Guard không cấp điện cho cổng FAULT)
  thay vì làm hỏng `state()` của cả trạm. Đường bình thường không đổi.
- DecisionTrace: trace mở có `safety.hard_limit_violations` (event_id, kinds, booking_ids, detail) và
  `safety.held_booking_ids`; `applied.hard_violation_details` (phút, loại, xe, thông điệp) cạnh `applied.hard_violations`.

**§1.5 — Test** — `tests/test_services/test_safety_event_delivery.py` (13 test). Test partial-batch cũ giữ nguyên.
- đường đọc `queue_status` / `session_view` / `overview` (cùng vòng) và `queue_status` từ threadpool: nguồn tụt im lặng,
  đồng hồ nhảy 5' ⇒ trạm dừng ở phút 1, outbox có `hard_limit_violated`, sự kiện được giao ⇒ lệnh EMERGENCY executed,
  4 phút còn lại chạy SAU giảm tải, đúng 1 phút vi phạm, trạm về trong trần, sự kiện được ghi;
- `charge_completed` từ đường đọc không bị bỏ; outbox không có vòng nhận ⇒ `on_event` kế tiếp lấy, không ghi trùng;
- catch-up `step(10)` dừng ở phút 1 (1 vi phạm, loại `aggregate_power`, `occurred_at` = giờ trạm); lần sau cùng vi phạm
  không dừng nữa; cờ tắt ⇒ 10 phút / 10 vi phạm như cũ; trong `on_event` fail-safe chạy trước `advance_clock`;
- `curtail_to_hard_limits` đưa trạm về trong trần lưới / vùng / tủ (tham số hoá), co không tăng;
- lỗi charging model (adapter trả năng lượng ≠ SOC cho `dc-a`): sự kiện `charging_model` + `["dc-a"]`; giảm tải tổng trả
  `[]` (không sửa được); fail-safe ngắt đúng cổng `dc-a` (0 kW, executed), giữ an toàn, không co xe khác; 20 phút sau 0
  vi phạm, `dc-a` vẫn 0 kW; trace có `safety` + `hard_violation_details`.

## 3. §2 P1 — Admission consistency (`1981c50`, `src/services/charging_service.py`, `src/services/runtime.py`)

1. **`change` = optimistic concurrency như `book`**: tối đa `BOOKING_COMMIT_ATTEMPTS = 3` lượt: `sync_clock` → chụp
   `rt.admission_fingerprint()` → đọc lại booking + dựng request mới → admission NGOÀI khoá → dưới `rt.booking_lock` kiểm
   lại booking + fingerprint; đổi ⇒ chạy lại; hết lượt ⇒ `PROPOSAL_EXPIRED`. Bản ghi mới dựng từ booking đọc lại dưới
   khoá.
2. **Kiểm lại trạng thái dưới khoá**: `change` — booking đã huỷ / kết thúc ⇒ `BOOKING_CONFLICT`, không ghi đè ("sống
   lại"), không đưa xe lại vào trạm; `cancel` — đọc lại dưới khoá ⇒ hai lần huỷ đồng thời: một lần đổi trạng thái + một
   `BOOKING_CANCELLED`, lần kia `BOOKING_CONFLICT`.
3. **`admission_fingerprint()`** = (`booking_version`, giới hạn nguồn hiện hành, đầu nối FAULT, policy, booking bị từ
   chối duyệt, booking giữ an toàn). `book` dùng fingerprint thay cho chỉ `booking_version` (cùng ngữ nghĩa + nguồn /
   cổng). Không gồm phút trôi / xe cắm-rút theo lịch và phê duyệt đang chờ (lý do ở docstring; ESCALATION 5).
4. **Consent**: `book` như trước (consent sẽ lưu); `change` chạy admission trên `booking.consent` thật (trước: consent
   mặc định). `quote` giữ consent mặc định (hành vi cũ) nhưng thêm một dòng vào `ScheduleProposal.assumptions` ghi rõ
   consent đã giả định (lùi giờ / giảm công suất / giảm tải khẩn cấp) và "kết quả được tính lại với consent thật".
   `_what_if(..., assume_consent=False)` mặc định ⇒ gọi trực tiếp không đổi (test cũ `assumptions == ASSUMPTIONS` giữ).
5. **Test** — `tests/test_services/test_admission_consistency.py` (10 test): `change` đua `book` (barrier) ⇒ 3 lượt
   admission, cả hai thành công, admission không chạy dưới khoá; `change` hết lượt ⇒ `PROPOSAL_EXPIRED`, booking cũ
   giữ; huỷ trong lúc `change` tính ⇒ `BOOKING_CONFLICT`, vẫn CANCELLED, không có `BOOKING_CHANGED`, xe không trở lại;
   hai `cancel` đồng thời ⇒ 1 đổi + 1 sự kiện + `booking_version` +1; nguồn giảm / đầu nối lỗi trong lúc admission của
   `book` ⇒ chạy lại trên trạng thái mới (thấy 80 kW / không gán cổng lỗi); nguồn tụt làm hết khả thi ⇒
   `PROPOSAL_EXPIRED`, không booking; `change` khi nguồn đổi ⇒ chạy lại; `change` chạy trên consent thật; `quote` có
   giả định consent. Kiểm đột biến (bỏ kiểm fingerprint / bỏ nguồn + cổng khỏi fingerprint / bỏ đọc lại trong `cancel`)
   ⇒ test fail: `raw/final-acceptance-b/mutation_checks.txt`.
6. **Không giữ khoá suốt rollout**; giới hạn một worker ghi ở docstring `admission_fingerprint` + `change`.

## 4. Cổng kiểm (`docs/refactor/raw/final-acceptance-b/`)

| Kiểm | Kết quả | Log |
|---|---|---|
| `ruff check` + `ruff format --check` `src tests scripts/refactor` | pass (221 file) | `ruff.txt` |
| `pytest tests -q` | **592 passed, 8 skipped** (trước: 569) | `pytest_tests.txt`, `pytest_tests_before.txt` |
| `pytest src/simulator/tests -q` | **174 passed** (như trước) | `pytest_simulator.txt` |
| AST gate | **114 compared, 0 undeclared, 0 declared** | `ast_gate.txt` |
| Golden simulator (`run_sim_kpi_gate.py run` + `compare --module-map phase4-final/module_map.txt --evidence eval/evidence/2026-11-22/raw/sim-hardware`) | **38/38 OK** | `sim_run.txt`, `kpi_gate.txt` |
| Benchmark backend `--seeds 1,2,3,4,5` + `compare_backend_benchmark.py` vs `2026-11-24-unified-core-final-baseline` (cờ fail-safe BẬT) | **100/100 run, 0 problems** | `eval_run_benchmark.txt`, `benchmark_compare.txt` |
| `export_openapi.py --check` (sau khi sinh lại) | khớp | `openapi_check.txt` |
| `check_docs.py` | pass | `check_docs.txt` |
| `eval/run_agent_eval.py --offline` | pass | `eval_agent_offline.txt` |
| Frontend `npm ci`, `gen:api`, `lint`, `typecheck`, `test` (28), `build` | pass | `web_checks.txt` (ghi tay từ stdout) |

Đổi API (chỉ thêm, ADR-009): `ViolationKind`, `StationEvent.violation_kinds` / `violation_booking_ids` (mặc định rỗng),
mô tả `GuardSettings.after_apply_failsafe`. `frontend/openapi.json` + `schema.d.ts` sinh lại; UI không cần sửa. Không đổi
schema DB. `eval/results/` không commit.

## 5. ESCALATION

1. **Đổi một assertion test cũ** (`tests/test_services/test_failsafe_after_apply.py::test_failsafe_is_opt_in_default_keeps_count_and_log_only`):
   `assert catalog.load_station_config().guard.after_apply_failsafe is False` mã hoá đúng giá trị mặc định mà ngoại lệ
   được duyệt §1.1 yêu cầu đổi ⇒ không thể giữ. Đổi thành `is True` + thêm `GuardSettings.model_fields[...].default is
   False` (thiếu khoá vẫn tắt). Phần còn lại của test (cờ tắt tường minh ⇒ chỉ đếm + log) giữ nguyên.
2. **Lỗi acceptance kéo cả trạm**: khi `candidates()` lỗi vì một xe, kernel bỏ MỌI ứng viên của bước đó (cả trạm 0 kW)
   chừng nào xe đó còn CHARGING — logic Physical Core có sẵn, không đổi. Fail-safe ngắt + giữ xe lỗi, nhưng acceptance
   vẫn được tính cho phiên CHARGING; planning (`propose`) cũng có thể gặp cùng lỗi. Tách xe lỗi khỏi `candidates()` /
   rút xe khỏi cổng cần đổi Physical Core hoặc thêm thao tác "ngắt cổng" — đề xuất quyết định riêng.
3. **"Đánh dấu fault" ở mức booking, chưa có thao tác vận hành gỡ**: giữ an toàn = `rt.safety_hold_booking_ids` (RAM,
   hết khi booking kết thúc / runtime dựng lại) + cổng hiển thị FAULT khi acceptance lỗi. Không gọi `kernel.fault_port`
   từ control loop (đó là sự cố môi trường, không phải lệnh qua dispatcher — ADR-002). Cần endpoint vận hành để gỡ giữ /
   đánh dấu đầu nối lỗi.
4. **Giao sự kiện từ đường đọc là bất đồng bộ**: response của `quote` / `session_view` / … không chờ fail-safe (đã lên
   lịch trên vòng sự kiện; trạm đã dừng ở phút vi phạm nên không tích phân thêm). Trước khi có vòng sự kiện được ghi
   (`get_runtime` dựng trong threadpool, vòng nền tắt, chưa có `on_event` nào) sự kiện nằm ở outbox tới lần `on_event`
   / `run_forever` kế tiếp. Đề xuất: lifespan gọi `get_runtime()` trong vòng sự kiện cả khi vòng nền tắt.
5. **Phạm vi fingerprint**: không gồm phê duyệt đang chờ / được duyệt và xe cắm-rút theo lịch (đưa vào sẽ làm admission
   chạy lại liên tục trong live); phê duyệt đã được báo bằng `approvals_pending_*`. Chỉ một worker (khoá + fingerprint ở
   RAM); nhiều worker cần ràng buộc DB (partial unique index booking hiệu lực theo cư dân) / khoá phân tán — chưa làm.
6. **Thứ tự sự kiện trong lô ở live**: `on_event` ghi (outbox cũ, lô truyền vào, sự kiện mới của lần tiến đồng hồ) thay
   vì (sự kiện mới, lô). Chỉ ảnh hưởng thứ tự ghi / `trigger.batched` ở live; benchmark không có sự kiện từ đồng hồ ⇒
   không đổi (0 problems).
7. **Ruff toàn `scripts/`**: lỗi có sẵn ở script logging hook (như FINAL_REVIEW_FIX_B ESCALATION 2); nhánh này không
   chạm `scripts/`. Cổng chạy trên `src tests scripts/refactor`.
8. **Xung đột khi gộp với nhánh A** có thể ở `runtime.py` (`build_sim_runtime` / `fork_runtime` — A truyền optimizer
   parameters) và `hybrid_station.py`. Ý định nhánh B: trường mới của `StationRuntime` (outbox, loop, deliver,
   deliveries, safety_hold_booking_ids) + `admission_fingerprint`; `HybridStation.step` dừng ở phút vi phạm +
   `_violation_event`; `_connector_state` chịu lỗi acceptance.

## 6. Đề xuất sửa tài liệu (điều phối cập nhật khi gộp)

- `CLAUDE.md` — Current Invariants:
  - "`guard.after_apply_failsafe: true` trong station.yaml (thiếu khoá = tắt). Vi phạm cứng sau áp ⇒ trạm dừng catch-up ở
    phút vi phạm, phát `hard_limit_violated` (có `violation_kinds`); `aggregate_power` ⇒ co đều về trần,
    `charging_model` / `acceptance` ⇒ ngắt cổng xe lỗi + giữ an toàn + báo vận hành — luôn qua dispatcher";
  - "Mọi consumer tiến đồng hồ bằng `rt.sync_clock()`; sự kiện vào `rt.outbox` và tới control_loop (`deliver_pending` /
    `on_event` / `run_forever`) — không đường nào bỏ sự kiện";
  - Booking đồng thời: "`book` và `change` chạy admission ngoài khoá, commit dưới `booking_lock` + kiểm
    `admission_fingerprint()` (booking, nguồn, cổng lỗi, policy); `change` / `cancel` kiểm lại trạng thái dưới khoá;
    `change` dùng consent thật; `quote` ghi giả định consent".
- `docs/adr/ADR-002`: fail-safe theo loại vẫn qua dispatcher; `ADR-017`: phân biệt aggregate power vs lỗi xe;
  `ADR-019`: mục "Final Acceptance 2026-11-24 (nhánh B)" — outbox sự kiện, catch-up dừng ở vi phạm, `HardViolation`,
  fingerprint admission.
- `FINAL_MAP.md`: `StationRuntime.outbox` / `advance_clock` / `take_events` / `admission_fingerprint`;
  `control_loop.deliver_pending`; `guard.emergency.stop_faulty_vehicles`; `AppliedResult.hard_violations`.
- `PROJECT_STATE.md` / `REFACTOR_REPORT.md`: số test 592 / 174; giới hạn ESCALATION 2–5.
