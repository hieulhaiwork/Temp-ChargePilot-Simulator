# Bằng chứng 2026-11-23 — refactor Unified Core, Phase 3 (kernel dùng chung + admission)

**Mục đích:** chứng minh (1) simulator standalone giữ golden ở chế độ tương thích, (2) code gốc được bảo toàn, (3) đo
số backend MỚI sau khi runtime đổi semantics (interval, replan). Số backend **không** dùng để kết luận "tốt hơn / tệ
hơn" so với Phase 2: hai bên khác cấu hình thời gian (ADR-019).

| Mục | Giá trị |
|---|---|
| Code đo | nhánh `feature/unified-core-p3` @ `c5632cb` (+ commit report chứa README này, chỉ tài liệu) |
| Baseline | HEAD `749c042` (output simulator chạy lại trên máy này) và evidence [`../2026-11-22/raw/sim-hardware/`](../2026-11-22/raw/sim-hardware/); backend: [`../2026-11-23-refactor-phase2/raw/backend_benchmark_seeds1-5.json`](../2026-11-23-refactor-phase2/raw/backend_benchmark_seeds1-5.json) |
| OS / Python / ev2gym / numpy / scipy | Windows 11 / 3.12.10 / 2.0.0 / 2.5.5 / 1.18.1 |
| Trạm backend | `HybridStation`, `TimeConfig(physics_step_minutes=1, decision_interval_minutes=15)` |
| Simulator standalone | `TimeConfig()` = chế độ tương thích (ZOH cả interval) |
| Policy / seed | B0, M2b, M3a, M3b (registry, version 1) × seed 1–5 × 5 scenario = 100 run |
| Lệnh | `eval/run_benchmark.py --seeds 1,2,3,4,5` với `RESULTS_DIR` trỏ ra thư mục tạm (không ghi `eval/results/`) |

## File

- `raw/kpi_gate.txt` — `compare_sim_output.py`: 32 so với output HEAD `749c042` (report, replay, events, DecisionTrace,
  CSV trùng byte, MVP-2, MVP-3 + 8 DecisionTrace) và 7 so với evidence 2026-11-22. **OVERALL rc=0.** Module map như Phase 2.
- `raw/ast_gate.txt` — `compare_ast_manifest.py` trên đúng các đường dẫn được bảo toàn: 91 định nghĩa, 0 thay đổi, rc=0.
- `raw/physical_core_step_backend_gate_f947b22.txt` — benchmark backend ở commit bước 2 (chỉ Physical Core):
  225/225 run **giống hệt** Phase 2 (0 vấn đề).
- `raw/backend_benchmark_seeds1-5.json` — 100 run, code cuối.
- `raw/backend_benchmark_seeds1-5_after_step3_ddfeb41.json` — 100 run ở snapshot `ddfeb41` (chỉ Planning Core / interval,
  chưa có replan bước 4), để quy chênh lệch về từng bước.
- `raw/backend_benchmark_seeds1-5_mean_vs_phase2.md`, `raw/backend_benchmark_seeds1-5_mean_after_step3.md` — trung bình 5 seed.
