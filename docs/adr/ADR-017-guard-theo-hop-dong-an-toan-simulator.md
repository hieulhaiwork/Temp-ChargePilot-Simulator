# ADR-017: Guard backend dùng cùng hợp đồng an toàn vật lý với HybridSimulator

- Trạng thái: Proposed — chờ nhóm duyệt
- Ngày: 2026-11-22
- Liên quan: ADR-002 (Guard là chokepoint), ADR-010 (ràng buộc ba tầng), ADR-011 (Guard hai lớp), ADR-016
- Nguồn đối chiếu: `src/simulator/src/safety/guard.py`, `safety/limits.py`, `scenario.py`,
  `src/simulator/docs/SIMULATOR_INTEGRATION_CONTRACT.md` §3.1, `DESIGN_DECISIONS.md` (mở rộng MVP-3)

## Bối cảnh

Nhóm đang đi theo nhánh simulator (MVP-2 / MVP-3). Guard của simulator là chuẩn an toàn vật lý của nhóm. Guard
backend (`src/guard/rules.py`) lệch khỏi chuẩn đó ở năm chỗ:

| # | HybridSimulator | Guard backend trước ADR này |
|---|---|---|
| 1 | Trần vùng = `physical_zone_cap_kw` (22 / 120 kW); 22 / 78 là ngân sách Fixed Share, coordinator được chia lại | Coi ngân sách 22 / 78 là trần cứng: chặn DC > 78 kW dù tủ DC 120 kW và lưới còn chỗ |
| 2 | Nguồn độc lập: Σ vùng / η ≤ `independent_grid_input_limit_kw[vùng]` | Bỏ qua `supply_mode=independent`; field giới hạn nằm trên tủ, không ai đọc |
| 3 | Chỉ cấp điện cho xe đang sạc (`candidates`) | Cho cấp điện cổng trống và xe đã đầy |
| 4 | Chỉ gán cổng cho xe đã đến và đang chờ (`QUEUED`, chưa ở cổng nào) | Không kiểm xe có ở bãi; cho "gán" xe đang ở cổng khác |
| 5 | Một xe không được gán hai cổng trong một lượt | Không kiểm |

## Quyết định

1. `StationConfig` thêm `physical_zone_cap_kw` và `independent_grid_input_limit_kw` (tên giống `Scenario`), bỏ
   `CabinetSpec.zone_grid_input_limit_kw`. Kiểm khi nạp như `Scenario.parse`: ngân sách ≤ trần thiết bị; nguồn độc
   lập bắt buộc khai giới hạn từng vùng và ngân sách ≤ giới hạn × η.
2. `config/station.yaml` khai `physical_zone_cap_kw: {AC: 22, DC: 120}` theo contract §3.1. [GIẢ ĐỊNH] của fixture.
3. **Lớp vật lý của Guard backend gọi thẳng Guard của simulator**, không viết lại: `src/guard/physical.py` dịch
   `StationConfig` + `StationState` + lô lệnh sang `EffectiveLimits` / `Candidate` / `DispatchObservation` rồi gọi
   `safety.guard.guard` (công suất) và `safety.guard.validate_dispatch` (gán cổng). `ConstraintViolationError`
   thành `Violation` kèm lý do tiếng Việt và nguyên văn của simulator. Không kéo theo ev2gym (có test).
   - `total_power_limit` = `guard(...)` trên cả bãi sau lô: Σ tủ, Σ vùng ≤ trần vùng (`zone_cap_kw()`: trần thiết
     bị, vắng thì ngân sách), nguồn chung theo `state.available_power_kw`, nguồn độc lập theo từng vùng.
   - `connector_power_limit` = `guard(...)` trên một cổng (xe đủ điều kiện, ≤ cổng, ≤ xe) và `validate_dispatch`
     cho lệnh gán.
   - Luật `conflicting_commands` thêm: một xe không gán vào hai cổng cùng lô (simulator kiểm trong cùng plan).
   - 5 luật còn lại (chống bật-tắt, trạng thái cũ, quyền, phiên bản lịch, xung đột) là lớp chính sách của backend,
     simulator không có, giữ nguyên.
   - Coordinator: backend chưa có, nên ngân sách được giao của từng vùng (`assigned_kw`) = trần vùng.
5. Optimizer backend vẫn lập lịch trong ngân sách 22 / 78 (lớp chính sách, ADR-011). Guard chỉ giữ lớp vật lý.

## Hệ quả

- Lệnh vượt 78 kW ở vùng DC (vận hành, hoặc coordinator động sau này) không còn bị chặn oan khi tủ DC và lưới
  còn chỗ. Mọi giới hạn vật lý vẫn được giữ: cổng, tủ, trần vùng, lưới 106 kW.
- Sửa Guard simulator (`src/simulator/src/safety/`) là đổi luôn Guard backend — một nguồn sự thật cho an toàn vật lý.
- Chạy lại benchmark A–D (`python eval/run_benchmark.py --scenarios hybrid_evening,hybrid_power_drop --seeds
  1,2,3,4,5`, 23/11, 50 lượt): `blocked_commands = 0`, `power_limit_violations = 0` ở mọi lượt; tỉ lệ đúng hạn không
  đổi. Optimizer không phát lệnh nào bị luật mới chặn.
- Chưa làm: hạ trần tủ theo sự kiện (`LimitEvent.cabinet_output_kw`) và công suất nhận theo đường sạc DC
  (`acceptance_kw`). `StationState` mới có `available_power_kw` (giới hạn lưới hiện hành). Hai việc này cần trạm
  báo thêm dữ liệu, đi cùng việc nối HybridSimulator vào backend (ADR-016 mục "Mở").
