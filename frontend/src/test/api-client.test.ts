import { describe, expect, it } from "vitest";

import { ApiError, MAX_RETRIES, isRetryable, networkError, retryDelayMs, shouldRetry, toApiError } from "@/lib/api/errors";

describe("toApiError — envelope lỗi của backend (ADR-008)", () => {
  it("đọc code, task_id và request_id của lỗi 501", () => {
    const error = toApiError(501, {
      detail: "[T2.2] queue_status — vị trí + ETA",
      code: "not_implemented",
      task_id: "T2.2",
      request_id: "abc",
      status: "not_implemented",
    });
    expect(error).toBeInstanceOf(ApiError);
    expect(error.isNotImplemented).toBe(true);
    expect(error.taskId).toBe("T2.2");
    expect(error.requestId).toBe("abc");
  });

  it("gom lỗi 422 của FastAPI thành danh sách theo ô nhập", () => {
    const error = toApiError(422, {
      detail: [{ loc: ["body", "soc_target"], msg: "Field required", type: "missing" }],
    });
    expect(error.code).toBe("validation_error");
    expect(error.fields).toEqual([{ path: "soc_target", message: "Field required" }]);
  });

  it("không vỡ khi body không phải envelope", () => {
    const error = toApiError(502, "Bad Gateway", "req-9");
    expect(error.code).toBe("unknown");
    expect(error.requestId).toBe("req-9");
  });
});

describe("chính sách thử lại — backend Render free đang thức dậy", () => {
  it("thử lại lỗi mạng và 502/503/504", () => {
    expect(isRetryable(networkError(new TypeError("Failed to fetch")))).toBe(true);
    for (const status of [502, 503, 504]) {
      expect(isRetryable(toApiError(status, { detail: "x", code: "database_unavailable" }))).toBe(true);
    }
  });

  it("KHÔNG thử lại 501, 4xx và llm_unavailable", () => {
    expect(isRetryable(toApiError(501, { detail: "[T2.2]", code: "not_implemented" }))).toBe(false);
    expect(isRetryable(toApiError(401, { detail: "x", code: "unauthenticated" }))).toBe(false);
    expect(isRetryable(toApiError(409, { detail: "x", code: "booking_conflict" }))).toBe(false);
    // 503 nhưng phải chuyển sang form thay vì chờ (NFR khả dụng)
    expect(isRetryable(toApiError(503, { detail: "x", code: "llm_unavailable" }))).toBe(false);
    expect(isRetryable(new Error("lỗi lạ"))).toBe(false);
  });

  it("backoff 1, 2, 4, 8, 15, 15… giây và dừng sau MAX_RETRIES lần", () => {
    expect([0, 1, 2, 3, 4, 5].map(retryDelayMs)).toEqual([1000, 2000, 4000, 8000, 15_000, 15_000]);
    const waking = networkError(null);
    expect(shouldRetry(0, waking)).toBe(true);
    expect(shouldRetry(MAX_RETRIES, waking)).toBe(false);
    const total = Array.from({ length: MAX_RETRIES }, (_, index) => retryDelayMs(index)).reduce((a, b) => a + b, 0);
    expect(total).toBeGreaterThanOrEqual(60_000); // đủ dài để phủ thời gian thức dậy ~1 phút
  });
});
