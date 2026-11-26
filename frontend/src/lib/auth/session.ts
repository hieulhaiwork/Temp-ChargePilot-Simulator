"use client";

/**
 * Phiên đăng nhập phía web (ADR-006): JWT gửi qua header Authorization, lưu ở sessionStorage.
 * Không dùng cookie vì web (*.vercel.app) và backend (*.onrender.com) khác site.
 *
 * `useSession()` trả:
 *   undefined → chưa biết (đang render phía server / đang hydrate) — hiện trạng thái chờ
 *   null      → chưa đăng nhập
 *   Session   → đã đăng nhập
 * Đây chỉ là trải nghiệm người dùng; phân quyền thật do backend quyết định (401/403).
 */
import { useSyncExternalStore } from "react";

import type { components } from "@/lib/api/schema";

export type Role = components["schemas"]["Role"];

export type Session = {
  token: string;
  role: Role;
  userId: string;
  displayName: string;
};

const STORAGE_KEY = "chargepilot.session";

type ActiveSession = Session & { generation: number };
let generation = 0;
let cached: ActiveSession | null | undefined;
const listeners = new Set<() => void>();

function readFromStorage(): Session | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null; // sessionStorage bị chặn hoặc dữ liệu hỏng → coi như chưa đăng nhập
  }
}

function snapshot(): ActiveSession | null {
  if (cached === undefined) {
    const stored = readFromStorage();
    cached = stored ? { ...stored, generation: ++generation } : null;
  }
  return cached;
}

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Đọc phiên ngoài React (API client, WebSocket). Phía server luôn trả null. */
export function getSession(): ActiveSession | null {
  return typeof window === "undefined" ? null : snapshot();
}

export function getToken(): string | null {
  return getSession()?.token ?? null;
}

export function setSession(session: Session): void {
  cached = { ...session, generation: ++generation };
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Không lưu được thì phiên chỉ sống tới khi tải lại trang.
  }
  emit();
}

/** Đăng xuất, hoặc backend trả 401 (token hết hạn). */
export function clearSession(): void {
  cached = null;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // bỏ qua
  }
  emit();
}

export function clearSessionIfCurrent(generation: number | undefined): void {
  if (generation !== undefined && getSession()?.generation === generation) clearSession();
}

export function useSession(): ActiveSession | null | undefined {
  return useSyncExternalStore(subscribe, snapshot, () => undefined);
}

/** Trang chủ của từng vai trò (S2 cho cư dân, S5 cho vận hành). */
export function homePathFor(role: Role): string {
  return role === "operator" ? "/operator" : "/resident";
}
