/**
 * Lỗi API ở phía web — bám envelope của backend (ADR-008):
 *   { detail, code, task_id?, request_id?, status? }
 * 422 giữ dạng mặc định của FastAPI: `detail` là MẢNG lỗi theo từng ô nhập.
 */
import type { components } from "./schema";

type BackendErrorCode = components["schemas"]["ErrorCode"];

/** Mã của backend + ba mã chỉ có ở phía web. */
export type ApiErrorCode = BackendErrorCode | "network_error" | "validation_error" | "unknown";

export type FieldError = { path: string; message: string };

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly detail: string;
  readonly taskId: string | null;
  readonly requestId: string | null;
  readonly fields: FieldError[];

  constructor(init: {
    status: number;
    code: ApiErrorCode;
    detail: string;
    taskId?: string | null;
    requestId?: string | null;
    fields?: FieldError[];
  }) {
    super(init.detail);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.detail = init.detail;
    this.taskId = init.taskId ?? null;
    this.requestId = init.requestId ?? null;
    this.fields = init.fields ?? [];
  }

  /** Endpoint đã có hợp đồng nhưng backend chưa cài — hiện NotImplementedPanel kèm task ID. */
  get isNotImplemented(): boolean {
    return this.status === 501;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Dựng ApiError từ mã HTTP + body lỗi (bất kể body có đúng envelope hay không). */
export function toApiError(status: number, body: unknown, requestIdHeader?: string | null): ApiError {
  if (isRecord(body) && Array.isArray(body.detail)) {
    const fields = body.detail.filter(isRecord).map((item) => ({
      path: Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "",
      message: typeof item.msg === "string" ? item.msg : "Giá trị không hợp lệ",
    }));
    return new ApiError({
      status,
      code: "validation_error",
      detail: "Dữ liệu gửi lên chưa hợp lệ",
      requestId: requestIdHeader,
      fields,
    });
  }
  if (isRecord(body)) {
    return new ApiError({
      status,
      code: typeof body.code === "string" ? (body.code as ApiErrorCode) : "unknown",
      detail: typeof body.detail === "string" ? body.detail : `Lỗi HTTP ${status}`,
      taskId: typeof body.task_id === "string" ? body.task_id : null,
      requestId: typeof body.request_id === "string" ? body.request_id : requestIdHeader,
    });
  }
  return new ApiError({ status, code: "unknown", detail: `Lỗi HTTP ${status}`, requestId: requestIdHeader });
}

/** fetch() ném lỗi (mất mạng, CORS, backend đang ngủ chưa nhận kết nối) → status 0. */
export function networkError(cause: unknown): ApiError {
  const error = new ApiError({ status: 0, code: "network_error", detail: "Không kết nối được máy chủ" });
  error.cause = cause;
  return error;
}

const RETRYABLE_STATUS = new Set([0, 502, 503, 504]);

/**
 * Chỉ thử lại lỗi TẠM THỜI của hạ tầng (backend Render free đang thức dậy).
 * Không thử lại 4xx, 501 (thử lại cũng vậy) và `llm_unavailable` (phải chuyển sang form, NFR khả dụng).
 */
export function isRetryable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.code === "llm_unavailable") return false;
  return RETRYABLE_STATUS.has(error.status);
}

/** Backoff 1, 2, 4, 8, 15, 15… giây — tổng khoảng 90 giây với MAX_RETRIES lần thử lại. */
export const MAX_RETRIES = 9;

export function retryDelayMs(attemptIndex: number): number {
  return Math.min(1000 * 2 ** attemptIndex, 15_000);
}

export function shouldRetry(failureCount: number, error: unknown): boolean {
  return failureCount < MAX_RETRIES && isRetryable(error);
}
