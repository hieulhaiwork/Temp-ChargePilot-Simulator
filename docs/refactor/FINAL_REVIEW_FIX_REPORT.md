# FINAL_REVIEW_FIX_REPORT — Sửa các vấn đề Final Review 2026-11-24 (tổng hợp)

> Nguồn: `docs/refactor/raw/final-review/FINAL_REVIEW_2026-11-24.md` §4. Brief: `docs/refactor/tasks/FINAL_REVIEW_FIX_BRIEF.md`.
> Chi tiết từng nhánh: `FINAL_REVIEW_FIX_A_REPORT.md` (claude2), `FINAL_REVIEW_FIX_B_REPORT.md` (claude3).
> Log cổng kiểm trên cây đã gộp: `docs/refactor/raw/final-review-merged/`.

## 1. Mục review → thay đổi

| Mục | Nhánh / commit | Mặc định | Test chứng minh |
|---|---|---|---|
| 4.5 P0 lô áp một phần (lệnh giảm bị Guard chặn) | điều phối `3255aee` | luôn bật (sửa lỗi an toàn) | `tests/test_guard/test_load_reduction.py::test_increase_that_relies_on_a_reduction_blocked_by_guard_is_not_applied` |
| 4.1 Policy lấy từ registry + `GET /simulation/policies` + `planning.policy_id` | A `a2bb8eb`…`3481f2c` | B0–M3b version `"1"`, `StrategyName` giữ | `tests/test_refactor/test_policy_registry.py` |
| 4.2 DC model backend theo tên, profile VinFast cho xe đến động | A `a2bb8eb`, `e5e32b9`, `89fae6c` | `SyntheticTaperV1()` | `tests/test_refactor/test_differential.py` (cuối file) |
| 4.7 Benchmark `--strict-incidents`, đếm sự cố dự kiến / thực thi / bỏ qua | A `8e7e72d`, `4ed0b7d`, `63dfd77` | skip + note như cũ | `tests/test_services/test_strict_incidents.py` |
| 4.3 Ground truth / declared / observation / estimated | B `dcaa7ed` | `PerfectObservation` (identity) | `src/simulator/tests/test_observation_layers.py` |
| 4.4 Fork isolation (share / fork / copy) | B `dcaa7ed` | thành phần hiện có khai báo stateless | `src/simulator/tests/test_fork_isolation.py`, `tests/test_services/test_fork_isolation.py` |
| 4.5b Fail-safe sau apply → lệnh EMERGENCY qua dispatcher; negative test rejected / expired / stale | B `74700d7` | `guard.after_apply_failsafe: false` | `tests/test_services/test_failsafe_after_apply.py`, `tests/test_guard/test_partial_batch_safety.py` |
| 4.6 Booking optimistic concurrency + consent parity | B `3b25130` | luôn bật (sửa lỗi đúng đắn) | `tests/test_services/test_booking_concurrency.py` |

Gộp: `feature/unified-core-review-b` rồi `feature/unified-core-review-a` vào `feature/unified-core` (merge `79f35ef`).
Hai xung đột: `services/runtime.fork_runtime` (giữ thuật toán đã cô lập của B + `parameters` của A) và
`HybridStation.fork` (giữ cô lập DC model trong `StationKernel.fork` của B — provider profile của A có `fork()` nên được
tách qua memo chung adapter + algorithms; bỏ đoạn fork thủ công của A để không tách hai lần).

## 2. Cổng kiểm trên cây đã gộp (`raw/final-review-merged/` + lệnh chạy trực tiếp)

| Kiểm | Kết quả |
|---|---|
| `ruff check` + `format --check` (`src tests scripts/refactor eval`) | pass |
| `pytest tests` | 569 passed, 8 skipped (trước: 521 / 8) |
| `pytest src/simulator/tests` | 174 passed (trước: 163) |
| AST code được bảo toàn | 114 compared, 0 undeclared, 0 declared |
| Golden simulator (`run_sim_kpi_gate.py`, so nhánh B + evidence 2026-11-22) | 38/38 OK (`kpi_gate.txt`) |
| Benchmark backend 100 run vs baseline 2026-11-24 | 0 problems (`benchmark_compare.txt`) |
| OpenAPI `--check`, `check_docs`, eval agent offline | pass |
| Frontend lint / typecheck / test / build | pass, 28 test (`web_*.txt`) |

Không test cũ nào bị sửa assertion; không thêm dependency; không đổi schema DB; evidence cũ không đổi.

## 3. Thay đổi interface (chỉ thêm, ADR-009)

- `GET /api/v1/simulation/policies`; trường tuỳ chọn `policy_id` / `policy_version` (plan, run, request);
  `EventType.hard_limit_violated`; `GuardSettings.after_apply_failsafe`; khối `planning:` tuỳ chọn (comment) trong
  `config/station.yaml`; số đếm `incidents` trong run benchmark.
- Lưu ý tương thích: `SchedulePlan.strategy` thành tuỳ chọn (None chỉ khi policy đăng ký mới không có trong enum;
  B0–M3b vẫn luôn có giá trị). Cột `schedule_plans.strategy` (`String(8)`) ghi `custom` cho id dài hơn 8 ký tự; id đầy
  đủ nằm trong payload.

## 4. Còn lại / cần chủ dự án quyết

- `CLAUDE.md` chưa cập nhật (cần duyệt): `GET /simulation/policies`, `planning.policy_id`, `--strict-incidents`,
  `guard.after_apply_failsafe`, lớp observation / fork isolation. ADR-019 nên có mục bổ sung (đường `strategy` ↔
  `policy_id`, quy ước thành phần có trạng thái phải có `fork()`).
- Kênh SOC còn lại: `Candidate.allowed_kw` vẫn tính từ SOC thật (Physical Guard cần) — tách ở MVP-3.5.
- `change()` booking chỉ tăng version, chưa có vòng thử lại như `book`. Nhiều worker cần ràng buộc DB qua Alembic.
- `ruff check scripts/` toàn thư mục còn lỗi có sẵn ở hook ghi log AI (không sửa theo CLAUDE.md).
- Chưa chạy: E2E Postgres thật, LLM thật, deploy Render.
