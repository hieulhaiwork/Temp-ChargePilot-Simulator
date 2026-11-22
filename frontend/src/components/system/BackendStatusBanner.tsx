"use client";

/**
 * Backend chạy trên Render free: ngủ sau 15 phút không có request, thức lại mất khoảng 1 phút.
 * Banner này gọi GET /health khi mở app, báo rõ "đang khởi động" trong lúc thử lại, và gọi lại mỗi
 * 5 phút khi tab đang hiển thị để backend không ngủ giữa buổi demo (docs/plan/20-frontend.md §7.1).
 */
import { useQuery } from "@tanstack/react-query";

import { queries } from "@/lib/api/queries";

const KEEP_AWAKE_MS = 5 * 60 * 1000;

export function BackendStatusBanner() {
  const health = useQuery({
    ...queries.health(),
    refetchInterval: KEEP_AWAKE_MS,
    refetchIntervalInBackground: false, // tab ẩn thì thôi giữ thức
  });

  if (health.isSuccess) return null;

  if (health.isError) {
    return (
      <div role="alert" className="flex items-center justify-between gap-3 bg-red-100 px-4 py-2 text-sm text-red-900">
        <span>Không kết nối được máy chủ.</span>
        <button
          type="button"
          onClick={() => void health.refetch()}
          className="min-h-11 rounded border border-red-700 px-3 py-1 font-medium"
        >
          Thử lại
        </button>
      </div>
    );
  }

  if (health.failureCount === 0) return null; // lần gọi đầu chưa xong — chưa cần báo gì

  return (
    <div role="status" aria-live="polite" className="bg-amber-100 px-4 py-2 text-sm text-amber-900">
      Máy chủ đang khởi động, thường mất khoảng 1 phút. Đang thử lại (lần {health.failureCount})…
    </div>
  );
}
