# Governance Phase 1 — Targeted Independent Re-review N2/N3/N4: kết quả hiện hành

Reviewer: Codex, độc lập với Implementation Agent. Ngày 2026-11-25, sau P1-12e; branch `feature/unified-core`, HEAD `ce23136`.

**Technical Acceptance: PASS (Governance Phase 1).**
**Formal Closure Readiness: NOT_READY — chờ Human quyết định hoặc ghi rõ việc hoãn các mục bắt buộc, rồi xác nhận đóng.**
**Trạng thái:** HANDOFF_READY khi đồng bộ checkpoint, nhả khóa Codex. Không tự CLOSED, không phê duyệt ADR.

## T0. Kết luận và phạm vi lượt này

N2/N3/N4 đều **RESOLVED** theo tiêu chí R6–R7 của lượt trước. F2/F5 được đóng trong phạm vi governance; F1/F3/F4 giữ RESOLVED, tái sử dụng bằng chứng độc lập trước còn hiệu lực. Tổng **5/5** phát hiện gốc đã xử lý về chất lượng governance. Không có phát hiện mới đủ mức chặn nghiệm thu trong phạm vi lượt này.

PASS xác nhận tài liệu cho phép truy vết yêu cầu, hiểu kiến trúc và thứ tự quan trọng, kiểm chứng evidence, phân biệt dữ kiện/suy luận, quản lý quyết định và chuyển giao. Không chứng nhận mọi feature đã xong, SLA 95%, an toàn ngoài mô phỏng, hiệu quả kinh tế tốt nhất, hoặc CI/deploy đạt.

Lượt này chỉ kiểm snapshot/phạm vi, registry MT1/MT2 và §6.1, ba luồng A/B/C, REMEDIATION §5.1/§8, các source reference được N3 dẫn, render đủ năm Mermaid và sổ quyết định để tổng hợp cho Human. Không lặp full audit, suite hoặc benchmark. Các phần R0–R9 bên dưới là **lịch sử lượt trước**, không phải verdict hiện hành.

## T1. Cổng tiếp nhận, snapshot và tái sử dụng evidence

Đọc lại AGENTS, CLAUDE các mục bắt buộc, HANDOFF §0/§1, REREVIEW R6–R7, REMEDIATION §5.1/§8. Git khớp checkpoint theo đường dẫn: sáu tracked tài liệu sửa; các file governance untracked và đầu ra eval/results có từ trước, không có đường dẫn lạ truy cập được. Cảnh báo quyền đọc cache/merged-sim vẫn có; không coi nội dung đó đã kiểm. Khóa tài liệu review đóng băng; quyền báo cáo/checkpoint chuyển Codex. Nhãn cũ trong §1.1/§1.6 được coi là lịch sử, đối chiếu bằng row P1-12e, snapshot và repository; không nâng thành blocker.

| File | SHA-256 hiện tại | So checkpoint P1-12e |
|---|---|---|
| docs/FEATURE_REGISTRY.md | `a4f57f5fb7eecc49d60e2a3f090fa8020ceb205da6890ab0efe0094f344c3bc4` | MATCH |
| docs/architecture_diagram.md | `2a88672d1cbe765b3945a45ed861e2c2e0d3884b3465cfd9ad33ef2f746639db` | MATCH |
| docs/adr/README.md | `585596a7d5d2657c4688a26db9ad69d144e10a6d8519a93ab0891ea27d390df4` | MATCH; không đổi so lượt review trước |
| docs/handoff/REMEDIATION_PHASE1.md | `9278931edd90c6e30222ddb33eb4fb30ca8da64ed37bcd3a6243e36055362f0b` | MATCH |

`git diff --name-only -- src tests frontend config migrations .github eval/evidence` rỗng; sáu source trọng điểm N3 được kiểm thêm `git diff --exit-code HEAD -- <file>` đều bằng HEAD. Remediation chỉ thay tài liệu, code vẫn ce23136. Vì registry/REMEDIATION là file chưa commit, Git không lưu diff giữa hai lượt; dùng hash đã ghi, bảng thay đổi §8 và đọc lại nội dung hiện hành, không giả định có lịch sử dòng đầy đủ.

F1/F3/F4: các ô sự cố/chi phí/truy vết tương ứng không đảo kết luận review trước; baseline tracked, source và tests không đổi. Đọc lại MT3/MT4, F10/F14, FR17/18/42–44 để xác nhận giới hạn vẫn được giữ. Tái sử dụng R2 và R8: 160/120/40, bảng policy lịch sử, 13 tên explicit có definition, ba targeted test đã đạt. **Không chạy lại** các phép tính/test đó. 814 passed/8 forecast skipped là evidence lịch sử; ba targeted tests đạt ở lượt trước cũng là lịch sử của lượt đó, không phải test mới hôm nay.

## T2. N2/N3/N4 — kiểm chứng theo tiêu chí R6–R7

### N2 — RESOLVED; F2 chuyển RESOLVED về governance

**Claim:** tài liệu không còn kết luận nguyên nhân chiếm ưu thế từ thời gian chờ censored hoặc cận năng lượng.

**Evidence:** registry MT2 (`FEATURE_REGISTRY.md:139`) đã bỏ “chủ yếu đo quá tải”; ghi rõ xe chưa cắm được tính tới deadline, không chỉ riêng xe đã phục vụ, đóng góp nguyên nhân UNVERIFIED. MT1 (`:138`) tách cận mọi kWh của hai workload ví dụ khỏi khả năng đạt 95% số xe. REMEDIATION §2 F2 (`:49–52`) tách VERIFIED/INFERRED/UNVERIFIED tương ứng. Đối chiếu source không đổi `simulation_service.compute_kpis:130–145` và `_is_feasible:162–164`, evidence cận năng lượng R2 trước giữ nguyên.

**Rationale:** diễn giải khớp điều thực sự đo được, không đổ lỗi optimizer/simulator hoặc quy toàn bộ tỷ lệ thấp cho quá tải. **Strongest Counterargument:** cận năng lượng vẫn rất bất lợi; đồng ý, được giữ như dữ kiện về khả năng giao mọi kWh, không thành phân rã nhân quả. **Falsification Condition:** xuất hiện lại kết luận nguyên nhân chính/tất cả mà không có đối chứng tương ứng. **Limitations:** không nghiên cứu nguyên nhân định lượng hay chạy simulation mới. **Verdict:** đáp ứng N2/R6; bài toán sản phẩm giữ ở R-2.

### N3 — RESOLVED; F5 và K15 chuyển ĐÚNG trong phạm vi sơ đồ được yêu cầu

**Claim:** các lỗi thứ tự được nêu ở R6 đã sửa, và cả năm sơ đồ hiển thị được.

| Mục | Nội dung tài liệu sau sửa | Đối chiếu source không đổi |
|---|---|---|
| Booking A | Loop tối đa BOOKING_COMMIT_ATTEMPTS; admission consent thật ngoài booking_lock; kiểm feasibility; lấy khóa, kiểm idempotency/booking/fingerprint; lệch rời khóa rồi thử lại; thành công lưu và upsert live; hết lượt báo hết hạn. | `charging_service.py:221–232,235–305`: quote assume_consent=True, book không tái dùng quote, continue rời context khóa trước vòng kế; chỉ publish sau commit. |
| Control B | Chỉ batch/outbox trong một on_event được gộp; phân biệt nguồn chính, event mới, on_minute riêng từng POWER_LIMIT_CHANGED rồi rest. Trật tự failsafe cũ→advance→đóng trace cũ→planning/consent→dispatcher→mở trace mới giữ đúng. | `control_loop.py:66–137,146–160`, `event_bus.py:34–42`; không có bảo đảm toàn cục một replan/timestamp. |
| Incident C | Đổi giới hạn/fault_port/restore_port dưới rt.lock trước khi trả event; nhả khóa rồi publish/on_event; nguồn giảm curtail sau advance theo code; fault không qua curtail; fail-safe tách tổng công suất với xe lỗi. | `simulation_service.py:375–390`, `hybrid_station.py:374–409`, `kernel.py:503–515`, `control_loop.py:78–97`; đúng mutation→event→reaction. |
| Rendering | Hai flowchart và ba sequenceDiagram trích nguyên văn từ snapshot, render PNG thành công, đã mở xem đủ5 ảnh. | Mermaid CLI12.2.0 / Mermaid12.3.0, Chrome headless cục bộ; T3. |

**Rationale:** loop/nhánh và prose đã sửa đúng các điểm từng dẫn đến FAIL. Chấp nhận sơ đồ nghiệp vụ lược chi tiết không ảnh hưởng các mốc an toàn, không coi là đặc tả mọi nhánh runtime. Nhãn “dừng” ở nhánh exception A và mô tả “rời khóa, thoát vòng” được đọc cùng prose/source, không diễn giải sẽ publish booking sau exception.

**Strongest Counterargument:** render thành công không chứng minh thứ tự đúng; đã đối chiếu riêng source ở bảng trên. C vẫn ghi nguy cơ vật lý tiến giữa nhả khóa/publish, nhưng có nhãn chưa test, không khẳng định runtime có bug hoặc đã an toàn tuyệt đối. **Falsification Condition:** source khác thứ tự trên hoặc một block cùng hash không render với môi trường đã ghi. **Limitations:** không chứng nhận mọi renderer/GitHub version, mọi alias động, hành vi race U1/U3 hoặc mọi nhánh implementation. **Verdict:** N3/F5 được đóng về governance; các điều chưa biết vẫn ở task sản phẩm, không che giấu bằng sơ đồ.

### N4 — RESOLVED

**Claim:** hồ sơ chuyển tiếp đáp ứng điều kiện owner hoặc chưa phân công, tiêu chí kiểm được, dependency rõ.

**Evidence:** REMEDIATION §5.1 ghi tất cả R-1…R-6 **CHƯA GIAO, chưa phân công**, có DoD/dependency/ngoài phạm vi từng task. R-1 yêu cầu fault AC/DC thực áp, strict incident và bảo toàn SHA baseline; R-2 định nghĩa workload/KPI/mẫu số và test mẫu rỗng; R-3 paired comparison/mức phục vụ/độ bất định, cung cấp evidence cho Q3 thay vì chờ Q3; R-4 test qua decide có/không consent và giới hạn năng lực, chờ D-6; R-5 actual/planned/ETA/UI assertion, thay API phải duyệt riêng; R-6 interleaving/restart và kết luận tái hiện hoặc không trong điều kiện nêu. Registry §6.1 dẫn đúng §5.1 và chuỗi phụ thuộc. Điều kiện chung giữ policy1/baseline, evidence mới có provenance và review.

**Rationale:** backlog đủ cụ thể để giao việc sau; ghi “chưa phân công” hợp lệ theo acceptance, không bắt triển khai ngay. **Strongest Counterargument:** các cận năng lượng chỉ là điều kiện cần của feasibility; đúng, DoD R-2 còn yêu cầu bằng chứng **cả workload theo seed**, không chỉ cận. Khi triển khai không được dùng cận cần thay cho witness đủ. R-1 cho phép loại incident có lý do nhưng vẫn buộc ít nhất fault AC/DC áp với xe đang cắm. **Falsification Condition:** không xác định được điều kiện hoàn tất/owner-status/dependency của một task, hoặc ngầm sửa policy1 để đạt số. **Limitations:** đây là kiểm hồ sơ task, không kiểm kết quả sản phẩm chưa làm. **Verdict:** đáp ứng N4/R7; không giao task hoặc duyệt thiết kế thay Human.

## T3. Evidence render cục bộ và lệnh thực chạy

Được phép tải CLI vào **cache tạm riêng** và chạy Chrome headless ngoài sandbox. Không thêm package vào frontend, không sửa package.json/lockfile hoặc cài global; không upload tài liệu lên dịch vụ render. CLI12.2.0, Mermaid12.3.0, Puppeteer25.18.1. Chrome dùng `C:\Program Files\Google\Chrome\Application\chrome.exe`.

Đầu vào tạm trích đúng năm code block ngôn ngữ Mermaid theo thứ tự từ `architecture_diagram.md` bằng regex với DOTALL, giữ nguyên nội dung giữa hai hàng rào ba dấu backtick, ghi UTF-8 không sửa nội dung. Gốc file tạm: `C:\Users\minhh\AppData\Local\Temp\p019-targeted-rereview-render\`. Mỗi block có `.mmd` và PNG. Đã mở xem bằng view_image đủ5; không có error image hoặc thiếu phần sơ đồ quan trọng, nhãn/loop/nhánh hiển thị được. Sơ đồ1 dài nên cần phóng to khi đọc; không phải lỗi render.

| # | Sơ đồ | SHA-256 đầu vào .mmd | PNG (px) | SHA-256 PNG |
|---|---|---|---|---|
|1|Bản đồ kiến trúc|`3cd65b19629ccb5869f1f74a4cca6f0e098ce986fc91f3ced4ea488f9d6302e1`|781×2199|`acd3d41ef6f341126b4ebd3b7628a467083d429a6a4a00f7ab114c908d02d77f`|
|2|Phụ thuộc import|`343286a2e223af499289d694e5d20bf98b95445740386268e57155ef5734d6bd`|2200×703|`b9661df7ad73d5518e04e509603b8b6263ac9bbc07147e3581afbc510f2c03b0`|
|3|Booking A|`b4ca0724e0f6c76c7dd4c807b0eb4ec517bd6f6519ae28548b5db4dd3dcf0544`|2200×1636|`76eea4236e4d6c4d403dd0ad28cf04d3636ed6649ca6752d7d2b893f5bfa8287`|
|4|Control B|`f0148365ea78590e38ebcfe83c9054aaf592ab7787df1635b1ec46c7ee241cc2`|2200×1015|`98aa0648b3b01ab9324d52c69a2451616befed20ae440a2dfb53a2aad5d0251a`|
|5|Incident C|`c21f7fbca88cce269bde88654ad4b8f8246bd8bea5abda91c2fc9387dabeec80`|2200×1479|`41fba4975629da21e47af0285f4018d99a568d08645abd6954a26411d465aec3`|

Các ảnh là artifact **tạm cục bộ**, không coi là baseline sản phẩm; hash đầu vào + snapshot + version/lệnh ở đây là evidence bền trong báo cáo. Nếu thư mục tạm bị dọn, có thể trích lại từ snapshot và chạy CLI đã ghi; PNG có thể khác hash nếu font/Chrome/metadata đổi, không tự suy nội dung sơ đồ đổi.

Lệnh Git/snapshot thực chạy: status --short, diff --stat, rev-parse --abbrev-ref HEAD, rev-parse --short HEAD; Get-FileHash bốn tài liệu; diff --name-only trên src/tests/frontend/config/migrations/.github/eval/evidence; diff --exit-code HEAD cho sáu source N3; diff --check. Tất cả phép so phiên bản/phạm vi trên khớp; diff --check không lỗi (có cảnh báo LF/CRLF). Kiểm29 link Markdown bốn tài liệu: không link thiếu. `scripts/check_docs.py`: **PASS, 50 md/131 link** (chỉ docs/guide, không thay kiểm targeted).

```powershell
$env:PUPPETEER_SKIP_DOWNLOAD='true'
npm exec --yes --cache "$env:TEMP\p019-rereview-mermaid-cache" --package '@mermaid-js/mermaid-cli' -- mmdc --version
# Kết quả 12.2.0; package chỉ nằm trong cache tạm.
$renderRoot = Join-Path $env:TEMP 'p019-targeted-rereview-render'
$mermaidCli = Join-Path $env:TEMP 'p019-rereview-mermaid-cache\_npx\668c188756b835f3\node_modules\@mermaid-js\mermaid-cli\src\cli.js'
1..5 | ForEach-Object {
  node $mermaidCli -i (Join-Path $renderRoot "diagram-$_.mmd") -o (Join-Path $renderRoot "diagram-$_.png") -p (Join-Path $renderRoot 'puppeteer.json') --size 2200 -b white
  if ($LASTEXITCODE -ne 0) { throw "Mermaid diagram $_ failed" }
}
# exit0 cả5; puppeteer.json: executablePath Chrome ở trên, headless=true, args=["--disable-gpu"].
```

Lỗi thao tác đã xử lý: CLI12 không còn `-w`, lần đầu báo unknown option; đọc --help rồi dùng --size. Sandbox chặn spawn Chrome EPERM; chạy lại ngoài sandbox với quyền được cấp thành công. Không coi hai lỗi công cụ/môi trường này là sơ đồ/source lỗi. Không chạy pytest/FE/full suite/benchmark/CI/VM/deploy trong lượt targeted.

## T4. Hai gate và các quyết định Human thực sự còn chờ

**Technical Acceptance = PASS.** Không còn blocker N2/N3/N4; không dùng PASS_WITH_CONDITIONS để bỏ qua lỗi. F1/F3/F4 tiếp tục hợp lệ với giới hạn cũ; F2/F5 nay đã sửa cách diễn giải/sơ đồ, không có nghĩa nguyên nhân kỹ thuật đã được giải quyết. K15 nay đúng cho phạm vi đã kiểm; những K khác giữ verdict/giới hạn R3, K10 CI vẫn chưa kiểm chứng.

**Formal Closure Readiness = NOT_READY.** Có đủ evidence kỹ thuật để Human xem xét; chưa có lệnh phê duyệt/đóng chính thức hoặc quyết định mới trong yêu cầu lượt này. Không bắt làm hết backlog sản phẩm để đóng governance. Human có thể quyết định hoặc ghi hoãn có điều kiện, chủ thể phụ trách và điều kiện mở lại cho các mục sản phẩm; không được diễn giải hoãn là Accepted.

Danh sách dưới đây gộp D-1=Q1, D-2=Q3 và các câu hỏi trùng để tránh xin cùng một quyết định hai lần. Đây là **đề xuất reviewer**, chưa phải quyết định đã duyệt:

| Quyết định còn chờ | Phương án đề xuất | Hệ quả / lựa chọn khác |
|---|---|---|
| Q1 — phạm vi AI-1/AI-4, ADR015 | Chốt lại mốc/phạm vi; ưu tiên AI-4 WHY trên trace có sẵn, hoãn AI-1 đầy đủ với task và mốc xét lại. | Có đường làm AI hữu ích nhỏ hơn; chưa có code AI-4 để gọi là hoàn thành. Giữ cả hai cần thêm nguồn lực hoặc dời mốc. Không mặc định lịch sprint cũ còn khả thi. |
| Q2 — mô hình bãi, ADR010 | Duyệt bãi hiện tại như giả định mô phỏng có nhãn, không như số đo VinFast/Vinhomes. | Giữ config/golden hiện tại, mở R-1/R-2 trên mô hình này; đổi topology cần cập nhật test/evidence mới. Không dùng100 run cũ thay bằng chứng đúng tất cả sự cố. |
| Q3 — mặc định policy, ADR018 | Giữ M3a **tạm thời có nhãn**, xét lại sau R-2/R-3. | Không đổi hành vi hiện tại; chưa tuyên bố M3a tốt nhất. Đổi ngay M3b đổi trade-off mà chưa có so sánh cùng mức phục vụ. |
| Q4 — nguyên tắc AI, ADR013/014 phần quyền/vòng đời | Duyệt nguyên tắc facts/trace, không tự apply sandbox, consent trước đổi cam kết, quyền phía server; chi tiết triển khai review riêng. | Tạo ranh giới cho AI chưa viết; chưa biến WHY/WHAT-IF/grounding thành tính năng đã đạt. Hoãn duyệt thì hoãn phần implementation phụ thuộc. |
| D-3 — offline demo | Demo offline có nhãn ở dev/test riêng, giữ cấm mock production; nếu Human yêu cầu offline ngay tại production phải duyệt thay đổi riêng. | Demo phục hồi được khi mất LLM, không bị hiểu nhầm là LLM thật; cần chuẩn bị môi trường riêng. Dùng LLM thật cho mọi demo thì chịu phụ thuộc key/mạng. |
| D-4 — workload/KPI nghiệm thu | Chốt định nghĩa khả thi cả workload và báo mẫu số; ưu tiên một ngữ nghĩa đúng hạn, hoặc hai tên khác nhau báo song song. | Mở R-2, tiếp đó R-3; số29–32% vẫn là lịch sử chưa đoMT1. Không yêu cầu phải đạt95% để xong task định nghĩa. |
| D-6 — vị trí Consent | Tạm giữ business rule backend với phạm vi và khác biệt standalone ghi rõ; giao R-4 test qua decide trước khi quyết đưa vào Planning Core. | Giữ hành vi/frozen policy1; không hứa backend=standalone tuyệt đối. Nếu chọn Planning Core, cần policy mới/thiết kế được duyệt, không sửa B0–M3b1. Đây là quyết định Human, reviewer không tự chốt. |
| Giao R-1…R-6 | Giao R-1/R-2 sau Q2/D-4, R-3 sau R-2; R-4 sau D-6; ưu tiên R-6 để kiểm U1/U3; R-5 theo nhu cầu hiển thị. Hoặc ghi chưa giao kèm mốc xét lại. | Biến rủi ro đã biết thành công việc đo được. Không giao vẫn được theo dõi, nhưng không dùng metric/claim tương ứng để nghiệm thu sản phẩm. |
| D-5 — đổi mã source; C-3 — nhãn forecast trong CLAUDE | Hoãn đổi mã source qua registry mapping; cho phép sửa nhãn tài liệu F12 (=F6 cũ) trong lượt tài liệu riêng. | Giữ ổn định tên code/test; còn cần cầu nối mã. Đây là quyết định vệ sinh tài liệu/phạm vi, không phải duyệt thuật toán; chưa sửa trong review này. |
| G-auto — tự động hóa | Giao kế hoạch riêng sau governance, giữ kiểm thủ công hiện tại cho tới lúc được phép đổi CI/repo config. | Giảm tái diễn drift khi có kiểm tự động; hiện còn phụ thuộc kỷ luật người/agent. Không bật VM hay sửa CI trong lượt này. |
| C-1 — commit; P1-14 — đóng chính thức | Human xác nhận cách xử lý các quyết định/hoãn trên, chấp nhận technical report, rồi cho phép commit và/hoặc xác nhận đóng bằng chỉ thị riêng. | Handoff không cần commit. Cho phép commit không đồng nghĩa cho phép push/merge/deploy; không được tự coi PASS là CLOSED. |

ADR nhóm B/D đã được checkpoint ủy quyền Tech Lead nhưng chưa xử lý; không phải các quyết định mới cần Human phê duyệt từng cái. Vẫn giữ Proposed và dấu vết duyệt một phần, không tự chuyển Accepted/Superseded trong lượt reviewer. Cũng không coi mọi Proposed của mục sản phẩm tương lai là blocker kỹ thuật governance.

## T5. Bàn giao và bước tiếp theo

Chỉ báo cáo này và các ô HANDOFF được cấp quyền thay đổi. Nhả khóa sau đồng bộ trạng thái; tài liệu review giữ nguyên và hash cuối lượt vẫn khớp T1. CI chưa kiểm chứng, runner tắt chủ ý, không là blocker governance. Không có implementation/ADR/policy mới được duyệt.

**Bước tiếp theo:** Human xem bảng T4 và xác nhận các lựa chọn hoặc việc hoãn, cùng ý định đóng Phase1; agent được giao sau đó ghi đúng quyết định đã nói. Không còn yêu cầu lượt sửa N2/N3/N4.

---

# Lịch sử: Independent Re-review sau P1-12b (kết luận FAIL ở thời điểm đó)

Reviewer: Codex, độc lập với Implementation Agent. Ngày 2026-11-25, tiếp tục sau P1-12b.
Code: `feature/unified-core` @ `ce23136`; tài liệu remediation chưa commit.
**Technical Acceptance: FAIL — chưa đủ điều kiện nghiệm thu governance trên bản tài liệu này.**
**Formal Closure: NOT_READY; Phase 1 không CLOSED.**
Trạng thái lượt này: **HANDOFF_READY** sau khi đồng bộ checkpoint; không giữ khóa chỉnh sửa.

## R0. Kết luận cho Human

3/5 phát hiện đã xử lý trong phạm vi governance: F1, F3, F4. F2 và F5 sửa được phần lớn nhưng còn kết luận nguyên nhân chưa đủ chứng cứ và sơ đồ chưa khớp thứ tự thực thi. Đây là lỗi tài liệu cần sửa trước nghiệm thu, không phải kết luận optimizer/simulator có lỗi. Không yêu cầu giải bài toán tối ưu hoặc đạt 95% trong Phase 1.

Cổng tiếp nhận cũ đã được khắc phục: checkpoint xác định được remediation, quyền sở hữu, báo cáo và bước tiếp theo. Báo cáo INSUFFICIENT_EVIDENCE của lượt trước được giữ ở cuối để bảo toàn lịch sử; **kết luận hiện hành là phần R0–R9 này**.

## R1. Checkpoint, phiên bản và phạm vi

Đã đọc lại AGENTS, CLAUDE, HANDOFF §0–§1, brief/review trước, REMEDIATION_PHASE1, registry, sơ đồ, ADR README, ADR-014/018; đối chiếu các phần PRD về FR/MT/AC, ARCHITECTURE và audit backend–simulator liên quan. Không audit lại toàn bộ sản phẩm hoặc toàn văn 19 ADR.

Git đầu lượt: sáu file tracked sửa là `ARCHITECTURE.md`, `CLAUDE.md`, `docs/PRD.md`, `docs/adr/README.md`, `docs/architecture_diagram.md`, `docs/handoff/HANDOFF.md`. Untracked gồm AGENTS, registry, communication/, REVIEW_PHASE1, REVIEW_PHASE1_RESULT, AUDIT_BACKEND_SIMULATOR_ALIGNMENT, REMEDIATION_PHASE1, REREVIEW_PHASE1_RESULT và ba file benchmark/manifest trong eval/results. Khớp §1.8 theo danh sách đường dẫn. Nhãn số lượng “kết quả review/audit (3)” trong HANDOFF thực tế liệt kê bốn file: MINOR, không cản đọc review. Cảnh báo quyền đọc cache/merged-sim vẫn có; không xem những thư mục đó là đã kiểm.

`git diff --name-only -- src tests frontend config migrations .github eval/evidence` không có đầu ra. HEAD không đổi từ review trước. Vì vậy tái sử dụng bằng chứng suite cũ @ce23136, chỉ chạy targeted tests cần cho F4. Không suy từ diff tracked rằng đã đọc mọi file untracked bị chặn quyền.

Phân loại theo checkpoint mới: tài liệu governance ban đầu có từ trước review; P1-12d sửa giao thức; P1-12b liệt kê rõ tài liệu remediation trong REMEDIATION §4. `eval/results/` là đầu ra ngoài Phase 1 có từ trước, giữ nguyên. Vì tài liệu đều chưa commit, không thể tái dựng chính xác từng dòng trước remediation từ Git; review này xác minh **nội dung hiện tại**, không coi bảng tự báo cáo thay cho bằng chứng.

Chỉ sửa báo cáo này và các ô checkpoint được cấp quyền trong HANDOFF. Không sửa source, test, policy, benchmark, baseline, ADR hoặc tài liệu đang review; không commit/push/merge/CI/deploy.

## R2. F1–F5: claim, evidence, rationale và verdict

| F | Trạng thái remediation | Bằng chứng và phạm vi |
|---|---|---|
| F1 | **RESOLVED** (governance) | Registry §2 F9, §3.1 MT4 và đoạn nguồn baseline ghi đúng 160 dự kiến/120 áp/40 bỏ, A05, legacy, chỉ regression. Tái tính JSON độc lập xác nhận; R-1 chưa giao. Không sửa nguyên nhân topology hoặc artifact lịch sử. |
| F2 | **PARTIALLY_RESOLVED** | MT1 đã phân biệt từng xe/workload, nguồn/cổng, admission và hai định nghĩa KPI, nhãn lịch sử, mẫu số rỗng = 100%. Nhưng MT2 kết luận chờ “chủ yếu đo quá tải” khi chưa phân rã nguyên nhân. N2 dưới đây. |
| F3 | **RESOLVED** (governance) | MT3, D-2, ADR README Q3 phân biệt tổng tiền và điện giao; không dùng chi phí thấp làm bằng chứng policy tốt nhất. M3a là mặc định implementation, Q3 chưa duyệt. Tái tính xác nhận bảng tiền/điện/đúng hạn và VND/kWh. |
| F4 | **RESOLVED** trong phạm vi phát hiện gốc | FR10–11 cũ và AC cũ đã ánh xạ; AC1–17, MT có bảng/nhãn thiếu. F10/F14 dẫn đúng assertion; F14 vẫn MỘT PHẦN, FR43/MT12 chưa xác minh. FR17/18 thu hẹp tới component/test cụ thể. 10 bảng khớp ORM; không dùng 30 FE test làm bằng chứng mọi màn. |
| F5 | **PARTIALLY_RESOLVED** | Booking có admission consent trước khóa; trace cũ đóng trước planning, trace mới mở sau dispatcher đã sửa. Phạm vi Guard backend/standalone đúng hơn. Còn đảo thứ tự fault/event ở C, thiếu vòng retry rõ ở A và lời gom một replan quá rộng ở B; render chưa kiểm. N3 dưới đây. |

### F1: giới hạn benchmark đã diễn giải đúng

**Claim:** tài liệu governance chính không còn lấy zero violation làm nghiệm thu toàn bộ sự cố.
**Evidence:** JSON baseline có 100 run, tổng incidents 160/120/40; 20 connector_failure đều bỏ A05 fault/restored. Ba tổng violations đều 0. Cả 20 run có KPI trùng peak_evening cùng policy/seed sau khi bỏ riêng latency. Header ba scenario legacy không cho dùng nghiệm thu/benchmark; registry đã ghi giới hạn. **Rationale:** mô tả giờ chỉ bao phủ tải/sự cố thực chạy. **Strongest Counterargument:** zero violation vẫn đúng về mặt số học; đồng ý và giữ nguyên số đó. **Falsification Condition:** phát hiện tuyên bố hiện hành dùng baseline này chứng nhận đầy đủ fault hoặc A05 thật sự được áp trong cùng artifact. **Limitations:** không chạy benchmark mới, không xác minh an toàn thực địa; brief Q2 nên dẫn hạn chế baseline thay vì dùng “100 run nhất quán” làm lý do duyệt mô hình bãi. **Verdict:** RESOLVED về diễn giải, nguyên nhân kỹ thuật chuyển R-1, chưa được sửa.

### F2: phần đúng và phần chưa đóng

**Claim:** kiểm từng xe không chứng minh workload khả thi; chưa có bằng chứng nguyên nhân chiếm ưu thế của thời gian chờ.
**Evidence:** `simulation_service.py:71–117` tạo CONFIRMED không admission; `:130–145` lấy outcomes.feasible làm mẫu số, rỗng trả 1.0 và lấy deadline thay plug-in cho xe chưa cắm; `:162–164` chỉ kiểm cap × giờ. `evaluation/extended.py:146,200–210` dùng completed_at ≤ departure và mọi session. Generator seed 1 hiện tại cho peak_evening: tổng pin 1378.6713, AC 1183.1725 kWh; hybrid_evening: tổng 813.3976, AC 676.1576 kWh. Cận lạc quan 2×11×24 = 528 kWh; nguồn legacy 35×24 = 840 kWh. Không dùng tổng giờ lưu trú làm cận bắt buộc.

**Rationale:** các cận chứng minh không phục vụ đủ năng lượng cho mọi yêu cầu của hai ví dụ, không chứng minh 95% số xe không thể đạt hoặc tất cả tỷ lệ thấp do quá tải. Thời gian chiếm cổng, hàng chờ, mục tiêu chi phí, DC taper còn cần tách riêng. **Strongest Counterargument:** nhu cầu AC vượt cận rất lớn nên quá tải có thể là nguyên nhân chính; đây là giả thuyết hợp lý, chưa phải kết quả phân rã định lượng. **Falsification Condition:** so sánh phản thực/đối chứng giữ cùng workload và thay từng giới hạn chứng minh đóng góp nguyên nhân. **Limitations:** không giải nghiệm tối ưu tham chiếu; không tái chạy simulation. **Verdict:** phần MT1 đúng; bỏ hoặc hạ nhãn suy luận “chủ yếu đo quá tải” ở MT2 để đóng F2.

### F3: tiền thấp không tự chứng minh policy tốt nhất

**Claim:** các con số lịch sử phù hợp và chưa đủ chọn policy.
**Evidence:** trung bình 25 run/policy, macro rate; reviewer tái tính:

| Policy | Đúng hạn % | Chờ phút | Tiền VND | Điện giao trước hạn kWh | Điện thiếu kWh | Service rate | Tiền/điện giao |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 30.2642 | 392.0084 | 722143.04 | 282.9004 | 681.22788 | .736 | 2552.6406 |
| M2b | 30.7023 | 392.5672 | 729863.44 | 286.46296 | 677.6652 | .728 | 2547.8458 |
| M3a | 29.1099 | 392.5672 | 685208.08 | 286.81776 | 677.31064 | .728 | 2389.0016 |
| M3b | 32.0880 | 392.7780 | 774704.96 | 332.77164 | 631.3566 | .728 | 2328.0378 |

**Rationale:** tỷ số tiền/điện trên là tổng tiền chia điện giao trước hạn (tương đương tỷ số hai trung bình vì cùng số run), không phải trung bình tỷ số từng run hoặc giá điện đầu vào thuần. Không xếp hạng hiệu quả kinh tế ở mức phục vụ tương đương từ bảng này. **Strongest Counterargument:** Human có thể ưu tiên tổng tiền và chấp nhận thiếu điện; đó là lựa chọn nghiệp vụ chưa được duyệt. **Falsification Condition:** evidence cùng mức phục vụ/paired scenario-seed và mục tiêu đã duyệt đủ để chọn. **Limitations:** chưa kiểm định ghép cặp/khoảng tin cậy; subset hybrid trong remediation chưa tái tính riêng trong lượt này. **Verdict:** RESOLVED về governance; giữ nguyên B0–M3b version 1 và mặc định implementation.

### F4: bằng chứng gốc đã được sửa, không nâng trạng thái sản phẩm

**Claim:** thiếu sót traceability được khắc phục đủ trong phạm vi review gốc.
**Evidence:** đọc assertion `test_profile_update_and_unknown_vehicle` cập nhật SOC/consent, đọc lại và từ chối vehicle lạ; `test_9ev_queue_occupancy_order_and_unplug` kiểm completed_at < departed_at và xe kế tiếp chờ; `test_dc_unplugs_after_delay_ac_holds_until_departure` kiểm DC rút trễ, AC finished vẫn giữ cổng rồi idle khi rời. Cả 3 chạy đạt lượt này. Đọc FE site-map (privacy, trạng thái, chọn cổng), simulation-policies (dropdown từ registry, gửi policy_id); không phải E2E màn cư dân. Đếm đúng 10 __tablename__. Kiểm AST 13 tên function test được dẫn rõ: đều có thật; 4 tên lịch sử bị loại đúng là không có. 29 link markdown ở bốn tài liệu remediation chính đều tồn tại.

**Rationale:** requirement→feature→code→assertion→evidence hiện đủ truy tới phần được kiểm; phần UI/metric chưa có được ghi đúng giới hạn. **Strongest Counterargument:** nhiều FR vẫn chỉ dẫn module/folder nên chưa chứng minh phủ từng điều khoản. Đồng ý; đây là Tested một phần, không Validated. **Falsification Condition:** một test dẫn mới không tồn tại hoặc trạng thái hoàn thành vượt assertion thực tế. **Limitations:** không audit hết assertion của mọi FR, API hoặc màn web; G1 không thay coverage. **Verdict:** RESOLVED cho các thiếu sót F4, không nghiệm thu toàn F10/F14 hay mọi AC.

### F5: thứ tự sự cố chưa đúng hoàn toàn

**Claim:** không thể chấp nhận cả ba sơ đồ như mô tả đúng call order hiện tại.
**Evidence:** `architecture_diagram.md:279` gửi event trước nhánh `fault_port` ở `:285`. Source `simulation_service.inject_incident:375–390` gọi trạm dưới khóa, thoát khóa rồi publish; `hybrid_station.py:390–400` gọi kernel.fault_port trước khi trả event; `kernel.py:503–515` bỏ cổng/đưa xe về đầu hàng và tăng state_version ngay. Tức thay đổi vật lý xảy ra trước consumer nhận sự kiện.

Luồng A `:215–220` biểu diễn retry như một nhánh sau bước “dưới khóa”, không vẽ vòng quay lại kiểm feasibility/fingerprint và commit sau retry thành công. Source `charging_service.py:266–305` continue thoát context khóa rồi admission lại ngoài khóa. Luồng B `:233–234` khẳng định mọi event cùng thời điểm một lần replan; `control_loop.on_minute:146–160` xử lý riêng từng POWER_LIMIT_CHANGED rồi thêm lần cho rest. Chỉ batch/outbox trong một on_event được gộp; không có bảo đảm một replan cho mọi event cùng timestamp.

**Rationale:** cần thấy rõ khi nào trạng thái cổng đã đổi, khi nào được tính lại và điều kiện nào bảo vệ commit. Đây chính là phạm vi F5/K15 còn mở; không chuyển sang task sản phẩm để đóng governance. **Strongest Counterargument:** sơ đồ nghiệp vụ được giản lược, B đã đúng các mốc trace/planning/dispatcher và prose A nói admission ngoài khóa. Đồng ý phần lớn đã sửa; nhưng C vẫn đảo mutation/event, còn tiêu đề B tuyên bố “theo đúng thứ tự” nên không thể coi là hoàn toàn chính xác. **Falsification Condition:** sơ đồ/prose diễn đạt fault→event→replan, vòng retry ngoài khóa và phạm vi gộp batch đúng source; renderer chạy được. **Limitations:** không kết luận có bypass Guard hay lỗi runtime. Không có mmdc/mermaid trong frontend hoặc npm cache CLI được kiểm, nên render **CHƯA KIỂM CHỨNG**; không tải thêm dependency, không dùng đọc cú pháp thay cho render. **Verdict:** PARTIALLY_RESOLVED.

## R3. K1–K15 cập nhật

“Tái sử dụng” dưới đây là evidence review độc lập 24/11 @ce23136, source/test không đổi; không phải chạy lại hôm nay.

| K | Verdict hiện hành | Bằng chứng/giới hạn |
|---|---|---|
| K1 | ĐÚNG — tái sử dụng | Mã cũ F6/7/8 được registry §1.1 ghi khác PRD; không đổi mã source. |
| K2 | ĐÚNG trong phạm vi sửa | Có FR10–11 cũ→FR8/12, AC cũ→mới, AC1–17 và MT; phần chưa có/chưa kiểm có nhãn. Không chứng nhận toàn bộ mọi plan cũ. |
| K3 | ĐÚNG — kiểm lại | 4 tên test lịch sử không có definition; được loại khỏi bằng chứng hiện hành. |
| K4 | ĐÚNG về evidence cũ | 604 backend+180 simulator+30 FE =814, forecast skip8; chạy mới chỉ 3 targeted đạt. |
| K5 | ĐÚNG trong phạm vi — tái sử dụng | AI-1/4 chưa implementation; trace/approvals không thay vòng đời proposal. ORM hiện 10 bảng. |
| K6 | ĐÚNG — tái sử dụng | Kiểm kWh/cổng không phải grounding từng claim; registry giữ MỘT PHẦN. |
| K7 | SUPPORTED — tái sử dụng | Chưa thấy FR4a; không tuyên bố tìm chuỗi chứng minh tuyệt đối. |
| K8 | ĐÃ LÀM RÕ — VERIFIED | Có giữ cổng sau đầy; 2 test mô phỏng chạy mới đạt. F14 UI/MT12 chưa kiểm. |
| K9 | ĐÚNG về số, giới hạn đã ghi | 100 run zero violation thực áp, macro29–32%; M3a thấp nhất tổng tiền, không tốt nhất kinh tế. |
| K10 | CHƯA KIỂM CHỨNG hiện tại | Không gh/CI mới; kết quả develop cũ là lịch sử. Runner chủ ý tắt không phải blocker. |
| K11 | SUPPORTED — tái sử dụng + đọc source | Một StationKernel, interface models/station_protocols; không phải hai optimizer. |
| K12 | ĐÚNG ở bảng chính — tái sử dụng | Source/test kiến trúc không đổi; AST không phải sandbox bảo mật tuyệt đối. |
| K13 | ĐÚNG với mock — tái sử dụng | Production từ chối mock; không suy mọi chế độ offline đều giống nhau. |
| K14 | ĐÚNG về triage/sổ duyệt; review bổ sung xong | 19 Proposed, lịch sử duyệt một phần còn; C đủ6 gồm014/018; xem R5. Không phê duyệt. |
| K15 | MỘT PHẦN | Các mốc B đã đúng, còn lỗi C và phạm vi batch/retry; F5. Render chưa xác nhận. |

## R4. Backend–Simulator và Consent

**Claim:** một nguồn optimizer/kernel dùng chung, không hai vòng quyết định cạnh tranh trên cùng live state; Consent là bước hậu xử lý backend thật, vị trí kiến trúc còn chờ quyết định.

**Evidence:** `runtime.build_sim_runtime:411–432` tạo station và scheduler mới mỗi run; `fork_runtime:435+` fork trạm/algorithms và store RAM. `SimulatorScheduler` giữ callable tới chính station của runtime; `decide:138–149` gọi kernel.propose, _start_minimums, _fit_with_minimums rồi approve. `HybridSimulator.step:139+` approve(proposal) trực tiếp rồi apply/advance. `test_differential._run:95–119` gọi station.kernel.propose/approve trực tiếp, không qua scheduler.decide. `control_loop.on_event` tuần tự dưới rt.lock; run_forever/on_minute đưa sự kiện tới cùng pipeline. Kernel sở hữu queue/adapter/setpoints/faults; DB lưu nghiệp vụ và phần phản chiếu.

**Rationale:** chia sẻ thuật toán không bảo đảm cùng kết quả khi input/thời gian/consent khác. `_start_minimums` dùng hạn tính từ thời điểm cắm, chỉ ép xe chưa nhận điện; `_fit_with_minimums` nâng mức ép rồi co xe khác, sau đó cả nhóm ép nếu cần để vừa tủ/vùng/lưới. Vì vậy có thể đổi phân bổ và điện giao; không chứng minh luôn đáp ứng consent khi năng lực không đủ. Guard vật lý approve lại; dispatcher còn 7 luật/HITL và kiểm batch lệnh tăng thực áp. Simulator standalone chỉ có Guard vật lý. Quote/admission chạy fork cùng runtime/control_loop/backend Guard, không thay trạng thái live; benchmark tạo instance độc lập.

**Strongest Counterargument:** đây là business rule chủ ý đã có trong ADR-018, không phải optimizer thứ hai. Đồng ý; sự tồn tại bước đó được xác nhận, tính đúng vị trí kiến trúc chưa được Human chốt. **Falsification Condition:** đường standalone tương ứng cũng áp consent, hoặc source scheduler không còn chỉnh setpoint; để chứng minh tác động định lượng cần ca đối chiếu qua decide với consent có hiệu lực. **Limitations:** chưa chạy counterexample Consent hoặc tái hiện U1/U3; không xác nhận rủi ro đồng thời là implementation bug. **Verdict:** B1/B4 được hỗ trợ trực tiếp từ source, D-6 còn chờ; B2 có heuristic riêng, B3 frontend và U1–U3 không được nâng lên lỗi xác nhận.

## R5. Review bổ sung ADR-014/018 và triage 19 ADR

| ADR | Kết luận kỹ thuật | Giới hạn, phản biện mạnh nhất, điều kiện bác bỏ |
|---|---|---|
| 014 | **PARTIALLY_IMPLEMENTED / SUPPORTED** cho nền trace/fork; không phải đã triển khai WHY/WHAT-IF/AI-1 đầy đủ. `decision_trace.open_trace:60+` mở facts/command correlation; close_open:177+ lấy kết quả vật lý; test_decision_trace kiểm closed trace, schema, replay Guard, tổng năng lượng. Fork isolation có test riêng. | Payload WHY/evidence_refs theo quyền, Patch whitelist, lifecycle TTL/idempotency/reverify, proposals/consents/vehicle_revisions, jobs ưu tiên và grounding nhân quả chưa có đầy đủ. Phản biện: ADR là mục tiêu tương lai, không bắt implementation đủ để nghiệm thu governance; đồng ý, registry đã ghi phần thiếu. Bác bằng endpoint/model/test/assertion thực sự đáp ứng từng điều khoản. Không xem admission fork là WHAT-IF người dùng đã xong; chưa chạy dịch vụ thật. |
| 018 | **SUPPORTED, sửa đổi bởi019**: engine backend dùng HybridStation/StationKernel, scheduler/policy dùng nguồn chung, thực thi qua dispatcher. Consent hậu planning đúng mô tả Hệ quả; không có bằng chứng hai optimizer độc lập. | Body lịch sử còn live dự phòng/A–D/POLICIES cũ; current README/019/registry ghi nguồn mới, LiveStation đã bỏ. Differential chỉ chứng minh core parity khi cùng state/config/setpoint, không qua consent. Phản biện: đây là thiết kế đã triển khai; triển khai không đồng nghĩa Human đã duyệt M3a/vị trí consent. Bác bằng runtime hiện hành có optimizer/kernel khác hoặc evidence parity qua decide. Không tái đo số RAM/latency/90 run lịch sử trong ADR. |

Đã kiểm header cả19: đều Proposed, không tự Accepted. Đối chiếu triage đủ19 duy nhất: A={010,013,014,015,018}, C={002,006,014,017,018,019}, B={001,003,004,005,007,008,009,012}, D={011,016}; A/C giao nhau theo phần, E là cờ phụ. Nhóm duyệt005–009, hướng018, chọn016 và019 Phase0–1 được giữ dấu vết theo file; chưa xác minh hội thoại gốc. Bốn ADR nhóm C đã review trước được tái sử dụng; bổ sung review014/018 ở đây, **không phê duyệt kiến trúc** hoặc tự sửa trạng thái README.

## R6. Phát hiện còn lại và gate nghiệm thu

| ID | Mức/loại | Claim và evidence | Cách đóng / owner |
|---|---|---|---|
| N1-cũ | Đã khôi phục | HANDOFF hiện có P1-12b/12c/12d, báo cáo remediation, khóa chuyển Codex, phân loại drift và completion checkpoint. | RESOLVED ở cổng tiếp nhận; vài nhãn lịch sử/I-2 cũ trong §1.6 là MINOR, không dừng review. |
| N2 | Trung bình, governance/F2 | Registry MT2 “chủ yếu đo quá tải” chưa được phép suy ra từ censoring/cận năng lượng; chính I-1 và remediation còn ghi các đóng góp UNVERIFIED. | Implementation Agent nếu được giao: sửa đúng mức chắc chắn, không bắt làm nghiên cứu định lượng trong Phase1. |
| N3 | Trung bình, governance/F5 | Sơ đồ C event→fault đảo source; A retry thiếu quay lại commit; B một replan/timestamp quá rộng. | Implementation Agent nếu được giao: sửa sơ đồ/prose theo F5, kiểm render; reviewer đọc lại đúng phạm vi. Không sửa source. |
| N4 | Trung bình, hồ sơ chuyển task | R-1…R-6 đã ghi “chưa giao” và vài phụ thuộc, nhưng chưa đủ rõ điều kiện hoàn tất, nhất là R-5 ETA/cổng dự kiến, R-6 test tái hiện hoặc kết quả không tái hiện được. | Trước nghiệm thu, ghi tiêu chí kiểm được và dependency cho từng task, có thể tiếp tục để “chưa phân công”; không bắt giao/triển khai sản phẩm ngay. Tiêu chí đề xuất ở R7. |

**Acceptance A = FAIL** vì N2/N3/N4 còn trong phạm vi chất lượng diễn giải, hiểu thứ tự an toàn và quản lý việc hoãn; không dùng PASS_WITH_CONDITIONS để bỏ qua. Không phải do tỷ lệ đúng hạn thấp, AI-1/4 chưa có, Consent chưa đổi hoặc runner tắt. Sai lệch runtime chưa được chứng minh không là lý do FAIL.

**Acceptance B = NOT_READY**: còn lỗi tài liệu và quyết định Human chưa duyệt. Không gộp hai gate và không tự CLOSED. Lần review tiếp theo chỉ cần kiểm các điểm mở, không lặp toàn audit/suite.

## R7. Task sản phẩm và quyết định Human

R-1…R-6 hiện **chưa giao**, ngoài phạm vi Re-review. Những tiêu chí dưới đây là đề xuất reviewer để hoàn chỉnh hồ sơ, **không phải giao việc hay phê duyệt**:

| Task | Điều kiện hoàn tất đề xuất | Phụ thuộc |
|---|---|---|
| R-1 dataset sự cố | Cổng tồn tại, mọi incident dự kiến áp hoặc có lý do loại rõ; strict check và evidence mới có provenance; baseline cũ giữ nguyên. | Mô hình bãi Q2; phạm vi sự cố được chốt. |
| R-2 khả thi/KPI | Định nghĩa từng xe và cả workload, nguồn/cổng/occupancy/vật lý, một ngữ nghĩa đúng hạn và denominator/zero-sample; evidence workload nghiệm thu. | D-4, Q2. |
| R-3 so policy | Cùng workload/seed, paired results, mức phục vụ, chờ/điện thiếu/tiền và độ bất định; không đổi policy1. | R-2, tiêu chí lựa chọn Human; cung cấp bằng chứng cho Q3, tránh vòng phụ thuộc phải Q3 trước mới đo. |
| R-4 Consent | Ghi quyết định vị trí, phạm vi backend/standalone, ca test qua scheduler.decide có/không consent và giới hạn năng lực. | D-6; nếu đụng frozen policy phải thiết kế policy mới được duyệt. |
| R-5 ETA/cổng | Tách actual/planned và giả định ETA; xác định API/UI dùng gì, assertion minh chứng hành vi đã chọn. | Quyết định nghiệp vụ/contract riêng nếu cần đổi API; chưa quyết ưu tiên. |
| R-6 U1/U3 | Test có lịch xen kẽ/restart rõ, báo tái hiện hoặc chưa tái hiện trong điều kiện nêu; không tự xác nhận bug hay đổi hành vi. | Kịch bản được duyệt và môi trường một worker hiện hành. |

Human còn phải quyết theo danh sách hiện hành: Q1 phạm vi; Q2 mô hình bãi; Q3 policy mặc định (chưa đủ evidence chọn lại); Q4 nguyên tắc/vòng đời/quyền AI; D-3 offline demo, D-4 định nghĩa khả thi/KPI, D-5 đổi mã, D-6 vị trí Consent; tự động hóa G-auto, C-1 commit và P1-14 đóng chính thức khi đủ điều kiện. C-3 là chỉnh nhãn tài liệu đang được checkpoint để chờ, không phải quyết định kiến trúc lớn. Không cần Human trả lời tất cả các mục này để sửa N2/N3/N4 bằng một lượt remediation tài liệu được giao.

## R8. Lệnh và bằng chứng thực chạy

```text
Set-Location -LiteralPath 'D:\VIN\P-019'
git status --short
git diff --stat
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git diff --name-only -- src tests frontend config migrations .github eval/evidence
git diff --check
.venv/Scripts/python.exe scripts/check_docs.py
  Checked 50 md files, 131 internal links; PASS (chỉ docs/guide, không thay kiểm registry)
.venv/Scripts/python.exe -m pytest tests/test_services/test_service_contracts.py::test_profile_update_and_unknown_vehicle tests/test_simulator/test_hybrid_station.py::test_dc_unplugs_after_delay_ac_holds_until_departure src/simulator/tests/test_hybrid.py::test_9ev_queue_occupancy_order_and_unplug -q -p no:cacheprovider
  3 passed in 0.92s (ngoài sandbox, đã được cho phép)
```

Test lần đầu sandbox: 1 passed/2 setup errors do SQLite tạm “unable to open database file”, không phải logic fail. Chạy lại ngoài sandbox đạt. Có cảnh báo pytest asyncio fixture scope, không sửa cấu hình trong review. Không chạy toàn suite/FE/build/benchmark/CI/VM/LLM/Postgres/deploy. 814/8 vẫn là evidence lịch sử review trước @ce23136, không cộng 3 targeted thành tổng mới.

Python stdin scripts thực chạy, không lưu script mới: đọc JSON baseline bằng stdlib, group policy và cộng incidents/violations; ghép connector_failure/peak_evening theo policy và seed trong notes, so kpis trừ replan_p95_seconds; gọi generator hiện tại với seed1 và SIM_DATE/zoneinfo từ config; AST tìm definition các tên `::test_`/tên đơn trong registry, tách bốn tên lịch sử cố ý vắng; kiểm link tương đối bốn file và đếm/header ADR. Không phải chạy benchmark mới. Kiểm G1 chỉ tên explicit, không giả vờ folder coverage đã đầy đủ.

Snapshot SHA-256 tài liệu đã đọc, để nhận diện bản chưa commit:

```text
docs/FEATURE_REGISTRY.md c55796598dec877bafda4c077f4e61a21d576e7fef9542c00cde85ed41232049
docs/architecture_diagram.md 0a0ff74280f7ab86d3b9604da21a9d4ce8f1403f084ab930c08298aef666f6b9
docs/adr/README.md 585596a7d5d2657c4688a26db9ad69d144e10a6d8519a93ab0891ea27d390df4
docs/handoff/REMEDIATION_PHASE1.md db5000d74317fd074837e0a475d1b6f88b031152e860dbda45b2241edc373c19
```

## R9. Bàn giao

Re-review nội dung đã hoàn tất và checkpoint được cập nhật; nhả khóa Codex. Tài liệu review giữ nguyên. **Bước tiếp theo duy nhất:** Human giao lượt remediation tài liệu giới hạn N2/N3/N4, sau đó reviewer kiểm lại đúng các điểm đó. Nếu không giao, giữ kết luận FAIL/Phase1 chưa đóng; không tự sửa hay triển khai R-1…R-6.

---

# Lịch sử: lượt tiếp nhận trước remediation (đã được thay bằng kết quả R0–R9)

Reviewer: Codex. Ngày tiếp nhận: 2026-11-25 (Asia/Bangkok).
Trạng thái: **DỪNG Ở CỔNG TIẾP NHẬN — chưa thực hiện kiểm chứng remediation**.
Technical Acceptance Verdict: **INSUFFICIENT_EVIDENCE**.
Formal Closure Readiness: **CHƯA SẴN SÀNG XÁC NHẬN**; không đánh dấu Phase 1 CLOSED.

## 1. Kết luận và điều kiện tiếp nhận

Yêu cầu của Human cho biết remediation đã hoàn thành. Tuy nhiên checkpoint trong workspace chưa ghi nhận giai đoạn này hoặc báo cáo remediation. Đây là mâu thuẫn về trạng thái bàn giao, chưa phải bằng chứng remediation không được thực hiện.

Theo `AGENTS.md` mục Bắt buộc bước 3, `CLAUDE.md` mục Tiếp nhận công việc và `HANDOFF.md` §0, phải dừng và báo khi trạng thái Git lệch checkpoint. Reviewer chỉ tạo file này theo quyền được Human cấp trong yêu cầu Re-review; không sửa HANDOFF, báo cáo review trước hoặc tài liệu đang được review. Không lấy khóa sửa tài liệu Phase 1 của Agent khác.

**Claim:** chưa thể bắt đầu Re-review từ một checkpoint remediation xác định được.

**Evidence:**

- `HANDOFF.md:49–55`: tiến độ vẫn là 11/14, chưa review độc lập, chờ Codex làm P1-12.
- `HANDOFF.md:168–179`: danh sách Git dự kiến không có `docs/handoff/REVIEW_PHASE1_RESULT.md` và `docs/handoff/AUDIT_BACKEND_SIMULATOR_ALIGNMENT.md`, trong khi hai file đang hiện diện và untracked.
- `HANDOFF.md:181–199`: khóa và hành động tiếp theo vẫn dành cho review lần đầu, đầu ra là `REVIEW_PHASE1_RESULT.md`.
- `HANDOFF.md:201–209`: nhật ký dừng ở lần bàn giao review đầu ngày 24/11.
- Đọc HANDOFF và liệt kê file trực tiếp trong `docs/handoff/`: có HANDOFF, REVIEW_PHASE1, REVIEW_PHASE1_RESULT, AUDIT_BACKEND_SIMULATOR_ALIGNMENT; không có báo cáo remediation được HANDOFF tham chiếu. Không suy ra báo cáo không tồn tại ở nơi khác.
- Báo cáo review trước ghi ngày 24/11, code `ce23136`, branch `feature/unified-core`, và chưa đủ điều kiện đóng Phase 1.

**Rationale:** cùng HEAD không phân biệt được các phiên bản tài liệu chưa commit. Cần xác định tập thay đổi remediation và trạng thái quyền sở hữu trước khi xác nhận đã kiểm một bản sửa cụ thể.

**Strongest Counterargument:** Human đã trực tiếp giao Re-review và cho biết implementation hoàn thành; HANDOFF có thể chỉ chưa được cập nhật. Quyền tạo báo cáo Re-review đã rõ. Tuy nhiên thông tin này chưa chỉ ra artifact remediation, tập thay đổi và checkpoint hiện tại; quy tắc dừng khi lệch vẫn áp dụng.

**Falsification Condition:** cung cấp checkpoint remediation nhất quán hoặc Human xác nhận rõ tiếp tục trên workspace hiện tại dù checkpoint cũ, kèm vị trí báo cáo remediation (hoặc xác nhận không có báo cáo riêng) và tình trạng Agent đang chỉnh sửa.

**Limitations:** chưa đọc toàn bộ tập tài liệu theo Context Recovery, chưa đối chiếu source/assertion hoặc đánh giá nội dung remediation. Không kết luận các tài liệu hiện tại chưa được sửa.

**Verdict:** thiếu bằng chứng để xác nhận remediation và nghiệm thu kỹ thuật tại cổng tiếp nhận; không phải FAIL về source hoặc sản phẩm.

## 2. Git và phạm vi thay đổi

Lệnh đã thực chạy tại repo sau khi đặt thư mục rõ ràng:

```powershell
Set-Location -LiteralPath 'D:\VIN\P-019'
Get-Location
Get-Content -Encoding UTF8 AGENTS.md
Get-Content -Encoding UTF8 CLAUDE.md
Get-Content -Encoding UTF8 docs/handoff/HANDOFF.md
git status --short
git diff --stat
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
rg -n '^##|^###|remedi|Remedi|sửa|Re-review|REREVIEW|F1|F5|1.8|1.9' docs/handoff/HANDOFF.md
Get-Content -Encoding UTF8 docs/handoff/REVIEW_PHASE1_RESULT.md -TotalCount 85
Get-ChildItem docs/handoff -File
```

Branch `feature/unified-core`, HEAD `ce23136`: khớp review trước. Trước khi tạo báo cáo này:

```text
 M ARCHITECTURE.md
 M CLAUDE.md
 M docs/PRD.md
 M docs/adr/README.md
 M docs/architecture_diagram.md
 M docs/handoff/HANDOFF.md
?? AGENTS.md
?? docs/FEATURE_REGISTRY.md
?? docs/communication/
?? docs/handoff/AUDIT_BACKEND_SIMULATOR_ALIGNMENT.md
?? docs/handoff/REVIEW_PHASE1.md
?? docs/handoff/REVIEW_PHASE1_RESULT.md
?? eval/results/benchmark.json
?? eval/results/benchmark.md
?? eval/results/manifest.json
```

Diff tracked: 6 file, 602 insertions, 556 deletions. Không có source/test/config/migration/frontend/CI được báo thay đổi trong phần Git truy cập được. Git cảnh báo không đọc được `.pytest_cache/` và một số thư mục `eval/results/merged-sim/`; không coi nội dung đó đã kiểm.

Phân loại: sáu file tracked sửa và các tài liệu governance đã được checkpoint ghi là công việc Phase 1; `eval/results/` được ghi là đầu ra có từ trước, ngoài Phase 1, giữ nguyên. Hai file review/audit bổ sung không có trong danh sách checkpoint. **Chưa phân tách được thay đổi remediation với nội dung Phase 1 ban đầu**, vì không có snapshot tài liệu sau review đầu hoặc báo cáo remediation được tham chiếu. File này là đầu ra mới duy nhất của lượt tiếp nhận.

Lệnh đọc đầu tiên chạy nhầm ở `D:\` do shell không giữ cwd, báo không tìm được file; đã đặt `Set-Location` và đọc lại thành công. Không dùng lỗi đó làm phát hiện về repo.

## 3. Trạng thái F1–F5

| Phát hiện | Trạng thái sau remediation | Bằng chứng / giới hạn |
|---|---|---|
| F1 — Incident benchmark integrity | UNVERIFIED | Review trước nêu 160/120/40 và A05; chưa xác minh tài liệu remediation hoặc artifact ở lượt này. |
| F2 — Feasibility/deadline KPI | UNVERIFIED | Chưa đối chiếu cách diễn giải workload, mẫu số KPI hoặc hai định nghĩa đúng hạn sau sửa. |
| F3 — Policy/economic claims | UNVERIFIED | Chưa kiểm cách diễn giải B0/M2b/M3a/M3b và trạng thái Human duyệt policy sau sửa. |
| F4 — Registry/traceability | UNVERIFIED | Chưa xác minh mapping, assertion, số bảng và trạng thái bằng chứng sau sửa. |
| F5 — Architecture/Guard | UNVERIFIED | Chưa đối chiếu ba sơ đồ với call order sau sửa; chưa render Mermaid. |

0/5 được **xác nhận** xử lý trong lượt này; không đồng nghĩa 5/5 chưa được sửa. Không đổi trạng thái phát hiện trước thành RESOLVED hoặc DEFERRED_WITH_JUSTIFICATION khi chưa kiểm bằng chứng.

## 4. Đối chiếu K1–K15

Các kết luận cũ dưới đây chỉ được đọc từ bảng review trước, không được nâng thành kết quả xác minh hiện tại.

| Mã | Kết luận review trước (rút gọn) | Trạng thái Re-review |
|---|---|---|
| K1 | Đúng: mã cũ khác nghĩa mới | UNVERIFIED sau remediation |
| K2 | Một phần: thiếu FR10–11/AC/MT | UNVERIFIED sau remediation |
| K3 | Đúng trong cây cũ: test dẫn không tồn tại | UNVERIFIED sau remediation |
| K4 | Đúng: 814 đạt, 8 skip | Chỉ ghi nhận evidence lịch sử; không chạy lại |
| K5 | Đúng trong phạm vi: AI-1/bảng chưa có | UNVERIFIED hiện tại |
| K6 | Kiểm lời giải thích chưa đối chiếu từng facts | UNVERIFIED hiện tại |
| K7 | Chưa thấy chuyển mục đích thành ràng buộc | UNVERIFIED hiện tại |
| K8 | Có mô phỏng giữ cổng; UI/MT12 chưa đủ | UNVERIFIED sau remediation |
| K9 | Số lịch sử đúng, sức chứng minh có giới hạn | UNVERIFIED sau remediation |
| K10 | Nhánh chưa có CI run được xác nhận | CI validation: CHƯA KIỂM CHỨNG |
| K11 | Một kernel/đường dùng chung được hỗ trợ | UNVERIFIED sau remediation |
| K12 | Bảng ranh giới chính phù hợp | UNVERIFIED sau remediation |
| K13 | Production từ chối mock | UNVERIFIED hiện tại |
| K14 | Thiếu phần C của ADR-014/018 | UNVERIFIED sau remediation |
| K15 | Ba sơ đồ giản lược sai thứ tự quan trọng | UNVERIFIED sau remediation |

## 5. Kiến trúc, Consent và ADR bổ sung

Chưa kiểm source `hybrid_planner.py`, ownership trạng thái vật lý, kernel fork, vòng quyết định hoặc parity backend/benchmark trong lượt này. Nhận định Backend điều chỉnh theo Consent sau planning còn là **claim cần kiểm chứng**, không phải lỗi implementation được reviewer xác nhận. Không mặc định có hai optimizer hay hai vòng điều khiển cạnh tranh. Không triển khai Consent.

Chưa hoàn thành review bổ sung ADR-014/018 hoặc triage lại 19 ADR. Không tự đổi Proposed thành Accepted, không xóa dấu vết phê duyệt một phần và không phê duyệt kiến trúc. Danh sách quyết định trong HANDOFF là checkpoint cũ, chưa xác minh còn đầy đủ hoặc còn chờ tại thời điểm này.

## 6. Test evidence, giới hạn và phát hiện mới

Review trước ghi: 604 backend + 180 simulator + 30 frontend = 814 passed, 8 forecast skipped ở `ce23136`. Đây là **kết quả lịch sử**, không phải test chạy lại trong lượt này. Chưa thực hiện test, build, benchmark mới, check_docs hoặc kiểm renderer. Không chạy lại suite chỉ để bù cho thiếu artifact bàn giao.

**N1 — Sai lệch checkpoint bàn giao (VERIFIED):** HANDOFF chưa phản ánh review đầu đã có kết quả, chưa xác định remediation, và chưa đưa hai artifact review/audit vào snapshot Git. Ảnh hưởng trực tiếp khả năng Agent mới khôi phục đúng Phase, tách việc xong/chưa xong và kiểm soát quyền sở hữu. Đây là blocker tiếp nhận governance; không phải bằng chứng source có lỗi.

Chưa xác minh có hai Agent cùng sửa task hay không; không suy từ checkpoint cũ rằng Agent khác đã nhả khóa remediation. Không sửa HANDOFF khi chưa rõ quyền. Không bật VM, CI, merge hoặc deploy. Runner tắt theo chủ ý Human không phải blocker source/governance; giữ CI validation chưa kiểm chứng.

## 7. Việc còn lại và quyết định Human

| Loại | Việc | Owner / trạng thái | Tiêu chí hoàn thành và phụ thuộc |
|---|---|---|---|
| Governance blocker tiếp nhận | Xác định checkpoint và artifact remediation | Implementation Agent / chưa xác nhận nhận việc | HANDOFF phản ánh review đầu, phạm vi sửa F1–F5, báo cáo remediation, Git và khóa hiện tại; hoặc Human cho phép rõ tiếp tục với checkpoint cũ. |
| Governance review | Tiếp tục F1–F5, K1–K15, kiến trúc/Consent, ADR-014/018, sơ đồ/assertion | Codex / chưa thực hiện | Phụ thuộc cổng tiếp nhận được giải quyết; kết luận có evidence cụ thể. |
| Phát triển sản phẩm | Benchmark topology/incident, KPI/feasibility, policy, Consent nếu còn tồn tại | Chưa xác minh task/owner remediation | Chưa đủ bằng chứng để xác nhận chuyển task hợp lệ; cần kiểm owner hoặc nhãn chưa phân công, tiêu chí hoàn thành và phụ thuộc trong Re-review tiếp theo. |
| Formal closure | Human xử lý quyết định bắt buộc còn chờ | Human / chưa thẩm định danh sách mới nhất | Chỉ sau Technical Acceptance và xác định các quyết định thực sự chưa được duyệt; không tự đóng Phase. |

**Hành động tiếp theo:** yêu cầu Implementation Agent bàn giao checkpoint remediation nhất quán và đường dẫn báo cáo đã lưu. Không yêu cầu commit. Reviewer tiếp tục trên cùng workspace sau khi điều kiện tiếp nhận được giải quyết.
