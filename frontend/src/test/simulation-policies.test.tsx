/**
 * Final Acceptance §4.1 — màn S8 lấy policy từ GET /simulation/policies và gửi `policy_id`:
 * thêm policy mới ở registry backend không cần sửa dropdown.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PolicyInfo } from "@/lib/policies";
import { policyLabel, policyOf, policyOptions, selectedPolicy } from "@/lib/policies";

const calls = vi.hoisted(() => ({ posts: [] as { path: string; body: unknown }[] }));

const POLICIES: PolicyInfo[] = [
  { policy_id: "B0", version: "1", dispatch_dc: "fcfs", optimizer_ac: "equal_share", optimizer_dc: "equal_share", coordinator: "fixed_share", description: "FCFS + Equal Share AC/DC + Fixed Share", frozen: true, legacy_strategy: "B0" },
  { policy_id: "M3a", version: "1", dispatch_dc: "llf", optimizer_ac: "ac_rolling_lp", optimizer_dc: "rolling_lp", coordinator: "fixed_share", description: "LLF + AC/DC LP + Fixed Share", frozen: true, legacy_strategy: "M3a" },
  { policy_id: "T41-edf", version: "test-2", dispatch_dc: "edf", optimizer_ac: "equal_share", optimizer_dc: "deadline_first", coordinator: "fixed_share", description: "policy mới", frozen: false, legacy_strategy: null },
];

vi.mock("@/lib/api/client", () => {
  const ok = (data: unknown) => Promise.resolve({ data, response: new Response(null, { status: 200 }) });
  const data: Record<string, unknown> = {
    "/api/v1/simulation/policies": POLICIES,
    "/api/v1/simulation/scenarios": [{ scenario_id: "hybrid_evening", name: "Tối hybrid", description: "" }],
    "/api/v1/simulation/benchmark": { generated_at: "2026-11-24T00:00:00Z", runs: [], notes: [] },
  };
  return {
    api: {
      GET: (path: string) => ok(data[path]),
      POST: (path: string, init: { body: unknown }) => {
        calls.posts.push({ path, body: init.body });
        return ok({
          run_id: "r1",
          scenario_id: "hybrid_evening",
          strategy: null,
          policy_id: "T41-edf",
          policy_version: "test-2",
          kpis: { on_time_rate: 1, wait_mean_minutes: 0, wait_p90_minutes: 0, unmet_energy_kwh: 0, delivered_energy_kwh: 1, service_rate: 1, energy_cost_vnd: 1, peak_load_kw: 1, power_limit_violations: 0, replan_p95_seconds: null, blocked_commands: 0 },
          started_at: "2026-11-24T00:00:00Z",
          finished_at: "2026-11-24T00:00:00Z",
          notes: "seed 42",
        });
      },
    },
    unwrap: async (call: Promise<{ data: unknown }>) => (await call).data,
  };
});

afterEach(() => {
  cleanup();
  calls.posts.length = 0;
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("policy từ registry (lib/policies)", () => {
  it("nhãn, lựa chọn mặc định và policy_id ?? strategy", () => {
    expect(policyOptions(POLICIES).map((o) => o.id)).toEqual(["B0", "M3a", "T41-edf"]);
    expect(policyLabel(POLICIES[1])).toContain("(mặc định)");
    expect(policyLabel(POLICIES[2])).toContain("vtest-2");
    expect(policyLabel(POLICIES[2])).toContain("thử nghiệm");
    expect(selectedPolicy(POLICIES, "")).toBe("M3a");
    expect(selectedPolicy(POLICIES, "T41-edf")).toBe("T41-edf");
    expect(selectedPolicy(POLICIES, "khong-co")).toBe("M3a");
    expect(selectedPolicy([POLICIES[2]], "")).toBe("T41-edf");
    expect(selectedPolicy(undefined, "M3a")).toBe("");
    expect(policyOf({ policy_id: "T41-edf", strategy: null })).toBe("T41-edf");
    expect(policyOf({ strategy: "M3b" })).toBe("M3b");
  });
});

describe("S8 · dropdown chiến lược", () => {
  it("hiện mọi policy của registry (kể cả policy mới) và gửi policy_id", async () => {
    const { default: Page } = await import("@/app/operator/simulation/page");
    render(<Page />, { wrapper });
    const select = (await screen.findByLabelText("Chiến lược")) as HTMLSelectElement;
    await waitFor(() => expect(select.options.length).toBe(3));
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["B0", "M3a", "T41-edf"]);
    expect(select.value).toBe("M3a");
    fireEvent.change(select, { target: { value: "T41-edf" } });
    expect(select.value).toBe("T41-edf");
    const runButton = screen.getByRole("button", { name: "Chạy" });
    await waitFor(() => expect((runButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(runButton);
    await waitFor(() => expect(calls.posts.length).toBe(1));
    expect(calls.posts[0].path).toBe("/api/v1/simulation/runs");
    expect(calls.posts[0].body).toMatchObject({ scenario_id: "hybrid_evening", policy_id: "T41-edf" });
    expect(calls.posts[0].body).not.toHaveProperty("strategy");
  });
});
