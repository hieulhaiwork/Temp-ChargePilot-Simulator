import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "@/components/resident/ChatPanel";
import { api } from "@/lib/api/client";

afterEach(cleanup);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("ChatPanel resume (S2 S3 G1 G4)", () => {
  it("resume trả 409 no_pending_confirmation → hiện thông báo và nút đặt bằng form", async () => {
    vi.spyOn(api, "PATCH").mockImplementation(async (path: string) => {
      if (path === "/api/v1/chat/sessions/{session_id}") {
        return {
          error: { detail: "Phiên chat không có yêu cầu nào đang chờ xác nhận", code: "no_pending_confirmation" },
          response: new Response(null, { status: 409 }),
        } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<ChatPanel initialConfirmingSession="test-session-123" />, { wrapper });

    const approveBtn = screen.getByRole("button", { name: /Xác nhận lịch/ });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(screen.getByText(/Chưa đặt được lịch qua Trợ lý/)).toBeTruthy();
    });
    expect(screen.getByRole("link", { name: /Đặt lịch bằng biểu mẫu/ })).toBeTruthy();
  });

  it("resume trả booking thành công → hiện trạng thái đã đặt lịch", async () => {
    vi.spyOn(api, "PATCH").mockImplementation(async (path: string) => {
      if (path === "/api/v1/chat/sessions/{session_id}") {
        return {
          data: {
            response: "Đã xác nhận đặt lịch sạc thành công.",
            session_id: "test-session-123",
            status: "answer",
            booking: {
              booking_id: "book-new-123",
              resident_id: "res-test",
              status: "confirmed",
              vehicle_model: "VF8_NEW_2026",
            },
          },
          response: new Response(),
        } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<ChatPanel initialConfirmingSession="test-session-123" />, { wrapper });

    const approveBtn = screen.getByRole("button", { name: /Xác nhận lịch/ });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(screen.getByText(/Đã chốt lịch thành công · Mã đặt lịch book-new-123/)).toBeTruthy();
    });
  });
});
