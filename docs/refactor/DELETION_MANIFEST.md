# Deletion manifest — Unified Core refactor

Mỗi mục: file / định nghĩa bị xoá, vì sao, cái gì thay thế, test nào chứng minh không mất chức năng. Mỗi phase / nhánh
chỉ thêm mục của mình.

## Phase 4 mục 1 — chat cư dân sang `src/llm_chat/` (nhánh `feature/unified-core-llmchat`)

| Đã xoá | Lý do | Thay thế / bằng chứng |
|---|---|---|
| `src/agents/nodes/retrieve_node.py` (`retrieve_node`, `_retrieve_chunks`, `_MOCK_KB`) | Template AI20K (RAG mock với 3 chunk demo về AI20K, không liên quan sạc EV). Không nối vào `graph.py`; không test, eval, script hay module nào import (đã `rg` trên `src tests eval scripts`). | Không cần thay: chat cư dân lấy dữ liệu qua tool `src/llm_chat/tools/charging.py` → `src/services`. Toàn bộ test giữ nguyên số lượng (475 passed, 8 skipped trước và sau xoá). |
| `src/agents/nodes/synthesize_node.py` (`synthesize_node`, `_get_structured_answer`) | Template AI20K (gọi `get_llm()` rồi parse `AgentAnswer`). Không nối vào `graph.py`; không có caller hay test. Node `finalize` của graph đã làm việc này với `FinalAnswer` + guardrail hậu kiểm. | `src/llm_chat/nodes/finalize_node.py`; test `tests/test_llm_chat/test_graph.py`, `test_agent_modes.py`, `test_guardrails.py`. |

Giữ lại (vẫn có test dùng, chưa đủ điều kiện xoá): `nodes/safety_node.py`, `nodes/validate_node.py`, `personas.py`,
`prompts.build_system_prompt`, `schemas.AgentAnswer` (`tests/test_llm_chat/test_agent_patterns.py`);
`tools/{knowledge,mcp_tool,risky_tools}.py` (nằm trong `TOOL_REGISTRY`, ẩn khỏi prompt qua
`TEMPLATE_DEMO_TOOL_NAMES`; `send_email` là tool risky mà `test_hitl.py`, `test_routes.py`, `eval/run_eval.py` dùng để
kiểm HITL). Muốn xoá các file này phải chuyển những test đó sang tool sạc trước.
