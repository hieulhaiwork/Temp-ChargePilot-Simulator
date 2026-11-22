# ChargePilot SC-16 · Bằng chứng triển khai MVP-2

**Trạng thái triển khai** READY để Tech Lead review trên simulator offline, ngày 2026-11-21. Mốc kiểm chứng là worktree trên `d15871a`, với EV2Gym 2.0.0, Python 3.12.3, NumPy 2.4.6 và SciPy 1.18.1 trên WSL2 x86-64.

## Tái lập

Chạy từ thư mục gốc repo bằng môi trường cài từ `src/simulator/requirements.txt`.

```bash
.simulator/bin/python -m pytest src/simulator/tests src/simulator/tests/ev2gym_smoke.py -q
.simulator/bin/ruff check src/simulator/src src/simulator/run.py src/simulator/benchmark.py src/simulator/tests
.simulator/bin/python -m src.simulator.run --scenario mvp1 --output-dir /tmp/p019-mvp2-final-mvp1
.simulator/bin/python -m src.simulator.run --scenario vinfast_dc_2port_120kw --output-dir /tmp/p019-mvp2-final-vinfast
.simulator/bin/python -m src.simulator.run --scenario mvp1 --algorithms src/simulator/config/algorithms_mvp2.json --decision-trace --output-dir src/simulator/outputs/mvp2_acceptance
.simulator/bin/python -m src.simulator.benchmark --vinfast-sensitivity --output-dir src/simulator/outputs/mvp2_acceptance
```

Suite đã đo **112 pass trước khi sửa** và **138 pass, 0 fail sau khi sửa**. Ba test golden, 23 test MVP-2, Ruff và `git diff --check` đạt. Các test MVP-2 kiểm tra FCFS/EDF/LLF khi xe đến đồng thời và cổng đang bận, ngân sách và trần tủ, input âm, lỗi solver, timeout thiếu nghiệm và có nghiệm khả thi, nghiệm sai kích thước/âm/vượt cap/NaN, tính tất định của trace và mốc đến ngoài lưới thời gian. Trong test mốc đến, 2 và 8 phút cho cùng setpoint khi khoảng lập kế hoạch tại phút 0 là 10 phút. Thời lượng và năng lượng thực thi thay đổi theo sự kiện đến thực tế.

Kết quả lượt đo cuối nằm ở `outputs/mvp2_acceptance/mvp2-benchmark-xivmrdpy/`. `benchmark.json` lưu tham số đầy đủ, SHA-256, KPI từng scenario, tổng hợp theo family/policy và chênh lệch từng cặp. `latency_records.json` lưu mẫu wall-clock theo interval và policy. Hai lượt benchmark cho cùng nội dung sau khi bỏ các thống kê wall-clock. `--decision-trace` của runner tạo thêm hai file JSON tách riêng cho facts và latency. Run mẫu nằm ở `outputs/mvp2_acceptance/20261121T092803548106Z-973fec6d42-96ccfc03/`.

## Mô hình thực thi

`HybridSimulator` đi qua `QueueController`, DC `DispatchPolicy`, `GlobalCoordinator`, DC `ZonePowerOptimizer`, Physical Guard, `EV2GymAdapter` và evaluation. Guard kiểm tra phép gán và ngân sách ngay tại ranh giới tương ứng, rồi kiểm tra cả setpoint và thực thi. AC tiếp tục gọi `EV.step()` qua adapter. `FixedBudgetCoordinator` cấp ngân sách đầu ra trước khi optimizer được gọi.

- **LLF** tính phút đến deadline trừ `remaining_kwh × 60 / (max_available_output_kw × charging_efficiency)`. Trần độc lập là min của cap xe, cap cổng trống tốt nhất, cap tủ và trần khu static. Ngân sách cấp cho từng khoảng được quyết định sau dispatch. Laxity lạc quan vì bỏ taper và tranh chấp công suất. Nếu không có tốc độ dương, trace lưu laxity `null` và cờ rủi ro. LLF xếp nhóm laxity âm sau nhóm khả thi, rồi xét mức thiếu nhỏ nhất trong nhóm âm, thời điểm đến và ID. Quy tắc này ưu tiên cơ hội hoàn thành của xe còn khả thi và có thể làm tăng thời gian chờ hoặc bỏ hàng ở nhóm khó phục vụ.
- **Rolling LP** lập kế hoạch từng xe DC đã cắm theo block, giữ khoảng đầu theo mốc sự kiện đã biết. Horizon mặc định 120 phút, block sau mặc định 5 phút và cắt ở deadline. Ngân sách, cap khu/tủ/cổng được giữ theo giả định persistence. Trần block đầu lấy từ adapter và cùng `DCChargingModel`. Các block sau dùng cận affine theo năng lượng đã dự kiến nạp, khớp thấp hơn hoặc bằng 9 mẫu acceptance từ SOC hiện tại tới target tại điểm lấy mẫu. Cận này có thể bảo thủ và là xấp xỉ giữa các mẫu. LP giới hạn kWh tới target, gán công suất 0 sau deadline, dùng slack để đo shortfall tới deadline hoặc mốc kết thúc horizon. Chỉ setpoint block đầu đi qua Guard và tới adapter.
- **Objective** đặt hệ số 1 cho mỗi kWh shortfall, cộng 4 chia cho nhu cầu còn lại với mẫu số tối thiểu 1 kWh khi deadline nằm trong horizon. Đó là proxy SLA theo phần nhu cầu chưa đáp ứng. Hệ số nạp sớm 0,02 và hệ số hàng chờ 0,5 tạo phần thưởng giảm dần theo thời gian. Phần thưởng hàng chờ cũng chia theo nhu cầu còn lại. Weighted LP dùng proxy liên tục cho việc giải phóng cổng, vì cổng chỉ được nhả qua lifecycle hiện tại. Kết quả phụ thuộc vào trọng số, thiếu bảo đảm thứ tự ưu tiên tuyệt đối.
- **Fallback** dùng DC Equal Share với cùng budget/caps. `linprog(method="highs")` có time limit 0,2 giây. Status khác 0 dùng fallback, kể cả status 1 kèm primal. Với status 0, optimizer kiểm tra kích thước, số hữu hạn, bounds, tổng năng lượng và các ràng buộc LP trước khi gửi setpoint. Guard của engine vẫn xác thực kế hoạch tổng. [Tài liệu SciPy HiGHS](https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html)
- **Quan sát online** loại xe chưa đến khỏi snapshot, kể cả roster lồng trong `Scenario` được truyền cho module. Coordinator và LP dùng khoảng lập kế hoạch dựa trên timestep, deadline và mốc rút đã biết. Engine thực thi đến mốc đến/rời/rút thực tế. Các optimizer MVP-1 giữ room-to-target theo khoảng thực thi cũ để giữ tương thích trên bước bị cắt. API thử nghiệm `policy=` v1.1 giữ snapshot offline theo contract hiện có và nằm ngoài luồng benchmark.
- **DecisionTrace** lưu danh sách chờ trước dispatch, phép gán, occupancy sau dispatch, SOC và deadline, ngân sách, cap vật lý, requested/allowed/actual output, pin/lưới, projected shortfall và trạng thái solver/fallback bằng mã. Binding chỉ ghi khi giới hạn kiểm tra được sát setpoint hoặc actual trong dung sai. Latency dùng `perf_counter()` và nằm ngoài trace facts. Decision latency tính từ trước khi xử lý hàng chờ đến hết Guard đầu vào, gồm tạo observation, dispatch, cấp ngân sách và kế hoạch. Solver latency chỉ đo lời gọi HiGHS, với mẫu lấy từ interval thực sự gọi solver.

## Workload và KPI

`benchmark.py` khóa năm seed 11, 23, 37, 51, 71 cho từng family. Mỗi scenario kéo dài 165 phút, bước 1 phút, bắt đầu 18:00. Xe DC theo các template trong mã. Seed thay đổi giờ đến sau lượt đầu ±2 phút, thời gian lưu trú ±5 phút và SOC đầu ±0,02. AC dùng cùng ba xe trong mọi lượt. Topology là 2 AC × 11 kW và 2 DC × 60 kW trên tủ DC 120 kW. Site grid input 106 kW, ngân sách đầu ra AC/DC 22/78 kW, hiệu suất chuyển đổi/sạc 0,95/0,98 và DC unplug delay 5 phút. Các policy chạy cùng workload, nguồn điện, physics và cách tính KPI. Chính sách và workload được giữ qua hai lượt thực thi.

Waiting gồm mọi xe đến, từ lúc đến tới khi cắm, rời hàng hoặc kết thúc horizon nếu còn chờ. `unserved` là phiên nhận ≤1e-7 kWh. `abandoned` là rời hàng trước khi cắm. Jain DC tính theo tỷ lệ kWh pin được đáp ứng trên nhu cầu của tất cả xe DC. Shortfall là nhu cầu pin còn lại tại cuối run. P50/p95 dùng nearest rank trên các mẫu gộp.

| Policy | DC SLA | AC SLA | Overall SLA | Chờ DC mean/p95 (phút) | Chờ chung mean/p95 (phút) | DC unserved/abandoned | DC shortfall (kWh) | Jain DC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 · FCFS + Equal Share | 74/180 · 41,11% | 75/75 | 149/255 · 58,43% | 26,15 / 60 | 25,13 / 68 | 31/31 · 17,22% mỗi chỉ số | 1.245,34 | 0,7238 |
| M2a · LLF + Equal Share | 93/180 · 51,67% | 75/75 | 168/255 · 65,88% | 25,92 / 67 | 24,96 / 68 | 37/37 · 20,56% mỗi chỉ số | 1.229,03 | 0,7486 |
| M2b · LLF + Rolling LP | 100/180 · 55,56% | 75/75 | 175/255 · 68,63% | 25,94 / 70 | 24,98 / 68 | 38/38 · 21,11% mỗi chỉ số | 1.209,89 | 0,7479 |
| M2c · EDF + Equal Share | 79/180 · 43,89% | 75/75 | 154/255 · 60,39% | 26,08 / 66 | 25,07 / 68 | 4/4 · 2,22% mỗi chỉ số | 1.161,80 | 0,8470 |

| Policy | Pin / charger output / lưới (kWh) | Decision p50 / p95 / max (ms) | Solver p50 / p95 / max (ms) |
| --- | ---: | ---: | ---: |
| B0 | 3.039,409 / 3.101,437 / 3.264,671 | 0,091 / 0,139 / 0,609 | — |
| M2a | 3.055,716 / 3.118,077 / 3.282,186 | 0,093 / 0,142 / 30,812 | — |
| M2b | 3.074,862 / 3.137,615 / 3.302,752 | 1,755 / 2,794 / 39,791 | 1,509 / 1,952 / 39,019 |
| M2c | 3.122,946 / 3.186,679 / 3.354,399 | 0,092 / 0,142 / 0,828 | — |

Mỗi policy chính có 4.125 decision intervals. M2b có 2.082 mẫu solver. Decision p95 quan sát của M2b đạt mục tiêu 2.000 ms trên topology 4 cổng này. Dao động wall-clock giữa các lượt bao gồm nhiễu hệ điều hành. Timeout có thể làm hai lần chạy chọn fallback ở các interval khác nhau trên môi trường khác.

| Family | B0 | M2a | M2b | M2c |
| --- | ---: | ---: | ---: | ---: |
| DC queue pressure | 15/55 | 20/55 | 22/55 | 13/55 |
| Deadline scarcity | 5/30 | 10/30 | 13/30 | 11/30 |
| High-SOC taper | 20/35 | 22/35 | 22/35 | 22/35 |
| Feasible/infeasible mix | 14/40 | 21/40 | 23/40 | 13/40 |
| No congestion | 20/20 | 20/20 | 20/20 | 20/20 |

No-congestion có chờ DC mean/p95 bằng 0 ở mọi policy. Theo số phiên DC đúng hạn trên 25 cặp, M2a thắng/hòa/thua B0 **13/11/1**, M2b **16/9/0**, M2c **7/15/3**. M2b so với M2a là **8/15/2**.

- M2a mất một phiên so với B0 ở `queue_pressure` seed 23. M2b mất một phiên so với M2a ở `queue_pressure` seed 11 và `feasible_infeasible_mix` seed 51.
- M2b nâng DC SLA tổng hợp 14,44 điểm phần trăm so với B0. Đồng thời p95 chờ DC tăng 10 phút, số unserved tăng 7 và kWh shortfall cao hơn B0 ở hai family queue pressure và feasible/infeasible mix. EDF có nhiều phiên nhận được năng lượng hơn, shortfall thấp nhất và Jain cao nhất trong suite.
- Đặt `sla_weight=0` giữ nguyên DC SLA ở cả 25 cặp, shortfall tổng 1.209,80 kWh. Đặt `queue_weight=0` giảm từ 100 xuống 97 phiên, thắng/hòa/thua mặc định 4/15/6, shortfall 1.221,36 kWh. Đặt `queue_weight=5` giữ tổng 100, chuyển kết quả ở hai cặp (1/23/1), giảm shortfall còn 1.204,58 kWh và tăng unserved từ 38 lên 39. Các kết quả không xác lập một bộ trọng số tối ưu.
- VinFast opt-in dùng topology fixture riêng. DC đúng hạn ở B0/M2a/M2b/M2c lần lượt 4/5, 5/5, 5/5, 5/5. Trên 200 dự báo theo xe-interval của M2b, sai lệch tuyệt đối cực đại giữa dự báo tuyến tính và thực thi là 0,374354 kW và 0,006114 kWh pin. Suite SyntheticTaperV1 có sai lệch tương ứng 7,11e-15 kW và 1,11e-16 kWh, phù hợp với mô hình vật lý lấy acceptance tại đầu bước.

## Golden, Guard và năng lượng

Fixture, hash golden và dữ liệu R&D benchmark giữ nguyên. 15 hash gốc của Claude khớp với worktree trước khi tích hợp. Sau tích hợp, cả năm phần `summary`, `vehicles`, `events`, `power_trace`, `frames` vẫn khớp trên ba cấu hình.

| Golden | SLA | Chờ started-only mean/p95 (phút) | Pin / lưới (kWh) | Peak grid (kW) | Events / frames / power intervals |
| --- | ---: | ---: | ---: | ---: | ---: |
| mvp1 mặc định | 9/9 | 51,11 / 135 | 223,000 / 239,527 | 105,263 | 36 / 361 / 360 |
| mvp1 EDF demo v1.2 | 9/9 | 54,56 / 135 | 223,000 / 239,527 | 86,316 | 36 / 361 / 360 |
| VinFast fixture | 8/9 | 44,78 / 135 | 203,982 / 219,099 | 149,474 | 35 / 361 / 360 |

So sánh hai fixture qua runner trước/sau cho `events.json`, `vehicles.csv` và `power_trace.csv` giống từng byte. `report.json` và `replay.json` khớp sau khi bỏ `command` và `run_id`. Snapshot trước sửa gồm kết quả từng xe và đầy đủ payload ở `/tmp/p019-mvp2-baseline-mvp1.json` và `/tmp/p019-mvp2-baseline-vinfast_dc_2port_120kw.json`.

Trong 179 run (100 policy chính, 75 độ nhạy trọng số, 4 VinFast), fallback, kế hoạch solver bị loại, kế hoạch Guard từ chối và applied violations đều bằng **0**. Các nhánh lỗi/fallback được kiểm tra bằng test ép lỗi. Audit độc lập kiểm tra setpoint/actual theo giới hạn, tích phân công suất từng interval, đối chiếu cả ledger từng xe và SOC cuối. Guard dùng dung sai 1e-7 theo đơn vị kiểm tra. Audit năng lượng dùng dung sai tuyệt đối 1e-6 kWh, với sai số lớn nhất toàn ma trận 3,98e-13 kWh. Trên 175 run synthetic, sai số lớn nhất là 1,71e-13 kWh.

## Giới hạn và điểm nối

Đây là benchmark exploratory trên hai cổng DC và năm seed, với synthetic DC taper, LLF lạc quan, horizon hữu hạn và persistence. Acceptance tuyến tính tương lai có sai số khi chuyển block hoặc khi curve đổi nhanh. Thực thi theo phút, thời điểm nhả cổng theo lifecycle và delay cấu hình. VinFast v0.1 dùng đường cong nghiên cứu ước lượng. Chưa có hiệu chuẩn dữ liệu trạm thực, kiểm chứng trên mạng điện thực hoặc đo p95 trên topology lớn hơn.

Các điểm nối cho vòng review MVP-3 gồm `DispatchPolicy` và `DispatchObservation`, `GlobalCoordinator` và `ZoneBudgets`, `ZonePowerOptimizer` với `SchedulingObservation` và `PowerProposal`, `DCChargingModel`, Physical Guard và DecisionTrace v1. Schema `Scenario.zone_kw` và phân biệt trần/ngân sách hiện tại được giữ để review tiếp. Đầu việc MVP-3 chờ Tech Lead review.
