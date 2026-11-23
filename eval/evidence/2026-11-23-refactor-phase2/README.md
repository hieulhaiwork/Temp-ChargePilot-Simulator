# Bằng chứng 2026-11-23 — refactor Unified Core, Phase 2 (thuật toán + Physical Guard về src/optimizer, src/guard)

**Mục đích:** chứng minh Phase 2 (ADR-019) chỉ di chuyển code. Không phải benchmark để so thuật toán.

| Mục | Giá trị |
|---|---|
| Code đo | nhánh `feature/unified-core`: working tree của commit chứa README này |
| Baseline | Phase 0 (`68692ee`): `docs/refactor/raw/phase0/` và evidence [`../2026-11-22/raw/sim-hardware/`](../2026-11-22/raw/sim-hardware/) |
| OS / Python / ev2gym / numpy / scipy | Windows 11 / 3.12.10 / 2.0.0 / 2.5.5 / 1.18.1 |
| Trạm backend | `HybridStation` (`STATION_ENGINE=hybrid`) |

## Kết quả (cổng kiểm, exit 0 = khớp)

- [`raw/ast_gate.txt`](raw/ast_gate.txt): 345 định nghĩa, 0 thay đổi chưa khai báo, 1 thay đổi khai báo
  (`hybrid_planner.POLICIES` lấy từ registry).
- [`raw/kpi_gate.txt`](raw/kpi_gate.txt): 11/11 so sánh simulator OK (MVP-1/2/3, VinFast, script mode, DecisionTrace,
  replay, events). Benchmark backend 225/225 run giống baseline (`replan_p95_seconds` là thời gian, bỏ qua).
  Metadata được phép khác: `run_id`, `command`, `config_source`, và `implementation` chỉ theo
  [`raw/module_map.txt`](raw/module_map.txt).
- Benchmark backend: [`raw/backend_benchmark_seeds1-5.json`](raw/backend_benchmark_seeds1-5.json). Gồm 5 scenario ×
  9 chiến lược (A_fcfs, A_edf, B, C, D, B0, M2b, M3a, M3b) × seed 1–5. Chạy với `RESULTS_DIR` trỏ ra thư mục tạm,
  **không** ghi `eval/results/`.
