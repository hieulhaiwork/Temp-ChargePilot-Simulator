# ADR-016: LiveStation — simulator chạy liên tục cho backend; HybridSimulator giữ vai trò R&D offline

- Trạng thái: Proposed — người phụ trách chọn 2026-11-22, chờ nhóm duyệt
- Ngày: 2026-11-22
- Liên quan: **sửa đổi một phần ADR-011** (mục "một simulator"); ADR-002 (Guard là chokepoint), ADR-003, ADR-007, ADR-010
- Bằng chứng: [`eval/evidence/2026-11-22/`](../../eval/evidence/2026-11-22/README.md)

## Bối cảnh

ADR-011 muốn một `HybridSimulator` duy nhất sau `src/simulator/base.py`. Khi nối backend, có ba vướng mắc:

1. `HybridSimulator` (`src/simulator/src/`) chạy trọn một kịch bản trong một lần gọi, với optimizer, coordinator và guard
   riêng của nó. Backend cần một trạm chạy liên tục: nhận lệnh **đã qua** `guard/dispatcher.py` (ADR-002), tiến từng
   bước theo đồng hồ, nhận sự cố lúc đang chạy.
2. `HybridSimulator` bắt buộc import `ev2gym` (kéo theo pandapower, numba, matplotlib…), nặng cho image Render free.
3. Muốn đặt nó sau chokepoint thì phải sửa engine R&D để chạy từng bước và nhận lệnh từ ngoài, tức là đụng code của
   người làm simulator.

## Quyết định

1. Thêm `src/simulator/live.py:LiveStation`, cài đúng Protocol `StationReader` + `StationActuator` của
   `src/simulator/base.py`. Không thêm dependency. Mọi tham số lấy từ `config/station.yaml` (ADR-003).
2. Bề mặt `base.py` thêm `VehicleVisit` và hai hàm **môi trường** `upsert_vehicle` / `remove_vehicle` (xe đến / huỷ),
   cùng loại với `inject_incident`: không phải lệnh điều khiển nên không đi qua Guard. Phần GHI vẫn chỉ có
   `apply_commands`, chỉ dispatcher được gọi (test kiến trúc không đổi).
3. Live (`runtime.get_runtime`) và benchmark backend (`runtime.build_sim_runtime`, `simulation_service.run_scenario`)
   dùng chung `LiveStation` và chung `control_loop.on_event`.
4. `HybridSimulator` giữ nguyên là công cụ R&D / benchmark offline với bộ test riêng (`src/simulator/tests/`). Số liệu
   hai simulator **không** được trộn vào cùng một bảng.

## Mô hình vật lý của LiveStation — [GIẢ ĐỊNH]

- Công suất cổng là công suất đầu ra tủ; năng lượng tích phân Σ p·Δt mỗi phút, đối chiếu `Booking.energy.grid_energy_kwh`.
- **Không mô phỏng đường sạc DC (taper)**: giới hạn xe là hằng số `max_charge_power_kw`. Đây là sai khác lớn nhất so
  với HybridSimulator.
- Xe đầy → cổng FINISHED. Xe AC giữ cổng tới giờ rời khai báo; xe DC rời sau `dc_unplug_delay_minutes` (F14).
- Cổng lỗi giữa chừng → xe quay lại đầu hàng chờ.
- Lệnh sai về vật lý (gán xe chưa đến, sai vùng, cổng bận) bị bỏ qua và ghi log — lưới an toàn cuối sau Guard.

## Hệ quả

- Backend có pipeline đầu–cuối thật: Optimizer → Guard → LiveStation, live và benchmark cùng một đường.
- Benchmark backend đo **LiveStation**, không đo HybridSimulator; mọi báo cáo phải ghi rõ nguồn.
- Khi nhóm quyết đưa HybridSimulator lên runtime (đúng tinh thần ADR-011), cần một adapter cài cùng Protocol và
  một test "live = research" so hai simulator trên cùng kịch bản trước khi thay.
- Mở: thêm taper DC vào LiveStation (dùng lại registry `dc_curve` của ADR-012) hay chuyển hẳn sang HybridSimulator.
