# Hợp đồng công cụ trong Chat Agent

Graph `llm_chat` chọn công cụ bằng `AgentDecision`. Adapter kiểm schema và gọi cùng instance `CopilotIntegration` mà ứng dụng cấp cho G6A. Các công cụ phân tích đọc dữ liệu và chạy các fork độc lập. Graph trả kết quả đã xác minh qua `ChatResponse.advisory` và sự kiện SSE `done`.

| Công cụ | Tham số có kiểu | Cư dân | Vận hành |
|---|---|---|---|
| `copilot_why` | `WhyIntent`, chủ đề, phạm vi và thời điểm tùy chọn | Booking của mình. Có thể suy ra nếu chỉ có một booking active | Trạm hoặc một booking được chỉ định rõ trong trạm |
| `copilot_what_if` | `WhatIfIntent`, một `change` và cửa sổ | `revise_vehicle`, có thể mang cả target và deadline | `site_limit` hoặc `outage` |
| `copilot_how_to` | `HowToRequest`, `RecommendationGoal` và cửa sổ | Pin cao nhất tại hạn, hoặc đạt target sớm nhất. Các cờ đánh đổi bắt buộc | Mức nguồn thấp nhất trong các mức thử xác minh đạt ngưỡng cam kết |
| `copilot_job` | UUID dạng hex và `status` hoặc `cancel` | Tác vụ của mình trong phiên hiện tại | Tác vụ của mình trong phiên hiện tại |

Actor và phạm vi trạm lấy từ auth và runtime. Thread key băm tài khoản, role, thông tin xác thực và ID phiên chat. Job kiểm cả actor và thread key. Cùng tài khoản đăng nhập mới hoặc dùng thread khác nhận 404 khi dùng job ID cũ. Mỗi phiên chỉ xử lý một lượt graph tại một thời điểm (`409`), đồng thời toàn bộ các đầu vào `/chat`, `/chat/stream` và `/chat/sessions/{session_id}` đều chịu giới hạn đồng thời theo người dùng (`3` lượt) và toàn tiến trình (`8` lượt, vượt trả `429` và tự giải phóng permit trong `finally`). Các thao tác phân tích và đặt lịch dùng các lượt riêng. Xác nhận booking và voice input tiếp tục yêu cầu vai trò cư dân.

WHY qua tên legacy `explain_schedule` được chuyển về WHY có DecisionTrace trong chat có service. Luồng đánh giá F1 offline vẫn có thể dùng legacy tool với fixture. Cư dân chọn luồng sửa lịch từ màn lịch sạc và xác nhận theo luồng hiện có.

## Tác vụ mô phỏng và Kiểm soát Admission

Cả `WHAT-IF` và `HOW-TO` dùng `WhatIfJobs` và cùng solver một worker. Mặc định tối đa 4 tác vụ chờ, 1 đang chạy, 64 bản ghi giữ lại, 60 giây kể cả xếp hàng và TTL kết quả 300 giây. `CopilotIntegration` thực hiện `check_admission()` ngay trước `capture_atomic_snapshot` (trong khóa chụp tối đa 5 giây), đảm bảo không chụp trạng thái thừa khi hàng đợi đầy hoặc actor đang vướng hạn ngạch. Mỗi actor chỉ có tối đa 1 tác vụ mô phỏng đang active xuyên suốt cả Chat lẫn biểu mẫu dự phòng G6A, và hai lần nộp mô phỏng qua chat phải cách nhau ít nhất 15 giây (không thể lách cooldown qua endpoint G6A). Một lượt chat có tối đa 4 lần gọi công cụ phân tích và 1 lần thử nộp mô phỏng. HOW-TO giữ một baseline và tối đa 8 nhánh ứng viên. Hủy job dừng việc lên lịch bước kế tiếp; lệnh solver native đã bắt đầu có thể chạy nốt.

- `POST /api/v1/chat` và `POST /api/v1/chat/stream` trả WHY, notice hoặc job handle có kiểu.
- `GET /api/v1/chat/sessions/{session_id}/jobs/{job_id}` trả `queued`, `running`, `succeeded`, `failed`, `cancelled` hoặc `expired`. Chỉ trạng thái `succeeded` mang kết quả. Engine có thể hoàn tất tìm kiếm với `search_status=partial`.
- `DELETE` trên cùng URL yêu cầu hủy. Nếu worker đang chạy, tiếp tục poll đến trạng thái cuối. TTL có giai đoạn tombstone trước khi thành 404. Endpoint dùng `Cache-Control: no-store`.
- Endpoint job G6A dùng cùng hàng đợi với scope riêng và tiếp tục phục vụ typed fallback.

## Ràng buộc Tham số Đầu vào và Grounding Đầu ra

LLM chọn công cụ, điền tham số và chọn trường cần làm rõ; `clarify` và `unsupported` có thông báo do server dựng. Trước khi admission, tầng kiểm tra phía server (`conflicts_with_simulation` và `why_conflicts_with_message`) đối chiếu đối xứng mọi giá trị và điều kiện mà người dùng đã nêu trong yêu cầu đang hoạt động với tham số công cụ: mức SOC mục tiêu (tách biệt với SOC hiện tại/ban đầu và từ chối độ lệch phần trăm tương đối chưa giải), hạn sạc và khoảng hạn tìm kiếm (phân biệt `sau/trước N phút` tính từ đồng hồ trạm `now` với các cụm dịch chuyển theo hạn gốc/lịch hiện tại như `muộn hơn N phút so với hạn gốc` — chỉ giải tỏa khi người dùng trả lời `clarify("time")` bằng mốc giờ/phút hợp lệ tường minh), mã đầu nối/vùng, mã booking, thời lượng và thời điểm sự cố, cửa sổ `horizon_minutes`, chủ thể công suất đầu vào lưới toàn trạm (từ chối quy chiếu công suất cổng/trụ/tủ/vùng hoặc lịch hẹn tương lai sang `site_limit` / `min_tested_site_limit_for_sla`), khoảng thử HOW-TO (`bounds`), ngưỡng tỷ lệ SLA gốc, yêu cầu bảo vệ các lịch AC đang đúng hạn, cũng như các cờ hy sinh cam kết (`allow_*`) và `hypothetical_infrastructure`. Trạng thái làm rõ đa lượt (`pending_copilot_clarification`) gắn chặt với tác vụ đang mở (tối đa 3 lượt liên tiếp, TTL 300 giây, hỗ trợ cả lượt hỗn hợp `WHY + clarify`, tự động xóa khi hoàn tất job/unsupported/refusal, khi timeout/lỗi LLM, khi đứt kết nối SSE hoặc khi chuyển sang HITL đặt lịch), không lấy tùy ý toàn bộ lịch sử phiên, không cho câu trả lời slot chuyển sang thao tác mô phỏng khác, chỉ re-anchor khi lượt trước đã đóng hoặc có chỉ thị hủy/đặt lại câu trước tường minh, và tuyệt đối không coi văn bản của `assistant` là dữ kiện hay sự đồng ý của người dùng. Ý định ngoài tập đã kiểm thử tiếp tục được đánh giá trên tập held-out ở G7.

Grounding dùng projection đã qua kiểm quyền. Claim HOW-TO liên kết `RecommendationEvidence.ref#/field`. Ví dụ `#/subject_goal_target/target_reached_at`, `#/subject_release_at` và `#/subject_soc_at_deadline_pct` là ba mốc riêng. Gate kiểm toàn bộ claim gồm subject, value, unit, time, stage, branch, code và refs. Signed WHAT-IF delta giữ `patched_minus_baseline`. Kết quả không có cùng horizon an toàn không tạo delta.

Finalize dựng câu từ WHY reasons đã xác minh, kết quả job và notice. So sánh cải thiện dựa trên cùng target hoặc cùng thời điểm quan sát. Chỉ gắn nhãn khả thi cho verdict của engine. Lưới thử G5 và SOC tolerance giữ theo engine. HOW-TO 94 kW trong oracle M3b là mức thấp nhất đã kiểm chứng trong tập thử với tìm kiếm một phần. `applied=false` đi cùng từng kết quả và job.
