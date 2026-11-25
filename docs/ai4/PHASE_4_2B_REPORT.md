# AI-4.2B — WHAT-IF Engine · Gate 4

## Candidate

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
| `revise_vehicle.deadline` | Giữ original deadline trong ledger. Revised deadline phải sau T và arrival. Physics rời tại phút tương ứng; SLA so theo timestamp khai báo. Oracle tính chênh energy tại 11 kW khi đổi deadline 15 phút thành 7 hoặc 23 phút. |
| `site_limit` | Đầu vào lưới kW hữu hạn, dương, shared supply. Tăng vượt cấu hình yêu cầu hypothetical infrastructure và vẫn giới hạn trong station power envelope. Known future grid events dùng chung, còn patch đặt trần riêng cho nhánh hypothetical; cabinet, port, zone và vehicle acceptance tiếp tục giới hạn output. Oracle kiểm B0 fixed share 22%, conversion 0.95, một source limit đã công bố và TOU trên grid input. |
| `outage` | Khoảng thời gian theo phút simulator. Chỉ ngắt connector hợp lệ, restore đúng fault do patch sở hữu. Pre-existing fault được giữ. Restore đúng horizon boundary cập nhật terminal state mà không tạo thêm energy interval. Oracle kiểm ba phút mất charging output và timestamp plug-in. |

## So sánh, an toàn và giới hạn

- Cả hai nhánh giữ cùng initial snapshot, `known_at(T)` manifest, cohort, experiment và planned horizon. Các metrics station dùng original commitments, scope theo actor, và tách charger output, grid input và battery energy. Revised SLA được báo riêng cho booking được sửa.
- Delta luôn là patched trừ baseline. Chỉ tạo delta khi cả hai nhánh hoàn tất an toàn tới cùng planned horizon. Branch unsafe hoặc unresolved có status/cutoff riêng, `feasible=false` và `applied=false`. Khi không có objective cho site/outage hoặc SLA chưa quan sát được, feasibility là null. Không dùng optimistic energy bound làm chứng nhận.
- Wait samples có observed/censored counts. Historical timestamps chưa biết vẫn là null. Release và target reached là mốc riêng. Kết quả luôn mang `applied=false`.
- Hủy job dừng coroutine và ngăn nó gửi thêm work. Native call đã vào worker có thể hoàn tất sau cancellation hoặc timeout. Jobs nằm trong RAM của một event loop. Queue, retention và TTL giới hạn bộ nhớ theo số job. Gate 4 chưa có durable jobs hoặc REST.
- PostgreSQL runtime vẫn PENDING. Hardware response và latency evidence thuộc synthetic fixture.

## Verification

**READY_FOR_REVIEW.** Mandatory gate exit `0` trên candidate cuối. [Exit-code ledger](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/gate-02/exit-codes.tsv)

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

**STOP — WAITING_FOR_TECH_LEAD_REVIEW (GATE 4)**
