# BASELINE — Phase 0 (trước refactor)

> Mọi số trong file này đều do **chạy thật trên worktree local của repo** ngày 2026-11-23. Log thô:
> `docs/refactor/raw/phase0/`. Không có số nào được chép từ tài liệu cũ.

## 1. Mốc

| Mục | Giá trị |
|---|---|
| Repo chính thức | `AI20K-Build-Phase-Cohort-5/P-019` (`origin`) |
| Nhánh làm việc | `feature/unified-core`, tạo từ `origin/develop` |
| HEAD baseline | `68692ee6c8e3d71a83aebefa95610d71840e3728` (Merge PR #15) |
| `feature/hybrid-backend` | `a88f821`, là tổ tiên của HEAD, không bị bỏ sót gì (MODULE_PROVENANCE §0) |
| Mốc code simulator gốc | `8c4c14e` (Le Hien Hieu, 2026-11-21). `src/simulator/src/**` trùng AST |
| Worktree | sạch khi bắt đầu. Chỉ thêm `docs/refactor/` (chưa commit) |
| Worktree khác (không đụng) | `.claude/worktrees/{hybrid-review,s1..s4}` và một worktree ngoài repo |
| Mirror `hieulhaiwork/Temp-ChargePilot-Simulator` @ `7e1eb61` | **568/568 file trùng blob** với `68692ee` (xem MODULE_PROVENANCE §0) |

## 2. Môi trường

| Thành phần | Phiên bản |
|---|---|
| OS | Windows 11 (MINGW64 shell) |
| Python (`.venv`) | 3.12.10 |
| ev2gym / scipy / numpy | 2.0.0 / 1.18.1 / 2.5.5 |
| langgraph / langchain / fastapi / sqlalchemy / pydantic | 1.2.20 / 1.4.9 / 0.162.2 / 2.1.8 / 2.14.3 |
| pytest / ruff | 9.2.0 / 0.17.4 |
| Node | v26.7.0 |
| `.env` | `LLM_PROVIDER=openai`. Test tự đặt LLM giả (tests/__init__.py). `STATION_ENGINE` mặc định `hybrid`, `LIVE_STRATEGY` mặc định `M3a` (src/config.py:84-86) |

## 3. Kết quả chạy

| # | Lệnh | Kết quả | Log |
|---|---|---|---|
| 1 | `ruff check src tests` (phạm vi `make lint`/CI) | **pass** | `ruff_check_make_scope.txt` |
| 2 | `ruff format --check src tests` | **pass** (194 file) | `ruff_format_make_scope.txt` |
| 3 | `ruff check .` (toàn repo, theo guide §6) | **8 lỗi có sẵn**, đều trong `scripts/{log_antigravity,log_hook,log_manual,submit_log}.py` (hook logging, không thuộc phạm vi CI) | `ruff_check.txt` |
| 4 | `ruff format --check .` | **27 file có sẵn** cần format: code mẫu trong `docs/guide/**/*.md` (Technical Book, guide §3.6.4 cấm sửa) và `scripts/` | `ruff_format.txt` |
| 5 | `pytest` (testpaths=`tests`) | **440 passed, 8 skipped**, 0 failed (37.6 s) | `pytest_tests.txt` |
| 6 | 8 skipped | đều thuộc `tests/test_forecast/test_forecast_contracts.py` (F6/T2.x hoãn, ADR-015) | `pytest_skipped.txt` |
| 7 | `pytest src/simulator/tests src/simulator/tests/ev2gym_smoke.py` | **163 passed** (10.2 s), khớp con số 163 trong `PROJECT_STATE.md` | `pytest_simulator.txt` |
| 8 | `scripts/export_openapi.py --check` | **OK**, khớp code | `openapi_check.txt` |
| 9 | `sha256(frontend/openapi.json)` | `9f01b5f082e6b026a6c84c9577a52b2dbd72f7ba5634b2ac3464d8477a28acf1`: 39 paths, 74 schemas | `openapi_sha256.txt` |
| 10 | `eval/run_agent_eval.py --offline` | OK. **Lưu ý: chỉ kiểm dataset (55 câu) và ngưỡng, không chạy agent.** Hành vi agent được phủ bởi 82 test trong `tests/test_agents` | `eval_agent_offline.txt` |
| 11 | `frontend: npm run lint` | pass | `web_lint.txt` |
| 12 | `frontend: npm run typecheck` | pass | `web_typecheck.txt` |
| 13 | `frontend: npm test` | **28 passed** (4 file) | `web_test.txt` |
| 14 | `frontend: npm run build` | **chưa chạy** (chậm, ghi `.next/`). Phase 5 cần chạy | — |

Số test theo thư mục (448 = 440 + 8 skipped): test_services 105, test_agents 82, test_api 64, test_guard 53,
test_optimizer 33, test_simulator 29, test_models 26, test_architecture 20, test_forecast 10, test_db 10,
test_config 9, test_eval_scripts 7.

## 4. Simulator golden và benchmark MVP-1/2/3

| Lệnh | Kết quả chính (in ra) | So với raw evidence `eval/evidence/2026-11-22/raw/sim-hardware/` |
|---|---|---|
| `python -m src.simulator.run --scenario mvp1 --decision-trace` | 9/9 đúng hạn, chờ TB 51.11', đỉnh lưới 105.263 kW | `mvp1_default_report.json`: **0 khác biệt KPI**, chỉ khác `run_id`/`command` |
| `… --scenario mvp1 --algorithms config/algorithms_mvp3.json` | 9/9, chờ TB 50.67', 105.263 kW | `mvp1_mvp3_report.json`: **0 khác biệt KPI**, chỉ khác `run_id`/`command`/đường dẫn tuyệt đối |
| `… --scenario vinfast_dc_2port_120kw` | 8/9, chờ TB 44.78', 149.474 kW | `vinfast_dc_120kw_report.json`: **0 khác biệt KPI**, chỉ khác đường dẫn/`run_id`/`command` |
| `python -m src.simulator.benchmark --vinfast-sensitivity` (MVP-2) | B0 DC 74/180 · M2a 93/180 · **M2b 100/180** · M2c 79/180 · M2b_no_sla 100 · M2b_no_queue 97 · M2b_10x_queue 100 | `mvp2_benchmark.json`: **0 khác biệt** ngoài timing |
| `python -m src.simulator.benchmark_mvp3` (MVP-3) | B0 AC 45/55 DC 58/215 TOU 916.15 · M2b 45/82 917.88 · **M3a 45/82 896.13** · M3b 35/89 953.20 USD | `mvp3_benchmark.json`: **0 khác biệt** ngoài timing |

Khớp với PROJECT_STATE: M3a tổng 127/270 SLA, TOU rẻ hơn M2b 21.75 USD; M3b +7 DC / −10 AC so với M3a.
Latency (không dùng để so): decision p95 M2b 5.1-6.0 ms, M3a/M3b khoảng 12.3 ms trên máy này.
So sánh: `golden_vs_evidence_2026-11-22.txt` (script `cmpbench.py`: bỏ các khoá timing, so số với dung sai tương đối 1e-9).

> **Đính chính 2026-11-23 (sau review).** Bản `cmpbench.py` dùng để ra kết luận ở bảng trên có hai lỗi.
> (1) Regex "timing" bỏ qua **mọi** khoá chứa `solver`/`path`/`created`/…, nên đã không so
> `rejected_solver_plan_count` (KPI) và `algorithm_metadata/*/solver` (cấu hình).
> (2) Script luôn trả exit 0; kết luận lấy từ output in ra, không phải từ exit code.
> Script đã được viết lại: chỉ bỏ đúng trường thời gian tường, chỉ cho phép khác ở `/metadata/{run_id,command,
> algorithms/*/config_source}`, khác ở chỗ khác thì exit 1 (mutation `rejected_solver_plan_count += 1` bị bắt, exit 1).
> Chạy lại trên **cùng output Phase 0**: 5/5 cặp OK, 0 khác biệt ngoài danh sách cho phép
> (`raw/phase1/recheck_strict_cmpbench.txt`). Kết luận ở bảng trên **giữ nguyên**, nhưng bằng chứng hợp lệ là lần chạy lại này.
Output đầy đủ khoảng 22 MB, không commit, nằm ở scratchpad phiên làm việc.

## 5. Benchmark Backend (`eval/run_benchmark.py --seeds 1,2,3,4,5`)

- 225 run = 5 scenario (`connector_failure`, `hybrid_evening`, `hybrid_power_drop`, `peak_evening`, `power_drop`) × 9
  chiến lược (A_fcfs, A_edf, B, C, D, B0, M2b, M3a, M3b) × 5 seed. Trạm `HybridStation`. Mất 461 s cho toàn bộ lệnh ở §4 + §5.
- **Tất định:** chạy lặp 2 lần `hybrid_evening,hybrid_power_drop × M3a,M3b,B × seed 1,2` cho 12/12 run giống hệt nhau
  và giống lần chạy đầy đủ (bỏ `replan_p95_seconds`).
- Bảng trung bình 5 seed: `eval_benchmark_seeds1-5_mean.md`. Thô: `eval_benchmark_seeds1-5.json/.md`.

Trích (trung bình 5 seed):

| scenario | strategy | on_time | unmet kWh | delivered kWh | cost VND | peak kW | violations | replan p95 s |
|---|---|---|---|---|---|---|---|---|
| hybrid_evening | B (LP backend) | 0.372 | 290.96 | 341.52 | 748,248 | 91.64 | 0 | 0.026 |
| hybrid_evening | B0 | 0.450 | 302.65 | 329.83 | 862,896 | 88.80 | 0 | 0.002 |
| hybrid_evening | M2b | 0.438 | 303.66 | 328.81 | 860,318 | 88.80 | 0 | 0.007 |
| hybrid_evening | **M3a** | 0.398 | 312.58 | 319.89 | 770,938 | 84.90 | 0 | 0.018 |
| hybrid_evening | M3b | 0.386 | 313.11 | 319.37 | 769,672 | 86.20 | 0 | 0.017 |
| hybrid_power_drop | B | 0.334 | 311.87 | 320.60 | 702,457 | 85.17 | 0 | 0.026 |
| hybrid_power_drop | B0 | 0.411 | 325.62 | 306.86 | 770,918 | 78.94 | 0 | 0.001 |
| hybrid_power_drop | **M3a** | 0.347 | 339.58 | 292.89 | 684,297 | 77.11 | 0 | 0.014 |

**Ghi nhận (chưa kết luận):**
- Trên backend, M3a/M3b **đúng hạn thấp hơn** B0/M2b. Offline MVP-3 thì M3a bằng M2b về SLA (127/270). Có thể do các
  khác biệt interval/vật lý ở PHASE0_FINDINGS §2/§4. **Không so trực tiếp** hai bộ số (guide §6).
- `connector_failure`: notes ghi "Bỏ qua sự cố không khớp topology" (sự cố trên cổng `A05` không có trong `mvp1`
  4 cổng). Kịch bản này chưa thực sự kiểm sự cố cổng trên topology hiện tại.
- `eval/results/benchmark.{json,md}` (được track, sinh ở `098877a`, **trước** `0a97a9f`/`a88f821`) bị lệnh trên ghi đè.
  Đã chép bản mới vào raw rồi **`git restore`** lại hai file đó. Bản commit hiện tại không phản ánh HEAD, cần người
  phụ trách quyết có sinh lại không (không làm trong Phase 0).

## 6. Hash bảo toàn cho Phase 2

`docs/refactor/raw/phase0/code_hash_manifest.txt`: với mỗi file của simulator core, `hybrid_station`, `live`, `base`,
CLI, `src/guard/*`, `src/optimizer/*`, `hybrid_planner` có: sha256 file, sha256 AST (bỏ docstring + import), sha256 AST
của từng hàm/lớp top-level. Sau khi di chuyển, hash hàm/lớp phải giữ nguyên. Hàm/lớp nào đổi hash phải có change note.

## 7. Chưa chạy / giới hạn của baseline

- `npm run build` (frontend), `make web-check` đầy đủ.
- E2E API với Postgres thật (`make migrate && make run`): chưa chạy. 64 test `tests/test_api` chạy với DB test của conftest.
- Chat với LLM thật (OpenAI/Gemini): chưa chạy, test dùng LLM giả.
- Differential live ↔ offline ngoài fixture mvp1 1': **chưa có**, việc này thuộc Phase 3 (PHASE0_FINDINGS §2).
- Log thô đã được làm sạch trước khi commit: đường dẫn máy local thay bằng `<REPO>` / `<LOCAL_TMP>`, đường dẫn
  máy đo 2026-11-22 thay bằng `<REPO_2026-11-22>`. Log ruff toàn repo chỉ giữ vị trí + mã lỗi.
