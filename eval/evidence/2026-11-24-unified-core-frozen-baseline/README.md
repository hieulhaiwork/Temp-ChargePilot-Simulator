# Baseline đóng băng — kết thúc refactor Unified Core (backend, 2026-11-24)

- `benchmark.json` = `eval/run_benchmark.py --seeds 1,2,3,4,5`: B0 / M2b / M3a / M3b × 5 kịch bản × seed 1–5 (100 run)
  trên `HybridStation` (một `StationKernel` dùng chung với simulator), tại `code_commit` trong `manifest.json`.
- `/simulation/benchmark` trả bảng này (`BENCHMARK_BASELINE_DIR`), kèm `source` = manifest.
- KPI **trùng** baseline trước (`../2026-11-24-unified-core-final-baseline/`): `compare_backend_benchmark.py` 100/100 run,
  0 problems (`docs/refactor/raw/final-acceptance-merged/benchmark_compare.txt`). Khác ở chỗ bổ sung (Final Acceptance):
  - mỗi run có `experiment` (policy / version, thành phần + version, tham số, DC model, `TimeConfig`, fingerprint) và
    `violations` (vi phạm cứng thật của kernel, tách khỏi KPI tổng công suất lấy mẫu);
  - `guard.after_apply_failsafe: true` mặc định (0 vi phạm cứng trong 100 run ⇒ fail-safe không kích hoạt).
- Giả định: vật lý mô phỏng (EV2Gym + mô hình DC synthetic), không phải phần cứng thật; một worker.
- Không so với số trước refactor (A–D, LP backend) hay Phase 2 (khác cấu hình thời gian).
