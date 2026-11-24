# REFACTOR_REPORT — Unified Core (ADR-019), báo cáo bàn giao final acceptance

> Nhánh `feature/unified-core-p4-final`, gốc `68692ee` (`origin/develop`). Dừng ở final acceptance, chờ Tech Lead review.
> Không merge / deploy nhánh chính. Bản đồ đường dẫn: `FINAL_MAP.md`. Xoá: `DELETION_MANIFEST.md`.
> Log cổng kiểm cuối: `docs/refactor/raw/phase4-final/`.

## 1. Kiến trúc cuối (chiều import thực tế: `FINAL_MAP.md` §2)

- **Một Physical Core + một Planning Core:** `StationKernel` (`src/simulator/core/kernel.py`) với
  `observe / propose / approve / apply_approved / advance` và một `boundary()`. Dùng chung cho:
  - `HybridSimulator` (`src/simulator/hybrid.py`: CLI, golden, benchmark MVP-1/2/3, DecisionTrace offline);
  - `HybridStation` (backend);
  - admission (fork trạm).
- **Một registry:** `src/optimizer/registry.py` (DISPATCH / OPTIMIZERS / COORDINATORS + POLICIES B0 / M2b / M3a / M3b
  đóng băng). Ghép DC charging model ở `src/simulator/core/algorithms.py`.
- **Guard hai lớp đúng vị trí:**
  - Physical Guard gốc `src/guard/physical/validator.py` (kernel gọi trước + sau thực thi);
  - Business Guard / HITL `src/guard/{rules,approval,dispatcher}.py` (chokepoint duy nhất tới trạm).
- **Chat cư dân:** `src/llm_chat/`. LLM provider dùng chung `src/services/llm.py`. `src/agents/` để dành AI-1 / AI-4.
- **Hợp đồng thuần:** `src/models/{simulation_core,scheduling,physical_*,charging_physics,decisions}` (stdlib).

## 2. Lịch sử phase và người làm

| Phase | Nội dung | Làm | Review |
|---|---|---|---|
| 0 | Baseline, provenance, import graph, 18 khác biệt engine | Claude điều phối | duyệt |
| 1 | Tách hợp đồng sang `src/models` | Claude điều phối | duyệt |
| 2 | Thuật toán → `src/optimizer`, Physical Guard → `src/guard/physical` | Claude điều phối | duyệt |
| 3 | Kernel dùng chung, admission trên fork, xoá LP A–D + LiveStation | claude2 | duyệt |
| 4 | Kernel → `src/simulator/core`, xoá shim, CHARGE_COMPLETED, deadband / deviation / hard-cap, DecisionTrace | claude2 (dừng giữa chừng do hạn mức) | — |
| 4 | Bỏ A–D (enum / OpenAPI / S8), quote có điều kiện, baseline có version, dọn tài liệu vận hành | claude3 | — |
| 4 | Chuyển chat sang `src/llm_chat/` | claude3 | — |
| 4 | Gộp, Alembic một head, dọn A–D còn sót, E2E, test registry, baseline chính thức, tài liệu cuối | claude3 bắt đầu merge; Claude điều phối hoàn tất | **chờ** |

## 3. Bằng chứng "một engine"

- Trong `src/` (trừ test của chủ simulator), `adapter.step(`, `coordinator(`, `queue.connect(` chỉ xuất hiện ở
  `src/simulator/core/kernel.py`. `_charge_one_minute`, `_decide`, LP backend, LiveStation đã xoá.
- Differential test (`tests/test_refactor/test_differential.py`): offline ↔ backend trên cùng kernel cho cùng gán
  cổng / setpoint / budget / năng lượng / SOC (≤ 1e-9). Phủ B0 / M2b / M3a / M3b, nguồn chung / độc lập, cắt nguồn,
  DC taper, cổng lỗi, fallback solver.
- Admission ↔ thực thi (`tests/test_services/test_admission.py`): quote trên fork = lịch chạy thật, cùng điều kiện.

## 4. Kiểm định lượng (cây cuối, `docs/refactor/raw/phase4-final/`)

| Kiểm | Kết quả | Log |
|---|---|---|
| `pytest` toàn repo | **520 passed, 8 skipped** (8 skip = F6 forecast hoãn, ADR-015) | `pytest_tests.txt` |
| `pytest src/simulator/tests` (golden, test chủ simulator chỉ đổi import) | **163 passed** | `pytest_simulator.txt` |
| Cổng AST code gốc (dispatch, zones, coordination, registry, validator, charging models, queue, EV2Gym adapter, evaluation, hợp đồng) | **114/114 trùng**, exit 0 (khai báo move sang `core/`, `evaluation/`) | `ast_gate.txt`, `moves.txt` |
| Cổng KPI golden so evidence 2026-11-22 (MVP-1/2/3, VinFast, script mode, DecisionTrace, replay, events) | **10/10 OK**; `vehicles.csv`, `power_trace.csv` mvp1 trùng byte Phase 0 | `kpi_gate.txt`, `module_map.txt` |
| ruff check + format `src tests scripts/refactor` | pass | `ruff.txt` |
| OpenAPI `--check`; `gen:api` sau gộp | khớp; không đổi nội dung type | `openapi_check.txt`, `web_gen_api.txt` |
| Frontend `npm ci / lint / typecheck / test / build` | pass, 28 test | `web_*.txt` |
| `check_docs`, `eval/run_agent_eval.py --offline` | pass | `check_docs.txt`, `eval_agent_offline.txt` |
| Alembic | một head `0001 → 0002 → 0003`; `tests/test_db` pass | — |

Số test theo phase (cùng máy):
- Phase 0: 440 / 8 skip.
- Phase 1: 448.
- Phase 2: 468.
- Phase 3 (sau gộp chat): 474.
- Phase 4 (cuối): **520**. Đã xoá 24 test LP / A–D, mỗi test có test thay thế trong `DELETION_MANIFEST.md`.

## 5. Backend / API / Chat / an toàn

- **E2E** `tests/test_api/test_flows.py::test_e2e_unified_core_acceptance`, runtime thật, DB test:
  quote (có điều kiện, có `assumptions`) → booking → control loop M3a → lệnh qua dispatcher / Guard → vật lý kernel →
  `CHARGE_COMPLETED` → mọi lệnh có `correlation_id` truy về DecisionTrace → 0 vi phạm vật lý →
  `/simulation/benchmark` chỉ B0–M3b, có nguồn. Mutation đổi `CHARGE_COMPLETED` thành `REPLAN_REQUESTED` làm test fail.
- **Chat / HITL:** 82 test chat chuyển sang `tests/test_llm_chat/` không sửa logic (`LLMCHAT_REPORT.md`). `/chat`,
  `/chat/stream`, `/chat/resume`, `resident_id` phía server, idempotency `confirm_booking`.
- **An toàn:**
  - `tests/test_guard/test_load_reduction.py`: giảm tải không bị anti-flapping / HITL giữ; lô phút 560 làm tròn lên
    bị chặn, làm tròn xuống thì qua;
  - `test_power_drop_is_curtailed_before_replan`: giảm nguồn đột ngột → cắt ngay;
  - `test_blocked_commands_show_up_for_operator`: lệnh vượt trần bị chặn;
  - test cổng lỗi trong differential / `test_hybrid_station`.
- **DecisionTrace** (`tests/test_services/test_decision_trace.py`):
  - cùng schema `decision_record` của simulator;
  - mọi Command có `correlation_id`;
  - replay Physical Guard từ trace;
  - năng lượng các trace cộng lại = năng lượng trạm;
  - không chứa `resident_id` / token.

## 6. Mở rộng optimizer (Definition of Done)

`tests/test_refactor/test_registry_extension.py`: đăng ký optimizer DC thử nghiệm vào `registry.OPTIMIZERS`, trỏ policy
M2b sang nó trong `registry.POLICIES`, rồi chạy runtime backend thật, **không sửa** `src/services` / `src/simulator`.
Kết quả:
- backend dùng đúng implementation mới (metadata);
- công suất DC ≤ 5 kW;
- 0 vi phạm.

Test đối chứng: khi bỏ cấu hình thử nghiệm, M2b trở lại `RollingHorizonLP` (> 5 kW).

## 7. Baseline

- Baseline chính thức: `eval/evidence/2026-11-24-unified-core-final-baseline/` (100 run = B0 / M2b / M3a / M3b ×
  5 kịch bản × seed 1–5; manifest commit `157f403`, `TimeConfig`, thư viện). `/simulation/benchmark` trả bảng này.
- So baseline Phase 3: **lệch có chủ ý** (`raw/phase4-final/backend_vs_phase3.txt`).
  - Nguyên nhân: Phase 3 làm tròn setpoint **lên**, lô lệnh vượt trần lưới 0,0095 W, nên `total_power_limit` chặn cả
    lô hợp lệ, kể cả lệnh giảm tải. Sửa: làm tròn xuống, lệnh không tăng công suất không bị chặn, giảm tải an toàn
    được ưu tiên. TOL trần cứng vẫn 1e-7.
  - Tác động lớn ở B0 / M2b trên ba kịch bản AC-only cũ (`peak_evening`, `connector_failure`, `power_drop`):
    - on_time 0.151 → 0.198;
    - lệnh bị chặn 63,4 → 0,6;
    - đỉnh 32,48 → 33,25 kW (= trần);
    - chi phí tăng vì giao thêm điện.
  - Các dòng khác lệch ≤ 0,2 kWh / ≤ 500 VND. `power_limit_violations` = 0 ở cả 100 run.
  - Số đo độc lập của Claude điều phối trùng bảng của claude2 (`PHASE4_P4-CORE_REPORT.md` §3).
- Không so với Phase 2 hay số trước refactor: khác cấu hình thời gian / A–D, là archive.

## 8. Giới hạn còn lại (MVP-3.5, ngoài phạm vi refactor)

- Sự cố nguồn "công bố trước" (`announced_at` / `effective_at`) chưa có ở backend (quyết định 4).
- Quote không mô hình xác suất đồng ý HITL; lệnh chờ duyệt coi như chưa thực thi (quyết định 5).
- Chưa có nhiễu SOC, sai số deadline, telemetry trễ, mô hình V / I / BMS, hiệu chuẩn DC taper.
- Final Review 2026-11-24 §4 đã xử lý ở `FINAL_REVIEW_FIX_REPORT.md` (điểm cắm / cơ chế, mặc định giữ hành vi cũ):
  registry policy, DC profile backend, lớp ground truth / observation, fork isolation, fail-safe sau apply, booking
  concurrency, benchmark `--strict-incidents`. Mô hình nhiễu thật và robust optimizer vẫn là việc MVP-3.5.
- PRD §8 / `docs/business-overview.md` còn mô tả benchmark A–D. **Chủ dự án quyết định** có sửa mục tiêu nghiệp vụ
  không.
- Chưa chạy: E2E với Postgres thật (Neon), LLM thật (OpenAI / Gemini), deploy Render.

## 9. Deployment notes + rollback

- Cần `alembic upgrade head` (`0002` bảng `decision_traces`, `0003` xoá lịch lưu A–D; downgrade `0003` không khôi phục
  được lịch A–D vì là dữ liệu dẫn xuất).
- Env: `STATION_ENGINE` chỉ `hybrid`; `LIVE_STRATEGY` ∈ B0 / M2b / M3a / M3b. Image cần `ev2gym` `--no-deps`.
- Frontend: OpenAPI đổi (bỏ A–D, thêm `CHARGE_COMPLETED`, quote `certainty` / `assumptions` / `approvals_pending_*`,
  `source` của benchmark). Deploy backend + frontend cùng lúc.
- Rollback: deploy lại commit trước refactor (`68692ee`) + `alembic downgrade 0001`. Bảng `decision_traces` bị xoá; lịch
  A–D không quay lại (được tính lại).
- **Chưa push `origin` P-019, chưa merge `develop` / `main`, chưa deploy.** Bản review có trên mirror
  `hieulhaiwork/Temp-ChargePilot-Simulator` nhánh `feature/unified-core`.
