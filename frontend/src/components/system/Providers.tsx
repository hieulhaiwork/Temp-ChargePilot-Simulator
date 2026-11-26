"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useMemo, type ReactNode } from "react";

import { retryDelayMs, shouldRetry } from "@/lib/api/errors";

import { useSession } from "@/lib/auth/session";

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

export function Providers({ children }: { children: ReactNode }) {
  const generation = useSession()?.generation;
  const client = useMemo(() => {
    // A login generation owns its cache, including in-flight requests.
    void generation;
    return makeQueryClient();
  }, [generation]);
  return <QueryClientProvider key={generation ?? "anonymous"} client={client}>{children}</QueryClientProvider>;
}
