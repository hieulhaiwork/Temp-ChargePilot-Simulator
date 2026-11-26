import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChangeBookingDialog } from "@/components/resident/ChangeBookingDialog";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

afterEach(cleanup);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const mockBooking: components["schemas"]["Booking"] = {
  booking_id: "book-123",
  resident_id: "res-test",
  connector_id: "AC-01-1",
  status: "confirmed",
  schedule_version: 1,
  created_at: "2026-11-23T18:00:00+07:00",
  planned_start: "2026-11-23T23:00:00+07:00",
  planned_end: "2026-11-24T05:00:00+07:00",
  estimated_cost_vnd: 120000,
  max_charge_power_kw: 11,
  request: {
    vehicle_model: "VF8_NEW_2026",
    soc_now: 30,
    soc_target: 80,
    deadline: "2026-11-24T07:00:00+07:00",
    mode: "reservation",
    zone: "AC",
  },
  energy: {
    battery_energy_kwh: 40,
    grid_energy_kwh: 42,
    efficiency: 0.95,
    soc_now: 30,
    soc_target: 80,
    vehicle_model: "VF8_NEW_2026",
  },
  consent: {
    allow_power_reduction: true,
    emergency_curtailment: true,
    max_start_delay_minutes: 60,
  },
};

const mockProposal: components["schemas"]["ScheduleProposal"] = {
  feasible: true,
  connector_id: "AC-01-1",
  planned_start: "2026-11-23T23:30:00+07:00",
  planned_end: "2026-11-24T06:00:00+07:00",
  slack_minutes: 60,
  energy: {
    battery_energy_kwh: 48,
    grid_energy_kwh: 50.5,
    efficiency: 0.95,
    soc_now: 30,
    soc_target: 90,
    vehicle_model: "VF8_NEW_2026",
  },
  estimated_cost_vnd: 145000,
  reasons: ["Sạc trong giờ thấp điểm"],
  certainty: "estimate",
  approvals_pending_for_booking: 0,
  approvals_pending_for_others: 0,
};

describe("ChangeBookingDialog (S3 G2)", () => {
  it("mở dialog, đổi soc_target → gọi POST quote và hiện phương án xem trước", async () => {
    const postSpy = vi.spyOn(api, "POST").mockImplementation(async (path: string) => {
      if (path === "/api/v1/resident/bookings/{booking_id}/quotes") {
        return { data: mockProposal, response: new Response() } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<ChangeBookingDialog booking={mockBooking} onClose={vi.fn()} onUpdated={vi.fn()} />, { wrapper });

    expect(screen.getByRole("heading", { name: /Đổi yêu cầu sạc/ })).toBeTruthy();
    expect(screen.getByText(/Mã đặt lịch:/)).toBeTruthy();
    expect(screen.getByText("book-123")).toBeTruthy();

    const targetInput = screen.getByLabelText(/Mức pin mục tiêu/);
    fireEvent.change(targetInput, { target: { value: "90" } });

    const quoteBtn = screen.getByRole("button", { name: /Xem trước phương án/ });
    fireEvent.click(quoteBtn);

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        "/api/v1/resident/bookings/{booking_id}/quotes",
        expect.objectContaining({
          params: { path: { booking_id: "book-123" } },
          body: expect.objectContaining({ soc_target: 90 }),
        }),
      );
    });

    expect(await screen.findByText(/Phương án mới dự kiến/)).toBeTruthy();
    expect(screen.getByText(/Kịp giờ lấy xe/)).toBeTruthy();

    postSpy.mockRestore();
  });

  it("bấm Áp dụng gọi PATCH; khi trả 409 proposal_expired dialog vẫn mở và hiện detail", async () => {
    const postSpy = vi.spyOn(api, "POST").mockResolvedValue({ data: mockProposal, response: new Response() } as never);
    const patchSpy = vi.spyOn(api, "PATCH").mockResolvedValue({
      error: { detail: "Trạm vừa thay đổi, phương án không còn khả thi", code: "proposal_expired" },
      response: new Response(null, { status: 409 }),
    } as never);

    render(<ChangeBookingDialog booking={mockBooking} onClose={vi.fn()} onUpdated={vi.fn()} />, { wrapper });

    const targetInput = screen.getByLabelText(/Mức pin mục tiêu/);
    fireEvent.change(targetInput, { target: { value: "90" } });
    fireEvent.click(screen.getByRole("button", { name: /Xem trước phương án/ }));

    const applyBtn = await screen.findByRole("button", { name: /Áp dụng thay đổi/ });
    fireEvent.click(applyBtn);

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith(
        "/api/v1/resident/bookings/{booking_id}",
        expect.objectContaining({
          params: { path: { booking_id: "book-123" } },
          body: expect.objectContaining({ soc_target: 90 }),
        }),
      );
    });

    expect(await screen.findByText(/Trạm vừa thay đổi, phương án không còn khả thi/)).toBeTruthy();
    expect(screen.getByText(/Huỷ lịch rồi đặt lại/)).toBeTruthy();

    postSpy.mockRestore();
    patchSpy.mockRestore();
  });
});
