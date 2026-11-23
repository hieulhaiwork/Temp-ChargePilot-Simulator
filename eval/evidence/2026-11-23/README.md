# Bằng chứng 2026-11-23 — backend chạy engine simulator (HybridStation, ADR-018)

Môi trường: Windows 11, Python 3.12.10, numpy 2.5.5, scipy 1.18.1, ev2gym 2.0.0 (`--no-deps`), gymnasium 1.4.0.
Branch `feature/hybrid-backend` từ `develop` @ `d1538a8`, working tree chưa commit. `STATION_ENGINE=hybrid`.

## 1. Đối chiếu trạm với HybridSimulator ("live = research", ADR-016 / ADR-018)

`tests/test_simulator/test_hybrid_station.py::test_replay_mvp1_matches_hybrid_simulator` phát lại quyết định gán cổng + công suất từng phút của
`HybridSimulator.run()` trên fixture `src/simulator/scenario/mvp1.json` (thuật toán mặc định) vào `HybridStation` qua
`apply_commands`: năng lượng pin, năng lượng lưới, SOC, thời điểm cắm / xong / rời khớp trong 1e-6 kWh, 0 vi phạm.
Kết quả test: [`raw/tests.txt`](raw/tests.txt) (15 test trạm + bộ lập lịch; 163 test simulator, không sửa).

## 2. Benchmark — mọi chiến lược trên CÙNG trạm HybridStation

Lệnh (cùng seed → cùng số):

```bash
python eval/run_benchmark.py --scenarios hybrid_evening,hybrid_power_drop --seeds 1,2,3,4,5
```

File gốc: [`raw/benchmark.json`](raw/benchmark.json), [`raw/benchmark.md`](raw/benchmark.md). Trung bình 5 seed; p95 tính
lại là lớn nhất trong 5 seed. A–D = bộ tối ưu backend (`src/optimizer/`); B0 / M2b / M3a / M3b = thuật toán simulator
(`src/simulator/benchmark_mvp3.py POLICIES`, chạy qua `src/services/hybrid_planner.py`).

| Kịch bản | Chiến lược | Đúng hạn | Điện thiếu (kWh) | Chi phí (VND) | Vượt giới hạn | Tính lại p95 (s) |
|---|---|---|---|---|---|---|
| hybrid_evening | A_fcfs | 47,5% | 304,5 | 859.538 | 0 | 0,006 |
| hybrid_evening | A_edf | 48,6% | 285,6 | 897.518 | 0 | 0,007 |
| hybrid_evening | B | 37,2% | 291,0 | 748.248 | 0 | 0,040 |
| hybrid_evening | C | 37,2% | 291,0 | 748.248 | 0 | 0,036 |
| hybrid_evening | D | 37,2% | 290,8 | 751.084 | 0 | 0,041 |
| hybrid_evening | B0 | 45,0% | 302,6 | 862.896 | 0 | 0,002 |
| hybrid_evening | M2b | 43,8% | 303,7 | 860.318 | 0 | 0,008 |
| hybrid_evening | M3a | 39,8% | 312,6 | 770.938 | 0 | 0,024 |
| hybrid_evening | M3b | 38,6% | 313,1 | 769.672 | 0 | 0,025 |
| hybrid_power_drop | A_fcfs | 42,3% | 329,0 | 776.619 | 0 | 0,005 |
| hybrid_power_drop | A_edf | 46,1% | 306,0 | 811.563 | 0 | 0,006 |
| hybrid_power_drop | B | 33,4% | 311,9 | 702.457 | 0 | 0,034 |
| hybrid_power_drop | C | 33,4% | 311,9 | 702.457 | 0 | 0,040 |
| hybrid_power_drop | D | 32,1% | 313,0 | 700.157 | 0 | 0,043 |
| hybrid_power_drop | B0 | 41,1% | 325,6 | 770.918 | 0 | 0,003 |
| hybrid_power_drop | M2b | 39,8% | 330,2 | 762.132 | 0 | 0,009 |
| hybrid_power_drop | M3a | 34,7% | 339,6 | 684.297 | 0 | 0,025 |
| hybrid_power_drop | M3b | 34,7% | 335,6 | 695.053 | 0 | 0,025 |

Đọc đúng các số này (ADR-015):

- **An toàn**: 90 / 90 lượt có 0 lần vượt giới hạn nguồn và 0 lệnh bị Guard chặn.
- **Không chiến lược nào đúng hạn hơn baseline.** A_edf đúng hạn cao nhất ở cả hai kịch bản. M3a / M3b **rẻ hơn** A_edf
  khoảng 14–16% nhưng đúng hạn **thấp hơn** (39,8% so với 48,6%; 34,7% so với 46,1%). M2b ≈ B0. Độ lệch chuẩn giữa seed
  16–24 điểm (xem `raw/benchmark.json`) — 5 seed chưa đủ để kết luận thứ hạng.
- Kết quả MVP-3 R&D (M3a / M3b nâng SLA DC) đo trên **fixture khác** (`src/simulator/docs/MVP3_BENCHMARK.md`); kịch bản ở
  đây là phiên tổng hợp của backend (`config/scenarios/`) và KPI của backend. Không so trực tiếp hai bảng.
- Số của LiveStation (`eval/evidence/2026-11-22/`) là engine khác — không trộn với bảng này.
- [GIẢ ĐỊNH] khác HybridSimulator.run(): khoảng quyết định 15' / theo sự kiện; biểu giá backend đổi sang Tariff simulator;
  consent cư dân không là ràng buộc của thuật toán simulator (ADR-018).
- Sửa sau review (consent "được lùi giờ bắt đầu tối đa" trong `hybrid_planner.py`): chạy lại cùng lệnh, KPI **không đổi** —
  phiên tổng hợp của benchmark cho lùi bằng cả thời gian đỗ (`simulation_service.py`, `max_start_delay = dwell`), nên quy
  tắc không kích hoạt. Hiệu lực được kiểm bằng `tests/test_services/test_hybrid_planner.py` (consent 0 ⇒ 11 kW; tắt quy tắc
  ⇒ 0 kW; cho lùi 10 h ⇒ thuật toán tự quyết).
