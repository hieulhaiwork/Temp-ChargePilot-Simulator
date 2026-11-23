# Baseline chính thức cuối refactor Unified Core (backend, 2026-11-24)

- Nội dung: `benchmark.json` = `eval/run_benchmark.py --seeds 1,2,3,4,5`: B0 / M2b / M3a / M3b × 5 kịch bản × seed 1–5
  (100 run) trên `HybridStation` (một `StationKernel` dùng chung với simulator). Metadata: `manifest.json` (commit,
  kịch bản, policy, seed, `TimeConfig`, thư viện).
- `/simulation/benchmark` trả bảng này, kèm `source` = manifest.
- Khác baseline Phase 3 (`../2026-11-23-refactor-phase3-baseline/`) **có chủ ý**: sửa lỗi làm tròn setpoint lên khiến
  Guard chặn lệnh hợp lệ (TECHLEAD_PHASE4_DECISIONS mục 3). Bảng trước / sau và nguyên nhân:
  `docs/refactor/REFACTOR_REPORT.md`, `docs/refactor/raw/phase4-final/backend_vs_phase3.txt`.
- Không so với số trước refactor (A–D, LP backend) hay Phase 2 (khác cấu hình thời gian).
