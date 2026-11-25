# ChargePilot SC-16 — AI-4 Master Implementation Plan

**Ngày:** 2026-11-24 | **Baseline review:** mirror `main@4f1477e84ac818549a69a74eb00e4b827fae230e` | **Trạng thái:** đề xuất Tech Lead, chờ nghiệm thu từng phase.

**Đối tượng:** Codex (Implementation Engineer). Người dùng/Tech Lead duyệt từng gate. Đây là kế hoạch triển khai, không phải báo cáo đã hoàn thành. Không tự nhận quyền thay đổi phạm vi sản phẩm.

## 0. Nguồn và quyết định phạm vi

- Research SC-16 (1).pdf, trang 7–10: WHY / WHAT-IF / HOW-TO; bảng thành phần và DecisionTrace trang 9; AI-1 phát triển trên AI-4. Trang 1–3: topology AC/DC, nguồn chung là giả định mô phỏng, optimizer/coordinator/guard xác định.
- Repo: https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/tree/4f1477e84ac818549a69a74eb00e4b827fae230e . Đọc `CLAUDE.md`, `README.md`, `docs/adr/ADR-013*`, `ADR-014*`, `ADR-015*`, `ADR-019*`, `docs/refactor/FINAL_ACCEPTANCE_REPORT.md`, `docs/refactor/FINAL_MAP.md`, `src/simulator/docs/PROJECT_STATE.md`, `docs/handoff/HANDOFF.md`, `tests/test_architecture.py`. Nếu có `AGENTS.md` trong workspace, tuân thủ cùng các hướng dẫn cấp cao hơn.
- ADR-015 hiện hoãn HOW-TO đa chiều. Scope mới giữ **HOW-TO hữu hạn, một biến / tập ứng viên nhỏ** theo thống nhất của người dùng sau research; ghi ADR bổ sung/superseding đúng phần này, không âm thầm sửa lịch sử. AI-1 chuyển backlog riêng, không phải gate AI-4. Các ADR còn ở trạng thái Proposed không được tự đánh dấu Accepted.
- **MUST:** WHY (xe, hàng đợi, giới hạn và lý do policy có bằng chứng); WHAT-IF (target SOC, deadline, site power, connector outage có thời lượng); baseline/patch delta; HOW-TO hữu hạn cho cư dân và vận hành; giao tiếp NL cả hai role; grounding, authorization, sandbox isolation; tích hợp giao diện tối thiểu.
- **SHOULD, không tự triển khai:** zone budget patch, compare policy, đối chiếu nâng cao nhiều cấu hình, hội thoại follow-up phức tạp, AI-1 negotiation/HITL. Multi-turn tối thiểu chỉ để làm rõ thông tin thiếu hoặc tham chiếu kết quả được server quản lý; không mở rộng thành agent tự lập kế hoạch không giới hạn. Không claim hỗ trợ O2/O3 trong research nếu chưa có zone budget/policy patch. HOW-TO bắt buộc cho Operator dùng site power candidates, không cần zone-budget search.
- **Ngoài phạm vi:** forecasting xe chưa đăng ký, telemetry noise/ML anomaly, learned scheduling, cross-zone migration, tối ưu toàn cục/multi-objective, OCPP/BMS thật, multi-worker/distributed infra, AI-1 apply/negotiation. Không đổi pipeline chat đặt lịch hiện hành nếu không cần thiết.
- Physical model EV2Gym AC + DC extension synthetic/proxy; không khẳng định là đường sạc VinFast đã hiệu chuẩn. Site shared supply là giả định; independent supply phải có hành vi rõ, không chuyển budget xuyên nguồn.

## 1. Workflow bắt buộc và ownership

### 1.1. Phase gate

Thứ tự đã duyệt là G0 → G1 → G2 → G3 → G4 final acceptance → G6A → G5 → G6B → G7. Mỗi lượt chỉ thực hiện phase người dùng chỉ định và dừng chờ Tech Lead ở mỗi gate. G4 remediation kết thúc tại **STOP — WAITING_FOR_TECH_LEAD_FINAL_ACCEPTANCE (GATE 4)**. Tech Lead có quyền yêu cầu patch cùng phase và review lại. Không merge main/push nếu người dùng chưa cho phép; khi được yêu cầu push, push đúng branch đã duyệt, không force-push. Không stash/reset/xóa thay đổi của người khác. Không cài deps không cần thiết hoặc đổi lockfile ngoài scope.

P0 trước hết đọc `git status --short`, `git rev-parse HEAD`, `git branch --show-current`, `git log -5 --oneline`; nếu repo local P-019 là nguồn chính, xác định commit local tương đương mirror bằng diff/hash file; không mặc định cùng hash (mirror được đồng bộ khác lịch sử). Nếu có drift, ghi báo cáo và dừng trước sửa code. Chỉ tạo branch sau khi baseline xác định, ví dụ `feature/ai-4` từ baseline được duyệt. Các phase tiếp theo tạo commit nhỏ, reviewable trên branch AI-4; có thể dùng nhánh con nếu nhóm quy định. Thành viên MVP-3.5 phát triển độc lập `feature/mvp-3.5` (tên đề xuất), không sửa frozen policy hoặc các contract chung nếu chưa phối hợp. Không tự merge branch optimizer mới trong quá trình AI-4.

### 1.2. Kiến trúc và file ownership

| Tầng | Hiện có / đề xuất |
|---|---|
| Contracts | `src/models/` (core stdlib giữ nguyên); thêm `src/models/copilot.py` cho schema API/intent/evidence |
| Core | `src/simulator/core/kernel.py`, `hybrid_station.py`, `evaluation/trace.py` — chỉnh bug có bằng chứng, không tạo engine thứ hai |
| Optimizer | `src/optimizer/{dispatch,zones,coordination,registry}.py` (registry.py là file; các nhóm còn lại là package) — MVP-3.5 sở hữu thuật toán, AI-4 chỉ yêu cầu diagnostics additive/versioned nếu thiếu |
| Integration | `src/services/runtime.py`, `control_loop.py`, `admission.py`, `experiment.py`, `solver.py` — snapshot và orchestration; đề xuất `src/services/copilot/{evidence,why,snapshot,counterfactual,recommendation,jobs}.py` (tên chỉ gợi ý, tránh tạo module rỗng) |
| Persistence | `src/services/repository.py`, `src/db/tables.py`, migrations — không ORM trong agent/model/API |
| AI layer | `src/agents/` dành AI-4/AI-1, gọi service/model; `src/llm_chat/` là chat cư dân cũ. Dùng `src/services/llm.py` provider chung, không import qua package bị cấm |
| API/UI | `src/api/copilot.py`, mount vào router hiện hành; `frontend/` dùng schema OpenAPI generate |
| Evidence | `docs/ai4/`, `eval/evidence/<date>-ai4-<phase>/`, `eval/` tests và dataset riêng |

`tests/test_architecture.py` xác nhận agents không import simulator, guard, optimizer, db, llm_chat; chỉ dispatcher được ghi live actuator. Chỉ service/adapter sandbox được phép thay trạng thái fork, chứng minh capability/identity, không mở quyền ghi live bằng cách nới AST gate. Không tạo đường gọi LLM trong Guard/control_loop. Simulator CLI standalone không phụ thuộc Pydantic/FastAPI/LLM/DB. Không có LLM trong WHY, WHAT-IF, HOW-TO deterministic services.

### 1.3. Common gate (mọi phase có code)

- TDD lỗi/edge case: test tái hiện fail trên baseline, log fail đúng nguyên nhân, sửa tối thiểu, test pass; nếu thiếu khả năng tái hiện ghi rõ risk/hypothesis. Mọi gate cần tests mới tương ứng yêu cầu phase; cấm giảm coverage/skip để pass.
- Chạy `python -m pytest tests/ -q`, `python -m pytest src/simulator/tests/ -q`, `ruff check src tests scripts/refactor eval`, `ruff format --check src tests scripts/refactor eval`, `python scripts/check_docs.py`, `python scripts/export_openapi.py --check`, `python eval/run_agent_eval.py --offline`. Dùng đúng venv repo; nếu máy Windows dùng lệnh tương đương, ghi lệnh thật. Khi thay API/schema: export OpenAPI, `npm run gen:api` trong frontend, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` (hoặc `make web-check`).
- Frozen invariants: chạy golden regression và benchmark parity nếu chạm runtime, core, trace, guard, optimizer, KPI; full gate tại P0, 4.0, 4.2A/4.2B nếu tác động core, 4.5. Phase khác dùng targeted parity + full pytest, giải thích vì sao không cần 100-run lại. Tham chiếu `scripts/refactor/run_sim_kpi_gate.py` (`run <out>`, `compare <base> <new> --evidence <dir>`), `scripts/refactor/compare_backend_benchmark.py` (đọc usage trước chạy), `eval/run_benchmark.py --seeds 1,2,3,4,5`. Benchmark script ghi `eval/results/benchmark.*`; chạy trong worktree/temp hoặc bảo toàn file có sẵn, lưu output riêng, không ghi đè frozen evidence. Không tự sửa ngưỡng, golden, policy cũ. So exact KPI non-timing theo script; latency đo riêng, sai khác phải giải thích. Trace schema mới so semantic projection v2 với golden, giữ artifact lịch sử byte-for-byte; test projection chỉ sau Tech Lead duyệt, không dùng projection che bug.
- Không yêu cầu đúng số lượng test cố định (sẽ tăng). Raw log Final Acceptance là 602 passed/8 skipped; report ghi 604/8; simulator 180 passed. P0 phải kiểm chứng và ghi số thực tế. Skips F6 forecast có thể giữ; skips mới phải được duyệt.
- Với phase không code (P0): không sửa product code, chỉ evidence/report. Với phase chưa chạy được gate bắt buộc (dependency, key, Postgres, CI), trạng thái BLOCKED, không tự tuyên bố pass.
- Tạo `docs/ai4/PHASE_<id>_REPORT.md`: baseline/HEAD, scope, file + diff tóm tắt, test fail→pass, lệnh/exit code, evidence path, kết quả regression, quyết định thiết kế, lỗi/giới hạn tồn tại, rollback, checklist AC pass/fail/not-run; `docs/ai4/PROJECT_STATE.md` cập nhật sau review hoặc ghi pending. Raw stdout/stderr, seed, scenario, resolved experiment/fingerprint, OS/Python/SciPy/EV2Gym, CPU, code commit; loại secret/JWT/PII. Evidence phải truy được tới code commit thực chạy (nếu dirty ghi diff hash; tốt nhất commit code trước rồi evidence commit riêng). Không tạo số giả, không chỉ ghi tóm tắt tự nhận.
- STOP: báo cáo `READY_FOR_REVIEW` hoặc `BLOCKED`, liệt kê commit, lệnh reproduce, điều chưa kiểm chứng; đợi **explicit APPROVED**. Không chạy phase sau, không tự gộp.

## 2. Roadmap

| Phase | Kết quả bắt buộc | Gate |
|---|---|---|
| P0 | Baseline được tái lập, issue ledger, branch/scope được duyệt | G0 |
| 4.0 | Fork/trace đúng semantics, persistence truy xuất được | G1 |
| 4.1 | WHY deterministic, evidence + auth | G2 |
| 4.2A | Snapshot/fork atomic, paired runner no-op | G3 |
| 4.2B | 4 loại patch, KPI delta, job isolation, remediation G4-F01–F03, Tech Lead final acceptance | G4 |
| 4.4A | Shared integration foundation, WHY và WHAT-IF end-to-end | G6A |
| 4.3 | Bounded recommendation search | G5 |
| 4.4B | HOW-TO end-to-end trên foundation đã có | G6B |
| 4.5 | Eval độc lập, E2E, release candidate | G7 |

Tech Lead duyệt đổi thứ tự cho demo mentor tối 25/11/2026. Sau remediation, G4 dừng chờ final acceptance. G6A cần authorization riêng từ Tech Lead sau khi review candidate G4. HOW-TO vẫn là MUST với toàn bộ requirements và acceptance criteria của G5, G6B và G7. G6 chỉ hoàn tất khi G6A và G6B đáp ứng toàn bộ AC G6.

## Phase P0 — Baseline Verification (G0)

**Mục tiêu:** xác minh đúng code hiện tại, không viết tính năng. Chốt conventions sau khi đọc repository.

1. Xác minh local/mirror, git status, diff, phiên bản runtime/deps; lập module map thực tế, các API có sẵn, architecture gates. Kiểm tra môi trường chạy bằng repo docs, không giả định cài sẵn. Chốt topology demo hiện tại 2 AC + 2 DC (4 đầu nối), 106 kW grid input theo `config/station.yaml`, 22/78 kW zone budgets output, 22/120 kW physical zone caps, conversion 0.95. Các số là config mô phỏng, không phải số đo trạm thật.
2. Chạy common regression, golden/benchmark full với seed 1–5, 5 scenarios × 4 frozen policies = 100 runs nếu manifest đúng; so baseline frozen `eval/evidence/2026-11-24-unified-core-frozen-baseline/`. Nếu khác config/seed/time, không so KPI trực tiếp. Kiểm tra raw test discrepancy 602/604, ghi số thực chạy.
3. Lập issue ledger R01–R09 theo review trước, file/line, test hiện có, expected/actual, classification confirmed/hypothesis/planned feature, owner, priority. Đọc các test admission/decision_trace/safety_event_delivery/fork_isolation. Đánh giá thêm: snapshot/read race, pending outbox, incomplete outcome, SOC revision dưới SOC thật, energy units, event knowledge, solver thread, cost accounting. Không sửa product code tại P0. Có thể tạo reproducer ngoài source hoặc lưu test draft chưa áp dụng; đánh dấu chưa chạy.
4. Lập scope ADR bổ sung dạng Proposed (HOW-TO bounded, AI-1 deferred), đề xuất file ownership và branch. Định nghĩa API ở mức design, không viết implementation. Chuẩn bị `docs/ai4/BASELINE.md`, `ISSUES.md`, report, evidence.

**G0:** đúng HEAD hoặc mapping local rõ; full regression có raw log; biết failure nào tồn tại trước AI-4; Tech Lead xác nhận issue ledger, scope. Nếu không chạy được, BLOCKED. STOP.

## Phase AI-4.0 — Foundation Hardening (G1)

**Mục tiêu:** sửa lỗi hiện có ảnh hưởng WHY/WHAT-IF. Không xây WHY/WHAT-IF API, không tuning optimizer. Các sửa dưới đây dựa trên static review 4f1477e; test tái hiện là bắt buộc.

### A. Fork/runtime parity — R01

- `src/services/runtime.py::fork_runtime`: copy độc lập `safety_hold_booking_ids` (đang copy rejected IDs nhưng thiếu hold); kiểm tra các cấu trúc mutable khác (`plan`, booking/approval models, recent commands, scheduler metadata/params, config, tariff, recorder, RNG, kernel/DC model). Chia sẻ chỉ object thực sự immutable hoặc khai báo stateless và có tests. Không copy event loop/locks/sinks live. Không copy history rồi tính KPI toàn bộ như KPI tương lai.
- Regression: live hold do acceptance/charging model fault; fork replan vẫn không cấp power/assign trái hold; fork thay set không đổi live; pending/rejected approvals, stateful optimizer, profile fallback isolation; không gửi WS, không write repository/live commands. Nếu cần deep-copy những Pydantic model hiện đang dùng chung, test cả nested fields.

### B. Trace semantics — R03/R04/R05

- `src/simulator/evaluation/trace.py::decision_record` đang hardcode guard.status=pass. `src/simulator/hybrid_station.py::decision_facts` có thể tạo record cả khi applied có hard violation. Tách pre-apply physical validation, per-command business verdict, post-apply status (pass/violation/not_evaluated/no_samples), failsafe triggered/result, giữ violation details. Không nói PASS khi zero minutes hoặc có vi phạm; fail-safe thành công không xóa vi phạm lịch sử. Giữ v2 offline compatibility/goldens bằng versioned backend adapter hoặc schema version mới, không sửa historical files.
- `control_loop._filter_held`: trả structured per-command exclusions hoặc sidecar; phân biệt PENDING_APPROVAL, REJECTED_CONSENT, SAFETY_HOLD; quy định precedence nếu nhiều lý do, giữ tất cả nếu cần. `open_trace` không được gọi tất cả là held_for_approval. Không thay behavior dispatcher chỉ để đổi trace. Test từng loại + kết hợp + emergency reduction.
- Phân biệt proposed, physically approved/consent-adjusted, dispatched, effective setpoint (old/stale/deadband), actual_output (interval avg), battery energy, grid input. `decision_facts` hiện map approved → requested trong v2; bổ sung trường chuẩn ở backend trace và ghi semantic version. Chỉ dùng dữ kiện đo; giữ source/units/time, không fabricate. Chưa đủ causal evidence thì ghi unknown. Nếu active trace chưa đóng, chỉ nói planned/command fact, không giả mạo measured actual. Kiểm tra trace ghi đúng policy tại decision time, không lấy policy mới lúc close.
- Gắn stable evidence reference: correlation_id + schema version + field path/subject + interval, không dùng text LLM sinh làm ID. Ghi fingerprint resolved config tại open, snapshot/decision versions, charging model provenance. Khi serialize JSON không cho NaN/Inf; biểu diễn unbounded/unknown tường minh, test independent supply và zero-duration.

### C. Trace persistence/retrieval — R02

- `src/config.py` mặc định decision_trace_dir rỗng; `decision_trace.persist` chỉ lưu full JSONL khi closed + configured, DB summary không đủ. Chọn **Postgres JSON payload + indexed lookup** làm mặc định MVP đề xuất (Tech Lead duyệt G0), tận dụng bảng trace hiện có bằng migration additive/hoặc bảng payload riêng; repository là đường ORM duy nhất. Nếu chọn JSONL thay thế cần durable volume, index theo correlation_id/booking/time, lifecycle/restart, không được chỉ dựa ephemeral FS. Không tạo cả hai nguồn truth cho WHY; JSONL optional export debug.
- Repository đọc trace full theo ID và window/booking, có giới hạn range/limit; support active/closed rõ, update open→closed idempotent, không ghi secrets/resident profile, ownership qua booking lookup server-side (kể cả lịch sử; deletion/ẩn danh theo chính sách). Không expose full payload raw qua resident API. Trace lỗi lưu không được làm sập safety loop, nhưng phải log/health signal và trả no_data, không silent hallucinate. Test serialization failure, write/read/restart, old summary-only record, active/closed, migration upgrade/downgrade SQLite dev và Postgres (thực nếu có; nếu thiếu Postgres ghi pending final gate).

### D. Consistency risk (R07 foundation)

- Xác minh `sync_clock` có thể step trong threadpool và `on_event` await solver; kiểm tra lock granularity, outbox, ordering safety. Không refactor lớn. Nếu có lỗi live safety/concurrency tái hiện, sửa tối thiểu; không xây snapshot engine ở phase này. Ghi yêu cầu atomic capture sang 4.2A. Không giả định asyncio.Lock bảo vệ sync thread. Giữ single-worker.

**AC G1:** tests tái hiện R01–R04 fail trước/pass sau; hold parity; trace hard violation không thể bị interpreted pass; zero actual samples trạng thái rõ; full trace read được với default config triển khai đã duyệt; old summary-only no_data; architecture/golden/benchmark parity pass; mọi thay đổi behavior có rationale và duyệt. Nếu trace change làm diff golden, nêu cụ thể và xin duyệt semantic comparator trước sửa test. STOP.

## Phase AI-4.1 — Deterministic WHY Engine (G2)

**Mục tiêu:** WHY hoạt động bằng service typed input/output trước khi gắn LLM. Không chạy counterfactual ở phase này; không claim nguyên nhân toàn cục từ binding constraint.

### Contract đề xuất

`WhyQuery`: subject scope (`own_booking`/`booking`/`station`), booking_id optional (resolve server), thời điểm hoặc interval timezone-aware, topic (`queue`, `power`, `deadline_risk`, `incident`, `policy`, `overview`); unknown topic → unsupported. `ActorContext` từ JWT/server (role + user_id), không do LLM/JSON body gán. `WhyAnswer`: status `ok|partial|no_data|forbidden|unsupported`, subject, decision_time, interval, policy/version, state_version, facts, reasons, evidence_refs, assumptions, missing_evidence. Mỗi fact có subject, time, units, source path, value. Reason có code, fact refs, evidence category (`observed`, `policy_reason`, `binding_constraint`, `inference_bound`), template deterministic; không nhận free-text reason do model sinh. Không có dữ liệu thì null/no_data, không 0.

- Evidence Resolver chọn đúng trace/booking/interval; active trace chỉ planned facts; historical closed trace có measured facts; UTC offset + timezone địa phương, khoảng [start,end), không chọn nearest ngoài window rồi gán là sự kiện thật. Reference resolver xác thực subject/time/source. Không tiết lộ booking ID khác, deadline, SOC, queue order định danh, trace raw cho resident; chỉ dữ kiện own + aggregate cần thiết. Operator station và authorized booking details, scope single site. Không để unauthorized/no-data làm oracle lộ tồn tại ID; áp dụng error convention của repo.
- WHY-queue: free compatible port, occupied/faulted, waiting/dispatch decision; nếu thiếu score/ranking log chỉ nói fact và policy, không khẳng định nguyên nhân chọn A thay B. WHY-power: proposed/approved/dispatched/actual, grid vs output vs battery, cap nguồn/vùng/tủ/cổng, taper theo model, business guard/consent/safety hold/fallback. WHY-SLA risk: distinguish `projected_shortfall` vs missed deadline observed; slack nếu có optimistic bound ghi nhãn optimistic, không bảo đảm. WHY-station: aggregate workload + bottlenecks, phân biệt policy chưa tìm được nghiệm và physically impossible (chỉ claim infeasible vật lý khi có bằng chứng/bound hợp lệ). Dynamic Slack reason codes map có kiểm thử theo policy/version; unknown policy reason → no claim. Có thể bổ sung diagnostics additive nếu cần và Tech Lead/MVP-3.5 duyệt, không tuning.
- Test fixtures độc lập: normal/no conflict, all ports occupied, DC dispatch LLF, site cap drop, cabinet/connector fault, vehicle cap/taper, held vs rejected vs safety hold, solver fallback, no trace/wrong interval, zero actual, untrusted metadata, independent supply, resident A hỏi B, cross-role. Oracle do test fixture xác định chứ không do LLM judge. Unit tests từng fact/reason và role; mutation test đổi subject/time/unit/code phải fail.

**AC G2:** WHY service chạy offline; các case bắt buộc trả đúng facts và evidence refs, no_data/partial đúng khi thiếu; zero cross-resident leakage; causal claims không vượt evidence; common gate. Chưa cần chat UI/LLM. STOP.

## Phase AI-4.2A — Counterfactual Foundation (G3)

**Mục tiêu:** một snapshot nhất quán tại T, two independent branches, runner cùng live kernel/Guard. Chưa hỗ trợ patch nghiệp vụ. Đây là hạng mục critical path.

### Snapshot và isolation

- Tạo snapshot/capture service với ownership lock rõ trên runtime. Chốt trình tự booking lock → runtime lock theo repo, đồng bộ thread-safe với `HybridStation` RLock và read consumers. Không giữ lock trong lúc rollout/solver. Xử lý outbox/pending hard violation trước capture hoặc reject snapshot `not_ready` / retry có giới hạn; không nuốt event, không step live vì chat ngoài normal clock path. Nếu version thay đổi trong capture, retry hoặc stale; không có mixed bookings/state. Viết concurrency test dùng barrier, không chỉ sleep.
- Snapshot gồm: station/booking/plan version, sim minute + timezone-aware T, ground-truth simulation physics state (dùng nội bộ sandbox), observation phù hợp optimizer, SOC/energy/counters, port faults, setpoints, queue, known bookings, pending approvals/consent/rejected/safety holds, recent commands, policy id/version/parameters/DC model/time config, tariff, announced/effective events, RNG/stateful algorithms nếu có, resolved config and hash, content digest. Không serialise lock/loop/DB/LLM clients. Không dùng `admission_fingerprint()` như digest đầy đủ; phân biệt snapshot content hash với resolved experiment fingerprint. Runtime fork có cấu trúc read-only bên ngoài, factory tạo các fork độc lập; không buộc pickle mọi object; nếu snapshot in-memory chưa portable thì ghi rõ.
- `known_at(T)`: chỉ booking đã đăng ký và event đã công bố tại T, không lấy future unannounced arrivals/faults từ benchmark truth. Dữ kiện quá khứ có thể dùng. Kiểm toán `StationKernel.fork`, queue and config filtering; simulation engine có thể dùng physics ground truth của snapshot synthetic, không đưa future ground truth tới optimizer/LLM. Giả định persistence cho chưa biết, pending approvals chưa thực thi như admission. Future recovery chỉ là giả định explicit nếu user patch. Khi không có announcement metadata, không giả vờ có; live chỉ known current + registered bookings.
- Build runner tái sử dụng `control_loop.on_minute` / `HybridStation.step` giống admission/benchmark; không gọi live `simulation_service.inject_incident` hay API mutate. Cả fork phải chạy same exogenous event schedule (materialized once), same time/horizon, same experiment fingerprint, same initial state hash; only declared patch được khác ở 4.2B. Không direct `apply_approved` bypass business rules. Tận dụng `solver.run_async` single-thread (Windows HiGHS crash đã tái hiện theo repo); không tạo solver thread pool riêng, không gọi `linprog` ngoài đường đã quy định. Cân nhắc yield/queue fairness; cap sandbox workloads, live safety priority, không giữ toàn solver thread cho full rollout, test live replan trong lúc job chạy. Nếu cần priority queue, patch nhỏ được Tech Lead duyệt; không để job starve live.
- Outcome ledger cho paired runner: cố định cohort từ snapshot known bookings + known arrivals trong horizon; giữ original arrival/deadline/target/battery/energy và initial readings; thu per-minute actual battery/output/grid energy, time target reached, plug-in/charge start/release, faults, hard violations, per-vehicle terminal status. Không dựa duy nhất `HybridStation.outcomes()` (bỏ NOT_ARRIVED, plug_in_time đang dùng charge_started và completed có thể clamp delivered); bổ sung evaluator additive, không đổi frozen KPI. Phân biệt plug wait và first charging wait, unserved, incomplete horizon, already departed. Chốt metric definitions cùng Tech Lead; tránh double count energy trước snapshot, sum grid conversion một lần. Existing compute_kpis có feasible filtering/empty cohort=1.0 và p90; không đổi baseline; AI-4 báo denominator/censored, empty null, p95 nếu có định nghĩa rõ. No-op compare exact non-timing metrics, trace random IDs/latency không bắt buộc byte-identical.

**AC G3:** baseline/no-op patched equality; same snapshot hash, same cohort/event inputs; 2 forks có kết quả độc lập dù chạy xen kẽ/lặp; live before/after digest unchanged trong controlled paused-clock fixture, DB/WS/filesystem unchanged; pending approvals/hold parity; known_at excludes hidden event; snapshot concurrency test; timeout/cancel leaves no live mutation; regression and provenance evidence. Nếu không đạt, không viết patch. STOP.

## Phase AI-4.2B — WHAT-IF Engine (G4)

**Mục tiêu:** chạy paired experiment thực trên foundation G3, 4 nhóm patch MUST. Không LLM/automatic apply.

### Typed patch contract

Discriminated union, `extra=forbid`, strict units/validations, actor auth server side; đề xuất ADR-014 canonical op names `revise_vehicle` (target_soc and/or deadline), `site_limit`, `outage` (connector_id, start/duration). Tên trước đây `change_target_soc`/`change_deadline` chỉ là semantics, không tạo hai bộ API. MVP một operation/lần (tối đa hai trường trong revise_vehicle nếu rõ và được duyệt); ADR cho phép tối đa 5 là upper bound không phải bắt buộc. Giới hạn horizon (đề xuất ≤24 giờ kể từ T, configurable), patch count, duration và numeric bounds. Pydantic revalidation sau patch, không `model_copy(update=...)` bỏ validation. LLM không cung cấp role, internal hash, arbitrary policy params, executable code.

| Op | Actor | Semantics / acceptance |
|---|---|---|
| revise_vehicle.target_soc | Resident own booking; Operator chỉ nếu quyền được duyệt | 0..100%; xác minh SOC thực tại T, target đã đạt → already_satisfied, không reset pin, không giả lập charge ngược; reject nếu trạng thái không hợp lệ. Nếu target giảm dưới SOC thật, xử lý explicit immediate attainment hoặc reject với lý do; giữ actual SOC và original commitment. Kiểm tra `_update_present` khi FINISHED/CHARGING, recompute energy basis đúng; không reset accumulated kWh/arrival/counter; không thay max_kw/zone ngoài patch. |
| revise_vehicle.deadline | như trên | Timezone-aware, sau T/arrival và nằm trên lưới phút tính từ snapshot T. Deadline explicit lệch lưới trả typed validation error. Target-only giữ deadline gốc và cách tính phút rời của live booking. Deadline chỉ đổi trong sandbox. Sạc xong và rút cổng là hai sự kiện riêng. |
| site_limit | Operator | Grid input kW dương, hữu hạn, trong power envelope, dùng shared supply. Tăng trên configured limit cần explicit hypothetical infrastructure. Patch thay runtime supply premise tại T và đặt trần cho các regime sau. Giữ announced source và cabinet schedule, kể cả sự kiện có hiệu lực tại T, cùng các trần thiết bị. |
| outage | Operator | connector fault tại T hoặc future time explicit, restore sau duration; reject ID lạ/cross-site, invalid interval, already faulted restoration không tự khôi phục fault trước đó; preserve event ordering. Cả cabinet là separate scope optional, không nhầm một đầu nối là cả tủ. |

### Result contract / metrics

`WhatIfResult`: `status`, `snapshot_id`, `snapshot_time`, `state_version`, baseline/patched run IDs, canonical patch, resolved experiment fingerprint + branch config/patch hashes, event manifest/hash, common horizon & cohort counts, baseline/patch KPI & delta, affected vehicles (authorized projection), assumptions, hard violation counters, guard/approval dependencies, `applied: Literal[False]`, `hypothetical_infrastructure`, truncation/error fields. Delta = patched − baseline, explicit sign/units. Report AC/DC/overall on-time with denominators, service coverage, unmet battery energy (and output/grid distinctly), time to target, wait metric definition and censored counts, future energy cost (VND) and peak grid input, safety counters; all same horizon. For revised vehicle: report evaluation against ORIGINAL target and deadline as well as revised target/deadline, original target not reached because revised charging stopped is valid original miss; no denominator gaming. Incomplete original deadline outside horizon → unknown/censored, not pass/fail artificially; no unconditional SLA promise. Existing `SessionOutcome` and compute_kpis can be reused where semantics fit; do not overwrite historical definitions.

- Rate, mean và p90 có delta khi hai nhánh chạy an toàn hết cùng horizon và dùng đúng cùng tập booking cho KPI đó. Giữ branch-local aggregates và counts. Khi delta metric là null, `delta_reasons` phân biệt `non_comparable_sample` và `missing_data`, không chứa booking IDs. `unmet_original_battery_kwh` và charger-output equivalent đo phần năng lượng còn thiếu để đạt target gốc tại observation cutoff.
- Job execution service for WHAT-IF/HOW-TO (per ADR-014), bounded queue, max candidate count/horizon, job ownership and TTL, timeout/cancel with safe checkpoints between solver tasks, statuses queued/running/succeeded/failed/cancelled/expired. In-process single worker acceptable for MVP; no durable jobs promise. Solver native call may not cancel immediately; mark cancellation accurately, stop subsequent simulation, never report applied. No unbounded background tasks, no thread-per-candidate. Expose service internally; REST contract in 4.4. Baseline simulation once per search job later, not repeated unnecessarily.
- Tests: patch exactness, no-op, same snapshot, SOC reduced/increased, target already met, earlier/later deadline, AC/DC, reserved not arrived, site reduction/increase & independent, connector fault+restore timing and invalid IDs, outage at horizon boundary, pre-existing fault, safety hold/pending approvals, infeasible and horizon censored, no known arrivals, impossible infrastructure, invalid patch/unknown fields, cross-user access/job results, no live state/DB/WS writes. Assertions on branch deltas and manually calculable small fixtures (not only snapshot equality). Verify energy accounting across repeated runs. Store raw run evidence; benchmark WHAT-IF latency separately from LP solver.

**AC G4:** all 4 operations pass deterministic cases and authorization; original/revised commitments reported; physical hard constraints remain enforced (if violation occurs mark unsafe, no recommended feasible); strict incident application, no swallowed errors; sandbox applied=false everywhere including failures; repeated/no-op results deterministic within declared numeric tolerance; common gates. STOP.

## Phase AI-4.3 — HOW-TO Engine (G5)

**Mục tiêu:** bounded candidate search tái dùng WHAT-IF; không sửa optimizer, không claim global optimum. Hoạt động trước LLM. Một biến tìm kiếm mỗi goal; candidate generation deterministic; baseline once from G3 snapshot; all evaluated branches same cohort/known events/horizon/config except patch.

**Must goals:**

- Resident `max_soc_by_deadline`: giữ departure time mong muốn, thử target SOC candidates (explicit user bounds, current SOC, original target; grid bước đề xuất 5 điểm % + boundaries, có cap). Chọn target cao nhất trong tập đã thử, original SLA reporting. Nếu deadline mới khác, giữ cố định deadline đó cho toàn candidate set; đây là goal với một biến search, không phải search hai chiều.
- Resident `earliest_completion_for_target`: giữ target, thử deadline candidates trong time window, xếp hạng thời điểm đạt target thực theo simulation, không dùng deadline làm proxy; nếu chỉ một run chứng minh đạt sớm hơn có thể report như evidence, không coi đổi deadline luôn cải thiện. Phân biệt charge completion vs unplug/release. Nếu horizon không đủ, no conclusion.
- Operator `min_tested_site_limit_for_sla`: giữ yêu cầu gốc toàn cohort, thử site input limits trong bounds, chọn mức thấp nhất trong candidates đạt mục tiêu và không vi phạm Guard. Nguồn vượt installed chỉ explicit hypothetical infrastructure, không khuyến nghị vận hành thật; independent supply unsupported. Không yêu cầu 100% nếu physically infeasible; không bịa alternative. Optional no-worsening AC constraint áp trên từng booking originally on time, không chỉ aggregate.

**Search contract:** `RecommendationGoal` (goal enum, typed constraints, explicit allowed sacrifices/bounds), `CandidateSet` deterministic and versioned, `RecommendationResult` (snapshot ID, baseline, tried candidate values/count, completed/skipped/failed, feasibility per candidate, evidence/whatif run IDs, chosen option(s), objective ranking tie-break, assumptions, search_status `found|no_feasible_in_tested_set|partial|unsupported`, applied=false). Default cap đề xuất 8 candidates + 1 baseline, configurable hard cap (duyệt G0), timeout đo thật; nếu truncated/failed chỉ kết luận trên candidates evaluated; không tuyên bố không có nghiệm toàn cục. No LLM candidate creation/ranking at this phase. Candidate search không dùng binary search khi chưa chứng minh monotonic. Hard constraints/consent/policy violation: không recommend unsafe/unknown; pending approvals label conditional, không coi verified unconditional. Tie-break stable, user preference explicit; không âm thầm đánh đổi target/deadline hoặc chọn chi phí thấp khi SLA gốc bị hy sinh trái yêu cầu. Return up to 3 options nếu có; report all attempted values trong evidence. HOW-TO chỉ advisory, không thay booking.

**Tests:** non-monotonic synthetic oracle, actual sandbox fixtures, exhaustive enumeration within candidate set, no feasible, ties, unknown candidate/timeout partial, zero capacity gain due connector bottleneck, high-power hypothetical, AC no-worsening per-booking, exact target/deadline bounds, active holds, safety errors, cross-role rejection, same snapshot reuse, live no mutation. Negative example: target revision makes revised SLA improve but original fails; verify both displayed. Test candidate budget/latency separately. Không đưa zone-budget/policy search vào scope trước approval.

**AC G5:** 3 goals có ít nhất một positive và negative actual simulator case; chosen best among tested feasible set according to declared ranking; all recommended options reproducible and safe within assumptions; no global optimum wording, no write; latency/candidate count logged; common gate. STOP.

## Phase AI-4.4 — LLM Decision Copilot (G6)

**Mục tiêu:** người dùng hai role hỏi bằng ngôn ngữ tự nhiên và nhận kết quả grounded từ service đã nghiệm thu. Không viết một agent tự điều phối sạc. Không gọi LLM trong loop vật lý, không đưa raw internal trace chứa dữ liệu ngoài quyền vào model context.

### G6A — AI-4.4A · Shared foundation, WHY và WHAT-IF

- Đưa WHY và WHAT-IF qua NL, structured fallback, API và UI ở hai role. Kiểm grounded claims, authorization, job lifecycle, lỗi và isolation end-to-end. Report và dừng review G6A riêng.
- Giữ `CopilotIntent` cho `why`, `what_if`, `how_to`, `clarify` và `unsupported`. HOW-TO giữ handler riêng trả `feature_not_available` cho đến khi có engine được tích hợp. Recommendations chỉ lấy từ engine deterministic sau G5. Router typed và deterministic với handler boundaries rõ, `ActorContext` và quyền do server xác định.
- API response và job envelopes có result type và job kind rõ ràng. WHAT-IF và HOW-TO dùng chung workload bounds và solver single-worker. Giữ thay đổi vào `WhatIfJobs` trong phạm vi cần thiết cho tích hợp.
- Giữ deterministic engine độc lập với HTTP, LLM và UI. Handoff phải giữ khả năng G5 tái sử dụng một baseline trong bounded candidate search và dùng chung semantics announced-event replay. Grounding contract có thể nhận HOW-TO evidence và candidate results khi có engine.
- Demo dùng dữ liệu và kết quả thực từ deterministic services. Giữ đầy đủ safety, authorization, grounding và sandbox isolation. Mọi kết quả là advisory, `applied=false`. API apply và tự sửa live booking nằm ngoài phạm vi.

### G6B — AI-4.4B · HOW-TO integration

Sau khi G5 được nghiệm thu và G6B được cấp phép, nối HOW-TO đã duyệt vào router, typed jobs, grounding, API và UI. Chạy E2E cả hai role, kiểm candidates và grounding evidence, cùng toàn bộ AC G6 dưới đây. G7 vẫn giữ đầy đủ AC release.

### A. Intent và routing

- `src/agents/` chứa AI-4, provider chung `src/services/llm.py`; giữ `src/llm_chat/` và resident booking flow hiện có. Dùng structured output (Pydantic schema) cho `CopilotIntent`: `why|what_if|how_to|clarify|unsupported`, query/patch/goal tương ứng, không dùng arbitrary tool name. LLM chỉ parse subject alias/thời điểm/đơn vị/giá trị và mục tiêu; server resolve booking/connector từ catalog/context đã auth. Không cho model gán role/owner/snapshot ID/authorization hoặc chọn code thực thi. Dùng timezone station, resolve giờ tương đối từ server clock, không đoán AM/PM/đơn vị/xe không rõ. Trích xuất nhiều điều kiện trong phạm vi whitelist; nếu vượt support, trả unsupported/clarify, không tự bỏ điều kiện.
- Deterministic router validate schema, authorize trước retrieval/rollout và gọi workflow bounded tương ứng. WHAT-IF dùng jobs 4.2B, HOW-TO dùng cùng workload bounds và single-worker solver khi tích hợp ở G6B. LLM timeout/budget/retry theo cấu hình chung; không chạy ReAct loop tùy ý, không cho LLM gọi arbitrary SQL, Python, URLs hay simulator mutator. Tách parse LLM latency khỏi simulation và final rendering. Mock/fixture mode và structured API/form deterministic fallback khi LLM unavailable; không coi mock là eval LLM thật.
- Hội thoại tối thiểu: hỏi lại trường thiếu, cho phép follow-up tham chiếu kết quả theo ID do server phát và kiểm ownership/TTL; lưu context ngắn đã redact. Không đọc raw system prompts hoặc hidden state. Không tự thực hiện AI-1. Test Việt/Anh (tiếng Việt trọng tâm), typo, relative dates, mơ hồ, injection qua user text/metadata, query nhiều mục tiêu unsupported, model output invalid. Intent handler server-only tests (LLM mock trả role operator vẫn không được escalate).

### B. Grounded explanation

- LLM chỉ nhận structured evidence đã lọc theo role, assumptions, tried candidates, results. Dùng output schema gồm `claims` (claim type, subject, value, unit, time, evidence_refs), explanation/summary theo template hoặc constrained rendering. Mọi câu có số liệu, causal claim, trade-off phải gắn evidence ID. `GroundingGate` xác thực exact fact value hoặc rounding do code quy định, đơn vị, đối tượng, thời điểm, stage, delta direction, reason-code semantics, evidence existence, role. Không chỉ check một con số xuất hiện ở đâu đó trong trace. Free-text prose không được tạo đường bypass: đề xuất dựng câu định lượng/nhân quả từ verified claim objects bằng template; LLM sinh phần ngôn ngữ không factual mới hoặc phải verify được. Nếu không qua, deterministic fallback/no_data; không gửi partial unverified claim. Explicitly label simulated/conditional/hypothetical/partial, no guarantee, applied=false. Không cho model hứa thời điểm sạc chắc chắn.
- Resident không thấy IDs hoặc trạng thái chi tiết xe khác qua claim, job status, logs, error response, history hoặc prompt. Operator có thể xem detail trong scope station. Prompt injection trong booking labels/evidence xử lý như untrusted data. Tests đối kháng: đúng số sai xe, đúng số sai phút, đúng số sai đơn vị, sai stage power, đảo dấu delta, gán causal reason không có, evidence ref giả, unauthorized lookup, model tự chèn câu ở free-text, missing provenance, failed simulation. Tất cả phải block/fallback.

### C. API và UI tối thiểu

- Đề xuất API `/api/v1/copilot/query` cho NL, `/api/v1/copilot/why` typed offline, `/api/v1/copilot/what-if`, `/api/v1/copilot/how-to` tạo job typed; `GET /api/v1/copilot/jobs/{job_id}`, optional cancellation nếu đã support; dùng router prefix chuẩn repo (xác minh trước code). Dùng JWT actor/deps hiện có cho hai role, server-side ownership, rate limit/bounded queue. Long operations trả 202/job ID; frontend poll có backoff, show progress/error/stale/expired; không expose raw stack. Không route nào có apply/booking mutation. Status codes tương thích repo DomainError, OpenAPI regenerated. API design được duyệt ở G0, tên ở đây là đề xuất, không tự tạo endpoint trùng.
- Giao diện tối thiểu ở resident/operator hiện có (owner frontend phối hợp, không thay toàn UI): input NL, ví dụ câu hỏi, clarify/fallback, WHY facts + reason + evidence/time; WHAT-IF baseline vs patch table, KPI delta, assumptions và nhãn chỉ mô phỏng; HOW-TO hiển thị candidates checked, lựa chọn, trade-off/no feasible/partial. Không có nút Apply; AI-1 sau. Resident only own + aggregate; Operator có affected IDs theo quyền. Không hardcode KPI/mock result production. Reuse typed OpenAPI client, loading/error/offline handling. Giữ các luồng booking, approval và simulation dashboard hiện tại chạy bình thường.

**AC G6:** real service + mocked LLM E2E ở cả hai role; 3 intent, clarification, offline fallback, WHAT-IF/HOW-TO job lifecycle, grounded claim gate và auth adversarial suite pass; no live mutations; frontend tests + build, schema generation + API contract pass. Nếu có key, chạy smoke LLM thật nhỏ và record cost/latency, nhưng full eval ở 4.5. Không có key không claim LLM integration passed thật; ghi pending. STOP.

## Phase AI-4.5 — Evaluation & Integration (G7)

**Mục tiêu:** nghiệm thu MVP-4 AI-4 đúng scope; không thêm feature. Gắn evidence thật cho pitching và handoff; không merge optimizer version mới nếu chưa được duyệt.

### 1. Bộ đánh giá độc lập

- Tạo eval AI-4 riêng (`eval/datasets/copilot_cases.jsonl`, `eval/run_copilot_eval.py` là tên đề xuất); không tái sử dụng eval F1 như bằng chứng AI-4. Dataset đề xuất ≥60 câu tiếng Việt có nhãn: 20 WHY, 20 WHAT-IF, 20 HOW-TO; thêm negative/ambiguous/unauthorized/injection suite riêng. Có cả Resident/Operator, normal/no conflict, scarcity, queue, site drop, outage, independent supply, held commands, stale/unknown trace, infeasible, partial horizon, typo/relative date và compound constraints. Nhãn do người review/fixture oracle độc lập; test prompts không chứa expected answers. Tách dev/held-out; không sửa nhãn/threshold khi kết quả xấu; lưu model/version, temperature, prompt hash, run metadata, latency, tokens/cost nếu có, raw outputs đã redact.
- Đánh giá deterministic offline trước: exact intent/patch fixture, reference oracle, numerical reconciliation, per-vehicle SLA/original commitments, no-op, repeated paired comparison, all recommendations feasible, safety/authorization/isolation. LLM thật sau: parse accuracy, grounding claim-level, causal correctness, refusal/clarification recall, task completion, latency/cost. Offline eval chỉ xác nhận deterministic path, không xác nhận chất lượng LLM thật.
- Ngưỡng đề xuất để Tech Lead chốt trước run held-out (không phải kết quả đã đạt): intent ≥95%; patch exact accuracy ≥95% (đối tượng/giá trị/đơn vị/thời điểm); factual faithfulness ≥95% theo raw model claims và report thêm delivered answer; causal correctness ≥95% ở cases answerable, báo riêng abstention/coverage để không đạt điểm bằng từ chối tất cả; unsupported numeric claims sau gate = 0; unauthorized leakage = 0; sandbox mutation = 0; accepted recommendations có simulator evidence + hard safety checks 100%; invalid patch execution = 0. Báo count/denominator, misses, confidence nếu phù hợp; sample nhỏ không claim thống kê mạnh. Không tự bỏ cases fail khỏi mẫu.
- AI value: so (A) dashboard manual WHAT-IF, (B) LLM no tools trên cùng authorized state, (C) full Copilot; thêm (D) structured deterministic form+same search/evidence services nếu đủ thời gian để cô lập đóng góp NL/LLM khỏi solver. Cùng task/fixture, mục tiêu và rubric, không cấp future truth cho bất kỳ hệ thống nào. Đo task success, time-to-answer, số bước thao tác, correct evidence, trade-off comprehension; human study nhỏ nếu có người tham gia (ghi cỡ mẫu và hạn chế). Nếu không có người dùng thật chỉ báo scripted proxy, không bịa feedback. Đừng chỉ chứng minh optimizer tốt hơn; AI-4 không tuning policy.

### 2. Integration & release checks

- Full backend + standalone test suites; regression golden 38/38 theo evidence nếu baseline xác nhận; frozen backend 100 runs same config; kiểm tra non-timing KPIs không drift. Test architecture và mutation/safety. Latency tách replan/solver, snapshot, rollout WHAT-IF, full bounded HOW-TO, queue delay, LLM parse/finalize, end-to-end; p95 replan ≤2s là target đã có, không áp nhầm lên LLM/rollout. Báo phân phối/case count và timeout; đề xuất target Copilot riêng sau đo P0/4.2B, không tự đặt số đạt. Live replan vẫn hoạt động khi Copilot job chạy. 4-port topology demo hiện tại không được trình bày thành 8/100-port benchmark; muốn đo 8/100 phải tạo config và evidence riêng.
- Postgres thật: migrations upgrade, persistence/open→close/history retrieval, restart; lỗi DB/LLM không làm live loop hỏng. Render hoặc môi trường deploy thực: health, single worker, secrets/env, auth cả hai role, OpenAPI/frontend, LLM real call, job/queue lifecycle, smoke 3 intents; không claim deployment nếu chưa chạy. Nếu unavailable → BLOCKED phần release, vẫn có thể ghi core PASS riêng và list missing gate; không tự đóng release.
- End-to-end demo tối thiểu: (1) resident queue WHY; (2) operator WHY power drop có binding + missing evidence handling; (3) resident SOC/deadline WHAT-IF với original/revised SLA; (4) operator connector outage 30 phút và site limit delta; (5) resident HOW-TO max SOC by early deadline; (6) operator min tested site limit, negative bottleneck; (7) forbidden/injection; (8) LLM unavailable fallback. Dùng fixture tái lập, actual results; no AI-1 apply. Nhãn giả định/provenance visible.
- Tài liệu: README/architecture/ADR scope cập nhật đúng code đã chạy; module map, API examples, config/env, limitations (synthetic taper, shared-supply hypothesis, known arrivals, one worker, persistence retention, advisory only), demo script, benchmark report/raw data, AI-1 handoff (future consumption of recommendations, consent/reverify separately). Cập nhật `docs/ai4/PROJECT_STATE.md` và `docs/handoff/HANDOFF.md` không đánh dấu approved trước review.

**AC G7:** tất cả MUST use cases hoạt động cả hai role đúng authorization, no unsafe/ungrounded delivered claims, no live writes, benchmarks reproducible, real provider/DB/deploy evidence đầy đủ hoặc release explicitly BLOCKED, Tech Lead xác nhận và người dùng quyết định merge/tag. STOP. Không triển khai AI-1.

## 3. Review checklist gửi Tech Lead ở mọi gate

```text
Phase: <id> | Status: READY_FOR_REVIEW / BLOCKED
Base commit: ... | Code commit: ... | Evidence commit: ...
Branch: ... | Working tree: clean / details
Scope completed / intentionally not done:
Files changed + rationale:
Tests added (fail-before/pass-after where relevant):
Raw commands / exit codes / evidence paths:
Golden + benchmark parity (or rationale not rerun):
Security / safety / isolation assertions:
Architecture boundaries and schema compatibility:
Known issues / assumptions / skipped or not-run tests:
Decisions requiring Tech Lead approval:
Rollback plan:
STOP — WAITING_FOR_TECH_LEAD_REVIEW
```

Tech Lead kiểm diff base..HEAD, code paths thực, test independence, negative/edge cases, provenance, docs vs behavior, và regression. Nếu phát hiện lỗi: sửa trong phase hiện tại, thêm reproducer, rerun affected gate, gửi commit mới. Không chấp nhận chỉ ghi 'all tests pass' nếu không có raw evidence.

## 4. Dependency and scope matrix

| MUST | Implemented | Tested / reviewed |
|---|---|---|
| Foundation fixes R01–R04 | 4.0 | G1 |
| Trace evidence semantics R05 | 4.0/4.1 | G1–G2 |
| WHY resident/operator | 4.1 | G2, G6A, G7 |
| Snapshot consistency R07 | 4.2A | G3 |
| WHAT-IF target SOC/deadline/site/outage + delta R06 | 4.2B | G4, G6A, G7 |
| HOW-TO bounded resident/operator | 4.3 | G5, G6B, G7 |
| NL, grounding, permissions, UI | 4.4A và 4.4B | G6A, G6B, G7 |
| Postgres / LLM real / deploy R08 | 4.5 | G7 |
| Optimizer research R09 | MVP-3.5 (separate) | not a gate AI-4 |

## 5. Prompt khởi động (copy vào Codex)

> Bạn là Implementation Engineer của ChargePilot SC-16. Đọc toàn bộ `docs/ai4/AI-4_MASTER_IMPLEMENTATION_PLAN.md` (hoặc file plan tôi đính kèm), RESEARCH SC-16 nếu có trong workspace, repo instructions và các ADR được liệt kê. Baseline review mirror là `main@4f1477e84ac818549a69a74eb00e4b827fae230e`; xác minh local source of truth trước khi làm, không mặc định local commit hash trùng mirror. **Chỉ thực hiện Phase P0 — Baseline Verification.** Không sửa product code, không tự bắt đầu AI-4.0, không tuning optimizer, không ghi đè evidence frozen, không tự merge/push. Chạy các kiểm tra thực tế theo plan, lập issue ledger R01–R09 và Proposed ADR scope, lưu raw logs/provenance, báo mọi blocker trung thực. Kết thúc bằng report có base/HEAD, lệnh reproduce, acceptance checklist và `STOP — WAITING_FOR_TECH_LEAD_REVIEW`. Chờ tôi phê duyệt rõ ràng trước khi bắt đầu phase kế tiếp.

Prompt cho các phase sau (chỉ gửi sau approval):

> Tech Lead đã duyệt gate <Gx> tại commit <sha>. Chỉ triển khai phase <phase-id> theo master plan, bắt đầu bằng xác minh HEAD và report trước đó. Không làm phase sau, không thêm feature ngoài scope. TDD lỗi và edge cases, giữ frozen invariants, thực hiện common gate, lưu evidence, gửi report và dừng chờ review. Nếu phát hiện conflict/semantic change cần quyết định, ghi BLOCKED và đề xuất phương án, không tự sửa contract ngoài quyền.

## 6. Quyết định đề xuất cần Tech Lead xác nhận tại G0

- Dùng Postgres JSON payload + indexed lookup cho detailed trace; JSONL chỉ optional debug/export.
- Tên package/file/API minh họa, canonical patch names `revise_vehicle/site_limit/outage`, giới hạn horizon mặc định 24h, cap 8 candidates + 1 baseline, mục tiêu eval; điều chỉnh sau kiểm tra thực tế, không biến thành claim đã có.
- HOW-TO hữu hạn là MUST mới; AI-1 deferred; zone budget/policy comparison vẫn SHOULD. Các use case phụ thuộc zone budget hoặc cross-zone chưa được claim hoàn thành trong MVP.
- Job in-process single worker; snapshot capture cần review locking; baseline KPI không đổi, evaluator AI-4 additive. Cần thống nhất metric definition và authorization cho Operator sửa hypothetical booking (không áp thật).

**Giới hạn của plan:** dựa trên static review tại commit nêu trên và tài liệu/evidence lưu trong repo, không phải kết quả chạy lại độc lập. Không có sửa code hay commit nào do Tech Lead thực hiện trong lượt lập plan. Codex phải xác minh từng giả thuyết và báo kết quả tại gate trước khi chấp nhận.
