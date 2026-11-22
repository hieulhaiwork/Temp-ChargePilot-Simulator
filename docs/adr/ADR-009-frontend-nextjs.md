# ADR-009: Frontend Next.js trong `frontend/`, chỉ nhận `openapi.json` từ backend

- Trạng thái: Proposed — nhóm đã duyệt 2026-11-17, chờ mentor
- Ngày: 2026-11-17
- Plan chi tiết: [`docs/plan/20-frontend.md`](../plan/20-frontend.md)

## Bối cảnh

PRD §7 đề xuất React + thư viện biểu đồ + WebSocket, deploy có live URL. Backend là contract-first (ADR-004): mọi
endpoint đã có schema trên OpenAPI. Hai nửa nằm chung một repo, nên rất dễ xuất hiện DTO gõ tay lệch với Pydantic.

## Quyết định

- Next.js (App Router) + TypeScript trong thư mục `frontend/`, tạo bằng `create-next-app`; Vercel đặt Root Directory =
  `frontend`.
- **Ranh giới duy nhất** với backend là file `frontend/openapi.json`, do `scripts/export_openapi.py` ghi.
  `npm run gen:api` (`openapi-typescript`) sinh `src/lib/api/schema.d.ts`; không gõ tay DTO.
- Gọi REST bằng `openapi-fetch`; cache và retry bằng `@tanstack/react-query`; biểu đồ tải bằng `recharts`; Gantt tự
  viết bằng CSS grid.
- Trang có dữ liệu người dùng là Client Component: token nằm ở trình duyệt (ADR-006).
- WebSocket nối thẳng từ trình duyệt tới backend, không đi qua Vercel.
- Mỗi khối dữ liệu tự xử lý 501 bằng `NotImplementedPanel` (hiện task ID), để dựng được đủ màn khi backend còn stub.

## Hệ quả

- `tests/test_architecture.py` thêm luật: không file nào trong `frontend/src/` import đường dẫn trỏ ra ngoài `frontend/`.
- Kiểu payload WebSocket không tự có trên OpenAPI: `src/lib/ws/types.ts` ánh xạ `type` sang model đã sinh.
- Phải mở công cụ AI ở repo root, không mở trong `frontend/` (hook AI-log dùng đường dẫn tương đối).
- `frontend/` bị loại khỏi image Docker của backend.
