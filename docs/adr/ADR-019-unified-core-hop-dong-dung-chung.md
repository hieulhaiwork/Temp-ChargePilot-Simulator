# ADR-019: Unified Core — một lõi mô phỏng/tối ưu, hợp đồng dùng chung ở `src/models`

- Trạng thái: Proposed — người phụ trách đã duyệt hướng và Phase 0–1 (2026-11-23). Phase 2+ duyệt theo từng phase.
- Ngày: 2026-11-23
- Liên quan: **sửa đổi ADR-018 điểm 4** ("không sửa `src/simulator/src/`"): từ Phase 1, code gốc được *di chuyển*
  (logic giữ nguyên, chứng minh bằng hash AST) và vị trí cũ thành re-export. Ảnh hưởng ADR-011, ADR-016, ADR-017
  (đánh dấu ở Phase 6). Bằng chứng: `docs/refactor/{BASELINE,MODULE_PROVENANCE,IMPORT_GRAPH,PHASE0_FINDINGS}.md`,
  `docs/refactor/PHASE1_REPORT.md`.

## Bối cảnh

Phase 0 đo được ba đường thực thi:
- `HybridSimulator` offline;
- `SimulatorScheduler._decide` + `HybridStation._charge_one_minute`, hai đường này **chép lại** một phần
  `HybridSimulator.step`;
- LP backend A–D, cũng là đường quote/booking tính `_what_if`.

Có 18 khác biệt đã ghi lại (PHASE0_FINDINGS §2). Muốn đưa thuật toán về `src/optimizer` và Guard vật lý về
`src/guard` mà không tạo vòng import, các kiểu dữ liệu dùng chung (Scenario, observation, budget, limits, DC model
Protocol) phải nằm ở một tầng thấp hơn cả ba. Hiện chúng nằm trong `src/simulator/src/`, và `safety/guard.py` lại
import kiểu của optimizer (`ZoneBudgets`, `DispatchObservation`), còn optimizer import `valid_kw` của guard.

Ràng buộc từ người phụ trách: simulator **phải chạy standalone** (CLI, benchmark MVP-1/2/3, golden, DecisionTrace)
mà không cần FastAPI, DB hay LLM, và standalone dùng **cùng** Planning Core + Physical Core với backend.

## Lựa chọn

1. Giữ hai simulator (R&D và backend), đồng bộ bằng test parity. Loại: đây chính là nguồn drift đã đo được.
2. Chuyển thẳng file theo tên folder đích. Loại: tạo vòng `optimizer ↔ guard` (IMPORT_GRAPH §3).
3. **Tách hợp đồng thuần (stdlib) xuống `src/models`, rồi di chuyển cơ học theo từng phase, có shim và hash AST.**

## Quyết định

1. **Lớp hợp đồng core** (Phase 1, đã làm). Các file được chuyển nguyên văn, chỉ đổi import tương đối thành tuyệt đối:
   - `src/models/simulation_core.py` ← `simulator/src/scenario.py`
   - `src/models/charging_physics.py` ← `charging_models/base.py`
   - `src/models/physical_constraints.py` ← `safety/constraints.py`, cộng thêm `valid_kw` chuyển từ `safety/guard.py`
   - `src/models/physical_limits.py` ← `safety/limits.py`
   - `src/models/scheduling/{observations,dispatch,coordination,optimization}.py` ← `observations.py`,
     `dispatch/base.py`, `coordination/base.py`, `optimizers/base.py`

   Nhóm này **chỉ dùng stdlib**, không dùng pydantic, nên simulator standalone import được.
2. **Vị trí cũ là shim re-export** (cùng đối tượng, `is` giữ nguyên). Code gốc của simulator chưa phải sửa import.
   Ngoài `src/simulator/`, mọi nơi phải import hợp đồng từ `src.models`.
3. **Đồ thị tầng đích** (một chiều, không vòng):
   ```text
   models (hợp đồng thuần) ◄── optimizer (dispatch, zones, coordination, registry)
          ▲                 ◄── guard.physical (hard constraints)       guard (business: rules/approval/dispatcher)
          │                 ◄── simulator (engine, charging_models, evaluation) ──► optimizer, guard.physical
   services ──► tất cả (orchestration, admission, runtime)   llm_chat ──► services, models   agents (AI-1/AI-4) ──► services
   ```
   Phase 1 chưa đổi bảng `BOUNDARIES`. Đường `simulator → optimizer/guard` sẽ được mở ở Phase 2, khi thuật toán thật sự
   đã được chuyển, và phải sửa ADR này cùng lúc.
4. **Danh sách adapter chuyển tiếp** được chạm `src.simulator.src.*` từ ngoài simulator (khoá bằng test):
   `src/simulator/hybrid_station.py`, `src/services/hybrid_planner.py`, `src/guard/physical.py`,
   `tests/test_simulator/test_hybrid_station.py`. Phase 2–3 thu hẹp danh sách này về rỗng.
5. **Standalone.** Thêm test chạy subprocess có bộ chặn import: import CLI, benchmark, engine, evaluation khi chặn
   `pydantic/fastapi/starlette/sqlalchemy/alembic/langchain/langgraph/openai` phải thành công. Thêm test chạy
   `python src/simulator/run.py`. Riêng entrypoint `run.py` ở chế độ script đặt gốc repo lên đầu `sys.path`; đây là
   chỗ duy nhất làm việc này.
6. **Quyết định đã chốt cho các phase sau** (chưa cài; ghi lại để không trôi):
   - Thời gian (P1): một kernel có cấu hình với `physics_step_minutes`, `decision_interval_minutes`,
     `planning_horizon_minutes`. Backend dùng vật lý 1'. Standalone có chế độ tương thích để giữ golden. Không so
     benchmark giữa hai cấu hình thời gian khác nhau.
   - Replan khi: sạc xong / phiên đổi trạng thái; xe đến / rời / huỷ / đổi yêu cầu; nguồn / tủ đổi, mất, khôi phục;
     mốc TOU đã công bố; tick định kỳ. Không trùng, có thứ tự, không dùng thông tin chưa công bố.
   - Hai loại ràng buộc: **hard physical**, do Physical Guard kiểm trước + sau thực thi; **assigned budget** của
     Coordinator, kiểm ở bước planning và trước khi gửi lệnh, nếu vượt thì ghi sai lệch rồi xử lý / replan.
   - `src/services/llm.py` là provider dùng chung. Chat cư dân chuyển sang `src/llm_chat/`. `src/agents/` để dành cho AI-1/AI-4.
   - Quote / Admission / Scheduling / Standalone / WHAT-IF dùng cùng nguồn logic tối ưu. Không xoá
     `optimizer/{lp_model,assignment}` khi `_what_if` còn dùng.

## Hệ quả

- `src/simulator/src/` có 8 file shim. `safety/guard.py` đổi đúng phần import (`valid_kw` lấy từ
  `src.models.physical_constraints`). Hash AST của 198/198 hàm/lớp top-level trùng Phase 0.
- `src/simulator/run.py` đổi nhánh script-mode (bootstrap `sys.path`). Đây là thay đổi duy nhất ở mức module ngoài
  import.
- Kiểu dataclass đổi `__module__` (ví dụ `Scenario.__module__ == "src.models.simulation_core"`). Golden và report
  không chứa trường này. Metadata `implementation` của thuật toán chưa đổi vì thuật toán chưa di chuyển.
- `tests/test_architecture.py` thêm 9 test (nhóm 7), không xoá hay nới luật cũ.
- Rủi ro: shim là lớp gián tiếp tạm thời và phải xoá ở Phase 6 khi không còn caller (deletion manifest).

## Cập nhật Phase 2 (2026-11-23)

1. **Thuật toán** đã chuyển về `src/optimizer/`:
   - `dispatch/` (arrival_order, edf, least_laxity);
   - `zones/` (ac_lp, rolling_lp, equal_share, deadline_first);
   - `coordination/` (fixed_budget, dynamic_slack);
   - `registry.py`: `Registration`, `DISPATCH`, `OPTIMIZERS`, `COORDINATORS`, và **một** bảng `POLICIES`
     B0/M2b/M3a/M3b, dùng chung cho `benchmark_mvp3` và `hybrid_planner`.

   Phần ghép với vật lý (`Algorithms`, `DC_MODELS`, `resolve_algorithms`) ở lại `src/simulator/src/algorithms.py`.
2. **Physical Guard gốc** nằm ở `src/guard/physical/validator.py`. Adapter backend nằm ở
   `src/guard/physical/adapter.py`. `src/guard/physical/__init__.py` chỉ nạp validator; tên cũ của adapter còn dùng
   được qua `__getattr__` (tương thích tạm).
3. `StationReader`/`StationActuator`/`VehicleVisit` chuyển sang `src/models/station_protocols.py`, để
   `guard/dispatcher.py` không import simulator.
4. `src/optimizer/__init__.py` không import gì. `get_scheduler` nằm ở `src/optimizer/strategies.py`; tên cũ vẫn dùng
   được qua `__getattr__`.
5. **Luật ranh giới mới** (`tests/test_architecture.py`):
   - simulator được import `src.optimizer.{dispatch,zones,coordination,registry}` và `src.guard.physical.validator`,
     không gì khác của optimizer/guard;
   - guard cấm import simulator;
   - gói thuật toán chỉ import hợp đồng core;
   - đồ thị `models/optimizer/guard/simulator` không vòng, tính cả import tương đối.
6. Shim ở vị trí cũ là alias `sys.modules` (cùng object module), để test patch `linprog` vẫn tác động đúng
   implementation. Danh sách shim còn lại: `docs/refactor/PHASE2_REPORT.md` §4.
