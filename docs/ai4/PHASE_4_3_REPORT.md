# AI-4.3 — HOW-TO Engine · Gate 5

Tech Lead quyết định **G5 APPROVED** tại mirror `42438430ee49f404e90080c49a76e4c6446530da`. Candidate SHA-256 `7dd32a1903aa67b9548ad30da21739a6b9a9b220d3ca681853d267027b4fc534`, bundle SHA-256 `ea90e5ca90452ac105683b6630de6f579bfddb33f8ec4f4a10839f55db1f1dc9`. Tech Lead xác nhận 6/6 blob, 6/6 source hash, 26/26 checksum nội dung, oracle M3a/M3b, hai trường hợp có cải thiện và không cải thiện, G5-F01–F04 đã xử lý, 30 G5, 137 hồi quy G2/G3/G4/G6A, 43 architecture, 838 backend + 8 forecast skips, 180 standalone và 10/10 cổng exit 0. G5 đóng, chỉ xử lý blocker tích hợp đã xác nhận nếu có.

## Targeted remediation · G5-F01–F04

Tech Lead ghi **CONDITIONAL PASS — TARGETED REMEDIATION REQUIRED** cho mirror
`9ecb1af2fad75ab9a5a92abee7d9de5246664abe`, với patch SHA-256
`f6ae745b88dd61bbcd19312b96fa09d608a7de3350b56d41c703387d3fd9153e`.
Lượt này dùng local `0f877f1` tương ứng merged baseline mirror `20bb246`. Năm file đã review khớp checksum trước khi sửa.

| Finding | Xử lý và evidence |
|---|---|
| G5-F01 | Thêm oracle mô phỏng trên M3a và M3b version 1, topology 2 AC + 2 DC. Dùng default `synthetic_taper_v1` đã resolve bởi runtime. Test xác minh provenance trong snapshot và trace từng fork. Dữ liệu xe dùng dung lượng fixture 60,13 kWh. Đường sạc DC là mô hình synthetic. |
| G5-F02 | Bổ sung `subject_goal_target` cho earliest completion, đo cùng target trên baseline và candidate, kể cả khi goal target khác cam kết gốc. `subject_soc_observed_at` ghi phút quan sát SOC của mục tiêu deadline. Kết quả giữ target, deadline, attainment, release, original/revised SLA và các cờ cho phép đánh đổi. |
| G5-F03 | Giữ `input_sha256` làm provenance của branch. `ref` định danh projection với version, hash đầu vào và trạng thái cuối, cutoff, goal và ngữ cảnh quan sát được phép. Probe trên bản đã review thấy 1 ref cho 4 projection. Bản sửa tạo 4 ref và giữ ref ổn định khi chạy lại cùng projection. |
| G5-F04 | `git check-ignore -v` xác nhận rule cho `raw/`, `*.patch` và `*.log`. Gói ZIP có checksum chứa bộ bằng chứng cuối và có thể chuyển độc lập. Artifact lịch sử vẫn lưu ở đường dẫn cũ. |

### Oracle định lượng

Các oracle tích phân delta công tơ từng phút trên các fork. Đối chiếu nguồn chung, trần vùng 22/120 kW đầu ra, trần cổng
11/60 kW, taper trên 60% SOC và chuyển đổi 95% lưới → cổng, 98% cổng → pin. Mốc đạt target kiểm bằng năng lượng thực vào pin.
Nhánh được chọn phải hoàn thành và qua kiểm safety, Guard và pending approval. `T` là phút capture.

| Ca thử | Candidates + baseline | Quan sát độc lập |
|---|---:|---|
| M3a max SOC trước T+18 | 6 + 1 | Chọn 70%. Trần taper độc lập là 84,820754%. Ứng viên 75% đo 74,999930% tại deadline và hụt target. Cam kết gốc 83% đạt T+29 ở baseline. Ứng viên 70% đạt revised SLA và mất original SLA theo cờ cho phép. |
| M3a deadline trong tải cạnh tranh | 8 + 1 | Cùng target 59%, deadline T+31 cho attainment T+31, sớm hơn 6 phút so với T+37 của baseline. Baseline nhả cổng T+42. Hai ứng viên khả thi khác vẫn đạt T+37. |
| M3a baseline đã đáp ứng | 5 + 1 | Cả năm ứng viên khả thi có attainment T+29 và release T+34 giống baseline. Tie-break xếp deadline gốc T+38 đầu tiên. |
| M3b mixed site limit | 8 + 1 | 22 kW đo peak 22,000 kW và cả hai vùng cùng sạc. Nguồn chỉ có thể nạp 9,2169 kWh trước deadline cuối, so với 24,6533 kWh cam kết. Tại 82 kW đạt 3/4, trong đó booking AC `ac-a` từ đúng hạn sang trễ nên bị loại dù đáp ứng ngưỡng 75%. 94 kW là mức thấp nhất đã xác minh đạt 4/4, cuối cùng trả partial vì bốn mức thấp có lệnh bị chặn. |
| M3a đối chiếu cùng target | 1 + 1 | Goal 75% đo trên baseline tại T+18, khác mốc đạt cam kết gốc 83% tại T+29. Cả hai mốc có trường riêng. |

Feasibility được quyết định theo goal và constraints. Để kết luận có lợi ích, so với baseline tại cùng target hoặc
cùng phút quan sát. Tách lợi ích về attainment khỏi thay đổi deadline hoặc release. Kết quả unknown cần được diễn giải
cùng trạng thái nhánh và cutoff. Bảng trên đo fixture, không dùng để cam kết latency triển khai.

### Handoff cho G6B

- Với mỗi claim, ghép `RecommendationEvidence.ref`, `#` và JSON Pointer chính xác tới trường đã qua projection.
  Ví dụ `#/subject_goal_target/target_reached_at` và `#/subject_release_at` cho hai mốc khác nhau. Giữ subject,
  stage, unit và thời điểm phù hợp khi G6B xác minh claim.
- `ref` là định danh bằng chứng được chiếu theo quyền, còn `input_sha256` chứng minh input của branch. Hai projection
  khác nhau có thể cùng branch input và physics. Validate quyền trước khi resolve pointer.
- Luồng F8 advisory giữ bounded search, original/revised SLA và `applied=false`. G6B có thể đọc chứng cứ để diễn giải
  lợi ích theo baseline. Round này dừng ở service contract và tests. Tech Lead tiếp nhận review cuối.

### Xác minh và bàn giao candidate

Patch cuối trên `0f877f1` có SHA-256
`7dd32a1903aa67b9548ad30da21739a6b9a9b220d3ca681853d267027b4fc534`.
So byte 380 đường dẫn giữa candidate đã review và candidate cuối. Delta gồm `src/models/recommendation.py`,
`src/services/copilot/recommendation.py` và `tests/test_services/test_recommendation_hybrid.py`.
Kế thừa Golden 38/38 và frozen benchmark 100/100 từ merged baseline dựa trên diff. Standalone được chạy lại.
PostgreSQL và real LLM còn PENDING.

| Cổng trên candidate cuối | Kết quả |
|---|---:|
| Focused G5 | 30 pass, gồm 24 tests đã review và 6 tests mới |
| G2/G3/G4/G6A | 137 pass |
| Architecture | 43 pass |
| Full backend | 838 pass, 8 forecast skips |
| Standalone simulator | 180 pass |
| Ruff lint/format, docs và OpenAPI | Pass |
| Offline F1 | 55 câu hợp lệ |

Tất cả 10 mục trong exit ledger trả 0. Architecture từng phát hiện test mới import class DC nội bộ. Test cuối lấy
provenance từ metadata runtime và snapshot, rồi xác minh cùng model qua trạng thái fork. Architecture gate giữ nguyên.
Log lỗi và artifact điều tra vẫn nằm dưới `raw/remediation`. Rule rsync từng được nhắc trong báo cáo G1. Workspace
hiện tại và cây mirror baseline đã tải không chứa `.rsync-exclude`. Nguồn loại trừ xác minh được ở lượt này là Git ignore.
Gói ZIP và SHA đủ điều kiện đồng bộ Git thông thường hoặc chuyển riêng.

[Verification bundle](../../eval/evidence/2026-11-26-ai4-g5/remediation/verification-bundle.zip) ·
[Checksum bundle](../../eval/evidence/2026-11-26-ai4-g5/remediation/BUNDLE.sha256) ·
[Patch](../../eval/evidence/2026-11-26-ai4-g5/remediation/candidate.patch) ·
[Checksum patch](../../eval/evidence/2026-11-26-ai4-g5/remediation/SHA256SUMS) ·
[Raw logs và JUnit](../../eval/evidence/2026-11-26-ai4-g5/raw/remediation/final-v2) ·
[Fail-before identity](../../eval/evidence/2026-11-26-ai4-g5/raw/remediation/identity-fail-before.log)

[Hướng dẫn tái hiện và rollback](G5_RECOVERY_STATE.md)

---

*Các mục 1–5 dưới đây lưu bằng chứng của candidate trước targeted remediation.*

## 1. Merged baseline readiness

Local P-019, `feature/ai-4-how-to` tại `0f877f196db7b89759af08aab825f0fff82f7c3c`. HEAD, `develop` và `origin/develop`
trùng nhau. `git merge-base --is-ancestor develop HEAD` trả 0. Cây Git sạch khi bắt đầu. Checkpoint governance cũ trong
HANDOFF là **RECOVERABLE**. Nhánh AI-4 lịch sử chỉ dùng làm tham chiếu.

`git ls-tree -r` xác nhận blob/path của `src`, `config`, `tests`, `scripts/refactor`, `frontend` và PDF nghiên cứu
trùng mirror `20bb246477a9ffa9b8a7b222bd430ba4a7d92b25`. So với mirror `8493dd058cf4713a4b58fe9aee68ea72930c6e0f`,
WHY, WHAT-IF, snapshot, counterfactual, outcome ledger, jobs, grounding và Copilot integration trùng blob.
Shared runtime, Guard, charging, repository, API, chat và frontend có thay đổi. [Diff inventory](../../eval/evidence/2026-11-26-ai4-g5/raw/mirror-drift.log)

| Gate baseline develop | Kết quả chạy mới |
|---|---:|
| G2/G3/G4/G6A, architecture, runtime, Guard, API, admission, charging, repository và trace | 399 pass |
| Full backend | 808 pass, 8 forecast skips |
| Standalone simulator | 180 pass |
| Frontend Vitest | 59 pass |
| Ruff lint/format, docs, OpenAPI | Pass |
| Offline F1 | 55 câu hợp lệ |
| Golden | 38/38, comparator gốc và CRLF fixture provenance |
| Frozen backend | 100/100 cùng seed 1–5, 4 policies, 5 scenarios, 0 sai khác theo comparator |

Focused suite xác nhận admission concurrency và fingerprint, pending-safety interlock, atomic capture và integrity,
known booking cohort, trace lookup trên SQLite, cùng cách ly side-effect DB/WS/actuator. Chạy trên bản xuất sạch từ
HEAD. Architecture trong workspace phát hiện import ở cây nghiên cứu cũ bị Git bỏ qua. Test nguyên gốc qua trên
bản xuất sạch. Không di chuyển cây nghiên cứu đó.

Asyncio trong sandbox có lần chờ dù worker solver đã trả kết quả. Đã tái hiện ở G6A baseline và G5 riêng. Rerun native
dùng env tối thiểu, dữ liệu fixture và SQLite tạm. Golden lần LF có 11 mismatch đều ở giá trị hash scenario. Hai
fixture CRLF trong bản sao tạm khớp hash Windows của reference. Golden dùng comparator và dữ liệu lịch sử nguyên gốc.

Các script và logs giữ Python/SciPy/EV2Gym, OS, CPU, phiên bản code, lệnh, seed, config và fingerprint. Frozen benchmark
là kiểm hồi quy của các tải đã thực thi. [Raw baseline evidence](../../eval/evidence/2026-11-26-ai4-g5/raw)

## 2. Contracts và execution

- `src/models/recommendation.py` có typed goals theo vai trò, bounds và cờ đánh đổi bắt buộc, candidate set có
  version, feasibility, evidence refs, original/revised SLA, assumptions và `applied=false`.
- `src/services/copilot/recommendation.py` cung cấp `run_recommendation(snapshot, actor, goal)` độc lập với HTTP, LLM
  và UI. Caller chụp một snapshot atomic bằng `capture_atomic_snapshot` và truyền `ActorContext` phía server.
- Service kiểm vai trò, station và ownership trước rollout. Resident thấy booking của mình. Operator thấy original
  SLA từng booking trong cohort khi chạy mục tiêu nguồn.
- Mỗi search được hỗ trợ chạy tối đa một baseline, tối đa 8 nhánh ứng viên và trả tối đa 3 lựa chọn có bằng chứng.
  Tất cả nhánh dùng cùng snapshot hash, manifest known-at, cohort, horizon, config và policy, với patch có kiểu cho
  biến đang thử. Hàm chung trong WHAT-IF trích cùng announced grid limits. Các nhánh dùng lại WHAT-IF patch preparation,
  Guard, runner và single-worker solver.
- SOC thử biên, mục tiêu gốc và SOC hiện tại nếu thuộc bounds, cùng các điểm 5% lấy đều nếu nhiều. Xếp target khả thi
  cao nhất. Đọc SOC vật lý đúng phút deadline trên fork. Nếu thiếu quan sát tại deadline, trả unknown.
- Deadline thử các phút trong cửa sổ, lấy đều khi vượt giới hạn. Xếp theo mốc đạt target thực tế, rồi độ lệch nhỏ nhất
  so với deadline gốc, rồi deadline sớm hơn. Khi target đã đạt tại snapshot, thời gian chờ thêm là 0. Release báo riêng.
- Site thử lưới đều gồm hai biên, xếp mức thấp nhất đã thử và đạt ngưỡng. Giữ cam kết gốc của toàn cohort. Mẫu số phải
  bao phủ toàn cohort và loại kết quả unknown khỏi xác nhận. Khi bật bảo vệ AC, từng booking AC đúng hạn ở baseline
  phải giữ đúng hạn. Trên công suất lắp đặt phải có giả định hạ tầng. Nguồn độc lập trả unsupported.
- Cờ cư dân kiểm giảm target, dời deadline muộn và mất kết quả đúng hạn của chính mình. Các booking còn lại được bảo vệ
  theo original SLA baseline. Khi chưa đủ dữ liệu xác nhận bảo toàn, candidate là unknown. Hold an toàn, vi phạm,
  allocation bị từ chối, lệnh bị chặn và approval chưa giải quyết đều ngăn đưa nhánh vào options.
- Timeout dùng ngân sách thời gian của cả search. Cooperative cancellation giữ các phương án đã hoàn tất và ghi
  failed/skipped. Task cancellation của caller vẫn lan truyền. Native solver call đã chạy có thể hoàn tất bước hiện
  tại. Không có binary search và mọi khẳng định chỉ trong tập đã thử.

## 3. Oracles và verification

Các oracle trong `tests/test_services/test_recommendation.py` độc lập với logic xếp hạng. Positive/negative dùng kernel
thật, tính giới hạn từ dung lượng pin fixture 60,13 kWh, cổng AC 11 kW, hiệu suất và phút khai báo. Fixture site sử dụng
ngân sách B0 22% và hiệu suất chuyển đổi 95%, lưu pin 98%. Các lần thử đầu ghi nhận lượng tử lệnh có thể để lại phần hụt dưới 1 Wh. Các fixture xác định rõ trường hợp giới hạn năng lượng, giữ so sánh target chính xác. Probe non-monotonic
chèn mốc hoàn tất với một thất bại xen giữa các ứng viên tốt, giữ kiểm tra đầy đủ các candidate và thứ tự kỳ vọng.

Coverage gồm tie-break, site denominator, per-booking AC protection, original/revised SLA, mốc SOC/deadline/target/release,
no feasible, phân quyền, safety/approval, unsupported supply, timeout/cancellation, no live mutation, sự kiện được công
bố và same-snapshot replay. Hồi quy G2/G3/G4/G6A kiểm ranh giới kiến trúc và tương thích các luồng cũ.

| Oracle thực tế | Candidates | Baseline | Tổng lượt nhánh | Lựa chọn đầu tiên | Search ms |
|---|---:|---:|---:|---|---:|
| Max SOC tại T+16 | 3 | 1 | 4 | 21% | 97,7 |
| Max SOC tại T+3 | 2 | 1 | 3 | Không có | 53,1 |
| Earliest completion cho 21% | 5 | 1 | 6 | Đạt T+16, rời T+23 | 139,0 |
| Earliest completion với cửa sổ T+1 đến T+3 | 3 | 1 | 4 | Không có | 84,2 |
| Site limit đủ SLA | 8 | 1 | 9 | 10 kW | 129,1 |
| Site limit khi cổng AC là nút thắt | 8 | 1 | 9 | Không có | 135,2 |
| Site SLA có booking censored | 1 | 1 | 2 | Partial | 40,5 |

Trong các oracle trên, mọi nhánh đã chạy đến kết quả. Những nhánh hụt mục tiêu được ghi là infeasible hoặc unknown
theo bằng chứng. Probe timeout và cancellation đều chạy 3 nhánh gồm 1 baseline, giữ ứng viên T+20, thất bại ở T+21
và bỏ qua T+22. Probe lỗi branch riêng chạy tổng 4 nhánh, ghi lỗi T+21 rồi chọn T+22 trong phần đã xác minh. Các mốc
latency là số đo fixture, không phải SLA dịch vụ. [Kết quả định lượng](../../eval/evidence/2026-11-26-ai4-g5/raw/verified/oracle-summary.json) · [JUnit và toàn bộ evidence từng nhánh](../../eval/evidence/2026-11-26-ai4-g5/raw/verified/g5-results.xml)

Lần chạy đầu phát hiện fixture chưa tính đúng công suất làm tròn và một case ghi kỳ vọng 21% trong grid 20/25/30%.
Đã giữ log lỗi và chỉnh fixture để bounds thực sự bao gồm 21%, dùng phép tính độc lập kiểm 25% và 30% vượt trần
năng lượng ở T+16. Tiêu chí đạt target và tests hồi quy cũ giữ nguyên. [Lần thử đầu](../../eval/evidence/2026-11-26-ai4-g5/raw/g5-first-native.log) · [Lần xác minh trước cuối](../../eval/evidence/2026-11-26-ai4-g5/raw/candidate-g5.log)

| Gate patch cuối | Kết quả |
|---|---:|
| Focused G5 | 24 pass |
| G2/G3/G4/G6A và architecture | 180 pass |
| G3 evaluator | 8/8 case, 6/6 mutation |
| Full backend | 832 pass, 8 forecast skips đã có |
| Standalone simulator | 180 pass |
| Ruff lint/format, docs, OpenAPI | Pass |
| Offline F1 | 55 câu hợp lệ |

Runner exit 0 và tất cả 11 mục verification exit 0. [Lệnh và kết quả](../../eval/evidence/2026-11-26-ai4-g5/raw/verified/verification-exits.tsv)

## 4. Provenance, reproduce và rollback

- [Candidate patch](../../eval/evidence/2026-11-26-ai4-g5/candidate.patch) · [SHA-256](../../eval/evidence/2026-11-26-ai4-g5/SHA256SUMS) · [Raw evidence](../../eval/evidence/2026-11-26-ai4-g5/raw)
- Code/test patch gồm 5 đường dẫn. Áp trên bản xuất sạch từ base với `git apply --check <candidate.patch>` rồi
  `git apply <candidate.patch>`. `raw/verified/candidate-executed-files.sha256` xác nhận nội dung thật chạy.
  [Cách chạy lại](G5_RECOVERY_STATE.md)
- Core, optimizer, Guard, runtime, snapshot/ledger/runner, API, frontend, config, migrations và CI giữ nguyên byte.
  Thay đổi WHAT-IF chỉ trích hàm chọn announced limits, có regression G4 và G6A. Golden và frozen benchmark được
  chạy lại trên develop merged. Candidate có standalone và hồi quy toàn backend. [Frozen-scope diff](../../eval/evidence/2026-11-26-ai4-g5/raw/candidate-frozen-scope.diff)
- Khi cần rollback, Tech Lead dùng `git apply --reverse --check <candidate.patch>` rồi reverse trên cây phù hợp.
  Kiểm diff trước khi làm trên workspace chung. Patch code/test không tạo migration hay state live. Ghi roadmap
  riêng theo quyết định nhóm. Raw evidence, patch, recovery và collaboration log nằm trong các đường dẫn chạy cục bộ
  bị Git bỏ qua theo cấu hình repo.

## 5. Chuyển giao kiến thức và G6B

1. Trước G5, AI-4 có WHY/WHAT-IF và đường standalone G6A. HOW-TO nhận diện intent nhưng trả `feature_not_available`.
2. G5 thêm service thử một biến có giới hạn, bằng chứng và kết quả khả thi theo mô phỏng. Người gọi chọn bounds và đánh đổi.
3. Một snapshot và baseline chung giúp so sánh các phương án cùng điều kiện. Guard và solver được tái sử dụng.
4. Phạm vi chức năng là F8 Decision Copilot và các ràng buộc FR28–FR29 về quyền, evidence, advisory-only.
5. Mô tả HOW-TO điều kiện từ AI-1 trong PRD/ADR-015 khác roadmap nhóm chọn. Đề xuất amendment giữ lịch sử ADR và
   ghi phạm vi tìm kiếm hữu hạn cùng Chat Agent là điểm vào chính. [Master Plan](AI-4_MASTER_IMPLEMENTATION_PLAN.md)
6. Khi được phép ở G6B, typed tools gọi approved deterministic services qua service boundary. Chat Agent giữ
   orchestration và HITL, dùng chung role-aware actor/job lifecycle, typed chat result/stream và grounding.
   G6A là fallback. Carry-over G6A-F01/F02/F03 giữ trong [issue ledger](ISSUES.md).
7. Đây là bằng chứng do implementation tự chạy trên fixture. Tech Lead review độc lập mới đóng gate. Real LLM smoke
   và PostgreSQL runtime còn PENDING.

**STOP — WAITING_FOR_TECH_LEAD_FINAL_ACCEPTANCE (GATE 5)**
