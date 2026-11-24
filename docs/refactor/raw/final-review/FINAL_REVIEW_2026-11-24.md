# **Final Review — ChargePilot Unified Core & MVP-3.5 Readiness**

Ngày 24/11/2026 · Branch `feature/unified-core` · Commit `e317391` · [Codebase được review](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/tree/e317391ec1db5c1885c5e3109c40548eb52d07c6?utm_source=chatgpt.com)

## **1. Trước tiên, tôi có còn nhớ MVP-3.5 không?**

**Có. MVP-3.5 là giai đoạn nâng cao tính thực tế, độ robust và chất lượng tối ưu của ChargePilot sau khi hoàn thành MVP-3, trước khi lựa chọn và triển khai tính năng AI chuyên sâu của MVP-4.**

Ngày 21/11, chúng ta đã trao đổi về việc hệ thống mô phỏng hiện tại vẫn hoạt động trong một môi trường tương đối lý tưởng, trong khi trạm sạc thực tế có nhiều yếu tố bất định.

Các hướng phát triển MVP-3.5 đã thảo luận gồm:

| Hướng nghiên cứu         | Nội dung                                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| **SOC uncertainty**      | SOC khai báo, SOC quan sát và SOC thực tế có thể khác nhau; optimizer cần thích nghi.                                                 |
| **Behavior uncertainty** | Xe đến muộn, rời sớm, thay đổi deadline hoặc kế hoạch sạc.                                                                            |
| **IoT uncertainty**      | Telemetry nhiễu, trễ, mất dữ liệu, sai thứ tự hoặc mất kết nối.                                                                       |
| **DC charging realism**  | Mô hình điện áp, dòng điện, giới hạn EVSE/BMS, SOC-dependent acceptance và đường cong sạc thực tế hơn.                                |
| **Robust optimization**  | Tối ưu và replan trong điều kiện bất định thay vì giả định mọi đầu vào đều chính xác.                                                 |
| **Global coordination**  | Cải thiện Dynamic Slack để tránh đánh đổi SLA của AC quá mức nhằm tăng throughput DC. Nghiên cứu QoS, fairness và tối ưu đa mục tiêu. |
| **Stress testing**       | Đánh giá độ robust, độ nhạy tham số, latency và mức độ vi phạm SLA trong các kịch bản khó.                                            |

Ngoài ra, trong quá trình refactor hôm qua, chúng ta đã thống nhất đưa **sự kiện giới hạn nguồn được thông báo trước** (`announced_at` / `effective_at`) vào MVP-3.5.

Lộ trình ChargePilot

**MVP-1 — Hybrid Simulator**

EV2Gym, AC/DC physics, Queue, Physical Guard

**MVP-2 — DC Optimization**

LLF Dispatch, DC Rolling Horizon LP

**MVP-3 — AC/DC/Global Optimization**

AC two-stage LP, Fixed Share, Dynamic Slack

**Unified Core Refactor**

Hợp nhất simulator, optimizer, Backend và Booking

**MVP-3.5 — Realism & Robust Optimization**

Giai đoạn nghiên cứu tiếp theo

**MVP-4 — Strong AI Feature**

Tích hợp tính năng AI chuyên sâu được lựa chọn sau nghiên cứu

Tôi cũng nhớ bốn ứng viên AI cho MVP-4 vẫn là Agentic Conflict Resolution & SLA Negotiation, IoT Anomaly Detection & Fault Diagnosis, Learning-based Scheduling và AI Decision Copilot (WHY/WHAT-IF/HOW-TO). Chúng ta chưa chính thức chọn một phương án.

**MVP-3.5 không phải một vòng refactor nữa.** Đây phải là giai đoạn nghiên cứu và cải tiến hệ thống thực sự, có giả thuyết, phương pháp, baseline, benchmark và kết quả định lượng. Phạm vi chi tiết và tiêu chí nghiệm thu riêng của MVP-3.5 vẫn chưa được đóng băng.

## **2. Kết quả kiểm toán codebase cuối Phase 4**

**Kết luận về kiến trúc: đạt phần lớn định hướng ban đầu. Tôi không đề xuất thực hiện thêm một đợt refactor toàn hệ thống.**

Tuy nhiên, tôi tìm thấy một số hạn chế mà báo cáo nghiệm thu của Claude chưa phản ánh đầy đủ. Đặc biệt, chúng sẽ ảnh hưởng khi bạn bắt đầu đưa uncertainty, optimizer có trạng thái và mô hình vật lý mới vào MVP-3.5.

### **2.1. Cấu trúc thư mục hiện tại**

Tôi đã kiểm tra cây thư mục thực tế trên GitHub. Đây là cấu trúc rút gọn của những thành phần chính:

&#x20;`src/`

&#x20;**models/**

Shared contracts, observations, decisions, constraints

&#x20;**optimizer/**

Toàn bộ thuật toán điều phối và tối ưu

dispatch/ — FCFS, EDF, LLF

zones/ — AC LP, DC LP, Equal Share

coordination/ — Fixed Share, Dynamic Slack

registry.py — đăng ký thuật toán và policy

&#x20;**guard/**

Physical Guard, Business Guard, HITL

physical/validator.py

physical/adapter.py

rules.py, dispatcher.py, approval.py

&#x20;**simulator/**

Một simulation kernel duy nhất

core/kernel.py

core/algorithms.py

core/charging_models/

core/queue.py

core/ev2gym_adapter.py

hybrid.py — offline facade

hybrid_station.py — backend adapter

evaluation/ — KPI, trace, replay

&#x20;**services/**

Runtime, orchestration, admission, decision trace

&#x20;**llm_chat/**

Resident-facing LangGraph Chat

&#x20;**agents/**

Dành riêng cho AI-1 / AI-4

&#x20;**forecast/**

Forecasting — chưa tích hợp F6 vào vận hành chính

So với phiên bản trước refactor, Claude đã thực sự loại bỏ:

- LP Backend A–D và các module phụ thuộc.
- `LiveStation`.
- `_charge_one_minute()` và `_decide()` — hai implementation trùng lặp.
- Toàn bộ package lồng `src/simulator/src/` và các compatibility shims tương ứng.
- Các strategy A–D trong hệ thống đang hoạt động.

Việc giữ `HybridSimulator` và `HybridStation` không phải là duy trì hai simulator nữa. Chúng đóng vai trò hai interface sử dụng chung một kernel.

Nguồn: [FINAL_MAP.md](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/docs/refactor/FINAL_MAP.md?utm_source=chatgpt.com).

### **2.2. Luồng thực thi mới**

CLI / Benchmark

Backend Runtime

Admission Fork

### **StationKernel**

**Planning Core**

Observe → Dispatch → Coordinator → Optimizer

**Physical validation**

ProposedDecision

**Approval & Actuation**

Backend/Admission qua consent, Business Guard và HITL

**Physical Core**

Queue · EV2Gym · DC model · Energy integration

**Post-execution validation**

AppliedResult

DecisionTrace

KPI / Replay

Station State

Đây chính là thay đổi có giá trị nhất của toàn bộ quá trình refactor: nếu bạn cải tiến thuật toán hoặc mô hình vật lý trong core, các thành phần khác có thể sử dụng chung implementation đó thay vì phải tái tạo thuật toán trên Backend.

## **3. Kết quả kiểm thử và hiệu suất**

Theo các log nghiệm thu được lưu trong repository:

Backend tests

# **520**

Passed · 8 skipped (forecast F6)

Simulator tests

# **163**

Passed, giữ golden

Frontend tests

# **28**

Lint, typecheck, build pass

AST preservation

# **114/114**

Định nghĩa được kiểm tra giữ nguyên

Backend benchmark

# **100**

Run · 4 policy × 5 scenario × 5 seed

Power-limit violations

# **0**

Quan sát được trong 100 run

Nguồn: [REFACTOR_REPORT.md](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/docs/refactor/REFACTOR_REPORT.md?utm_source=chatgpt.com), [pytest log](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/docs/refactor/raw/phase4-final/pytest_tests.txt?utm_source=chatgpt.com) và [final benchmark evidence](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/tree/e317391/eval/evidence/2026-11-24-unified-core-final-baseline?utm_source=chatgpt.com).

Tôi đã kiểm tra source và evidence, nhưng chưa tự chạy độc lập toàn bộ suite. E2E với Postgres thật, LLM thật và deployment Render cũng chưa được thực hiện.

### **Một bug quan trọng đã được Claude giải quyết**

Ở Phase 3, việc làm tròn setpoint lên khiến một lô lệnh có thể vượt giới hạn rất nhỏ, làm Guard chặn cả những lệnh hợp lệ và dẫn đến setpoint cũ tiếp tục được giữ.

Phase 4 đã chuyển sang làm tròn xuống và ưu tiên các lệnh giảm tải an toàn.

Đối với nhóm benchmark AC legacy B0 được trích trong báo cáo, kết quả trung bình thay đổi như sau:

Tỷ lệ hoàn thành đúng hạn

Phase 3

15.1%

Phase 4

19.8%

Số lệnh bị Guard chặn trung bình

Phase 3

63.4

Phase 4

0.6

So sánh trước/sau sửa lỗi Guard và làm tròn setpoint; không phải kết quả của một optimizer mới.

Đây là lý do chính đáng để tạo baseline Backend mới. Không nên coi việc tất cả KPI Phase 4 không còn trùng Phase 3 là regression.

## **4. Những vấn đề tôi phát hiện khi đọc trực tiếp code**

Đây là phần quan trọng nhất trước khi bạn bắt đầu MVP-3.5. Tôi phân loại theo mức độ ảnh hưởng đến nghiên cứu tiếp theo, thay vì yêu cầu Claude sửa mọi điểm chưa hoàn hảo.

### **4.1. Registry chưa thực sự linh hoạt hoàn toàn**

P1 — Khả năng mở rộng

Trong [hybrid_planner.py, dòng 40–45](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/src/services/hybrid_planner.py?utm_source=chatgpt.com#L40-L45):

```
POLICIES: Mapping[StrategyName, tuple[str, str, str, str]] = {    strategy: REGISTRY_POLICIES[strategy.value]    for strategy in (        StrategyName.SIM_B0,        StrategyName.SIM_M2B,        StrategyName.SIM_M3A,        StrategyName.SIM_M3B,    )}SIMULATOR_STRATEGIES = frozenset(POLICIES)POLICY_VERSION = "1"
```

Điều này có nghĩa nếu bạn tạo một policy `M35a`, chỉ thêm nó vào `registry.py` là **chưa đủ để Backend nhận diện**.

Bạn vẫn phải cập nhật enum, mapping và có thể cả Frontend/API.

Bên cạnh đó, test [test_registry_extension.py](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/tests/test_refactor/test_registry_extension.py?utm_source=chatgpt.com) chứng minh việc thay optimizer bằng cách tạm ghi đè M2b, chứ chưa chứng minh việc đăng ký một policy hoàn toàn mới mà không chỉnh orchestration.

Đây là hai mức extensibility khác nhau.

| Thao tác                                    | Hiện tại       |
| ------------------------------------------- | -------------- |
| Thêm DC Optimizer mới                       | Được           |
| Thêm AC Optimizer mới                       | Được           |
| Thêm Global Coordinator mới                 | Được           |
| Chọn optimizer khác trên CLI                | Được           |
| Thêm policy độc lập và Backend tự nhận diện | Chưa hoàn toàn |
| Chọn DC charging model từ Backend config    | Chưa hoàn toàn |
| Version riêng cho từng policy mới           | Chưa đầy đủ    |

**Đề xuất:** Đây nên là một task nhỏ đầu MVP-3.5. Backend tra cứu policy trực tiếp từ registry; config chọn policy ID, version, model và tham số. API công bố danh sách policy hợp lệ từ cùng nguồn.

Không ghi đè M3a để thử nghiệm optimizer mới vì sẽ phá ý nghĩa của baseline.

### **4.2. DC Vehicle Profiles vẫn chưa tích hợp hoàn toàn với Backend**

P1 — Trực tiếp liên quan MVP-3.5

Trong [hybrid_station.py](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/src/simulator/hybrid_station.py?utm_source=chatgpt.com#L115-L117):

```
@classmethoddef with_vinfast_profiles(cls, *args, **kwargs):    raise NotImplementedError(        "Profile DC VinFast chưa nối vào HybridStation — truyền dc_model tự dựng"    )
```

Và khi khởi tạo trạm:

```
adapter = EV2GymAdapter(    scenario,    self._dc_model or SyntheticTaperV1())
```

Trong khi đó, offline simulator đã hỗ trợ lựa chọn `vinfast_profiles_v0_1`.

Nghĩa là **đã dùng chung engine nhưng chưa dùng chung hoàn toàn cơ chế lựa chọn mô hình vật lý**.

Nếu bạn phát triển mô hình DC mới có voltage, current, BMS acceptance và thermal derating, chỉ đăng ký model trong offline registry chưa bảo đảm Backend sẽ tự sử dụng model đó.

Tôi đề xuất bổ sung vehicle-profile provider hỗ trợ xe đến động, vì offline biết trước danh sách xe còn Backend thì không.

### **4.3. Chưa có sự phân biệt Ground Truth và Observed State**

P1 — Nền tảng nghiên cứu MVP-3.5

Trong [observations.py](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/src/models/scheduling/observations.py?utm_source=chatgpt.com), hiện tại `VehicleObservation` có một trường `soc` và một đối tượng `Vehicle` chứa deadline.

Điều đó phù hợp với simulator lý tưởng, nhưng không đủ khi chúng ta đưa telemetry uncertainty vào.

#### **Hiện tại — MVP-3**

Physical State

SchedulingObservation

Optimizer

#### **Kiến trúc đề xuất — MVP-3.5**

**Ground Truth**

SOC, deadline, physics thực tế

**Declared State**

SOC và yêu cầu cư dân khai báo

**Telemetry / Observation Layer**

Noise · Delay · Missing Data · Stale Data

**Estimated State**

Giá trị ước lượng, timestamp và uncertainty

Robust Optimizer

Ground truth trong mô phỏng phải được dùng để đánh giá và thực thi physics, **không được vô tình cung cấp cho optimizer**.

Nếu không tách hai lớp này ngay từ đầu, thí nghiệm uncertainty rất dễ mắc lỗi data leakage: giả vờ telemetry bị nhiễu nhưng optimizer vẫn đọc được SOC thực từ adapter.

### **4.4. Admission fork đang chia sẻ đối tượng thuật toán**

P1 — Stateful modules

Trong [kernel.py, dòng 93–110](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/src/simulator/core/kernel.py?utm_source=chatgpt.com#L93-L110):

```
twin = copy.copy(self)memo = {    id(self.scenario): self.scenario,    id(self.adapter.dc_model): self.adapter.dc_model}twin.queue, twin.adapter = copy.deepcopy(    (self.queue, self.adapter), memo)
```

Trong docstring, Claude xác định các thuật toán hiện tại là stateless nên có thể chia sẻ.

Điều này hợp lý với LP và các charging model không thay đổi trạng thái hiện tại. Tuy nhiên, trong MVP-3.5 và MVP-4, bạn có thể thêm:

- Optimizer lưu trạng thái warm-start.
- Online state estimator.
- Forecasting model có bộ nhớ lịch sử.
- Stochastic charging model.
- Bộ sinh số ngẫu nhiên.
- Learning-based scheduling.

Khi đó, một lượt WHAT-IF có thể vô tình thay đổi trạng thái model của hệ thống vận hành.

**Đề xuất:** Quy định rõ module nào immutable/stateless được phép dùng chung; module có trạng thái phải có cơ chế `fork()` hoặc snapshot độc lập. Thêm test mutation isolation trước khi đưa stochastic simulation vào.

### **4.5. Cần kiểm tra lại Guard khi chỉ một phần lô lệnh được thực thi**

P0 — Safety correctness

Đây là vấn đề cần ưu tiên hơn clean code.

Trong [guard/dispatcher.py](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/src/guard/dispatcher.py?utm_source=chatgpt.com#L69-L145), Claude đã bổ sung kiểm tra lại các lệnh tăng công suất nếu một lệnh khác bị giữ vì HITL:

```
to_apply, dropped = (    _without_unsafe_increases(to_apply, ctx)    if held    else (to_apply, []))
```

Tuy nhiên, một lệnh giảm công suất cũng có thể không được thực thi vì **Business Guard từ chối**, chứ không phải vì HITL.

Nếu lệnh tăng được kiểm tra dựa trên giả định lệnh giảm trong cùng lô sẽ được thực hiện, nhưng sau đó lệnh giảm bị chặn, tập lệnh thực tế cần được kiểm tra lại.

Tôi chưa tái hiện lỗi bằng test, nhưng điều kiện `if held` cho thấy đây là một đường thực thi có nguy cơ bị bỏ sót.

**Cần có negative test riêng và xác nhận mọi tập lệnh thực sự gửi tới actuator đều an toàn**, kể cả khi một phần lô bị rejected, expired hoặc stale. Ngoài ra, kiểm tra cơ chế fail-safe khi kernel phát hiện hard violation: hiện chế độ Backend chủ yếu ghi log và tiếp tục, chưa có hành động khẩn cấp trực tiếp từ `_after_apply_violation()`.

### **4.6. Booking concurrency và tính nhất quán của snapshot**

P1 — Tính đúng đắn nghiệp vụ

Trong [charging_service.py, dòng 209–261](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/src/services/charging_service.py?utm_source=chatgpt.com#L209-L261), luồng booking hiện có thứ tự:

```
Kiểm tra booking đang tồn tại
        ↓
Tạo candidate
        ↓
await Admission.evaluate(...)
        ↓
Lưu booking vào repository
        ↓
Lấy runtime lock
        ↓
Cập nhật simulator
```

Hai yêu cầu đồng thời có thể cùng kiểm tra và chạy admission trên trạng thái chưa có booking của yêu cầu kia. Tôi chưa xác nhận có cơ chế transaction hoặc ràng buộc database đủ để ngăn mọi trường hợp race này.

Ngoài ra, admission chạy trên candidate có consent mặc định; consent thực tế của người dùng được đưa vào booking sau đó. Điều này có thể làm điều kiện mô phỏng khác điều kiện thực thi.

Cần test concurrency, state-version revalidation và consent parity. Không nhất thiết phải khóa toàn bộ trạm trong suốt quá trình rollout dài; có thể dùng optimistic concurrency control và kiểm tra lại khi commit.

### **4.7. Benchmark chưa đủ tin cậy cho mọi nghiên cứu về sự cố**

P1 — Research validity

Trong [simulation_service.py](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/src/services/simulation_service.py?utm_source=chatgpt.com#L160-L210), nếu một incident trỏ vào đầu nối không tồn tại, chương trình sẽ bắt `ValueError`, ghi chú sự cố bị bỏ qua và tiếp tục benchmark.

Điều này xuất phát từ các kịch bản legacy chưa khớp topology hiện tại.

Đối với demo thông thường, một cảnh báo có thể đủ. Nhưng đối với MVP-3.5, nếu chúng ta nghiên cứu robustness trước connector fault hoặc power drop, một benchmark có tên `connector_failure` mà sự cố không thực sự diễn ra sẽ làm sai ý nghĩa kết quả.

**Đề xuất:** Chế độ research benchmark phải fail-fast khi incident không hợp lệ và ghi số lượng sự kiện dự kiến/thực thi. Không sửa evidence cũ; tạo benchmark suite MVP-3.5 mới.

## **5. Hiệu suất đã tối ưu chưa?**

**Đủ tốt để tiếp tục phát triển MVP, nhưng chưa thể kết luận đã được tối ưu toàn diện.**

Tôi đánh giá việc Claude giữ một worker thread duy nhất cho SciPy/HiGHS là hợp lý trong bối cảnh nhóm đã ghi nhận native crash trên Windows khi gọi solver từ nhiều thread.

Tuy nhiên, kiến trúc này cũng có nhược điểm: admission, runtime replan và các thí nghiệm WHAT-IF có thể tranh nhau cùng một solver worker.

| Thành phần                               | Đánh giá                                                         |
| ---------------------------------------- | ---------------------------------------------------------------- |
| Sparse matrix trong LP                   | Tốt                                                              |
| Rolling horizon thay vì giải toàn cục    | Tốt                                                              |
| Event-driven replanning                  | Tốt                                                              |
| Tách solver khỏi event loop              | Tốt                                                              |
| Admission rollout từng phút tới deadline | Có chi phí đáng kể khi mở rộng                                   |
| Deep copy EV2Gym và queue                | Hợp lý ở quy mô nhỏ                                              |
| Solver worker dùng chung                 | An toàn hơn cho môi trường hiện tại, nhưng có thể tạo bottleneck |
| DecisionTrace                            | Rất hữu ích, cần kiểm soát chi phí lưu trữ                       |
| Quy mô 50–100 đầu nối                    | Chưa đủ benchmark để kết luận                                    |

Nguồn: [solver.py](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/src/services/solver.py?utm_source=chatgpt.com), [admission.py](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/blob/e317391/src/services/admission.py?utm_source=chatgpt.com).

Tôi **không khuyên chuyển ngay sang multiprocessing, Redis, Celery hoặc viết lại solver**. Hãy profile trước, xác định bottleneck bằng số đo, sau đó mới cải tiến.

Đối với một dự án thiên về nghiên cứu tối ưu như ChargePilot, p95 solver latency, p95 end-to-end replan latency và p95 quote latency cần được đo riêng.

## **6. Chấm điểm codebase sau refactor**

Đây là điểm đánh giá kỹ thuật chủ quan của tôi dựa trên phạm vi đã kiểm tra, không phải kết quả của một công cụ đo tự động.

Modularity — phân tách module

9/10

Đồng bộ Simulator / Backend

9/10

Extensibility — dễ thay thuật toán

8/10

Clean code và dependency boundaries

8.5/10

Regression & reproducibility

9/10

Safety & execution correctness

7.5/10

Performance & scalability

7.5/10

Readiness cho MVP-3.5

8.5/10

**Đánh giá tổng thể**

Đủ tốt làm nền tảng R&D tiếp theo

# **8.4/10**

Không đạt 10/10 vì khả năng mở rộng policy vẫn chưa hoàn chỉnh, state isolation còn dựa vào giả định stateless, một số edge case về safety/concurrency chưa được chứng minh và hiệu suất ở quy mô lớn chưa được kiểm định.

Nhưng so với trước khi bắt đầu Phase 0, kiến trúc hiện tại đã tiến bộ rõ rệt.