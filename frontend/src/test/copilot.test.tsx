import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { CopilotPanel } from "@/components/copilot/CopilotPanel";

const calls = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), cancel: vi.fn(),
  session: { userId: "resident-1", role: "resident", token: "tok-1", generation: 1 } as {
    userId: string;
    role: string;
    token?: string;
    generation: number;
  } | null,
}));

vi.mock("@/lib/api/client", () => ({
  api: { GET: calls.get, POST: calls.post, DELETE: calls.cancel },
  unwrap: (call: Promise<unknown>) => call,
}));
vi.mock("@/lib/auth/session", () => ({ useSession: () => calls.session }));

const when = "2026-11-23T12:01:00+07:00";
const context = {
  as_of: when, timezone: "Asia/Ho_Chi_Minh", booking_ids: ["B1"],
  connectors: [{ connector_id: "DC-01-1", zone: "DC" }],
  default_horizon_minutes: 120, max_horizon_minutes: 1440,
};
const job = (status: string, result?: unknown) => ({
  kind: "job", job: { job_id: "id1", job_kind: "what_if", status, applied: false, result },
});

function show(role: "resident" | "operator") {
  calls.session = { userId: calls.session?.userId ?? "resident-1", role, token: calls.session?.token ?? "tok-1", generation: calls.session?.generation ?? 1 };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return {
    client,
    ...render(<CopilotPanel role={role} />, {
      wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
    }),
  };
}

function ask(text: string) {
  fireEvent.change(screen.getByLabelText("Câu hỏi"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
}

beforeEach(() => {
  calls.session = { userId: "resident-1", role: "resident", token: "tok-1", generation: 1 };
  calls.get.mockReset().mockImplementation(async (path) => path.endsWith("context") ? context : job("running"));
  calls.post.mockReset();
  calls.cancel.mockReset();
});
afterEach(cleanup);

it("clears prior reply and keeps context cache isolated across resident sessions", async () => {
  calls.get.mockImplementation(async () => ({
    ...context, booking_ids: [calls.session?.userId === "resident-1" ? "B1" : "B2"],
  }));
  calls.post.mockResolvedValueOnce({ kind: "notice", code: "unsupported", message: "Phản hồi phiên trước" });
  const screenRoot = show("resident");
  expect(await screen.findByRole("option", { name: "B1" })).toBeTruthy();
  ask("Một câu hỏi");
  expect(await screen.findByText("Phản hồi phiên trước")).toBeTruthy();
  calls.session = { userId: "resident-2", role: "resident", token: "tok-2", generation: 2 };
  screenRoot.rerender(<CopilotPanel role="resident" />);
  expect(screen.queryByRole("option", { name: "B1" })).toBeNull();
  expect(screen.queryByText("Phản hồi phiên trước")).toBeNull();
  expect(await screen.findByRole("option", { name: "B2" })).toBeTruthy();
});

it("drops delayed in-flight query and cancel responses across logout and re-login", async () => {
  let resolveSlowPost!: (value: unknown) => void;
  let resolveSlowCancel!: (value: unknown) => void;
  calls.get.mockImplementation(async () => ({
    ...context,
    booking_ids: [calls.session?.userId === "resident-2" ? "B2-FRESH" : "B1-STALE"],
  }));
  calls.post
    .mockImplementationOnce(
      () => new Promise((resolve) => {
        resolveSlowPost = resolve;
      }),
    )
    .mockResolvedValueOnce(job("queued"));
  calls.cancel.mockImplementationOnce(
    () => new Promise((resolve) => {
      resolveSlowCancel = resolve;
    }),
  );

  const screenRoot = show("resident");
  expect(await screen.findByRole("option", { name: "B1-STALE" })).toBeTruthy();

  // Trigger an in-flight query for resident-1, then logout and log back in as resident-2 BEFORE it resolves.
  ask("Câu hỏi trễ của resident-1");
  await waitFor(() => expect(calls.post).toHaveBeenCalledTimes(1));
  calls.session = null;
  screenRoot.rerender(<CopilotPanel role="resident" />);
  expect(screenRoot.client.getQueriesData({ queryKey: ["copilot"] })).toHaveLength(0);

  calls.session = { userId: "resident-2", role: "resident", token: "tok-2", generation: 2 };
  screenRoot.rerender(<CopilotPanel role="resident" />);
  expect(await screen.findByRole("option", { name: "B2-FRESH" })).toBeTruthy();

  resolveSlowPost({ kind: "notice", code: "unsupported", message: "Rò rỉ từ phiên đã đăng xuất" });
  await Promise.resolve();
  expect(screen.queryByText("Rò rỉ từ phiên đã đăng xuất")).toBeNull();
  expect(screen.queryByRole("option", { name: "B1-STALE" })).toBeNull();

  // Trigger a job + in-flight cancel for resident-2, then logout and re-login as resident-1 with a new token.
  ask("Nếu sạc đến 75% thì sao?");
  expect(await screen.findByRole("button", { name: "Hủy mô phỏng" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Hủy mô phỏng" }));
  await waitFor(() => expect(calls.cancel).toHaveBeenCalledTimes(1));

  calls.session = { userId: "resident-1", role: "resident", token: "tok-1-new", generation: 3 };
  screenRoot.rerender(<CopilotPanel role="resident" />);
  resolveSlowCancel(job("cancelled"));
  await Promise.resolve();
  expect(screen.queryByText("Đã hủy")).toBeNull();
});

it("opens the structured form after fallback and submits the station timestamp", async () => {
  calls.post.mockResolvedValueOnce({ kind: "notice", code: "structured_fallback", message: "Chọn biểu mẫu" });
  calls.post.mockResolvedValueOnce({
    kind: "why", summary: "Có bằng chứng",
    claims: [{ claim_id: "f1", name: "queue", value: 2, stage: "planned", observed_at: when, evidence_refs: ["trace#queue"] }],
    result: { missing_evidence: [] },
  });
  show("resident");
  ask("Yêu cầu không rõ");
  expect(await screen.findByText("Chọn biểu mẫu")).toBeTruthy();
  fireEvent.click(await screen.findByRole("button", { name: "Xem bằng chứng" }));
  await waitFor(() => expect(calls.post).toHaveBeenLastCalledWith("/api/v1/copilot/why", {
    body: { at: when, topic: "queue", limit: 20, subject_scope: "own_booking", booking_id: null },
  }));
  expect(await screen.findByText("trace#queue")).toBeTruthy();
  expect(screen.getByText(/Kế hoạch/)).toBeTruthy();
  expect(screen.queryByLabelText("Đầu nối")).toBeNull();
});

it("polls and renders the non-comparable sample and original/revised commitments", async () => {
  const original = { target_soc: 90, deadline: when, met_deadline: null };
  calls.post.mockResolvedValueOnce(job("queued"));
  calls.get.mockImplementation(async (path) => path.endsWith("context") ? context : job("succeeded", {
    kind: "what_if", summary: "Đã mô phỏng hai nhánh.",
    claims: [
      { claim_id: "baseline:plug_wait_mean_minutes", value: 30, unit: "min" },
      { claim_id: "patched:plug_wait_mean_minutes", value: 15, unit: "min" },
      { claim_id: "delta:plug_wait_mean_minutes", value: null, reason_code: "non_comparable_sample" },
    ],
    result: {
      status: "completed", snapshot_time: when, horizon_end: when, horizon_minutes: 15,
      baseline: {}, patched: {}, assumptions: [],
      affected_vehicles: [{
        booking_id: "B1", baseline_original: original, patched_original: original,
        patched_revised: { ...original, target_soc: 75, met_deadline: true },
      }],
    },
  }));
  show("resident");
  ask("Nếu sạc đến 75% thì sao?");
  expect(await screen.findByText("Khác tập booking")).toBeTruthy();
  expect(screen.getByText("75% · Đúng hạn")).toBeTruthy();
  expect(screen.getAllByText("90% · Chưa xác định SLA")).toHaveLength(2);
  expect(calls.get).toHaveBeenCalledWith("/api/v1/copilot/jobs/{job_id}", expect.anything());
  expect(screen.queryByRole("button", { name: /áp dụng/i })).toBeNull();
});

it("rules clarify connector selection, cancel a job and show HOW-TO unavailable", async () => {
  calls.post.mockResolvedValueOnce(job("queued"));
  calls.cancel.mockResolvedValueOnce(job("cancelled"));
  calls.post.mockResolvedValueOnce({ kind: "notice", code: "feature_not_available", message: "HOW-TO hiện chưa khả dụng." });
  show("operator");
  const connector = await screen.findByLabelText("Đầu nối");
  await screen.findByRole("option", { name: "DC-01-1" });
  fireEvent.change(connector, { target: { value: "DC-01-1" } });
  ask("Nếu một cổng DC bị lỗi trong 30 phút thì sao?");
  expect(await screen.findByRole("button", { name: "Hủy mô phỏng" })).toBeTruthy();
  expect(calls.post.mock.calls[0][1].body.selected_connector_id).toBe("DC-01-1");
  fireEvent.click(screen.getByRole("button", { name: "Hủy mô phỏng" }));
  expect(await screen.findByText("Đã hủy")).toBeTruthy();
  ask("Cần tăng công suất nguồn lên bao nhiêu?");
  expect(await screen.findByText("HOW-TO hiện chưa khả dụng.")).toBeTruthy();
});

it("never puts the credential in query cache keys and rekeys same-account login", async () => {
  calls.session = { userId: "resident-1", role: "resident", token: "test-private-jwt-credential", generation: 41 };
  const root = show("resident");
  await screen.findByRole("option", { name: "B1" });
  const cache = root.client.getQueryCache();
  const hashes = () => cache.findAll({ queryKey: ["copilot"] }).map((query) => query.queryHash);
  const contextHash = () => cache.find({ queryKey: ["copilot", "context"], exact: false })?.queryHash;
  expect(hashes().length).toBeGreaterThan(0);
  expect(hashes().join()).not.toContain("test-private-jwt-credential");
  const initial = contextHash();
  expect(initial).toBeDefined();
  calls.session = { ...calls.session!, generation: 42 };
  root.rerender(<CopilotPanel role="resident" />);
  await waitFor(() => {
    expect(contextHash()).toBeDefined();
    expect(contextHash()).not.toBe(initial);
  });
  expect(hashes().join()).not.toContain("test-private-jwt-credential");
});
