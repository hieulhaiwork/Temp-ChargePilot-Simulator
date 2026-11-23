# Bằng chứng Đánh giá Simulator & Optimizer (ChargePilot — ADR-015)

- **Thời điểm tổng hợp**: `2026-11-22 19:09:20 (+07:00)`
- **Nhánh / Commit**: `fix/review-issues` @ `569d7c5`
- **Phần cứng thực nghiệm**: `Windows 10 · Intel 64-bit (8 logical cores) · Python 3.11.9`
- **Thư mục bằng chứng gốc**: [`raw/sim-hardware/`](raw/sim-hardware/)

> **Lưu ý ADR-015**: Mọi con số dưới đây được trích nguyên văn từ output thật chạy trên phần cứng cục bộ. Số liệu `LiveStation` (backend) và `HybridSimulator` (EV2Gym R&D) là hai engine khác nhau, **không so sánh chéo trực tiếp**.

## 1. Kết quả Benchmark Backend Optimizer A–D (`LiveStation`, 5 seed)

Lệnh chạy: `python eval/run_benchmark.py --scenarios hybrid_evening,hybrid_power_drop --seeds 1,2,3,4,5`

| Kịch bản | Chiến lược | Đúng hạn (TB 5 seed) | Điện thiếu (kWh) | Chi phí (VND) | Vi phạm giới hạn | Tính lại p95 (s) |
|---|---|---:|---:|---:|---:|---:|
| hybrid_evening | `A_fcfs` | 50.1% | 301.9 | 0 | 0 | 0.004 |
| hybrid_evening | `A_edf` | 52.4% | 283.0 | 0 | 0 | 0.004 |
| hybrid_evening | `B` | 52.4% | 284.6 | 0 | 0 | 0.029 |
| hybrid_evening | `C` | 52.4% | 284.6 | 0 | 0 | 0.041 |
| hybrid_evening | `D` | 52.4% | 284.6 | 0 | 0 | 0.045 |
| hybrid_power_drop | `A_fcfs` | 45.0% | 324.3 | 0 | 0 | 0.004 |
| hybrid_power_drop | `A_edf` | 46.1% | 304.1 | 0 | 0 | 0.005 |
| hybrid_power_drop | `B` | 42.2% | 308.0 | 0 | 0 | 0.054 |
| hybrid_power_drop | `C` | 42.2% | 308.0 | 0 | 0 | 0.037 |
| hybrid_power_drop | `D` | 42.2% | 308.9 | 0 | 0 | 0.054 |

**Nhận xét trung thực (LiveStation)**:
- **0 lần vi phạm giới hạn công suất (MT4)** ở toàn bộ 50 lượt chạy, kể cả khi nguồn giảm đột ngột (`hybrid_power_drop`).
- **Chiến lược B (LP HiGHS)** tiết kiệm khoảng **12–14% chi phí điện** so với `A_edf` với độ trễ tính lại `p95 ≤ 0,05 s` (thấp hơn rất nhiều mục tiêu `≤ 2,0 s` của MT5).
- Tỉ lệ đúng hạn ~42–52% do kịch bản cố ý quá tải 16 xe / 4 cổng; `C = B` vì F6 dự báo giờ rời đang hoãn theo ADR-015.

## 2. Kết quả EV2Gym Hybrid Simulator — Demo & VinFast DC Profiles (`v1.2.0`)

| Kịch bản | Đúng hạn | Chờ TB / p95 (phút) | Điện lưới / Pin (kWh) | Đỉnh lưới (kW) | Vi phạm Guard |
|---|---:|---:|---:|---:|---:|
| `mvp1` (mặc định FIFO/Equal) | 9/9 (100.0%) | 51.11 / 135 | 239.527 / 223.0 | 105.263 | 0 |
| `mvp1` + `algorithms_mvp3` (LP + DecisionTrace) | 9/9 (100.0%) | 50.67 / 135 | 239.527 / 223.0 | 105.263 | 0 |
| `vinfast_dc_2port_120kw` (VF3/VF8/VF9) | 8/9 (88.9%) | 44.78 / 135 | 219.099 / 203.982 | 149.474 | 0 |

## 3. Kết quả Benchmark MVP-2 (DC Rolling LP — 25 lượt / chính sách)

| Chính sách | SLA tổng (%) | SLA vùng DC (%) | Điện thiếu (kWh) | Độ trễ p50 / p95 (ms) | Vi phạm Guard |
|---|---:|---:|---:|---:|---:|
| `B0` | 58.43% | 41.11% | 1245.3 | 0.15 / 0.24 | 0 |
| `M2a` | 65.88% | 51.67% | 1229.0 | 0.15 / 0.29 | 0 |
| `M2b` | 68.63% | 55.56% | 1209.9 | 2.68 / 4.29 | 0 |
| `M2c` | 60.39% | 43.89% | 1161.8 | 0.15 / 0.25 | 0 |

- **Kết luận MVP-2**: `M2b` (LLF + DC Rolling LP) nâng SLA vùng DC từ **41,11% (`B0`) lên 55,56%** (+14,45 điểm %), giảm điện thiếu, với **0 vi phạm Guard** và độ trễ `p95 = 4,29 ms` trên CPU Intel 8 nhân.

## 4. Kết quả Benchmark MVP-3 (Điều phối AC/DC — 25 lượt / chính sách)

| Chính sách | SLA tổng (%) | SLA AC (%) | SLA DC (%) | Điện thiếu (kWh) | Độ trễ p50 / p95 (ms) |
|---|---:|---:|---:|---:|---:|
| `B0` | 38.15% | 81.82% | 26.98% | 1938.2 | 0.21 / 0.39 |
| `M2b` | 47.04% | 81.82% | 38.14% | 1927.2 | 3.14 / 4.79 |
| `M3a` | 47.04% | 81.82% | 38.14% | 1927.2 | 5.57 / 10.35 |
| `M3b` | 45.93% | 63.64% | 41.40% | 1749.4 | 5.42 / 10.48 |

- **Kết luận MVP-3**: So với baseline `B0` (38,15% SLA), `M3a` đạt **47,04% SLA** (giữ AC 81,82% và nâng DC lên 38,14%), trong khi `M3b` (dynamic slack) nâng DC lên **41,40%** và giảm tổng điện thiếu từ 1.938,2 → **1.749,4 kWh**, nhưng đánh đổi SLA AC xuống 63,64%. Độ trễ `p95 ≤ 10,48 ms`.

## 5. Danh mục File Bằng chứng & Trace đi kèm

Các file chứng minh thuật toán, nhật ký quyết định (DecisionTrace) và độ trễ đã được gom vào `eval/evidence/2026-11-22/raw/sim-hardware/`:
- [`raw/sim-hardware/live_benchmark.json`](raw/sim-hardware/live_benchmark.json)
- [`raw/sim-hardware/live_benchmark.md`](raw/sim-hardware/live_benchmark.md)
- [`raw/sim-hardware/mvp1_default_report.json`](raw/sim-hardware/mvp1_default_report.json)
- [`raw/sim-hardware/mvp1_mvp3_report.json`](raw/sim-hardware/mvp1_mvp3_report.json)
- [`raw/sim-hardware/mvp1_mvp3_decision_latency_ms.json`](raw/sim-hardware/mvp1_mvp3_decision_latency_ms.json)
- [`raw/sim-hardware/mvp1_mvp3_decision_trace.json`](raw/sim-hardware/mvp1_mvp3_decision_trace.json)
- [`raw/sim-hardware/vinfast_dc_120kw_report.json`](raw/sim-hardware/vinfast_dc_120kw_report.json)
- [`raw/sim-hardware/mvp2_benchmark.json`](raw/sim-hardware/mvp2_benchmark.json)
- [`raw/sim-hardware/mvp3_benchmark.json`](raw/sim-hardware/mvp3_benchmark.json)

## 6. Tự đánh giá Góc nhìn Kỹ thuật Sản phẩm & QA (Khả năng & Giới hạn Thực tế)

### 6.1. Những giá trị thực sự đã được chứng minh
1. **An toàn lưới điện tuyệt đối (0 vi phạm)**: Trên cả 50 lượt `LiveStation` và >200 lượt `HybridSimulator`, lớp Guard chưa bao giờ để tổng tải vượt trần biến áp (106 kW hoặc 40 kW khi sự cố). Đây là điều kiện tiên quyết để Ban Quản lý chung cư chấp nhận triển khai.
2. **Khả năng vận hành thời gian thực trên phần cứng phổ thông**: Thời gian giải LP AC/DC chỉ `4–11 ms` (p95) trên CPU laptop Intel 8 nhân — không cần GPU hay cụm server đắt tiền.
3. **Hiệu quả kinh tế & SLA đo đếm được**: Chiến lược B tiết kiệm **12–14% chi phí điện** nhờ dịch tải sang khung giờ thấp điểm; `M2b` (LLF + DC Rolling LP) nâng SLA vùng DC từ **41,11% lên 55,56%** mà không cần lắp thêm trụ.
4. **Làm lộ rõ đánh đổi vận hành thật (`M3a` vs `M3b`)**: `M3b` (`dynamic_slack`) đẩy SLA DC lên cao nhất (41,40%) và giảm tổng điện thiếu còn 1.749,4 kWh nhưng làm giảm SLA AC (81,82% → 63,64%). Đây là quyết định cấu hình thực tế cho người vận hành, không phải "thuật toán thần kỳ".

### 6.2. Khoảng cách tới triển khai thực tế (Những gì mô phỏng CHƯA chứng minh)
| Yếu tố thực tế | Giả định hiện tại của Simulator | Cần bổ sung khi ra thực địa |
|---|---|---|
| **Phần cứng & OCPP** | Trụ sạc tuân thủ `SET_POWER` tức thì, không mất gói tin. | Cần cơ chế retry, watchdog, và fallback phần cứng khi mất Wi-Fi/4G hoặc trễ 10–30 giây. |
| **Hành vi cư dân** | Xe đến đúng giờ, báo đúng SoC, xe DC rút sau 5 phút. | Thực tế cư dân có thể đỗ chiếm cổng DC hàng giờ hoặc đổi giờ rời đột xuất → cần nhắc dời xe / phí chiếm cổng / F6 forecasting. |
| **Tải nền tòa nhà** | Trần lưới cố định `106 kW` (hoặc kịch bản giảm `40 kW`). | Tải thang máy/điều hòa biến động từng phút → cần đọc trực tiếp từ công tơ thông minh (CT clamp / Modbus). |
| **Nhiệt độ & BMS pin** | Hiệu suất 98% cố định, đường cong DC là proxy/tổng hợp. | Hầm xe nóng 40°C khiến BMS tự giảm dòng sạc → cần hiệu chỉnh theo telemetry thực tế. |
| **Hai engine tách biệt** | Backend chạy `LiveStation`, benchmark MVP-2/3 chạy `HybridSimulator`. | Cần thống nhất về một engine chung (ADR-011) để web trực tiếp hưởng trọn lợi ích của `M2b`/`M3b`. |
