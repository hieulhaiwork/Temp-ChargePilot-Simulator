/**
 * Biến môi trường công khai của web. KHÔNG đặt secret vào biến NEXT_PUBLIC_* — chúng nằm trong bundle.
 * Mặc định trỏ backend local để `npm run dev` chạy được ngay.
 */
const DEFAULT_API_URL = "http://localhost:8000";

function trimTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

/** Gốc REST của backend, vd https://p019-backend.onrender.com (không có /api/v1). */
export const API_URL = trimTrailingSlash(process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL);

/**
 * Gốc WebSocket. Trình duyệt nối THẲNG tới backend (Vercel Hobby không giữ kết nối WebSocket).
 * Bỏ trống thì suy từ API_URL: http → ws, https → wss.
 */
export const WS_URL = trimTrailingSlash(process.env.NEXT_PUBLIC_WS_URL || API_URL.replace(/^http/, "ws"));

export const API_PREFIX = "/api/v1";
