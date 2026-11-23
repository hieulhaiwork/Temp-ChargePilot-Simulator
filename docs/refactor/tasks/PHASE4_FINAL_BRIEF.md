# Brief Phase 4 — vòng tích hợp + nghiệm thu cuối (claude3, headless)

Worktree này: nhánh `feature/unified-core-p4-final`, gốc `feature/unified-core` @ `70d0eaf`. Mọi quy tắc của
`docs/refactor/tasks/PHASE4_BRIEF.md` (mục "Quy tắc") vẫn áp dụng, trừ một ngoại lệ: **ở worktree này bạn được
`git merge`** hai nhánh bên dưới. Vẫn cấm push, rebase, reset, đổi nhánh, deploy.

Đọc trước: `docs/refactor/TECHLEAD_PHASE4_DECISIONS.md`, `PHASE4_BRIEF.md`, và sau khi merge:
`docs/refactor/PHASE4_P4-CORE_REPORT.md` (claude2, **dừng giữa chừng vì hết hạn mức**, xem §5 "Còn lại"),
`docs/refactor/PHASE4_P4-API_REPORT.md` (bạn, vòng trước).

## Việc

1. **Gộp:** `git merge --no-ff feature/unified-core-p4-core`, rồi `git merge --no-ff feature/unified-core-p4-api`.
   - Giải quyết xung đột theo ý của **cả hai** báo cáo.
   - **Alembic:** hai nhánh đều có revision mới trên `0001`. Phải còn **một head** (đổi `down_revision` của một bên).
     Test `alembic upgrade head` trên SQLite tạm và downgrade được.
   - Sinh lại `frontend/openapi.json` (`scripts/export_openapi.py`) + `npm run gen:api` **một lần** sau khi gộp.
   - Tài liệu trỏ tới kernel phải dùng đường dẫn mới `src/simulator/core/`.
2. **Migration xoá dữ liệu (kiểm lại quyết định vòng trước):** migration chỉ được xoá dữ liệu **dẫn xuất tính lại
   được** (lịch / plan của chiến lược A–D). **Không bao giờ** xoá booking, cư dân, approval, audit / guard log,
   sự kiện. Ghi rõ trong migration + báo cáo: bảng nào, điều kiện nào, vì sao, cách downgrade. Nếu không chứng minh
   được dữ liệu là dẫn xuất thì **không xoá**: đổi thành đánh dấu / ánh xạ, và ghi ESCALATION.
3. **Dọn A–D còn sót** trong vùng core mà vòng trước không đụng: `oracle_bookings`, nhánh lỗi A–D của
   `make_scheduler`, comment. Theo quyết định 1: bỏ hẳn.
4. **Hoàn tất phần còn lại của claude2** (`PHASE4_P4-CORE_REPORT.md` §5):
   - cổng golden + AST sau bước 3 và 6;
   - benchmark backend sau DecisionTrace, lưu JSON đầy đủ vào `eval/evidence/2026-11-23-refactor-phase4/raw/`;
   - cập nhật ADR-019 (mục Phase 4), `CLAUDE.md` (DecisionTrace, đường dẫn kernel), `EXPECTED_FAILURES.md`.
5. **Nghiệm thu cuối (milestone 4 của Tech Lead):**
   - Full regression trên cây đã gộp: `pytest` toàn repo, `pytest src/simulator/tests`, ruff, OpenAPI `--check`,
     `check_docs`, `eval/run_agent_eval.py --offline`, frontend `lint / typecheck / test / build`.
   - Cổng AST code được bảo toàn: so `docs/refactor/raw/phase3-merged/preserved_baseline_manifest.txt`. Module nào được
     di chuyển (vd. charging_models, queue, ev2gym_adapter, evaluation → `src/simulator/core|evaluation`) dùng
     `--moves`; định nghĩa phải SAME / MOVED-SAME. Thay đổi chủ ý phải `--allow-changed` kèm lý do.
   - Golden: `compare_sim_output.py` so `eval/evidence/2026-11-22/raw/sim-hardware/` (MVP-1/2/3, VinFast, script
     mode, DecisionTrace). Module map cập nhật đúng các đường dẫn mới.
   - **E2E** (không cần Postgres; dùng SQLite tạm qua `DATABASE_URL`, `LLM_PROVIDER=mock`): khởi động app bằng
     `python -m uvicorn` hoặc `TestClient` trong một script `scripts/refactor/e2e_acceptance.py`. Kịch bản:
     đăng nhập → quote (có điều kiện) → booking → control loop / planning → Guard / HITL (duyệt + từ chối) → thực thi
     vật lý → sự kiện `CHARGE_COMPLETED` → DecisionTrace truy được theo correlation ID → replay / KPI. Script exit 1
     khi bất kỳ bước nào sai. Thêm vào `tests/` nếu chạy nhanh.
   - Negative safety: giảm nguồn đột ngột (fail-safe giảm tải không bị anti-flapping / HITL chặn), lệnh vượt hard cap
     bị chặn, cổng lỗi.
   - **Baseline chính thức cuối refactor:** benchmark backend B0 / M2b / M3a / M3b × 5 scenario × seed 1–5 → evidence
     `eval/evidence/2026-11-24-unified-core-final-baseline/` (manifest: commit, scenario, policy, seed, TimeConfig,
     thư viện). Báo cáo trước / sau so baseline Phase 3, giải thích mọi chênh lệch. Cho `/simulation/benchmark` trả
     baseline này.
6. **Tài liệu cuối:**
   - `docs/refactor/FINAL_MAP.md` (old path → new path, owner, đường tiêm policy, file đã xoá + lý do, gotchas);
   - `docs/refactor/REFACTOR_REPORT.md` (theo guide §8: kiến trúc + chiều import thực tế, moved / deleted / kept,
     bằng chứng một engine, số kiểm định lượng, backend / API / chat check, giới hạn còn lại cho MVP-3.5, test mở
     rộng optimizer qua registry, deployment notes + rollback);
   - đánh dấu ADR-011 / 016 / 017 / 018 superseded / amended (ghi đầu ADR cũ, không xoá).

   Mọi số trong tài liệu phải trỏ tới log / evidence thật.
7. Dừng ở final acceptance. Dòng cuối stdout: `DONE <commit sha>`.
