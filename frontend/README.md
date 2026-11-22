# ChargePilot — web (Next.js)

Web hai vai trò của ChargePilot (đề tài SC-16, nhóm T019): cư dân trên điện thoại, vận hành trạm trên máy tính.
Hệ thống là **mô phỏng**; dữ liệu không phải của trạm sạc thật.

Thiết kế và phân việc: [`docs/plan/20-frontend.md`](../docs/plan/20-frontend.md) · quyết định: [`ADR-009`](../docs/adr/ADR-009-frontend-nextjs.md).

> Phiên bản Next.js ở đây có thay đổi so với các bản cũ. Trước khi viết code, đọc `AGENTS.md` và tài liệu đi kèm
> trong `node_modules/next/dist/docs/`.
>
> Mở công cụ AI (Claude Code, Cursor, Codex…) ở **repo root**, không mở trong `frontend/`: hook ghi AI-log dùng đường
> dẫn tương đối `scripts/…`.

## Chạy

```bash
cp .env.example .env.local     # trỏ NEXT_PUBLIC_API_URL tới backend
npm install
npm run dev                    # http://localhost:3000 (backend: uvicorn src.main:app --reload ở repo root)
```

## Lệnh

| Lệnh | Việc |
|---|---|
| `npm run gen:api` | Sinh `src/lib/api/schema.d.ts` từ `openapi.json` |
| `npm run lint` · `npm run typecheck` · `npm test` · `npm run build` | Bốn bước CI của web |

## Ranh giới với backend

Web chỉ nhận **một** thứ từ backend: `openapi.json`. Khi backend đổi model hoặc endpoint:

```bash
# ở repo root
python scripts/export_openapi.py
# ở frontend/
npm run gen:api
```

Không gõ tay DTO và không import gì từ ngoài `frontend/` (`tests/test_architecture.py` kiểm điều này).

## Cấu trúc

```text
src/app/            route theo Wireframe: /login (S1) · /resident/* (S2–S4) · /operator/* (S5–S8)
src/components/     auth/ (AuthGate, LoginForm) · system/ (banner backend, khối 501, lỗi, khung vai trò)
src/lib/api/        client có type, lỗi + chính sách thử lại, query key
src/lib/auth/       phiên đăng nhập (sessionStorage)
src/lib/ws/         WebSocket tự nối lại + kiểu bản tin
src/test/           vitest
```

Trạng thái: **skeleton**. Mỗi trang gọi đúng endpoint của mình và hiện dữ liệu thô, hoặc khối
"Chức năng này chưa được cài đặt — task Txx" khi backend trả 501.
