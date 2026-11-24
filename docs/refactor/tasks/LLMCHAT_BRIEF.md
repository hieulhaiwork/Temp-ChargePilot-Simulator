# Brief giao việc — Phase 4 mục 1: chuyển LLM chat sang `src/llm_chat/` (claude3)

Bạn chuyển resident-facing LangGraph chat của ChargePilot (P-019) sang `src/llm_chat/`. Đọc trước khi làm:
1. `CLAUDE.md` (gốc repo)
2. `docs/refactor/PLAN.md`: Phase 4 mục 1 là phạm vi của bạn
3. `docs/adr/ADR-019-unified-core-hop-dong-dung-chung.md`: mục 6 và "Quyết định 2026-11-23 sau review Phase 2"
4. `docs/refactor/PHASE0_FINDINGS.md` §5: luồng chat hiện tại, checklist caller, bẫy cần tránh

## Môi trường

- Làm **chỉ** trong worktree này, nhánh `feature/unified-core-llmchat`. Không đụng `D:\VIN\P-019` hay worktree `p3`.
- Python: `D:\VIN\P-019\.venv\Scripts\python.exe` (ví dụ `... -m pytest -q -p no:cacheprovider`).
- Windows: `PYTHONIOENCODING=utf-8` khi chạy script in tiếng Việt; file mới để xuống dòng LF.

## Quy tắc bắt buộc (của chủ dự án)

- Commit nhỏ, message `type(scope): mô tả` bằng tiếng Việt. **Không thêm `Co-Authored-By` / `Claude-Session`.**
- **Không `git push`** đi đâu cả, không merge / rebase nhánh khác, không force, không deploy. Claude điều phối sẽ gộp.
- Không tắt hook `.ai-log`, không `--no-verify`. Không đưa đường dẫn cá nhân vào file commit.

## Phạm vi

1. `git mv` code chat thật từ `src/agents/` sang `src/llm_chat/` (giữ lịch sử):
   - `graph.py`, `state.py`, `guardrails.py`, `prompts.py`, `mock_llm.py`, `personas.py`;
   - `nodes/`, `tools/`.

   Phân loại phần template chưa nối graph (`nodes/{retrieve,safety,synthesize,validate}`, `personas`,
   `tools/{knowledge,mcp_tool,risky_tools}`): giữ nếu test / eval còn dùng; nếu bỏ thì ghi lý do và test thay thế vào
   `docs/refactor/DELETION_MANIFEST.md` (tạo nếu chưa có, chỉ thêm mục của bạn).
2. `src/agents/` chỉ còn `__init__.py` (docstring: dành cho AI-1 negotiation / AI-4 decision copilot, chưa có code).
   **Không** tạo shim `src/agents/*` trỏ sang `llm_chat`. Không viết AI-1 / AI-4.
3. LLM provider **giữ ở `src/services/llm.py`** (dùng chung cho chat, `eval/judge.py`, AI module sau này). Không
   chuyển, không đổi API.
4. Cập nhật mọi caller (PHASE0_FINDINGS §5):
   - `src/api/routes.py`;
   - `eval/run_agent_eval.py`, `eval/run_eval.py`;
   - `tests/conftest.py`, `tests/__init__.py`, `tests/test_agents/**` (có thể đổi tên thư mục thành `tests/test_llm_chat/`);
   - `tests/test_api/test_flows.py`: monkeypatch bằng **chuỗi** `"src.agents.mock_llm._now_local"`, `rg` theo dạng
     import sẽ không bắt được;
   - `tests/test_architecture.py`;
   - docs có đường dẫn `src/agents`.
5. `prompts/`: loader `prompts.py:18` dùng `parent.parent.parent / "prompts"`. Kiểm loader vẫn trỏ đúng sau khi
   chuyển. **Không sửa nội dung prompt.**
6. `src/models/schemas.py`: `ChatRequest` / `ChatResponse` nằm trong OpenAPI. `AgentDecision` / `FinalAnswer` /
   `AgentAnswer` là kiểu nội bộ chat, có thể chuyển sang `src/llm_chat/schemas.py`. **Không đổi tên class, field,
   response shape, endpoint, status code.**
   `D:\VIN\P-019\.venv\Scripts\python.exe scripts/export_openapi.py --check` phải pass, và `frontend/openapi.json`
   không đổi.
7. `tests/test_architecture.py`:
   - đổi luật `agents` thành `llm_chat`: chỉ gọi `services`, `models`, `config`; không simulator / guard /
     optimizer / db / api; không tạo `Command`; tool chỉ gọi services;
   - thêm luật cho `src/agents/` mới (AI-1 / AI-4): chỉ qua services, không bypass Guard, không tạo `Command`,
     không DB / actuator.

   Không xoá hay nới luật hiện có.
8. Cập nhật `CLAUDE.md`, chỉ các mục nói về Agent graph / kiến trúc `agents/`. `ARCHITECTURE.md` nếu có mô tả agents.

## Nghiệm thu (không đổi hành vi chat / HITL)

- `pytest` toàn repo pass (cùng số test, trừ test đổi tên / chuyển chỗ; ghi rõ con số trước / sau).
- `/chat`, `/chat/stream`, `/chat/resume`, interrupt / resume, `resident_id` phía server, idempotency của
  `confirm_booking`: test hiện có phải pass không sửa logic.
- `eval/run_agent_eval.py --offline` OK. `scripts/check_docs.py` pass. ruff `src tests` sạch.
- `rg -n "src\.agents|src/agents" src tests eval scripts docs` chỉ còn tham chiếu tới `src/agents/` mới (AI-1 /
  AI-4) và tài liệu lịch sử.
- Báo cáo ngắn `docs/refactor/LLMCHAT_REPORT.md`: file đã chuyển, file bỏ (nếu có), caller đã sửa, số test, kiểm
  OpenAPI.

## Phối hợp

claude2 làm Phase 3 song song trên `feature/unified-core-p3`. Bạn **không sửa** `src/optimizer`, `src/simulator`,
`src/guard`, `src/services/*`, trừ chỗ chỉ đổi import `src.agents`. Hai bên đều có thể sửa
`tests/test_architecture.py` và `CLAUDE.md`. Giữ thay đổi gọn, đúng vùng của mình.
