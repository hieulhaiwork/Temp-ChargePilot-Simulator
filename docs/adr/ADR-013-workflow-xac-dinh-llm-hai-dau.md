# ADR-013: Workflow xác định là xương sống; LLM chỉ ở hai đầu; LangGraph chỉ cho hội thoại và HITL

- Trạng thái: Proposed — chờ nhóm duyệt
- Ngày: 2026-11-21
- Sửa đổi một phần: ADR-001 (phạm vi của LangGraph ReAct harness)
- Liên quan: ADR-002, ADR-006, ADR-011, ADR-014
- Nguồn: RESEARCH SC-16 ("Kiến trúc cơ bản đề xuất"); master context v1.0 §1, §6 (ranh giới MVP-3 / MVP-4), §9

## Bối cảnh

ADR-001 giữ LangGraph ReAct harness để Agent F1 gọi tool đặt lịch, với HITL `interrupt()` cho bước xác nhận.
RESEARCH SC-16 kết luận: không cần một AI Agent tổng điều phối các tool (AC/DC Optimizer, Global Coordinator, Global
Guard); Agent còn tạo độ trễ vì phải suy nghĩ chọn tool, trong khi một workflow thiết kế kỹ làm được đa số yêu cầu điều
phối. Master context: "MVP-3 chứng minh chất lượng scheduler và an toàn vật lý, không cần LLM để vận hành optimizer";
LLM không được nằm trên đường cấp phát công suất.

## Các lựa chọn

1. Giữ Agent ReAct làm bộ điều phối trung tâm: trái kết luận research, thêm độ trễ và rủi ro LLM chọn sai bước.
2. Bỏ hẳn LangGraph: mất checkpointer theo `thread_id` và `interrupt()` mà HITL cần; phải tự viết lại.
3. **Workflow xác định cho mọi quyết định; LLM chỉ ở hai đầu; giữ LangGraph đúng cho phần hội thoại.**

## Quyết định

Chọn (3).

- **Đường quyết định không có LLM:** yêu cầu đã xác nhận → `charging_service.quote/book` → `SimulatorGateway.replan`
  (dispatch → AC/DC optimizer → coordinator) → Guard → simulator (ADR-002, ADR-011). Form và chat gọi **cùng** service.
- **LLM ở đầu vào:** hiểu câu tiếng Việt thành phiếu / intent / patch có schema (Pydantic validate), hỏi lại trường
  thiếu, không tự điền deadline / target / xe khi người dùng chưa nói. Người dùng xác nhận trước khi `book`.
- **LLM ở đầu ra:** diễn đạt kết quả đã tính (`facts`, `reason_codes`, `evidence_refs`) qua grounding gate (ADR-014).
  Text của LLM không bao giờ quay lại solver hay Guard.
- **LangGraph** giữ cho: hội thoại nhiều lượt (checkpointer), chọn tool đọc / mô phỏng có schema (WHY, WHAT-IF, quote),
  `interrupt()` cho các bước cần người (xác nhận đặt lịch, đồng ý / từ chối đề nghị AI-1). `max_iterations` giữ làm
  escape hatch. Không thêm node lập kế hoạch nhiều bước (FR30a) — HOÃN (ADR-015).
- **Chế độ offline xác định:** khi không có LLM (hoặc `OPENAI_API_KEY` rỗng), parser luật + template chạy đủ luồng và UI
  ghi "LLM chưa cấu hình". Không gọi parser luật là "LLM".
- Agent không import `guard`, `optimizer`, `simulator` (luật hiện có trong `tests/test_architecture.py`, giữ nguyên).

## Bằng chứng

Quyết định này dựa trên lập luận kiến trúc và yêu cầu an toàn, không dựa trên số đo. Phần "LLM có thêm giá trị so với
template hay không" **chưa đo được** vì chưa có API key: phải đo trong eval MVP-4 với ba nhánh (template / LLM không tool
/ LLM + tool + evidence) như master context §9.5, kết quả để ở `eval/evidence/`. Tới lúc đó không tuyên bố giá trị LLM.

## Hệ quả

- `prompts/reason.md` và tool list thu về phạm vi hội thoại; tool sạc chỉ gọi `src/services/*`.
- Độ trễ quyết định (MT5, p95 ≤ 2 s, [MỤC TIÊU]) đo trên workflow, **không** gồm LLM; độ trễ LLM báo riêng.
- ADR-001 vẫn đúng ở lý do kỹ thuật (HITL, checkpointer); chỉ thu hẹp vai trò.
