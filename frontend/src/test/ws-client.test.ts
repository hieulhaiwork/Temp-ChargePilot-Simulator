import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  BACKOFF_MS,
  CLOSE_PONG_TIMEOUT,
  PING_INTERVAL_MS,
  PONG_TIMEOUT_MS,
  ReconnectingSocket,
  backoffDelay,
  type SocketLike,
  type SocketStatus,
} from "@/lib/ws/client";

class FakeSocket implements SocketLike {
  sent: string[] = [];
  closedWith: number | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onerror: (() => void) | null = null;

  send(data: string): void {
    this.sent.push(data);
  }

  close(code = 1000, reason = ""): void {
    this.closedWith = code;
    this.onclose?.({ code, reason });
  }

  /** Server (hoặc mạng) đóng kết nối. */
  serverClose(code: number, reason = ""): void {
    this.onclose?.({ code, reason });
  }
}

function setup(token: string | null = "jwt-1") {
  const sockets: FakeSocket[] = [];
  const statuses: SocketStatus[] = [];
  const messages: unknown[] = [];
  const onReconnect = vi.fn();
  const client = new ReconnectingSocket({
    url: "ws://test/api/v1/ws/operator",
    getToken: () => token,
    onMessage: (message) => messages.push(message),
    onStatus: (status) => statuses.push(status),
    onReconnect,
    createSocket: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
    random: () => 0.5, // jitter = 0 → độ trễ đúng bằng BACKOFF_MS
  });
  return { client, sockets, statuses, messages, onReconnect };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("ReconnectingSocket", () => {
  it("gửi token trong bản tin ĐẦU, không đặt trên URL (ADR-006)", () => {
    const { client, sockets, statuses } = setup();
    client.start();
    sockets[0].onopen?.();
    expect(JSON.parse(sockets[0].sent[0])).toEqual({ type: "auth", token: "jwt-1" });
    expect(statuses).toEqual(["connecting", "open"]);
  });

  it("không có token thì không mở kết nối", () => {
    const { client, sockets, statuses } = setup(null);
    client.start();
    expect(sockets).toHaveLength(0);
    expect(statuses).toEqual(["unauthorized"]);
  });

  it("nối lại theo backoff tăng dần và báo onReconnect khi thành công", () => {
    const { client, sockets, statuses, onReconnect } = setup();
    client.start();
    sockets[0].onopen?.();

    sockets[0].serverClose(1006);
    expect(statuses.at(-1)).toBe("reconnecting");
    vi.advanceTimersByTime(BACKOFF_MS[0] - 1);
    expect(sockets).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(sockets).toHaveLength(2);

    sockets[1].serverClose(1006); // lần hai thất bại trước khi mở → chờ lâu hơn
    vi.advanceTimersByTime(BACKOFF_MS[1]);
    expect(sockets).toHaveLength(3);

    sockets[2].onopen?.();
    expect(onReconnect).toHaveBeenCalledTimes(1);
    expect(statuses.at(-1)).toBe("open");
  });

  it("về lại 1 giây sau một lần nối thành công", () => {
    const { client, sockets } = setup();
    client.start();
    sockets[0].serverClose(1006);
    vi.advanceTimersByTime(BACKOFF_MS[0]);
    sockets[1].onopen?.();
    sockets[1].serverClose(1006);
    vi.advanceTimersByTime(BACKOFF_MS[0]);
    expect(sockets).toHaveLength(3);
  });

  it.each([
    [4401, "unauthorized"],
    [4403, "forbidden"],
    [1011, "not_implemented"],
  ] as const)("mã đóng %i → %s và KHÔNG thử lại", (code, expected) => {
    const { client, sockets, statuses } = setup();
    client.start();
    sockets[0].onopen?.();
    sockets[0].serverClose(code, "[T3.6] WebSocket chưa implement");
    expect(statuses.at(-1)).toBe(expected);
    vi.advanceTimersByTime(120_000);
    expect(sockets).toHaveLength(1);
  });

  it("không nhận pong trong 10 giây thì tự đóng để nối lại", () => {
    const { client, sockets } = setup();
    client.start();
    sockets[0].onopen?.();
    vi.advanceTimersByTime(PING_INTERVAL_MS);
    expect(JSON.parse(sockets[0].sent.at(-1) ?? "{}")).toEqual({ type: "ping" });
    vi.advanceTimersByTime(PONG_TIMEOUT_MS);
    expect(sockets[0].closedWith).toBe(CLOSE_PONG_TIMEOUT);
  });

  it("có pong thì giữ kết nối; pong không lọt ra onMessage", () => {
    const { client, sockets, messages } = setup();
    client.start();
    sockets[0].onopen?.();
    vi.advanceTimersByTime(PING_INTERVAL_MS);
    sockets[0].onmessage?.({ data: JSON.stringify({ type: "pong", payload: {}, sent_at: "2026-11-16T12:00:00Z" }) });
    vi.advanceTimersByTime(PONG_TIMEOUT_MS);
    expect(sockets[0].closedWith).toBeNull();
    expect(messages).toEqual([]);
  });

  it("chuyển bản tin nghiệp vụ cho onMessage và bỏ qua bản tin hỏng", () => {
    const { client, sockets, messages } = setup();
    client.start();
    sockets[0].onopen?.();
    sockets[0].onmessage?.({ data: "không phải JSON" });
    sockets[0].onmessage?.({ data: JSON.stringify({ type: "event", payload: { type: "tick" }, sent_at: "x" }) });
    expect(messages).toHaveLength(1);
  });

  it("stop() thì không nối lại nữa", () => {
    const { client, sockets, statuses } = setup();
    client.start();
    sockets[0].onopen?.();
    client.stop();
    vi.advanceTimersByTime(120_000);
    expect(sockets).toHaveLength(1);
    expect(statuses.at(-1)).toBe("closed");
  });
});

describe("backoffDelay", () => {
  it("giữ ở mức trần 30 giây và có jitter ±20%", () => {
    expect(backoffDelay(99, () => 0.5)).toBe(30_000);
    expect(backoffDelay(0, () => 0)).toBe(800);
    expect(backoffDelay(0, () => 1)).toBe(1200);
  });
});
