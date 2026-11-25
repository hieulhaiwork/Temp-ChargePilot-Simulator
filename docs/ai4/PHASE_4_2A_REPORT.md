# AI-4.2A — Counterfactual Foundation · Gate 3

**APPROVED.** Accepted mirror `d0fcf5d11cfd75b677eeaed00e5b5264ab828744` và candidate patch SHA-256 `59a92d326cfaae6cd8bb3d2b94b4124765b3efdcb3551b2c48d36e60ca73dc5d`. Tech Lead chấp nhận G3-F01–F08 cùng kết quả gate đã ghi. PostgreSQL runtime vẫn PENDING.

## Candidate và provenance

| Hạng mục | Giá trị |
|---|---|
| Local source of truth | `P-019`, branch `feature/ai-4`, HEAD G2 `4658b1f068350c130ed5ed1a744c19a7b8cd522c` |
| Mirror G2 approved | `aa37ca55978f99009c6d4b25c0676d87eac7fa7b` |
| Mirror G3 reviewed | `49b6fec00e90c1f5c6f504abfb038969f2d6c64c`, verdict Tech Lead CHANGES REQUIRED |
| Candidate Gate 3 | SHA-256 `59a92d326cfaae6cd8bb3d2b94b4124765b3efdcb3551b2c48d36e60ca73dc5d` |
| Môi trường | Linux WSL2, Python 3.12.3, EV2Gym 2.0.0, SciPy 1.18.1, NumPy 2.4.6. Dùng lại `.simulator`. |

Patch mirror áp được trên local baseline và khớp từng byte với chín tệp product/test ban đầu. Candidate gate sinh từ local baseline có cả source/test untracked. Hai cây candidate tách biệt dùng cho backend và Golden CRLF. Báo cáo, recovery notes và raw output nằm ngoài nội dung patch cần băm. [Mapping và trạng thái recovery](G3_RECOVERY_STATE.md) · [Reviewed product diff](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/reviewed-product.patch) · [Candidate patch](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/candidate.patch)

## Implementation handoff

| Tệp | Công việc |
|---|---|
| `src/services/runtime.py`, `control_loop.py` | Neon bổ sung pending safety inheritance và fingerprint. Codex dùng runtime advance có interlock trong rollout, retry/readback G1 và dedup mutation đã replay. |
| `src/services/admission.py`, `charging_service.py`, `simulation_service.py` | Dừng admission khi safety unresolved. Đưa event booking/incident vào outbox khi cập nhật physics để capture có thể replay. |
| `src/services/copilot/snapshot.py`, `src/simulator/hybrid_station.py`, `src/simulator/core/kernel.py` | Giữ atomic capture, detached seed và prospective manifest của Neon. Bổ sung digest nội dung, kiểm cohort, tách live registration khỏi simulator clock, lọc context ngoài cohort và copy mutable maps. |
| `src/services/copilot/counterfactual.py` | Giữ paired no-op và shared solver của Neon. Thực thi safety trước bước kế tiếp và ở biên horizon. Báo cutoff, giới hạn active branches và thu hồi branch còn lại khi paired job thất bại. |
| `src/models/copilot.py`, `src/services/copilot/outcome_ledger.py` | Giữ additive ledger của Neon. Thêm trạng thái branch và observed cutoff. Tách timestamp lịch sử, dùng optimistic energy bound và công khai denominator thời gian chờ. |
| `tests/test_services/test_counterfactual_foundation.py`, `test_g3_runtime_readiness.py`, G3 evidence scripts | Mở rộng regression probes. Chạy evaluator độc lập của Neon và hoàn thiện gate runner, reproducibility và expected exits. |

## G3-F01–F08

| ID | Phân loại | Root cause, resolution và evidence |
|---|---|---|
| F01 | Confirmed bug, Neon fixed | Fork thiếu pending/ACK/attempt state, fingerprint thiếu thay đổi pending. Clean G2 với test patch có đúng ba lỗi, exit 1. Reviewed Neon qua cả ba. |
| F02 | Confirmed bug | Sandbox và admission gọi thẳng simulator step. Runtime interlock giờ sở hữu step và pending event. Guard/readback giải quyết tại cùng phút hoặc dừng sớm. Probes bao phủ emergency bị chặn, retry exhaustion, thành công, cancel khi delivery và hard event ở phút cuối. |
| F03 | Confirmed bug | Cached manifest hash, seed projection làm tròn và bỏ trường execution, fork chia sẻ mutable maps. Hash được tính lại từ nội dung và seed trước branch. Mutation probes bao phủ manifest, booking, config, plan, scheduler và seed. |
| F04 | Confirmed bug | Lệch clock giữa DB và simulator, physical sessions không thuộc cohort, mutation event giao sau commit. Snapshot lấy committed live registrations, kiểm session parity, lọc plan/approval/command/profile metadata, giữ effective incidents cho replay hoặc trả not_ready. Kiểm riêng missing physical update, present untracked, clock lệch và staged booking. |
| F05 | Confirmed bug | Code suy lịch sử first charge từ plug và có thể mất plug khi reassign. Timestamp không chứng minh được trả null. `first_rollout_charge_at` đo riêng. Probe cắm 0 kW, bắt đầu sạc sau đó rồi fault/reassign trước T. |
| F06 | Confirmed limitation | Công thức optimistic power × time từng mang tên physical feasibility. Bound đã đổi tên. Ledger giữ original targets, fixed cohort, `observed_until`, censoring và mẫu số công khai. Oracle kiểm energy, TOU units, DC completion/release, NOT_ARRIVED và mẫu số rỗng. |
| F07 | Confirmed bug và giới hạn | `gather` cũ có thể để peer chạy tiếp. Paired job hủy và chờ cleanup peer. Minute gate và tám branch giới hạn concurrency trên một loop. Kiểm default/probe contention, branch exception, cancellation và timeout với worker còn chạy. Strict priority và latency dưới tải sản xuất chưa được kiểm chứng. |
| F08 | Confirmed evidence gap | Runner cũ thiếu patch, evaluator và overall failure propagation. Runner mới lưu exit thực, expected exit, provenance và logs. Gate 01 thực tế trả 1 khi full backend lỗi dù các nhóm khác qua. G4 MUST backlog đã khớp ADR. |

[Fail-before G2](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/fail-before-f01.stdout.txt) · [Reviewed Neon pass-after F01](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/focused-reviewed-readiness.txt) · [Fail-before probes trên Neon](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/fail-before-expanded.txt)

## Contract và giới hạn

- Atomic capture dùng lock hierarchy đã duyệt, không tiến đồng hồ hoặc drain live outbox. Snapshot tách dữ liệu khỏi live và xác minh SHA-256 trước khi build fork. Pydantic nested objects có thể sửa được. Branch từ chối content thay đổi. Contract dùng in-memory cloning và tin cậy implementation của custom component fork. Custom state không biểu diễn được trả `not_ready`.
- Synthetic known-at dùng đồng hồ simulator cho publication. Live dùng committed store membership ở thời điểm capture. Backend incident chỉ có thông tin effect hiện thời. Xe chưa đăng ký trong benchmark truth bị loại khỏi rollout. Thiếu mapping cohort vật lý làm snapshot unavailable để peak, cost và energy của branch có cùng phạm vi.
- Paired no-op dùng cùng horizon, snapshot digest, manifest và cohort. Trạng thái `unsafe` giữ hard violation đã đo kể cả khi readback đã an toàn. `unresolved_safety` giữ pending và cutoff thực. R10 billing và frozen KPI dùng contract hiện hành.
- Live và sandbox dùng cùng single-worker solver. Coroutine cancellation ngăn công việc rollout tiếp theo. Native call đã vào worker có thể hoàn tất sau timeout. Smoke tests chứng minh tiến triển ở fixture cụ thể. PostgreSQL runtime vẫn PENDING.
- ADR-014 mô tả replay ban đầu. Kiến trúc Unified Core và Master Plan áp dụng fork hiện nay. HOW-TO hữu hạn giữ theo AI-4 scope mới, AI-1 nằm ngoài gate này.

## Verification và nghiệm thu

Gate runner ghi lại từng mục với overall exit **0**. Mỗi stdout có command và cwd. Mã thoát 1 của fail-before F01 được xác nhận là đúng ba regression failures. Trên reviewed Neon, nhóm probe mở rộng có 17 failures và một pass. Full backend gate đầu có 26 failures vì exact class check giữ reference cũ sau registry reload. Lookup qua module hiện hành sửa lỗi này. [Gate 01](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-01/exit-codes.tsv) · [Gate 02](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/exit-codes.tsv)

| Gate | Kết quả thực chạy |
|---|---|
| Focused, gồm architecture và registry extension | 213 passed |
| Backend | 721 passed, 8 forecast skips đã có |
| Standalone simulator | 180 passed |
| Ruff lint, Ruff format, docs, OpenAPI | Pass |
| Offline F1 dataset | 55 câu hợp lệ |
| Preserved AST | 114/114, 0 undeclared differences |
| G3 independent evaluator | 8/8 cases, 6/6 mutations |
| Golden CRLF | 38/38, gồm CSV byte-identical. Hai SHA fixture và SHA archive P0 khớp. Historical base chuẩn `70d0eaf4f326b9a9317258bec44d7d71bbe60ffe`. |
| Frozen backend | 100/100, 0 problems. Non-timing KPIs, experiment fingerprints và từng run violation counters đều khớp. Tổng hard physical violations, rejected allocations và sampled over-limit minutes đều 0. |
| PostgreSQL runtime | PENDING, exit 77. Không có postgres binaries trong môi trường gate và Docker daemon không kết nối được. |

[Focused logs](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/focused-g3.stdout.txt) · [Full backend](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/backend-tests.stdout.txt) · [Simulator](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/simulator-tests.stdout.txt) · [G3 evaluator](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/g3-eval/g3-eval-summary.json) · [Golden comparator](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/golden-compare.stdout.txt) · [Frozen comparator](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/benchmark-compare.stdout.txt) · [Benchmark provenance và counters](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/benchmark-provenance.stdout.txt)

### Acceptance checklist

- [x] Atomic snapshot, lock order, known-at filtering, mutation integrity và consistent cohort.
- [x] Paired no-op equality khi chạy tuần tự, xen kẽ và lặp, với hai fork độc lập.
- [x] Live digest và DB, WS, actuator, filesystem side-effect probes.
- [x] Pending approvals, Safety Hold và unresolved hard interlock, kể cả bước cuối.
- [x] Admission khi unresolved pending, booking concurrency và outbox replay.
- [x] Fixed cohort ledger, timestamps, energy và SLA/wait censoring với hand-calculated cases.
- [x] Timeout, explicit cancellation, exception cleanup và smoke test live replan contention. Probe bổ sung xác nhận stop và safety ACK trên runtime đại diện live trong lúc sandbox giữ solver worker.
- [x] Mandatory verification và Unified Core regression trên đúng candidate.
- [ ] PostgreSQL runtime verification, tiếp tục PENDING theo G7.
- [x] Tech Lead Gate 3 approval.

[Live safety probe](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/live-safety-under-load.stdout.txt) · [PostgreSQL availability](../../eval/evidence/2026-11-24-ai4-4-2a/recovery/gate-02/postgres-runtime.stderr.txt)

### Reproduce và rollback

- Dùng baseline local ở trên, copy candidate patch sang evidence directory mới và chạy `bash eval/evidence/2026-11-24-ai4-4-2a/run_gate.sh <new-scratch> <new-evidence-dir>` từ root. Runner tạo các clone cách ly và giữ mọi kết quả ở output mới. Lượt thăm dò đầu từ workspace bị loại khỏi evidence. Workspace có cấu hình dotenv mặc định, còn các lượt chính thức chạy từ clone không có `.env` local và với `env -i`.
- Reproduce fail-before mở rộng bằng clone sạch local baseline, áp `reviewed-product.patch`, rồi copy đúng hai tệp G3 test từ candidate. Chạy `python -m pytest tests/test_services/test_counterfactual_foundation.py tests/test_services/test_g3_runtime_readiness.py -q -k 'handles_hard_safety or altered_branch or untracked_present or rollout_hard_safety or historical_charge_start or reaps_peer or cancelled_during_delivery or missing_physical_update or vehicle_safety_readback or live_store_clock'`. Kỳ vọng exit 1 và 17 lỗi trước sửa.
- Để kiểm tra rollback, dựng candidate trong cây mới và kiểm `git apply --reverse --check --include='src/**' --include='tests/**' <candidate.patch>`. Chạy rollback trên cây kiểm tra rồi dùng `reviewed-product.patch` để tái lập trạng thái Neon nếu mục tiêu chỉ là bỏ remediation. Trong workspace, Project Owner duyệt từng hunk cần rollback sau khi đối chiếu thay đổi thành viên khác. Giữ lại docs và evidence để phục vụ review.

Gate 3 được đóng sau khi Tech Lead phê duyệt và cấp quyền triển khai Gate 4.
