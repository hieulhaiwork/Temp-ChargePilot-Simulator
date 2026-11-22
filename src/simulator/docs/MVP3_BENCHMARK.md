# ChargePilot SC-16 · Nghiệm thu và benchmark MVP-3

**Trạng thái** READY cho review kỹ thuật offline trên worktree `781c3f0`. Policy Dynamic Slack là challenger. Kết quả nguồn chung khan hiếm cần review trước khi chọn policy vận hành.

## Chạy và tái lập

```bash
.simulator/bin/python -m pytest src/simulator/tests src/simulator/tests/ev2gym_smoke.py -q
.simulator/bin/ruff check src/simulator/src src/simulator/run.py src/simulator/benchmark.py src/simulator/benchmark_mvp3.py src/simulator/tests
.simulator/bin/python -m src.simulator.benchmark_mvp3 --output-dir src/simulator/outputs/mvp3_acceptance
.simulator/bin/python -m src.simulator.run --scenario mvp1 --algorithms src/simulator/config/algorithms_mvp3.json --decision-trace --output-dir src/simulator/outputs/mvp3_acceptance
.simulator/bin/python -m src.simulator.benchmark --vinfast-sensitivity --output-dir src/simulator/outputs/mvp3_regression
```

Lượt đo cuối lưu trong `outputs/mvp3_acceptance/mvp3-benchmark-nhrdqc5i/`. `benchmark.json` gồm config/hash từng case, KPI mỗi policy và delta cặp ghép. `latency_records.json` lưu mẫu wall-clock thô của workload chính. Thư mục lưu DecisionTrace của seed 11 cho nguồn chung khan hiếm và source drop ở cả bốn policy. Kết quả nghiệp vụ của 100 lượt chính giống nhau giữa hai lần chạy. Các số liệu latency bên dưới lấy từ lượt cuối. Môi trường dùng Python 3.12.3, EV2Gym 2.0.0, NumPy 2.4.6 và SciPy 1.18.1 trên WSL2 x86-64.

**163 test pass, 0 fail**, từ 138 trước thay đổi. Năm golden cases khóa summary, kết quả xe, events, power trace và frames của MVP-1/EDF/VinFast và M2b trên hai fixture. Hai golden M2b được thu từ HEAD trước chỉnh sửa. Hash, fixture và DC `rolling_lp.py` của MVP-2 giữ nguyên. Test MVP-3 đo AC TOU có deadline sớm, SOC cao, nguồn độc lập, site drop về 0, khôi phục, cabinet derating, no-lookahead với mốc thực thi bị cắt, Guard từ chối yêu cầu vượt cap và fallback ở từng lượt solve AC.

Lượt chạy lại toàn bộ 179 run của MVP-2 cho cùng các KPI cũ sau khi bỏ latency. Báo cáo hồi quy ở `outputs/mvp3_regression/mvp2-benchmark-nyps0hcm/`. CLI với cấu hình MVP-3 xuất 360 trace v2 và 360 bản ghi latency riêng ở `outputs/mvp3_acceptance/20261121T101841984594Z-973fec6d42-4a515037/`.

## Cấu hình và contract

Các fixture cũ tiếp tục dùng `ac_power_budget_kw` và `dc_power_budget_kw`. Scenario mới có thể khai báo cả hai ngân sách qua `default_zone_budget_kw`. Khi cùng xuất hiện, các giá trị phải khớp. Ví dụ trường mở rộng cho mô phỏng bắt đầu 18:00.

```json
{
  "default_zone_budget_kw": {"AC": 22, "DC": 78},
  "physical_zone_cap_kw": {"AC": 22, "DC": 120},
  "grid_input_limit_kw": 106,
  "limit_events": [
    {"effective_at": "18:17", "grid_input_limit_kw": 24},
    {"announced_at": "18:34", "effective_at": "18:49", "grid_input_limit_kw": 106},
    {"effective_at": "19:06", "cabinet_output_limit_kw": {"DC-01": 25}}
  ],
  "tou_tariff": {
    "currency": "USD",
    "periods": [
      {"start": "18:00", "price_per_kwh": 0.45},
      {"start": "19:00", "price_per_kwh": 0.12}
    ]
  }
}
```

- Cap vùng, tủ và ngân sách dùng kW đầu ra. Cap nguồn dùng kW đầu vào. Giới hạn sự kiện duy trì tới cập nhật tiếp theo, nằm trong nameplate và có thể bằng 0. Nếu vắng `announced_at`, runtime biết tại mốc `effective_at`. Lịch tariff là thông tin được công bố từ đầu, có giá ở mọi khoảng đã mô phỏng.
- Nguồn độc lập dùng `independent_grid_input_limit_kw` với khóa AC/DC. Tổng dùng cho báo cáo và từng nguồn được kiểm tra riêng. Sự kiện site grid input áp dụng cho nguồn chung. Sự kiện tủ áp dụng cho cả hai chế độ. Cabinet derating và outage giảm công suất nhưng giữ phiên đang cắm theo lifecycle cũ.
- Coordinator và Guard dùng cùng instance `EffectiveLimits`. Guard xác thực budget trước optimizer và xác thực power trước/sau adapter. Khả năng tiếp nhận riêng từng xe trong trace là `allowed_output_kw`, với cap tủ/vùng/nguồn và budget thể hiện riêng. `actual_output_kw` đến từ phản hồi adapter.
- Fixed Share giữ phần phân bổ và giảm tỷ lệ khi nguồn chung bị cắt. Dynamic Slack xét headroom deadline, phần giữ theo ngân sách và công suất dư theo thứ tự đó. Nhu cầu nằm trong trần của tủ, vùng và nguồn. Chế độ nguồn độc lập chỉ phân bổ trong từng nguồn. Headroom là heuristic theo năng lượng và tốc độ tối đa lạc quan, bỏ tương tác hàng chờ. Lỗi solver được log và kèm mã trong trace. Fallback Equal Share vẫn chịu cùng giới hạn.
- AC LP tối thiểu hóa tổng kWh thiếu tại deadline hoặc cuối run trước khi tối thiểu hóa chi phí lưới trong tập nghiệm có cùng mức thiếu. `block_minutes` mặc định 15, với các boundary ở deadline, tariff và sự kiện giới hạn đã công bố. Future zone budget dùng persistence. Cận taper AC được áp ở SOC cuối block dựa trên pilot crossover của EV2Gym 2.0.0. Adapter thực thi native. Stage 2 ưu tiên nạp sớm khi giá dự báo phẳng.
- DC LP giữ nguyên mô hình và trọng số. Engine cấp cho contract DC cũ view cap vùng/tủ hiện hành, và DC dự báo theo persistence. Planner loại xe chưa đến và giới hạn chưa công bố khỏi observation. API `policy=` legacy giữ forecast roster offline để tương thích caller cũ.
- DecisionTrace v2 lưu policy, yêu cầu và phân bổ của coordinator, lý do dạng mã, effective limits, tariff và sự kiện đã công bố, các dự báo của optimizer, thực thi và Guard. Binding là dữ kiện chạm trần. Trace facts và latency có file riêng, phù hợp làm dữ liệu đầu vào cho replay/counterfactual sau khi có công cụ AI-4.

## Workload và kết quả

Năm family × năm seed 11, 23, 37, 51, 71. Mỗi workload chính chạy 180 phút với timestep danh định 5 phút và tách bước theo sự kiện. Topology 2 AC × 11 kW, 2 DC × 60 kW; mặc định nguồn chung 106 kW, hiệu suất chuyển đổi/sạc 0,95/0,98. Nguồn khan hiếm hạ site xuống 70 kW và dùng chia cố định 22/44 kW. Source drop có mốc +17 xuống 24 kW, +43 xuống 0, +49 phục hồi 106, +66 tủ DC xuống 25 kW và +83 phục hồi. Nguồn độc lập cấp cho mỗi vùng đủ 22/78 kW đầu ra. Tariff synthetic 0,45 / 0,12 / 0,32 USD/kWh lưới ở các mốc +0 / +60 / +145 phút.

| Policy | AC đúng hạn | DC đúng hạn | Tổng đúng hạn | AC / DC shortfall (kWh) | AC / DC unserved | Jain AC / DC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 · Equal Share AC/DC + Fixed | 45/55 | 58/215 | 103/270 | 27,87 / 1.910,33 | 0 / 69 | 0,9925 / 0,5523 |
| M2b · AC Equal Share + DC LP + Fixed | 45/55 | 82/215 | 127/270 | 27,87 / 1.899,35 | 0 / 76 | 0,9925 / 0,6013 |
| M3a · AC/DC LP + Fixed | 45/55 | 82/215 | 127/270 | 27,87 / 1.899,35 | 0 / 76 | 0,9915 / 0,6013 |
| M3b · AC/DC LP + Dynamic Slack | 35/55 | 89/215 | 124/270 | 24,77 / 1.724,67 | 0 / 71 | 0,9862 / 0,6301 |

`unserved` là nhận tối đa 1e-7 kWh pin. DC abandoned lần lượt 69, 73, 73, 70. Waiting mean/p95 DC lần lượt 37,02/67, 36,30/85, 36,30/85, 36,23/85 phút. Mọi policy có AC chờ 17,80/98 phút. Waiting tính cả xe rời hàng. Jain dùng tỷ lệ năng lượng đã đáp ứng cho toàn bộ xe của vùng.

| Policy | TOU AC / DC / tổng (USD) | Decision p50/p95/max (ms) | Solver AC p50/p95/max (ms) | Solver DC p50/p95/max (ms) |
| --- | ---: | ---: | ---: | ---: |
| B0 | 158,09 / 758,06 / 916,15 | 0,152 / 0,241 / 0,667 | — | — |
| M2b | 158,09 / 759,79 / 917,88 | 2,061 / 3,018 / 4,814 | — | 1,546 / 2,009 / 3,351 |
| M3a | 136,34 / 759,79 / 896,13 | 3,618 / 6,976 / 11,037 | 2,970 / 3,556 / 6,778 | 1,520 / 1,904 / 2,429 |
| M3b | 139,98 / 813,21 / 953,20 | 3,679 / 6,856 / 27,417 | 2,958 / 3,433 / 3,930 | 1,527 / 1,936 / 22,743 |

Decision latency gồm cập nhật hàng chờ, observation, coordinator, optimizer và Guard trước thực thi. Solver latency AC cộng hai lời gọi HiGHS mỗi interval. Chi phí thực tích phân grid kWh × giá, riêng theo vùng và toàn site. Công suất/giá do simulator khai báo. Các mức giá vắng mặt ở fixture golden nên KPI TOU ở đó là null.

| Family | B0 AC/DC đúng hạn | M2b AC/DC | M3a AC/DC | M3b AC/DC |
| --- | ---: | ---: | ---: | ---: |
| AC flexibility/TOU | 15/15 · 20/20 | 15/15 · 20/20 | 15/15 · 20/20 | 15/15 · 20/20 |
| DC congestion | 5/5 · 14/55 | 5/5 · 22/55 | 5/5 · 22/55 | 5/5 · 30/55 |
| Shared-source scarcity | 15/15 · 3/30 | 15/15 · 7/30 | 15/15 · 7/30 | 4/15 · 9/30 |
| Site curtailment | 5/15 · 7/55 | 5/15 · 11/55 | 5/15 · 11/55 | 6/15 · 8/55 |
| Independent supply | 5/5 · 14/55 | 5/5 · 22/55 | 5/5 · 22/55 | 5/5 · 22/55 |

Trên 100 run chính và bốn control, Guard rejections, applied violations và fallback quan sát được đều 0. Sai số audit năng lượng lớn nhất là 5,68e-14 kWh cho bộ chính và 6,82e-13 kWh cho legacy controls, trong dung sai 1e-6 kWh. Audit tích phân output/input, đối chiếu năng lượng pin với SOC từng xe, kiểm tra effective caps và kiểm tra không có interval sạc cắt qua mốc đổi giá/giới hạn. Test ép timeout xác nhận fallback được log và qua Guard.

## Kết quả âm tính và phạm vi kết luận

- **M3a giữ 127/270 SLA** và giảm 21,75 USD TOU so với M2b. Trên AC flexibility, chi phí AC giảm từ 61,07 còn 44,34 USD và giữ 15/15 SLA. TOU tối ưu trên dự báo hiện tại và mục tiêu tổng kWh thiếu. Ở scarcity, cùng tổng kWh thiếu có thể có số phiên SLA khác nhau.
- **M3b thêm 7 SLA DC** so với M3a, giảm shortfall DC 174,68 kWh và giảm unserved DC 5. M3b mất 10 SLA AC, tổng SLA giảm 3, và chi phí TOU tăng 57,07 USD. M3b giao thêm 177,77 kWh pin trên toàn site. Kết quả chi phí cần đọc cùng năng lượng phục vụ.
- Ở scarcity seed 11 tại 18:09, Fixed Share cấp AC/DC 22/44 kW; Dynamic cấp 6,5/60 kW, với headroom DC 60 kW do heuristic tín hiệu deadline. Tất cả năm seed scarcity giảm SLA AC với Dynamic. Site curtailment giảm SLA DC ở bốn trong năm cặp dù tổng shortfall DC của family giảm. Ở đối chứng nguồn độc lập, fixed/dynamic có cùng SLA và công suất dư AC không được chuyển sang DC.
- Review nghiệp vụ nên chốt mức bảo vệ SLA/coverage theo vùng khi phân bổ thiếu nguồn. Headroom hiện có thể dồn tới trần cho xe với deadline bất khả thi. Một phase nghiên cứu sau có thể kiểm nghiệm điều này bằng counterfactual hoặc oracle nhỏ. Joint LP là challenger tùy chọn và nằm ngoài ma trận MVP-3 đã đo.

DoD áp dụng cho simulator offline. Taper DC synthetic, cận taper AC, ngân sách dự báo persistence, bước thời gian, deadline và giả định nguồn đều giới hạn khả năng suy rộng. Chưa có hiệu chuẩn trạm thực hoặc chứng minh tối ưu toàn cục. DecisionTrace cung cấp dữ kiện, chưa thực hiện WHAT-IF hay suy diễn nguyên nhân.
