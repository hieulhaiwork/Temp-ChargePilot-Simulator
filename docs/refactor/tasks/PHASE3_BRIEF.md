# Brief giao việc — Phase 3: Unified Runtime + Booking Migration (claude2)

Bạn làm Phase 3 của refactor Unified Core cho ChargePilot (P-019). Đọc theo thứ tự trước khi code:
1. `CLAUDE.md` (gốc repo)
2. `docs/refactor/PLAN.md`: **kế hoạch hiện hành; mục Phase 3 là phạm vi của bạn**
3. `docs/adr/ADR-019-unified-core-hop-dong-dung-chung.md`: đặc biệt mục "Quyết định 2026-11-23 sau review Phase 2"
4. `docs/refactor/PHASE0_FINDINGS.md` §2–§4: 18 khác biệt `HybridSimulator` ↔ `HybridStation`/`SimulatorScheduler`,
   khác biệt quote ↔ lịch thật, phân tích interval
5. `docs/refactor/PHASE2_REPORT.md`: vị trí code sau Phase 2, shim còn lại, cổng kiểm

## Môi trường

- Làm **chỉ** trong worktree này, nhánh `feature/unified-core-p3`. Không đụng `D:\VIN\P-019` (repo chính, nhánh
  `feature/unified-core` do Claude điều phối giữ) và không đụng worktree `llmchat`.
- Python: `D:\VIN\P-019\.venv\Scripts\python.exe` (worktree không có `.venv` riêng). Ví dụ:
  `D:\VIN\P-019\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`.
- Windows: ghi log bằng `PYTHONIOENCODING=utf-8`; file log mới để xuống dòng LF.

## Quy tắc bắt buộc (của chủ dự án)

- Commit nhỏ, message `type(scope): mô tả` bằng tiếng Việt (type ∈ feat, fix, docs, test, refactor, chore).
  **Không thêm dòng `Co-Authored-By` hay `Claude-Session`** vào commit.
- **Không `git push`** đi đâu cả (cả `origin` lẫn mirror). Không merge, không rebase nhánh khác, không force, không
  `reset --hard` trên commit đã có, không deploy. Claude điều phối sẽ gộp và đồng bộ.
- Không tắt hook `.ai-log`, không `--no-verify`.
- Không ghi `eval/results/benchmark.{json,md}`. Chạy `eval/run_benchmark.py` thì đặt `RESULTS_DIR` ra thư mục tạm,
  như trong `eval/evidence/2026-11-23-refactor-phase2/README.md`. Evidence mới để ở
  `eval/evidence/2026-11-23-refactor-phase3/`, có commit / policy / seed / môi trường.
- Không xoá / sửa `eval/evidence/**` cũ, golden của simulator, `src/simulator/docs/MVP{2,3}_BENCHMARK.md`.
- Không đưa đường dẫn cá nhân (`C:\Users\...`, `D:\VIN\...`) vào file commit. Thay bằng `<REPO>` / `<LOCAL_TMP>`.

## Phạm vi (theo `PLAN.md` Phase 3)

Làm theo thứ tự, mỗi bước commit riêng và chạy test phù hợp:

1. **`docs/refactor/PHASE3_DESIGN.md` trước khi code.** Nội dung:
   - contract kernel (`observe / propose / apply_approved / advance`, thêm / bớt xe, sự cố);
   - `ProposedDecision / ApprovedDecision / AppliedResult` (immutable, `policy_id` + version, `state_version`,
     interval, effective limits, diagnostics, reason codes; phân biệt rejected-before-apply và violation-after-apply);
   - ba tham số thời gian P1 và chế độ tương thích golden; nêu giới hạn của P1 và đối chiếu P2 / P3;
   - hàm boundary sự kiện duy nhất;
   - vị trí consent / Business Guard / HITL;
   - assigned budget ≠ hardware cap;
   - thiết kế admission (quote / booking chạy trên bản sao trạng thái, cùng core).

   Đặt contract thuần ở `src/models` (stdlib) nếu simulator standalone cần.
2. **Physical Core** một vòng tích phân, dùng chung cho `HybridSimulator` và `HybridStation`. Xoá
   `HybridStation._charge_one_minute`.
3. **Planning Core** dùng chung (gồm `_online_observation`). Xoá `SimulatorScheduler._decide`. Consent đứng sau
   propose; mọi plan sau consent phải qua lại cùng Physical Guard.
4. **Replan events + budget checks** (PLAN.md mục 4–5).
5. **Admission:** quote / booking dùng core. Chuyển caller của `src/optimizer/{assignment,lp_model,horizon,mpc,
   baselines,base,strategies}` rồi xoá. Đề xuất số phận A–D trong báo cáo. Xoá `LiveStation` khi hết caller. Ghi
   mọi xoá vào `docs/refactor/DELETION_MANIFEST.md` (đường dẫn cũ, lý do, thay thế, test, SHA).
6. **Differential tests** (PLAN.md mục 8) và test admission ↔ policy thực thi.
7. **`docs/refactor/PHASE3_REPORT.md`**, rồi **dừng**. Không bắt đầu Phase 4.

## Bảo toàn và cổng kiểm

- Code gốc được bảo toàn, **không sửa logic**:
  - `src/optimizer/{dispatch,zones,coordination}/`, `src/optimizer/registry.py` (POLICIES đóng băng);
  - `src/guard/physical/validator.py`;
  - `src/simulator/src/charging_models/`, `engine/ev2gym_adapter.py`, `engine/queue.py`;
  - `src/models/{simulation_core,physical_*,charging_physics}.py`.

  Cổng: `scripts/refactor/compare_ast_manifest.py docs/refactor/raw/phase2/final_manifest.txt -- <các đường dẫn trên>`
  phải exit 0. Thay đổi chủ ý đi qua `--allow-changed` kèm lý do.
- `engine/hybrid.py` được tách thành core. **Chế độ tương thích phải giữ golden:** `pytest src/simulator/tests`
  (163 test, không sửa test của chủ simulator) và `scripts/refactor/compare_sim_output.py` với evidence
  `eval/evidence/2026-11-22/raw/sim-hardware/` (MVP-1/2/3, VinFast, DecisionTrace) phải OK. Module map khai báo như
  `docs/refactor/raw/phase2/module_map.txt` (thêm cặp mới nếu bạn di chuyển module).
- Simulator phải chạy standalone, không cần FastAPI / DB / LLM / pydantic: `tests/test_architecture.py` có probe.
  Không nới luật ranh giới mà không cập nhật ADR-019.
- Benchmark backend **sẽ đổi số** khi runtime đổi semantics (interval, replan…). Không so như "tốt hơn / tệ hơn". Ghi
  số mới ở evidence Phase 3 và giải thích nguồn chênh lệch theo từng khác biệt của PHASE0_FINDINGS §2.
- Test backend tạm fail: ghi `docs/refactor/EXPECTED_FAILURES.md`. Không xoá test, không làm yếu safety check.

## Escalate (dừng phần đó, hỏi chủ dự án ngay trong cửa sổ này)

Khi phải đổi công thức vật lý, objective, tham số solver, hard safety semantics, consent / quyền / định nghĩa SLA /
quote, xoá dữ liệu quan trọng, hoặc khi không đạt parity mà không phải đổi thứ tự sự kiện / bỏ qua Guard.

## Phối hợp

- claude3 làm song song trên `feature/unified-core-llmchat` (chuyển `src/agents` → `src/llm_chat`). Bạn **không sửa**
  `src/agents/**`, `src/api/routes.py` phần `/chat`, `prompts/`, `tests/test_agents/**`.
- Hai bên đều có thể sửa `tests/test_architecture.py` và `CLAUDE.md`. Giữ thay đổi gọn, đúng vùng của mình, để gộp dễ.
