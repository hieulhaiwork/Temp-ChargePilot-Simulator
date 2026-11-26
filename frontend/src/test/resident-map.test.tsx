import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ResidentMapPage from "@/app/resident/map/page";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

afterEach(cleanup);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const mockSiteMapData: components["schemas"]["ResidentSiteMap"] = {
  timestamp: "2026-11-25T08:00:00+07:00",
  bays: [
    { bay_id: "BAY-AC-1", zone: "AC", public_status: "busy", mine: true },
    { bay_id: "BAY-AC-2", zone: "AC", public_status: "idle", mine: false },
    { bay_id: "BAY-DC-1", zone: "DC", public_status: "busy", mine: false },
    { bay_id: "BAY-DC-2", zone: "DC", public_status: "idle", mine: false },
  ],
  queues: {
    AC: { length: 1, my_position: null },
    DC: { length: 0, my_position: null },
  },
};

const mockStationConfig = {
  station_id: "station-test",
  name: "Bãi sạc thông minh VinAI",
  power_limit_kw: 106,
  timezone: "Asia/Ho_Chi_Minh",
  connectors: [
    { connector_id: "AC-01-1", max_power_kw: 11, zone: "AC" },
    { connector_id: "AC-02-1", max_power_kw: 11, zone: "AC" },
    { connector_id: "DC-01-1", max_power_kw: 60, zone: "DC" },
    { connector_id: "DC-01-2", max_power_kw: 60, zone: "DC" },
  ],
  layout: {
    frame_landscape: [1000, 600],
    frame_portrait: [360, 640],
    bays: [
      { bay_id: "BAY-AC-1", zone: "AC", connector_id: "AC-01-1", x: 100, y: 100, width: 80, height: 120 },
      { bay_id: "BAY-AC-2", zone: "AC", connector_id: "AC-02-1", x: 200, y: 100, width: 80, height: 120 },
      { bay_id: "BAY-DC-1", zone: "DC", connector_id: "DC-01-1", x: 300, y: 100, width: 80, height: 120 },
      { bay_id: "BAY-DC-2", zone: "DC", connector_id: "DC-01-2", x: 400, y: 100, width: 80, height: 120 },
    ],
  },
} as unknown as components["schemas"]["StationConfig"];

describe("ResidentMapPage (S9 G24)", () => {
  it("render từ ResidentSiteMap và StationConfig, ô mine có nhãn 'Xe của bạn'", async () => {
    vi.spyOn(api, "GET").mockImplementation(async (path: string) => {
      if (path === "/api/v1/resident/site-map") {
        return { data: mockSiteMapData, response: new Response() } as never;
      }
      if (path === "/api/v1/station/config") {
        return { data: mockStationConfig, response: new Response() } as never;
      }
      return { error: { detail: "not found" }, response: new Response(null, { status: 404 }) } as never;
    });

    render(<ResidentMapPage />, { wrapper });

    expect(await screen.findByText(/Cổng AC trống 1\/2/)).toBeTruthy();
    expect((await screen.findAllByText(/BAY-AC-1/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Xe của bạn/).length).toBeGreaterThan(0);
  });
});
