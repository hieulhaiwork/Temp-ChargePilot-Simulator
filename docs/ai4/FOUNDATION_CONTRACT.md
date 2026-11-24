# AI-4.0 — Foundation contract

## Backend DecisionTrace

Backend schema `chargepilot.backend_decision_trace/2` mở sau dispatch và đóng khi bắt đầu quyết định kế tiếp. Active có `decision=null`, `applied=null` và `post_apply=not_evaluated`. Closed có `post_apply=violation` nếu từng ghi nhận hard violation, kể cả khi fail-safe ở quyết định kế tiếp thành công. `no_samples` cho khi thiếu số đo công suất xe, kể cả ca trạm idle. `pass` đòi có số đo và không có hard violation trong các bước đã ghi. Số đo lưu theo phút mô phỏng, nguồn do engine ghi. `applied.coverage` ghi khoảng kỳ vọng, số phút giữ lại,
số phút bị eviction và số hard violations đã rời buffer. Khi coverage thiếu, post-apply báo `incomplete` trừ khi có
vi phạm đã quan sát thì báo `violation`. Số power/energy vẫn chỉ tổng hợp từ sample giữ lại. Hard violation count và
reason code bao gồm vi phạm đã rời buffer. Detail theo xe/phút chỉ có cho sample còn giữ.

- `validation.pre_apply_physical` gồm `pass`, `rejected`, `not_evaluated`. `commands` và `emergency_commands` giữ verdict business Guard, approval ID và cờ executed theo lệnh. `validation.fail_safe` ghi `not_triggered`, `no_commands`, `executed`, `partially_executed` hoặc `blocked` cùng command IDs. Executed nghĩa là lệnh an toàn đã dispatch. `fail_safe.outcomes` ghi riêng `delivery`, `dispatch`,
  `resolution`, attempt và event IDs. Sau lỗi sink có thể ghi delivery failed, dispatch unknown và resolution resolved
  nếu readback xác minh trạm an toàn. Kết quả vật lý đến từ post-apply.
- `command_exclusions` lưu mọi lý do áp dụng, với thứ tự ưu tiên **PENDING_APPROVAL → SAFETY_HOLD → REJECTED_CONSENT** theo đường lọc hiện hành. Safety hold vẫn cho lệnh ngắt/đặt 0 qua kiểm tra tương ứng. Fail-safe dùng đường dispatcher khẩn cấp độc lập với bộ lọc này.
- `power.proposed` và `approved` là kW đầu ra do kernel đề xuất/duyệt. `power.dispatched` trỏ tới command rows executed. `effective_setpoint` là held setpoint kW đầu mỗi bước, trước khi áp giới hạn acceptance. `actual_output` là kW đầu ra đo theo từng bước, có interval và số phút đo theo booking. Trung bình chỉ dùng các phút có số đo của booking. Thiếu số đo biểu diễn null hoặc thiếu key của subject, tùy tầng dữ kiện. Giữ legacy v2 facts trong field `decision` của backend để replay/debug, với trạng thái Guard và null theo semantics này. Standalone dùng serializer v2 độc lập.
- `policy`, `experiment`, config/tariff hashes, `state_version`, schedule version và algorithm labels được ghi khi mở. `decided_at` theo station clock của quyết định. `evidence_refs` dùng correlation ID, schema và JSON Pointer. Booking hoặc command được định danh trong pointer/row. Mỗi trace ghi cả planned interval và measured sample boundaries.
- Giá trị grid limit vô hạn (nếu có) được biểu diễn bằng null và `grid_input_unbounded=true`. Persistence kiểm JSON hữu hạn và ghi structured error theo correlation ID khi thất bại. Lỗi xây dựng trace ghi `decision_trace_build_failed`. Nếu facts lỗi hoặc không serialize hữu hạn, giữ applied
  evidence, validation và dấu vi phạm đã thu được, còn `decision` để null. Vòng xử lý safety ưu tiên trước trace,
  event store và notification. Raw payload chỉ dành cho service nội bộ. G1 chưa thêm API retrieval cho người dùng. Authorization và redaction projection của WHY thuộc phase tương ứng.

## Storage và restart

Migration `0004` thêm `decision_traces.full_payload` nullable (Postgres JSONB, SQLite JSON) và `decision_trace_bookings` có chỉ mục booking/time. PK correlation ID và decided-at index cũ phục vụ lookup. Summary, detail và index theo subject được cập nhật cùng transaction. Đóng trace chỉ một lần theo correlation ID. Retry active không ghi đè bản closed. Summary-only đọc từ đường cũ, lookup detail trả `None`. Query window nội bộ là `[start, end)`, tối đa 31 ngày và 100 payloads mỗi lần. Active đã lưu vẫn đọc được sau restart với dữ liệu planned. Restart không suy diễn số đo để đóng các trace còn mở. JSONL là export debug tùy chọn, có thể lặp record khi retry.

## Runtime và concurrency

Fork copy booking/approval DTO, recent commands, plan, config, tariff, scheduler parameters và metadata. Safety/rejected holds được copy thành set riêng. Kernel tiếp tục dùng isolation contract hiện có cho thuật toán, DC model, RNG và vật lý; chỉ share phần frozen hoặc stateless theo khai báo. Recorder, locks, sinks và clock thuộc fork.

Runtime khóa thread-safe bước vật lý và enqueue/drain. Ordinary events dùng deque có giới hạn. Hard events được giữ
bằng event ID riêng tới acknowledge, kể cả khi vừa đọc để xử lý batch. Clock và dispatch thường tạm dừng khi còn hard
event chưa giải quyết. Consumer sync không step trong lúc control loop tạo ranh giới quyết định. Retry ghi hard event
vào timeline theo event ID. Cùng một batch có cả power-limit change và hard violation, fail-safe hard được xử lý trước
trace, ghi event và notification.

Safety resolution dựa trên readback held setpoints, site/cabinet/zone caps qua Physical Guard hiện có và trần cổng.
Vehicle fault đã định danh đòi Safety Hold và công suất giữ bằng 0 nếu xe vẫn cắm. Không đủ evidence định danh fault
thì giữ fail-closed. Tối đa ba lần thử dispatch mỗi episode. Hết số lần thử giữ clock paused và phát error log.
Readback vẫn được kiểm khi có lượt xử lý mới, cho phép tiếp tục sau khi trạm trở về trạng thái an toàn. Lỗi/cancellation
giữ event pending nếu chưa có xác minh an toàn. Approval được duyệt vẫn qua Guard và kiểm lại Safety Hold của booking
hoặc occupant hiện tại ngay trước apply. Khi có hard event pending, approval chỉ cho đường STOP hoặc SET_POWER 0
đi tiếp tới Guard.

Outbox và retry sống trong một runtime. G3 sẽ xác minh full snapshot atomic qua bookings, state, outbox và persisted data.


## R10 — grid input, charger output, battery stored

- `output_kwh` tích phân actual charger-output kW qua interval. `grid_input_kwh` chia output kWh cho hiệu suất grid → charger đúng một lần, với conversion của quyết định. `battery_stored_kwh` cộng số đo năng lượng lưu vào pin do adapter trả về.
- Chi phí điện vận hành trong WHAT-IF sẽ dùng grid input kWh từng interval nhân tariff TOU theo thời gian trạm, bắt đầu từ snapshot. Không cộng năng lượng trước snapshot. Resident service bill là contract giá dịch vụ riêng, do owner Billing/Product quyết định.
- Các trường legacy như `EnergyEstimate.grid_energy_kwh` có ngữ nghĩa admission hiện tại. G1 thêm stage evidence ở trace. Việc sửa quote, billing hoặc frozen energy KPI cần review riêng. Owner Backend Energy với Billing/Product.

## R11 — outcome ledger

Owner Copilot Evaluator tại G3. Ledger giữ cohort đã biết theo snapshot, original/revised commitments, plug-in, first charge, deadline/outcome, energy và censoring riêng. Mọi xe NOT_ARRIVED cần được thể hiện với trạng thái phù hợp horizon. Denominator và SLA của cohort rỗng cần nhãn rõ. KPI frozen tiếp tục dùng `outcomes()` và `compute_kpis()` hiện hành.

## AI-4.1 (G1-F05 & G1-F06) — Planned Evidence và Deterministic WHY Contract

- **Additive G1-F05 trên `chargepilot.backend_decision_trace/2`**: Giữ nguyên tương thích ngược với schema v2 backend và không sửa standalone trace serializer (`src/simulator/evaluation/trace.py`). Khi mở trace, `open_trace()` bổ sung khối `planned` (cách ly lỗi dựng vào `decision_trace_build_failed stage=planned`), `safety.by_booking`, cùng mốc ISO timezone-aware `start_at`/`end_at` trên `interval`, các sample công suất và `applied.{closed_at,from_at,to_at,completed_by_booking}`, `coverage.{expected_from_at,expected_to_at}`.
- **Tách bạch các tầng sự kiện & Grounding (G2-F02 / G2-F06)**: Khối `planned.observed` chụp trạng thái trước khi gán cổng và trước `dispatcher.submit` (từ `proposal.dispatch`). `planned_assigned_connector` tách khỏi `connector_id` quan sát. `WhyFact` phân biệt rõ `direct` (kiểm khớp giá trị canonical với trace) và `derived` (khai báo `DerivationOp` hữu hạn và đầy đủ `input_evidence_refs`, không bao giờ chỉ trỏ `samples/0`). Loại bỏ hoàn toàn fallback hiệu suất ngầm (`0.95` / `0.98`): thiếu decision-time efficiency thì không tính và trả `PARTIAL` kèm mã thiếu dữ kiện.
- **G1-F06 & G2-F01/F03/F04 Temporal Resolution & Integration**: Truy vấn hỗ trợ as-of (`at`) và half-open `[start, end)` kèm keyset `cursor`/`next_cursor` trên chỉ mục hiện có của migration `0004` (không thêm migration 0005), tách in-window ASC với prior-boundary và luôn đọc station-wide superseding timeline để truy vấn lọc `booking_id` thấy quyết định ghi đè cấp trạm. Khi `runtime._live is None` sau restart, active trace cũ trong DB lập tức gắn `stale_after_restart=True`; truy vấn vượt đồng hồ vật lý live gắn `query_exceeds_live_physics_clock`. Tích phân sub-window dùng **exact clipped overlap duration** (giả định piecewise-constant) và chống cộng trùng mẫu; truy vấn `at` chỉ trả công suất mẫu, không trả năng lượng tích lũy. Tách bạch 7 `TemporalBasis` (`decision_snapshot` không gắn planned interval; derived measured facts gắn đúng `[derivation_start, derivation_end)`).
- **Authorization, Privacy Projection & Causal Invariants (G2-F05 / G2-F07)**: `ActorContext` do trusted server-side boundary tạo; `resolve_evidence_ref` đòi `AuthorizedSubject` đã xác minh hoặc `Booking` khớp chủ sở hữu và kiểm đủ tính nhất quán `ref_id`/path/schema/correlation/policy/decided_at/subject/interval. Allowlist Resident chỉ mở các leaf path an toàn, kèm hậu kiểm explicit trên `reason.subject`/`params`/`summary` và toàn bộ JSON. Không rò rỉ completion tương lai vào `at` trước thời điểm hoàn tất; không gán station violation thành vehicle violation nếu thiếu bằng chứng cấp xe; không phát `NO_INCIDENT_OBSERVED` khi trace active, incomplete, không có mẫu hoặc có gap. WHY Engine hoàn toàn read-only.
