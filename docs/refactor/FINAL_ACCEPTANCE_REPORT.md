# FINAL_ACCEPTANCE_REPORT — Nhóm patch cuối + đóng băng baseline Unified Core (2026-11-24)

> Nguồn: review Final Acceptance của Tech Lead trên mirror `b9a6668` (= P-019 `3e47d13`). Brief:
> `docs/refactor/tasks/FINAL_ACCEPTANCE_PATCH_BRIEF.md`. Chi tiết: `FINAL_ACCEPTANCE_A_REPORT.md` (claude2),
> `FINAL_ACCEPTANCE_B_REPORT.md` (claude3). Log trên cây đã gộp: `docs/refactor/raw/final-acceptance-merged/`.
> **Kết luận: refactor Unified Core kết thúc; baseline đóng băng.**

## 1. Patch → commit

| Mục review | Commit | Test chứng minh |
|---|---|---|
| §1.1 `guard.after_apply_failsafe: true` mặc định | `a6695ea` | `tests/test_services/test_failsafe_after_apply.py` |
| §1.2 không consumer nào bỏ event của `sync_clock` (outbox → control_loop) | `7e7733f`, `a9def2f` | `tests/test_services/test_safety_event_delivery.py` |
| §1.3 catch-up dừng ở phút vi phạm cứng | `674123c` | như trên (`test_multi_minute_catch_up_stops_at_the_violation_minute`) |
| §1.4 curtailment đưa về trần; tách `aggregate_power` / `charging_model` / `acceptance` | `674123c`, `7e7733f` | như trên (`…brings_every_tier_back_within_its_cap`, `…charging_model_fault_is_isolated…`) |
| §2 optimistic concurrency `change`, kiểm lại dưới khoá ở `change` / `cancel`, fingerprint nguồn / cổng / policy, consent thật, giả định consent của quote | `1981c50` | `tests/test_services/test_admission_consistency.py` |
| §3.1 `build_sim_runtime` truyền tham số optimizer | `0d3ec8c` | `tests/test_services/test_config_parity.py` |
| §3.2–3.3 resolved experiment + fingerprint trong run / report / manifest | `6c2fb6a` | như trên |
| §3.4 tham số khác mặc định: live = benchmark = admission | `e37e0a9` | như trên |
| §3.5 tách phút vượt lấy mẫu (MT4) khỏi vi phạm cứng kernel | `249ec14` | như trên |
| §4.1 S8 lấy policy từ `GET /simulation/policies`, gửi `policy_id` | `1d9f3a7` | frontend test (30) |
| §4.2 `HybridSimulator.fork` có bản ghi riêng | `bd00c9a` | `src/simulator/tests/test_fork_isolation.py` |
| §4.3 cô lập fallback DC model có trạng thái; từ chối closure có trạng thái | `540d458` | như trên |
| Đóng băng baseline (provenance) + `/simulation/benchmark` trả baseline này | `9a69e5a` | `tests/test_eval_baseline.py`, `tests/test_api/test_contract.py` |

Điều phối thêm `a9def2f` (ESCALATION 4 của nhánh B): runtime dựng trong threadpool khi vòng nền tắt chưa biết vòng sự
kiện ⇒ event của đường đọc nằm chờ outbox; nay `lifespan` ghi vòng của app (`runtime.register_app_loop`) và giao ngay.

Gộp: `57971d8` (accept-b), `d4cdb2a` (accept-a). Xung đột chỉ ở `frontend/openapi.json` / `schema.d.ts` (sinh lại).

## 2. Regression trên cây cuối (`raw/final-acceptance-merged/`)

| Kiểm | Kết quả |
|---|---|
| ruff check + format (`src tests scripts/refactor eval`) | pass |
| `pytest tests` | 604 passed, 8 skipped (F6 forecast hoãn) |
| `pytest src/simulator/tests` | 180 passed |
| AST code gốc | 114 compared, 0 undeclared, 0 declared |
| Golden MVP-1/2/3 (evidence 2026-11-22) | 38/38 OK |
| Benchmark backend 100 run vs `2026-11-24-unified-core-final-baseline` (fail-safe BẬT) | 0 problems |
| OpenAPI `--check`, `check_docs`, eval agent offline | pass |
| Frontend lint / typecheck / test / build | pass, 30 test |

## 3. Baseline đóng băng

`eval/evidence/2026-11-24-unified-core-frozen-baseline/` (`backend-unified-core-frozen` / `2026-11-24-frozen`,
`code_commit` `a9def2f`): KPI trùng baseline final (ngoài latency), có `experiment` + fingerprint cho B0 / M2b / M3a /
M3b và `violations` của kernel (0 trong 100 run). Baseline final + Phase 3 giữ nguyên làm lịch sử.

## 4. Thay đổi test cũ (có lý do)

- `test_failsafe_after_apply.py`: assertion "mặc định false" → "config vận hành true, thiếu khoá vẫn false" (chính là
  thay đổi §1.1 được duyệt).
- `test_eval_baseline.py`, `test_api/test_contract.py`: baseline được phục vụ đổi sang bản đóng băng (cơ chế dự kiến
  ghi ở `simulation_service.BENCHMARK_BASELINE_DIR`); test baseline final cũ vẫn chạy.
- `test_config_parity.py::test_old_baseline_without_experiments_still_loads`: trỏ tường minh vào baseline cũ.

## 5. Giới hạn đã biết (ghi rõ, chưa làm)

- Vật lý mô phỏng (EV2Gym + DC synthetic); profile VinFast v0.1 là ước lượng / proxy. Chưa hiệu chuẩn phần cứng.
- Một worker: khoá booking, fingerprint, outbox, safety hold trong RAM; nhiều worker cần ràng buộc DB / khoá phân tán.
- Lỗi acceptance của một xe làm bước đó bỏ mọi ứng viên tới khi xe bị ngắt (logic Physical Core gốc, không đổi);
  chưa có endpoint vận hành gỡ safety hold.
- `Candidate.allowed_kw` vẫn tính từ SOC thật (Physical Guard cần).
- `planning.parameters` chỉ áp cho policy live; tham số theo từng policy cần khoá cấu hình mới.
- Chưa kiểm chứng sau refactor: E2E Postgres thật, LLM thật, deploy Render.
- Ngoài phạm vi (MVP-3.5 / MVP-4): nhiễu quan sát thật, BMS V / I, uncertainty-aware scheduling, QoS coordinator, AI-4.
