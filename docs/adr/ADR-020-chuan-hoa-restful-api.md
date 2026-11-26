# ADR-020: Chuẩn hoá RESTful API trên `/api/v1`

- Trạng thái: Proposed — theo quyết định thống nhất với người dùng ngày 2026-11-25.
- Ngày: 2026-11-25
- Sửa đổi một phần: [ADR-008](ADR-008-quy-uoc-api.md) (quy ước versioning `/api/v1`, phương thức HTTP, status code, và pagination envelope).

## Bối cảnh

API `/api/v1` ban đầu theo hướng Pragmatic REST + Role-based BFF (`/resident/...`, `/operator/...`), trong đó nhiều endpoint sử dụng `POST` kèm động từ/hành động (RPC-style), endpoint danh sách trả mảng JSON trần thay vì envelope phân trang, `DELETE` trả `200 OK` kèm body, và một số thao tác tạo tài nguyên chưa gắn `201` hoặc header `Location`.

Trong giai đoạn phát triển nội bộ khi `frontend/` là client duy nhất được sinh trực tiếp từ `frontend/openapi.json` (ADR-009), việc giữ các endpoint RPC-style sẽ làm lệch ngữ nghĩa HTTP, thiếu metadata phân trang cho các bảng nhật ký và giảm tính nhất quán của hợp đồng API.

## Lựa chọn

1. **Tương thích ngược**: Sửa trực tiếp trên `/api/v1` (breaking change đồng bộ backend, `openapi.json`, `frontend/`, và `tests/`) thay vì mở `/api/v2` hoặc duy trì route song song.
2. **Namespace theo vai trò**: Giữ phân tách `/resident/...` và `/operator/...` để bảo toàn ranh giới quyền và OpenAPI type giữa S2–S4 và S5–S7, thay vì gộp chung `/bookings`, `/approvals`.
3. **Chuẩn hoá endpoint hành động & đọc dữ liệu**:
   - Đổi toàn bộ endpoint cập nhật trạng thái (`POST /approvals/{id}`, `POST /notifications/{id}/read`, `POST /notifications/read-all`, `POST /chat/resume`) sang `PATCH` theo tài nguyên.
   - Đổi phép tính không lưu trạng thái đơn giản (`POST /energy/estimate`) sang `GET /energy-estimates`; các phép tính payload phức tạp đổi sang danh từ số nhiều (`POST /resident/quotes`, `POST /resident/bookings/{booking_id}/quotes`).
   - Chuẩn hoá các lệnh điều khiển còn lại sang tài nguyên danh từ số nhiều (`POST /operator/schedule/replans`, `POST /operator/bookings/{booking_id}/assignments`).

## Quyết định

- **Quy đổi URI và HTTP Method trên `/api/v1`**:
  - `POST /energy/estimate` → `GET /energy-estimates` (query: `vehicle_model`, `soc_now`, `soc_target`)
  - `POST /resident/quote` → `POST /resident/quotes`
  - `POST /resident/bookings/{booking_id}/quote` → `POST /resident/bookings/{booking_id}/quotes`
  - `POST /resident/notifications/{notification_id}/read` → `PATCH /resident/notifications/{notification_id}` (body `{"read": true}`)
  - `POST /resident/notifications/read-all` → `PATCH /resident/notifications` (body `{"read": true}`)
  - `POST /resident/approvals/{approval_id}` → `PATCH /resident/approvals/{approval_id}`
  - `POST /operator/approvals/{approval_id}` → `PATCH /operator/approvals/{approval_id}`
  - `POST /operator/schedule/replan` → `POST /operator/schedule/replans`
  - `POST /operator/queue/{booking_id}/assign` → `POST /operator/bookings/{booking_id}/assignments`
  - `POST /chat/resume` → `PATCH /chat/sessions/{session_id}` (body `{"resume": "approve" | "reject"}`)
- **HTTP Status Codes & Header**:
  - `DELETE /resident/bookings/{booking_id}` trả `204 No Content` (không trả body).
  - `POST /resident/bookings` (`201 Created`) trả kèm header `Location: /api/v1/resident/bookings/{booking_id}`.
  - `POST /simulation/runs` trả `201 Created`.
- **Pagination Envelope**:
  - Các endpoint phân trang cursor (`GET /operator/commands/blocked`, `GET /operator/decision-log`) trả `DecisionLogPage`: `{"items": [...], "next_cursor": int | null, "has_more": bool}`.

## Hệ quả

- Nới lỏng quy ước "trong `/api/v1` chỉ thêm" của ADR-008 trong giai đoạn tiền phát hành nội bộ; từ khi publish cho client ngoài cần quay lại cơ chế deprecation/version mới.
- Mọi thay đổi hợp đồng phải chạy đồng bộ `python scripts/export_openapi.py` và `npm run gen:api` trong `frontend/` để pass `tests/test_api/test_openapi_snapshot.py`.
- Frontend màn `S7` (`operator/approvals`) đọc `items`, `next_cursor`, `has_more` từ envelope thay vì mảng trần, loại bỏ phỏng đoán `hasMore` ở client.

## Phạm vi bổ sung (ghi nhận 2026-11-25)

Các thay đổi sau nằm trong cùng nhánh `feature/unified-fullstack` nhưng **không thuộc** quy đổi RESTful ở trên. Chúng được giữ lại vì frontend đã dùng, và được ghi nhận ở đây để có căn cứ review:

- **Sơ đồ bãi công khai (G24):** `PublicBayStatus` là enum (`busy` / `idle` / `fault`), thêm `PublicBay` và `ZoneQueue` theo vùng. `GET /resident/site-map` trả về `ResidentSiteMap`. Vùng hàng chờ lấy từ cấu hình đầu nối (`queue_zones`), không viết cứng AC/DC. Bản tin WebSocket `site_occupancy` được **tạm tắt** (chưa có consumer); kiểu tin nhắn và cơ chế realtime vẫn giữ để bật lại khi có màn hình realtime.
- **Phê duyệt và Guard (G7):** approval mang thêm `current_power_kw`, `effective_from`, `effective_until`. Dispatcher vẫn là chokepoint duy nhất gửi lệnh tới trạm.
- **Phương án thay thế (G6):** `Alternative.request` là yêu cầu đã chỉnh sẵn để cư dân đặt ngay.
- **Chat:** phản hồi HITL có tiền tố `[CẦN PHÊ DUYỆT]`, không lộ tên tool nội bộ; chỉ `confirm_booking` mang proposal của lượt đó; `BLOCKED_BY_HUMAN` không được tính là đặt lịch thành công (G4).
- **Bảo mật:** gỡ chế độ demo `/dev/agent` và `DEMO_RESIDENT` (`AGENT_PLAYGROUND`), vì token rỗng hoặc `"demo"` từng cho phép truy cập không xác thực.
- **Lỗi trùng khoá:** `is_unique_violation` nhận diện UNIQUE bằng SQLSTATE (`23505`) của driver; SQLite (không có SQLSTATE) dùng thông báo `UNIQUE constraint failed`.
- **Phân trang:** `before` có giới hạn int64 (`422` thay vì `500`); logic `limit+1` nằm trong `station_service.build_decision_page`, router chỉ gọi service.
- **Tiền tố API:** `API_PREFIX` định nghĩa tại `src/api/paths.py`, dùng chung cho router và `Location` header.
- **Frontend:** hook `useLoadMore` dùng chung cho tab "Bị Guard chặn" và "Nhật ký"; tab remount khi trang đầu đổi để tránh bỏ sót lệnh.
- **Script:** `scripts/_pyrun.sh` nhận diện Python của Windows Store alias; `scripts/dev/use-shared-env.ps1` kích hoạt venv dùng chung.

Trạng thái ADR vẫn là **Proposed** cho đến khi người duyệt chấp nhận.
