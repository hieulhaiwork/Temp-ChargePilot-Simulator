# ChargePilot EV2Gym Hybrid Simulator v1.2

MVP1 mô phỏng bãi sạc AC/DC offline bằng **EV2Gym-based hybrid/DC extension**.
Kịch bản `scenario/mvp1.json` giữ nguyên fixture 9 xe synthetic. Hai cổng AC
giới hạn 11 kW/cổng, một tủ DC có hai cổng 60 kW/cổng. Nguồn chung 106 kW,
ngân sách đầu ra AC 22 kW và DC 78 kW là giả định của fixture.

## Chạy demo

Từ thư mục gốc repository, tạo môi trường simulator bằng Python 3.12 nếu
chưa có. Manifest này cài EV2Gym, dependency cho smoke test môi trường Gym
upstream và công cụ test/lint.

```bash
python3.12 -m venv .simulator
.simulator/bin/python -m pip install -r src/simulator/requirements.txt
```

```bash
.simulator/bin/python -m src.simulator.run --list-scenarios
.simulator/bin/python -m src.simulator.run --scenario mvp1
.simulator/bin/python src/simulator/run.py --scenario src/simulator/scenario/mvp1.json --output-dir /tmp/chargepilot-demo
```

Mở đường dẫn `viewer.html` do lệnh in ra bằng trình duyệt. Trang tự chứa dữ liệu
replay, chạy với `file://` và có thể mở `replay.json` của run khác. Trang gốc
nằm trong `frontend/public/chargepilot-replay.html`, cũng có thể mở trực tiếp
để nạp tệp JSON. Viewer dùng HTML/JavaScript và SVG, phát hành qua thư mục
public của web app hiện có và dùng chung một template khi xuất file offline.
Replay chỉ cần trình duyệt. Các dependency vẽ đồ thị Python trong
`requirements.txt` phục vụ smoke test EV2Gym upstream.

Mỗi lượt tạo thư mục riêng `src/simulator/outputs/<scenario>/<run-id>/`
hoặc dưới `--output-dir`. Run ID gồm thời gian UTC, hash fixture và hậu tố
ngẫu nhiên. Git bỏ qua thư mục đầu ra mặc định.

| Tệp | Nội dung |
| --- | --- |
| `report.json` | KPI, từng xe, scenario, seed, engine/version, EV2Gym version/hash và lệnh chạy |
| `events.json` | Nhật ký đến, cắm, hoàn tất, rút hoặc rời hàng chờ |
| `power_trace.csv` | Công suất AC/DC/lưới, độ dài hàng chờ, số cổng bận và chiều dài từng bước |
| `vehicles.csv` | SOC, năng lượng, thời gian, cổng và trạng thái cuối từng xe |
| `replay.json` | Snapshot đầu mỗi khoảng và tại horizon, công suất từng xe và event ledger |
| `viewer.html` | Bản đồ bãi 2D, Play/Pause, Step, Seek, tốc độ, chi tiết xe và đồ thị công suất |

Cách xuất KPI giữ tương thích với báo cáo v1. `events` nằm trong
`events.json` và `replay.json`, `power_trace` tổng hợp nằm trong CSV.
Mean/p95 tiếp tục tính trên phiên đã cắm, p95 dùng nearest-rank.
`queue_wait_for_all_arrivals` bao gồm lượt chờ trước khi rời. Xe còn
chờ tại horizon có `censored=true`. Arrival phải nằm trong `[start, end)`
để một yêu cầu được tính vào fixture. Deadline được phép sau horizon.
`rejected_allocation_count` đếm kế hoạch dispatch, ngân sách, acceptance
hoặc setpoint bị Guard chặn trước bước nạp năng lượng.
`applied_constraint_violation_count` đếm khoảng sạc có phản hồi bị hậu kiểm
phát hiện vi phạm. `constraint_violation_count` là alias tương thích của
bộ đếm thứ hai. CLI xuất chẩn đoán JSON qua stderr và trả mã 2 khi Guard
phát hiện lỗi. Lỗi đọc hoặc validate cấu hình trả thông báo văn bản và mã 2.
Report và replay hoàn chỉnh chỉ có ở run thành công.

## Kiến trúc

> **Bố cục sau refactor Unified Core (ADR-019 Phase 4).** Gói `src/simulator/src/` cũ đã bỏ (không còn shim). Đoạn
> mô tả bên dưới giữ tên file gốc; vị trí hiện tại:

```text
src/simulator/
├── core/                          # MỘT kernel dùng chung với backend (HybridStation)
│   ├── kernel.py                  # StationKernel: observe / boundary / propose / approve / apply_approved / advance
│   ├── algorithms.py              # Ghép thuật toán theo config + DC model registry
│   ├── queue.py                   # Phiên, hàng chờ, mốc xe đến / rời / rút DC
│   ├── ev2gym_adapter.py          # Tích phân năng lượng EV2Gym
│   └── charging_models/           # Taper MVP-1 và profile theo xe
├── hybrid.py                      # HybridSimulator = kernel + trace / frame / report
├── evaluation/                    # KPI, DecisionTrace, benchmark audit
└── hybrid_station.py              # Adapter backend trên cùng kernel
src/models/simulation_core.py      # (trước: scenario.py) kịch bản và giới hạn vật lý
src/models/scheduling/             # (trước: observations.py, */base.py) hợp đồng snapshot / dispatch / optimizer
src/models/physical_{constraints,limits}.py, src/models/charging_physics.py
src/optimizer/{dispatch,zones,coordination}/   # (trước: dispatch/, optimizers/, coordination/)
src/guard/physical/validator.py    # (trước: safety/guard.py) Physical Guard
```

- `src/scenario.py` validate scenario và chuẩn hóa giờ theo phút. Sau nửa đêm,
  dùng `24:xx`, `25:xx`. Có thể đặt `timestep_minutes` hoặc dùng khóa cũ
  `step_minutes`, là số nguyên dương và phải trùng nhau nếu cùng khai báo.
  Event đến/rời/rút DC tách bước nếu cần. Adapter dùng số phút thực của mỗi
  khoảng khi tính năng lượng. Offset đến/rời trong đối tượng EV dùng phút,
  với `timescale=1` khi `spawn_ev()` chạy AFAP nội bộ. Thời điểm hoàn tất
  được ghi tại cuối bước. Horizon xử lý xe rời đúng thời điểm kết thúc.
- `src/engine/hybrid.py` điều phối vòng mô phỏng và ghi sự kiện/replay.
  `src/engine/queue.py` quản lý xe đến/rời, hàng chờ và cổng. QueueController
  thực thi phép gán đã được Guard kiểm tra. AC giữ cổng đến giờ rời. DC
  nhả cổng sau thời gian chờ hoặc vào giờ rời, tùy mốc nào đến trước.
- `src/dispatch/` chọn xe chờ theo khu. FIFO/FCFS dùng cùng
  `arrival_order.py` và xử lý xe đến đồng thời theo ID. EDF ưu tiên deadline,
  sau đó xét giờ đến và ID.
- `src/coordination/` cấp ngân sách đầu ra riêng cho từng khoảng.
  `src/optimizers/` đề xuất setpoint cho xe đã cắm. AC và DC chọn optimizer
  độc lập và có thể dùng chung `equal_share.py`.
- `src/safety/guard.py` kiểm tra phép gán cổng, ngân sách, công suất và phản hồi
  thực thi. Scenario giữ giới hạn bất biến. Sai số tuyệt đối của Guard là
  `1e-7` kW/kWh theo đại lượng kiểm tra.
- `src/engine/ev2gym_adapter.py` dùng EV2Gym `EV_Charger.spawn_ev()` cho xe có chỗ,
  giữ ánh xạ ID ChargePilot khi EV2Gym đổi `EV.id` thành index cổng. Adapter
  đối chiếu ID, đối tượng xe, slot và số xe cắm khi kết nối, sạc và tháo cổng.
  Queue controller quyết định lúc giải phóng slot.
  AC gọi `EV.step(type="AC")` và dùng lớp con bỏ làm tròn dung lượng lên
  0,01 kWh. DC dùng contract trong `src/charging_models/base.py` để tính
  acceptance và năng lượng theo SOC. Công suất thực ở đầu ra được
  suy từ kWh mà mô hình trả về, chia thời gian và hiệu suất sạc. Công suất
  lưới tiếp tục chia hiệu suất chuyển đổi.
- `src/evaluation/metrics.py` tính KPI từ kết quả đã thực thi.
  `run.py` xuất report và nhúng replay vào viewer.

## P0 trên EV2Gym 2.0.0

Gói đã cài không có `direct_url.json` để xác định commit. Fingerprint của
`models/ev.py` là
`bd06ccc8b2e57d7551228129151d9fde4fafb093d7f25468a28bb75529e0fc31`,
và của `models/ev_charger.py` là
`47476d64d5a81ba81380e51ec7d747704d1a456dadf176d7b08e49811b0b3c34`.

| Probe upstream | Quan sát |
| --- | --- |
| AC qua `EV_Charger.step()` | Trả 0,091094325 kWh. Dung lượng pin tăng 0,10 kWh do làm tròn lên |
| `EV.step(type="DC")` và `EV_Charger.step()` tại trụ DC | Cả hai ném `NotImplementedError` |
| `spawn_ev()` tại trụ đầy | Ném `AssertionError`, xe chờ không được kết nối |
| Giải phóng cổng rồi lấy xe từ deque ngoài | Xe tiếp theo vào đúng cổng và EV2Gym gán lại ID cục bộ |

Adapter dùng các component EV2Gym trong cùng quy trình AC/DC. DC v1 là
**extension tổng hợp**, chưa có native DC. Runtime dùng cơ chế thời gian
và ngân sách ChargePilot, còn `EV2Gym.env`, mô hình lưới, replay và KPI
upstream nằm ngoài phạm vi tích hợp.

DC duy trì `prev_capacity`, `current_capacity`, `current_energy` (kWh
trong khoảng vừa sạc), `total_energy_exchanged`, `abs_total_energy_exchanged`,
`required_energy` (phần còn thiếu đến dung lượng tối đa theo EV2Gym) và SOC.
Dòng điện native, lịch sử SOC native, số chu kỳ, AFAP, thống kê trụ và suy
giảm pin không thuộc hợp đồng DC. Gọi `DCEV.get_battery_degradation()` báo
`NotImplementedError`. KPI chờ, năng lượng và tỷ lệ đạt mục tiêu lấy từ
dữ liệu thực thi của ChargePilot.

## Chọn thuật toán

Thêm object `algorithms` dưới đây vào scenario, hoặc lưu phần bên trong
object làm JSON riêng rồi truyền `--algorithms`. File CLI thay toàn bộ
selection trong scenario. Từng khóa hoặc khu bị bỏ qua nhận mặc định v1.1.

```json
{
  "algorithms": {
    "dispatch": {"AC": "fifo", "DC": "fcfs"},
    "optimizers": {"AC": "equal_share", "DC": "equal_share"},
    "coordinator": "fixed_budget",
    "physical_guard": "physical_v1",
    "dc_charging_model": "synthetic_taper_v1"
  }
}
```

Ví dụ CLI dùng EDF ở DC, `deadline_first` chia công suất DC và ngân sách
gán 60 kW cho DC. Đây là cấu hình thử giao diện. Để đổi riêng AC, đặt
`optimizers.AC` thành `deadline_first`. Để cấp ngân sách thấp hơn trần
scenario, dùng `{"name":"fixed_budget","parameters":{"output_kw":{"AC":22,"DC":60}}}`.

```bash
.simulator/bin/python -m src.simulator.run --scenario mvp1
.simulator/bin/python -m src.simulator.run --scenario mvp1 --algorithms src/simulator/config/algorithms_edf_demo.json
```

Cách thêm thuật toán là cài đặt contract tương ứng, thêm `Registration`
vào registry tường minh trong `src/algorithms.py`, rồi chọn tên bằng JSON.
Registration có version và có thể nhận factory khai báo tham số. Với DC
model, factory cũng khai báo xuất xứ, trạng thái ước lượng/đo thực và phạm
vi hợp lệ. Tên hoặc tham số lạ báo lỗi. `physical_v1` luôn được gọi.

`report.json` và `replay.json` lưu tên thực thi, version, tham số,
implementation và nguồn cấu hình trong `metadata.algorithms`. Dùng
`report.json` cùng thư mục làm metadata cho các CSV, giữ header CSV v1.
Xem [thiết kế và thứ tự thực thi](docs/DESIGN_DECISIONS.md).

### DC MVP-2

Chọn `llf` ở `dispatch.DC` và `rolling_lp` ở `optimizers.DC` để chạy MVP-2.
`--decision-trace` xuất `decision_trace.json` và `decision_latency_ms.json`
cùng thư mục kết quả. Benchmark mặc định chạy năm nhóm workload trên năm seed
với AC FIFO + Equal Share, Fixed Budget và SyntheticTaperV1.

```bash
.simulator/bin/python -m src.simulator.run --scenario mvp1 --algorithms src/simulator/config/algorithms_mvp2.json --decision-trace
.simulator/bin/python -m src.simulator.benchmark --vinfast-sensitivity
```

Xem [phương pháp, KPI và giới hạn MVP-2](docs/MVP2_BENCHMARK.md).

### Điều phối AC/DC MVP-3

`ac_rolling_lp` dùng mục tiêu thiếu hụt trước, chi phí TOU sau. Chọn
`fixed_share` cho đối chứng hoặc `dynamic_slack` để phân bổ phần nguồn chung
còn dư. Mặc định của các fixture cũ giữ nguyên. Kịch bản mới có thể khai báo
`physical_zone_cap_kw`, `limit_events`, `tou_tariff` và giới hạn nguồn độc lập
`independent_grid_input_limit_kw`.

```bash
.simulator/bin/python -m src.simulator.run --scenario mvp1 --algorithms src/simulator/config/algorithms_mvp3.json --decision-trace
.simulator/bin/python -m src.simulator.benchmark_mvp3 --output-dir src/simulator/outputs/mvp3_acceptance
```

Xem [schema và kết quả nghiệm thu MVP-3](docs/MVP3_BENCHMARK.md).

## DC Vehicle Profiles v0.1

Fixture `vinfast_dc_2port_120kw` chọn `vinfast_profiles_v0_1` qua registry.
Trong scenario, đặt `vehicle_model` cho từng xe DC và khai báo
`battery_kwh` khả dụng cùng `max_dc_kw`. Xe DC thiếu `vehicle_model` dùng
`SyntheticTaperV1`. Muốn thử xe chưa định danh, dùng `UNKNOWN` hoặc tên
chưa có trong danh mục. Fallback generic lấy dung lượng và cap từ scenario.
`VF2` bị từ chối để tránh ghép nhầm với `VF3`. Với profile đã biết,
dung lượng sai bị từ chối khi chọn profile.

| `vehicle_model` | Pin khả dụng / công suất tham chiếu | Nguồn đường cong |
| --- | --- | --- |
| `VF3` | 18,64 kWh / 24 kW theo [VinFast VF 3](https://vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3) | Các điểm taper tổng hợp của ChargePilot |
| `VF8_NEW_2026` | 60,13 kWh / 100 kW theo [VinFast VF 8 thế hệ mới](https://vinfastauto.com/vn_vi/dat-coc-xe-vf8-the-all-new-2026) | Proxy từ bảng [VF8 Plus đời cũ](https://evkx.net/models/vinfast/vf8/vf8_plus/chargingcurve/), chuẩn hóa theo mốc 103 kW và bỏ điểm bật tăng tại 100% |
| `VF9_123` | 123 kWh theo [VinFast VF 9](https://stg-cms-v2.vinfastauto.com/vn_vi/car-pdp-v2/vf9) / 60 kW giả định | Đa thức generic từ [Simolin et al., Eq. 13](https://doi.org/10.1016/j.treng.2025.100350) |
| `UNKNOWN` | `battery_kwh` và `max_dc_kw` từ scenario | Cùng đa thức generic |

Các đường cong này dùng để thử độ nhạy trong mô phỏng. Đặc biệt, đường
cong VF 8 mới là proxy từ khác đời xe và đa thức generic được fit trên
quần thể xe hỗn hợp. Report và replay ghi nguồn, confidence, version và
cờ `oem_cap_verified` (áp dụng cho **công suất tham chiếu**, không xác nhận
đường cong) theo ID trong
`metadata.algorithms.dc_charging_model.vehicle_profiles`.

Fixture giả định hai cổng DC 60 kW cùng tủ 120 kW, ngân sách đầu ra AC/DC
22/120 kW và nguồn vào 150 kW. Tổng đầu ra 142 kW tương ứng 149,474 kW đầu
vào khi hiệu suất chuyển đổi là 0,95. Đây là cấu hình giả định của fixture.
Wrapper dùng setpoint đã duyệt và tích phân taper với bước con tối đa
10 giây. Hiệu suất pin 0,98 được áp dụng trong wrapper. Adapter cập nhật
SOC một lần từ kWh vào pin, còn engine quy đổi năng lượng lưới theo hiệu
suất chuyển đổi 0,95. Mốc hoàn tất và nhả cổng vẫn theo clock của engine.

```bash
.simulator/bin/python -m src.simulator.run --scenario vinfast_dc_2port_120kw
```

MVP-1 tiếp tục dùng `synthetic_taper_v1` theo mặc định. Để so sánh độ nhạy
trên chính fixture VinFast, truyền `--algorithms` với JSON
`{"dc_charging_model":"synthetic_taper_v1"}`. Cách này giữ nguyên các xe,
ngân sách và policy mặc định, chỉ đổi mô hình DC.

## Kết quả demo và kiểm thử

Fixture seed 42, không ngẫu nhiên, 360 khoảng một phút và 361 snapshot gồm
horizon. Lúc 18:00 có 4 xe cắm, 2 AC và 3 DC chờ. Sau 44 phút, DC-C vào
cổng DC-01/P2 ngay khi DC-B rút.

| KPI | EV2Gym hybrid/DC extension |
| --- | ---: |
| Mục tiêu đạt đúng hạn | 9/9 |
| Chờ mean / p95, phiên đã cắm (phút) | 51,11 / 135 |
| Năng lượng đầu vào lưới (kWh) | 239,527 |
| Năng lượng vào pin (kWh) | 223,000 |
| Đỉnh đầu vào lưới (kW) | 105,263 |

Run hybrid ghi 0 xe rời khi còn chờ, 0 kWh nhu cầu còn lại và 0 vi phạm.
Mục tiêu AC của fixture đều dưới ngưỡng taper mặc định EV2Gym (80%). Test
SOC cao cho thấy công suất thực AC có thể thấp hơn đề xuất.

```bash
.simulator/bin/python -m pytest src/simulator/tests/test_ev2gym_p0.py -q -s
.simulator/bin/python -m pytest src/simulator/tests src/simulator/tests/ev2gym_smoke.py -q
.simulator/bin/ruff check src/simulator src/models src/optimizer src/guard/physical
```

Suite v1.2 với DC Vehicle Profiles đạt 112 test, gồm 24 ca tích hợp mới.
Cần chỉ đích danh
`ev2gym_smoke.py` để pytest chạy thêm smoke test. So sánh trước/sau khi đổi
cây thư mục cho thấy dữ liệu KPI, replay và events khớp ở cả mặc định lẫn
demo EDF. Hai CSV của mỗi cấu hình khớp từng byte. Chromium đã kiểm tra
hai dạng replay trong vòng v1.2 trước khi sắp xếp lại package.

Xem [trạng thái dự án](docs/PROJECT_STATE.md) và [bằng chứng tương thích](docs/DESIGN_DECISIONS.md#bằng-chứng-tương-thích)
để đối chiếu các mốc trước. Suite toàn repository hiện dừng ở API cũ do
import `src.simulator.base`. Dùng lệnh suite simulator ở trên khi làm việc
với runtime offline.

## Giới hạn

Taper DC được lấy tại đầu bước, áp dụng như giới hạn trong suốt bước.
Động học sạc, hiệu suất cố định và giới hạn nguồn/tủ là giả định mô phỏng.
Phiên bản này chưa hiệu chỉnh từ dữ liệu xe hoặc trụ thật, chưa mô hình hóa
lỗi thiết bị, telemetry, nhiệt độ, tải nền, V2G, giá điện hay điều phối công
suất động. Adapter giải phóng cổng qua hai thuộc tính occupancy của EV2Gym,
nên cần chạy lại P0 và suite năng lượng/hàng chờ khi đổi phiên bản thư viện.
