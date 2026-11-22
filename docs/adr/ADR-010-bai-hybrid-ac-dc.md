# ADR-010: Bãi sạc hybrid AC + DC; fixture nền `mvp1`; ràng buộc ba tầng

- Trạng thái: Proposed — chờ nhóm và mentor duyệt (lệch PRD v0.2 §1)
- Ngày: 2026-11-21
- Sửa đổi một phần: ADR-003 (giá trị 8 × 7 kW / 35 kW trong bối cảnh của ADR-003; quyết định "tham số nằm trong
  `config/`" giữ nguyên)
- Liên quan: ADR-011 (simulator), ADR-012 (danh mục xe, kịch bản), ADR-015 (phạm vi, bằng chứng)
- Nguồn: RESEARCH SC-16 (khảo sát Vinhomes Ocean Park 1, ý kiến mentor chốt hướng AC + DC); master context v1.0
  (20/11) §1, §3; simulator v1.2 trên `feature/simulator` @ `d15871a`

## Bối cảnh

PRD v0.2 mô phỏng một bãi chỉ có AC: 8 đầu nối × 7 kW, giới hạn 35 kW. Khảo sát trong RESEARCH SC-16 cho thấy trạm
trước toà nhà ở Vinhomes Ocean Park 1 có cả trụ AC (11 kW, Type 2) và trụ DC (CCS2), đặt thành hai khu cạnh nhau.
Sau khi hỏi mentor, nhóm chốt đề tài là bãi hỗn hợp AC + DC. Bài toán khác hẳn bãi chỉ AC: hai loại tải (AC đỗ lâu, DC đỗ
ngắn, có taper theo SOC) cùng chia một giới hạn nguồn.

Việc AC và DC dùng chung một máy biến áp / feeder là **[GIẢ ĐỊNH]**: RESEARCH ghi rõ đây là giả định, chưa có số liệu
điện lưới tại site.

## Các lựa chọn

1. Giữ 8 × 7 kW, coi DC ngoài phạm vi: trái hướng đã chốt với mentor.
2. Giữ A01–A08 và thêm một tủ DC: các con số không còn khớp fixture đã chạy và đã có golden regression.
3. **Lấy fixture `mvp1` của simulator v1.2 làm topology nền**, mọi số nằm trong `config/` (ADR-003, ADR-012), có thêm
   chế độ nguồn độc lập để so sánh.

## Quyết định

Chọn (3).

### Topology nền (fixture `mvp1`, scenario_id `evening_9cars_hybrid_v1`)

| Thành phần | Giá trị | Bản chất |
|---|---|---|
| Tủ AC | `AC-01`, `AC-02`: mỗi tủ 1 cổng 11 kW | [GIẢ ĐỊNH] theo quan sát loại trụ |
| Tủ DC | `DC-01`: 2 cổng × 60 kW, **giới hạn tủ 120 kW** (tổng hai cổng, cap vật lý) | [GIẢ ĐỊNH] |
| Lưới cả khu | 106 kW đầu vào | [GIẢ ĐỊNH] |
| Ngân sách vùng | AC 22 kW · DC 78 kW đầu ra (chính sách, không phải cap phần cứng) | [GIẢ ĐỊNH] |
| Hiệu suất | chuyển đổi 0,95 (lưới → đầu ra tủ) · sạc 0,98 (đầu ra → pin) | [GIẢ ĐỊNH] |
| Bước / rút cổng | 1 phút; AC giữ cổng tới giờ rời khai báo; DC rút sau 5 phút | Tham số fixture |
| Tải | 9 lượt xe (4 AC, 5 DC), cùng tới 18:00, horizon 360 phút | Synthetic |

22 + 78 = 100 kW đầu ra, tương ứng 100 / 0,95 ≈ 105,263 kW phía lưới, không vượt 106 kW.

Topology này là **fixture nền cho regression và demo đầu**, không phải cấu hình cuối cùng của sản phẩm. Các kịch bản
khác không được nhập nhằng với nó: `vinfast_dc_2port_120kw` (kiểm hồ sơ xe DC), `rnd_conflict_site_drop` (R&D,
8 cổng AC + 2 cổng DC, 12 lượt xe, lưới 180 → 120 kW) và workload synthetic nhiều quy mô.

### Ràng buộc ba tầng, kiểm ở mọi bước

1. **Cổng / xe:** `p ≤ port_limit_kw` và `p ≤ EV_acceptance(SOC)` / `max_ac_kw` / `max_dc_kw`.
2. **Tủ / vùng:** `Σ p (tủ) ≤ cabinet_output_limit_kw`; `Σ p (vùng) ≤ zone_budget_kw`.
3. **Lưới:** `Σ p (mọi cổng) / η_conversion ≤ grid_input_limit_kw(t)`, kể cả khi giới hạn đổi theo thời gian.

Công suất **yêu cầu** (setpoint) ≠ **được phép** ≠ **thực phát**. Điện **vào pin** khác điện **lấy từ lưới**:
`E_grid = E_output / η_conversion`, `E_battery = E_output × η_battery`. Mỗi hiệu suất chỉ áp một lần.

### Nguồn chung hoặc độc lập

Kịch bản khai `supply_mode: shared | independent`. `shared`: coordinator chia ngân sách AC/DC trong giới hạn lưới.
`independent`: mỗi vùng có `zone_grid_input_limit_kw` riêng; **không** chuyển ngân sách xuyên nguồn. Mọi phát biểu
"bãi thật dùng chung feeder" vẫn là giả định.

### Vùng và hàng đợi

Xe yêu cầu một vùng (`AC` hoặc `DC`); hàng đợi và gán cổng theo vùng; xe AC không vào cổng DC và ngược lại. Mã cổng:
`AC-01-1`, `AC-02-1`, `DC-01-1`, `DC-01-2`.

## Bằng chứng

Chạy lại ngày 21/11 trên `feature/simulator` @ `d15871a` (Python 3.12.10, EV2Gym 2.0.0), log ở
[`eval/evidence/2026-11-21/`](../../eval/evidence/2026-11-21/README.md):

| Kịch bản | Đúng hạn | Wait mean / p95 (phút, started only) | Peak lưới | Điện lưới / pin | Vi phạm |
|---|---|---|---|---|---|
| `mvp1` FIFO/FCFS | 9/9 | 51,11 / 135 | 105,263 kW | 239,527 / 223,000 kWh | 0 rejected · 0 applied |
| `mvp1` + EDF demo | 9/9 | 54,56 / 135 | 86,316 kW | 239,527 / 223,000 kWh | 0 · 0 |
| `vinfast_dc_2port_120kw` | 8/9 | 44,78 / 135 | 149,474 kW (giới hạn 150) | 219,099 / 203,982 kWh | 0 · 0 |

Hệ quả rút ra từ số đo: `mvp1` **không đủ phân biệt** chính sách (FIFO và EDF đều 9/9). Nghiệm thu optimizer phải dùng
kịch bản có ca baseline thua (ADR-015).

## Hệ quả

- **Lệch PRD v0.2:** PRD v0.4 (`docs/PRD.md`) sửa trước, rồi YAML, rồi test (thứ tự của ADR-003).
- **Contract** (task T1.10, chỉ thêm field, có default): `ConnectorSpec` thêm `cabinet_id`, `zone`, `bay_id`, `layout`;
  `StationConfig` thêm `grid_input_limit_kw`, `zone_budgets_kw`, `power_conversion_efficiency`, `supply_mode`,
  `dc_unplug_delay_minutes`, `cabinets`; `power_limit_kw` là alias của `grid_input_limit_kw` trong một vòng;
  `ChargeRequest` / `Booking` thêm `zone`; `VehicleSpec` tách `max_ac_kw`, `max_dc_kw`.
- **Chưa đổi code ở ADR này.** Tới khi làm T1.10, CODE WINS: `config/station.yaml` và API vẫn trả A01–A08.
- **Guard**: luật công suất kiểm cả ba tầng; thêm ca "vượt ngân sách DC nhưng chưa vượt lưới" và ca `independent`.
- **Optimizer**: bước 1 phút như simulator; LP nếu dùng phải có ràng buộc vùng, tủ, lưới theo thời gian.
- **UI**: mọi số "35 kW", "8 đầu nối", "A01–A08" lấy từ API; màn vận hành hiện lưới, ngân sách AC, ngân sách DC riêng.
- **Sơ đồ bãi** (S9 vận hành, "Sơ đồ bãi" cư dân): vẽ theo vùng → tủ → cổng → ô đỗ, cộng hai làn chờ AC và DC.
- **Forecast F6**: lúc rút DC gần như cố định (rút sau 5 phút), nên F6 chủ yếu có giá trị ở vùng AC.
- **`nameplate_power_kw`**: 11 + 11 + 60 + 60 = 142 kW danh định; ngân sách thực 100 kW đầu ra.
- **EV2Gym upstream** raise `NotImplementedError` ở `EV.step(type='DC')`: vùng DC cần động học tự viết hoặc fork có
  test (ADR-011).
- **Không được tuyên bố**: DC chạy native trên EV2Gym; hai nhãn 60 kW nghĩa là mỗi xe luôn nhận 60 kW; số fixture là
  số đo tại trạm thật.
