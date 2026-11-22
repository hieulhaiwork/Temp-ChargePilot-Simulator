/**
 * API client có type — sinh từ frontend/openapi.json (ADR-009). KHÔNG gõ tay DTO:
 * đổi model ở backend → `python scripts/export_openapi.py` → `npm run gen:api`.
 */
import createClient, { type Middleware } from "openapi-fetch";

import { clearSession, getToken } from "@/lib/auth/session";
import { API_URL } from "@/lib/env";

import { networkError, toApiError } from "./errors";
import type { paths } from "./schema";

export const api = createClient<paths>({ baseUrl: API_URL });

/** Gắn token đăng nhập vào mọi request. Token không bao giờ nằm trên URL. */
const authMiddleware: Middleware = {
  onRequest({ request }) {
    const token = getToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
};
api.use(authMiddleware);

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/**
 * Chuyển kết quả `{ data, error, response }` của openapi-fetch thành: trả `data` hoặc NÉM ApiError.
 * - fetch() ném lỗi (mất mạng, backend đang ngủ) → ApiError status 0, có thể thử lại.
 * - 401 → xoá phiên; AuthGate sẽ đưa người dùng về /login.
 */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await call;
  } catch (cause) {
    throw networkError(cause);
  }
  if (result.response.ok) return result.data as T;
  const error = toApiError(result.response.status, result.error, result.response.headers.get("X-Request-ID"));
  if (error.status === 401) clearSession();
  throw error;
}

/** Khoá idempotency cho thao tác đặt lịch (ADR-008): bấm "Xác nhận" hai lần không tạo hai booking. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
