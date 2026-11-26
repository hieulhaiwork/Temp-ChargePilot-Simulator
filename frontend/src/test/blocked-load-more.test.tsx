import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import OperatorApprovalsPage from "@/app/operator/approvals/page";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

afterEach(cleanup);

type Entry = components["schemas"]["DecisionLogEntry"];

function makeEntry(seq: number, connector: string): Entry {
  return {
    entry_id: `entry-${seq}`,
    seq,
    timestamp: "2026-11-23T18:10:00+07:00",
    executed: false,
    note: "",
    command: {
      command_id: `cmd-${seq}`,
      type: "set_power",
      connector_id: connector,
      power_kw: 22,
      source: "optimizer",
      issued_by: "optimizer",
      reason: "Chống dao động",
      created_at: "2026-11-23T18:10:00+07:00",
      based_on_schedule_version: 1,
      based_on_state_at: "2026-11-23T18:10:00+07:00",
    },
    verdict: {
      command_id: `cmd-${seq}`,
      passed: false,
      checked_at: "2026-11-23T18:10:00+07:00",
      violations: [{ rule: "connector_power_limit", detail: "Vượt công suất tối đa đầu nối" }],
    },
  } as Entry;
}

function ok(data: unknown) {
  return { data, response: new Response() } as never;
}

describe("approvals: 'Tải thêm' sau khi trang đầu được làm mới", () => {
  it("dùng cursor của trang mới, không dùng cursor cũ, để không bỏ sót lệnh", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    function wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }

    let refreshed = false;
    const getSpy = vi
      .spyOn(api, "GET")
      .mockImplementation(async (path: string, init?: { params?: { query?: { before?: number } } }) => {
        if (path === "/api/v1/operator/commands/blocked") {
          const before = init?.params?.query?.before;
          if (before === 10) {
            // Trang kế tiếp của trang cũ: seq 9, còn tiếp với cursor 8.
            return ok({ items: [makeEntry(9, "DC-01-1")], next_cursor: 8, has_more: true });
          }
          if (before === 12) {
            return ok({ items: [makeEntry(11, "AC-02-1")], next_cursor: 10, has_more: true });
          }
          if (refreshed) {
            // Có quyết định mới: trang đầu trượt lên, seq 12 và 13 là mới nhất.
            return ok({ items: [makeEntry(13, "AC-01-1"), makeEntry(12, "AC-01-1")], next_cursor: 12, has_more: true });
          }
          return ok({ items: [makeEntry(10, "AC-01-1")], next_cursor: 10, has_more: true });
        }
        if (path === "/api/v1/operator/approvals") return ok([]);
        return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
      });

    render(<OperatorApprovalsPage />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "Bị Guard chặn" }));
    await waitFor(() => expect(screen.getAllByText(/set_power AC-01-1/).length).toBeGreaterThan(0));

    // Tải thêm một lần: trang cũ lấy seq 9, cursor kế tiếp là 8.
    fireEvent.click(screen.getByRole("button", { name: "Tải thêm" }));
    await waitFor(() => expect(screen.getAllByText(/set_power DC-01-1/).length).toBeGreaterThan(0));

    // Trang đầu được làm mới (polling) sau khi có lệnh mới.
    refreshed = true;
    await queryClient.invalidateQueries({ queryKey: ["operator", "blocked"] });
    await waitFor(() => expect(screen.getAllByText(/set_power AC-01-1/).length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("button", { name: "Tải thêm" }));
    await waitFor(() => expect(screen.getAllByText(/set_power AC-02-1/).length).toBeGreaterThan(0));

    // Cursor phải lấy từ trang mới (12), không phải cursor cũ (8) — nếu không, lệnh seq 11 bị bỏ qua.
    expect(getSpy).toHaveBeenCalledWith("/api/v1/operator/commands/blocked", { params: { query: { before: 12 } } });
    expect(getSpy).not.toHaveBeenCalledWith("/api/v1/operator/commands/blocked", { params: { query: { before: 8 } } });
  });
});
