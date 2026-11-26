"use client";

/**
 * Nối WebSocket theo vai trò và đồng bộ với cache của TanStack Query.
 *
 * Skeleton: mọi bản tin đều làm mới các truy vấn của vai trò đó (invalidate). Khi làm T3.6, thay bằng
 * setQueryData theo từng `type` để không phải gọi lại REST (bảng type → payload ở lib/ws/types.ts).
 * Backend chưa cài realtime (đóng 1011) → trạng thái `not_implemented`; component gọi hook tự chuyển
 * sang hỏi lại REST định kỳ (POLL_FALLBACK_MS).
 */
import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState } from "react";

import { clearSessionIfCurrent, getSession, useSession, type Role } from "@/lib/auth/session";
import { API_PREFIX, WS_URL } from "@/lib/env";

import { ReconnectingSocket, type SocketStatus } from "./client";

export const POLL_FALLBACK_MS = 15_000;

export type StreamState = { status: SocketStatus; detail?: string };

/** RoleShell nối WebSocket một lần cho cả vai trò và chia sẻ trạng thái qua context này. */
export const StreamContext = createContext<StreamState>({ status: "idle" });

/**
 * Khoảng hỏi lại REST cho các khối dữ liệu realtime: `undefined` khi WebSocket đang mở (dữ liệu được
 * đẩy về), POLL_FALLBACK_MS khi không có realtime (vd backend còn trả 1011).
 */
export function usePollFallback(): number | undefined {
  return useContext(StreamContext).status === "open" ? undefined : POLL_FALLBACK_MS;
}

export function useStream(role: Role): StreamState {
  const queryClient = useQueryClient();
  const generation = useSession()?.generation;
  const [state, setState] = useState<StreamState>({ status: "idle" });

  useEffect(() => {
    let active = true;
    const refresh = () => {
      if (active) void queryClient.invalidateQueries({ queryKey: [role] });
    };
    const socket = new ReconnectingSocket({
      url: `${WS_URL}${API_PREFIX}/ws/${role}`,
      getToken: () => {
        const session = getSession();
        return session?.generation === generation ? session?.token ?? null : null;
      },
      onMessage: refresh,
      onReconnect: refresh, // server không phát lại bản tin đã lỡ → làm mới qua REST
      onStatus: (status, detail) => {
        if (!active) return;
        setState({ status, detail });
        if (status === "unauthorized") clearSessionIfCurrent(generation);
      },
    });
    socket.start();
    return () => {
      active = false;
      socket.stop();
    };
  }, [generation, queryClient, role]);

  return state;
}
