# AI-4.2B — WHAT-IF Engine · Gate 4

**G4 — READY_FOR_FINAL_ACCEPTANCE**

## Final remediation

Tech Lead ghi `CONDITIONAL PASS — FINAL REMEDIATION REQUIRED` tại mirror `343cddce2e7c22e8753945589a94d2ad7ed48042` trên Gate 02 patch `ec99050de22414c7f3b964c6ae898458db15a169119bc05ae5ba5abaa92491bf`. Remediation xử lý G4-F01–F03 trên local `P-019`, branch `feature/ai-4`, HEAD `4658b1f068350c130ed5ed1a744c19a7b8cd522c`. Git local dùng patch để dựng lại trạng thái review. Hai mirror SHA là định danh Tech Lead cung cấp. Cả 245 source/test files match reviewed tree trước sửa và match final candidate tree sau sửa.

| Artifact | SHA-256 |
|---|---|
| Final G4 candidate, áp sau G3 approved patch | `e8ae5cedbbe5af0a0a05d63f3dbb4ea6ac22fda40a4628a2cf7abca82be10d0f` |
| Remediation-only, áp sau Gate 02 reviewed patch | `1cdb630cc10a4bfd1fb96d1ac2264dbd4a9515f3dbfe7153780f0c6fd33160bf` |

[Final candidate](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/candidate.patch) · [SHA-256](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/candidate.sha256) · [Remediation-only diff](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/remediation.patch) · [Provenance](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/candidate-provenance.txt)

### Resolution matrix

| Finding | Confirmed behavior và resolution |
|---|---|
| G4-F01 — Revised deadline | Reviewed candidate nhận T+7:30, giữ cổng tới T+8 và chuyển plug-in của booking B từ T+15 lên T+8. Battery kWh A/B lần lượt là 2,695/0,898333 ở baseline và 1,437333/2,156 ở patched. Cả original và revised SLA của A đều false. `_prepare_patch` trả Pydantic `ValidationError` tại `deadline` với code `deadline_not_on_simulator_minute` cho explicit deadline lệch lưới phút tính từ T. Có tests cho offset, grid tại giây/microsecond lẻ và target-only với deadline gốc lẻ. `HybridStation.minute_of` và live departure semantics giữ theo vật lý hiện hành. |
| G4-F02 — Comparable KPI deltas | Reviewed candidate trả −15 phút khi baseline quan sát A=10 và B=50, nhưng patched chỉ A=15 và B censored. Kết quả giữ cả hai branch aggregates và delta=null với `non_comparable_sample` cho wait mean/p90 khi mất booking. SLA overall/AC/DC và service/charged coverage dùng đúng membership mẫu số của từng metric. Empty sample cùng tập trả `missing_data`. Unsafe hoặc quan sát thiếu horizon trả cả `delta` lẫn `delta_reasons` là null. Counts, energy và cost vẫn có delta hợp lệ trên full safe horizon; resident metadata chỉ chứa mã lý do. |
| G4-F03 — Numerical site limit | Xác nhận binding source tăng 40→80 kW làm output horizon tăng 5,066667→10,133333 kWh và cost 14.666,67→29.333,33 VND trong ca 2 AC + 2 DC. Ca connector, cabinet, zone và vehicle cap, future down/up và cabinet-only đã có oracle độc lập. Confirmed replay bug tại T khi captured runtime override 50 kW che event 30 kW, tạo 9,5 thay vì 8,233333 output kWh ở baseline. Fork replay tại T giữ cả nguồn công bố và runtime override. Site patch thay captured runtime supply premise và áp trần riêng. Tới future effective event, announced regime thay starting runtime premise ở cả hai fork, site cap vẫn áp trên patched. Cabinet kW output vẫn lấy từ cùng scenario schedule. |

[Fail-before trên reviewed source với final test file](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/final-fail-before.stdout.txt) · [Pass-after và numerical oracles](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/g4-oracles.stdout.txt) · [Phép tính độc lập](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/oracle-calculations.md)

`unmet_original_battery_kwh` là năng lượng còn thiếu để đạt original target tại observation cutoff. `unmet_original_output_kwh` là charger-output equivalent tại cùng cutoff, dùng booking charging efficiency. Vì xe có thể tiếp tục sạc qua original deadline tùy patch, các field này đo một thời điểm khác với shortfall đánh giá tại original deadline. Original SLA giữ timestamp gốc.

### Final verification

| Gate | Kết quả trên final candidate |
|---|---|
| Fail-before trên Gate 02 | Exit 1, 8 failed / 7 passed trong 15 targeted cases. Có lỗi deadline, KPI, replay và các assertions về contract mới. |
| WHAT-IF and numerical oracles | 47 passed |
| Combined focused | 184 passed |
| G3 foundation / Architecture chạy riêng | 37 passed / 43 passed |
| Full backend | 768 passed, 8 existing forecast skips |
| G3 evaluator | 8/8 cases, 6/6 mutations caught |
| Ruff lint, Ruff format, docs, OpenAPI | Pass |
| F1 offline dataset | 55 câu hợp lệ |
| Preserved AST và standalone simulator | 114/114 AST, 180 passed |
| Golden CRLF | 38/38, frozen fixture và reference archive hashes khớp |
| Frozen benchmark | 100/100, 0 comparator problems. Non-timing KPIs và experiment fingerprints khớp. Hard violations, rejected allocations và sampled over-limit minutes đều 0. |
| PostgreSQL runtime | PENDING, exit 77. Không có PostgreSQL binaries trong PATH và Docker daemon không kết nối được. |
| Mandatory gate | Overall exit 0 |

[Exit ledger](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/exit-codes.tsv) · [Backend](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/backend-tests.stdout.txt) · [G3 foundation](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/g3-foundation.stdout.txt) · [Architecture](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/architecture.stdout.txt) · [Golden CRLF](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/golden-compare.stdout.txt) · [Non-timing comparator](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/benchmark-compare.stdout.txt) · [Benchmark fingerprints và counters](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/benchmark-provenance.stdout.txt)

Final timing probe lặp mỗi operation ba lần trên fixture B0 AC 25 phút. Median paired latency theo operation là 28,526–36,084 ms và chữ ký phi thời gian khớp giữa các lần lặp. Fixture và TOU vẫn là dữ liệu mô phỏng. Internal jobs dùng một worker, in-memory retention và TTL. Một native solver call đang chạy có thể hoàn tất sau khi job bị cancel. [Timing results](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/g4-latency.json)

### Reproduce final candidate

- Dùng local HEAD trên, sao chép final `candidate.patch` vào evidence directory mới và chạy `bash eval/evidence/2026-11-25-ai4-4-2b/run_gate.sh <new-scratch> <new-evidence-dir>`. Runner kiểm SHA G3, dựng clone LF/CRLF và áp G3 rồi final G4 trong mỗi clone. [Lệnh thực chạy](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate-launch.stdout.txt)
- `git apply --reverse --check` đã chạy cho cả final G4 candidate và remediation-only patch trong cây scratch. Reverse remediation-only đưa riêng các hunk của vòng này về Gate 02. Candidate source/test và handoff Markdown được lưu riêng để tài liệu có thể trỏ SHA-256 của candidate.
- Mandatory gate chạy lại standalone, Golden CRLF và frozen benchmark vì fix G4-F03 chạm cả tương tác `HybridStation` và `StationKernel.effective_limits`. G3 evaluator, architecture và checks khác dùng cùng final candidate. [Raw commands và exit codes](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/exit-codes.tsv)

### G6A readiness

WHY đã được nghiệm thu ở G2. WHAT-IF đã qua final local verification và chờ Tech Lead final acceptance ở G4. G6A dùng hai engine này cho shared integration foundation và WHY/WHAT-IF end-to-end sau authorization riêng. Trình tự sau đó là G5 → G6B → G7. HOW-TO giữ toàn bộ approved scope và acceptance criteria. Shared intent, jobs, grounding và announced replay constraints được ghi trong Master Plan. [Roadmap handoff](AI-4_MASTER_IMPLEMENTATION_PLAN.md)

## Candidate đã review (Gate 02)

| Hạng mục | Provenance |
|---|---|
| Local workspace | `P-019`, branch `feature/ai-4`, HEAD `4658b1f068350c130ed5ed1a744c19a7b8cd522c` |
| G3 đã duyệt | Mirror `d0fcf5d11cfd75b677eeaed00e5b5264ab828744` và patch SHA-256 `59a92d326cfaae6cd8bb3d2b94b4124765b3efdcb3551b2c48d36e60ca73dc5d` |
| G4 patch sau G3 | SHA-256 `ec99050de22414c7f3b964c6ae898458db15a169119bc05ae5ba5abaa92491bf` |
| Môi trường | Linux WSL2, Python 3.12.3, NumPy 2.4.6, SciPy 1.18.1, EV2Gym 2.0.0. Dùng lại `.simulator`. |

Product và test workspace ban đầu khớp từng byte với candidate Gate 3 đã duyệt. Gate 4 chạy trên cây sạch dựng bằng local HEAD rồi áp hai patch theo thứ tự. Gate Golden dùng clone riêng với CRLF. Các tài liệu phê duyệt G3 và evidence độc lập với candidate patch. [Candidate patch](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/candidate.patch) · [Recovery state](G4_RECOVERY_STATE.md)

## Contract và thay đổi theo tệp

| Thành phần | Hành vi |
|---|---|
| `src/models/what_if.py` | Discriminated union cho một operation. `revise_vehicle` có thể chứa target, deadline hoặc cả hai. Schema từ chối extra fields, số không hữu hạn, sai kiểu, timestamp không có offset và duration ngoài bounds. |
| `src/services/copilot/what_if.py` | Authorize theo actor do server cấp, station và booking ownership. Operator có thể chạy infrastructure operations hoặc hypothetical booking revision trong station scope. Resident thấy các booking thuộc mình và aggregate station metrics. Result gắn snapshot, manifest, patch, branch input/config hashes, run IDs và actual observation cutoff. |
| `src/services/copilot/counterfactual.py`, `outcome_ledger.py`, `snapshot.py` | Dùng runner và safety semantics G3. Hai fork độc lập replay cùng announced future grid events. Original target crossing được đo độc lập khi target giả định thay đổi, và revised commitment được đánh giá từ cùng energy/SOC observations. Snapshot digest được kiểm trước và sau pair. |
| `src/simulator/hybrid_station.py`, `core/kernel.py` | Fork-only environment methods, copy-on-write cho Scenario và vehicle definitions, giữ adapter/energy history, hardware limits và fault ownership. Business Guard, Physical Guard và solver hiện hành tiếp tục điều khiển mọi allocation. |
| `src/services/copilot/jobs.py` | Typed internal submit/poll/cancel/close trên một event loop. Một consumer, mặc định bốn queued jobs, tối đa 64 retained records, 60 giây end-to-end timeout, TTL 300 giây. Sau TTL, view đổi thành expired và payload bị giải phóng. Tombstone được giữ thêm một TTL. |
| `tests/test_services/test_what_if.py`, G4 harness | Hand-calculated acceptance, energy, timing và safety oracles. Coverage cho authorization, repeated runs, native G3 cancellation, G4 job cleanup during an active native solver call, snapshot tamper và live-effect spies. |

## Bốn MUST operation

| Operation | Semantics và evidence oracle |
|---|---|
| `revise_vehicle.target_soc` | Dùng SOC thật ở T cho xe đã đến. Khi đã đạt revised target, giữ SOC và năng lượng, trả nhãn already satisfied. Xe DC đang cắm mới đạt bắt đầu release delay thông thường và AC vẫn giữ cổng tới deadline. Xe đang chờ đã đạt target không cần cổng. Một booking NOT_ARRIVED chỉ có assumed arrival SOC, do đó yêu cầu hạ target tới hoặc dưới dữ kiện giả định đó nhận validation error. Oracle đo target 21% và 22%, original 80%, historical completion và release. |
| `revise_vehicle.deadline` | Giữ original deadline trong ledger. Revised deadline phải sau T và arrival. Final remediation kiểm alignment theo simulator minute grid. Physics rời tại phút tương ứng và SLA so theo timestamp khai báo. Oracle tính chênh energy tại 11 kW khi đổi deadline 15 phút thành 7 hoặc 23 phút. |
| `site_limit` | Đầu vào lưới kW hữu hạn, dương, shared supply. Tăng vượt cấu hình yêu cầu hypothetical infrastructure và vẫn giới hạn trong station power envelope. Known future grid events dùng chung, còn patch đặt trần riêng cho nhánh hypothetical; cabinet, port, zone và vehicle acceptance tiếp tục giới hạn output. Oracle kiểm B0 fixed share 22%, conversion 0.95, một source limit đã công bố và TOU trên grid input. |
| `outage` | Khoảng thời gian theo phút simulator. Chỉ ngắt connector hợp lệ, restore đúng fault do patch sở hữu. Pre-existing fault được giữ. Restore đúng horizon boundary cập nhật terminal state mà không tạo thêm energy interval. Oracle kiểm ba phút mất charging output và timestamp plug-in. |

## So sánh, an toàn và giới hạn

- Cả hai nhánh giữ cùng initial snapshot, `known_at(T)` manifest, cohort, experiment và planned horizon. Các metrics station dùng original commitments, scope theo actor, và tách charger output, grid input và battery energy. Revised SLA được báo riêng cho booking được sửa.
- Delta có dấu patched trừ baseline khi comparison hợp lệ. Cả hai nhánh phải hoàn tất an toàn tới cùng planned horizon. Mean, p90 và rates yêu cầu cùng membership theo từng metric. Branch unsafe hoặc unresolved có status/cutoff riêng, `feasible=false` và `applied=false`. Khi không có objective cho site/outage hoặc SLA chưa quan sát được, feasibility là null. Optimistic energy bound chỉ là một bound.
- Wait samples có observed/censored counts. Historical timestamps chưa biết vẫn là null. Release và target reached là mốc riêng. Kết quả luôn mang `applied=false`.
- Hủy job dừng coroutine và ngăn nó gửi thêm work. Native call đã vào worker có thể hoàn tất sau cancellation hoặc timeout. Jobs nằm trong RAM của một event loop. Queue, retention và TTL giới hạn bộ nhớ theo số job. Gate 4 chưa có durable jobs hoặc REST.
- PostgreSQL runtime vẫn PENDING. Hardware response và latency evidence thuộc synthetic fixture.

## Verification đã lưu ở Gate 02

Gate 02 đã handoff `READY_FOR_REVIEW` với mandatory gate exit `0`. [Exit-code ledger](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/exit-codes.tsv)

| Gate | Kết quả thực chạy |
|---|---|
| Focused, gồm architecture và G3 foundation | 169 passed |
| G4 oracle và contract tests | 32 passed |
| Full backend | 753 passed, 8 existing forecast skips |
| Standalone simulator | 180 passed |
| G3 evaluator regression | 8/8, mutation 6/6 |
| Ruff lint, Ruff format, documentation, OpenAPI | Pass |
| F1 offline data | 55 câu hợp lệ |
| Preserved AST | 114/114 |
| Golden CRLF | 38/38. Hai fixture byte hashes và P0 archive hash khớp. |
| Frozen benchmark | 100/100, 0 comparator problems. Non-timing KPIs, experiment fingerprints và counters từng run khớp. Tổng hard violations, rejected allocations và sampled over-limit minutes đều 0. |
| PostgreSQL runtime | PENDING, exit 77. PostgreSQL binaries không có sẵn và Docker daemon không kết nối được. |

[Focused](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/focused-g4.stdout.txt) · [Oracle logs](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/g4-oracles.stdout.txt) · [Full backend](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/backend-tests.stdout.txt) · [Standalone](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/simulator-tests.stdout.txt) · [Golden](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/golden-compare.stdout.txt) · [Frozen comparator](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/benchmark-compare.stdout.txt) · [Frozen provenance và counters](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/benchmark-provenance.stdout.txt)

WHAT-IF latency đo từ đầu đến cuối một pair trên fixture B0 synthetic AC, horizon 25 phút. Mỗi operation lặp ba lần với cùng chữ ký phi thời gian. Median từng operation nằm trong 48,846–57,270 ms. Kết quả mô tả fixture này. [Timing và example results](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/g4-latency.json)

### Checklist

- [x] Bốn MUST operation, strict schema và authorization.
- [x] Cùng snapshot, known-at manifest, cohort, policy và planned horizon. Kiểm integrity, copy-on-write và live side-effect guards.
- [x] Original/revised SLA, hand-calculated energy, TOU, wait/release và horizon censoring.
- [x] Safety interlock, cả hard violation đã ACK và unresolved. Delta chỉ có cho cặp full safe horizon.
- [x] Owner-scoped jobs, queue/retention bounds, TTL, timeout và cancellation trong lúc native worker chạy.
- [x] Candidate source/test trùng từng byte với workspace. Mandatory gate và Unified Core regressions chạy lại trên đúng patch.
- [ ] PostgreSQL runtime verification.
- [ ] Tech Lead Gate 4 review.

### Fail-before và pass-after

Gate 01 qua bộ test ban đầu. Oracle bổ sung tái hiện lỗi khi cap giả định bằng mức nguồn tại T và sau đó có đợt tăng nguồn đã công bố. Trước sửa, AC peak grid input là 4,4 kW so với kỳ vọng 1,76 kW. Gate 02 duy trì cap giả định trong đợt tăng nguồn. Log ban đầu cũng ghi lại việc hiệu chỉnh oracle theo AC acceptance và B0 fixed shares. [Gate 01](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-01/exit-codes.tsv) · [Fail-before](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/site-cap-fail-before.stdout.txt) · [Focused pass-after](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/focused-final-probes.stdout.txt)

### Reproduce và rollback

- Từ local baseline, dùng accepted G3 patch và G4 patch trong evidence directory mới. Chạy `bash eval/evidence/2026-11-25-ai4-4-2b/run_gate.sh <new-scratch> <new-evidence-dir>`. Runner tự kiểm G3 SHA, tạo clone LF và CRLF rồi áp hai patch tương ứng. Lệnh thực, cwd, stdout, stderr và từng exit đều có trong ledger.
- Để kiểm rollback G4, dùng `git apply --reverse --check <G4 candidate.patch>` trong clone candidate. Đảo riêng G4 delta trên cây kiểm tra trả code về accepted G3. Project Owner xem từng hunk nếu rollback trong workspace đang có thay đổi của thành viên khác. Giữ báo cáo phê duyệt và toàn bộ evidence.

**STOP — WAITING_FOR_TECH_LEAD_FINAL_ACCEPTANCE (GATE 4)**

