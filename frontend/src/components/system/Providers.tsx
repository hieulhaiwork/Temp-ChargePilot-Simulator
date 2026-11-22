"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { retryDelayMs, shouldRetry } from "@/lib/api/errors";

let browserQueryClient: QueryClient | undefined;

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Backend Render free ngủ sau 15 phút: thử lại lỗi mạng / 502 / 503 / 504 theo backoff
        // (~90 giây). KHÔNG thử lại 4xx và 501 — xem lib/api/errors.ts.
        retry: shouldRetry,
        retryDelay: retryDelayMs,
        staleTime: 10_000,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false }, // chỉ thao tác có Idempotency-Key mới được tự thử lại — bật riêng từng cái
    },
  });
}

function getQueryClient(): QueryClient {
  // Mỗi lần render phía server một client riêng; trình duyệt dùng lại một client để giữ cache.
  if (typeof window === "undefined") return makeQueryClient();
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}

export function Providers({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={getQueryClient()}>{children}</QueryClientProvider>;
}
