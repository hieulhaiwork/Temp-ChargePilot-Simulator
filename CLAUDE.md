# CLAUDE.md — Project context cho Claude Code (C4/C5)

> Inspire team 001 (PROJECT_CONTEXT Quick Rehydrate) + team 008 (CLAUDE.md structure).

## Quick Rehydrate (≤ 60s)

Đọc nhanh khi mất context:
- **Đây là**: ChargePilot (đề tài SC-16, nhóm T019) — AI Agent tối ưu lịch sạc EV cho 1 bãi **mô phỏng** hỗn hợp
  AC + DC (fixture `mvp1`: 2 cổng AC 11 kW + 2 cổng DC 60 kW, lưới 106 kW — `config/station.yaml`, ADR-010).
  Dựng trên AI20K Agent Template.
- **Stack**: Python 3.12, FastAPI, LangGraph 1.x, LangChain 1.x, Pydantic v2, SQLAlchemy 2 + Alembic;
  web Next.js 16 + TypeScript trong `frontend/`.
- **Trạng thái**: backend chạy thật (DB, auth, Guard, optimizer, `LiveStation`, WebSocket, chat). Stub còn lại
  (`raise NotImplementedError("[Txx] …")` → 501) chỉ là F6 forecast, đang hoãn (ADR-015).
  Backlog: `grep -rn 'NotImplementedError("\[T' src/ --include=*.py`.
- **Simulator là gốc** (ADR-018, ADR-019 Unified Core): backend chạy `HybridStation` (`src/simulator/hybrid_station.py`)
  dựng từ engine simulator, với policy `M3a` (mặc định) / `M3b` / `M2b` / `B0` (`src/services/hybrid_planner.py`).
  Refactor Unified Core đang chạy theo phase (`docs/refactor/`, nhánh `feature/unified-core`). Code gốc MVP-1/2/3 chỉ
  được **di chuyển** (thuật toán: `src/optimizer/{dispatch,zones,coordination,registry.py}`; Physical Guard:
  `src/guard/physical/validator.py`; hợp đồng: `src/models/{simulation_core,scheduling,physical_*,charging_physics}`),
  logic giữ nguyên và chứng minh bằng `scripts/refactor/compare_ast_manifest.py`. Vị trí cũ trong `src/simulator/src/`
  là shim. KHÔNG sửa thuật toán, objective, tham số solver hay vật lý để cho khớp backend — sửa backend.
  Simulator phải chạy standalone (không FastAPI / DB / LLM). `LiveStation` chỉ là dự phòng (`STATION_ENGINE=live`).
- **LLM**: `LLM_PROVIDER=openai` (OpenAI, hoặc Gemini / OpenRouter qua `OPENAI_BASE_URL`) · `local` · `mock` (chỉ
  dev/test, cấm ở production). Test và eval offline dùng LLM giả; để `OPENAI_API_KEY` RỖNG khi chưa có key (chuỗi
  placeholder bị coi là key thật).
- **Deploy**: bản test đang chạy — [`docs/plan/56-deploy-render-image.md`](docs/plan/56-deploy-render-image.md) §0.
- **Chạy server**: `make migrate && make run` → http://localhost:8000/docs
- **Chạy web**: `cd frontend && npm run dev` → http://localhost:3000
- **Chạy check**: `make check` (ruff + format + pytest + docs) · `make check-all` · `make web-check`
- **Đang làm dở?** Đọc `docs/handoff/HANDOFF.md` trước, rồi `PROJECT_CONTEXT.md`.

## Current Invariants (để không drift)

- **Source of truth kỹ thuật**: code trong `src/`. File `.md` (kể cả file này) chỉ là
  tóm tắt — khi mâu thuẫn, CODE WINS (inspire team 011 source-of-truth rule).
- **3 trụ**: Agent hiểu yêu cầu (chat cư dân `src/llm_chat/`) → Optimizer tính lịch (`src/optimizer/`) → Guard kiểm soát mọi lệnh
  (`src/guard/`). Ranh giới import khoá bằng `tests/test_architecture.py`; nới ranh giới phải viết ADR trong `docs/adr/`.
- **Chỉ `src/guard/dispatcher.py` gửi lệnh tới trạm** (`StationActuator.apply_commands`) — ADR-002.
- **Agent graph** (chat cư dân): `src/llm_chat/graph.py` — ReAct harness: guardrail → reason → act (tools, HITL
  interrupt cho risky tools, gồm `confirm_booking`) → assess → finalize (escape hatch max-iterations). Đừng thêm node mà
  không cập nhật state schema (`src/llm_chat/state.py`). Chỉ `src/api/routes.py` import `src.llm_chat.graph`. LLM
  provider dùng chung ở `src/services/llm.py`. `src/agents/` dành cho AI-1 / AI-4 (chưa có code): chỉ qua services,
  không tạo `Command`, không DB / actuator.
- **kWh do code tính** (`src/services/energy.py`, FR3), không do LLM. **`resident_id` lấy phía server**
  (JWT → `config["configurable"]`), không là tham số tool, LLM không đọc / ghi được (ADR-006).
- **Prompts**: nằm ở `prompts/*.md` (external file, `{{placeholder}}`). KHÔNG nhúng prompt dài trong Python string.
- **Tham số mô phỏng** ở `config/*.yaml` (ADR-003), không hardcode.
- **Persistence**: ORM chỉ ở `src/db/` và `src/services/repository.py`; schema chỉ đổi qua Alembic (ADR-005).
  `src/models/` là Pydantic thuần, không phụ thuộc ORM.
- **API**: router chỉ gọi `src/services`; lỗi theo envelope `{detail, code, request_id}` (ADR-008). Đổi model /
  endpoint → `python scripts/export_openapi.py` rồi `npm run gen:api` trong `frontend/` (ADR-009).
- **Dependency**: lúc chạy ở `requirements-runtime.txt`, dev/test ở `requirements.txt`. Thêm gói phải ghi lý do + task.
- **Safety guardrail**: 2 lớp — prompt (`prompts/charging_safeguards.md`) và code (`src/llm_chat/guardrails.py`);
  lệnh trạm do Guard 7 luật kiểm (`src/guard/`), không phụ thuộc LLM.
- **Logging hooks**: `.claude/.cursor/.codex/.gemini/.github` auto-log prompt vào
  `.ai-log/`. KHÔNG disable, KHÔNG bypass `--no-verify`. Luôn mở AI tool ở repo root, không mở trong `frontend/`.
- **Git**: `feature/<tên>` → `develop` → `main`; commit dạng `type(scope): mô tả`.

## Commands hay dùng

```bash
make check         # ruff check + ruff format --check + pytest + check_docs
make check-all     # + OpenAPI snapshot + eval Agent offline
make run           # uvicorn (make migrate trước lần đầu)
make migrate       # alembic upgrade head
make openapi       # ghi lại frontend/openapi.json
make eval-agent    # python eval/run_agent_eval.py --offline
make benchmark     # benchmark A–D (exit 2 khi pipeline còn stub)
make web-check     # lint + typecheck + test + build của frontend/
```

## Kiến trúc

```
src/
  models/      # hợp đồng dữ liệu Pydantic (không import tầng nào khác) + hợp đồng core thuần stdlib (ADR-019):
               #   simulation_core, scheduling/, physical_constraints, physical_limits, charging_physics, station_protocols
  llm_chat/    # Trụ 1 (chat cư dân): graph.py, state.py, schemas.py, nodes/, tools/charging.py, guardrails.py, prompts.py
  agents/      # dành cho AI-1 negotiation / AI-4 decision copilot (ADR-019) — chưa có code
  services/    # tầng ứng dụng: charging_service, station_service, control_loop, runtime, event_bus,
               #   realtime, auth, repository, catalog, energy, llm, errors
  optimizer/   # Trụ 2: dispatch/, zones/ (AC/DC LP), coordination/, registry.py (policy B0/M2b/M3a/M3b) — gốc simulator;
               #   strategies.py + baselines/mpc/lp_model/assignment: LP backend A–D cũ (quote/booking còn dùng)
  forecast/    # F6: dự báo lúc rút đầu nối (cấm feature unplug_time)
  guard/       # Trụ 3: rules (7 luật), checker, approval, emergency, dispatcher (chokepoint);
               #   physical/validator.py (Physical Guard gốc) + physical/adapter.py (map DTO backend)
  simulator/   # src/ engine HybridSimulator (queue, EV2Gym, charging_models, evaluation) · hybrid_station.py · live.py
  db/          # SQLAlchemy: tables (9 bảng), session, mappers
  api/         # REST /api/v1 + WebSocket: auth, catalog, resident, operations, simulation, routes (/chat), ws
config/        # station.yaml, vehicles.yaml, tariff.yaml, scenarios/
prompts/       # reason.md, finalize.md, charging_domain.md, charging_safeguards.md
migrations/    # Alembic
frontend/      # Next.js: src/app (13 route), src/lib/api (type sinh từ openapi.json)
eval/          # run_agent_eval.py, run_benchmark.py, datasets/, thresholds.yaml
docs/          # plan/, adr/, handoff/, architecture_diagram.md
```

Chi tiết: `ARCHITECTURE.md` (sườn thư mục, ranh giới, truy vết FR → module → test).

## Quyết định kỹ thuật (ADR ngắn)

Bản đầy đủ: `docs/adr/` (ADR-001 … ADR-019).

- **Contract-first, stub trả 501** (ADR-004): app luôn khởi động được, `/docs` đủ endpoint, việc còn lại đọc được từ code.
- **Guard là chokepoint** (ADR-002): mọi lệnh tới trạm, kể cả benchmark, đi qua `guard/dispatcher.py`.
- **External prompt files**: tách prompt khỏi code → mentor review được, diff rõ.
- **Defence-in-depth safety**: guardrail ở cả prompt LẪN code → chống jailbreak bỏ qua 1 lớp.
- **Retry loop trong graph**: dùng conditional edge thay vì try/except đệ quy.
- **`StationRuntime` là composition root** (ADR-007): chạy thật và benchmark dùng chung `control_loop.on_event`.
- **Một worker**: trạng thái trạm, WebSocket, checkpoint chat nằm trong RAM của process.
- **Vòng nền** (`control_loop.run_forever`): deploy bật `CONTROL_LOOP_ENABLED=true` để trạm tự chạy theo thời gian;
  local mặc định tắt. Người chỉ duyệt khi lệnh vượt consent cư dân hoặc do Agent đề xuất (`guard/approval.py`).
- **Guard theo hợp đồng an toàn của simulator** (ADR-017): trần vùng = `physical_zone_cap_kw` (22/120), ngân sách
  22/78 chỉ là phân bổ của optimizer; không cấp điện cổng trống / xe đầy; chỉ gán xe đang chờ ở bãi.
- **Backend chạy engine simulator** (ADR-018, thay ADR-016): trạm `HybridStation` + `SimulatorScheduler`; lệnh vẫn qua
  `guard/dispatcher.py`. Cài: `make install` (ev2gym `--no-deps`).

<!-- BEGIN P019-DISTILLATION-LOCAL-RULES -->
## Agent Knowledge Library (external, local only)
Distilled agent-framework knowledge from this project was migrated on 2026-11-19 to
`D:\VIN\Agent-Knowledge-Library` (outside this repo; the former `agent-distillation/` directory was removed).
Before using, adapting, recommending, extending, implementing or integrating any distilled mechanism or framework
(M-001…M-022, including M-005 action-authorization-gate), follow
`D:\VIN\Agent-Knowledge-Library\SOURCE_USE_POLICY.md`, then read
`D:\VIN\Agent-Knowledge-Library\integration-guides\P-019.md`. Do not copy the library into this repo.
M-005 v1.1.0-rc is RESTRICTED_PILOT / NOT_VALIDATED / NOT_PRODUCTION_READY; integration needs separate owner
approval plus prerequisites PR-1…PR-6 and PR-D3.
Never run git add, git commit, git push, merge, rebase, checkout, reset, cherry-pick,
stash, or create PRs for that program. Read-only Git inspection is permitted.
Never modify existing product source on the program's behalf.
Do not publish or upload library artifacts without explicit approval.
<!-- END P019-DISTILLATION-LOCAL-RULES -->
