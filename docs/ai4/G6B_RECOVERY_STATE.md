# G6B — Trạng thái phục hồi

**IN_PROGRESS · Codex · 2026-11-26.**

- Local `feature/ai-4-how-to` tại `64c85f1624ee2893eff776a1e82fbdd893d3fe4d`, cây sạch khi nhận, một worktree. `git ls-remote` xác minh remote develop tại `0f877f196db7b89759af08aab825f0fff82f7c3c` trùng local develop và là cha trực tiếp của HEAD. Cập nhật G5 đã có trên nhánh hiện tại. Checkpoint cũ là RECOVERABLE.
- Mirror nghiệm thu chưa có object trong local. Đối chiếu thông qua patch và bundle Tech Lead chấp nhận. Hai SHA-256 khớp cùng 26/26 nội dung bundle, 6/6 source SHA-256 và 6/6 Git blob prefix.
- Khoá G6B do Codex giữ trong lượt triển khai. G6A là fallback, booking và HITL đi theo graph hiện tại. G7, release và đồng bộ PRD/ADR-015 chờ quyết định riêng.

## Audit baseline

Đã đọc Research SC-16, PRD, roadmap, foundation contract, báo cáo G5/G6A, ledger, registry và quy tắc kiến trúc. Research §Hướng 4 mô tả WHY, WHAT-IF và HOW-TO là ba năng lực riêng cho hai vai trò. PRD/ADR-015 hiện vẫn hoãn HOW-TO tìm mức tối thiểu. Thay đổi wording và tiêu chí nghiệm thu cần nhóm đồng thuận.

- `graph.py`, `state.py`, `nodes/`, `tools/` và `guardrails.py` có ReAct hữu hạn, MemorySaver và HITL booking. Legacy finalize dùng numeric check, cần đường render riêng cho phân tích. Legacy `explain_schedule` đọc giải thích lịch qua charging service.
- `routes.py` và `deps.py` trước đây giới hạn chat cho resident. `services/llm.py` có structured provider dùng chung. `services/copilot/integration.py` đã xác thực và gọi WHY/WHAT-IF nhưng đường NL G6A có parser riêng. Jobs là application-owned trong lifespan. `copilot_grounding.py` có claim gate exact cho WHY và WHAT-IF.
- `ChatPanel` có SSE, form/voice và resume. `CopilotPanel` là standalone. Cache key chứa token và API client xóa mọi phiên khi nhận 401. Kiểm Git trước sửa xác nhận chỉ có worktree hiện tại và không có thay đổi teammate trên các tệp được giao.
- `src/simulator/claude_rd/` được Git ignore nhưng có test cũ dùng import đã bỏ nên kiểm architecture trực tiếp trong workspace có một lỗi sẵn có. Chạy xác minh trên cây xuất sạch từ HEAD và overlay delta G6B. Giữ thư mục nghiên cứu của teammate ở nguyên vị trí.

| Checkpoint | Trạng thái |
|---|---|
| A · typed tools | Implemented. Graph gọi bốn adapters qua service, alias WHY legacy và schemas theo vai trò. |
| B · shared jobs | Tested. Một worker và queue dùng chung, cap 8+1, 4 tool calls và 1 simulation attempt/turn, 1 job active/actor và 15 giây giữa lần nộp. |
| C · vai trò và phiên | Tested. Actor do server cấp, JWT generation và session scope cho checkpoint và job. Booking và HITL tiếp tục theo quyền cư dân. |
| D · grounding | Tested. WHY/WHAT-IF dùng gate hiện có. HOW-TO thêm ref và JSON Pointer, render kết luận từ số liệu có kiểu. |
| E · giao diện và findings G6A | Frontend tests qua. Một ChatPanel cho hai role và G6A form fallback. Regression cache key, delayed 401 và constraint. |
| F · kiểm chứng | Focused 11, hồi quy 167, legacy 97, architecture 43, backend 849 + 8 forecast skips, standalone 180. Chromium và gói cuối đang xác minh. |

[Hợp đồng công cụ](G6B_TOOL_CONTRACTS.md) · [Demo](G6B_DEMO.md)
