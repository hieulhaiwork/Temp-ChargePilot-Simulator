# Kế hoạch refactor Unified Core (bản sửa 2026-11-23, sau review Phase 2)

> Quyết định: ADR-019 (mục "Quyết định 2026-11-23 sau review Phase 2"). Bản này thay lộ trình Phase 3–6 của guide.
> Phase 0–2 đã xong và đã duyệt (`BASELINE.md`, `PHASE1_REPORT.md`, `PHASE2_REPORT.md`).

## Nguyên tắc

- **Thay thế, không chạy song song.** Một Planning Core, một Physical Core, một registry/policy. Xoá đường cũ khi đã
  có đường thay thế. Không thêm shim / adapter để giữ thiết kế đã bỏ.
- **Bảo toàn:**
  - code gốc simulator MVP-1/2/3: dispatch, zones (AC/DC LP), coordination, Physical Guard validator, charging models,
    EV2Gym adapter, queue;
  - công thức vật lý, objective, tham số solver, hard safety constraints;
  - golden và `eval/evidence/**`.

  Mọi thay đổi semantics: phân loại (bug fix / quyết định đã duyệt / cần escalate) và ghi riêng.
- **Backend/Frontend được phép tạm hỏng** giữa các commit. Mỗi lần như vậy ghi vào
  `docs/refactor/EXPECTED_FAILURES.md` (test nào, vì sao, commit nào sẽ sửa). Không xoá test, không làm yếu safety
  check để che lỗi.
- **Cổng kiểm** (`scripts/refactor/`, mọi script exit 1 khi lệch): `compare_ast_manifest.py` cho code gốc được bảo
  toàn; `compare_sim_output.py` cho golden ở chế độ tương thích; `compare_backend_benchmark.py` chỉ dùng khi semantics
  backend được giữ.
- Commit nhỏ, độc lập, message `type(scope): mô tả`. Không push / merge `develop` / `main`, không force-push, không
  deploy.

## Phase 3 — Unified Runtime + Booking Migration (dừng cuối phase để Tech Lead review)

1. Thiết kế contract (`docs/refactor/PHASE3_DESIGN.md`) trước khi code:
   - kernel `observe / propose / apply_approved / advance`;
   - `ProposedDecision → ApprovedDecision → AppliedResult` (immutable, có policy/version, `state_version`, interval,
     effective limits, diagnostics, reason codes);
   - ba tham số thời gian `physics_step_minutes`, `decision_interval_minutes`, `planning_horizon_minutes` (P1);
   - một hàm boundary sự kiện;
   - admission.
2. **Physical Core** dùng chung: một vòng tích phân. `HybridSimulator` (CLI / benchmark) và `HybridStation`
   (backend) gọi cùng core; xoá `HybridStation._charge_one_minute`. Chế độ tương thích (`physics_step = interval`)
   giữ golden lịch sử.
3. **Planning Core** dùng chung: dispatch → coordinator → optimizer → Physical Guard, gồm `_online_observation`.
   `SimulatorScheduler` gọi core; xoá `_decide`. Consent / Business Guard / HITL đứng sau `propose` và trước
   `apply_approved`; mọi chỉnh sửa do consent phải qua lại **cùng** Physical Guard.
4. **Sự kiện / replan:**
   - replan khi sạc xong / phiên đổi trạng thái, xe đến / rời / huỷ / đổi yêu cầu, nguồn / tủ đổi / mất /
     khôi phục, mốc TOU đã công bố, tick định kỳ;
   - không replan trùng, có thứ tự sự kiện, không dùng thông tin chưa công bố.
5. **Hai loại ràng buộc:**
   - hard physical: Physical Guard kiểm trước + sau thực thi;
   - assigned budget của Coordinator: kiểm khi planning và trước khi gửi lệnh; vượt thì ghi sai lệch và
     xử lý / replan.
6. **Quote / Booking Admission / Feasibility** dùng Planning Core + Physical Core trên bản sao trạng thái (không
   mutate live). Chuyển mọi caller của LP backend cũ (`optimizer/{assignment,lp_model,horizon,mpc,baselines,base,
   strategies}`) rồi xoá; quyết định số phận A–D (bỏ, hoặc giữ làm baseline được quản lý trong registry). Có test:
   booking được chấp nhận không mâu thuẫn với ràng buộc của policy thực thi.
7. **LiveStation:** xoá khi không còn caller, ghi vào `DELETION_MANIFEST.md`.
8. **Differential tests:**
   - cùng policy / config / state → cùng plan;
   - cùng setpoint đã duyệt + physics config → cùng kết quả thực thi (CLI ↔ backend);
   - phủ M2b / M3a / M3b, nguồn chung / độc lập, curtailment, DC taper, xe đến / rời, cổng lỗi, deadline bất khả
     thi, fallback solver.
9. `docs/refactor/PHASE3_REPORT.md`: kiến trúc thực tế, moved / deleted / kept, bằng chứng "một engine", số liệu
   cổng kiểm, expected failures còn lại, câu hỏi cho Tech Lead.

**Escalate** (dừng phần đó, hỏi): khi phải đổi công thức vật lý, objective, tham số solver, hard safety semantics, dữ
liệu quan trọng, hoặc mục tiêu nghiệp vụ đã chốt (SLA / quote / consent / quyền).

## Phase 4 — Cleanup + Final Integration (sau review Phase 3)

1. Resident-facing LangGraph chat → `src/llm_chat/`. LLM provider ở `src/services/llm.py`. `src/agents/` để dành
   cho AI-1 / AI-4. **Làm song song với Phase 3** trên nhánh riêng (`feature/unified-core-llmchat`), vì độc lập với core.
2. Xoá mọi shim, `__getattr__` tương thích, đường import cũ, tài liệu lỗi thời. Đánh dấu ADR-011/016/017/018
   superseded / amended.
3. Cập nhật consumers, API schema, OpenAPI, Frontend nếu cần.
4. Nghiệm thu E2E: booking → planning → Guard/HITL → physical execution → replay / KPI. Golden, differential,
   stress / negative safety, Backend / Frontend test, E2E, benchmark cuối. `FINAL_MAP.md`, `REFACTOR_REPORT.md`,
   `DELETION_MANIFEST.md`.

## Definition of Done

- Một Planning Core, một Physical Core, một registry / policy composition.
- Quote / Booking không còn dùng LP backend cũ độc lập.
- Không còn hai implementation vật lý / điều phối song song.
- Thêm / thay optimizer AC, DC hoặc Global qua registration + config, không viết lại orchestration backend.
- Simulator standalone và backend dùng cùng source logic.
- Physical Guard và Business Guard / HITL đúng vị trí.
- Test và benchmark cuối tái lập được; mọi khác biệt chủ ý được ghi nhận.

## Phân công (2026-11-23)

| Nhánh | Người làm | Việc | Brief |
|---|---|---|---|
| `feature/unified-core-p3` | claude2 (cửa sổ tương tác) | Phase 3 | `docs/refactor/tasks/PHASE3_BRIEF.md` |
| `feature/unified-core-llmchat` | claude3 (cửa sổ tương tác) | Phase 4 mục 1 (LLM chat) | `docs/refactor/tasks/LLMCHAT_BRIEF.md` |
| `feature/unified-core` | Claude điều phối | gộp nhánh, chạy cổng kiểm, đồng bộ mirror | — |
