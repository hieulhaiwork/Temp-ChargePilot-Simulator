# ADR-006: Danh tính — JWT, `resident_id` phía server, WebSocket xác thực bằng bản tin đầu

- Trạng thái: Proposed — nhóm đã duyệt 2026-11-17, chờ mentor. **Sửa đổi một phần — xem ghi chú bên dưới.**
- Ngày: 2026-11-17
- Plan chi tiết: [`docs/plan/10-backend.md`](../plan/10-backend.md) §4.3, §8 · [`docs/plan/30-ai.md`](../plan/30-ai.md) §3.4


> **Sửa đổi một phần:** [ADR-014](ADR-014-decision-trace-counterfactual-hitl.md) §6, 2026-11-21: JWT và `resident_id` phía server giữ nguyên. Operator cũng được dùng Copilot (WHY cấp bãi, WHAT-IF `site_limit` / `outage`) qua endpoint phân quyền theo role; `/chat` hiện có giữ cho resident.

## Bối cảnh

FR1 yêu cầu đăng nhập hai vai trò. `/chat` và `/chat/resume` đang mở công khai, trong khi tool của Agent cần biết
cư dân nào đang chat. Nếu LLM điền được `resident_id`, một prompt injection có thể xem hoặc sửa lịch của người khác.
Frontend (`*.vercel.app`) và backend (`*.onrender.com`) khác site nên cookie phiên là cookie bên thứ ba.

## Các lựa chọn

1. Cookie phiên httpOnly: an toàn hơn trước XSS, nhưng bị trình duyệt chặn khi khác site.
2. **Bearer JWT trong header**, lưu ở `sessionStorage` phía web.
3. Dịch vụ xác thực bên ngoài: vượt phạm vi đề tài.

## Quyết định

Chọn (2):

- JWT HS256 (PyJWT), claim `sub` = `user_id` giả danh, `role`, `name`, `iat`, `exp` (mặc định 8 giờ). Không có refresh token.
- Mật khẩu băm bằng `hashlib.scrypt` của stdlib, không thêm `bcrypt`.
- Tài khoản demo seed lúc khởi động từ biến môi trường `SEED_USERS_JSON`; không có mật khẩu nào trong repo.
- `/chat` và `/chat/resume` yêu cầu vai trò `resident`. Router đặt `config["configurable"]["resident_id"]` từ token và
  dùng `thread_id = f"{user_id}:{session_id}"`. Tool đọc `resident_id` từ `RunnableConfig`; không tool nào có tham số
  `resident_id` trong schema gửi LLM.
- WebSocket: client gửi `{"type": "auth", "token": …}` trong 5 giây đầu. Không dùng `?token=` vì uvicorn ghi query
  string vào access log.

## Hệ quả

- Dependency mới: `pyjwt`.
- `JWT_SECRET` bắt buộc ở production. Chỉ thêm vào validator của `src/config.py` cùng PR với `render.yaml` và job
  `docker-smoke`, nếu không deploy sẽ fail.
- Token trong `sessionStorage` lộ nếu có XSS: chấp nhận trong phạm vi demo với dữ liệu giả lập.
- `tests/test_api/test_routes.py` phải giả lập user đã đăng nhập khi gọi `/chat`.
- Thiếu `resident_id` trong config thì tool raise ngay, không dùng giá trị mặc định.
