# PHASE4_P4-API_REPORT — nhánh `feature/unified-core-p4-api` (quyết định 1, 5, 8, 9)

> Từ `70d0eaf` (brief Phase 4). Chạy headless theo `docs/refactor/tasks/PHASE4_BRIEF.md`. Quyết định gốc:
> `docs/refactor/TECHLEAD_PHASE4_DECISIONS.md`. Log cổng kiểm: `docs/refactor/raw/phase4-p4-api/`. Không đụng
> `src/simulator/**`, `src/optimizer/**`, `src/guard/**`, `services/{control_loop,hybrid_planner,runtime}.py`,
> `models/events.py` (phạm vi nhánh core).

## 1. Commit

| Commit | Quyết định | Nội dung |
|---|---|---|
| `79236e7` | 1 | Bỏ A–D khỏi `StrategyName`; `LIVE_STRATEGY` chỉ B0 / M2b / M3a / M3b; Alembic `0003` (`0003_drop_lp_strategy_plans.py`); S8 dropdown; OpenAPI + `gen:api` |
| `eaf8842` | 8 (+ 9 phần `eval/*.py`) | Baseline có version `eval/evidence/2026-11-23-refactor-phase3-baseline/`; `GET /simulation/benchmark` trả `source`; bảng A–D → `eval/results/archive/`; `run_benchmark.py` ghi `source` kind `generated`; S8 hiện nguồn / version |
| `8e49975` | 5 | Quote / admission = ước tính có điều kiện (`certainty`, `assumptions`, số phê duyệt chờ); UI S3 + chat; prompt / mock LLM |
| `952313f` | 9 | Dọn tài liệu vận hành (README, PROJECT_CONTEXT, ARCHITECTURE, sơ đồ, HANDOFF, `docs/plan` banner, `.env.example`, `render*.yaml`, Makefile); sổ nhãn archive |
| (commit này) | — | Log cổng kiểm, EXPECTED_FAILURES, DELETION_MANIFEST, ADR-019, báo cáo |

## 2. Đã làm

### (1) Loại A–D
- `src/models/charging.py::StrategyName` = `B0`, `M2b`, `M3a`, `M3b`; test khoá enum = `SIMULATOR_STRATEGIES` của
  registry. `src/config.py::live_strategy` là `Literal[...]` 4 giá trị → `LIVE_STRATEGY=B` bị từ chối khi đọc cấu hình.
- API: `POST /simulation/runs` với A–D → **422** (validate), không tới service. OpenAPI / `schema.d.ts` sinh lại.
- S8: dropdown B0 / M2b / M3a / M3b (mặc định M3a), tiêu đề "Bảng đối chứng B0 / M2b / M3a / M3b", cột ghi policy + seed.
- DB: `schedule_plans` lưu `SchedulePlan` dạng JSON; dòng A–D không đọc lại được → Alembic `0002` xoá **chỉ** các dòng
  đó (dữ liệu dẫn xuất, lịch tính lại ở lần replan kế tiếp; schema không đổi; downgrade no-op).
- Evidence A–D: không xoá số. `eval/results/benchmark.{json,md}` `git mv` vào `eval/results/archive/2026-11-22-pre-refactor/`
  kèm README **DEPRECATED**; nhãn cho các thư mục `eval/evidence/**` cũ ở `eval/evidence/2026-11-23-refactor-phase4/ARCHIVE_LABELS.md`
  (quy tắc cấm sửa evidence đã có nên không sửa README của chúng).

### (5) Quote / admission có điều kiện
- `services/admission.py`: `ASSUMPTIONS` (xe chưa đặt lịch không biết trước; không tính sự cố tương lai; lệnh chờ
  HITL coi như chưa thực thi). `evaluate` gom mọi phê duyệt `PENDING` thấy được mỗi phút trong bản fork (kế thừa từ
  trạm live + phát sinh trong fork) → `approvals_for_candidate` / `approvals_for_others`, `depends_on_approval`.
  Không mô hình xác suất đồng ý; mô phỏng thận trọng giữ nguyên (quyết định 5).
- `ScheduleProposal`: `certainty` (`estimate` | `conditional`), `approvals_pending_for_booking`,
  `approvals_pending_for_others` (chỉ đếm, không lộ xe khác), `assumptions`. Validator: `conditional` ⇔ còn phê duyệt
  chờ. `reasons` luôn có câu "ước tính … không phải cam kết", thêm câu "Phụ thuộc phê duyệt …" khi có.
- UI: S3 (`/resident/plan?view=draft`) thẻ "Ước tính kịp giờ lấy xe", thẻ + thông báo "Phụ thuộc phê duyệt", khung
  "Đây là ước tính, không phải cam kết" liệt kê `assumptions`; tóm tắt phương án trong chat ghi "ước tính, không phải
  cam kết" + điều kiện. Prompt `charging_domain.md`: cấm "chắc chắn / bảo đảm / cam kết", nói rõ khi `conditional`.
  Mock LLM và fallback của `finalize_node` ghi "ước tính" / điều kiện.
- Test admission ↔ thực thi giữ nguyên (3 ca + hàng chờ) và thêm: ca không chờ duyệt = `estimate` + giả định; ca có
  phê duyệt chờ (các xe đang có không cho giảm công suất) = `conditional`, phê duyệt trong fork không rò ra trạm live,
  và kết quả quote **vẫn khớp thực thi** khi không ai trả lời (cùng cổng / lúc cắm / bắt đầu / kết thúc / năng lượng).
- Booking (`POST /resident/bookings`) vẫn chỉ nhận khi quote khả thi; response `Booking` không thêm trường (phê duyệt
  phát sinh sau đó đi qua S4 như cũ).

### (8) Baseline có version
- `eval/evidence/2026-11-23-refactor-phase3-baseline/`: `benchmark.json` = **bản chép byte-y-hệt**
  `eval/evidence/2026-11-23-refactor-phase3/raw/backend_benchmark_seeds1-5.json` (test so byte), `manifest.json`
  (`backend-phase3` / `2026-11-23-phase3`, `provisional`, commit `c5632cb`, 5 kịch bản, 4 policy registry v1, seed 1–5,
  100 run, `TimeConfig(1, 15, None)`, Windows 11 / Python 3.12.10 / ev2gym 2.0.0 / numpy 2.5.5 / scipy 1.18.1), README.
  Không chạy lại khác điều kiện. `config/` và code đo không đổi giữa `c5632cb` và gốc nhánh (đã `git diff`).
- `GET /simulation/benchmark` đọc thư mục đó (`simulation_service.BENCHMARK_BASELINE_DIR`), trả `BenchmarkReport.source`
  (kind `versioned_baseline`, baseline, version, trạng thái, commit, đường dẫn, kịch bản, policy, seed, `TimeConfig`, thư
  viện) và dòng đầu `notes` "Nguồn: baseline … version …". Không còn đọc `eval/results/benchmark.json`.
- `eval/run_benchmark.py` (và `simulation_service.run_benchmark`) ghi `source` kind `generated` (`TimeConfig` lấy từ
  trạm thật, phiên bản thư viện, commit git). Baseline nghiệm thu cuối = thư mục mới cùng định dạng + đổi hằng số.

### (9) Tài liệu vận hành
- Không file vận hành nào còn `STATION_ENGINE=live`. Đã cập nhật: `README.md` (bảng kết quả = baseline B0 / M3a, stack,
  sơ đồ, cây thư mục, deliverable), `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `docs/architecture_diagram.md`,
  `docs/handoff/HANDOFF.md` (mục 23/11 mới nhất; mục 22/11 ghi là lịch sử), banner hiện trạng ở `docs/plan/{00,10,21,30,50}`
  + sửa các dòng "hiện tại", `.env.example`, `render*.yaml`, `Makefile`, `eval/README.md`.
- `eval/build_simulator_evidence.py`: nhãn **ARCHIVE** (mô tả kiến trúc cũ là nội dung của bằng chứng lịch sử, giữ để tái
  lập), đọc bảng A–D từ archive, từ chối ghi đè `eval/evidence/2026-11-22/`. `eval/run_manual_agent_evidence.py`: nhãn
  chế độ dịch vụ = `HybridStation`.
- Phân biệt archival evidence (giữ nguyên, nhãn tập trung) với tài liệu vận hành (đã sửa).

## 3. Đã xoá

Chi tiết + SHA: `DELETION_MANIFEST.md` mục "Phase 4 — nhánh `feature/unified-core-p4-api`".
- 5 giá trị `StrategyName` (A_fcfs, A_edf, B, C, D).
- Dòng `schedule_plans` của A–D (Alembic 0002, dữ liệu dẫn xuất).
- `simulation_service.BENCHMARK_FILE` (thay bằng `BENCHMARK_BASELINE_DIR`).
- Không xoá test nào. Test sửa: `test_removed_lp_strategies_fail_loudly` (A–D → `ValueError` ở enum),
  `test_simulation_run_unknown_scenario_is_404` (gửi `M3a`), `test_repository._plan` (`SIM_M3A`).
- `eval/results/benchmark.{json,md}`: **chuyển** (`git mv`), không xoá.

## 4. Cổng kiểm

| Kiểm | Kết quả | Log |
|---|---|---|
| Cổng AST code được bảo toàn (`compare_ast_manifest.py` so `phase3-merged/preserved_baseline_manifest.txt`) | **exit 0**: 115 định nghĩa SAME, 0 đổi, 0 khai báo | `ast_gate.txt` |
| `pytest src/simulator/tests` (golden) | **163 passed** | `pytest_simulator.txt` |
| Cổng KPI `compare_sim_output.py` (module map Phase 2, không thêm cặp — nhánh không di chuyển module) so `eval/evidence/2026-11-22/raw/sim-hardware/` | **6/6 OK, OVERALL rc=0**: MVP-1 report, MVP-1+mvp3cfg report + DecisionTrace, VinFast, MVP-2, MVP-3 | `kpi_gate.txt`, `run_*.txt`, `benchmark_mvp{2,3}.txt` |
| `pytest tests` | **493 passed, 8 skipped** (474 ở `phase3-merged` + 19 test mới) | `pytest_tests.txt` |
| ruff check + format `src tests scripts/refactor eval migrations` | pass | `ruff.txt` |
| `export_openapi.py --check` | khớp (OpenAPI đã sinh lại trong nhánh) | `openapi_check.txt` |
| `check_docs.py`, `run_agent_eval.py --offline` | pass | `check_docs.txt`, `eval_agent_offline.txt` |
| Frontend `npm run lint` / `typecheck` / `test` / `build` | pass / pass / 28 passed / pass | `web_*.txt` |
| Benchmark backend (B0 / M2b / M3a / M3b × 5 kịch bản × seed 1–5, `RESULTS_DIR` tạm) so baseline Phase 3 bằng `compare_backend_benchmark.py` | **100/100 run giống baseline, 0 vấn đề, exit 0** — nhánh api không đổi semantics backend. Log vẫn có 2 dòng sai lệch budget AC +1,97 kW ở phút 560 (đã biết từ Phase 3; root-cause là việc của nhánh core, quyết định 3) | `eval_run_benchmark.txt`, `backend_benchmark_gate.txt` |

**Chưa chạy:** E2E Postgres, LLM thật, E2E trình duyệt (vòng nghiệm thu cuối).

## 5. Expected failures còn lại

Không có test hỏng. Các mục cần xử lý khi gộp / thuộc nhánh khác: `EXPECTED_FAILURES.md` mục "Phase 4 — nhánh
`feature/unified-core-p4-api`" — tóm tắt:
- `oracle_bookings` (chỉ D dùng) và nhánh `DomainError` A–D trong `runtime.make_scheduler` còn ở file của nhánh core.
- Alembic: nếu nhánh core thêm revision từ `0001` thì có hai head khi gộp.
- `frontend/openapi.json` / `schema.d.ts` sinh lại một lần sau gộp; đường dẫn kernel trong tài liệu đổi theo `src/simulator/core/`.
- `docs/PRD.md` / `business-overview.md` và thân `docs/plan/21`, `30` còn mô tả A–D (có banner hiện trạng).

## 6. ESCALATION

Không có mục nào phải dừng. Ghi lại các quyết định đã tự chốt trong phạm vi (để Tech Lead xác nhận khi review):
1. **Xoá dữ liệu `schedule_plans` A–D bằng Alembic 0002.** Coi là dữ liệu dẫn xuất (lịch tính lại từ booking), không
   phải dữ liệu cư dân. Nếu chủ dự án muốn giữ, thay bằng migration đổi `strategy` sang giá trị đánh dấu — cần thêm
   giá trị enum, trái quyết định 1, nên chưa làm.
2. **PRD §8 vẫn định nghĩa benchmark A–D.** Đổi PRD là mục tiêu nghiệp vụ → chủ dự án quyết; tài liệu vận hành đã theo
   quyết định 1.
3. **`Booking` (response đặt lịch) không mang `certainty`.** Quyết định 5 yêu cầu thể hiện điều kiện ở quote; lúc đặt
   lịch, phê duyệt phát sinh sau đó đã có luồng S4. Nếu muốn hiện trên thẻ lịch đã đặt thì cần thêm trường vào
   `Booking` (đổi hợp đồng) — chưa làm.
