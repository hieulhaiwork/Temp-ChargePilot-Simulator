/**
 * WebSocket tự nối lại (FR16) — giao thức ở docs/plan/10-backend.md §8:
 *   1. mở kết nối → gửi {"type":"auth","token"} → server trả snapshot đầy đủ rồi chỉ gửi thay đổi;
 *   2. mất kết nối → thử lại theo backoff 1, 2, 4, 8, 16, 30 giây (có jitter), thành công thì về 1 giây;
 *   3. ping 25 giây; 10 giây không có pong → tự đóng để nối lại;
 *   4. nối lại thành công → gọi onReconnect (màn hình làm mới dữ liệu REST, vì server không phát lại);
 *   5. mã đóng 4401 / 4403 / 1011 → DỪNG, không thử lại.
 *
 * Không phụ thuộc React hay DOM ngoài `WebSocket`; socket và nguồn ngẫu nhiên tiêm được để test.
 */
import { WS_CLOSE, type WsClientMessage, type WsMessage } from "./types";

export type SocketStatus =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed" // đã stop() chủ động
  | "unauthorized" // 4401 — token sai / hết hạn → đăng xuất
  | "forbidden" // 4403 — sai vai trò
  | "not_implemented"; // 1011 — backend chưa cài realtime [T3.6] → chuyển sang hỏi lại REST

export const BACKOFF_MS = [1000, 2000, 4000, 8000, 16_000, 30_000] as const;
export const PING_INTERVAL_MS = 25_000;
export const PONG_TIMEOUT_MS = 10_000;
/** Mã đóng do client tự dùng khi không nhận được pong. */
export const CLOSE_PONG_TIMEOUT = 4000;

/** Độ trễ trước lần nối lại thứ `attempt` (0 = lần đầu), có jitter ±20% để các tab không nối cùng lúc. */
export function backoffDelay(attempt: number, random: () => number = Math.random): number {
  const base = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
  return Math.round(base * (0.8 + 0.4 * random()));
}

export type SocketLike = {
  send(data: string): void;
  close(code?: number, reason?: string): void;
  onopen: (() => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code: number; reason: string }) => void) | null;
  onerror: (() => void) | null;
};

export type ReconnectingSocketOptions = {
  url: string;
  getToken: () => string | null;
  onMessage: (message: WsMessage) => void;
  onStatus: (status: SocketStatus, detail?: string) => void;
  onReconnect?: () => void;
  createSocket?: (url: string) => SocketLike;
  random?: () => number;
};

const TERMINAL_CLOSE: Record<number, SocketStatus> = {
  [WS_CLOSE.UNAUTHENTICATED]: "unauthorized",
  [WS_CLOSE.FORBIDDEN]: "forbidden",
  [WS_CLOSE.NOT_IMPLEMENTED]: "not_implemented",
};

export class ReconnectingSocket {
  private socket: SocketLike | null = null;
  private attempt = 0;
  private everOpened = false;
  private stopped = true;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private pongTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly options: ReconnectingSocketOptions) {}

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.attempt = 0;
    this.connect("connecting");
  }

  stop(): void {
    this.stopped = true;
    this.clearTimers();
    this.socket?.close(1000, "client stop");
    this.socket = null;
    this.options.onStatus("closed");
  }

  private connect(status: SocketStatus): void {
    const token = this.options.getToken();
    if (!token) {
      this.stopped = true;
      this.options.onStatus("unauthorized");
      return;
    }
    this.options.onStatus(status);
    const create = this.options.createSocket ?? ((url: string) => new WebSocket(url) as unknown as SocketLike);
    const socket = create(this.options.url);
    this.socket = socket;

    socket.onopen = () => {
      this.send({ type: "auth", token });
      const wasReconnect = this.everOpened;
      this.everOpened = true;
      this.attempt = 0;
      this.options.onStatus("open");
      this.startHeartbeat();
      if (wasReconnect) this.options.onReconnect?.();
    };
    socket.onmessage = (event) => this.handleMessage(event.data);
    socket.onerror = () => {
      // Trình duyệt luôn bắn `close` sau `error` — xử lý nối lại ở onclose.
    };
    socket.onclose = (event) => this.handleClose(event.code, event.reason);
  }

  private handleMessage(data: unknown): void {
    if (typeof data !== "string") return;
    let message: WsMessage;
    try {
      message = JSON.parse(data) as WsMessage;
    } catch {
      return; // bản tin không phải JSON — bỏ qua, không làm rơi kết nối
    }
    if (message.type === "pong") {
      if (this.pongTimer) clearTimeout(this.pongTimer);
      this.pongTimer = null;
      return;
    }
    this.options.onMessage(message);
  }

  private handleClose(code: number, reason: string): void {
    this.clearTimers();
    this.socket = null;
    if (this.stopped) return;
    const terminal = TERMINAL_CLOSE[code];
    if (terminal) {
      this.stopped = true;
      this.options.onStatus(terminal, reason);
      return;
    }
    this.options.onStatus("reconnecting");
    const delay = backoffDelay(this.attempt, this.options.random);
    this.attempt += 1;
    this.reconnectTimer = setTimeout(() => this.connect("reconnecting"), delay);
  }

  private startHeartbeat(): void {
    this.pingTimer = setInterval(() => {
      this.send({ type: "ping" });
      if (this.pongTimer) return; // đang chờ pong của lần trước
      this.pongTimer = setTimeout(() => this.socket?.close(CLOSE_PONG_TIMEOUT, "pong timeout"), PONG_TIMEOUT_MS);
    }, PING_INTERVAL_MS);
  }

  private send(message: WsClientMessage): void {
    this.socket?.send(JSON.stringify(message));
  }

  private clearTimers(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.pingTimer) clearInterval(this.pingTimer);
    if (this.pongTimer) clearTimeout(this.pongTimer);
    this.reconnectTimer = null;
    this.pingTimer = null;
    this.pongTimer = null;
  }
}
