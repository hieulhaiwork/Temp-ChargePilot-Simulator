# ADR-008: Quy ước API — error envelope, idempotency, versioning

- Trạng thái: Proposed — nhóm đã duyệt 2026-11-17, chờ mentor. **Sửa đổi một phần — xem ghi chú bên dưới.**
- Ngày: 2026-11-17
- Plan chi tiết: [`docs/plan/10-backend.md`](../plan/10-backend.md) §4


> **Sửa đổi một phần:** [ADR-014](ADR-014-decision-trace-counterfactual-hitl.md) §8, 2026-11-21: envelope và quy ước giữ nguyên. Thêm mã `stale_state_version` (409), `patch_not_allowed` (403), `job_pending` (202); idempotency áp cho approve / reject / apply revision.
>
> **Sửa đổi một phần:** [ADR-020](ADR-020-chuan-hoa-restful-api.md), 2026-11-25: cho phép breaking change đồng bộ trên `/api/v1` trong giai đoạn nội bộ để chuẩn hoá RESTful (HTTP methods `GET`/`PATCH`/`DELETE 204`, URI danh từ số nhiều, `201` + `Location`, và pagination envelope `DecisionLogPage` cho cursor endpoints).

## Bối cảnh

Lỗi hiện trả theo dạng mặc định của FastAPI (`{"detail": …}`), riêng 501 có thêm `status`. Frontend cần phân biệt
"chưa implement", "hết phiên", "xung đột trạng thái", "LLM không dùng được" mà không phải dò chuỗi. `routes.py` bọc mọi
exception thành 500 kèm `str(exc)`: làm `NotImplementedError` thành 500 và lộ thông tin nội bộ. Service được gọi từ cả
router lẫn tool của Agent nên không thể ném `HTTPException`. Người dùng bấm "Xác nhận" hai lần không được tạo hai booking.

## Quyết định

- **Envelope lỗi** (chỉ thêm field, giữ `detail`): `{"detail", "code", "task_id", "request_id"}`. 501 giữ thêm
  `status: "not_implemented"`. Lỗi 422 giữ nguyên dạng mặc định của FastAPI.
- **`DomainError(code, detail, http_status)`** ở `src/services/errors.py`; `ErrorCode` ở `src/models/api.py`. Router map
  sang HTTP qua một handler chung; tool của Agent map sang JSON `{"error": code}`.
- **`X-Request-ID`**: middleware nhận hoặc sinh, trả lại trong header và trong envelope.
- **Idempotency**: `POST /resident/bookings` nhận header `Idempotency-Key`. Cùng key + cùng body trả booking cũ; cùng
  key khác body trả 409 `idempotency_mismatch`. Luồng chat dùng key `chat:{session_id}`.
- **Versioning**: trong `/api/v1` chỉ thêm. Hợp đồng được chụp vào `frontend/openapi.json`;
  `tests/test_api/test_openapi_snapshot.py` fail khi code và bản chụp lệch nhau.
- **`GET /ready`**: readiness (config, database); `GET /health` giữ là liveness không đụng DB.

## Hệ quả

- Client cũ đọc `detail` vẫn chạy.
- Đổi hợp đồng phải chạy `python scripts/export_openapi.py` và `npm run gen:api` trong cùng thay đổi.
- Lỗi không lường trước trả 500 với thông điệp chung; chi tiết chỉ nằm trong log kèm `request_id`.
- Một cư dân tối đa một booking đang hiệu lực (mặc định Q6): cái thứ hai trả 409 `booking_conflict`.
