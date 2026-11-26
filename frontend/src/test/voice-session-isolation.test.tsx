import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ChatAdvisory } from "@/components/copilot/ChatAdvisory";
import { ChatPanel } from "@/components/resident/ChatPanel";
import { Providers } from "@/components/system/Providers";
import { clearSession, getSession, setSession } from "@/lib/auth/session";
import { useStream } from "@/lib/ws/useStream";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  clearSession();
});

it("drops delayed FileReader transcribe from Resident A after switching to Resident B while keeping Resident B voice functional", async () => {
  const readers: Array<{ result: string; onloadend: (() => void) | null }> = [];
  class StubFileReader {
    result = "";
    onloadend: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onabort: (() => void) | null = null;
    readAsDataURL() {
      const tag = readers.length === 0 ? "A" : "B";
      this.result = `data:audio/webm;base64,${tag.repeat(200)}`;
      readers.push(this);
    }
  }
  const stopTrackA = vi.fn();
  const stopTrackB = vi.fn();
  let streamCount = 0;
  class StubMediaRecorder {
    static isTypeSupported() {
      return true;
    }
    state: "inactive" | "recording" = "inactive";
    ondataavailable: ((ev: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob(["x".repeat(256)], { type: "audio/webm" }) });
      this.onstop?.();
    }
  }
  const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ text: "cần sạc cho resident B" }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));

  vi.stubGlobal("FileReader", StubFileReader);
  vi.stubGlobal("MediaRecorder", StubMediaRecorder);
  vi.stubGlobal("fetch", fetchSpy);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn(async () => {
        streamCount += 1;
        return { getTracks: () => [{ stop: streamCount === 1 ? stopTrackA : stopTrackB }] };
      }),
    },
  });

  setSession({ token: "token-resident-A", role: "resident", userId: "res-a", displayName: "Resident A" });
  render(
    <Providers>
      <ChatPanel role="resident" />
    </Providers>,
  );

  fireEvent.click(screen.getByRole("button", { name: "Nói bằng giọng tiếng Việt" }));
  const stopBtnA = await screen.findByRole("button", { name: "Dừng ghi âm" });
  fireEvent.click(stopBtnA);
  await waitFor(() => expect(readers).toHaveLength(1));
  expect(stopTrackA).toHaveBeenCalled();

  // Logout Resident A and login Resident B BEFORE Resident A's FileReader finishes.
  act(() => {
    clearSession();
    setSession({ token: "token-resident-B", role: "resident", userId: "res-b", displayName: "Resident B" });
  });

  // Resolve Resident A's stale FileReader: must NOT call fetch or write into Resident B's textbox.
  await act(async () => {
    readers[0].onloadend?.();
    await Promise.resolve();
  });
  expect(fetchSpy).not.toHaveBeenCalled();
  expect((screen.getByLabelText("Tin nhắn cho Trợ lý sạc") as HTMLInputElement).value).toBe("");

  // Resident B's own recording and transcription still works cleanly with Resident B's token.
  fireEvent.click(screen.getByRole("button", { name: "Nói bằng giọng tiếng Việt" }));
  const stopBtnB = await screen.findByRole("button", { name: "Dừng ghi âm" });
  fireEvent.click(stopBtnB);
  await waitFor(() => expect(readers).toHaveLength(2));
  await act(async () => {
    readers[1].onloadend?.();
  });
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
  const [, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit];
  expect((init.headers as Record<string, string>).Authorization).toBe("Bearer token-resident-B");
  expect(stopTrackB).toHaveBeenCalled();
  expect(await screen.findByDisplayValue("cần sạc cho resident B")).toBeTruthy();
});

it("stops active MediaStream tracks without transcribing on logout and closes delayed getUserMedia tracks", async () => {
  const stopActiveTrack = vi.fn();
  const stopLateTrack = vi.fn();
  let resolveLateMedia!: (stream: { getTracks: () => Array<{ stop: () => void }> }) => void;
  let mediaCall = 0;

  class StubMediaRecorder {
    static isTypeSupported() {
      return true;
    }
    state: "inactive" | "recording" = "inactive";
    ondataavailable: ((ev: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob(["y".repeat(256)], { type: "audio/webm" }) });
      this.onstop?.();
    }
  }
  const fetchSpy = vi.fn();
  vi.stubGlobal("MediaRecorder", StubMediaRecorder);
  vi.stubGlobal("fetch", fetchSpy);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn(() => {
        mediaCall += 1;
        if (mediaCall === 1) {
          return Promise.resolve({ getTracks: () => [{ stop: stopActiveTrack }] });
        }
        return new Promise((resolve) => {
          resolveLateMedia = resolve;
        });
      }),
    },
  });

  setSession({ token: "tok-1", role: "resident", userId: "res-1", displayName: "R1" });
  render(
    <Providers>
      <ChatPanel role="resident" />
    </Providers>,
  );

  // 1) Active recording interrupted by logout -> track stops, no transcribe request fired
  fireEvent.click(screen.getByRole("button", { name: "Nói bằng giọng tiếng Việt" }));
  await screen.findByRole("button", { name: "Dừng ghi âm" });
  act(() => {
    clearSession();
    setSession({ token: "tok-2", role: "resident", userId: "res-2", displayName: "R2" });
  });
  expect(stopActiveTrack).toHaveBeenCalled();
  expect(fetchSpy).not.toHaveBeenCalled();

  // 2) Pending getUserMedia resolving after session change -> late track stopped immediately
  fireEvent.click(screen.getByRole("button", { name: "Nói bằng giọng tiếng Việt" }));
  act(() => {
    clearSession();
  });
  await act(async () => {
    resolveLateMedia({ getTracks: () => [{ stop: stopLateTrack }] });
    await Promise.resolve();
  });
  expect(stopLateTrack).toHaveBeenCalledTimes(1);
  expect(fetchSpy).not.toHaveBeenCalled();
});

it("aborts in-flight transcribe on relogin and delayed 401 from old generation never clears new session", async () => {
  let resolveTranscribe!: (res: Response) => void;
  let capturedSignal: AbortSignal | undefined;

  class FastFileReader {
    result = `data:audio/webm;base64,${"Z".repeat(200)}`;
    onloadend: (() => void) | null = null;
    readAsDataURL() {
      queueMicrotask(() => this.onloadend?.());
    }
  }
  class StubMediaRecorder {
    static isTypeSupported() {
      return true;
    }
    state: "inactive" | "recording" = "inactive";
    ondataavailable: ((ev: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob(["z".repeat(256)], { type: "audio/webm" }) });
      this.onstop?.();
    }
  }
  const fetchSpy = vi.fn((_url: string, init?: RequestInit) => {
    capturedSignal = init?.signal ?? undefined;
    return new Promise<Response>((resolve) => {
      resolveTranscribe = resolve;
    });
  });

  vi.stubGlobal("FileReader", FastFileReader);
  vi.stubGlobal("MediaRecorder", StubMediaRecorder);
  vi.stubGlobal("fetch", fetchSpy);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })) },
  });

  const creds = { token: "same-user-tok", role: "resident" as const, userId: "res-1", displayName: "R1" };
  setSession(creds);
  const oldGen = getSession()?.generation;
  render(
    <Providers>
      <ChatPanel role="resident" />
    </Providers>,
  );

  fireEvent.click(screen.getByRole("button", { name: "Nói bằng giọng tiếng Việt" }));
  fireEvent.click(await screen.findByRole("button", { name: "Dừng ghi âm" }));
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

  // Same account logs out and logs back in (new generation) while transcribe is in flight.
  act(() => {
    clearSession();
    setSession({ ...creds, token: "same-user-fresh-tok" });
  });
  const newGen = getSession()?.generation;
  expect(newGen).not.toBe(oldGen);
  expect(capturedSignal?.aborted).toBe(true);

  await act(async () => {
    resolveTranscribe(new Response(JSON.stringify({ detail: "Expired" }), { status: 401 }));
    await Promise.resolve();
  });
  expect(getSession()?.generation).toBe(newGen);
  expect(getSession()?.token).toBe("same-user-fresh-tok");
});

it("isolates WebSocket useStream across session generations and ignores stale close codes", async () => {
  const sockets: Array<{
    url: string;
    closed: boolean;
    onopen: (() => void) | null;
    onclose: ((ev: { code: number; reason: string }) => void) | null;
  }> = [];
  class FakeWebSocket {
    closed = false;
    onopen: (() => void) | null = null;
    onmessage: ((ev: { data: unknown }) => void) | null = null;
    onclose: ((ev: { code: number; reason: string }) => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(public url: string) {
      sockets.push(this);
    }
    send() {}
    close() {
      this.closed = true;
    }
  }
  vi.stubGlobal("WebSocket", FakeWebSocket);

  function Probe() {
    const state = useStream("resident");
    return <div data-testid="ws-status">{state.status}</div>;
  }

  setSession({ token: "ws-tok-1", role: "resident", userId: "res-1", displayName: "R1" });
  render(
    <Providers>
      <Probe />
    </Providers>,
  );
  expect(sockets).toHaveLength(1);

  act(() => {
    clearSession();
    setSession({ token: "ws-tok-2", role: "resident", userId: "res-1", displayName: "R1" });
  });
  const freshGen = getSession()?.generation;
  expect(sockets[0].closed).toBe(true);
  expect(sockets).toHaveLength(2);

  // Late 4401 on already-stopped socket[0] must never clear the new session.
  act(() => {
    sockets[0].onclose?.({ code: 4401, reason: "stale token" });
  });
  expect(getSession()?.generation).toBe(freshGen);
});

it("renders ChatAdvisory HOW-TO loading, cancelled, failed, empty, and ranked partial states without any Apply button", () => {
  const when = "2026-11-26T12:00:00Z";
  const baseHowTo = {
    applied: false as const,
    goal: {
      goal: "min_tested_site_limit_for_sla" as const,
      min_grid_input_kw: 22,
      max_grid_input_kw: 106,
      min_original_on_time_rate: 1,
      protect_on_time_ac_bookings: true,
      hypothetical_infrastructure: false,
    },
    search_status: "partial" as const,
    snapshot_id: "snap-1",
    snapshot_sha256: "a".repeat(64),
    known_at: when,
    horizon_end: when,
    event_manifest_sha256: "b".repeat(64),
    experiment_fingerprint: "c".repeat(64),
    policy_id: "M3b",
    policy_version: "1",
    candidate_set: {
      version: "chargepilot.how_to_candidates/1" as const,
      search_variable: "grid_input_kw" as const,
      values: [22, 94],
    },
    baseline: null,
    candidates: [
      { value: 22, status: "completed" as const, feasibility: "unknown" as const, reason: "blocked_command" as const, hypothetical_infrastructure: false },
      { value: 94, status: "completed" as const, feasibility: "feasible" as const, hypothetical_infrastructure: false },
    ],
    options: [
      { value: 94, status: "completed" as const, feasibility: "feasible" as const, hypothetical_infrastructure: false },
    ],
    ranking: ["grid_input_kw_asc"],
    assumptions: ["Advisory simulation only"],
    baseline_execution_count: 1,
    branch_execution_count: 2,
    elapsed_ms: 12,
  };

  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  const { rerender, container } = render(
    <QueryClientProvider client={client}>
      <ChatAdvisory
        sessionId="s1"
        advisory={[
          { kind: "job", job: { job_id: "a".repeat(32), job_kind: "how_to", status: "running", applied: false } },
          { kind: "job", job: { job_id: "b".repeat(32), job_kind: "how_to", status: "cancelled", applied: false } },
          { kind: "job", job: { job_id: "c".repeat(32), job_kind: "how_to", status: "failed", error: "timeout", applied: false } },
        ]}
      />
    </QueryClientProvider>,
  );
  expect(screen.getByText("Đang mô phỏng · HOW-TO")).toBeTruthy();
  expect(screen.getByText("Đã hủy · HOW-TO")).toBeTruthy();
  expect(screen.getByText("Tác vụ thất bại · HOW-TO")).toBeTruthy();

  rerender(
    <QueryClientProvider client={client}>
      <ChatAdvisory
        sessionId="s1"
        advisory={[
          {
            kind: "job",
            job: {
              job_id: "d".repeat(32),
              job_kind: "how_to",
              status: "succeeded",
              applied: false,
              result: { kind: "how_to", summary: "Không có mức khả thi.", claims: [], result: { ...baseHowTo, search_status: "no_feasible_in_tested_set", options: [] } },
            },
          },
          {
            kind: "job",
            job: {
              job_id: "e".repeat(32),
              job_kind: "how_to",
              status: "succeeded",
              applied: false,
              result: { kind: "how_to", summary: "Mức 94 kW khả thi trong tìm kiếm một phần.", claims: [], result: baseHowTo },
            },
          },
        ]}
      />
    </QueryClientProvider>,
  );
  expect(container.querySelectorAll("ol > li > strong")[0]?.textContent).toBe("94 kW đầu vào lưới · Khả thi");
  expect(screen.queryByRole("button", { name: /áp dụng|apply/i })).toBeNull();
});
