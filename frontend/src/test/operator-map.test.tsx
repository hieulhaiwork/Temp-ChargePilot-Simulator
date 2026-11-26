import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import OperatorMapPage from "@/app/operator/map/page";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

afterEach(cleanup);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const mockStationConfig = {
  station_id: "station-test",
  name: "Bãi sạc thông minh VinAI",
  power_limit_kw: 106,
  timezone: "Asia/Ho_Chi_Minh",
  connectors: [
    { connector_id: "AC-01-1", max_power_kw: 11, zone: "AC", bay_id: "B-A1" },
    { connector_id: "AC-02-1", max_power_kw: 11, zone: "AC", bay_id: "B-A2" },
    { connector_id: "DC-01-1", max_power_kw: 60, zone: "DC", bay_id: "B-D1" },
    { connector_id: "DC-01-2", max_power_kw: 60, zone: "DC", bay_id: "B-D2" },
  ],
  layout: {
    frame_landscape: [1000, 600],
    frame_portrait: [360, 640],
    bays: [
      { bay_id: "B-A1", zone: "AC", connector_id: "AC-01-1", x: 255, y: 300, width: 110, height: 160 },
      { bay_id: "B-A2", zone: "AC", connector_id: "AC-02-1", x: 385, y: 300, width: 110, height: 160 },
      { bay_id: "B-D1", zone: "DC", connector_id: "DC-01-1", x: 585, y: 300, width: 165, height: 160 },
      { bay_id: "B-D2", zone: "DC", connector_id: "DC-01-2", x: 775, y: 300, width: 165, height: 160 },
    ],
  },
} as unknown as components["schemas"]["StationConfig"];

const mockStationOverview: components["schemas"]["StationOverview"] = {
  power_limit_kw: 106,
  grid_input_kw: 74,
  grid_input_limit_kw: 106,
  utilization_pct: 69.8,
  charging_count: 3,
  queue_length: 2,
  zones: [
    { zone: "AC", output_kw: 22, budget_kw: 22 },
    { zone: "DC", output_kw: 48, budget_kw: 78 },
  ],
  state: {
    available_power_kw: 106,
    schedule_version: 3,
    timestamp: "2026-11-23T18:30:00+07:00",
    connectors: [
      { connector_id: "AC-01-1", status: "charging", power_kw: 11, max_power_kw: 11, booking_id: "VF8-01" },
      { connector_id: "AC-02-1", status: "charging", power_kw: 11, max_power_kw: 11, booking_id: "VF9-02" },
      { connector_id: "DC-01-1", status: "charging", power_kw: 48, max_power_kw: 60, booking_id: "VFe34-03" },
      { connector_id: "DC-01-2", status: "idle", power_kw: 0, max_power_kw: 60 },
    ],
  },
};

describe("OperatorMapPage (S9 G22, G23)", () => {
  it("render từ StationConfig.layout và StationOverview, không còn nhãn minh hoạ, hỗ trợ chọn ô bằng phím Enter", async () => {
    vi.spyOn(api, "GET").mockImplementation(async (path: string) => {
      if (path === "/api/v1/station/config") {
        return { data: mockStationConfig, response: new Response() } as never;
      }
      if (path === "/api/v1/operator/station") {
        return { data: mockStationOverview, response: new Response() } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<OperatorMapPage />, { wrapper });

    // Đợi dữ liệu render
    expect(await screen.findByText(/Bãi sạc thông minh VinAI/)).toBeTruthy();

    // Không còn banner "Dữ liệu minh hoạ"
    expect(screen.queryByText(/Dữ liệu minh hoạ/)).toBeNull();

    // Tìm ô B-A1 hoặc các button/interactive element của ô
    const bays = await screen.findAllByText(/B-A1/);
    expect(bays.length).toBeGreaterThan(0);

    // Nhấn Enter trên ô hoặc nút chọn ô
    const bayA1 = bays[0];
    const btnBay = bayA1.closest("[role='button'], button, [tabindex='0']") ?? bayA1;
    fireEvent.keyDown(btnBay, { key: "Enter", code: "Enter" });

    // Kiểm tra ô đang chọn cập nhật thông tin
    expect((await screen.findAllByText(/Ô B-A1/)).length).toBeGreaterThan(0);
  });
});
