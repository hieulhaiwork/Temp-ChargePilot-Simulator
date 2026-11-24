# AI-4.0 — Foundation contract

## Backend DecisionTrace

Backend schema `chargepilot.backend_decision_trace/2` mở sau dispatch và đóng khi bắt đầu quyết định kế tiếp. Active có `decision=null`, `applied=null` và `post_apply=not_evaluated`. Closed có `post_apply=violation` nếu từng ghi nhận hard violation, kể cả khi fail-safe ở quyết định kế tiếp thành công. `no_samples` cho khi thiếu số đo công suất xe, kể cả ca trạm idle. `pass` đòi có số đo và không có hard violation trong các bước đã ghi. Số đo lưu theo phút mô phỏng, nguồn do engine ghi.

- `validation.pre_apply_physical` gồm `pass`, `rejected`, `not_evaluated`. `commands` và `emergency_commands` giữ verdict business Guard, approval ID và cờ executed theo lệnh. `validation.fail_safe` ghi `not_triggered`, `no_commands`, `executed`, `partially_executed` hoặc `blocked` cùng command IDs. Executed nghĩa là lệnh an toàn đã dispatch. Kết quả vật lý đến từ post-apply.
- `command_exclusions` lưu mọi lý do áp dụng, với thứ tự ưu tiên **PENDING_APPROVAL → SAFETY_HOLD → REJECTED_CONSENT** theo đường lọc hiện hành. Safety hold vẫn cho lệnh ngắt/đặt 0 qua kiểm tra tương ứng. Fail-safe dùng đường dispatcher khẩn cấp độc lập với bộ lọc này.
- `power.proposed` và `approved` là kW đầu ra do kernel đề xuất/duyệt. `power.dispatched` trỏ tới command rows executed. `effective_setpoint` là held setpoint kW đầu mỗi bước, trước khi áp giới hạn acceptance. `actual_output` là kW đầu ra đo theo từng bước, có interval và số phút đo theo booking. Trung bình chỉ dùng các phút có số đo của booking. Thiếu số đo biểu diễn null hoặc thiếu key của subject, tùy tầng dữ kiện. Giữ legacy v2 facts trong field `decision` của backend để replay/debug, với trạng thái Guard và null theo semantics này. Standalone dùng serializer v2 độc lập.
- `policy`, `experiment`, config/tariff hashes, `state_version`, schedule version và algorithm labels được ghi khi mở. `decided_at` theo station clock của quyết định. `evidence_refs` dùng correlation ID, schema và JSON Pointer. Booking hoặc command được định danh trong pointer/row. Mỗi trace ghi cả planned interval và measured sample boundaries.
- Giá trị grid limit vô hạn (nếu có) được biểu diễn bằng null và `grid_input_unbounded=true`. Persistence kiểm JSON hữu hạn và ghi structured error theo correlation ID khi thất bại. Raw payload chỉ dành cho service nội bộ. G1 chưa thêm API retrieval cho người dùng. Authorization và redaction projection của WHY thuộc phase tương ứng.

## Storage và restart

Migration `0004` thêm `decision_traces.full_payload` nullable (Postgres JSONB, SQLite JSON) và `decision_trace_bookings` có chỉ mục booking/time. PK correlation ID và decided-at index cũ phục vụ lookup. Summary, detail và index theo subject được cập nhật cùng transaction. Đóng trace chỉ một lần theo correlation ID. Retry active không ghi đè bản closed. Summary-only đọc từ đường cũ, lookup detail trả `None`. Query window nội bộ là `[start, end)`, tối đa 31 ngày và 100 payloads mỗi lần. Active đã lưu vẫn đọc được sau restart với dữ liệu planned. Restart không suy diễn số đo để đóng các trace còn mở. JSONL là export debug tùy chọn, có thể lặp record khi retry.

## Runtime và concurrency

Fork copy booking/approval DTO, recent commands, plan, config, tariff, scheduler parameters và metadata. Safety/rejected holds được copy thành set riêng. Kernel tiếp tục dùng isolation contract hiện có cho thuật toán, DC model, RNG và vật lý; chỉ share phần frozen hoặc stateless theo khai báo. Recorder, locks, sinks và clock thuộc fork.

Runtime khóa thread-safe bước vật lý và enqueue/drain outbox. Consumer sync không step trong lúc control loop đang tạo ranh giới quyết định. Hard violation mới chặn clock advance tới khi handler fail-safe xử lý. Nếu handler raise, sự kiện hard được đưa vào outbox lại. Dispatcher vẫn áp Guard hiện có. Điều này bảo toàn thứ tự hai ca đã tái hiện tại G1. G3 sẽ xác minh full snapshot atomic qua bookings, state, outbox và persisted data.

## R10 — grid input, charger output, battery stored

- `output_kwh` tích phân actual charger-output kW qua interval. `grid_input_kwh` chia output kWh cho hiệu suất grid → charger đúng một lần, với conversion của quyết định. `battery_stored_kwh` cộng số đo năng lượng lưu vào pin do adapter trả về.
- Chi phí điện vận hành trong WHAT-IF sẽ dùng grid input kWh từng interval nhân tariff TOU theo thời gian trạm, bắt đầu từ snapshot. Không cộng năng lượng trước snapshot. Resident service bill là contract giá dịch vụ riêng, do owner Billing/Product quyết định.
- Các trường legacy như `EnergyEstimate.grid_energy_kwh` có ngữ nghĩa admission hiện tại. G1 thêm stage evidence ở trace. Việc sửa quote, billing hoặc frozen energy KPI cần review riêng. Owner Backend Energy với Billing/Product.

## R11 — outcome ledger

Owner Copilot Evaluator tại G3. Ledger giữ cohort đã biết theo snapshot, original/revised commitments, plug-in, first charge, deadline/outcome, energy và censoring riêng. Mọi xe NOT_ARRIVED cần được thể hiện với trạng thái phù hợp horizon. Denominator và SLA của cohort rỗng cần nhãn rõ. KPI frozen tiếp tục dùng `outcomes()` và `compute_kpis()` hiện hành.
