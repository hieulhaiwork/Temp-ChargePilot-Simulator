# ADR-001: Giữ LangGraph ReAct harness của template cho Agent F1

- Trạng thái: Proposed — chờ mentor trả lời câu hỏi "có bắt buộc template AI20K?" (PRD §11). **Sửa đổi một phần — xem ghi chú bên dưới.**
- Ngày: 2026-11-16


> **Sửa đổi một phần:** [ADR-013](ADR-013-workflow-xac-dinh-llm-hai-dau.md), 2026-11-21: lý do HITL / checkpointer giữ nguyên. Thu hẹp vai trò: LangGraph chỉ cho hội thoại (intake, Copilot đọc / mô phỏng có schema, `interrupt()` cho xác nhận và đồng ý). Đường quyết định công suất là workflow xác định, không có Agent điều phối.

## Bối cảnh

PRD §7 ghi: "Agent: LLM với tool-calling; chỉ dùng LangGraph nếu có lý do kỹ thuật cụ thể".
Repo được sinh từ template AI20K, đã có sẵn harness LangGraph v2 có test.

## Các lựa chọn

1. **Giữ harness LangGraph v2**: vòng ReAct có `max_iterations`, router thật, checkpointer, HITL `interrupt()`.
2. Tự viết vòng tool-calling bằng SDK của provider: ít phụ thuộc hơn, nhưng phải tự làm lại HITL, checkpoint và escape hatch.

## Quyết định

Chọn (1). Lý do kỹ thuật cụ thể:

- FR2 yêu cầu **xác nhận với cư dân trước khi chốt**. `interrupt()` + `Command(resume=…)`
  của harness chính là bước "Xác nhận" ở màn S3 (`confirm_booking` nằm trong `RISKY_TOOL_NAMES`).
- Checkpointer theo `thread_id` cho hội thoại nhiều lượt (hỏi lại chỗ thiếu, FR2).
- Có sẵn guardrail 2 lớp, test harness và eval runner chạy offline (mock LLM qua injection).

## Hệ quả

- Tool sạc thêm vào `src/agents/tools/charging.py`. Tool chỉ gọi `src/services/*`, khoá bởi `tests/test_architecture.py`.
- 4 tool demo của template còn giữ tới T2.5 vì test harness đang dùng. Khi gỡ, phải chuyển các test đó sang tool sạc.
- Prompt reason hiện chỉ liệt kê TÊN tool, không có mô tả và tham số. T2.5 cần đưa `tool.description`/`tool.args` vào prompt, kèm `prompts/*.md` riêng cho domain sạc.
- Nếu mentor không bắt buộc LangGraph, quyết định này vẫn đứng vững nhờ lý do HITL ở trên. Muốn đổi thì viết ADR mới.
