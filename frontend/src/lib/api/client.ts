/**
 * API client có type — sinh từ frontend/openapi.json (ADR-009). KHÔNG gõ tay DTO:
 * đổi model ở backend → `python scripts/export_openapi.py` → `npm run gen:api`.
 */
import createClient, { type Middleware } from "openapi-fetch";

import { clearSessionIfCurrent, getSession } from "@/lib/auth/session";
import { API_URL } from "@/lib/env";

import { networkError, toApiError } from "./errors";
import type { paths } from "./schema";

export const api = createClient<paths>({ baseUrl: API_URL });

/** Gắn token đăng nhập vào mọi request. Token không bao giờ nằm trên URL. */
const requestGenerations = new WeakMap<Request, number>();
const authMiddleware: Middleware = {
  onRequest({ request }) {
    const session = getSession();
    if (session) {
      request.headers.set("Authorization", `Bearer ${session.token}`);
      requestGenerations.set(request, session.generation);
    }
    return request;
  },
  onResponse({ request, response }) {
    if (response.status === 401) clearSessionIfCurrent(requestGenerations.get(request));
  },
};
api.use(authMiddleware);

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/**
 * Chuyển kết quả `{ data, error, response }` của openapi-fetch thành: trả `data` hoặc NÉM ApiError.
 * - fetch() ném lỗi (mất mạng, backend đang ngủ) → ApiError status 0, có thể thử lại.
 * - Middleware xử lý 401 trong phạm vi phiên đã gửi request.
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
  throw error;
}

/** Khoá idempotency cho thao tác đặt lịch (ADR-008): bấm "Xác nhận" hai lần không tạo hai booking. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
