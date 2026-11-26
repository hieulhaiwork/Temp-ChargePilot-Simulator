# Hợp đồng công cụ trong Chat Agent

Graph `llm_chat` chọn công cụ bằng `AgentDecision`. Adapter kiểm schema và gọi cùng instance `CopilotIntegration` mà ứng dụng cấp cho G6A. Các công cụ phân tích đọc dữ liệu và chạy các fork độc lập. Graph trả kết quả đã xác minh qua `ChatResponse.advisory` và sự kiện SSE `done`.

| Công cụ | Tham số có kiểu | Cư dân | Vận hành |
|---|---|---|---|
| `copilot_why` | `WhyIntent`, chủ đề, phạm vi và thời điểm tùy chọn | Booking của mình. Có thể suy ra nếu chỉ có một booking active | Trạm hoặc một booking được chỉ định trong trạm |
| `copilot_what_if` | `WhatIfIntent`, một `change` và cửa sổ | `revise_vehicle`, có thể mang cả target và deadline | `site_limit` hoặc `outage` |
| `copilot_how_to` | `HowToRequest`, `RecommendationGoal` và cửa sổ | Pin cao nhất tại hạn, hoặc đạt target sớm nhất. Các cờ đánh đổi bắt buộc | Mức nguồn thấp nhất trong các mức thử xác minh đạt ngưỡng cam kết |
| `copilot_job` | UUID dạng hex và `status` hoặc `cancel` | Tác vụ của mình trong phiên hiện tại | Tác vụ của mình trong phiên hiện tại |

Actor và phạm vi trạm lấy từ auth và runtime. Thread key băm tài khoản, role, thông tin xác thực và ID phiên chat. Job kiểm cả actor và thread key. Cùng tài khoản đăng nhập mới hoặc dùng thread khác nhận 404 khi dùng job ID cũ. Phiên có thể gửi một turn vào graph tại một thời điểm. Các thao tác phân tích và booking dùng các turn riêng. Xác nhận booking và voice input tiếp tục yêu cầu vai trò cư dân.

WHY qua tên legacy `explain_schedule` được chuyển về WHY có DecisionTrace trong chat có service. Luồng đánh giá F1 offline vẫn có thể dùng legacy tool với fixture. Cư dân chọn luồng sửa lịch từ màn lịch sạc và xác nhận theo luồng hiện có.

## Tác vụ mô phỏng

Cả `WHAT-IF` và `HOW-TO` dùng `WhatIfJobs` và cùng solver một worker. Mặc định tối đa 4 tác vụ chờ, 1 đang chạy, 64 bản ghi giữ lại, 60 giây kể cả xếp hàng và TTL kết quả 300 giây. Snapshot có 5 giây và một lượt capture tại một thời điểm. Chat tối đa 4 lần gọi công cụ phân tích và 1 lần thử nộp mô phỏng mỗi lượt. Một actor chỉ có một job chat active và hai lần nộp thành công cách ít nhất 15 giây. HOW-TO giữ một baseline và tối đa 8 nhánh ứng viên. Hủy job dừng việc lên lịch bước kế tiếp. Lệnh solver native đã bắt đầu có thể chạy nốt.

- `POST /api/v1/chat` và `POST /api/v1/chat/stream` trả WHY, notice hoặc job handle có kiểu.
- `GET /api/v1/chat/sessions/{session_id}/jobs/{job_id}` trả `queued`, `running`, `succeeded`, `failed`, `cancelled` hoặc `expired`. Chỉ trạng thái `succeeded` mang kết quả. Engine có thể hoàn tất tìm kiếm với `search_status=partial`.
- `DELETE` trên cùng URL yêu cầu hủy. Nếu worker đang chạy, tiếp tục poll đến trạng thái cuối. TTL có giai đoạn tombstone trước khi thành 404. Endpoint dùng `Cache-Control: no-store`.
- Kết quả chat có liên kết với phiên. Endpoint job G6A dùng cùng hàng đợi với scope riêng và tiếp tục phục vụ typed fallback.

## Điều kiện và bằng chứng

LLM chọn công cụ, điền tham số và chọn trường cần làm rõ. `clarify` và `unsupported` có thông báo do server dựng. Các kiểm tra trước admission chặn điều kiện kết hợp nằm ngoài schema, xung đột tham số và cờ đánh đổi mà người dùng chưa đồng ý rõ. Những phép thử riêng lẻ dùng window mặc định 120 phút hợp đồng G6A và hiển thị cửa sổ thực tế. Ý định ngoài tập đã kiểm thử cần được đánh giá thêm ở G7.

Grounding dùng projection đã qua kiểm quyền. Claim HOW-TO liên kết `RecommendationEvidence.ref#/field`. Ví dụ `#/subject_goal_target/target_reached_at`, `#/subject_release_at` và `#/subject_soc_at_deadline_pct` là ba mốc riêng. Gate kiểm toàn bộ claim gồm subject, value, unit, time, stage, branch, code và refs. Signed WHAT-IF delta giữ `patched_minus_baseline`. Kết quả không có cùng horizon an toàn không tạo delta.

Finalize dựng câu từ WHY reasons đã xác minh, kết quả job và notice. So sánh cải thiện dựa trên cùng target hoặc cùng thời điểm quan sát. Chỉ gắn nhãn khả thi cho verdict của engine. Lưới thử G5 và SOC tolerance giữ theo engine. HOW-TO 94 kW trong oracle M3b là mức thấp nhất đã kiểm chứng trong tập thử với tìm kiếm một phần. `applied=false` đi cùng từng kết quả và job.
