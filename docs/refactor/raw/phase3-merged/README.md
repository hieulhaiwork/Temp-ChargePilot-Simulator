# Kiểm độc lập sau khi gộp Phase 3 + LLM chat (Claude điều phối)

Cây đo: `feature/unified-core` @ merge `0fd9441` (Phase 3 của claude2 + chuyển chat sang `src/llm_chat/` của claude3).
Mọi cổng chạy lại bằng `scripts/refactor/*` (exit 1 khi lệch), không dùng số tự báo của hai nhánh.

| Kiểm | Kết quả | File |
|---|---|---|
| `pytest` | 474 passed, 8 skipped (= 469 gốc − 1 nhánh p3 + 6 nhánh chat) | `pytest_tests.txt` |
| `pytest src/simulator/tests …` (golden) | 163 passed, test chủ simulator không sửa | `pytest_simulator.txt` |
| ruff check + format `src tests scripts/refactor` | pass | `ruff.txt` |
| OpenAPI `--check` | khớp, `frontend/openapi.json` không đổi | `openapi_check.txt` |
| `check_docs.py`, `eval/run_agent_eval.py --offline` | pass | `check_docs.txt`, `eval_agent_offline.txt` |
| Cổng AST code được bảo toàn (115 định nghĩa: `optimizer/{dispatch,zones,coordination,registry.py}`, `guard/physical/validator.py`, `charging_models/`, `engine/{ev2gym_adapter,queue}.py`, `evaluation/`, `models/{simulation_core,physical_*,charging_physics,scheduling}`) so manifest cuối Phase 2 | exit 0, 0 thay đổi | `ast_gate.txt` |
| Cổng KPI (module map Phase 2) so evidence 2026-11-22 + output Phase 0 | 11/11 OK: MVP-3, MVP-2, mvp1, mvp1+mvp3cfg, vinfast, script mode, 2 DecisionTrace, replay, events; `vehicles.csv` (vinfast) và `power_trace.csv` (mvp1) trùng byte với Phase 0 | `kpi_gate.txt` |
| Benchmark backend (semantics Phase 3: B0/M2b/M3a/M3b × 5 scenario × seed 1–5) so evidence của claude2 | 100/100 run giống hệt (tái lập) | `kpi_gate.txt`, `eval_run_benchmark.txt` |

Chưa chạy: `make web-check` (OpenAPI không đổi), E2E Postgres, LLM thật.
