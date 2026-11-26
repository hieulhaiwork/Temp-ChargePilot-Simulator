import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ResidentPlanPage from "@/app/resident/plan/page";
import { Notice } from "@/components/ui/blocks";
import { api } from "@/lib/api/client";
import { saveDraft, type Draft } from "@/lib/booking/draft";

let searchQuery = "view=draft";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(searchQuery),
}));

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  searchQuery = "view=draft";
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const draftWithAssumptions: Draft = {
  createdAt: "2026-11-25T08:00:00+07:00",
  request: {
    vehicle_model: "VF8_NEW_2026",
    soc_now: 30,
    soc_target: 80,
    deadline: "2026-11-25T19:00:00+07:00",
    mode: "reservation",
    zone: "AC",
  },
  proposal: {
    feasible: true,
    connector_id: "AC-01-1",
    planned_start: "2026-11-25T10:00:00+07:00",
    planned_end: "2026-11-25T16:00:00+07:00",
    slack_minutes: 60,
    energy: {
      vehicle_model: "VF8_NEW_2026",
      soc_now: 30,
      soc_target: 80,
      battery_energy_kwh: 30,
      grid_energy_kwh: 31.5,
      efficiency: 0.95,
    },
    estimated_cost_vnd: 90000,
    reasons: ["Sạc trong giờ thấp điểm"],
    assumptions: ["Không có xe ưu tiên mới đến", "Nguồn cấp giữ ở 106 kW"],
    certainty: "estimate",
    approvals_pending_for_booking: 0,
    approvals_pending_for_others: 0,
  },
};

function collectNestingErrors(calls: unknown[][]) {
  return calls
    .flat()
    .map(String)
    .filter((msg) => msg.includes("cannot be a descendant of") || msg.includes("validateDOMNesting"));
}

describe("ResidentPlanPage DraftView (S3)", () => {
  it("không lồng <ul> hoặc block element bên trong <p> khi hiển thị assumptions", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    saveDraft(draftWithAssumptions);

    const { container } = render(<ResidentPlanPage />, { wrapper });

    const list = await screen.findByTestId("proposal-assumptions");
    expect(list.tagName).toBe("UL");

    expect(collectNestingErrors(errorSpy.mock.calls)).toEqual([]);
    expect(container.querySelectorAll("p ul, p ol, p p, p div")).toHaveLength(0);
  });

  it("Notice hỗ trợ children là block element (<p>, <div>) mà không lồng trong <p>", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { container } = render(
      <Notice title="Có đề nghị" tone="gold" icon="alert">
        <p>Tóm tắt tác động</p>
        <div>Hành động</div>
      </Notice>,
    );

    expect(collectNestingErrors(errorSpy.mock.calls)).toEqual([]);
    expect(container.querySelectorAll("p p, p div")).toHaveLength(0);
  });

  it("không lỗi trùng React key khi /resident/explanation trả các dòng giải thích giống nhau", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    searchQuery = "";

    const mockBooking = {
      booking_id: "bk-1",
      resident_id: "u-1",
      status: "confirmed",
      connector_id: "AC-01-1",
      planned_start: draftWithAssumptions.proposal.planned_start,
      planned_end: draftWithAssumptions.proposal.planned_end,
      request: draftWithAssumptions.request,
      energy: draftWithAssumptions.proposal.energy,
      estimated_cost_vnd: draftWithAssumptions.proposal.estimated_cost_vnd,
      created_at: "2026-11-25T08:00:00+07:00",
    };

    const repeatedReason = "16:45: optimizer áp set_power 11 kW trên AC-01-1";
    vi.spyOn(api, "GET").mockImplementation(async (path: string) => {
      if (path === "/api/v1/resident/bookings/current") {
        return { data: mockBooking, response: new Response() } as never;
      }
      if (path === "/api/v1/resident/explanation") {
        return { data: [repeatedReason, repeatedReason], response: new Response() } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<ResidentPlanPage />, { wrapper });

    expect(await screen.findAllByText(repeatedReason)).toHaveLength(2);
    const keyErrors = errorSpy.mock.calls.flat().map(String).filter((m) => m.includes("same key"));
    expect(keyErrors).toEqual([]);
  });

  it("hiển thị tiêu đề Phiên sạc theo tên xe, đưa Mã đặt lịch xuống bảng thông số và hỏi xác nhận huỷ gọn", async () => {
    searchQuery = "";
    const mockBooking = {
      booking_id: "CP-4F9A2K",
      resident_id: "u-1",
      status: "confirmed",
      connector_id: "AC-01-1",
      planned_start: draftWithAssumptions.proposal.planned_start,
      planned_end: draftWithAssumptions.proposal.planned_end,
      request: draftWithAssumptions.request,
      energy: draftWithAssumptions.proposal.energy,
      estimated_cost_vnd: draftWithAssumptions.proposal.estimated_cost_vnd,
      created_at: "2026-11-25T08:00:00+07:00",
    };

    const getSpy = vi.spyOn(api, "GET").mockImplementation(async (path: string) => {
      if (path === "/api/v1/resident/bookings/current") {
        return { data: mockBooking, response: new Response() } as never;
      }
      if (path === "/api/v1/resident/explanation") {
        return { data: ["Mã đặt lịch CP-4F9A2K: cần 31.5 kWh."], response: new Response() } as never;
      }
      if (path === "/api/v1/vehicles") {
        return {
          data: [{ vehicle_model: "VF8_NEW_2026", display_name: "VinFast VF 8", usable_capacity_kwh: 87.7, max_ac_power_kw: 11, max_dc_kw: 150 }],
          response: new Response(),
        } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<ResidentPlanPage />, { wrapper });

    expect(await screen.findByRole("heading", { name: "Phiên sạc · VinFast VF 8" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /Lịch CP-4F9A2K/ })).toBeNull();
    expect(screen.getByText("Mã đặt lịch")).toBeTruthy();
    expect(screen.getByText("CP-4F9A2K")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Huỷ lịch" }));
    expect(screen.getByText("Huỷ lịch sạc này?")).toBeTruthy();

    getSpy.mockRestore();
  });
});
