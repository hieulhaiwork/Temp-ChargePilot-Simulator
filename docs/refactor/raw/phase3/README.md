# Log Phase 3 — nguồn gốc từng file

Hai nguồn ghi vào thư mục này **cùng lúc** (khoảng 17:23–17:27, 2026-11-23, trên cùng code `c5632cb` + tài liệu):

| File | Sinh bởi | Ghi chú |
|---|---|---|
| `ast_gate.txt`, `kpi_gate.txt`, `preserved_manifest.txt`, `module_map.txt` | claude2 (người làm Phase 3) | cổng AST (91 định nghĩa được bảo toàn) và cổng KPI |
| `pytest_tests.txt`, `pytest_simulator.txt`, `ruff.txt`, `openapi_check.txt`, `check_docs.txt`, `eval_agent_offline.txt`, `run_*.txt`, `benchmark_mvp{2,3}.txt`, `eval_run_benchmark.txt` (dòng cuối `exit=N`) | Claude điều phối (`gates.sh`), kiểm độc lập | ghi đè log cùng tên của claude2 vì chạy trùng thư mục. Nội dung đo trên cùng code. `eval_run_benchmark.txt` đã được thay bằng bản chạy đầy đủ (bản commit đầu bị cắt giữa chừng) |

Đường dẫn máy local được thay bằng `<REPO>` / `<LOCAL_TMP>`. Kết quả kiểm độc lập sau khi gộp nhánh: `docs/refactor/raw/phase3-merged/`.
