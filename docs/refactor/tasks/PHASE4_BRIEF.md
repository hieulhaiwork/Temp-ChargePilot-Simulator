# Brief Phase 4 — Cleanup & Final Integration (chạy headless, không có người duyệt)

Đọc trước:
1. `CLAUDE.md`
2. `docs/refactor/TECHLEAD_PHASE4_DECISIONS.md` (**quyết định chốt; nguồn sự thật của phase này**)
3. `docs/refactor/PLAN.md`
4. `docs/adr/ADR-019-unified-core-hop-dong-dung-chung.md`
5. `docs/refactor/PHASE3_REPORT.md`, `PHASE3_DESIGN.md`, `EXPECTED_FAILURES.md`, `DELETION_MANIFEST.md`, `LLMCHAT_REPORT.md`

## Quy tắc (bắt buộc; chủ dự án đang điều khiển từ xa, KHÔNG ai trả lời câu hỏi của bạn)

- Chỉ làm trong worktree hiện tại, trên nhánh của nó. Không đụng `D:\VIN\P-019` hay worktree khác.
- Python: `D:\VIN\P-019\.venv\Scripts\python.exe`. Frontend: trong `frontend/` của worktree chạy `npm ci` một lần rồi
  `npm run lint && npm run typecheck && npm test && npm run build`; sau khi đổi model / endpoint chạy
  `python scripts/export_openapi.py` rồi `npm run gen:api`.
- Commit nhỏ, `type(scope): mô tả` tiếng Việt. **Không** thêm `Co-Authored-By` / `Claude-Session`.
- **Không** push, merge, rebase, `reset --hard`, đổi nhánh, deploy (các lệnh này bị chặn). Không `--no-verify`.
- Không xoá / sửa `eval/evidence/**` đã có và golden simulator. Evidence mới ở `eval/evidence/2026-11-23-refactor-phase4/`.
- Không đưa đường dẫn cá nhân (`C:\Users\...`, `D:\VIN\...`) vào file commit. File log commit để xuống dòng LF.
- Không xoá test để xanh, không làm yếu safety check. Test tạm hỏng → ghi `docs/refactor/EXPECTED_FAILURES.md`.
- **Escalate** (đổi công thức vật lý, objective, tham số solver, hard safety, cam kết SLA, quyền phê duyệt): KHÔNG tự
  quyết. Dừng phần đó, ghi vào mục "ESCALATION" của báo cáo, làm tiếp phần khác.
- Cổng kiểm (`scripts/refactor/`, exit 1 khi lệch) phải chạy và ghi log vào `docs/refactor/raw/phase4-<nhánh>/`:
  - AST code được bảo toàn: so `docs/refactor/raw/phase3-merged/preserved_baseline_manifest.txt`;
  - golden: `pytest src/simulator/tests` + `compare_sim_output.py` so `eval/evidence/2026-11-22/raw/sim-hardware/`,
    module map ở `docs/refactor/raw/phase2/module_map.txt` (thêm cặp nếu di chuyển module);
  - `pytest` toàn repo; ruff `src tests scripts/refactor`; `export_openapi.py --check`; frontend checks.
- Kết thúc: báo cáo `docs/refactor/PHASE4_<NHÁNH>_REPORT.md` (đã làm, đã xoá, cổng kiểm + số, expected failures còn
  lại, ESCALATION) và commit. Dòng cuối stdout: `DONE <commit sha>`.

## Nhánh `feature/unified-core-p4-core` (claude2): quyết định 2, 3, 6, 7

- **(7)** Chuyển `StationKernel` (+ phần planning / physics / event của nó) vào `src/simulator/core/`. `HybridSimulator`
  và `HybridStation` dùng đúng kernel đó.
  - **Xoá mọi shim**: alias / re-export trong `src/simulator/src/**`, `src/simulator/base.py`, `__getattr__` tương
    thích ở `src/guard/physical/__init__.py`.
  - Sửa mọi import, kể cả test của chủ simulator: chỉ đổi đường dẫn import / đích monkeypatch, **không đổi assert**.
  - Cập nhật luật `tests/test_architecture.py` (không nới).
- **(2)** `EventType.CHARGE_COMPLETED`: kernel phát, backend nhận, tách khỏi `REPLAN_REQUESTED`. Không replan trùng
  cùng timestamp. Golden không đổi. Cập nhật OpenAPI + `npm run gen:api` + nhãn S6.
- **(3)** Tách command deadband (0,01 kW / cổng) / budget deviation / hard-cap violation (TOL 1e-7) trong trace, log,
  metrics.
  - **Root-cause sai lệch AC +1,97 kW** (phút 560, `peak_evening` / `connector_failure`, xem PHASE3_REPORT §7): viết
    test tái hiện, sửa nguyên nhân.
  - Lệnh **giảm** công suất cần cho an toàn không được bị anti-flapping / HITL chặn: ưu tiên giảm tải / fail-safe
    hợp lệ, có test. Không nới luật an toàn khác.
- **(6)** DecisionTrace backend đầy đủ, **cùng schema / facts / reason codes với simulator**, có correlation ID. Tóm
  tắt vận hành trong DB qua repository + Alembic (ADR-005), chi tiết dạng artifact. Không secret / dữ liệu cá nhân
  thừa. Có test replay từ trace.
- Sau khi sửa (3), chạy benchmark backend (B0 / M2b / M3a / M3b × 5 scenario × seed 1–5, `RESULTS_DIR` ra thư mục tạm),
  so baseline Phase 3 (`eval/evidence/2026-11-23-refactor-phase3/raw/backend_benchmark_seeds1-5.json`) bằng
  `compare_backend_benchmark.py`. Khác biệt nào cũng phải có báo cáo trước / sau + lý do.
- **Không đụng:** `src/models/charging.py::StrategyName`, `frontend/src/app/operator/simulation/**` (S8),
  `src/services/admission.py`, `charging_service.py` phần quote, `src/api/simulation.py` phần benchmark. Đây là việc
  của nhánh api.

## Nhánh `feature/unified-core-p4-api` (claude3): quyết định 1, 5, 8, 9

- **(1)** Xoá A–D khỏi `StrategyName`, mọi consumer backend, OpenAPI, frontend (S8 chỉ B0 / M2b / M3a / M3b).
  Evidence A–D cũ: thêm nhãn deprecated / archive (README), không xoá số.
- **(5)** Quote / admission: API + UI thể hiện kết quả **có điều kiện** khi phụ thuộc approval / HITL. Không trình bày
  như SLA vô điều kiện. Ghi rõ giả định (sự cố tương lai, xe chưa biết, approval) trong tài liệu và response nếu hợp
  lý. Giữ test admission ↔ execution.
- **(8)** Baseline Phase 3 có version: `eval/evidence/2026-11-23-refactor-phase3-baseline/` (commit, scenario, policy,
  seed, `TimeConfig`, phiên bản thư viện), copy số từ evidence Phase 3, không chạy lại khác điều kiện.
  `/simulation/benchmark` không được trả số cũ A–D: đọc baseline có version / sinh lại B0–M3b. Ghi rõ nguồn và version
  trong response. Baseline **chính thức cuối** sẽ sinh ở vòng nghiệm thu, sau khi nhánh core sửa budget deviation.
- **(9)** Xoá / cập nhật mọi hướng dẫn, config, README còn `STATION_ENGINE=live` / LiveStation / A–D / LP backend
  trong tài liệu **vận hành hiện hành** (`render*.yaml`, `.env.example`, README, `docs/handoff`, `docs/plan` hiện
  hành, `eval/*.py` mô tả). Phân biệt archival evidence (giữ nguyên, thêm nhãn nếu cần) với tài liệu vận hành.
- **Không đụng:** `src/simulator/**`, `src/optimizer/**`, `src/guard/**`, `src/services/{control_loop,hybrid_planner,
  runtime}.py`, `src/models/events.py`. Đây là việc của nhánh core.

Hai nhánh cùng sinh lại `frontend/openapi.json` / type `gen:api`: cứ commit; khi gộp sẽ sinh lại một lần.
