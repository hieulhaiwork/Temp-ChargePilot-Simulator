# AI-4 — Issue ledger P0

Nguồn R01–R09 là Master Plan. Nguồn R10/R11 là G0 review. Dòng trỏ source trong kết quả P0 theo code tại baseline `ce23136`. Ưu tiên và owner dưới đây là đề xuất để Tech Lead duyệt. Probe chạy trên HEAD baseline với fixture tổng hợp, qua runtime và Guard hiện có. Exit 0 của probe nghĩa là quan sát kỳ vọng về **hành vi baseline** đã tái hiện. [Lệnh và quan sát](../../eval/evidence/2026-11-24-ai4-p0/raw/issue-probe-final.stdout.txt)

| ID / phân loại | Kỳ vọng và kết quả tại baseline | Code và coverage hiện có | Owner / ưu tiên |
|---|---|---|---|
| **R01 · Confirmed** — mất safety hold trong fork | Fork phải bảo toàn safety hold độc lập. Probe tạo `charging_model` violation, fail-safe giữ `dc-a` ở 0 kW. Fork mất hold và replan cấp lại 33 kW. Live vẫn 0 kW. | [fork_runtime](../../src/services/runtime.py#L435) copy rejected IDs, dùng chung plan/config/tariff và tham chiếu booking/approval DTO. [Backend fork test](../../tests/test_services/test_fork_isolation.py) kiểm stateful optimizer. [Simulator fork test](../../src/simulator/tests/test_fork_isolation.py) kiểm RNG, stateful DC/fallback và recorder. Chưa xác minh mọi DTO lồng nhau hoặc assignment cho xe đang hold. | Runtime/Admission · **P0** · G1 |
| **R02 · Confirmed** — default persistence thiếu full payload | WHY cần full trace truy xuất bền vững theo ID/booking/time. Probe chạy migrations và đóng/mở lại SQLite repository. Summary còn, `artifact=None` và không có fields decision/applied. Default `decision_trace_dir=""`. | [persist](../../src/services/decision_trace.py#L232), [repository](../../src/services/repository.py#L312), [trace test](../../tests/test_services/test_decision_trace.py#L125) kiểm summary và JSONL khi có cấu hình. Full retrieval trên Postgres thuộc quyết định G0/G1. | Persistence/Backend · **G1 blocker** |
| **R03 · Confirmed** — Guard status thiếu post-apply semantics | Hard violation và zero samples cần trạng thái riêng. Probe thấy v2 `guard.status=pass` cùng hard violation `charging_model` ở trace có 2 phút thực thi. Một trace đóng ở 0 phút vẫn gắn `pass` và giữ interval dự kiến 15 phút. Outer `applied` vẫn ghi violation và lý do. | [decision_record](../../src/simulator/evaluation/trace.py#L191), [decision_facts](../../src/simulator/hybrid_station.py#L516), [close_open](../../src/services/decision_trace.py#L177). [Safety test](../../tests/test_services/test_safety_event_delivery.py#L307) kiểm fail-safe và violation details. [Trace test](../../tests/test_services/test_decision_trace.py#L114) kiểm zero violation của fixture bình thường. | Trace/Physical Core · **G1 blocker** |
| **R04 · Confirmed** — nhãn hold sai | Cần ghi pending approval, rejected consent và safety hold riêng. Probe thấy `dc-a` nằm trong `held_for_pending_approval` dù pending approvals bằng 0 và booking nằm trong safety hold. Nhánh rejected consent có cùng đường gộp theo code. | [caller](../../src/services/control_loop.py#L117), [filter](../../src/services/control_loop.py#L458), [trace field](../../src/services/decision_trace.py#L117). [Admission tests](../../tests/test_services/test_admission.py) kiểm ước tính có điều kiện khi pending approval. Nhánh rejected và precedence kết hợp chưa có probe riêng. | Guard/Trace · **P1** · G1 |
| **R05 · Confirmed gap** — stage và provenance chưa đủ | WHY cần phân biệt proposed, approved, dispatched, effective và actual đo được. Probe ghi approved 11 kW dưới label nested `requested_output_kw`, trong khi `actual_output_kw=0` với 0 phút đo. Trace có outer proposed/approved, command rows và actual energy rollup. Nested v2 lấy algorithm labels lúc đóng, chưa kiểm chứng drift khi đổi policy giữa hai lần đóng/mở. | [Open trace](../../src/services/decision_trace.py#L82), [decision_facts](../../src/simulator/hybrid_station.py#L516), [trace tests](../../tests/test_services/test_decision_trace.py) kiểm schema, correlation, replay, JSON và output energy. Evidence refs ổn định và fingerprint tại decision time là phần thiết kế. | Trace/Evidence · **P1** · G1–G2 |
| **R06 · Planned feature** — paired WHAT-IF | Cần 4 thao tác typed, cùng snapshot/cohort/horizon, original/revised SLA và delta. Có quote trên fork, batch simulation và API inject sự cố mô phỏng theo đường live operator. Chưa có paired Copilot API. | [Admission](../../src/services/admission.py#L62), [simulation router](../../src/api/simulation.py), [admission tests](../../tests/test_services/test_admission.py). Các test hiện tại không bao phủ whitelist/job/delta của Copilot. | Copilot Services · **P1** · G3–G4 |
| **R07 · Confirmed race** — đường đọc. Snapshot vẫn là hypothesis | Cần snapshot atomic qua booking, runtime, state, outbox. `sync_clock` đến từ threadpool có thể step simulator ngoài `rt.lock` của asyncio. `HybridStation` có RLock cho từng method. `on_event` giữ asyncio lock và await solver. `fork_runtime` chụp trạm, approvals và plan ở các bước riêng. Barrier tests G1 tái hiện read thứ hai bước qua phút vi phạm trước fail-safe và read dời mốc vật lý khi solver đang chờ. Atomic full snapshot và tính nhất quán liên store vẫn thuộc G3. | [sync_clock/outbox](../../src/services/runtime.py#L138), [on_event](../../src/services/control_loop.py#L66), [RLock wrapper](../../src/simulator/hybrid_station.py#L71), [safety delivery tests](../../tests/test_services/test_safety_event_delivery.py#L128), [admission consistency tests](../../tests/test_services/test_admission_consistency.py). Có regression delivery/dedup và optimistic booking. Cần barrier test cho snapshot và pending hard violation. | Runtime/Safety · **P1** · G1/G3 |
| **R08 · Not run / verification gap** — Postgres thật, LLM thật, deploy | CI có repository job Postgres. P0 dùng SQLite tạm và eval F1 offline. Postgres thật, provider thật, Render sau refactor chưa xác minh trong lượt này. | [CI](../../.github/workflows/ci.yml#L109), [Handoff](../handoff/HANDOFF.md#L7), [Offline eval](../../eval/run_agent_eval.py#L144). | Integration/Ops · **P1** · G7 |
| **R09 · Planned research** — optimizer MVP-3.5 | Giữ policy registry v1 đóng băng cho AI-4. Noise, robust scheduling và trade-off Dynamic Slack thuộc MVP-3.5. `Candidate.allowed_kw` dựa trên SOC thật theo Physical Guard, cần ghi rõ khi đánh giá observation-aware. | [Registry](../../src/optimizer/registry.py), [observation tests](../../src/simulator/tests/test_observation_layers.py), [simulator state](../../src/simulator/docs/PROJECT_STATE.md). | MVP-3.5 · Ngoài G0/G1–G7 |

| **R10 · Confirmed contract gap** — energy/cost | Contract phân biệt grid input kWh, charger output kWh và battery stored kWh. Admission quote hiện nhân output kWh với tariff, benchmark cost dùng grid input kWh. Station electricity cost dùng grid input và TOU, tách khỏi resident service bill. Thay semantics quote/billing hiện hành cần Tech Lead duyệt. | [Kernel](../../src/simulator/core/kernel.py#L629), [Admission](../../src/services/admission.py#L92), [Benchmark](../../src/services/simulation_service.py#L137), [Contract](FOUNDATION_CONTRACT.md) | Backend Energy / Finance contract · **P1** · ghi contract G1 |
| **R11 · Planned feature** — outcome ledger | Baseline `outcomes()` bỏ NOT_ARRIVED, dùng charge_started thay plug-in, clamp delivered nếu đạt đúng hạn. `compute_kpis` trả 1.0 cho cohort rỗng và dùng deadline thay censoring biểu diễn rõ. Giữ KPI frozen. WHAT-IF cần outcome ledger additive. | [Outcomes](../../src/simulator/hybrid_station.py), [KPI](../../src/services/simulation_service.py#L120) | Copilot Evaluator · **P1** · G3 (AI-4.2A) |

## G1 verification

R01–R04 và hai ca barrier R07 fail trên code trước sửa ở đúng hành vi được mô tả. G1 thêm copy state có owner riêng, lifecycle detail lookup, validation stages, exclusion precedence và power provenance. Xem verdict test, migration và parity ở [báo cáo G1](PHASE_4_0_REPORT.md).

## Kiểm tra bổ sung cho G1–G4

| Chủ đề | Quan sát và bước xác minh cần thiết |
|---|---|
| Snapshot/read race và outbox | Runtime lưu outbox trong deque có giới hạn. Chụp danh sách rồi clear là hai bước. `sync_clock` có thể enqueue ngoài asyncio lock. Test hiện có xác minh off-thread delivery, app-loop registration và dedup. G1 tuần tự step/enqueue/drain và tạm hoãn read-driven step khi đang lập lịch. Capture epoch, atomic snapshot và mixed booking/runtime digest chờ G3. |
| Incomplete outcome | `outcomes()` bỏ `NOT_ARRIVED`, dùng `charge_started` làm `plug_in_time` và nâng delivered tới requested ở ca hoàn tất đúng hạn. KPI lọc feasible, cohort rỗng trả 1.0, wait p90 gán deadline cho xe chưa bắt đầu sạc. Cần ledger additive với denominator, censored và tách plug wait khỏi first-charge wait. [Outcomes](../../src/simulator/hybrid_station.py#L587) · [KPI](../../src/services/simulation_service.py#L120) |
| Target thấp hơn SOC thật | `_update_present` sửa desired capacity, không trực tiếp reset SOC. Adapter tính headroom bằng `max(0, desired - current)`; kernel đánh dấu FINISHED trên bước vật lý có candidate. Chưa probe ca target dưới SOC thật qua đường revise. G0 chọn already attained. G4 kiểm cả CHARGING/FINISHED, giữ original SLA và kWh. [Update](../../src/simulator/hybrid_station.py#L658) · [Adapter](../../src/simulator/core/ev2gym_adapter.py#L151) · [Kernel](../../src/simulator/core/kernel.py#L617) |
| Năng lượng và chi phí | Kernel ghi riêng output kWh, delivered battery kWh, delivered grid kWh qua conversion. Admission nhân delta output kWh với tariff, benchmark chia cho conversion trước khi tính tiền. `EnergyEstimate.grid_energy_kwh` chỉ chia charging efficiency và được `VehicleVisit.required_kwh` diễn giải là output kWh. Khác biệt công thức đã xác nhận qua code. Chưa có số đo quote/bill cùng fixture hoặc quyết định bên nào chịu hao hụt. Copilot cần field tách nguồn, pin, output và định nghĩa TOU tính từ T một lần. [Kernel](../../src/simulator/core/kernel.py#L629) · [Energy](../../src/services/energy.py#L23) · [Admission](../../src/services/admission.py#L92) · [Benchmark](../../src/services/simulation_service.py#L137) |
| Event knowledge | Observation lọc limit events theo announced minute, có standalone test chống nhìn trước. Fork giữ scenario và copy queue, nên observation filtering chưa đủ làm bằng chứng cho rollout `known_at(T)`. Kiểm riêng future bookings, announcements, recovery và incident manifest của hai nhánh. [Fork](../../src/simulator/core/kernel.py#L121) · [Observation](../../src/simulator/core/kernel.py#L353) · [Test](../../src/simulator/tests/test_mvp3.py#L169) |
| Solver thread | Backend dùng `ThreadPoolExecutor(max_workers=1)`. Repo ghi nhận sự cố HiGHS đa thread trên Windows. P0 chạy lại luồng hiện hữu. Tải job, fairness và cancellation đối với live replans chưa đo, thuộc G3/G4. [Solver](../../src/services/solver.py) |
| Dữ liệu trace | Đã xác nhận thiếu evidence refs và config fingerprint trong outer trace. Kiểm JSON số hữu hạn, independent/unbounded representations và policy tại decision time trước khi dùng cho WHY. P0 probe mới bao phủ zero sample và charge-model fault. [Open trace](../../src/services/decision_trace.py#L82) · [JSONL](../../src/services/decision_trace.py#L232) |

## G1 remediation ledger

| ID | Phân loại và kết quả | Owner |
|---|---|---|
| G1-F01 | **Confirmed** qua fault-injection. Destructive drain làm mất hard event trước trace close, event store, notification/cancellation và power emergency. Batch mixed và overflow tái hiện mất event. Sửa bằng pending registry không eviction, acknowledge theo safety, hard-first và idempotent timeline. | Runtime / Safety |
| G1-F02 | **Confirmed** qua fault-injection. Dispatch blocked, pending, partial hoặc không sinh command khi vẫn unsafe từng mở interlock sai. Lỗi sink sau apply từng giữ interlock dù trạm đã an toàn. Dùng readback, tách delivery/dispatch/resolution, retry tối đa ba lần và log khi unresolved. | Runtime / Guard |
| G1-F03 | **Confirmed inherited** cho tăng công suất trên local `d2b5d48`. G1 review cũng tái hiện assignment đã duyệt trước fault. Dispatcher recheck hiện tại khóa cả hai theo Safety Hold/occupant và giữ audit executed=false. | Guard / Approval |
| G1-F04 | **Confirmed** qua sample eviction, lỗi dựng facts và non-finite serialization tại close. Coverage phát hiện dữ liệu thiếu, eviction không xóa violation counter, fallback giữ applied evidence và fail-safe chạy trước trace. | Trace / Runtime |
| G1-F05 | **APPROVED at Gate 2 (`aa37ca5`)**. Mở rộng additive `planned`, `safety.by_booking` và mốc ISO trên `chargepilot.backend_decision_trace/2` trong `hybrid_station.py` và `decision_trace.py`, tách bạch observed/planned/approved/dispatched/effective/measured và giữ nguyên standalone serializer. | WHY Evidence Resolver |
| G1-F06 | **APPROVED at Gate 2 (`aa37ca5`)**. `repository.py` + `src/services/copilot/{trace_reader,evidence,why}.py` hỗ trợ as-of, half-open `[start, end)` overlap, cắt replan sớm, giới hạn active trace sau restart, bounded pagination, phân quyền non-enumerating và privacy projection. | WHY Evidence Resolver / Persistence |

## Gate 2 remediation ledger (mirror `6ba13b8` → `2d15ca1` → APPROVED `aa37ca5`)

| ID | Phân loại và kết quả | Owner |
|---|---|---|
| G2-F01 | **Confirmed bug → Fixed**. `extract_measured_slice()` từng cộng full sample duration cho sub-minute window, trả năng lượng sample cho `at`, và double-count mẫu trùng. Đã sửa sang exact overlap piecewise-constant, high-water dedup và tách as-of power khỏi interval energy. | WHY Trace Reader |
| G2-F02 | **Confirmed bug → Fixed**. Derived sub-window facts từng chỉ trỏ `samples/0` và direct fact không kiểm khớp giá trị canonical. Đã thêm `derivation_kind`/`derivation_op`/`input_evidence_refs`, kiểm khớp direct value và kiểm provenance reason. | WHY Evidence / Explainer |
| G2-F03 | **Confirmed bug → Fixed**. Sub-window measured facts từng dùng interval toàn trace và observed snapshot dùng planned 15-min interval. Đã tách `TemporalBasis` cho cả booking & station. | WHY Explainer |
| G2-F04 | **Confirmed bug → Fixed**. Đường mặc định `_live_open_trace_state()` khi `_live is None` từng không gắn stale; booking query từng bỏ qua station-level supersede; limit bị lookback chiếm. Đã sửa trên index `0004` + station timeline + keyset `cursor`/`next_cursor` + `query_exceeds_live_physics_clock`. | WHY Trace Reader / Persistence |
| G2-F05 | **Confirmed bug → Fixed**. Khắc phục future completion leakage (`completed_by_booking`), completion ref trỏ `state="CHARGING"`, station violation gán nhầm vehicle, `NO_INCIDENT_OBSERVED` khi chưa đủ bằng chứng, thiếu verdict/rule/approval_id/hardware inputs. | WHY Explainer |
| G2-F05a | **Confirmed bug → Fixed (final targeted fix)**. Post-apply violation từng dùng trạng thái toàn trace không lọc theo query `at`/`window` (rò rỉ violation T+12 vào T+5), và post-decision completion dùng `decision_snapshot`. Đã lọc theo `applied.hard_violation_details` (`v_start <= at` / half-open overlap), gắn `post_apply_violation_temporal_attribution_missing` (`PARTIAL`) khi eviction/thiếu timestamp, và đổi completion sau quyết định sang `MEASURED_COVERAGE` tại `[comp_dt, comp_dt]`. | WHY Explainer |
| G2-F05b | **Confirmed bug → Fixed (final targeted fix)**. `_has_vehicle_specific_violation` từng dùng Safety Hold cũ làm điều kiện đủ để quy kết violation mới. Đã loại bỏ Safety Hold khỏi liên kết violation, yêu cầu bằng chứng trực tiếp từ `applied.hard_violation_details/{idx}/{kind,minute,vehicle_ids/v_idx}` và fallback an toàn sang `STATION_POST_APPLY_HARD_VIOLATION` cho Resident ở sự kiện nhiều xe. | WHY Explainer / Auth |
| G2-F06 | **Confirmed bug → Fixed**. Loại bỏ hoàn toàn silent fallback `0.95` / `0.98`; trả `PARTIAL` + missing evidence khi thiếu decision-time efficiency. | WHY Trace Reader / Explainer |
| G2-F07 | **Confirmed bug → Fixed**. `resolve_evidence_ref` bắt buộc `AuthorizedSubject`/verified `Booking`, kiểm đủ ref_id/path/schema/policy/decided_at/subject/interval; thu hẹp allowlist xuống leaf paths; kiểm explicit reason `subject`/`params`/`summary`. | WHY Auth & Privacy |
| G2-F08 | **Confirmed gap → Fixed**. Mở rộng independent oracle kiểm toán mọi emitted fact/ref, tách 9 chỉ số kèm denominator rõ ràng và 7/7 mutation detection. | WHY Evaluation |
| G2-F09 | **Confirmed handoff gap → Fixed**. Tạo/xác minh `docs/ai4/PHASE_4_1_REPORT.md` đồng bộ với `PROJECT_STATE.md`, ledger, hashes và raw evidence. | Docs / Handoff |

## Gate 3 (AI-4.2A) remediation ledger

G3-F01–F08 được Tech Lead phê duyệt tại mirror `d0fcf5d11cfd75b677eeaed00e5b5264ab828744` với candidate patch SHA-256 `59a92d326cfaae6cd8bb3d2b94b4124765b3efdcb3551b2c48d36e60ca73dc5d`. PostgreSQL runtime vẫn PENDING.

| ID | Phân loại | Xử lý |
|---|---|---|
| G3-F01 | Confirmed bug | Giữ bản sửa của Neon cho fork và fingerprint. Readiness đã qua 3/3 trên candidate Neon. |
| G3-F02 | Confirmed bug | Rollout và admission dùng runtime interlock, retry/readback G1 và ghi kết quả an toàn tại bước cuối. |
| G3-F03 | Confirmed bug | So hash nội dung manifest và seed trước khi dựng branch, copy budget/setpoint maps. |
| G3-F04 | Confirmed bug | Từ chối cohort vật lý bất nhất, dùng commit membership cho store live, scope lại plan/commands/approvals và lưu mutation event trong outbox. |
| G3-F05 | Confirmed bug | Historical first charge thiếu evidence trả null. Tách mốc first rollout charge và lưu trạng thái historical plug unknown. |
| G3-F06 | Confirmed limitation | Đặt tên optimistic energy bound, báo denominator và dùng mốc quan sát được khi censor. |
| G3-F07 | Confirmed bug và giới hạn | Hủy và thu hồi branch còn lại khi paired job lỗi. Giới hạn concurrency trong một event loop. Native solver và live priority giữ giới hạn. |
| G3-F08 | Confirmed evidence gap | Candidate patch và gate runner với expected exit codes, independent evaluation và kết quả tổng hợp. |

Trạng thái kiểm chứng và raw evidence theo [báo cáo G3](PHASE_4_2A_REPORT.md).

## Backlog sau AI-4.2A

- G4 MUST gồm `revise_vehicle.target_soc`, `revise_vehicle.deadline`, `site_limit` và `outage`. Tech Lead đã cấp quyền triển khai G4.
- Sau G4 final acceptance và authorization riêng, thứ tự là G6A → G5 → G6B → G7. Bounded HOW-TO, production grounding, LLM integration và PostgreSQL runtime verification giữ scope đã duyệt. [Master Plan](AI-4_MASTER_IMPLEMENTATION_PLAN.md)

## Gate 4 (AI-4.2B) verification ledger

- **R06.** Bốn WHAT-IF operation và owner-scoped jobs đã qua local gate ở candidate được review. Tech Lead ghi `CONDITIONAL PASS — FINAL REMEDIATION REQUIRED` cho G4-F01–F03 tại mirror `343cddce2e7c22e8753945589a94d2ad7ed48042`.
- **R10/R11.** G4 tách station grid input, charger output và battery energy. Original và revised SLA có cutoff và denominator. Station unmet battery kWh và charger-output equivalent đo remaining energy để đạt target gốc tại observation cutoff. R10 billing giữ phạm vi đã duyệt.
- **Remaining.** PostgreSQL runtime verification. Native solver call đã bắt đầu có thể tiếp tục sau khi job bị hủy. G4 probe xác nhận job bị hủy ở baseline không submit patched branch.

| Finding | Phân loại | Resolution và evidence |
|---|---|---|
| G4-F01 | Confirmed bug | T+7:30 từng rời cổng tại T+8, ảnh hưởng năng lượng và booking tiếp theo. Typed validation chặn explicit deadline lệch lưới T. Fixture kiểm timezone, lưới bắt đầu tại giây lẻ, deadline aligned và target-only với deadline gốc lẻ. |
| G4-F02 | Confirmed bug | Mất mẫu B từng tạo delta wait −15 phút. Mean, p90 và rates cần đúng tập booking; metadata tách `non_comparable_sample` khỏi `missing_data`. Giữ counts và additive energy/cost delta. |
| G4-F03 | Verification gap và confirmed replay bug | Mixed AC/DC oracles kiểm site binding, hardware/acceptance, future decrease/increase và cabinet-only. Sandbox replay giữ announced source có hiệu lực tại T riêng với runtime override, và phát một effective limit event cho mỗi nhánh tại boundary. |

[Báo cáo Gate 4](PHASE_4_2B_REPORT.md) · [Oracle calculations](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/oracle-calculations.md)

**G4 — APPROVED.** Tech Lead đã nghiệm thu G4-F01–F03 tại mirror `eb5967ae720b46b089b09e03063aa2c727ca5fd8` với remediation-only patch `1cdb630cc10a4bfd1fb96d1ac2264dbd4a9515f3dbfe7153780f0c6fd33160bf`. Remediation candidate `e8ae5cedbbe5af0a0a05d63f3dbb4ea6ac22fda40a4628a2cf7abca82be10d0f` qua mandatory gate exit 0. PostgreSQL runtime vẫn PENDING. [Gate ledger](../../eval/evidence/2026-11-25-ai4-4-2b/recovery/final/gate/exit-codes.tsv)

## Gate 6A (AI-4.4A) recovery & verification ledger

| ID | Phân loại | Xử lý và bằng chứng |
|---|---|---|
| **G6A-R01** — Delayed/in-flight Copilot responses qua logout hoặc đổi tài khoản | **Confirmed frontend isolation gap → Fixed** | `CopilotPanel.tsx` của Codex đã tách `key={session.userId}`, nhưng chưa gắn `session.token`/`role` vào khóa phiên, chưa xóa `["copilot"]` trên `QueryClient` khi logout và chưa chặn callback `onSuccess` của `submit`/`cancel` đang bay khi phiên cũ unmount. Đã bổ sung `actorKey`, `{ signal }`, dọn cache khi logout/unmount, `mountedRef` + `submitEpochRef`, kiểm chứng bằng Vitest (`35/35` PASS) và Chromium smoke chuyển tài khoản cùng tab (`exit 0`). |
| **G6A-R02** — Turbopack build restriction | **Environment / sandbox restriction (Confirmed)** | Lỗi `binding to a port — Operation not permitted` ở phiên chạy Codex là hạn chế chặn bind socket của sandbox đó; trên cây `/tmp` dùng symlink `node_modules` xuyên phân vùng, Turbopack từ chối symlink ngoài workspace root. Cổng `verify.sh` hỗ trợ `G6A_WEBPACK=1` (`next build --webpack` PASS `exit 0`), đồng thời `next build` (Turbopack) trên `P-019/frontend` với `node_modules` trực tiếp cũng xác nhận PASS `exit 0`. |
| **R08 (G6A scope)** — Real LLM provider & PostgreSQL runtime | **PENDING (không có key / dịch vụ trong môi trường)** | `provider-status.json` xác nhận không có API key được cấp phép và không có local LLM server tại `localhost:11434`; demo và browser smoke dùng `LLM_PROVIDER=mock` (deterministic fallback), tách bạch rõ với kiểm thử LLM thật và PostgreSQL thuộc G7. |

[Báo cáo Gate 6A](PHASE_4_4A_REPORT.md) · [G6A Recovery](G6A_RECOVERY_STATE.md) · [Backend exits](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/backend-exits.tsv) · [Frontend exits](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/frontend/frontend-exits.tsv)


## Merged develop và Gate 5 (2026-11-26)

| ID | Phân loại | Kết quả / người xử lý |
|---|---|---|
| G5-A01 | RECOVERABLE, checkpoint cũ | Local branch và develop cùng `0f877f1`, khớp cây mã nguồn mirror `20bb246`. Giá trị checkpoint Phase 1 giữ làm lịch sử. |
| G5-A02 | Nhiễu workspace | Architecture quét cây R&D cũ bị Git bỏ qua dưới `src/simulator/claude_rd/`. Bản xuất sạch từ Git dùng architecture nguyên gốc và pass. |
| G5-A03 | Hạn chế môi trường test | Sandbox không đánh thức vòng lặp asyncio kịp sau khi thread solver trả kết quả. Trace thấy future đã hoàn tất. Chạy lại ngoài sandbox, với env tối thiểu và SQLite tạm. Baseline backend pass. |
| G5-A04 | Golden provenance | Golden LF lệch hash file scenario ở 11 phép so sánh. Hai fixture được xuất CRLF trong bản sao tạm, khớp hash lịch sử. Gate 38/38, comparator giữ nguyên. |
| G5-R01 | Amendment chờ duyệt | Nhóm chọn Chat Agent thống nhất. Đề xuất cập nhật PRD v0.4 và ADR bổ sung cho bounded HOW-TO MUST, AI-1 backlog, G6A fallback và G6B typed tools. [Master Plan](AI-4_MASTER_IMPLEMENTATION_PLAN.md) |
| G6A-F01 | **Fixed in G6B** | Đã thay raw JWT trong khóa cache bằng `session.generation` (`session.ts`, `CopilotPanel.tsx`, `ChatAdvisory.tsx`). |
| G6A-F02 | **Fixed in G6B** | Phản hồi `401` trễ (REST, chat stream, voice transcribe và WS `4401`) chỉ gọi `clearSessionIfCurrent(requestGeneration)`, không đăng xuất nhầm phiên mới (`session-401.test.ts`, `voice-session-isolation.test.tsx`). |
| G6A-F03 | **Fixed in G6B (bounded fixture scope; held-out thuộc G7)** | Đã ràng buộc tham số đầu vào phía server (`conflicts_with_simulation`, `why_conflicts_with_message`) cho cả WHAT-IF, HOW-TO và WHY; bộ đánh giá NL held-out với LLM thật thuộc G7. |

Candidate G5 ban đầu đã qua oracle và gate cục bộ. Real LLM smoke và PostgreSQL runtime còn **PENDING**. [Raw evidence](../../eval/evidence/2026-11-26-ai4-g5/raw)


## G5 targeted remediation

| Finding | Xử lý |
|---|---|
| G5-F01 | Oracle actual simulator trên M3a/M3b dùng 2 AC + 2 DC với DC taper synthetic, lấy mẫu vật lý từng phút. 94 kW là mức nhỏ nhất đã xác minh giữ 4/4 SLA trong ca mixed load. |
| G5-F02 | Baseline quan sát cùng target với goal, giữ original SLA riêng. Có ca M3a đạt sớm 6 phút và ca baseline đã đáp ứng với cùng attainment/release trên cả năm ứng viên. |
| G5-F03 | Tách provenance đầu vào khỏi ref của projection. Cùng snapshot có 4 projection theo booking, goal hoặc phút quan sát. Trước sửa chỉ có 1 ref. Field-level claim dùng JSON Pointer tới phần evidence đã chiếu. |
| G5-F04 | Rule Git bỏ qua raw logs và patch rời. Gói verification ZIP nhỏ gồm bản patch, checksum, file hashes, full/gate logs, JUnit, oracle và exit ledger. |

[Báo cáo và bằng chứng](PHASE_4_3_REPORT.md)

**G5 — READY_FOR_FINAL_ACCEPTANCE.** Bốn finding đã có bằng chứng kiểm chứng cục bộ. Tech Lead quyết định cuối.

## Quyết định cuối Gate 5

Tech Lead quyết định **G5 APPROVED** tại mirror `42438430ee49f404e90080c49a76e4c6446530da`. Candidate SHA-256 `7dd32a1903aa67b9548ad30da21739a6b9a9b220d3ca681853d267027b4fc534`, bundle SHA-256 `ea90e5ca90452ac105683b6630de6f579bfddb33f8ec4f4a10839f55db1f1dc9`. Tech Lead xác nhận 6/6 blob, 6/6 source hash, 26/26 checksum nội dung, oracle M3a/M3b, hai trường hợp có cải thiện và không cải thiện, G5-F01–F04 đã xử lý, 30 G5, 137 hồi quy G2/G3/G4/G6A, 43 architecture, 838 backend + 8 forecast skips, 180 standalone và 10/10 cổng exit 0. G5 đóng, chỉ xử lý blocker tích hợp đã xác nhận nếu có.

## Gate 6B targeted remediation (sau review mirror `2c72e2b`)

| Finding | Phân loại | Xử lý và bằng chứng |
|---|---|---|
| **G6B-F01** — Ràng buộc tham số đầu vào với yêu cầu người dùng | **Confirmed bug → Fixed** | Tái hiện 2 ca E2E HTTP và 3 ca direct validator trên `85ba2959...`. Bổ sung kiểm chứng đầy đủ phía server (`copilot_intent.py`, `integration.py`, `act_node.py`) cho target SOC, deadline/time window theo múi giờ trạm, connector/booking ID, thời lượng/starts_at outage, `horizon_minutes`, site kW, khoảng thử HOW-TO (`bounds`), ngưỡng SLA %, bảo vệ xe AC và cờ hy sinh/hạ tầng giả định; lịch sử nhiều lượt chỉ đọc `role="user"`, bỏ qua văn bản `assistant`. Spy `capture_atomic_snapshot` chứng minh 0 lần chụp khi lệch/thiếu tham số (`17/17` focused G6B PASS). |
| **G6B-F02** — Cô lập phiên cho voice input | **Confirmed bug → Fixed** | Tái hiện bằng Vitest lỗi gửi audio của Resident A kèm Bearer token của Resident B khi `FileReader` hoàn tất sau đổi phiên. Gia cố `ChatPanel.tsx` và `useStream.ts`: khóa `voiceEpoch` + `capturedGeneration` tại thời điểm bắt đầu, kiểm tra trước/sau mọi `await`, hủy `AbortController`, dừng `MediaStream` tracks (kể cả `getUserMedia` trễ) và gỡ handler trước khi `stop()` khi logout/unmount; `401` chỉ xóa đúng generation đã gửi (`66/66` Vitest PASS). |
| **G6B-F03** — Selector Chromium `--ranked` | **Confirmed test blocker → Fixed** | Tái hiện lỗi strict-mode locator trên Chromium `159.0.8154.6`. Định vị tường minh `ol > li > strong` trong `browser_smoke.mjs` đồng thời kiểm tra danh sách ứng viên `details ul > li` vẫn giữ nguyên, không đổi giao diện. Cả `two-roles` và `--ranked` (`94 kW`, `partial`, `applied=false`) đều đạt `exit 0`. |
| **G6B-F04** — Kiểm soát tải tầng tích hợp | **Confirmed gap → Fixed (phạm vi G6B); G7 giữ phần tải lớn** | Đưa `check_admission()` lên trước `capture_atomic_snapshot`, bật `max_active_per_actor=1` và đồng bộ cooldown 15s giữa Chat và G6A fallback; bổ sung trần lượt đồng thời theo user (`3`) và toàn cục (`8`) trên cả `/chat`, `/chat/stream` và `/chat/sessions/{id}`, tự nhả permit khi timeout/disconnect. Phần tải 1.000 concurrent, p95 dưới tải, rate/cost LLM thật và tỉa `MemorySaver` giữ ở backlog G7. |
| **G6B-F05** — Đóng gói bằng chứng và provenance cuối | **Confirmed gate blocker → PASS mã thực thi (mirror `de82afe7`)** | Bảo tồn patch và raw logs lịch sử của Codex + vòng 1 (`dab76e32...`), sửa dòng trắng cuối `prompts/booking_reason.md`, cập nhật `.gitignore` cho `eval/evidence/2026-11-26-ai4-g6b/raw/`, ghi rõ provenance `.env.example` (`a96d656...`) trên nhánh chính so với mirror, dựng `candidate.patch`, `SHA256SUMS` và `verification-bundle.zip` trên bản xuất sạch từ `64c85f1`. |
| **F01-R1** — Công suất đầu nối đơn lẻ bị hiểu thành `site_limit` | **Confirmed residual bug (`de82afe7`) → Fixed** | Tái hiện fail-before (`f01-r1-r3-fail-before.log`): `"Nếu công suất sạc của cổng DC-01-1 còn 50 kW thì sao?"` từng chạy `site_limit=50`. Bắt buộc chủ thể nguồn/lưới/đầu vào trạm (`_SITE_POWER_SUBJECT`) và chặn mọi mã đầu nối, danh từ cổng/trụ/bộ sạc/tủ (xử lý chuẩn đồng âm không dấu `cổng` vs `công suất`, `tủ` vs `từ`), phạm vi vùng AC/DC riêng lẻ và độ lệch kW tương đối; bổ sung đối chứng dương tính nguồn lưới trạm `50 kW`. |
| **F01-R2** — Lịch hẹn tương lai trên site HOW-TO bị lược bỏ âm thầm | **Confirmed residual bug (`de82afe7`) → Fixed** | Tái hiện fail-before: `"Cần nguồn bao nhiêu từ ngày mai lúc 18h00?..."` từng chạy ngay trên snapshot hiện tại. Chặn mọi điều kiện thời điểm/ngày/buổi/thời lượng ngoài cửa sổ `horizon` trong `_has_site_temporal_condition` cho cả `SourceChange` và `MinTestedSiteLimitForSla`; bổ sung đối chứng dương tính tìm nguồn tức thời `22–106 kW` / SLA `95%` / giữ AC. |
| **F01-R3** — Độ lệch tương đối theo hạn gốc bị dịch thành tương đối theo `now` | **Confirmed residual bug (`de82afe7`) → Fixed** | Tái hiện fail-before: `"muộn hơn 30 phút so với hạn gốc"` từng tạo hạn `12:31+07` thay vì `14:30+07`. Tách `_SHIFT_OFFSET` / `_NON_NOW_ANCHOR` khỏi `_RELATIVE` (chỉ giữ `sau`/`trước`/`in` tính từ `now`), trả `clarify("time")` / `unsupported` trước `capture_atomic_snapshot`; kiểm chứng đối chứng dương tính cả `sau 30 phút` (`12:31+07`) và mốc tuyệt đối `2026-11-23T14:30:00+07:00` (`14:30+07`). |

[Báo cáo Gate 6B](PHASE_4_4B_REPORT.md) · [Recovery G6B](G6B_RECOVERY_STATE.md) · [Verification bundle](../../eval/evidence/2026-11-26-ai4-g6b/verification-bundle.zip)

**G6B — READY_FOR_FINAL_ACCEPTANCE.** Chờ Tech Lead nghiệm thu độc lập.
