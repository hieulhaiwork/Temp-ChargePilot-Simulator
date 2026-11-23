# Baseline backend Phase 3 có version — `backend-phase3` / `2026-11-23-phase3` (TẠM)

Quyết định 8 của Tech Lead (`docs/refactor/TECHLEAD_PHASE4_DECISIONS.md`): kết quả backend Phase 3 là baseline mới,
lưu riêng, có version. Thư mục này **chỉ chép** số đã đo ở Phase 3, không chạy lại.

| Mục | Giá trị |
|---|---|
| File số | `benchmark.json` = bản chép byte-y-hệt [`../2026-11-23-refactor-phase3/raw/backend_benchmark_seeds1-5.json`](../2026-11-23-refactor-phase3/raw/backend_benchmark_seeds1-5.json) (sha256 `0ecab1d2…81e28`) |
| Metadata máy đọc | `manifest.json` (API `GET /simulation/benchmark` đọc file này để ghi nguồn + version trong response) |
| Code đo | `feature/unified-core-p3` @ `c5632cb` |
| Kịch bản | `connector_failure`, `hybrid_evening`, `hybrid_power_drop`, `peak_evening`, `power_drop` (`config/scenarios/*.yaml` tại `c5632cb`) |
| Policy | B0, M2b, M3a, M3b (registry version 1) |
| Seed | 1–5 (100 run) |
| `TimeConfig` backend | `physics_step_minutes=1`, `decision_interval_minutes=15`, `planning_horizon_minutes=None` (= interval) |
| Thư viện | Windows 11, Python 3.12.10, ev2gym 2.0.0, numpy 2.5.5, scipy 1.18.1 |
| Trạng thái | **provisional** — baseline chính thức cuối refactor sinh ở vòng nghiệm thu, sau khi nhánh core sửa budget deviation |

## Không so chéo

- Không so với Phase 2 (`../2026-11-23-refactor-phase2/`) như cùng điều kiện: interval quyết định / replan khác (ADR-019 P1).
- Không trộn với bảng A–D cũ (`eval/results/archive/2026-11-22-pre-refactor/`, đã gắn nhãn deprecated).
- Thay đổi KPI ở Phase 4 do sửa lỗi thật phải có báo cáo trước / sau + lý do (`compare_backend_benchmark.py`).
