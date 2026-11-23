# Báo cáo Phase 4 mục 1 — chat cư dân sang `src/llm_chat/`

- Nhánh: `feature/unified-core-llmchat`, gốc `749c042`. Brief: `docs/refactor/tasks/LLMCHAT_BRIEF.md`.
- Kết quả: chat cư dân (LangGraph ReAct + HITL) nằm ở `src/llm_chat/`. `src/agents/` chỉ còn `__init__.py` (dành cho
  AI-1 / AI-4, chưa có code, không shim). LLM provider giữ nguyên ở `src/services/llm.py`. Hành vi chat / HITL không đổi.

## 1. File đã chuyển (`git mv`, giữ lịch sử)

| Cũ | Mới |
|---|---|
| `src/agents/{graph,state,guardrails,prompts,mock_llm,personas}.py` | `src/llm_chat/…` |
| `src/agents/nodes/{act,assess,finalize,human_review,reason,safety,validate}_node.py`, `nodes/__init__.py` | `src/llm_chat/nodes/…` |
| `src/agents/tools/{__init__,charging,knowledge,mcp_tool,risky_tools}.py` | `src/llm_chat/tools/…` |
| `tests/test_agents/**` (9 file) | `tests/test_llm_chat/**` |
| `AgentDecision`, `FinalAnswer`, `AgentAnswer` trong `src/models/schemas.py` | `src/llm_chat/schemas.py` (nguyên văn) |

`src/models/schemas.py` còn `ChatRequest` / `ChatResponse` (DTO trong OpenAPI). Mới: `src/llm_chat/__init__.py`
(docstring), `src/llm_chat/schemas.py`. `src/agents/__init__.py` có docstring mới.

## 2. File bỏ

`nodes/retrieve_node.py`, `nodes/synthesize_node.py`: template RAG, không nối graph, không có caller hay test. Lý do và
những gì giữ lại: `docs/refactor/DELETION_MANIFEST.md`.

## 3. Caller đã sửa

- Code: `src/api/routes.py` (import `src.llm_chat.graph`), `eval/run_agent_eval.py`, `eval/run_eval.py`.
- Test: `tests/conftest.py`, `tests/__init__.py` (chú thích), `tests/test_llm_chat/**` (gồm đường dẫn file
  `src/llm_chat/nodes` trong `test_no_long_prompt_is_embedded_in_node_modules`), `tests/test_api/test_flows.py`
  (monkeypatch **chuỗi** `"src.llm_chat.mock_llm._now_local"`), `tests/test_api/test_routes.py` và
  `tests/test_services/test_llm_cascade.py` (import schema).
- Chú thích / chuỗi đường dẫn: `src/config.py`, `src/guard/__init__.py` (docstring), `src/services/llm.py` (thông báo
  lỗi của `get_llm` và mô tả model mock của `describe_provider`: `src/agents/mock_llm.py` → `src/llm_chat/mock_llm.py`;
  không đổi API hay logic), `scripts/check_docs.py` (`TEMPLATE_PATHS`), `prompts/README.md`.
- Docs hiện hành: `CLAUDE.md` (3 trụ, Agent graph, Safety guardrail, sơ đồ kiến trúc), `ARCHITECTURE.md`,
  `docs/architecture_diagram.md`, `docs/PRD.md` (bảng truy vết FR2–FR4, FR4a, FR15, FR31), `docs/handoff/HANDOFF.md`,
  `docs/guide/agent-practices/{context-management,prompts}.md`.
- Không sửa (tài liệu lịch sử / guidebook template): `docs/refactor/{PHASE0_FINDINGS,IMPORT_GRAPH,MODULE_PROVENANCE}.md`,
  `docs/refactor/raw/**`, `docs/plan/**`, ADR-001/002, `docs/guide/chapter-*.md` (ví dụ chung của template, các module
  được nhắc tới chưa từng tồn tại). `docs/PRD.md` dòng FR22–FR30 (AI-1 / AI-4) vẫn trỏ `src/agents/`, đúng nghĩa mới.

`prompts/`: loader `src/llm_chat/prompts.py` vẫn dùng `parent.parent.parent / "prompts"`, cùng độ sâu nên vẫn trỏ đúng
`<repo>/prompts` (đã kiểm `_PROMPTS_DIR` và `load_prompt("reason.md")`). Không đổi nội dung prompt.

## 4. Luật kiến trúc (`tests/test_architecture.py`)

Không xoá hay nới luật nào. Thay đổi:
- `BOUNDARIES["llm_chat"]`: cấm `simulator, guard, optimizer, forecast, db, api, agents`.
- `BOUNDARIES["agents"]`: giữ các mục cũ, thêm `src.llm_chat`.
- `test_agent_package_cannot_construct_station_commands` → `test_ai_packages_cannot_construct_station_commands`, chạy
  cho `llm_chat` **và** `agents`.
- `test_agent_tools_only_call_the_services_layer` → `test_llm_chat_tools_only_call_the_services_layer` (cùng luật, đổi
  đường dẫn).
- Mới: `test_ai_packages_only_use_services_models_config` (`llm_chat`, `agents`: chỉ `src.services`, `src.models`,
  `src.config` và chính mình), `test_agents_package_cannot_touch_db_actuator_or_bypass_guard` (`sqlalchemy`, `alembic`,
  `src.db`, `src.services.repository`, `src.guard`, `src.simulator`, `StationActuator`),
  `test_only_api_imports_llm_chat_and_only_its_graph`. Tự kiểm `test_boundary_checker_detects_violation` thêm một
  assert cho `llm_chat`.

## 5. Nghiệm thu

| Kiểm | Trước (`749c042`) | Sau |
|---|---|---|
| `pytest` toàn repo | 469 passed, 8 skipped | **475 passed, 8 skipped** (+6 test kiến trúc mới: 1 `BOUNDARIES` cho `llm_chat`, 2 → 7 test nhóm 5) |
| Test chat (`tests/test_agents` → `tests/test_llm_chat`) | 82 | 82 (không sửa logic test) |
| `ruff check src tests`, `ruff format --check src tests` | sạch | sạch |
| `scripts/export_openapi.py --check` | khớp | khớp; `frontend/openapi.json` không đổi |
| `eval/run_agent_eval.py --offline` | OK | OK (dataset và ngưỡng hợp lệ) |
| `eval/run_eval.py` (mock, offline) | — | 10/10 PASS (report giống hệt trừ timestamp; không commit report) |
| `scripts/check_docs.py` | PASS | PASS |

Test `/chat`, `/chat/stream`, `/chat/resume`, interrupt / resume, `resident_id` phía server, idempotency của
`confirm_booking` (`tests/test_api/test_routes.py`, `test_flows.py`, `tests/test_llm_chat/test_charging_agent.py`,
`test_hitl.py`) pass mà không sửa logic.

**Cổng AST "chỉ di chuyển"** (`scripts/refactor/compare_ast_manifest.py`, bằng chứng ở
`eval/evidence/2026-11-23-refactor-llmchat/raw/`): 134 định nghĩa top-level của `src/agents/**`,
`src/models/schemas.py`, `src/services/llm.py`, `src/config.py`, `src/guard/__init__.py`, `src/api/routes.py`.
- 121 SAME, 4 MOVED-SAME (ba schema sang `src/llm_chat/schemas.py`; `logger` của `synthesize_node`);
- 2 CHANGED đã khai báo (`get_llm`, `describe_provider`: chỉ đổi chuỗi đường dẫn, `allow_changed.txt`);
- 7 MISSING: đúng các định nghĩa của hai file đã bỏ (mục 2). Script thoát 1 vì 7 mục này.

`rg -n "src\.agents|src/agents" src tests eval scripts docs` chỉ còn: luật kiến trúc và docstring cho `src/agents/` mới,
`docs/PRD.md` FR22–FR30 (AI-1 / AI-4), brief / plan / ADR, tài liệu refactor Phase 0, `DELETION_MANIFEST.md`,
`docs/plan/**`, `docs/guide/chapter-*.md` và `eval/evidence/**` (bằng chứng lịch sử).

## 6. Ghi chú cho người gộp

- `src/services/llm.py` có hai chuỗi đổi (mục 3). Brief chỉ cho đổi import trong `src/services/*`; đây là chuỗi đường
  dẫn tới `mock_llm.py`, giữ chuỗi cũ thì trỏ tới file không còn tồn tại. Muốn hoàn tác chỉ cần đảo hai dòng đó.
- Xung đột có thể gặp khi gộp với `feature/unified-core-p3`: `tests/test_architecture.py` (khối `BOUNDARIES` đầu file,
  nhóm 5), `CLAUDE.md` (mục 3 trụ / Agent graph / sơ đồ kiến trúc), `ARCHITECTURE.md` (bảng ranh giới).
- ADR-019 chưa được sửa ở nhánh này (đồ thị tầng đích đã ghi `llm_chat ──► services, models` và
  `agents (AI-1/AI-4) ──► services`). Để Claude điều phối ghi "Cập nhật Phase 4 mục 1" khi gộp.
