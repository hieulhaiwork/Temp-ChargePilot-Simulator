# Kết quả Independent Review Phase 1

Reviewer: Codex, độc lập với Claude soạn tài liệu. Ngày 2026-11-24, khoảng 18:18–18:28 UTC+7.
Code: `ce23136`, nhánh `feature/unified-core`. Kết quả: **CHƯA ĐỦ ĐIỀU KIỆN ĐÓNG PHASE 1**.
Đã hoàn thành lượt kiểm K1–K15; các phần thiếu bằng chứng ghi rõ bên dưới, không coi là đã nghiệm thu.

## Kết luận cho người giám sát

Registry dùng được làm bản đồ sơ bộ, cần sửa trước khi dùng làm căn cứ nghiệm thu hoặc chọn policy.
814 là tổng 604 backend + 180 simulator + 30 frontend; không mâu thuẫn với 604. Có 8 test bỏ qua.
Baseline thực sự có tỷ lệ đúng hạn 29–32%, nhưng trộn kịch bản cũ với bãi mới và bỏ qua 40/160 sự cố.
Có trường hợp tải đầu vào vượt năng lực vật lý ngay cả với giả định lý tưởng; chưa tách được toàn bộ nguyên nhân tỷ lệ thấp.
Xe đầy vẫn chiếm cổng và hồ sơ cư dân đều có test: registry đã bỏ sót bằng chứng này.
Test đạt không chứng minh mục tiêu ≥95%, an toàn ngoài mô phỏng, hay AI thật đã đạt.
CI của code đang review chưa được xác nhận; runner tắt không phải lỗi source. Không cần bật VM trong Phase này.
Không sửa source/test/API/DB/CI, không duyệt ADR, không commit/push/merge/deploy.

## Phạm vi và cách kiểm

VERIFIED = trực tiếp đọc/chạy/tính; SUPPORTED = có bằng chứng chưa đầy đủ; INFERRED = suy luận;
UNVERIFIED = chưa kiểm chứng; CONTRADICTED = bị bằng chứng phản bác. Nhãn áp cho mệnh đề cụ thể, không cho toàn hệ thống.

Git đầu lượt kiểm khớp HANDOFF §1.8: sáu file sửa là ARCHITECTURE.md, CLAUDE.md, docs/PRD.md,
docs/adr/README.md, docs/architecture_diagram.md, docs/handoff/HANDOFF.md. Untracked:
AGENTS.md, docs/FEATURE_REGISTRY.md, docs/communication/, docs/handoff/REVIEW_PHASE1.md,
eval/results/benchmark.json, benchmark.md, manifest.json. Có cảnh báo không đọc được cache và một số thư mục
merged-sim; không coi các thư mục đó đã được kiểm. Giữ nguyên thay đổi của Implementation Agent.

Lệnh thực chạy:

```text
git status --short
git diff --stat
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git show 8f6f08a:ARCHITECTURE.md
.venv/Scripts/python.exe -m pytest tests src/simulator/tests -q -p no:cacheprovider
  PYTHONUTF8=1: 784 passed, 8 skipped in 62.41s
.venv/Scripts/python.exe -m pytest tests --collect-only -q -p no:cacheprovider
  612 tests collected
.venv/Scripts/python.exe -m pytest src/simulator/tests --collect-only -q -p no:cacheprovider
  180 tests collected
frontend: npx vitest run
  5 files passed, 30 tests passed
gh run list --limit 10 --json headBranch,headSha,status,conclusion,createdAt
gh run list --branch feature/unified-core --limit 100 --json headSha,status,conclusion
  []
```

Python lần đầu trong sandbox lỗi mở SQLite tạm trước khi chạy logic; dừng và chạy lại ngoài sandbox được phép.
Vitest lần đầu lỗi spawn EPERM; lần chạy ngoài sandbox đạt. Không dùng hai lỗi môi trường này để kết luận code lỗi.
Không chạy build, Postgres thật, LLM thật, deploy, CI hoặc benchmark mới. Tái tính JSON baseline bằng Python stdlib,
không chỉ đọc bảng tổng hợp của Claude. Kết quả test là trực tiếp; provenance và KPI baseline là dữ liệu lịch sử.

## Bảng 15 khẳng định

| Mã | Phán quyết | Bằng chứng và giới hạn |
|---|---|---|
| K1 | ĐÚNG — VERIFIED | `src/forecast/__init__.py:1` gọi dự báo F6; `src/api/simulation.py:1` gọi S8 là F7; `src/db/tables.py:24` gọi hồ sơ F8. So PRD §5 và registry §1.1: nghĩa mới khác. |
| K2 | MỘT PHẦN — SUPPORTED | `git show 8f6f08a:ARCHITECTURE.md` xác nhận FR7 gán cổng, FR8 sự kiện, FR12 Guard, FR13 phê duyệt, FR14 log, FR15–16 web/WS, FR17 dự báo, FR18 sự cố. Registry chưa phải bảng đầy đủ: thiếu dòng ánh xạ FR10–11 cũ; không có đối chiếu từng AC1–AC8, MT. Chưa xác minh mọi biến thể trong mọi plan cũ. |
| K3 | ĐÚNG — VERIFIED trong cây hiện tại | `rg` bốn tên trong `tests src` không có kết quả; bảng lịch sử thật sự dẫn các tên đó. Không kết luận chúng chưa từng tồn tại ở commit khác. |
| K4 | ĐÚNG — VERIFIED | 784 Python đạt, 8 bỏ qua; collect riêng 612 backend, 180 simulator; 30 frontend đạt. Các skip thuộc forecast. 604+180+30=814; tổng thu thập kể cả skip là 822. |
| K5 | ĐÚNG trong phạm vi — SUPPORTED | `src/agents/` chỉ có `__init__.py`; bảng ORM tại `src/db/tables.py` không có bốn bảng được nêu; tìm trong migrations không thấy. Có approvals và decision_log, không có nghĩa vòng đời AI-1 đã tồn tại. Chưa quét mọi database bên ngoài. |
| K6 | ĐÚNG — VERIFIED | `src/llm_chat/guardrails.py:119` kiểm số kWh và mã cổng; finalize gọi ở `src/llm_chat/nodes/finalize_node.py:98`. Không có kiểm từng mệnh đề với facts/reason_codes/evidence_refs. |
| K7 | SUPPORTED: chưa thấy implementation | Tìm mục đích/quãng đường/trip/purpose trong services và llm_chat không thấy bộ chuyển mục đích thành ràng buộc; tool dùng ChargeRequest đã có SOC/deadline. Tìm chuỗi không chứng minh tuyệt đối không có logic tương đương ở nơi khác; chưa thử với LLM thật. |
| K8 | MỘT PHẦN; nghi vấn thiếu mô phỏng bị CONTRADICTED | `queue.py:34–64`: AC rời khi tới departure; DC rời sau completed_at+delay hoặc departure. `kernel.py:642` đánh FINISHED không tự rút cổng. `test_hybrid.py:28` kiểm AC completed_at < departed_at, xe kế tiếp chỉ bắt đầu khi xe trước rời; DC trễ 5 phút. F14 UI và metric MT12 vẫn chưa được xác minh đầy đủ. |
| K9 | ĐÚNG về số, MỘT PHẦN về giá trị chứng minh | Tái tính 100 run xác nhận 0 ở ba trường violations, thứ hạng và trung bình. Nhưng 40 sự cố bị bỏ qua, ba scenario mang nhãn legacy không dùng benchmark. Xem F1–F3 bên dưới. |
| K10 | MỘT PHẦN — VERIFIED trạng thái nhánh | GitHub trả develop @68692ee failure và unified-core không có run. Chưa kiểm log job frontend để xác nhận nguyên nhân failure. Có run be-fe-integration đang queued. Runner VM tắt theo thông tin người dùng; không suy ra source lỗi. |
| K11 | ĐÚNG về cấu trúc — SUPPORTED | Test kiến trúc kiểm shim/base.py bị xoá, một StationKernel và đường dùng chung; toàn suite đạt. Interface đọc/ghi ở `src/models/station_protocols.py`, không phải kernel thay mọi vai trò interface. |
| K12 | ĐÚNG ở các bảng chính — VERIFIED | So BOUNDARIES `tests/test_architecture.py:34` với ARCHITECTURE mục Ranh giới module: phù hợp. Kiểm thêm standalone, core contracts, simulator consumers và chu kỳ đều chạy đạt. Không coi AST import test là bằng chứng bảo mật tuyệt đối. |
| K13 | ĐÚNG với provider mock — VERIFIED | `src/config.py:103–115` từ chối mock khi production. Không đồng nghĩa mọi hình thức mất mạng đều bị cấm hoặc phải cho mock vào production; demo dev/test là phương án khác. |
| K14 | MỘT PHẦN — SUPPORTED | 19 header đều Proposed; README không tự duyệt mới. Nhưng 018 và 014 cũng có nhóm C, nên brief gọi “4 ADR nhóm C” thiếu hai phần C này. “Không ADR nào đã duyệt” nếu hiểu tuyệt đối là sai: 005/006/007/008/009 ghi nhóm đã duyệt, 019 ghi đã duyệt hướng/Phase 0–1; chưa xác thực hội thoại gốc. Chưa thẩm định nội dung toàn bộ 19 ADR tới mức phê duyệt. |
| K15 | MỘT PHẦN — VERIFIED có giản lược sai | A bỏ bước admission lại với consent thật khi book trước khoá (`charging_service.py:235–304`). B vẽ advance sau apply rồi ghi trace; code on_event tiến đồng hồ/đóng trace cũ trước planning, mở trace mới sau dispatcher (`control_loop.py:66–137`); advance kế tiếp đo kết quả. C có đường giảm nguồn và fail-safe, nhưng tủ hỏng không nhất thiết cùng đường giảm nguồn; sơ đồ chưa diễn đạt batch/outbox. Không đủ chính xác để làm đặc tả thứ tự an toàn. |

## Phát hiện quan trọng: claim, bằng chứng và phản biện

### F1 — Cao: baseline không kiểm đủ sự cố được đặt tên

**Claim:** không dùng baseline hiện tại để tuyên bố đã kiểm đủ khả năng xử lý hỏng cổng của bãi hiện tại.
**Evidence (VERIFIED):** tái cộng incidents trong benchmark.json: planned=160, applied=120, skipped=40.
20 run connector_failure bỏ cả fault/restored tại A05. Notes ghi rõ topology không khớp.
`config/scenarios/peak_evening.yaml:1–4` ghi legacy 8×7 kW, không dùng nghiệm thu/benchmark;
baseline vẫn chứa peak_evening, connector_failure, power_drop cùng hai scenario hybrid.
**Rationale:** một sự cố không xảy ra không thử được phản ứng của hệ thống với sự cố đó; 0 vi phạm vẫn đúng cho tải thực đã chạy.
**Counterargument:** baseline cố ý đóng băng để kiểm parity refactor, không dùng nghiệm thu sản phẩm.
**Falsification:** có evidence gắn cùng run cho thấy A05 được ánh xạ sang cổng thật và sự cố thực sự áp; hiện JSON nói skipped.
**Limitations:** không chạy lại sự cố; không phủ nhận test đơn vị về fault hoặc parity.
**Verdict:** số liệu an toàn được xác nhận trong phạm vi thực chạy; diễn giải như đủ thử nghiệm sự cố là không được hỗ trợ.

### F2 — Cao: “khả thi từng xe” chưa phải “khả thi cả bãi”; chưa giải thích hết tỷ lệ 30%

**Claim:** tỷ lệ thấp có yếu tố tải vượt năng lực vật lý; chưa thể quy toàn bộ cho optimizer hoặc miễn trách nhiệm optimizer.
**Evidence (VERIFIED):** `simulation_service.py:162` chỉ kiểm max_charge_power_kw × số giờ >= requested_kwh.
Không xét cạnh tranh cổng, đường giảm công suất DC, tổng nguồn hay sự cố.
`compute_kpis:130–145` chỉ lấy outcomes có cờ này làm mẫu số, không phải mọi xe hoặc một workload đã chứng minh khả thi chung.
Không có xe feasible thì rate=1.0: cần báo mẫu số để không hiểu “không có mẫu” thành thành công.

Tính lại generator hiện tại, peak_evening seed=1: 30 xe, nhu cầu pin tổng **1378.6713 kWh**, AC **1183.1725 kWh**.
Ngay cả nguồn 35 kW chạy đủ 24 giờ với hiệu suất 100% chỉ có **840 kWh**; hai cổng AC 11 kW chỉ có **528 kWh**.
Đây là cận trên cố ý lạc quan: thực tế xe chưa đến, tổn hao và giữ cổng còn làm năng lực thấp hơn.
Generator không nhận từng xe qua admission mà tạo Booking CONFIRMED (`simulation_service.py:71–117`).

**Rationale:** workload này không thể phục vụ toàn bộ nhu cầu, dù policy lý tưởng. Nhận hàng loạt synthetic booking
khác với kiểm nghiệm tỷ lệ đúng hạn của yêu cầu đã được sản phẩm tiếp nhận qua admission.
**Counterargument:** cận năng lượng không chứng minh không thể đạt 95% *số xe*: có thể hy sinh ít xe có nhu cầu lớn;
seed 1 không đại diện mọi run. Hai scenario hybrid vẫn đạt thấp dù nguồn 106 kW.
**Falsification:** nghiệm tham chiếu phục vụ đủ nhu cầu toàn bộ chính workload trên trong cùng nguồn/thời gian sẽ bác cận này;
để bác nguyên nhân chính của tỷ lệ thấp cần nghiệm tối ưu theo số xe, giới hạn cổng và cùng vật lý trên từng seed.
**Limitations:** chưa giải LP/MILP tham chiếu; chưa tách ảnh hưởng hàng chờ, tối ưu chi phí, giữ cổng, admission và DC taper.
279.32 giờ lưu trú AC khi cắm từ lúc đến không được dùng làm cận bắt buộc: xe có thể chờ rồi mới cắm.
**Verdict:** VERIFIED workload ví dụ không đủ năng lượng cho mọi yêu cầu; INFERRED đây là một yếu tố tỷ lệ thấp;
UNVERIFIED đóng góp định lượng của từng nguyên nhân và khả năng đạt MT1.

### F3 — Cao về quyết định: giá rẻ hơn chưa chứng minh hiệu quả kinh tế tốt hơn

**Claim:** chưa có cơ sở chọn policy chỉ vì tổng tiền thấp nhất.
**Evidence (VERIFIED từ artifact lịch sử a9def2f):** trung bình đều trên 25 run/policy:

| Policy | Đúng hạn | Chờ phút | Chi phí VND | Điện giao trước hạn kWh | Điện thiếu kWh |
|---|---:|---:|---:|---:|---:|
| B0 | 30.2642% | 392.0084 | 722143.04 | 282.9004 | 681.2279 |
| M2b | 30.7023% | 392.5672 | 729863.44 | 286.4630 | 677.6652 |
| M3a | 29.1099% | 392.5672 | 685208.08 | 286.8178 | 677.3106 |
| M3b | 32.0880% | 392.7780 | 774704.96 | 332.7716 | 631.3566 |

**Rationale:** tiền và lượng điện phục vụ cùng thay đổi. M3b giao nhiều điện hơn M3a; cần so trong cùng mức phục vụ,
hoặc báo trade-off với số xe/điện thiếu. “Trung bình” ở đây là macro-average tỷ lệ từng run, không gộp mẫu số xe.
Chờ có cả xe chưa cắm, bị chặn quan sát tại deadline (`compute_kpis:132–135`); không phải chỉ thời gian chờ của xe được phục vụ.
**Counterargument:** nhóm có thể thật sự ưu tiên tổng tiền, chấp nhận ít xe đúng hạn hơn.
**Falsification:** workload khả thi cùng mức phục vụ và phân tích ghép cặp theo scenario/seed chứng minh M3a tốt hơn theo mục tiêu nhóm chốt.
**Limitations:** chưa tính khoảng biến thiên/kiểm định ghép cặp; không diễn giải chênh lệch là quan hệ nhân quả.
**Verdict:** thứ hạng tiền và đúng hạn đúng; “M3a tốt nhất” chưa được xác lập. Không tự đổi policy.

### F4 — Trung bình: registry bỏ sót bằng chứng và truy vết còn quá rộng

**Claim:** không nên hiểu bảng §3 là đã phủ mọi yêu cầu nghiệm thu.
**Evidence (VERIFIED):** `tests/test_services/test_service_contracts.py:162` có test cập nhật hồ sơ, đọc lại và từ chối xe lạ;
`src/simulator/tests/test_hybrid.py:28` có test chiếm cổng sau hoàn tất, cả hai chạy trong suite đạt.
Registry F10/I-3 và F14/I-2 chưa ghi nhận. Ánh xạ AC/MT chưa từng dòng; FR17/18 chỉ dẫn “test FE” và tổng 30 test,
không chỉ ra assertion cho từng yêu cầu màn hình. `src/db/tables.py` có 10 __tablename__, trong khi CLAUDE ghi 9 bảng.
**Rationale:** có test riêng bị bỏ sót làm đánh giá thấp; dẫn cả folder/tổng test có thể làm đánh giá cao khả năng phủ.
**Counterargument:** registry đã ghi rõ Tested không phải Validated, F14 còn yêu cầu UI và metric chưa kiểm.
**Falsification:** ma trận yêu cầu → test/assertion → điều kiện chạy chứng minh đủ từng mục.
**Limitations:** chưa kiểm mọi endpoint và mọi assertion frontend; không tuyên bố toàn bộ F10/F14 đã xong.
**Verdict:** sửa bằng chứng F10/F14; giữ trạng thái từng phần khi chưa có UI/metric/nghiệm thu. Các mã thiếu phải ghi chưa truy vết.

### F5 — Trung bình: sơ đồ và phạm vi cam kết Guard cần chính xác

**Claim:** code có một cửa apply_commands trên đường backend, nhưng không nên mô tả mọi đường nghiên cứu đều qua dispatcher.
**Evidence (VERIFIED/SUPPORTED):** `rg 'apply_commands\(' src` chỉ thấy lời gọi thực ở dispatcher:125,184;
test kiến trúc đạt. Kernel standalone có apply_approved/connect/hold_setpoint; test ràng buộc simulator chỉ dùng Guard vật lý.
ADR-002 đã ghi research/what-if chỉ có Guard vật lý; admission sản phẩm dùng fork runtime/control_loop.
`control_loop.py:66–137` khác thứ tự thể hiện ở sơ đồ B như K15.
**Rationale:** cần phân biệt an toàn vật lý với consent/HITL và cần biết trace ghi trước hay sau khoảng thực thi.
**Counterargument:** sơ đồ quản lý được phép lược chi tiết; đường sản phẩm vẫn qua dispatcher.
**Falsification:** đối chiếu call trace của một chu kỳ có clock/event cho thấy thứ tự sơ đồ đúng nguyên văn hoặc mọi primitive standalone đều qua dispatcher.
**Limitations:** AST không bắt mọi getattr/alias động; chưa phát hiện đường bypass sản phẩm thực tế. Không kết luận có lỗ hổng khai thác.
**Verdict:** cơ chế backend được hỗ trợ bởi code và test; phạm vi ngôn từ và sơ đồ phải thu hẹp cho đúng.

## Review kỹ thuật ADR quan trọng (không phê duyệt)

| ADR | Kết luận với code hiện tại | Giới hạn/phản biện và cách bác bỏ |
|---|---|---|
| 002 | SUPPORTED: dispatcher là cửa apply_commands của sản phẩm; interface nay ở models/station_protocols. | Ghi chú LiveStation/base.py lỗi thời; research vật lý không phải cùng đường HITL. Bác bằng lời gọi sản phẩm ngoài dispatcher. Test AST không phải sandbox bảo mật. |
| 006 | SUPPORTED: JWT, role dependency, resident_id do router gán, thread_id gắn user; tool không nhận resident_id của LLM (`routes.py:46`, `charging.py:44`). | SessionStorage có rủi ro XSS đã ghi trong ADR; test giả/mock không chứng minh chống XSS trên deploy. Chế độ playground dev có identity demo, bị cấm production trong config. Chưa audit đầy đủ websocket/browser. Bác bằng thử truy cập chéo cư dân qua token/session thật. |
| 017 | SUPPORTED: Guard vật lý chia sẻ, phân biệt trần thiết bị/budget, test emergency/failsafe đạt. | Body còn đường dẫn cũ và mô tả coordinator “chưa có”; không coi 0 vi phạm baseline là chứng minh toàn bộ sự cố. Bác bằng lô lệnh vượt hard cap vẫn được áp hoặc safety reduction bị HITL giữ. |
| 019 | VERIFIED về một kernel/policy source và standalone import qua test hiện tại; SUPPORTED về thiết kế tổng thể. | Chưa tự chạy lại AST manifest toàn lịch sử; không chứng nhận mọi hành vi giữ nguyên vì parity chỉ phủ mẫu. Ghi rõ trạng thái duyệt Phase 0–1 khác Phase 2+. Bác bằng import cycle, kernel thứ hai hoặc differential counterexample. |

018 (backend engine + policy) và 014 (trace/sandbox/lifecycle/quyền) cũng có phần C trong triage; chưa hoàn tất
review riêng hai ADR này. Không ghi “đã review toàn bộ nhóm C”. Nhóm A/B/D/E nhìn chung có lý, nhưng đây là đánh giá
SUPPORTED, chưa phải thẩm định toàn văn 19 quyết định. Các ghi chú từng được nhóm duyệt không tự chuyển thành Accepted,
cũng không được xoá lịch sử duyệt một phần. Không tìm được hội thoại gốc trong lượt này.

## Khuyến nghị để người giám sát quyết định

| Việc đề nghị | Vì sao / nếu bỏ qua | Phương án khác | Bằng chứng / khi không còn cần |
|---|---|---|---|
| Cho Implementation Agent sửa registry và sơ đồ sau review, giữ nguyên implementation | Tránh quản lý theo bằng chứng bỏ sót hoặc thứ tự an toàn sai; nếu bỏ qua dễ đánh giá nhầm phạm vi đã xong. | Đánh dấu tạm từng ô chưa đủ chứng cứ và chưa đóng Phase. | F4/F5, K2/K15; không còn cần khi đã đối chiếu yêu cầu tới assertion và sơ đồ tới call order. |
| Giữ baseline cũ làm regression, không dùng làm nghiệm thu sự cố/MT1; lập kế hoạch dataset nghiệm thu riêng | 40 sự cố bị bỏ qua, workload quá tải; không làm thì điểm đúng hạn và an toàn dễ được diễn giải sai. | Chỉ phân tích lại subset hybrid có nhãn và báo mẫu số; chưa sửa scenario/code trong Phase này. | F1/F2; thay đổi khi workload có chứng minh khả thi và mọi sự cố áp đúng. |
| Chưa đổi mặc định chỉ từ trung bình chi phí; so policy ở cùng mức phục vụ | Chi phí thấp có thể kèm phục vụ ít; bỏ qua có thể chọn trái mục tiêu cư dân. | Human chốt rõ ưu tiên tổng tiền, chấp nhận tỷ lệ trễ; hoặc giữ tạm mặc định có nhãn. | F3; không còn cần khi mục tiêu đã chốt và kết quả ghép cặp đủ điều kiện quyết. |
| Ghi riêng “CI code hiện tại CHƯA KIỂM CHỨNG”; không yêu cầu bật VM lúc này | Local test không thay CI, runner offline không chứng minh code lỗi. | Chờ thời điểm được phép xác nhận CI. | GitHub không có run unified-core; hết giới hạn khi CI cùng commit chạy xong. |
| Với offline demo, xem xét dev/test có nhãn trước khi nới production | FR33 cho demo không tự đòi nới chế độ production; nới sớm có thể làm người xem tưởng đang dùng LLM thật. | Demo dùng LLM thật, hoặc mock có nhãn ở môi trường riêng. | K13; chỉ cần đổi chính sách nếu Human thật sự yêu cầu offline tại production. |

## Tự phản biện và việc chưa xác minh

Phản biện mạnh nhất: Phase 1 chỉ lập bản đồ, đã chủ động ghi Tested ≠ Validated và I-1/I-2 để điều tra;
các thiếu sót không chứng minh thiết kế hoặc thuật toán hỏng. Tôi đồng ý: không đề nghị bỏ Unified Core, thay policy,
hay kết luận MT1 thất bại trên workload khả thi. Kết luận hẹp hơn là chưa thể đóng Phase với chất lượng truy vết hiện tại.

Không tự chạy benchmark mới, không có nghiệm tối ưu tham chiếu; số 30% được xác minh từ dữ liệu lịch sử chứ không tái lập
simulation. Chưa kiểm checksum provenance LF, toàn bộ nội dung 19 ADR, log job CI thất bại, mọi endpoint, giao diện thực,
LLM thật, PostgreSQL, bảo mật end-to-end hay deploy. Các giới hạn này phải được giữ khi chuyển giao.

**Bước tiếp theo:** Implementation Agent đọc kết quả này, đề xuất/sửa tài liệu trong phạm vi đã được Human cho phép;
Human xử lý các quyết định nghiệp vụ còn chờ. Không tự đánh dấu P1-13/P1-14 xong. Reviewer chỉ tạo file kết quả này.
