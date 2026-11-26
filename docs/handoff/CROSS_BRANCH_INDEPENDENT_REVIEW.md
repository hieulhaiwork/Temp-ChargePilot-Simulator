# X-02 — Independent Cross-branch Review

Reviewer: Codex, 2026-11-25; độc lập với tác giả báo cáo X-01 và các thay đổi nhánh được kiểm. Trạng thái: **HANDOFF_READY** khi đồng bộ checkpoint và nhả khóa.

## 1. Verdict và phạm vi

| Hạng mục | Verdict kỹ thuật | Phạm vi kết luận |
|---|---|---|
| AI-4 G1 safety fixes | **CHANGES_REQUIRED** đối với toàn bộ candidate hiện tại | Các sửa lỗi gốc có fail-before/pass-after thật, nhưng fork chưa kế thừa hard event pending; còn mất event timeline sau khi safety đã resolved. Không đưa cả G1 vào baseline chỉ từ nhãn “Approved”. |
| AI-4 G2 WHY Engine | **CHANGES_REQUIRED** | Service deterministic/read-only có nền tốt, quyền và temporal tests đạt; vẫn có phản ví dụ Consent 60 kW bị trình bày là approved minimum dù chỉ duyệt39 kW. Chưa API/JWT/UI; không phải feature người dùng đã nghiệm thu. |
| BE–FE integration | **NOT_READY để tích hợp nguyên nhánh** | Dựa trên nền cũ, contract và safety semantics khác; có thành phần giá trị để port chọn lọc. |
| Cross-branch integration readiness | **NOT_READY** | Cần remediation các phát hiện mới, bảo toàn Safety Hold/interlock và thống nhất contract trên nền mới trước khi tích hợp. Không phải Git conflict đơn thuần. |

Không đổi Technical Acceptance Governance Phase1 đã đạt trước đây. Review này phát hiện lỗi/gap sản phẩm và điều kiện tích hợp mới, không sửa hồ sơ đã nghiệm thu, không tự quyết Formal Closure hoặc phê duyệt ADR.

## 2. Checkpoint, refs và cách kiểm

Đọc AGENTS, CLAUDE các mục bắt buộc, HANDOFF mới nhất, `CROSS_BRANCH_ALIGNMENT_AUDIT.md` (X-01). Git đầu lượt khớp §1.8 theo danh sách đường dẫn: sáu tracked tài liệu sửa, các tài liệu governance/audit untracked, đầu ra eval/results có từ trước. Source/test/config/CI của workspace không có chỉnh sửa. Cảnh báo không đọc được cache/merged-sim không được coi là đã kiểm nội dung đó. Claude đã nhả khóa X-01; Human giao X-02 trong yêu cầu hiện tại; Codex chỉ nhận báo cáo mới và ô checkpoint được phép.

| Local ref cố định | Full SHA |
|---|---|
| refs/audit/2026-11-25/unified-core | `ce23136d50ad08abb7c9fdc98eff791875d24516` |
| refs/audit/2026-11-25/ai-4 | `4658b1f068350c130ed5ed1a744c19a7b8cd522c` |
| refs/audit/2026-11-25/be-fe-integration | `b92e61a10d6c086c06d9e32939f08ca3a5ffec0e` |
| refs/audit/2026-11-25/develop | `68692ee6c8e3d71a83aebefa95610d71840e3728` |

Các source references dưới đây là **đường dẫn trong snapshot/ref được nêu**, không ngầm trỏ tới code baseline đang mở. AI-4: G1 local commit `490f43300afb05ef7e809099a77e0c7174e272fb`, G2 final `4658b1f`; commit docs trước G1 là `d2b5d48`.

Xuất bằng `git archive --format=zip <ref>` qua Python zipfile vào thư mục mới `C:\Users\minhh\AppData\Local\Temp\p019-x02-b74f505b\{unified-core,ai-4,be-fe-integration}`. Không checkout, tạo worktree, merge/rebase hoặc đổi refs. Dùng venv workspace để chạy Python tại từng snapshot; không mượn `.env` sản phẩm. Test dùng SQLite tạm, LLM giả; không truy cập GitHub, DB sản phẩm, VM runner hay deploy.

Đã đọc diff runtime/clock, control_loop, dispatcher, charging_service, HybridStation instrumentation/fork, trace producer/persistence, ORM và migration0004; đọc chi tiết các đường authorization/evidence/temporal/numerical/causal trong `copilot/{why,evidence,trace_reader}.py`, test và oracle tương ứng; đọc BE–FE tại các component/findings X-BF-01…07. Đây không phải chứng minh mọi nhánh của WHY3216 dòng đều đúng; những giới hạn chưa test được nêu riêng.

## 3. Priority0 — tái hiện và fail-before/pass-after

### X02-S01 — Confirmed: Safety Hold mất ở baseline; G1 sửa được ca đã xử lý fault

**Commit/source:** baseline ce23136 `src/services/runtime.py:435+` không copy safety_hold_booking_ids; AI-4 `runtime.py:499–535` thêm copy set độc lập. Regression nhánh `test_safety_event_delivery.py:358–385` tạo lỗi charging model rồi qua fail-safe; reviewer viết thêm probe quan sát độc lập, không chỉ assert tên field.

**Evidence chạy mới:** cùng fleet DC/AC và lỗi adapter trả pin×3 cho dc-a, restore adapter rồi xử lý event:

```text
ce23136: live_holds=[dc-a], live_kw=0; fork_holds=[], fork_kw=33
4658b1f: live_holds=[dc-a], live_kw=0; fork_holds=[dc-a], fork_kw=0
```

**Rationale:** bản sao admission không được tự hồi phục xe lỗi mà live đang hold. **Counterargument mạnh nhất:** fork không điều khiển live; đúng, probe không chứng minh live bị cấp sai điện. Lỗi làm ước tính/admission không theo trạng thái an toàn mà nó phải mô phỏng. **Acceptance criteria:** copy hold độc lập, replan/assignment/old approval không cấp lại điện; giữ cả live và fork0kW, mutation set của fork không đổi live. **Verdict:** fix trường hợp hold đã thiết lập được xác nhận; không suy rộng sang hard event chưa xử lý (S02).

### Cặp regression cùng nội dung, không dùng số test thay assertion

Chép nguyên test safety từ ref AI-4 thành file **mới chỉ trong Temp** `tests/test_services/test_x02_safety_review.py` của cả hai snapshot, SHA bytes như nhau: `ffa4747a23522fcba02cbb32bcf9c232f5610854e6adb66bbcb955421765b4df`. Không sửa source/product test ở repo làm việc.

| Nhóm assertion | ce23136 | AI-4 final |
|---|---|---|
| Fork hold sau trip (1) | FAIL: hold rỗng | PASS |
| R07 hai barrier (2) | FAIL: clock tới phút6 thay1; read dời boundary2 phút khi solver chờ | PASS |
| G1-F01 failure window trace/record/notify/cancel/power-emergency (5) | FAIL: không emergency và hard event không còn retry được | PASS theo assertion an toàn của nhánh |
| G1-F02 blocked/partial/pending/no_commands (4) | FAIL: hard event biến mất/interlock không được bảo toàn | PASS: event còn pending, physics dừng; tối đa3 dispatch attempts |
| G1-F02 sink lỗi sau apply (2) | PASS từ baseline ở các fixture này | PASS; **không** báo hai ca này là fail-before ở baseline |
| G1-F03 old SET_POWER/ASSIGN approval (2) | FAIL: audit executed=true | PASS: executed=false, setpoint0 |

Tổng cặp chọn lọc: baseline **14 failed,2 passed**, 25 deselected; final16 ca này nằm trong nhóm targeted130 passed. Failures baseline là assertion hành vi, không phải thiếu API/import. Không tuyên bố đã tái lập nguyên bộ lịch sử19/20 trên mirror G1 ban đầu; mirror đó không có object local. G1-F01 mixed batch/overflow và cancellation lúc dispatch cũng chạy trên final trong targeted130, nhưng không được ghi là fail-before baseline khi test dùng API queue_events mới.

### X02-S02 — Cao, CONFIRMED: fork làm mất interlock của hard event còn pending

**Commit/source:** AI-4 final4658b1f `runtime.py:113,150–198,499–535`; `admission.py:62–68`. Fork copy hold đã thiết lập nhưng không copy `_pending_safety`/event chưa xử lý. Admission dựng fork ngay đầu coroutine, không có barrier buộc hard event live được xử lý trước capture.

**Evidence reviewer mới:** tạo cùng charging-model hard violation, đưa events vào runtime bằng queue_events, **chưa gọi handler**; fork rồi gọi TICK trên fork:

```text
live_pending=true; live_holds=[]
fork_pending_at_capture=false; fork_holds=[]; fork_kw(dc-a)=33
```

Assertion “fork phải xử lý pending fault trước khi planning nonzero” **FAIL** trên4658b1f; product source không bị thay. Đây khác S01: hold chưa được tạo vì handler chưa chạy.

**Rationale:** dữ kiện an toàn đã biết ở thời điểm capture không đi theo snapshot; quote/booking có thể mô phỏng xe lỗi như xe bình thường. **Counterargument:** live delivery thường được schedule ngay; atomic full snapshot được hoãn G3. Scheduling không chứng minh delivery hoàn tất trước fork; không đòi triển khai cả G3 để bảo toàn sự kiện an toàn đã biết. Probe dùng boundary runtime/fork thực, chưa chứng minh endpoint luôn chọn đúng interleaving này. Live vẫn có pending interlock, **không kết luận live bị cấp điện sai**.

**Acceptance criteria:** capture trạng thái an toàn nhất quán dưới cơ chế đồng bộ phù hợp; fork giữ/tiêu thụ pending hard events trước planning hoặc từ chối admission có nhãn chưa đủ điều kiện; regression cả charging-model và aggregate fault, không chia sẻ pending mutable state giữa fork/live. **Verdict:** blocker đối với khẳng định G1 đã bảo toàn safety state cho mọi fork; cần sửa/test trước khi nhập nguyên candidate.

### X02-S03 — Trung bình, CONFIRMED: safety resolved không đồng nghĩa hard event đã được giao bền

**Commit/source:**4658b1f `control_loop.py:80–102,441–479`, `runtime.py:173–198`. `_deliver_safety` acknowledge và xóa hard pending ngay sau readback, rồi `_on_event_locked` mới record_event/notify. Ordinary outbox đã drain. Không có retry ledger riêng cho side effects sau acknowledge.

**Evidence reviewer:** hạ nguồn30kW, queue hard event, fault-inject `rt.store.record_event` raise sau safety dispatch; bỏ fault, gọi deliver_pending:

```text
safety_pending=false; event_stored=false; event_retained=false
total_output_kw=28.499  # trạm đã về trong nguồn30kW với conversion0.95
```

Assertion “event timeline phải được lưu hoặc còn retry được” **FAIL**. Old physical trace có thể vẫn chứa vi phạm; không nói mọi evidence bị xóa. Assertion failure-window của nhánh chỉ cần emergency đã xảy ra **hoặc** pending còn, nên không phát hiện mất timeline sau an toàn.

**Rationale:** claim reliable delivery của hard event không được chứng minh bởi readback an toàn; incident timeline/notification có thể thiếu, ảnh hưởng WHY/audit. **Counterargument:** ưu tiên safety hơn logging, không nên giữ clock khi trạm đã an toàn. Đồng ý; yêu cầu là tách safety-resolution acknowledgment khỏi delivery/retry acknowledgment, không bắt giữ physics vì notification lỗi. **Acceptance criteria:** lỗi record/notify sau apply vẫn có delivery record/retry idempotent; không dispatch lại không cần thiết hoặc đóng băng trạm đã an toàn; test riêng stored/retained/notification states. **Verdict:** không phải electrical violation mới, nhưng phải sửa hoặc thu hẹp contract và chuyển task được chấp nhận rõ trước khi claim “không mất hard event”.

### Locking, clock, starvation và regression admission

| Chủ đề | Đánh giá trên4658b1f | Giới hạn / điều kiện nghiệm thu |
|---|---|---|
| Lock order | decision_lock lấy asyncio lock, đặt paused flag dưới `_clock_lock` rồi nhả RLock trước await; clock step/enqueue/drain dùng cùng RLock; HybridStation RLock riêng. Không thấy đường mặc định chờ asyncio lock từ thread đang giữ clock lock. | Hai barrier + cancellation chạy đạt; không chứng minh không deadlock với mọi future callback/extension. Cần giữ thứ tự khóa này khi port. |
| R07 | Fail-before thật cho read chạy qua phút vi phạm và read dời trace boundary khi solver chờ. Final giữ boundary và không step khi pending. | Full snapshot liên DB/runtime/booking vẫn chưa atomic; S02 là một counterexample cụ thể đã biết, không gom mọi race thành bug đã xác nhận. |
| G1-F01/02 | Hard registry không eviction, retain trước lock, hard-first trước phần trace/sink có thể lỗi; verify held setpoint qua safety_state, không dùng display power đã acceptance-clip để kết luận an toàn; retry3 rồi giữ interlock nếu unresolved. | Ordinary deque vẫn có giới hạn và có thể evict; hard registry/process crash/restart không durable. S03 là gap sau acknowledgment. Không gọi cơ chế này “exactly once” end-to-end. |
| Starvation/liveness | Retry exhausted cố ý fail-closed; không có bảo đảm tự phục hồi sau3 lần nếu setpoint vẫn unsafe. request_delivery có thể tạo task mỗi lần đọc, không thấy coalescing in-flight. Solver và sinks vẫn được await trong decision lock. | Nguy cơ backlog/latency/memory khi lỗi kéo dài hoặc đọc dồn: **UNVERIFIED**, không có load test. Cần vận hành xác nhận recovery/escalation; không coi pause đúng thiết kế là deadlock đã tái hiện. |
| Simulation clock | Physical time dừng ở violation cho tới readback resolved, read-driven step hoãn lúc decision; trace decided_at đổi sang station.now. Wall clock/runtime clock không ngừng tương ứng. | Có thay semantics ở lỗi và concurrent read, phải review như bug-fix có chủ ý; không tuyên bố thời gian hoàn toàn unchanged. Không sửa kernel/TimeConfig/solver policy. |
| Admission/concurrency | Targeted admission_consistency và booking_concurrency chạy đạt cùng foundation/fork tests; book/change/cancel chuyển outbox.extend sang queue_events. | Existing tests không phủ S02; pass không chứng minh toàn snapshot consistent. |
| Old approvals | resolve_approval dùng decision_lock, advance, execute_approved với cả safety_holds và safety_pending; dispatcher chặn cả occupant-held hoặc assigned booking-held, chỉ STOP/SET_POWER0 qua interlock và vẫn phải Guard check. | Phải bảo toàn call-site kwargs và lock khi tích hợp, không chỉ giữ chữ ký có default. |

### Migration0004 và phân loại phạm vi G1

`490f433`/`4658b1f:migrations/versions/0004_full_decision_traces.py` thêm nullable JSON/JSONB full_payload, bảng decision_trace_bookings PK(booking_id,correlation_id), FK cascade tới decision_traces và index booking/time; downgrade bỏ detail/index table, giữ summary. Chỉ thêm0004, không sửa migrations cũ. `repository.save_decision_trace:315–345` upsert payload/summary và index trong cùng transaction, không mở lại closed trace khi retry. SQLite upgrade/downgrade/legacy-summary tests đã chạy trong targeted130. **PostgreSQL thật CHƯA KIỂM CHỨNG**, không suy từ SQLite hoặc dialect JSONB rằng deployment migration đạt; downgrade mất detail là tính chất phải chấp nhận trong kế hoạch rollback.

| Thành phần | Phân loại | Có bắt buộc cho sửa an toàn tối thiểu? |
|---|---|---|
| Copy hold, pending state đúng, chặn old approval, serialize clock/enqueue/drain, hard-first/readback | Bug-fix safety/admission bắt buộc | Có; S02/S03 cần được giải quyết đúng contract. |
| Deep-copy config/tariff/plan/DTO/commands/params và model isolation | Sửa isolation của fork, không phải đổi optimizer | Cần phần chứng minh không ảnh hưởng live; không tự gọi toàn bộ là tối ưu AI. |
| Trace stage/coverage/no_samples, giữ dấu hard violation | Sửa chất lượng evidence có liên quan safety | Có giá trị bắt buộc nếu dùng trace làm căn cứ an toàn/WHY; không thay physical interlock. |
| Full trace persistence/migration0004, booking lookup | Foundation phục vụ WHY và audit | Không phải điều kiện logic để copy hold/chặn old command; cần gate schema/persistence riêng. |
| planned_decision_facts/bindings, labels/fingerprint/evidence refs, temporal SQL pagination và Copilot DTO | Phần mở rộng dữ liệu/kiến trúc phục vụ AI-4 G1/G2 | Không nên coi tất cả là electrical bug-fix để bỏ qua review/duyệt phạm vi. |

Diff xác nhận không chạm `src/optimizer`, `src/simulator/core`, config, policy registry, OpenAPI hoặc CI ở AI-4 so ce23136. Thay HybridStation adapter hơn300 dòng và runtime/control_loop không phải “chỉ thêm WHY”. Không đề nghị sửa frozen policy để xử lý các findings này.

## 4. Priority1 — WHY Engine, evidence và temporal semantics

### X02-W01 — Trung bình, CONFIRMED: requested Consent minimum bị mô tả như approved minimum

**Commit/source:**4658b1f `src/services/copilot/why.py:932–956`; nguồn giá trị `hybrid_planner.py:_start_minimums/_fit_with_minimums` và `decide:138–149`. adjustments_kw là mức minimum **yêu cầu trước fit**; khi tổng minimum vượt cap, fit có thể co cả nhóm forced. Không thay consent hay optimizer trong probe.

**Evidence reviewer, runtime thật:** hai xe DC cùng consent max_start_delay0, nhu cầu đủ lớn, M3a với budgetDC78kW. Forced60kW mỗi xe, approved39kW mỗi xe. WHY trả:

```text
power.consent_forced_min_kw: stage=approved, value=60
approved_setpoints_kw[dc-1]=39
“Công suất được điều chỉnh theo consent max_start_delay tối thiểu 60 kW
 và đã qua Physical Guard kiểm lại.”
```

Assertion semantic “không hứa approved minimum cao hơn approved power” **FAIL**. Direct pointer existence/value matching vẫn đúng; lỗi nằm ở stage/diễn đạt ngữ nghĩa và quan hệ giữa facts, không phải LLM bịa số.

**Counterargument:** minimum là yêu cầu nghiệp vụ nên fact60 hữu ích; đồng ý, phải ghi “minimum requested/đề nghị, không bảo đảm sau fit” và nói approved39 nếu muốn giải thích. Physical Guard kiểm giới hạn vật lý không xác nhận mọi consent minimum được thỏa. **Acceptance criteria:** tách requested minimum, approved allocation và shortfall; không sửa policy/consent để làm câu đúng; có paired fixture nhiều xe forced vượt cap, resident/operator assertions và oracle mutation bắt sai stage/claim này. **Verdict:** G2 cần sửa trước acceptance đầy đủ về factual grounding.

### Những phần G2 đã có bằng chứng tốt và giới hạn

| Mục | Source/evidence | Kết luận / counterargument / acceptance tiếp theo |
|---|---|---|
| Read-only | why.py:137–328 chỉ query repository/catalog, không sync_clock/step/apply; typed WhyQuery/ActorContext; tests read-only đạt. | SUPPORTED ở service. raw_traces/bookings_override là trusted test/service injection, không được expose trực tiếp qua HTTP/LLM. G6 phải dựng actor từ JWT. |
| Quyền và non-enumeration | evidence.py:92–179 kiểm station, role/scope, own booking, foreign và unknown resident cùng FORBIDDEN; resolve_evidence_ref:480+ kiểm ref_id/schema/cid/policy/time/path; safe projection + scan toàn answer. | Tests resident/operator, stale/ref tamper/privacy đạt; không tìm phản ví dụ truy cập chéo trong lượt này. AuthorizedSubject là Python object trusted, không phải capability chống caller Python độc hại. API/JWT/WS chưa nối nên chưa end-to-end authorized. |
| Direct/derived facts | EvidenceCollector:633+ kiểm direct value với raw pointer; derived có op hữu hạn và refs cùng cid; reason chỉ dùng facts/refs đăng ký, có privacy gate. | Derived builder không tự chứng minh công thức/cause; oracle độc lập số học hữu ích nhưng W01 chứng minh pointer đúng chưa đủ nghĩa đúng. |
| Time/energy | trace_reader.py:136–488 tách decision/planned/effective/measured; superseding timeline, stale restart, bounds31days, limit100/cursor. :515–727 exact overlap piecewise-constant, high-water chống double count, point query chỉ power, không mặc định efficiency. | Fractional windows, duplicates, missing efficiency, future completion/violation attribution tests đạt. Không đồng nhất planned với measured; clock ngoài thực thi được ghi PARTIAL. |
| Thiếu dữ liệu | WhyStatus OK/PARTIAL/NO_DATA/FORBIDDEN/UNSUPPORTED; trace active/no_samples/incomplete/legacy, thiếu efficiency/causal evidence được annotate. | Đúng về các fixture đã chạy; parse timestamp/shape hỏng có thể raise thay vì typed fallback, nên API cần map validation/corrupt evidence; chưa tái hiện thành lỗi endpoint. |
| Cause/scope | why paths queue/power/deadline/incident/policy/overview phân loại observed, model-estimated, policy và conditional; final-fix tests chặn future hard violation/held booking khác. | Không thể suy cause từ tổng safety status. W01 là phần cần sửa mới; không dùng oracle31/31 chứng minh mọi claim của3216 dòng. |
| Complexity | why3216 dòng, evidence840, reader727; resolve next timestamp quét timeline mỗi trace, sample sort + iterate bookings; privacy scan mỗi ID trên serialized answer. SQL main page bounded100, station timeline limit500. | Khả năng bảo trì và worst-case latency chưa đo. Cần modules/helpers theo topic khi được giao, test >500 timeline/multi-page và tối đa retained samples; không refactor trong review. Không nâng thành bug performance đã xác nhận. |

Rerun oracle của nhánh (đọc implementation oracle riêng, không chỉ gọi production resolver làm chân lý) trên final: **31/31 cases**, refs260/260, direct223/223, derived25/25, temporal/subject248/248, causal19/19, usefulness17/17, abstention13/13, privacy0, mutations8/8. Các con số26/7 ở phần lịch sử báo cáo được final README cập nhật31/8; không coi là mâu thuẫn chưa giải thích. Bộ này dùng fixture và expected reason list do nhánh soạn, không độc lập về tổ chức hoặc oracle ngữ nghĩa toàn diện; W01 không nằm trong coverage đó.

## 5. Provenance các gate tự báo cáo

**X02-P01 — SUPPORTED về nội dung evidence; UNVERIFIED về thẩm quyền duyệt mirror.** Commit4658b1f lưu raw logs, patches, scripts, manifests; `git cat-file -t` d520ffb/fed2c5e/6ba13b8/2d15ca1 đều không có object trong repo. Không thể xác thực danh tính/thẩm quyền reviewer từ tên commit hoặc nhãn APPROVED. X-AI4-03 được xác nhận với giới hạn này; không kết luận review đó là giả.

Kiểm501 entries CHECKSUMS ở5 gói evidence:193 khớp byte ngay,308 khớp sau chuẩn hóa CRLF→LF, **0 khác biệt không giải thích,0 file thiếu**. Git export trên máy core.autocrlf=true sinh CRLF cho các file text; không dùng raw hash khác để cáo buộc sửa evidence. G2 final patch canonical-LF SHA `97ffb4758af2c0721b5a35bb19b30da0b4c18f0aebc4c03f24554f79748fc528` khớp README. Index target blob prefixes của candidate patches khớp15 product/test/migration paths tại490f433 và12 tại4658b1f. Đây là kiểm linkage patch→committed blobs, **không** chữ ký người duyệt hoặc rerun mọi historic gate.

**Counterargument:** mirror không truy cập được nhưng có đủ patch/raw để review source; đồng ý, không chặn đọc hay các tái hiện ở đây. **Acceptance criteria:** owner ghi reviewer, authority, base/candidate SHA local và verdict trên đúng SHA; nếu cần dùng approval lịch sử thì cung cấp mapping có thể xác minh. PostgreSQL, CI, deploy vẫn CHƯA KIỂM CHỨNG. Không cần GitHub cho X-02.

## 6. Priority2 — X-BF-01…07 và Git ancestry

Mọi source be-fe dưới đây ở `b92e61a`; so với core ce23136/AI-4 final4658b1f. Findings kế thừa được kiểm lại, không biến test đạt trên nền cũ thành evidence tích hợp.

| Finding | Verdict độc lập | Source/evidence | Counterargument và acceptance criteria |
|---|---|---|---|
| X-BF-01 nền cũ | CONFIRMED; “mọi backend phải viết lại” quá rộng | Merge-base68692ee; core ahead81, be-fe ahead12; be-fe routes.py:28–30 import src.agents; không có kernel/admission/physical package mới. | Nền cũ do thời điểm tạo nhánh, không phải mọi diff đều sai. Port từng thay đổi API/domain có giá trị; không chép lại legacy engine. Test trên nền mới. |
| X-BF-02 contract | CONFIRMED | OpenAPI core StrategyName4 policy; be-fe có cả A–D cũ **và** B0/M2b/M3a/M3b, thiếu GET simulation/policies; thêm4 endpoint resident (approvals, quote-change, read-all, site-map). Thiếu provenance/assumptions/event safety fields mới; S8 cũ vẫn dùng A–D. | DTO mới hữu ích, có thể additive. Acceptance: chọn contract core làm nền, giữ policy_id/version/correlation/violation metadata, thêm endpoint có test, sinh lại OpenAPI/types và chạy S8 trên registry; không copy schema cũ nguyên file. |
| X-BF-03 DB/WS live trong on_event | CONFIRMED semantic incompatibility nếu port nguyên | control_loop.py:92,208–221 gọi broadcast đọc repository.list_bookings; station_service.py:172+ dùng active_booking/get_booking toàn cục. Core fork/benchmark dùng rt.store RAM. | Trên nền cũ chưa fork nên tests không thấy. Acceptance: projection từ store của runtime, chỉ phát cho live, kiểm fork/benchmark không đọc dữ liệu/sink live, không thêm I/O UI vào đoạn quyết định an toàn. |
| X-BF-04 Safety Hold khi resolve conflict | CONFIRMED bằng fault-injection độc lập | be-fe control_loop.py:183–185 execute_approved4args dưới rt.lock; ai-4 :258–265 truyền safety_holds/pending dưới decision_lock. Reviewer monkeypatch caller bỏ hai kwargs trên code AI-4: assertion no-execution của ca G1-F03 lại FAIL, trong khi vẫn chạy được vì defaults. | Approval.executed mới là cải tiến đúng, không phải lý do loại mọi logic BF. Acceptance: giữ guard/decision_lock của safety core, bổ sung metadata/broadcast BF quanh đó; regression held SET_POWER, ASSIGN, pending hard, STOP0, recheck Guard phải đạt. |
| X-BF-05 quote-change | CONFIRMED | charging_service.py:215–225 dùng _what_if đồng bộ, không consent parity/assumptions/fingerprint flow hiện hành. | Preview endpoint nên giữ, không cần bỏ UI. Port vào admission async/fork đúng consent, labels/conditional certainty, không mutate live; ownership404 và concurrent booking tests trên nền mới. |
| X-BF-06 budget/cap | CONFIRMED | station_service.py:102 dùng zone_cap_kw; models/station.py trả physical_zone_cap_kw trước (DC120), PowerTiers.tsx:75 fallback22/78. | Số cap có ích nếu nhãn đúng. Acceptance: tách physical cap và assigned/default optimizer budget, ghi input/output units, không hardcode layout/policy budgets trong UI; test DC cap120 vs budget78 và dynamic budgets. |
| X-BF-07 phần đúng | SUPPORTED trong phạm vi | Idempotent cancel; executed từ Guard recheck; site-map privacy projection busy/idle/fault (FINISHED busy); tests own resident/broadcast. Reviewer chạy6 targeted API tests:6 passed. | Những API tests chỉ trên b92e61a, FE component tests dùng mock data; không chứng minh runtime mới/E2E. Port ý tưởng và assertion nhưng giữ booking_lock/fingerprint/events mới, không chép cancel cũ làm mất concurrency protection. |

### X02-G01 — DISPUTED: merge ref develop này sẽ khôi phục code cũ

**Claim X-01 §6.3:** merge develop cũ vào unified-core kéo lại src.agents/LP A–D.

**Evidence Git chạy mới:** `git merge-base develop_ref unified_ref = 68692ee`; `git merge-base --is-ancestor develop_ref unified_ref` exit0. Với đúng hai refs đã khóa, develop là tổ tiên của unified-core; một merge develop vào unified-core sẽ là already-up-to-date, **không** reintroduce các file đã xóa. Không thực hiện merge để chứng minh điều đã xác định bằng ancestry.

**Rationale:** ancestry khác với trạng thái cây có file cũ. **Counterargument:** merge BE–FE hoặc chọn “theirs” có thể đưa code cũ trở lại; đúng, đó là ref khác và conflict resolution khác, được X-BF-01…06 chứng minh. **Acceptance criteria:** sửa claim vào đúng ref/operation, kiểm merge-base trên ref mới nếu develop di chuyển; không cảnh báo no-op merge như hành động khôi phục code. **Verdict:** claim cụ thể bị phản bác; khuyến nghị port BF vẫn có lý do semantic độc lập.

X-01 báo9 file textual conflict; X-02 **không chạy merge/merge-tree/merge-file** theo ranh giới Human. Exact count9 là reported, chưa tái lập lượt này. Đã kiểm trực tiếp overlap/semantics ở routes, dispatcher, models/station, charging/control và contract. “Merge sạch” AI-4 không có nghĩa safety/grounding đạt; “có conflict” BF không có nghĩa mọi component phải bỏ.

## 7. Danh sách reuse / port / loại khỏi candidate

| Component | Hướng đề xuất, chưa thi hành |
|---|---|
| AI-4 fork hold/dispatcher guards/hard interlock | Giữ như nguồn sửa lỗi cần thiết; **remediate S02 và delivery gap S03**, lập patch safety có phạm vi và regression riêng, không lấy nhãn approved thay review. |
| Trace stages, coverage, safe serialization | Giữ nguyên tắc phân biệt planned/approved/effective/actual; kiểm riêng lỗi trace không chặn fail-safe, không tuyên bố evidence luôn đầy đủ sau sink failure. |
| Migration0004/full_payload/index | Port cùng feature trace persistence khi được phép đổi schema; Postgres/upgrade legacy/rollback plan riêng. Không gộp mặc định vào patch hold tối thiểu. |
| WHY typed models/reader/evidence | Tái sử dụng sau sửa W01; giữ read-only/auth abstraction; G6 nối JWT/API và đánh giá tải riêng. Không đưa test overrides/trusted actor thành input người dùng. |
| BE–FE SiteMap/ChangeBookingDialog/approval screens/layout | Reuse UI/UX và các assertion privacy/action-error; port API client/types/fields trên contract mới. |
| BE–FE quote_change/cancel/read-all/approval metadata | Port hành vi nghiệp vụ có giá trị; giữ async admission, consent thật, optimistic booking locking, event handling và Guard mới. |
| BE–FE PowerTiers/S8/schema/WS projection | Sửa cap/budget, registry policies, provenance và live-only sink; regenerate contract trên backend mới. |
| Legacy src.agents graph, LP A–D, LiveStation/base shims và generated schema cũ nguyên file | Không reintroduce vào nền core. Tham khảo chỉ như lịch sử, không dùng làm implementation tích hợp. |
| HOW-TO/WHAT-IF chưa triển khai | Không kéo vào scope WHY bằng nhãn Approved của ADR ngoài sổ chính. Human chốt/hoãn riêng; không bỏ source có giá trị chưa được review chỉ vì scope tương lai. |

**Integration gate đề xuất:** Human giao remediation X02-S02/S03/W01 và xác nhận exception sửa an toàn lõi frozen; reviewer kiểm lại phản ví dụ và regression. Sau đó chốt patch safety/trace-persistence/WHY theo phạm vi, hợp nhất contract, port BF chọn lọc rồi chạy integration tests trên **cùng candidate**, gồm pending safety fork, G1-F03 (SET_POWER/ASSIGN), read/admission barriers, resident privacy, site-map no live sink in fork, registry S8 và migration Postgres khi có môi trường được phép. Không đòi sản phẩm đạt95% hoặc CI runner phải bật để hoàn thành review này.

## 8. Kiểm thử thực chạy, evidence và giới hạn

| Lần chạy mới | Kết quả và ý nghĩa |
|---|---|
| ce23136 same16 safety assertions |14 failed,2 passed,25 deselected,3.63s; không phải14 setup error.|
| AI-4 targeted10 files |130 passed,16.25s: safety delivery/fork/trace/migration/admission-consistency/booking-concurrency/4 WHY files. Không full suite.|
| Reviewer fork probe baseline |1 failed,0.80s; ghi trực tiếp live0/fork33.|
| Reviewer probes AI-4 lần đầu |2 passed,1 failed,1.12s: handled hold đúng; pending fork lỗi; bỏ safety kwargs tái mở approved command như dự đoán.|
| Reviewer event-delivery probe AI-4 |1 failed,3 deselected,0.86s; physical safe nhưng timeline event không stored/retained.|
| Reviewer WHY runtime probe |1 failed,0.84s; forced60 vs approved39 và summary như W01.|
| WHY oracle của nhánh rerun |31/31 cases,8/8 mutations,0 auth/privacy; denominators §4.|
| BE–FE6 targeted API tests |6 passed,25 deselected,0.95s; chỉ nền b92e61a.|

Công cụ trả exit0 ở các shell có lệnh Get-Content sau pytest; **không** dùng exit shell đó để gọi tests pass. Bảng lấy summary/assertion thực trong log. Lần baseline sandbox lỗi SQLite temporary DB, đã chạy lại ngoài sandbox với quyền được cấp. Một lần probe reviewer dùng sai tên enum M3A, đã sửa **chỉ test tạm** thành StrategyName('M3a'); không tính lỗi harness này là lỗi WHY. Warning pytest async fixture scope giữ nguyên, không sửa cấu hình.

Lệnh test chính (venv tuyệt đối `D:\VIN\P-019\.venv\Scripts\python.exe`, PYTHONUTF8=1, PYTHONDONTWRITEBYTECODE=1, cwd snapshot tương ứng):

```text
-m pytest tests/test_services/test_x02_safety_review.py -k "fork_keeps_the_hold_after_a_real_trip or threadpool_clock_cannot or hard_event_survives_failure_window or unsafe_failsafe_dispatch or rechecks_safety_when_sink or held_booking_cannot_use_older" -q -p no:cacheprovider --tb=short
-m pytest tests/test_services/test_safety_event_delivery.py tests/test_services/test_fork_isolation.py tests/test_services/test_decision_trace.py tests/test_db/test_migrations.py tests/test_services/test_admission_consistency.py tests/test_services/test_booking_concurrency.py tests/test_services/test_why_engine.py tests/test_services/test_why_temporal_and_auth.py tests/test_services/test_why_g2_remediation.py tests/test_services/test_why_g2_final_fix.py -q -p no:cacheprovider --tb=short
-m pytest tests/test_services/test_x02_independent_review.py -q -s -p no:cacheprovider --tb=short
-m pytest tests/test_services/test_x02_independent_review.py -k safe_readback -q -s -p no:cacheprovider --tb=short
-m pytest tests/test_services/test_x02_why_review.py -q -s -p no:cacheprovider --tb=short
eval/evidence/2026-11-24-ai4-4-1-remediation/run_why_eval.py <Temp-root>/why-oracle
-m pytest tests/test_api/test_flows.py -k "cancel_twice or pending_approvals_list_only_own or decision_reports_executed_flag or resident_site_map_hides_other_residents or site_map_broadcast_is_per_resident or quote_change_of_other_residents" -q -p no:cacheprovider --tb=short
```

Không chạy full suite864/623 hoặc FE44, lint/build, full benchmark/golden, Postgres, LLM thật, CI, VM hoặc deploy. Những số X-01/gate lịch sử chỉ được xem là reported trừ kiểm lại đã nêu. Không thử tích hợp branches, nên không kết luận candidate merged đã chạy.

Reviewer probes chỉ ở Temp: `tests/test_services/test_x02_independent_review.py`, `test_x02_why_review.py`; không sửa implementation snapshot. Cách tái lập độc lập chính:

1. Dùng helpers fixture `_sim_runtime`/`_trip_charging_model` trong safety file ref4658 để tạo actual trip cho S01; fork_runtime, TICK và đọc connector power/hold set trên cả baseline/final.
2. S02: tạo `_sim_runtime(failsafe=True)`; monkeypatch adapter.step chỉ trong test để battery_kwh(dc-a)×3 khi kw>0; sim.step5; restore adapter; rt.queue_events(events); **chưa on_minute live**; fork_runtime rồi TICK fork. Quan sát pending/holds/kW như §3. Không chỉ giả lập hold bằng cách đặt set.
3. S03: `_charging_live`; disable auto deliver trong fixture để kiểm interleaving; hạ available_power_kw30, clock+4min, sync_clock thu hard; monkeypatch record_event raise; on_event(TICK) xử lý safety rồi lỗi; restore; deliver_pending; kiểm event_id trong repository.list_events và outbox, cùng readback power.
4. W01: `_make_booking` hai DC kwh60/hours2 với ConsentScope(max_start_delay_minutes=0), `_sim_station(M3a)`; TICK, raw trace; explain_why POWER cho dc-1 với trusted actor operator/live clock tại T0 và mappings booking. So consent.adjustments60, approved39 và fact stage/summary. Không sửa raw trace để tạo số sai.

Logs tạm và SHA-256 (cùng gốc Temp ở §2; tên file là evidence trực tiếp để kiểm nếu thư mục chưa bị dọn):

```text
before-tests.log 288db10c268aab1267a729276ccfe39494a1f722e3d10fed73b6bf8eccd59dda
after-tests.log ab89aeda1fadb40cc34bc18f153b10f8ea5a63c713c84f0f720229bea8c5e5ee
independent-before.log d232202b41fc335ef306337453012617ca00522de83309c96f996e51ebd2bacc
independent-after.log e8f81702ce6d1e5e4218d1b05c378a63b00fe8c4d1b7e0b52c00ddada66344da
independent-event.log dcac243c0f1d53ed5cebad8726ec6a5da40a0732322463576a6b9f57c8542680
independent-why.log 1c51e31e4d14aa2233414eed4d415e5c10e723ad0a837d674ca6ebaae7079249
why-oracle.log 1adb891ca7930fa27cf0655699310afcdb83cf269c580533713bed8dd109bfc4
be-fe-targeted.log b62413d22a104fb1070d67b6a6a7e49bd9282e0eb4f1a6770c77222ccdabd469
```

Các log/fixtures tạm không phải baseline sản phẩm; các refs, source/assertion, tái hiện, output và hash được lưu bền ở báo cáo này. Nếu cần archive raw/test reviewer vào repo, giao phạm vi evidence riêng; không tự thêm source/test hay thay artifact lịch sử trong X-02.

## 9. Bàn giao và những quyết định thực sự cần Human

1. **Cho phép một lượt remediation riêng** các findings S02/S03/W01 trên nhánh phù hợp, giữ frozen optimizer/policy; G1 safety exception không đồng nghĩa duyệt toàn bộ refactor/persistence/AI scope. Đây là việc cần quyết ngay để tiến tới integration.
2. **Chọn port BE–FE trên nền core sau safety remediation** thay vì lấy nguyên backend cũ hoặc ưu tiên “theirs”. Hợp nhất contract trước khi regenerate FE types; giữ giá trị UI và domain behavior đã có bằng chứng.
3. **Phạm vi WHY/WHAT-IF/HOW-TO và thay registry:** chỉ thay theo quyết định Human hiện hành trong HANDOFF; không lấy ADR “Approved” của nhánh tự mở scope. C-1/H-4 và phê duyệt đóng/migration/deploy vẫn là quyền riêng, không suy từ báo cáo.

X-02 không chờ mirror/GitHub để hoàn thành nội dung review. Owner nhánh cần làm rõ provenance approval nếu muốn dùng gate lịch sử làm căn cứ phê duyệt; các source/test observations mới ở đây độc lập với nhãn đó. Chuyển reviewer sau remediation chỉ kiểm các phản ví dụ và integration contract liên quan, không lặp audit vô hạn.

**Integrity workspace:** chỉ thêm báo cáo này và sửa ô checkpoint HANDOFF; source, migration, policy, optimizer, refs và tài liệu đã nghiệm thu giữ nguyên. Snapshot báo cáo X-01 SHA `290daeb177af4603899b355cf76c566bc2e33129bfbc91c39a968833e0b81b57`; registry `7f94dca1f7fe7e21d26b89da6b77a84916b69ee085c383ee6f2d116b0fcfadb8`; sơ đồ `2a88672d1cbe765b3945a45ed861e2c2e0d3884b3465cfd9ad33ef2f746639db`; ADR README `f90a42b77e9ecabea93a404f6dbacb941e575f87a66f24de404f8cabb201a51c`; CLAUDE `36ac0e23e81fadd5e78ea19bea26ef33c6b96303b44507b57283396a6e2e910a`; ARCHITECTURE `9f7e7766feb1068b466b0c3812948beb6f3d2f88903e9cb80e9709d192ea2ef4`.
