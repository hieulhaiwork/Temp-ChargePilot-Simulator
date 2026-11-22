# ADR-007: `StationRuntime` là composition root; sự kiện xử lý ngay trong request

- Trạng thái: Proposed — nhóm đã duyệt 2026-11-17, chờ mentor. **Sửa đổi một phần — xem ghi chú bên dưới.**
- Ngày: 2026-11-17
- Plan chi tiết: [`docs/plan/10-backend.md`](../plan/10-backend.md) §5, §6


> **Sửa đổi một phần:** [ADR-011](ADR-011-mot-simulator-sau-be-mat-cong-khai.md) và [ADR-014](ADR-014-decision-trace-counterfactual-hitl.md) §7, 2026-11-21: `StationRuntime.simulator` là adapter `HybridStation`; live, benchmark và what-if dùng chung một bộ `Algorithms`. `replan` vẫn đồng bộ trong request; sinh phương án AI-1 và WHAT-IF nặng chạy job nền trong cùng process. `forecaster` được phép `None` (F6 hoãn, [ADR-015](ADR-015-pham-vi-mvp4-va-quy-tac-bang-chung.md)).
>
> **Hiện trạng 2026-11-22 ([ADR-016](ADR-016-livestation-cho-backend.md)):** `StationRuntime.simulator` là `LiveStation` (live: `get_runtime`; benchmark: `build_sim_runtime`), chưa phải `HybridStation`. Vòng nền `run_forever` đã chạy thật; deploy bật `CONTROL_LOOP_ENABLED=true`.

## Bối cảnh

ADR-002 yêu cầu benchmark và vận hành thật đi chung đường Guard. Nhưng `control_loop.on_event(event)` không có cách nào
nhận simulator, đồng hồ hay nơi ghi nhật ký khác nhau cho hai chế độ, và chưa có chỗ nào giữ simulator của chế độ chạy
thật. Render free tự ngủ, nên một vòng nền chạy liên tục không đáng tin. Router đang gọi thẳng `src.guard.approval`,
nhưng `approval.decide` không có actuator để thực thi lệnh đã duyệt.

## Các lựa chọn

1. Biến toàn cục trong từng module (simulator, lịch hiện hành, đồng hồ): nhanh, nhưng benchmark và live giẫm lên nhau.
2. **Một dataclass `StationRuntime`** gom mọi phụ thuộc, truyền tường minh vào `on_event`.
3. Hàng đợi sự kiện + worker nền: tách request khỏi việc tính lại, nhưng lịch chỉ đúng khi worker còn sống.

## Quyết định

Chọn (2):

- `src/services/runtime.py`: `StationRuntime(config, tariff, simulator, scheduler, forecaster, clock, sinks, plan, lock)`.
  `get_runtime()` dựng bản live lần đầu được gọi; `build_sim_runtime(scenario, strategy)` dựng bản benchmark.
- `control_loop.on_event(event, rt)` chạy tuần tự dưới `rt.lock`.
- `guard.dispatcher.submit(commands, ctx, actuator, sinks)`: `DispatchSinks` là ba callable (`log_decision`,
  `save_approval`, `notify`). Live trỏ tới `repository` + `realtime`; benchmark gom vào bộ nhớ.
- `event_bus.publish` gọi handler ngay trong request (await). Đặt lịch xong là có lịch mới, không phụ thuộc vòng nền.
- `control_loop.run_forever` chỉ lo việc theo thời gian (bước simulator, `TICK`, hết hạn phê duyệt), bật bằng
  `CONTROL_LOOP_ENABLED`, mặc định tắt.
- Service phát sự kiện là `async def`: `book`, `cancel`, `change`, `replan`, `manual_assign`, `inject_incident`.
- Router không import `src.guard`. Quyết định phê duyệt đi qua `control_loop.resolve_approval`.

## Hệ quả

- Container phải chạy đúng một worker: runtime, event bus, sổ kết nối WebSocket nằm trong RAM của process.
- `tests/test_architecture.py` thêm luật: `src/api` không import `guard`, `optimizer`, `simulator`, `forecast`, `db`.
- `on_event` chạy trong request nên request chậm theo solver; MT5 (p95 ≤ 2 s) là ngưỡng cho phần này.
- Khởi động lại: runtime nạp `repository.latest_plan()` và booking còn hiệu lực, kèm cảnh báo trên dashboard.
- Bất biến của ADR-004 giữ nguyên: không bật vòng nền khi nó còn là stub.
