import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import OperatorApprovalsPage from "@/app/operator/approvals/page";
import OperatorSchedulePage from "@/app/operator/schedule/page";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

afterEach(cleanup);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const mockApproval: components["schemas"]["Approval"] = {
  approval_id: "ap-1",
  kind: "operator_review",
  requested_from: "operator",
  created_at: "2026-11-23T18:00:00+07:00",
  impact_summary: "Tăng công suất cổng AC-01-1",
  status: "pending",
  command: {
    command_id: "cmd-1",
    type: "set_power",
    connector_id: "AC-01-1",
    power_kw: 11,
    source: "operator",
    issued_by: "operator",
    reason: "Thủ công",
    created_at: "2026-11-23T18:00:00+07:00",
    based_on_schedule_version: 1,
    based_on_state_at: "2026-11-23T18:00:00+07:00",
  },
  verdict: {
    command_id: "cmd-1",
    passed: true,
    checked_at: "2026-11-23T18:00:00+07:00",
    violations: [],
  },
};

const mockStationConfig = {
  station_id: "station-test",
  name: "Bãi sạc thông minh VinAI",
  power_limit_kw: 106,
  timezone: "Asia/Ho_Chi_Minh",
  connectors: [{ connector_id: "AC-01-1", max_power_kw: 11, zone: "AC", bay_id: "B-A1" }],
  step_minutes: 15,
} as unknown as components["schemas"]["StationConfig"];

const mockSchedulePlan: components["schemas"]["SchedulePlan"] = {
  version: 2,
  created_at: "2026-11-23T18:00:00+07:00",
  horizon_start: "2026-11-23T18:00:00+07:00",
  step_minutes: 15,
  strategy: "M3a",
  sessions: [],
};

const mockQueueBooking: components["schemas"]["Booking"] = {
  booking_id: "book-queue-1",
  resident_id: "res-1",
  connector_id: null,
  status: "queued",
  created_at: "2026-11-23T18:00:00+07:00",
  schedule_version: 1,
  max_charge_power_kw: 11,
  request: {
    vehicle_model: "VF8",
    soc_now: 30,
    soc_target: 80,
    deadline: "2026-11-23T22:00:00+07:00",
    mode: "reservation",
    zone: "AC",
  },
  energy: {
    battery_energy_kwh: 40,
    grid_energy_kwh: 42,
    efficiency: 0.95,
    soc_now: 30,
    soc_target: 80,
    vehicle_model: "VF8",
  },
};

describe("Operator Approvals & Schedule - 501 vs Success handling", () => {
  it("approvals: duyệt thành công → hiện thông báo thực thi, KHÔNG hiện NotImplementedPanel", async () => {
    vi.spyOn(api, "GET").mockImplementation(async (path: string) => {
      if (path === "/api/v1/operator/approvals") {
        return { data: [mockApproval], response: new Response() } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    vi.spyOn(api, "PATCH").mockImplementation(async (path: string) => {
      if (path === "/api/v1/operator/approvals/{approval_id}") {
        return {
          data: {
            ...mockApproval,
            status: "approved",
            executed: true,
          },
          response: new Response(),
        } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<OperatorApprovalsPage />, { wrapper });

    const btnDuyet = await screen.findByRole("button", { name: "Duyệt" });
    fireEvent.click(btnDuyet);

    await waitFor(() => {
      expect(screen.getByText(/Đã duyệt và thực thi thành công tới trạm/)).toBeTruthy();
    });

    expect(screen.queryByText(/Chưa cài đặt|Tính năng chưa hoàn thiện/i)).toBeNull();
  });

  it("approvals: backend trả 501 → hiển thị NotImplementedPanel", async () => {
    vi.spyOn(api, "GET").mockImplementation(async (path: string) => {
      if (path === "/api/v1/operator/approvals") {
        return { data: [mockApproval], response: new Response() } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    vi.spyOn(api, "PATCH").mockImplementation(async (path: string) => {
      if (path === "/api/v1/operator/approvals/{approval_id}") {
        return {
          error: {
            detail: "PATCH /operator/approvals/{id} chưa được cài đặt",
            code: "not_implemented",
            task_id: "T2.7",
          },
          response: new Response(null, { status: 501 }),
        } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<OperatorApprovalsPage />, { wrapper });

    const btnDuyet = await screen.findByRole("button", { name: "Duyệt" });
    fireEvent.click(btnDuyet);

    await waitFor(() => {
      expect(screen.getByText(/PATCH \/api\/v1\/operator\/approvals\/\{approval_id\}/)).toBeTruthy();
      expect(screen.getByText(/T2\.7/)).toBeTruthy();
    });
  });

  it("schedule: replan thành công → hiện lịch mới, khi trả 501 → hiện NotImplementedPanel", async () => {
    vi.spyOn(api, "GET").mockImplementation(async (path: string) => {
      if (path === "/api/v1/station/config") {
        return { data: mockStationConfig, response: new Response() } as never;
      }
      if (path === "/api/v1/operator/schedule") {
        return { data: mockSchedulePlan, response: new Response() } as never;
      }
      if (path === "/api/v1/operator/bookings") {
        return { data: [mockQueueBooking], response: new Response() } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    // 1. Replan thành công
    vi.spyOn(api, "POST").mockImplementation(async (path: string) => {
      if (path === "/api/v1/operator/schedule/replans") {
        return {
          data: { ...mockSchedulePlan, version: 3, solve_time_s: 0.15 },
          response: new Response(),
        } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<OperatorSchedulePage />, { wrapper });

    const btnReplan = await screen.findByRole("button", { name: /Lập lịch lại/ });
    fireEvent.click(btnReplan);

    await waitFor(() => {
      expect(screen.getByText(/Đã tính lại: lịch v3/)).toBeTruthy();
    });
    expect(screen.queryByText(/POST \/api\/v1\/operator\/schedule\/replans/)).toBeNull();

    // 2. Replan bị 501
    vi.spyOn(api, "POST").mockImplementation(async (path: string) => {
      if (path === "/api/v1/operator/schedule/replans") {
        return {
          error: {
            detail: "Chưa hỗ trợ replan",
            code: "not_implemented",
            task_id: "T2.6",
          },
          response: new Response(null, { status: 501 }),
        } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    fireEvent.click(btnReplan);

    await waitFor(() => {
      expect(screen.getByText(/POST \/api\/v1\/operator\/schedule\/replans/)).toBeTruthy();
      expect(screen.getByText(/T2\.6/)).toBeTruthy();
    });
  });

  it("approvals: tab 'Bị Guard chặn' và 'Nhật ký' dùng seq cho 'Tải thêm'", async () => {
    const mockBlockedEntry1: components["schemas"]["DecisionLogEntry"] = {
      entry_id: "entry-b1",
      seq: 10,
      timestamp: "2026-11-23T18:10:00+07:00",
      executed: false,
      note: "",
      command: {
        command_id: "cmd-b1",
        type: "set_power",
        connector_id: "AC-01-1",
        power_kw: 22,
        source: "optimizer",
        issued_by: "optimizer",
        reason: "Chống dao động",
        created_at: "2026-11-23T18:10:00+07:00",
        based_on_schedule_version: 1,
        based_on_state_at: "2026-11-23T18:10:00+07:00",
      },
      verdict: {
        command_id: "cmd-b1",
        passed: false,
        checked_at: "2026-11-23T18:10:00+07:00",
        violations: [
          {
            rule: "connector_power_limit",
            detail: "Vượt công suất tối đa đầu nối",
          },
        ],
      },
    };

    const mockBlockedEntry2: components["schemas"]["DecisionLogEntry"] = {
      ...mockBlockedEntry1,
      entry_id: "entry-b2",
      seq: 9,
      command: {
        ...mockBlockedEntry1.command,
        command_id: "cmd-b2",
        connector_id: "DC-01-1",
      },
    };

    const getSpy = vi.spyOn(api, "GET").mockImplementation(async (path: string, init?: { params?: { query?: { before?: number } } }) => {
      if (path === "/api/v1/operator/commands/blocked") {
        if (init?.params?.query?.before === 10) {
          return { data: { items: [mockBlockedEntry2], next_cursor: null, has_more: false }, response: new Response() } as never;
        }
        return { data: { items: [mockBlockedEntry1], next_cursor: 10, has_more: true }, response: new Response() } as never;
      }
      if (path === "/api/v1/operator/approvals") {
        return { data: [], response: new Response() } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<OperatorApprovalsPage />, { wrapper });

    // Chuyển sang tab Bị Guard chặn
    const tabBlocked = screen.getByRole("tab", { name: "Bị Guard chặn" });
    fireEvent.click(tabBlocked);

    await waitFor(() => {
      expect(screen.getAllByText(/set_power AC-01-1/).length).toBeGreaterThan(0);
    });

    // Click Tải thêm
    const btnLoadMore = screen.getByRole("button", { name: "Tải thêm" });
    fireEvent.click(btnLoadMore);

    await waitFor(() => {
      expect(screen.getAllByText(/set_power DC-01-1/).length).toBeGreaterThan(0);
    });

    // Xác nhận đã gọi api với before = 10
    expect(getSpy).toHaveBeenCalledWith("/api/v1/operator/commands/blocked", {
      params: { query: { before: 10 } },
    });
  });
});
