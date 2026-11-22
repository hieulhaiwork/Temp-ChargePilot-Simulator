"use client";

/**
 * Khối dữ liệu của một màn: gọi MỘT query và hiện một trong bốn trạng thái —
 * đang tải (skeleton) · chưa cài (501 + task ID, ADR-004) · lỗi (kèm thử lại) · dữ liệu (render bằng `children`).
 * Bọc theo TỪNG KHỐI: một endpoint 501 hay lỗi không làm hỏng phần còn lại của trang.
 */
import { useQuery, type QueryKey, type UseQueryOptions } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/blocks";
import { ApiError } from "@/lib/api/errors";

import { ErrorPanel } from "./ErrorPanel";
import { NotImplementedPanel } from "./NotImplementedPanel";

type Props<TData, TKey extends QueryKey> = {
  /** Hiển thị cho người phát triển khi backend còn 501, vd "GET /api/v1/resident/queue". */
  endpoint: string;
  query: UseQueryOptions<TData, Error, TData, TKey>;
  /** Hỏi lại định kỳ (ms) — dùng khi WebSocket chưa có. */
  refetchInterval?: number;
  /** Số dòng skeleton lúc đang tải. */
  loadingLines?: number;
  children: (data: TData) => ReactNode;
};

export function DataBlock<TData, TKey extends QueryKey>({
  endpoint,
  query,
  refetchInterval,
  loadingLines = 3,
  children,
}: Props<TData, TKey>) {
  const result = useQuery({ ...query, refetchInterval });

  if (result.isPending) {
    return (
      <div>
        <Skeleton lines={loadingLines} />
        {result.failureCount > 0 ? <p className="hint">Đang thử lại lần {result.failureCount}…</p> : null}
      </div>
    );
  }
  if (result.isError) {
    return result.error instanceof ApiError && result.error.isNotImplemented ? (
      <NotImplementedPanel endpoint={endpoint} taskId={result.error.taskId} detail={result.error.detail} />
    ) : (
      <ErrorPanel error={result.error} onRetry={() => void result.refetch()} />
    );
  }
  return <>{children(result.data)}</>;
}
