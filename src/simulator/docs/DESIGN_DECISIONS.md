# Modular simulator v1.2

Refactor áp dụng cho simulator offline của ChargePilot. Một runtime
`HybridSimulator` sử dụng EV2Gym 2.0.0 EV/EV_Charger và DC extension của
ChargePilot. Baseline giữ FIFO/FCFS, equal-share, ngân sách cố định và
`synthetic_taper_v1`.

## Khảo sát và điểm ghép

| Trước v1.2 | Sau v1.2 |
| --- | --- |
| `QueueController.advance()` tự lấy đầu hàng | `DispatchPolicy` đề xuất, Guard xác thực, controller thi hành |
| Một `SchedulingPolicy` chia công suất cả hai khu | Hai `ZonePowerOptimizer` nhận ngân sách và danh sách ứng viên riêng |
| `Scenario.zone_kw` vừa là giới hạn vừa là ngân sách chạy | Scenario là giới hạn bất biến, `ZoneBudgets` là phân bổ đã gắn với khoảng thời gian |
| `DCEV` chứa cả công thức taper và cập nhật EV state | `DCChargingModel` tính acceptance/năng lượng, adapter cập nhật EV state |
| Guard nằm cùng file với equal-share | `safety/guard.py` độc lập và bắt buộc. Registry không chọn được chế độ bỏ guard |

```text
run.py → algorithms.py → registry gồm các implementation tin cậy
       → engine/hybrid.py
           → engine/queue.py + DispatchPolicy → safety/guard.py (validate_dispatch)
           → EV2GymAdapter → EV2Gym AC / DCChargingModel
           → GlobalCoordinator → safety/guard.py (validate_budgets)
           → AC optimizer + DC optimizer → guard → EV2GymAdapter
           → validate_response + guard → ledger → evaluation/metrics.py + export/replay
```

## Contract và thứ tự một bước

1. Controller xử lý rời/rút rồi nhận xe đến. `DispatchPolicy(observation)`
   nhận khu, timestamp, tuple cổng trống và hàng chờ, trạng thái xe chỉ đọc.
   Kết quả là cặp cổng → ID xe đang chờ của khu. Guard kiểm tra cả hai kế
   hoạch trước khi cắm. Controller áp dụng theo thứ tự cổng của fixture.
   Nếu EV2Gym chọn slot trống đầu tiên khác slot đã duyệt, adapter chỉ dời
   **xe vừa spawn** tới slot được chọn và đối chiếu occupancy. Xe đã cắm
   giữ cổng cho đến boundary rời/rút theo chính sách hiện hành.
2. Core xác định độ dài khoảng đến mốc sự kiện kế tiếp. Adapter cung cấp
   acceptance của xe và headroom tới mục tiêu pin. Core kết hợp với cap
   cổng để tạo ứng viên. `GlobalCoordinator(observation, demand_kw)`
   nhận tổng acceptance ứng viên theo khu trước khi áp cap tủ. Coordinator
   trả `ZoneBudgets(minute, interval_minutes, output_kw)`, với kW đầu ra.
   Guard từ chối ngân sách lệch timestamp/độ dài khoảng, thừa/thiếu khu,
   không hữu hạn hoặc vượt trần khu/nguồn.
3. `ZonePowerOptimizer(observation, zone, budget_kw)` đề xuất map
   ID → kW đầu ra. Snapshot ghi SOC phân số, deadline, xe chờ/sắp đến,
   occupancy, ứng viên của riêng khu và các giới hạn vật lý. Xe bị bỏ qua
   nhận setpoint 0. Engine ghép hai map và gọi Guard trên kế hoạch tổng.
   Cổng, tủ, xe, ngân sách được cấp, trần khu và nguồn chung đều được kiểm tra.
   Lối gọi Python `policy=` v1.1 được giữ cho test/experiment cũ, đi qua
   cùng Guard và ngân sách. CLI luôn dùng hai module optimizer.
4. Adapter chạy `EV.step()` cho AC. DC nhận `VehicleBatteryState` chỉ đọc
   và trả acceptance (kW) hoặc năng lượng vào pin (kWh), ứng với khoảng
   phút và hiệu suất cấu hình. Adapter cập nhật các trường năng lượng
   được hỗ trợ. Guard kiểm tra response, SOC, chênh lệch năng lượng, setpoint
   và tổng công suất. Các giá trị replay đầu khoảng được ghi kèm mức
   thực thi trung bình trong khoảng. Phản hồi thất bại làm dừng run như v1.1.
5. Ledger ghi event và state thực thi. Runner xuất JSON/CSV/HTML với schema
   replay v1, kèm metadata thuật toán. CSV tiếp tục dùng cấu trúc v1.

Scenario và records quan sát là frozen dataclass. Map được bọc chỉ đọc,
queue được sao chép thành tuple. EV2Gym object chỉ xuất hiện trong adapter.
Guard kiểm tra map đầu ra trước khi sử dụng. Bộ đếm
`rejected_allocation_count` gồm dispatch/budget/setpoint hoặc acceptance
bị từ chối trước bước nạp năng lượng. Bộ đếm
`applied_constraint_violation_count` dành cho lỗi hậu kiểm response.
Rollback khi lỗi giữa bước vẫn là điểm mở.

## Bằng chứng tương thích

Baseline lấy từ Git `f7eaac898df6506a83a19c4e62c530dac76d5d09`, EV2Gym
2.0.0, fixture SHA-256
`973fec6d427c442adc7f6f7db58259293374b58f4f617bc26a78bcf9332bb5d2`.

```bash
.simulator/bin/python -m src.simulator.run --scenario mvp1 --output-dir /tmp/p019-modular-before
.simulator/bin/python -m src.simulator.run --scenario mvp1 --output-dir src/simulator/outputs/modular_default
.simulator/bin/python -m src.simulator.run --scenario mvp1 --algorithms src/simulator/config/algorithms_edf_demo.json --output-dir src/simulator/outputs/modular_edf
.simulator/bin/python -m pytest src/simulator/tests src/simulator/tests/ev2gym_smoke.py -q
```

Lệnh đầu chạy trên revision trước refactor. Sau refactor, report và replay
khớp từng giá trị sau khi bỏ trường version và metadata. Events JSON và
hai CSV khớp từng byte. KPI giữ 9/9 đúng hạn, chờ 51,11/135 phút,
239,527 kWh lưới, 223,000 kWh pin và đỉnh 105,263 kW.

Suite simulator đạt 88 test, gồm 54 test cũ và 34 ca module hóa.
Chromium đọc được replay nhúng và nạp lại JSON cho cả hai cấu hình, kiểm tra
Step/Seek, thứ tự hàng chờ và occupancy ở bốn mốc. Lệnh
`.simulator/bin/python -m pytest --collect-only -q` ở cấp repo dừng vì API
cũ import `src.simulator.base`. Cùng lỗi được tái lập trên bản archive
của `f7eaac8`.

## Phạm vi mô hình

DC mặc định dùng `synthetic_taper_v1`, một taper giả định của ChargePilot
trên SOC phân số [0, 1]. Thay model không đổi công thức room-to-target của
adapter hay các trần Guard. Test với profile ước lượng thay thế và cap xe
24 kW là input giả định có chủ đích. VF3/VF8/VF9 chưa có đường cong thực
nghiệm được xác nhận ở đây. Chia sẻ chung nguồn AC/DC và công suất tủ của
fixture là giả định mô phỏng.

Registry có coordinator ngân sách cố định. Contract một lượt cấp ngân sách
có thể tiếp nhận implementation khác trong phạm vi trần site/zone bất biến.
Các bước phối hợp lặp, ngân sách thích nghi, giới hạn site thay đổi theo thời
gian, dữ liệu hiệu chuẩn, MPC và benchmark chính thức nằm ở vòng sau. EDF và
deadline-first chỉ là ví dụ thử giao diện.

# Mở rộng MVP-3 · AC/DC coordinated optimization

`Scenario.default_zone_budget_kw` giữ phân bổ cố định, với `Scenario.zone_kw`
là alias tương thích trên scenario legacy. `physical_zone_cap_kw` là trần thiết bị ở
đầu ra. Scenario cũ dùng ngân sách làm trần vùng khi trường này vắng mặt. Engine tạo
một `EffectiveLimits` bất biến cho mỗi interval, đưa cùng instance vào dispatch,
coordinator, xác thực ngân sách và Guard trước/sau adapter. Trong nguồn chung,
output AC + DC bị giới hạn bởi grid input × hiệu suất chuyển đổi. Trong nguồn độc lập,
từng vùng có giới hạn grid input riêng. Công suất dư chỉ được chuyển vùng trong
nguồn chung.

Boundary của runtime gồm xe đến/rời/rút, giá TOU, công bố giới hạn và mốc giới hạn
có hiệu lực. Planner thấy roster đã đến và lịch giới hạn đã công bố. Một sự kiện
bất ngờ có thể ngắt thực thi, sau đó engine tính lại giới hạn và giải lại. Công bố giá
TOU trong config có hiệu lực thông tin từ đầu run. Mô hình kế thừa cho `policy=`
v1.1 giữ khả năng nhìn roster offline.

Fixed Share giảm tỷ lệ phần chia khi nguồn chung giảm và giữ phần chia của từng vùng.
Dynamic Slack phân bổ nhu cầu xe đang cắm theo headroom deadline lạc quan, phần giữ
theo ngân sách cố định, rồi phần nguồn chung còn dư. Nhu cầu được chặn bởi nguồn,
trần vùng và tổng nhu cầu khả thi theo tủ. Các bước thiếu nguồn chia tỷ lệ trong
cùng bước. Hai cơ chế đều đi qua `ZoneBudgets`; diagnostics đi vào DecisionTrace.

AC LP giải hai bài liên tiếp. Lượt đầu tối thiểu hóa tổng kWh thiếu tại deadline hoặc
kết thúc mô phỏng. Lượt hai giữ mức đó rồi giảm chi phí TOU dự kiến theo kWh đầu vào
lưới. Với giá bằng nhau, lượt hai ưu tiên nạp sớm. Các block kết thúc tại mốc
deadline, tariff và giới hạn đã công bố, với dự báo ngân sách hiện tại giữ nguyên.
Cận taper AC chặn pilot sao cho SOC cuối block ở trong miền native EV2Gym có thể giữ
pilot đó. Adapter vẫn xử lý phản hồi native. DC optimizer MVP-2 giữ nguyên mã và
tham số. Engine chuyển trần hiệu lực vào view `Scenario` của optimizer legacy để
DC tiếp tục dùng contract cũ.

DecisionTrace v2 giữ dữ kiện quyết định, lý do phân bổ dạng mã, giới hạn hiệu lực,
lịch đã công bố, chi phí/shortfall dự báo và kW yêu cầu, được phép, thực tế. Binding
chỉ phản ánh quan sát chạm giới hạn. Latency wall-clock vẫn xuất riêng. Xem
[workload, KPI và giới hạn MVP-3](MVP3_BENCHMARK.md).
