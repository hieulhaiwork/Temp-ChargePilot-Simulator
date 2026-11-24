# PHASE3_DESIGN — Unified Runtime + Booking Migration (thiết kế trước khi code)

> Nhánh `feature/unified-core-p3`, từ `749c042`. Căn cứ: `PLAN.md` mục Phase 3, ADR-019 (mục "Quyết định 2026-11-23
> sau review Phase 2"), `PHASE0_FINDINGS.md` §2–§4, `PHASE2_REPORT.md`. Số thứ tự `#n` dưới đây là khác biệt thứ n ở
> PHASE0_FINDINGS §2.

## 0. Tóm tắt

Có **một kernel** `StationKernel` (`src/simulator/src/engine/hybrid.py`) sở hữu trạng thái vật lý (queue, EV2Gym
adapter, đồng hồ, setpoint đang giữ, cổng lỗi) và bốn thao tác:

```text
observe()                        xe đến / rời / rút DC tại `now` (QueueController.advance)
propose(...)    → ProposedDecision   Planning Core: dispatch → coordinator → optimizer → Physical Guard (trước)
approve(...)    → ApprovedDecision   chỉ chấp nhận chỉnh sửa nghiệp vụ nếu qua lại CÙNG Physical Guard
apply_approved(approved)             gắn xe vào cổng + giữ setpoint (kiểm state_version)
advance(until)  → AppliedResult      Physical Core: một vòng tích phân + Physical Guard (sau)
```

- `HybridSimulator` (CLI, benchmark MVP-1/2/3, golden, DecisionTrace) **là** `StationKernel` cộng phần ghi
  trace / frame / report. `step()` = `observe → propose → approve → apply_approved → advance`.
- `HybridStation` (backend) **giữ một** `StationKernel`. `step(minutes)` gọi `kernel.advance` + `kernel.observe`;
  `apply_commands` (chỉ `guard/dispatcher.py` gọi) dùng đúng primitive `connect` / `hold_setpoint` của kernel.
- `SimulatorScheduler.plan` gọi `kernel.propose` trên trạm đang chạy → consent → `kernel.approve` → `SchedulePlan`.
  Lệnh vẫn đi `diff_commands → guard/dispatcher.py` (Business Guard 7 luật + HITL) trước khi tới `apply_commands`.
- Quote / booking / change (`charging_service`) gọi `services/admission.py`: **fork** trạm (bản sao sâu), thêm xe
  giả định, chạy cùng `SimulatorScheduler` + cùng kernel tới deadline của xe. Không mutate trạm live.
- Bị xoá: `HybridStation._charge_one_minute`, `SimulatorScheduler._decide`, LP backend A–D
  (`optimizer/{assignment,lp_model,horizon,mpc,baselines,base,strategies}`), `LiveStation`. Ghi ở
  `DELETION_MANIFEST.md`.

Vì sao kernel nằm trong `engine/hybrid.py` mà không ở file mới: test của chủ simulator (không được sửa) monkeypatch
`hybrid.guard` và gán lại `sim.algorithms`; Physical Guard trước + sau phải là lời gọi tới **global `guard` của
module `hybrid`**, và `algorithms` phải đọc từ chính đối tượng simulator lúc chạy. `HybridSimulator(StationKernel)`
đáp ứng cả hai mà không cần shim.

## 1. Hợp đồng `src/models/decisions.py` (stdlib, simulator standalone import được)

Mọi đối tượng là `@dataclass(frozen=True)`; mapping bị đóng băng bằng `MappingProxyType` trong `__post_init__`.

```python
@dataclass(frozen=True)
class TimeConfig:
    physics_step_minutes: int | None = None     # None = chế độ tương thích golden (ZOH cả interval)
    decision_interval_minutes: int | None = None  # trần interval quyết định; None = scenario.timestep
    planning_horizon_minutes: int | None = None   # trần interval optimizer thấy; None = interval quyết định

class ReasonCode:                     # hằng chuỗi, ghi vào diagnostics / trace
    PLANNED, OPTIMIZER_FALLBACK, CONSENT_ADJUSTED, REJECTED_BEFORE_APPLY, STALE_STATE,
    VIOLATION_AFTER_APPLY, BUDGET_DEVIATION, CHARGE_COMPLETED

@dataclass(frozen=True)
class ProposedDecision:
    policy_id: str; policy_version: str       # "M3a"/"1", "custom"/"1", hoặc nhãn từ registry
    state_version: int                        # phiên bản trạng thái kernel lúc propose
    minute: int                               # đầu interval
    interval_end: int                         # mốc boundary kế tiếp (interval quyết định)
    planning_interval_minutes: int            # interval optimizer thấy (acceptance, block đầu LP, consent)
    assignments: Mapping[str, str]            # cổng → xe (dispatch, CHƯA áp)
    setpoints_kw: Mapping[str, float]         # xe → kW đầu ra (đã qua Physical Guard trước)
    budgets: ZoneBudgets                      # assigned budget của Coordinator
    effective_limits: EffectiveLimits         # hard caps tại `minute` (đúng object Guard đã dùng)
    candidates: Mapping[str, Candidate]       # xe được cấp điện + allowed_kw cho interval quyết định
    observation / planning / dispatch / demand  # bằng chứng cho DecisionTrace (chính các object optimizer thấy)
    diagnostics: Mapping[str, object]; solver_ms: Mapping[str, float]
    reason_codes: tuple[str, ...]

@dataclass(frozen=True)
class ApprovedDecision:
    proposal: ProposedDecision
    setpoints_kw: Mapping[str, float]         # = proposal.setpoints_kw, hoặc bản đã chỉnh bởi nghiệp vụ
    adjustments_kw: Mapping[str, float]       # phần nghiệp vụ ép (consent), rỗng nếu không chỉnh
    rechecked: bool                           # True ⇔ setpoint khác đề xuất ⇒ đã chạy lại guard(...)
    reason_codes: tuple[str, ...]

@dataclass(frozen=True)
class AppliedResult:
    minute: int; end: int; physics_step_minutes: int
    requested_kw / allowed_kw / actual_kw / stored_kwh: Mapping[str, float]
    completed: tuple[str, ...]                # xe đạt target trong lần advance này
    violations: tuple[str, ...]               # VIOLATION_AFTER_APPLY: Physical Guard sau (hard)
    budget_deviation_kw: Mapping[str, float]  # BUDGET_DEVIATION: vượt assigned budget (không phải hard)
    state_version: int
```

`ProposedDecision` / `ApprovedDecision` cần `Candidate`, `ZoneBudgets`, `EffectiveLimits` nên file nằm ở `src/models`
cạnh `scheduling/` và chỉ import hợp đồng core (thêm vào `CORE_CONTRACTS` của `tests/test_architecture.py`).

**Rejected-before-apply ↔ violation-after-apply.**
- `propose()` hoặc `approve()` raise `ConstraintViolationError` khi dispatch / budget / setpoint không qua Physical
  Guard (trước). Kernel đếm `rejected_allocation_count`. Không có gì được áp (không cắm xe, không đổi setpoint).
  Offline: dừng run (fail-closed, như cũ). Backend: `SimulatorScheduler` trả lịch an toàn (0 kW, giữ gán cổng hiện
  có), ghi `REJECTED_BEFORE_APPLY` vào `last_diagnostics` (#10).
- `advance()` kiểm phản hồi pin (`validate_response`) và tổng công suất thực tế (`guard`) **sau** khi tích phân. Sai
  thì `applied_constraint_violation_count += 1`, mã `VIOLATION_AFTER_APPLY`. Chế độ `strict` (offline) raise và
  khoá run; backend ghi log + đếm và chạy tiếp (trạm live không được chết, ADR-017).

## 2. Thời gian (P1) và chế độ tương thích

| Tham số | Offline tương thích (mặc định CLI / golden) | Backend (`HybridStation`) | Offline 1' (mới, cho differential) |
|---|---|---|---|
| `physics_step_minutes` | `None` = một lần tích phân cho cả interval (ZOH) | `1` | `1` |
| `decision_interval_minutes` | `scenario.timestep` (1 hoặc 5) | `optimizer.planning_step_minutes` (15) | `scenario.timestep` |
| `planning_horizon_minutes` | = interval quyết định | = interval quyết định | = interval quyết định |

- Interval quyết định `[now, end)` với `end = kernel.boundary(now, cap=decision_interval)`.
- Physical Core (`advance`) chia `[now, end)` thành các bước `physics_step` (hoặc một bước nếu `None`). Mỗi bước:
  candidates (allowed cho đúng độ dài bước), setpoint thực = `min(setpoint giữ, allowed)`, `adapter.step`,
  `validate_response`, cộng năng lượng, xe đạt target → `FINISHED`, `completed_at = cuối bước`, rồi Physical Guard sau.
  Ở chế độ `None` bước duy nhất dùng đúng candidates / limits của quyết định, nên kết quả trùng `HybridSimulator.step`
  cũ (golden). Ở chế độ 1' taper DC được tính lại từng phút (#1) và `completed_at = phút + 1` (#2).
- Ở chế độ 1', xe sạc xong giữa interval làm `advance` dừng sớm để quyết định lại ngay (#4). Backend phát
  `REPLAN_REQUESTED` (detail "Xe … sạc xong") để `control_loop` tính lại.
- **Không so benchmark giữa hai cấu hình thời gian khác nhau** (ADR-019). Mọi report / evidence ghi `TimeConfig`.

**Giới hạn của P1 (đối chiếu P2 / P3, PHASE0 §4).**
- Còn hai cấu hình vật lý (cùng code): kết quả offline tương thích phụ thuộc cách chia interval (ZOH 5' ở MVP-3),
  nên số MVP-3 không so được với backend. P2 (mọi chế độ 1') bỏ được giới hạn này nhưng đổi golden MVP-3 → phải có
  policy / benchmark version mới, cần escalate. P3 (backend theo interval quyết định 15') giữ một cấu hình nhưng xe
  hoàn thành trễ tới 15', xấu cho demo.
- Ở chế độ 1', optimizer vẫn hứa theo acceptance đầu interval; phần `actual < setpoint` do taper trong interval không
  được chia lại cho xe khác tới lần quyết định sau (≤ 15' hoặc sớm hơn nếu có sự kiện). Đây là hệ quả của P1, ghi rõ.

## 3. Một hàm boundary sự kiện

```python
def boundary(self, now, *, cap, scenario=None, include_unseen_arrivals=True, online=False) -> int:
    cfg = scenario or self.scenario
    end = self.queue.next_boundary(now, cfg if cap == cfg.timestep else replace(cfg, timestep=cap),
                                   include_unseen_arrivals=include_unseen_arrivals)
    return environment_boundary(cfg, now, end, online=online)
```

- Mốc: `now + cap`, cuối kịch bản, xe đến, giờ rời khai báo, mốc rút DC (`completed_at + delay`), đổi giá TOU, mốc
  công bố / hiệu lực `LimitEvent` (online chỉ thấy sự kiện đã công bố).
- Offline: interval quyết định `boundary(now, cap=timestep)`; interval online của optimizer
  `boundary(now, cap=timestep, include_unseen_arrivals=False, online=True)` (= `_online_observation` cũ, #7).
- Backend: `propose` dùng `boundary(now, cap=15, scenario=với tariff, online=True)`. Xe đã đặt lịch là thông tin đã
  biết nên được tính. Interval optimizer = khoảng tới mốc đó (thay cho 15' cố định, #3, #5).
- Backend runtime: trạm giữ `next_decision_minute` = `interval_end` của lần propose gần nhất. Vòng benchmark và
  `run_forever` phát `TICK` khi tới mốc này (thay cho TICK theo bội số 15' tính từ lúc khởi động). Sự kiện xe đến /
  rời / huỷ / đổi / cổng lỗi / khôi phục / nguồn đổi / sạc xong vẫn gây tính lại ngay.
- Không replan trùng: vòng benchmark gom mọi sự kiện của cùng một phút (booking, sự cố, sự kiện trạm, TICK) và gọi
  `on_event` một lần (sự cố nguồn vẫn chạy trước, AC5). Thứ tự: sự kiện môi trường → bảo vệ khẩn cấp → tính lại.

## 4. Planning Core và vị trí consent / Business Guard / HITL

```text
kernel.propose  (thuần: không mutate)
  1. limits = effective_limits(cfg, now)                       (một object, dùng lại cho mọi bước dưới)
  2. dispatch theo vùng → validate_dispatch                    (không connect: quan sát sau-dispatch dựng ảo, #8)
  3. candidates = xe đang CHARGING + xe vừa gán, allowed(interval)
  4. observation / planning (interval online, `_online_observation`)
  5. coordinator → validate_budgets ; optimizer theo vùng
  6. guard(cfg, candidates, setpoints, budgets, limits=limits)  ← Physical Guard trước
business (chỉ backend)
  7. consent: `_start_minimums` + `_fit_with_minimums` (hybrid_planner, logic giữ nguyên)
  8. kernel.approve(proposal, setpoints) → nếu khác đề xuất: guard(...) LẦN NỮA, cùng candidates / budgets / limits
  9. SchedulePlan → diff_commands → guard/dispatcher.py: 7 luật Business Guard → HITL (approval) → apply_commands
kernel.apply_approved / apply_commands → kernel.connect + kernel.hold_setpoint
kernel.advance → Physical Guard sau
```

- Quan sát sau-dispatch dựng ảo phải trùng với quan sát sau `queue.connect` thật: cùng state `CHARGING`, cổng,
  `charge_started = now`, thứ tự `occupied` (cổng mới thêm cuối theo thứ tự connector), thứ tự hàng chờ. Golden và
  DecisionTrace là bằng chứng.
- Offline không có consent: `approve(proposal)` không đổi setpoint ⇒ **không** gọi guard lần ba (test
  `test_coordinator_and_guards_share_the_same_snapshot_before_and_after` đếm đúng 2 lần / quyết định).
- Lệnh bị HITL giữ thì setpoint cũ tiếp tục chạy (#12). Đây là hành vi nghiệp vụ đã có, giữ nguyên.

## 5. Assigned budget ≠ hardware cap

- **Hard physical** (cổng, tủ, trần vùng vật lý `physical_zone_cap_kw`, nguồn chung / độc lập, acceptance xe):
  Physical Guard kiểm trước (propose / approve) và sau (advance).
- **Assigned budget** (`ZoneBudgets` của Coordinator): kiểm ở planning (`validate_budgets` + `guard(..., budgets)`) và
  trước khi gửi lệnh (approve dùng cùng `budgets`). Sau thực thi:
  - offline `strict`: một lời gọi `guard(cfg, candidates, actual, budgets.output_kw, limits)` (như cũ) — vượt budget
    hay vượt cap đều fail-closed;
  - backend: `guard(..., limits.zone_output_kw)` (chỉ hard, ADR-017, #11) và một phép đo riêng
    `budget_deviation_kw` = phần tổng vùng vượt budget của quyết định đang hiệu lực. Có sai lệch thì đếm
    `budget_deviation_count`, ghi log và phát `REPLAN_REQUESTED`.

## 6. Admission (quote / booking / change)

`services/admission.py::evaluate(rt, candidate, exclude=None) -> ScheduleProposal`:
1. `fork = rt.simulator.fork()` — bản sao sâu dưới khoá (EV2Gym, queue, setpoint, cổng lỗi, nguồn); trạm live không đổi.
2. Bỏ `exclude` (đổi yêu cầu), `fork.upsert_vehicle(visit_of(candidate))`.
3. Rollout tới `candidate.deadline`: ở mỗi mốc quyết định (lúc đầu, sự kiện của fork, `next_decision_minute`) gọi
   **cùng** `SimulatorScheduler.decide(fork, ctx)` (propose → consent → approve), rồi `fork.apply_approved(approved)`
   (chỉ fork nhận lệnh trực tiếp; trạm thật vẫn chỉ nhận lệnh qua dispatcher), rồi `fork.step(1)`.
4. Đọc kết quả của xe giả định từ chính fork: cổng được gán, lúc bắt đầu nhận điện, lúc đầy, năng lượng giao trước
   deadline (`outcomes()`, cùng quy tắc KPI), chi phí = Σ công suất × giá TOU từng phút, vị trí hàng chờ lúc `now`.
5. `feasible = có cổng ∧ thiếu ≤ 0,05 kWh`. Không khả thi → phương án thay thế (FR4, logic `_alternatives` giữ nguyên).

Khác biệt chủ ý so với thực thi thật, ghi trong report: rollout không chạy Business Guard 7 luật / HITL (fork không
phải trạm thật), không biết xe chưa đặt lịch và sự cố tương lai. Test: booking được chấp nhận ⇒ chạy runtime thật cùng
policy cho đúng thời điểm cắm / đầy / năng lượng như quote (§8).

**Số phận A–D** (đề xuất): bỏ. A_fcfs ≈ B0 (FCFS + equal share), B/C/D là LP backend không có DC taper / coordinator
và không cùng mô hình với thực thi. `StrategyName` vẫn giữ giá trị (đổi enum / OpenAPI / màn S8 là việc Phase 4);
chọn A–D thì `make_scheduler` báo lỗi rõ ràng. Nếu Tech Lead muốn giữ làm baseline, phải viết lại thành
`Registration` trong `src/optimizer/registry.py` (không khôi phục đường LP cũ).

## 7. Những gì không đổi

Thuật toán (`src/optimizer/{dispatch,zones,coordination}`, `registry.POLICIES`), `guard/physical/validator.py`,
charging models, `ev2gym_adapter.py`, `queue.py`, hợp đồng core cũ, công thức vật lý, objective, tham số solver,
consent / SLA. Cổng: `compare_ast_manifest.py` + golden (`pytest src/simulator/tests`, `compare_sim_output.py`).

## 8. Kế hoạch test

- Golden: 163 test simulator + `compare_sim_output.py` (MVP-1/2/3, VinFast, script mode, DecisionTrace, replay, events)
  so với output HEAD `749c042` và evidence 2026-11-22.
- Differential (`tests/test_refactor/test_differential.py`):
  - cùng policy / config / state ⇒ cùng `ProposedDecision` (offline kernel ↔ `HybridStation.kernel`, M2b / M3a / M3b,
    nguồn chung / độc lập, curtailment);
  - cùng setpoint đã duyệt + `physics_step=1` ⇒ cùng kết quả thực thi (offline 1' ↔ backend): AC, DC taper, xe đến /
    rời, deadline bất khả thi;
  - cổng lỗi, fallback solver (monkeypatch `linprog`) đi cùng một đường.
- Admission ↔ policy thực thi: quote khả thi ⇒ booking ⇒ chạy tiếp ⇒ đúng hạn, cùng thời điểm cắm / đầy.
- Backend: test cũ chạy lại; test hỏng tạm ghi `EXPECTED_FAILURES.md`.
