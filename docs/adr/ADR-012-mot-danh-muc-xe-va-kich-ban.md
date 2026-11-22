# ADR-012: Một danh mục xe và một nơi chứa kịch bản trong `config/`; simulator chỉ nhận dữ liệu đã nạp

- Trạng thái: Proposed — chờ nhóm duyệt
- Ngày: 2026-11-21
- Sửa đổi một phần: ADR-003 (nội dung `vehicles.yaml`, định dạng và vị trí kịch bản)
- Liên quan: ADR-010, ADR-011, ADR-014
- Nguồn: master context v1.0 §4 (hồ sơ xe VinFast, provenance), §5.4, §10.4

## Bối cảnh

Hiện có hai danh mục xe và hai bộ kịch bản không đồng bộ:

| | Skeleton (branch này) | Simulator v1.2 (`feature/simulator` @ `d15871a`) |
|---|---|---|
| Danh mục xe | `config/vehicles.yaml`: 1 xe `DEMO-60`, `verified: false`, chỉ `usable_capacity_kwh`, `max_ac_power_kw` | Hằng số trong `src/simulator/src/charging_models/{dc_charging_models,vehicle_profiles}.py`: `VF3`, `VF8_NEW_2026`, `VF9_123`, `UNKNOWN`, kèm đường sạc DC và link nguồn |
| Kịch bản | `config/scenarios/*.yaml`: 3 kịch bản 8 × 7 kW | `src/simulator/scenario/*.json`: `mvp1`, `vinfast_dc_2port_120kw`; xe khai thông số inline |
| Validate | Pydantic trong `src/services/catalog.py` | `Scenario.parse` trong `src/simulator/src/scenario.py` |

Hậu quả: FR3 (kWh do code tính) và simulator có thể dùng hai bộ thông số khác nhau. Mức kiểm chứng khác nhau theo
**từng trường** (VF9: dung lượng là công bố OEM, nhưng 60 kW DC là giả định cho cổng 60 kW; đường sạc VF8 là proxy từ
VF8 Plus đời cũ trên EVKX) mà không có chỗ nào ghi máy đọc được.

## Các lựa chọn

1. Giữ hai danh mục, viết test so khớp: vẫn hai nguồn sự thật.
2. App đọc danh mục của simulator: app phụ thuộc phần nội bộ simulator, trái ADR-011.
3. **Một danh mục và một nơi chứa kịch bản trong `config/`**; `catalog.py` nạp, truyền object đã nạp vào
   `base.build_station(...)`.

## Quyết định

Chọn (3).

### 1. `config/vehicles.yaml` là danh mục duy nhất

| Trường | Ý nghĩa |
|---|---|
| `vehicle_model` | Mã duy nhất, giữ mã simulator đang dùng (`VF3`, `VF8_NEW_2026`, `VF9_123`, `UNKNOWN`) |
| `display_name` | Tên hiển thị |
| `usable_capacity_kwh` | Dung lượng khả dụng (`UNKNOWN`: bắt buộc khai trong kịch bản / yêu cầu) |
| `max_ac_kw`, `max_dc_kw` | Công suất tối đa xe nhận theo loại dòng |
| `dc_curve` | Mã đường sạc DC. **Tên đề xuất, registry chưa có:** simulator v1.2 hiện chọn đường sạc theo `vehicle_model` (`resolve_dc_profile`) với `curve_kind ∈ {piecewise, generic_polynomial}` và fallback `synthetic_taper_v1`. Migration phải tạo registry `vf3_synthetic_v0_1`, `vf8_shape_proxy_v0_1`, `simolin_2025_generic`, `synthetic_taper_v1` và giữ golden hash |
| `charging_efficiency` | Tuỳ chọn, ghi đè mặc định của trạm |
| `provenance` | Theo từng trường: `{source, status}`, `status ∈ verified · oem_claim · proxy · assumed · synthetic · unverified` |

- Bỏ cờ `verified` chung. Báo cáo nghiệm thu phải liệt kê mọi trường `proxy` / `assumed` / `synthetic` của xe được dùng.
- Đường sạc là **code** (mô hình) trong `src/simulator/src/charging_models/`; YAML chỉ **chọn** bằng `dc_curve`. Mã
  không có trong registry → lỗi lúc nạp. `VF2` vẫn bị từ chối, không tự đổi sang `VF3`.
- Mọi kết quả, biểu đồ, trace dùng profile phải ghi `curve_name`, `PROFILE_VERSION`, `status`, `source`.
- Không curve nào là số đo OEM: VF3 synthetic; VF8_NEW_2026 proxy EVKX; VF9_123 / UNKNOWN generic theo Simolin et al.
  (2025), DOI 10.1016/j.treng.2025.100350. Trước khi nói "dùng đúng Eq. 13" phải đối chiếu bài gốc.

### 2. Mọi kịch bản nằm trong `config/scenarios/`

- Chuyển `mvp1.json`, `vinfast_dc_2port_120kw.json` sang `config/scenarios/`; chấp nhận JSON hoặc YAML, một loader trong
  `catalog.py`.
- **Validator duy nhất là `Scenario.parse`**, gọi qua `base.py`. `catalog.py` không viết lại luật.
- Xe trong kịch bản tham chiếu `vehicle_model`. Thông số inline chỉ cho xe tổng hợp, đánh dấu `synthetic: true`.
- Trường tuỳ chọn của kịch bản (đã có trong R&D, cần đưa vào parser chính khi merge): `supply_mode`,
  `zone_grid_input_limit_kw`, `site_limit_schedule`, `cabinet_outages`, `vehicle_revisions` (thay đổi cam kết có mốc
  thời gian, không ghi đè lịch sử), `tariff` (synthetic, VND).
- Ba kịch bản 8 × 7 kW của skeleton giữ với nhãn `legacy_ac_only` tới khi nhóm quyết bỏ; không dùng cho nghiệm thu.
- `config/station.yaml` mô tả topology mặc định theo ADR-010.

### 3. Simulator không tự đọc `config/`

`base.build_station(scenario, vehicles, algorithms)` nhận object đã nạp; `src/simulator/` không import `src.services`.
CLI `python -m src.simulator.run` vẫn chạy độc lập bằng cùng loader.

## Bằng chứng

Golden regression của `mvp1`, `mvp1 + EDF`, `vinfast_dc_2port_120kw` chạy ngày 21/11 (ADR-010 §Bằng chứng) là mốc so
sánh cho migration: sau khi chuyển file và danh mục, **report / events / power trace / vehicles phải khớp hash cũ**.

## Hệ quả

- Migration là một PR riêng, sau ADR-011: thêm 4 mẫu xe vào `vehicles.yaml` (chép giá trị và nguồn từ code), xoá hằng
  số khỏi `charging_models`; chuyển 2 file kịch bản; sửa đường dẫn CLI / test / README; golden hash phải khớp, không khớp
  thì dừng điều tra; `test_catalog.py` khoá danh mục mới thay `DEMO-60`.
- Thứ tự của ADR-003 giữ: PRD trước, rồi YAML, rồi test.
- Có một điểm lệch nguồn cần sửa khi migration: link OEM của VF9 trong `vehicle_profiles.py` trỏ tới máy chủ staging
  (`stg-cms-v2.vinfastauto.com`), còn master context dùng `vinfastauto.com/vn_vi/dat-coc-xe-vf9`.
