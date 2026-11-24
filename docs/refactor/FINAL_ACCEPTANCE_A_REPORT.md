# FINAL_ACCEPTANCE_A_REPORT — nhánh `feature/unified-core-accept-a` (claude2)

> Brief: `docs/refactor/tasks/FINAL_ACCEPTANCE_PATCH_BRIEF.md`, nhánh A: §3 P1 config parity + provenance, §4 P2 xoá
> hardcode + hoàn thiện isolation. Luật bất biến và cổng kiểm theo `docs/refactor/tasks/FINAL_REVIEW_FIX_BRIEF.md`.
> Gốc nhánh `6d99661`. Log cổng kiểm: `docs/refactor/raw/final-acceptance-a/`.
> Không push / merge / rebase. Không sửa `CLAUDE.md`, ADR, `FINAL_MAP`, `README`, `PROJECT_STATE.md` (đề xuất ở §6).

## 1. Tóm tắt

| Mục | Commit | Kết quả |
|---|---|---|
| §3.1 `build_sim_runtime` truyền tham số như live | `0d3ec8c` | `policy_parameters(config, policy)` dùng đúng quy tắc của `live_policy`; tham số tường minh `parameters=` |
| §3.2 Resolved experiment configuration | `6c2fb6a` | `ResolvedExperiment` + `src/services/experiment.py` (fingerprint sha256 ổn định) |
| §3.3 Ghi vào run / report / manifest | `6c2fb6a` | `SimulationRunResult.experiment`, `BenchmarkSource.experiments`, `eval/results/manifest.json` |
| §3.4 Test parity tham số khác mặc định | `e37e0a9` | live = benchmark từng phút; admission = thực thi thật; mặc định cho lịch khác |
| §3.5 KPI lấy mẫu ≠ vi phạm cứng kernel | `249ec14` | `SimulationRunResult.violations` (hai trường tên rõ) |
| §4.1 S8 lấy policy từ API | `1d9f3a7` | dropdown đọc `GET /simulation/policies`, gửi `policy_id`; `policy_id ?? strategy` |
| §4.2 `HybridSimulator.fork()` | `bd00c9a` | bản fork có bản ghi riêng (events / frames / trace / decision trace / latency / applied) |
| §4.3 Fallback DC model + closure | `540d458` | fallback có trạng thái được cô lập; `fork_component` từ chối closure / hàm có trạng thái |
| §4.4 Baseline đóng băng | — | B0 / M2b / M3a / M3b không đổi (AST 114/0, golden 0 unexpected, benchmark 0 problems) |

So với baseline: **0 chênh lệch**, chỉ khác latency.
- Benchmark 100 / 100 run, 0 problems so `eval/evidence/2026-11-24-unified-core-final-baseline/`.
- Golden simulator: 0 unexpected.
- AST: 114 compared, 0 undeclared.

Test: `tests` 578 passed / 8 skipped (trước: 569 / 8). `src/simulator/tests` 180 passed (trước: 174). Frontend 30 test
(trước: 28). Không assertion cũ nào bị đổi: `git diff --numstat 6d99661 HEAD -- tests src/simulator/tests` chỉ có dòng
thêm (`test_config_parity.py` mới, `test_fork_isolation.py` +137 / −0).

## 2. §3 Config parity + experiment provenance

### §3.1 — `build_sim_runtime` (`0d3ec8c`, `e37e0a9`)

- **Trước:** `build_sim_runtime` gọi `make_scheduler(strategy, …)` không có tham số. Nếu `planning.parameters` khác
  mặc định, live chạy một thuật toán còn benchmark / `POST /simulation/runs` chạy thuật toán khác.
- **Sau** (`src/services/runtime.py`):
  - `policy_parameters(config, strategy)`: `planning.parameters` gắn với policy mà runtime live chạy (`live_policy`:
    `planning.policy_id`, không thì env `LIVE_STRATEGY`). Đúng docstring đã có của `PlanningPolicyConfig` ("Chỉ áp cho
    policy live").
    - Benchmark / admission chạy ĐÚNG policy đó nhận ĐÚNG tham số đó.
    - Policy khác chạy tham số mặc định của registry. Lý do: tham số theo thành phần (vd. `optimizer_dc.horizon_minutes`
      của `rolling_lp`) không áp được cho thành phần khác loại (`equal_share` của B0 sẽ lỗi `Unsupported parameters`).
  - `build_sim_runtime(…, parameters=None)`: `None` = như live; dict = tường minh (thí nghiệm), `{}` = mặc định registry.
  - `live_scheduler(config, station)`: `get_runtime` và test parity dựng scheduler live qua cùng một hàm.
  - Admission: `fork_runtime` vốn đã mang `parameters` của scheduler live, giờ có thêm test.
- `config/station.yaml` hiện không có khối `planning:` ⇒ `parameters` rỗng ⇒ benchmark baseline không đổi.

### §3.2 / §3.3 — Resolved experiment configuration (`6c2fb6a`)

- **`src/models/simulation.py`** (chỉ thêm): `ResolvedComponent`, `ResolvedExperiment` gồm:
  - `policy_id`, `policy_version`;
  - `components`: `dispatch.AC` / `dispatch.DC` / `optimizers.AC` / `optimizers.DC` / `coordinator` / `physical_guard`,
    mỗi mục có name, version, implementation và tham số ĐẦY ĐỦ sau mặc định;
  - `dc_charging_model` (name + version + tham số);
  - `parameters` đã cung cấp, `time_config` (TimeConfig của trạm);
  - `station_config_sha256`, `tariff_sha256`;
  - `fingerprint` = sha256 của JSON chuẩn hoá (khoá sắp xếp) mọi trường trên; có `schema_version`.
- **`src/services/experiment.py`**: `resolve_experiment(rt)` dựng từ metadata mà `resolve_algorithms` trả cho scheduler
  (không chép tay), nên áp được cho live, benchmark và fork admission.
  - `fork_runtime` chép metadata của scheduler live sang bản fork (cùng thành phần đã resolve).
  - `try_resolve_experiment` trả None cho scheduler không phải policy registry (scheduler giả trong test).
- **Ghi lại (trường mới, tuỳ chọn)**:
  - mỗi `SimulationRunResult.experiment`;
  - `BenchmarkSource.experiments` (policy → cấu hình). Nếu các run cùng policy lệch fingerprint thì thêm note;
  - `eval/run_benchmark.py` ghi thêm `RESULTS_DIR/manifest.json`: manifest nháp cùng khoá với manifest baseline, cộng
    `experiments`, `experiment_fingerprints`, `benchmark_sha256`, `command`.
  - `latest_benchmark` đọc khoá `experiments` của manifest baseline nếu có. Baseline 2026-11-24 không có ⇒ rỗng;
    evidence cũ không sửa.
- **Fingerprint của lần benchmark 100 run** (`raw/final-acceptance-a/benchmark_experiment_fingerprints.txt`): mỗi policy
  một fingerprint duy nhất qua 25 run, không có note lệch.

### §3.4 — Test parity (`tests/test_services/test_config_parity.py`, 9 test cho cả §3)

- `test_non_default_parameters_give_the_same_results_in_live_benchmark_and_admission`: M3a với
  `optimizer_ac.block_minutes = 30`, `optimizer_dc.horizon_minutes = 30`.
  - Runtime dựng như `get_runtime` (`make_station` + `live_scheduler`) và `build_sim_runtime` có cùng fingerprint.
  - Cả hai cho công suất từng cổng TỪNG PHÚT giống hệt trong 240'.
  - Đối chứng: cùng kịch bản với tham số mặc định cho lịch khác (105 / 240 phút khác) ⇒ phép so không tầm thường.
  - Admission: `evaluate` trên bản fork của runtime live = chạy tiếp CHÍNH runtime đó với cùng xe tới deadline. Trùng
    cổng, lúc cắm, bắt đầu, kết thúc, kWh giao (≤ 1e-9) và chi phí. Fingerprint của bản fork = của live.
- Kiểm đột biến thủ công: bỏ truyền `parameters` trong `build_sim_runtime` ⇒ 5 test đỏ.
- Các test khác:
  - `test_benchmark_runtime_gets_the_live_parameters`;
  - `test_other_policies_keep_registry_defaults_and_explicit_parameters_win`;
  - `test_admission_fork_keeps_the_parameters`;
  - `test_resolved_experiment_is_explicit_and_stable`: ổn định qua seed / thời điểm, băm lại từ JSON ra cùng giá trị.
    Đổi tham số / policy / DC model ⇒ 4 fingerprint khác nhau;
  - `test_benchmark_report_and_manifest_carry_the_experiment`;
  - `test_old_baseline_without_experiments_still_loads`.

### §3.5 — Hai loại vượt giới hạn (`249ec14`)

- `ViolationCounts` (trường tuỳ chọn `SimulationRunResult.violations`):
  - `sampled_power_over_limit_minutes`: số phút tổng công suất lấy mẫu cuối phút (đầu ra / η) vượt giới hạn nguồn.
    Bằng KPI `power_limit_violations` (MT4), giữ nguyên định nghĩa và giá trị;
  - `applied_constraint_violation_count`: số lần Physical Guard của kernel phát hiện vi phạm trần cứng sau khi áp;
  - `rejected_allocation_count`: đề xuất bị Physical Guard từ chối trước khi áp (không phải vi phạm).
- Không thêm khoá vào `kpis`, vì `compare_backend_benchmark.py` so mọi khoá KPI. Chỉ sửa mô tả của
  `power_limit_violations` cho rõ nghĩa (không đổi giá trị / ngữ nghĩa).
- `benchmark.md` có thêm cột "Vi phạm cứng (kernel)".
- Test:
  - `test_run_reports_sampled_and_hard_violations_separately`;
  - `test_hard_violation_counter_comes_from_the_kernel_not_from_samples`: nguồn tụt im lặng trong một bước rồi hồi lại
    trước lần lấy mẫu ⇒ mẫu = 0, kernel ≥ 1.
- Benchmark 100 run: mọi run có `sampled = 0`, `applied = 0`.

## 3. §4 Xoá hardcode + hoàn thiện isolation

### §4.1 — Frontend S8 (`1d9f3a7`)

- `frontend/src/lib/policies.ts`:
  - `policyOptions`, `policyLabel`: `id · mô tả`, kèm version nếu khác "1", "thử nghiệm" nếu không đóng băng, "(mặc định)"
    cho M3a;
  - `selectedPolicy`: lựa chọn còn hợp lệ, không thì M3a, không thì policy đầu tiên;
  - `policyOf = policy_id ?? strategy`.
- `queries.policies()` → `GET /api/v1/simulation/policies`.
- `operator/simulation/page.tsx`:
  - bỏ bảng `STRATEGIES` cứng; dropdown dựng từ API;
  - `POST /simulation/runs` gửi `policy_id` (không gửi `strategy`);
  - tiêu đề cột bảng đối chứng dùng `policy_id ?? strategy`;
  - lỗi tải danh sách policy hiện `ErrorPanel`.
- `operator/schedule/page.tsx`: nhãn lịch dùng `policyOf(plan)` (trước là `plan.strategy`, sẽ là `None` với policy mới).
- Test `frontend/src/test/simulation-policies.test.tsx`:
  - render S8 với API giả có policy mới `T41-edf` ⇒ dropdown có đủ 3 policy, mặc định M3a;
  - chọn policy mới ⇒ body POST có `policy_id: "T41-edf"`, không có `strategy`;
  - helper được kiểm riêng.

### §4.2 — `HybridSimulator.fork()` (`bd00c9a`)

- **Trước:** `fork()` thừa kế `StationKernel.fork` (`copy.copy`), nên bản fork dùng chung list `events` / `frames` /
  `trace` / `decision_trace` / `decision_latency_ms` / `applied_results` với bản gốc. `emit` của bản fork ghi thẳng vào
  `events` của bản gốc.
- **Sau:** `HybridSimulator.fork()` gọi `super().fork()` (giữ quy tắc isolation), rồi tách bản ghi:
  - deep copy các bản ghi dict / list;
  - `applied_results` chỉ chép list, vì `AppliedResult` frozen với mapping chỉ đọc (MappingProxyType không deep copy được).
- Test `src/simulator/tests/test_fork_isolation.py`:
  - `test_hybrid_simulator_fork_does_not_share_recordings`:
    - bản fork bắt đầu đúng lịch sử của bản gốc;
    - đột biến sâu và chạy bản fork tới hết ⇒ bản gốc không đổi;
    - bản gốc chạy tiếp ⇒ bản fork khác không đổi.
  - `test_hybrid_simulator_fork_runs_like_the_original`: `fork().run()` = `run()`.
  - Kiểm đột biến: bỏ override ⇒ test đỏ.

### §4.3 — Fallback DC model có trạng thái + từ chối closure (`540d458`)

- **`src/simulator/core/isolation.py`**:
  - `NESTED = {VehicleProfilesDCModel: ("fallback",)}`: container khai báo stateless chỉ được dùng chung khi thành phần nó
    giữ cũng dùng chung được.
    - Fallback mặc định `SyntheticTaperV1` ⇒ như cũ.
    - Fallback có trạng thái ⇒ dựng lại bằng `dataclasses.replace` quanh bản fork của fallback. Deep copy không dùng được
      vì `profiles` là MappingProxyType.
  - `StatefulComponentError(TypeError)`: `fork_component` từ chối hàm chưa khai báo có trạng thái thấy được (closure,
    tham số mặc định mutable, thuộc tính gán lên hàm). Thông báo nêu tên hàm, lý do và cách sửa (`fork()` hoặc
    `__stateless__ = True`).
  - Hàm thuần không có dấu hiệu trạng thái: giữ nguyên như trước (deep copy vốn trả lại chính nó).
  - Hàm gán `__stateless__ = True`: dùng chung.
- **`live_profiles.DynamicVehicleProfilesDCModel.fork(memo=None)`**:
  - `fallback` đi qua `fork_component`: trước đây luôn dùng chung, kể cả khi có trạng thái;
  - `__deepcopy__` truyền `memo`.
- Test (thêm cuối `test_fork_isolation.py`):
  - `test_stateful_fallback_of_the_profile_model_is_isolated`: kernel thật, 30' trên bản fork, fallback live không bị gọi;
  - `test_stateful_fallback_of_the_live_provider_is_isolated`;
  - `test_stateful_closure_is_refused_with_a_clear_error`: closure, mutable default, thuộc tính hàm; `kernel.fork()` lỗi rõ;
  - `test_declared_or_plain_functions_are_still_shared`.
  - Kiểm đột biến: tắt `NESTED` ⇒ test đỏ.

## 4. Cổng kiểm (`docs/refactor/raw/final-acceptance-a/`)

| Cổng | Kết quả | Log |
|---|---|---|
| `ruff check` + `ruff format --check` (`src tests scripts/refactor eval`) | pass (258 file) | `ruff.txt` |
| `pytest tests -q` | **578 passed, 8 skipped** (trước 569 / 8) | `pytest_tests.txt`, `pytest_tests_before.txt` |
| `pytest src/simulator/tests -q` | **180 passed** (trước 174) | `pytest_simulator.txt` |
| AST `compare_ast_manifest.py … -- src` | **114 compared, 0 undeclared, 0 declared**, exit 0 | `ast_gate.txt` |
| Golden (`run_sim_kpi_gate.py run` + `compare --evidence eval/evidence/2026-11-22/raw/sim-hardware --module-map phase4-final/module_map.txt`) | **6 / 6 cặp evidence 0 unexpected**. Số allowed trùng các lần trước: MVP1 9, mvp3cfg 13, DecisionTrace 0, VinFast 10, MVP2 0, MVP3 20 | `sim_run.txt`, `kpi_gate.txt` |
| `eval/run_benchmark.py --seeds 1,2,3,4,5` + `compare_backend_benchmark.py` vs baseline final | **OK — 100 / 100 run, 0 problems** | `eval_run_benchmark.txt`, `benchmark_compare.txt` |
| `export_openapi.py --check` (đã sinh lại ở `6c2fb6a`, `249ec14`) | khớp | `openapi_check.txt` |
| `check_docs.py` | pass | `check_docs.txt` |
| `eval/run_agent_eval.py --offline` | pass | `eval_agent_offline.txt` |
| Frontend `npm ci`, `gen:api`, `lint`, `typecheck`, `test`, `build` | pass, 30 test | `web_checks.txt` |

Không commit gì trong `eval/results/`: `benchmark.json` / `.md` / `manifest.json`, output golden `final-acceptance-a-sim/`,
và script dò tham số `tmp-accept-a/`.

## 5. ESCALATION

1. **Quy tắc tham số cho policy không phải policy live (§3.1).** Benchmark / API chạy policy khác policy live ⇒ tham số
   mặc định của registry, không lấy `planning.parameters`.
   - Lý do: tham số theo thành phần không áp được cho thành phần khác loại, và docstring `PlanningPolicyConfig` đã ghi
     "Chỉ áp cho policy live".
   - Hệ quả: khi `planning.policy_id` không khai, policy live (và tham số của nó) phụ thuộc env `LIVE_STRATEGY`, như
     runtime live. Cấu hình đã resolve của mỗi run được ghi tường minh ở `experiment` nên luôn truy được.
   - Nếu chủ dự án muốn tham số theo policy (vd. `planning.parameters_by_policy`), cần thêm khoá cấu hình mới. Chưa làm
     vì ngoài brief.
2. **Golden "vs bản gốc".** Worktree không có output simulator của commit gốc (ESCALATION 2 / 3 của hai báo cáo trước).
   - Cổng so output mới với evidence 2026-11-22 (6 cặp, đúng bằng chứng), còn cặp "tự so" chỉ kiểm cấu trúc chạy.
   - `compare` cần `--module-map docs/refactor/raw/phase4-final/module_map.txt`. Thiếu cờ này thì chỉ trường
     `implementation` (đường module đã chuyển ở Phase 4) bị báo lệch.
3. **`ruff` toàn `scripts/`** vẫn có lỗi sẵn ở hook ghi log AI. Không chạm (CLAUDE.md), cổng chạy như các lần trước.
4. **Phát hiện hàm có trạng thái (§4.3) là heuristic.** Trạng thái giấu trong biến toàn cục của module không phát hiện
   được (ghi trong docstring `isolation.py`). Closure hợp lệ (bất biến) phải khai báo `__stateless__ = True`.
   Thành phần đã đăng ký hiện có đều là hàm thuần / class khai báo ⇒ không đổi hành vi (golden + benchmark 0 lệch).
5. **`live_profiles.py`** (provider của Final Review 4.2, nhánh này viết) có sửa `fork()`: chỉ thêm cô lập `fallback`, không
   sửa vật lý. Các class model sạc gốc (`synthetic_dc.py`, `vehicle_profiles.py`, manifest AST) không đổi.
6. **Kênh phụ thuộc nhánh B.** `fork_runtime` (sửa ở §3.2: chép `metadata`) cũng là điểm nhánh B có thể chạm (§2 admission
   consistency). Khi gộp: giữ dòng `scheduler.metadata = …` sau `make_scheduler`.
7. Không có test cũ nào phải đổi assertion. Không thêm dependency. Không đổi schema DB. Không có tài liệu chung nào bị sửa.

## 6. Đề xuất sửa tài liệu (điều phối làm khi gộp)

- **`CLAUDE.md`** (Quick Rehydrate / Current Invariants):
  - "`planning.parameters` chỉ áp cho policy live; benchmark / admission chạy đúng policy đó nhận đúng tham số
    (`runtime.policy_parameters`)";
  - "mỗi run benchmark ghi `experiment` (cấu hình đã resolve + fingerprint, `src/services/experiment.py`);
    `eval/results/manifest.json` là manifest nháp";
  - "MT4 `power_limit_violations` = phút vượt lấy mẫu; vi phạm cứng của kernel ở `violations.applied_constraint_violation_count`".
- **`FINAL_MAP.md`**:
  - §3: S8 đọc policy từ `GET /simulation/policies` (không còn danh sách cứng ở frontend);
  - §4: `isolation.NESTED`, `StatefulComponentError`, `HybridSimulator.fork` tách bản ghi.
- **ADR-019**, mục bổ sung Final Acceptance:
  - resolved experiment / fingerprint là điều kiện so hai bảng benchmark;
  - quy tắc fork: closure có trạng thái bị từ chối; container stateless chỉ dùng chung khi thành phần lồng cũng stateless.
- **Quy trình baseline**: thư mục baseline mới chép thêm `manifest.json` nháp do `run_benchmark.py` sinh (có
  `experiments`), rồi điền `baseline_id` / `version` / `status`.
- **`REFACTOR_REPORT.md`**: số test (578 / 180 / web 30). Bỏ giới hạn "`HybridSimulator.fork()` chia sẻ list ghi"
  (ESCALATION 7 của báo cáo B Final Review) vì đã xử lý ở §4.2.
