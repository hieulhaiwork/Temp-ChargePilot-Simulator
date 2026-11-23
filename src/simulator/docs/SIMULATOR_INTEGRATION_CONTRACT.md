# ChargePilot SC-16 — SIMULATOR_INTEGRATION_CONTRACT

**Phiên bản tài liệu:** 1.0 · 21/11/2026  
**Nguồn sự thật để đối chiếu:** private repository [`hieulhaiwork/Temp-ChargePilot-Simulator`](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator), **commit [`8d7731c`](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/commit/8d7731cb539467ed40e2cbea1beb57d760e0d4a2)**.  
**Người nhận bàn giao:** Claude / nhóm Backend; nhóm Frontend có thể dùng các mục Output và Demo.  
**Phạm vi:** *System MVP-1* — gọi một **simulation offline** với cấu hình trạm và danh sách xe để xuất KPI, sự kiện, replay. **Không** phải API điều khiển trạm thật hoặc backend đặt lịch đã hoàn chỉnh.

> **QUAN TRỌNG — phân biệt ĐÃ CÓ và CẦN LÀM:** Simulator tại commit này **đã** hỗ trợ `Scenario.parse(combined_dict)`, `resolve_algorithms(...)`, `HybridSimulator.step()`, `run()`, `snapshot()` và CLI `--scenario <combined.json>`. Nó **chưa** có API nạp hai file JSON riêng. Tài liệu này quy định một **adapter mỏng ở Backend** ghép `station.json` + `traffic.json` thành `combined.json` trước khi gọi engine. Không sửa `HybridSimulator` hoặc tạo engine mới chỉ để nạp file.

> **Hiện trạng 22/11/2026 ([ADR-016](../../../docs/adr/ADR-016-livestation-cho-backend.md)):** backend **chưa** tích hợp theo hợp đồng này. Backend (chạy thật, mô phỏng S8, `eval/run_benchmark.py`) dùng `LiveStation` (`src/simulator/live.py`) sau Guard; `HybridSimulator` chạy offline qua `src/simulator/run.py` và bộ test riêng. Không trộn số liệu hai bên.

## 1. Mục tiêu và ranh giới phụ trách

### Mini demo phải chạy được

1. Operator chọn **cấu hình trạm** (có bao nhiêu tủ/cổng AC/DC, giới hạn cổng/tủ/vùng/nguồn) và **kịch bản giao thông sạc** (bao nhiêu xe, đến lúc nào, SOC/target/deadline; có thể gồm giá và sự cố đã được định nghĩa trước).
2. Backend load hai file, ghép và validate theo parser **hiện có**.
3. Backend gọi trực tiếp thư viện Python `HybridSimulator` (không gọi LLM, không chạy optimizer/simulator thứ hai).
4. Frontend hiển thị **Operator replay** (xe vào hàng, cổng, SOC, công suất, sự kiện), KPI và nếu cần DecisionTrace.
5. Phần Agent tạo booking/giữ chỗ 5 phút thuộc **Booking Service**, không thuộc simulator. Nếu muốn thể hiện booking lên replay, Backend chuyển **booking đã xác nhận** thành một vehicle record **trước khi bắt đầu run**.

### Ownership

| Nội dung | Simulator Codex (đang có) | Backend Claude (cần triển khai) |
|---|---|---|
| Mô hình AC/DC, Dispatch, Optimizers, Guard | **Giữ nguyên** | Không viết lại |
| `Scenario.parse()` và các quy tắc hợp lệ | **Đã có** | Sử dụng làm bước validate cuối |
| Tách file station/traffic | Chưa có native | **Implement gateway/loader** |
| Chạy toàn bộ scenario, frame, event, KPI, trace | **Đã có** | Gọi và đóng gói kết quả |
| HTTP REST, auth, run ID, storage, progress | Không thuộc simulator | **Implement** |
| Booking, HOLD 5 phút, concurrent reservation | Không thuộc simulator | **Implement riêng** |
| Web UI playback | Có viewer HTML mẫu | Frontend nối hoặc dùng artifact |

## 2. Các entry point thực sự có trong code

Từ repository root, dùng các import **đúng với code hiện tại**:

```python
from src.models.simulation_core import Scenario
from src.simulator.core.algorithms import resolve_algorithms
from src.simulator.hybrid import HybridSimulator

scenario = Scenario.parse(combined_config)  # dict, KHÔNG phải hai file riêng
algorithms, algorithm_metadata = resolve_algorithms(selection, scenario, "backend_simulation_gateway")
sim = HybridSimulator(scenario, algorithms=algorithms, record_decisions=True)

# Cách A: chạy offline đến hết scenario
result = sim.run()

# Cách B: chạy từng bước trên một instance riêng
# while not sim.finished:
#     sim.step()
#     current_frame = sim.snapshot()   # frame UI, KHÔNG phải full checkpoint
```

**Lưu ý:** `HybridSimulator.run()` là đồng bộ, có trạng thái nội bộ mutable, không được dùng chung một instance cho nhiều request. Mỗi simulation run phải tạo instance riêng. `snapshot()` không cung cấp checkpoint/restore. Input kịch bản là roster xe **cố định lúc khởi tạo**; chưa hỗ trợ inject thêm xe/booking khi engine đã chạy.

### CLI đã tồn tại

```bash
# Chạy trực tiếp combined JSON, không cần Backend server
.simulator/bin/python -m src.simulator.run \
  --scenario /path/to/combined_scenario.json \
  --algorithms /path/to/policy_m3a_fixed.json \
  --decision-trace \
  --output-dir src/simulator/outputs/e2e_demo
```

Tệp `config/algorithms_mvp3.json` đang có trong repo chọn **Dynamic Slack**. Theo review benchmark MVP-3, **M3a (Fixed Share + AC/DC LP)** là policy tham chiếu tốt hơn cho demo ổn định. Dùng file chọn policy minh họa ở mục 4 hoặc cung cấp `selection` tương đương từ Backend. Không hiểu nhầm kết quả M3b tốt hơn toàn diện: trong benchmark đã báo cáo, M3b hy sinh SLA AC ở nguồn chung khan hiếm.

## 3. Hai file input độc lập — contract đề xuất cho Backend

### 3.1. `station_demo.json` — mô tả trạm/hạ tầng

Đây là **định dạng của gateway**, không phải file đã được `Scenario.parse()` nhận trực tiếp. Backend bỏ `station_id` trước khi truyền engine.

```json
{
  "station_id": "CHARGEPILOT-DEMO-01",
  "grid_input_limit_kw": 106.0,
  "power_conversion_efficiency": 0.95,
  "charging_efficiency": 0.98,
  "ac_unplug_policy": "declared_departure",
  "default_zone_budget_kw": {"AC": 22.0, "DC": 78.0},
  "physical_zone_cap_kw": {"AC": 22.0, "DC": 120.0},
  "charger_cabinets": [
    {"id": "AC-01", "zone": "AC", "ports": 1, "port_limit_kw": 11.0, "cabinet_output_limit_kw": 11.0},
    {"id": "AC-02", "zone": "AC", "ports": 1, "port_limit_kw": 11.0, "cabinet_output_limit_kw": 11.0},
    {"id": "DC-01", "zone": "DC", "ports": 2, "port_limit_kw": 60.0, "cabinet_output_limit_kw": 120.0}
  ]
}
```

**Ý nghĩa:** ví dụ này có **2 cổng AC × 11 kW** (hai cabinet, mỗi cabinet một cổng) và **2 cổng DC × 60 kW** trên **một cabinet DC 120 kW**. Tổng trần đầu ra từ nguồn chung là `106 × 0.95 = 100.7 kW`, không phải 142 kW. `22/78` là **ngân sách Fixed Share**, `22/120` là **trần vùng vật lý**. Các giới hạn nguồn chung là giả định mô phỏng, **không** được tuyên bố là số đo tại trạm Vinhomes hay FPT.

| Field | Kiểu | Ý nghĩa / điều kiện |
|---|---|---|
| `station_id` | string | Chỉ metadata/backend; không chuyển vào `Scenario` |
| `charger_cabinets[]` | array | Mỗi object tạo cabinet; **số cổng = `ports`**, không phải số xe có thể phục vụ trong cả ngày |
| `id` / `zone` | string | Cabinet ID duy nhất; `zone` nhận `AC` hoặc `DC` |
| `ports` | integer ≥ 1 | Số cổng thuộc cabinet |
| `port_limit_kw` | kW | Công suất đầu ra tối đa **mỗi cổng** |
| `cabinet_output_limit_kw` | kW | Tổng trần đầu ra **cả cabinet** |
| `grid_input_limit_kw` | kW input | Trần lưới cho chế độ nguồn chung |
| `power_conversion_efficiency` | (0,1] | Đầu ra tổng ≤ grid input × hệ số chuyển đổi |
| `charging_efficiency` | (0,1] | kWh vào pin = output kWh × hiệu suất pin trong mô hình |
| `default_zone_budget_kw` | AC/DC → kW | Ngân sách phân bổ mặc định; phải đúng 2 khóa AC/DC |
| `physical_zone_cap_kw` | AC/DC → kW | Trần vật lý cho từng vùng; nên khai báo minh bạch |
| `ac_unplug_policy` | string | Hiện chỉ hỗ trợ `declared_departure` |

**Chú ý:** `Scenario.parse()` còn hỗ trợ `independent_grid_input_limit_kw` cho trường hợp nguồn AC và DC độc lập. Demo mặc định dùng shared supply. Nếu cấu hình independent supply, phải kiểm tra lại sự phù hợp giữa nguồn từng vùng, ngân sách và event type; không được tự cho phép chuyển công suất AC dư sang DC.

### 3.2. `traffic_demo.json` — kịch bản xe và sự kiện thời gian

Số lượng xe được xác định bằng **số phần tử trong `vehicles`**. Ví dụ có 7 xe (3 AC, 4 DC). Dữ liệu này là synthetic, cố ý cho DC có hàng chờ.

```json
{
  "scenario_id": "chargepilot_e2e_demo_7cars",
  "start_time": "18:00",
  "duration_minutes": 180,
  "step_minutes": 5,
  "dc_unplug_delay_minutes": 5,
  "seed": 42,
  "tou_tariff": {
    "currency": "USD",
    "periods": [
      {"start": "18:00", "price_per_kwh": 0.45},
      {"start": "19:00", "price_per_kwh": 0.12},
      {"start": "20:15", "price_per_kwh": 0.32}
    ]
  },
  "limit_events": [
    {"effective_at": "19:05", "grid_input_limit_kw": 80.0},
    {"effective_at": "19:25", "grid_input_limit_kw": 106.0}
  ],
  "vehicles": [
    {"id": "AC-A", "zone": "AC", "arrival": "18:00", "departure": "20:40", "battery_kwh": 60.0, "initial_soc": 0.40, "target_soc": 0.65, "max_ac_kw": 11.0},
    {"id": "AC-B", "zone": "AC", "arrival": "18:10", "departure": "20:50", "battery_kwh": 70.0, "initial_soc": 0.50, "target_soc": 0.70, "max_ac_kw": 11.0},
    {"id": "AC-C", "zone": "AC", "arrival": "18:40", "departure": "20:55", "battery_kwh": 60.0, "initial_soc": 0.55, "target_soc": 0.75, "max_ac_kw": 11.0},
    {"id": "DC-A", "zone": "DC", "arrival": "18:00", "departure": "19:20", "battery_kwh": 70.0, "initial_soc": 0.25, "target_soc": 0.75, "max_dc_kw": 60.0},
    {"id": "DC-B", "zone": "DC", "arrival": "18:00", "departure": "19:10", "battery_kwh": 65.0, "initial_soc": 0.35, "target_soc": 0.70, "max_dc_kw": 60.0},
    {"id": "DC-C", "zone": "DC", "arrival": "18:15", "departure": "20:15", "battery_kwh": 80.0, "initial_soc": 0.20, "target_soc": 0.65, "max_dc_kw": 60.0},
    {"id": "DC-D", "zone": "DC", "arrival": "18:30", "departure": "20:55", "battery_kwh": 60.0, "initial_soc": 0.30, "target_soc": 0.75, "max_dc_kw": 60.0}
  ]
}
```

| Field | Kiểu | Ý nghĩa / điều kiện |
|---|---|---|
| `scenario_id` | string | Định danh lượt kịch bản |
| `start_time` | `HH:MM` | Đồng hồ simulation; `24:xx`, `25:xx` hợp lệ khi qua nửa đêm |
| `duration_minutes` | integer > 0 | Chiều dài run |
| `step_minutes` hoặc `timestep_minutes` | integer > 0 | Bước mặc định; nếu khai cả hai phải bằng nhau |
| `dc_unplug_delay_minutes` | integer ≥ 0 | Chậm rút cổng DC sau khi hoàn tất |
| `vehicles[]` | array | Mỗi phần tử là **một xe và một yêu cầu sạc**; ID duy nhất |
| `arrival`, `departure` | `HH:MM` | `start ≤ arrival < scenario_end`, `departure > arrival`; deadline có thể sau end nhưng lúc đó KPI cần phân biệt pending |
| `initial_soc`, `target_soc` | số thực `[0,1]` | SOC fraction (khác API cư dân dùng `%`); `target > initial` |
| `battery_kwh` | kWh | Dung lượng sử dụng của xe; > 0 |
| `max_ac_kw` hoặc `max_dc_kw` | kW | Chọn đúng field theo `zone`; đây là giới hạn xe, có thể lớn hơn cổng |
| `vehicle_model` | string tùy chọn | DC profile registry; chỉ bật khi selection dùng `vinfast_profiles_v0_1` |
| `tou_tariff` | object tùy chọn | Các period bắt đầu đúng `start_time`, tăng dần; giá theo **kWh lưới**; USD ví dụ **không phải biểu giá EVN** |
| `limit_events[]` | array tùy chọn | Source drop, recovery, cabinet derating; `effective_at`, có thể thêm `announced_at ≤ effective_at` |

**Cảnh báo semantics:** `date`, `description`, `seed` có thể được ghi metadata nhưng engine đang sử dụng mô hình đồng hồ theo **phút**, không chạy theo ngày/tháng/timezone thực. Backend phải tự chuẩn hóa `AwareDatetime` thành `HH:MM` của kịch bản. **Không dùng timestamp UTC chưa chuyển múi giờ**. `initial_soc`/`target_soc` của API đặt lịch là phần trăm `0–100`, còn simulator cần `0–1`: chia 100 đúng một lần ở gateway.

**Cảnh báo physics:** ví dụ trên dùng model `synthetic_taper_v1` cho DC. Để dùng `vinfast_profiles_v0_1`, phải khai báo `vehicle_model` tương ứng và bảo đảm `battery_kwh` **khớp đúng dung lượng profile**; không được chỉ thay nhãn xe trong ví dụ rồi kỳ vọng chạy. Vehicle profiles hiện là giả định/proxy nghiên cứu, không phải đường sạc thực đo.

### 3.3. `policy_m3a_fixed.json` — chọn thuật toán

```json
{
  "dispatch": {"AC": "fifo", "DC": "llf"},
  "optimizers": {"AC": "ac_rolling_lp", "DC": "rolling_lp"},
  "coordinator": "fixed_share",
  "dc_charging_model": "synthetic_taper_v1",
  "physical_guard": "physical_v1"
}
```

**Tại sao M3a?** Làm demo ổn định với AC/DC Rolling LP và ngân sách cố định. Nếu muốn kiểm chứng Global Dynamic Slack, đổi `coordinator` thành `dynamic_slack`, nhưng luôn thể hiện trade-off AC/DC và không dùng một KPI đơn lẻ để nói nó tối ưu hơn.

## 4. Loader/adapter hai file — chạy được mà không sửa engine

### 4.1. Lệnh chạy nhanh với bộ ví dụ kèm tài liệu

Bộ ví dụ bên ngoài tài liệu gồm:

```text
integration_demo/
├── station_demo.json             # topology, cổng, công suất, ngân sách
├── traffic_demo.json             # xe đến, deadline, SOC, giá, sự kiện
├── policy_m3a_fixed.json         # thuật toán cố định để demo
└── run_split_demo.py            # ghép + validate + gọi CLI HIỆN CÓ
```

Sao chép thư mục `integration_demo/` vào **repository root** (cùng cấp với `src/`, `frontend/`). Từ repository root:

```bash
# Chỉ cần làm một lần nếu chưa có môi trường simulator
python3.12 -m venv .simulator
.simulator/bin/python -m pip install -r src/simulator/requirements.txt

# Load đúng 2 JSON riêng, compile sang Scenario hiện có và chạy
.simulator/bin/python integration_demo/run_split_demo.py

# Hoặc chỉ định file tùy ý:
.simulator/bin/python integration_demo/run_split_demo.py \
  --station integration_demo/station_demo.json \
  --traffic integration_demo/traffic_demo.json \
  --policy integration_demo/policy_m3a_fixed.json \
  --output-dir src/simulator/outputs/integration_demo
```

Trên Windows native, thay `.simulator/bin/python` bằng `.simulator/Scripts/python.exe` nếu sử dụng PowerShell; hoặc dùng WSL theo môi trường đã kiểm chứng trong benchmark.

**Cách vận hành của script:**

1. Load hai JSON riêng và kiểm tra ownership các top-level field; không nhận trường lạ một cách âm thầm.
2. Gộp `{**station_fields_without_station_id, **traffic_fields}` thành một `combined_config`.
3. Validate bằng `Scenario.parse()` và `resolve_algorithms()` của chính simulator.
4. Xuất `compiled_scenario_<hash>.json` (để audit input).
5. Gọi `src.simulator.run.main()` với combined scenario, policy, `--decision-trace`.
6. Simulator tạo thư mục `<run-id>/` chứa `viewer.html`, `replay.json`, `report.json`, CSV, events và decision trace.

**Lưu ý về quy trình thử nghiệm:** các file và script này được xây dựng theo interface thực tế và đã kiểm tra cú pháp/JSON. Chúng **chưa được chạy end-to-end với EV2Gym trong môi trường tạo tài liệu**, vì môi trường này không cài `ev2gym`. Backend/Codex cần thực chạy lệnh nêu trên trong `.simulator` và bổ sung một smoke test trong CI trước khi chốt demo.

### 4.2. Tích hợp trực tiếp trong Backend (khuyến nghị thay CLI khi làm API)

Tận dụng chính hàm ghép/validation ở script hoặc chuyển vào `src/services/simulator_gateway.py`:

```python
from src.models.simulation_core import Scenario
from src.simulator.core.algorithms import resolve_algorithms
from src.simulator.hybrid import HybridSimulator

# station_dict, traffic_dict được load và validate từ nguồn đáng tin cậy.
# compose(...) là helper trong integration_demo/run_split_demo.py;
# Backend nên đặt bản production ở gateway module, không import CLI script.
combined = compose(station_dict, traffic_dict)
scenario = Scenario.parse(combined)
algorithms, metadata = resolve_algorithms(policy_dict, scenario, "backend_gateway")
result = HybridSimulator(scenario, algorithms=algorithms, record_decisions=True).run()

# result["frames"], result["events"], result["power_trace"],
# result["vehicles"], result["decision_trace"], result["decision_latency_ms"]
```

**Không** cần tạo HTTP API trong simulator, không dùng subprocess cho mỗi lần gọi API trong production, không nhân bản thuật toán vào `src/optimizer/*`. Gateway phải là ranh giới duy nhất giữa backend schema và `src.simulator.src.*`.

## 5. Output contract — đọc như thế nào cho đúng

### 5.1. `HybridSimulator.run()` trả `dict` (in-process)

| Key | Kiểu | Sử dụng |
|---|---|---|
| `scenario_id` | string | Identifies run scenario |
| `vehicles` | list[dict] | SOC cuối, trạng thái, arrival/departure, năng lượng, waiting, connector |
| `events` | list[dict] | `ARRIVED`, `PLUGGED_IN`, `CHARGE_COMPLETED`, `UNPLUGGED`, `LEFT_QUEUE` |
| `frames` | list[dict] | Trạng thái mỗi interval cho replay; chứa `minute`, `time`, `vehicles`, `queues`, `ports`, `completed`, power của interval |
| `power_trace` | list[dict] | `minute`, `duration_minutes`, `ac_output_kw`, `dc_output_kw`, `grid_input_kw`, queue lengths, connector counts |
| `decision_trace` | list[dict] | Chỉ có khi `record_decisions=True`; facts của Dispatch/Coordinator/Optimizer/Guard |
| `decision_latency_ms` | list[dict] | Chỉ có khi bật trace; wall-clock, **không** nằm trong golden deterministic decisions |
| `requests`, `completed_on_time`, `satisfied_demand_rate` | summary fields | Tổng nhu cầu và mức hoàn thành |
| `mean_wait_minutes_started_only`, `p95_wait_minutes_started_only` | summary fields | Chỉ xe đã được cắm; **không** đại diện mọi xe đến |
| `queue_wait_for_all_arrivals` | list | Có cả những xe chờ rồi rời đi (và censored nếu chưa rời) |
| `total_grid_energy_kwh`, `total_battery_energy_kwh`, `peak_grid_input_kw` | summary fields | Năng lượng và đỉnh công suất |
| `rejected_allocation_count`, `applied_constraint_violation_count` | counters | Safety metrics; 0 cần được đo trên run thực |

**Time convention:** `frames` ghi snapshot ở **đầu mỗi interval sau xử lý sự kiện boundary**, còn kW là mức trung bình trong interval tiếp theo. Không diễn giải frame power thành công suất tức thời tại cùng millisecond.

**Power convention:** đầu ra cổng và đầu vào lưới là hai đại lượng khác nhau. Đối với output chung: `grid_input_kw = (ac_output_kw + dc_output_kw) / conversion_efficiency` theo simulator hiện tại. Battery energy có hiệu suất pin riêng. Đây là **mô hình tổn hao cố định**, không phải dữ liệu điện năng trạm thật.

### 5.2. File export của CLI

```text
<output-dir>/<run-id>/
├── report.json                 # KPI + metadata + vehicles
├── replay.json                 # schema_version 1, frames + events
├── viewer.html                 # standalone replay, mở trực tiếp
├── events.json
├── vehicles.csv
├── power_trace.csv
├── decision_trace.json          # nếu --decision-trace
└── decision_latency_ms.json     # nếu --decision-trace
```

`viewer.html` được tạo từ `frontend/public/chargepilot-replay.html` trong repo. **Không cần viết lại viewer để demo**; có thể nhúng/hiển thị viewer hoặc dùng `replay.json` để phát dữ liệu trong Next.js.

### 5.3. REST API ở Backend — đề xuất, chưa có đủ implementation

| Route | Input/Output | Trạng thái tại commit này |
|---|---|---|
| `POST /simulation/runs` | Scenario ID/policy → run ID + KPI | Router đã có, service còn `NotImplementedError` |
| `GET /simulation/runs/{run_id}` | Trạng thái run + KPI | **Đề xuất** |
| `GET /simulation/runs/{run_id}/replay` | Frames/events | **Đề xuất** |
| `GET /simulation/runs/{run_id}/decisions` | DecisionTrace | **Đề xuất** |

Để giữ API đang có, Backend có thể chọn scenario bằng ID từ danh mục đã khai báo, thay vì cho request web trỏ tùy ý đến đường dẫn local. **Không cho người dùng tùy ý đọc file máy chủ thông qua `station_path`/`traffic_path`.** Trong mini demo, file path hoặc ID phải do server kiểm soát.

**Không được nhầm model:** `src.models.simulation.Scenario` của Backend **không** phải `src.simulator.src.scenario.Scenario`. Contract Gateway chịu trách nhiệm chuyển đổi cấu hình. Một số module backend cũ (như `simulation_service.py`, `runtime.py`) hiện là stub/contract chưa hoàn thiện; không tự giả định chúng gọi engine được.

## 6. Luồng LLM Booking → mini demo

```text
Resident -> LLM Agent -> ChargeRequest (Pydantic, SOC %)
                          -> BookingService / admission / HOLD 5 phút
                          -> CONFIRMED booking(s)
                          -> Backend scenario builder (trước run)
                          -> station.json + traffic.json (+ confirmed vehicles)
                          -> Scenario.parse + HybridSimulator.run()
                          -> report/replay -> Operator dashboard
```

**QUAN TRỌNG:** đừng gọi `HybridSimulator.run()` trên hàng nghìn yêu cầu đồng thời để quyết định HOLD. `BookingService` phải kiểm tra inventory theo slot (cổng + ngân sách điện) bằng transaction chống double-booking; simulator dành cho replay/benchmark/what-if có kiểm soát. HOLD 5 phút hiện **chưa** tồn tại trong schema `BookingStatus`/`BookingRow` ở commit này — đây là phần Backend phải bổ sung, độc lập với simulator.

Đối với mini demo nếu chưa có khả năng chuyển confirmed bookings thành xe: **vẫn chạy scenario predefined và phải nói rõ replay minh họa độc lập với ticket vừa tạo**. Không tuyên bố ticket đã ảnh hưởng đến công suất/queue nếu nó chưa được ghép vào scenario.

## 7. Acceptance checklist cho Claude Backend

- [ ] Nạp **2 file riêng** station/traffic cùng file policy từ server-controlled location; hỗ trợ đổi số lượng `charger_cabinets` và `ports`, thêm/bớt `vehicles` mà không sửa simulator.
- [ ] Ghép hai file thành config duy nhất, validate thật qua `Scenario.parse()`; test dữ liệu âm, trùng `id`, sai SOC, deadline ≤ arrival, ngân sách > cap, giới hạn và tariff không hợp lệ.
- [ ] Chạy `.simulator/bin/python integration_demo/run_split_demo.py`; có ít nhất một `<run-id>/viewer.html`, `replay.json`, `report.json`, `decision_trace.json`.
- [ ] Chạy gateway **in-process** và so sánh kết quả nghiệp vụ với CLI cùng scenario/policy; không so sánh wall-clock latency hoặc run_id ngẫu nhiên.
- [ ] `requests == len(vehicles)` của input; port counts đúng theo `sum(cab.ports)` và Guard violations = 0 trên demo được chọn.
- [ ] SOC `0–100` từ API đổi sang `0–1` đúng một lần; timezone chuyển từ aware datetime sang phút local; phần hiển thị đổi lại rõ ràng.
- [ ] Hai lượt chạy đồng thời phải tạo **hai simulator instances riêng**, không có state leak; file/run ID không trùng.
- [ ] Endpoint có phân quyền Operator; frontend lấy được replay/KPI thật, không hardcode mock data trong đường demo.
- [ ] Nếu có booking trong demo: `booking_id → vehicle.id` mapping ổn định, không đưa HOLD chưa xác nhận vào scenario, không nhân đôi ID hoặc năng lượng.
- [ ] Regression simulator MVP-1/2/3 không bị ảnh hưởng vì gateway không chạm engine.

## 8. Các giới hạn không được che giấu

- `HybridSimulator` **simulation offline**, không tự nhận live telemetry/booking update trong lúc chạy; cần một runtime command/event contract khác nếu demo tương tác trực tiếp giữa phiên.
- `step()` chỉ tiến thời gian mô phỏng một bước; không phải một tác vụ chờ wall-clock hoặc điều khiển EVSE thật.
- Thời gian sạc DC là synthetic/proxy; chưa mô phỏng đầy đủ điện áp/dòng, nhiệt độ/BMS. Các thử nghiệm SOC uncertainty, rút sớm, IoT delay/drop, voltage-aware DC thuộc **MVP-3.5**, không chặn mini demo replay.
- Source `106 kW`, fixed budget `22/78`, tariff USD trong ví dụ **chỉ là giả định minh họa**, không phải thông số công khai/đo kiểm của trạm thực.
- Chính sách `fixed_share` là policy tham chiếu cho demo chứ không khẳng định tối ưu toàn cục hay SLA bảo đảm với mọi workload.
- `run()` đồng bộ và có thể tốn thời gian với scenario lớn; nếu tải/khối lượng tăng, Backend phải có job execution, per-run isolation và lưu artifact, không giữ toàn bộ simulation lâu trong request HTTP.

## 9. Nguồn cần đọc trực tiếp trong repository

1. [`src/simulator/src/scenario.py`](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/8d7731c/src/simulator/src/scenario.py) — chính xác schema và validations.
2. [`src/simulator/src/algorithms.py`](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/8d7731c/src/simulator/src/algorithms.py) — registry, lựa chọn policy, DC models.
3. [`src/simulator/src/engine/hybrid.py`](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/8d7731c/src/simulator/src/engine/hybrid.py) — lifecycle, step/run/snapshot, return dict.
4. [`src/simulator/run.py`](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/8d7731c/src/simulator/run.py) — CLI/export thực tế.
5. [`src/simulator/docs/MVP3_BENCHMARK.md`](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/8d7731c/src/simulator/docs/MVP3_BENCHMARK.md) — giới hạn, policy trade-offs, nghiệm thu đã báo cáo.
6. [`src/services/simulation_service.py`](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/8d7731c/src/services/simulation_service.py) — stub cần nối ở Backend.
7. [`src/api/simulation.py`](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/8d7731c/src/api/simulation.py) — routes hiện có.

**Handoff decision:** Claude phụ trách HTTP + Gateway + orchestration; Codex giữ simulator core. Nạp file trạm + kịch bản hoạt động nhờ một bước **compose ở Gateway**, không cần Codex thay đổi MVP-3.
