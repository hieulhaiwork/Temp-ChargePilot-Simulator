import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PowerTiers } from "@/components/station/PowerTiers";
import type { components } from "@/lib/api/schema";

afterEach(cleanup);

type ZoneUsage = components["schemas"]["ZoneUsage"];

describe("PowerTiers component (S5/S9 G14, G23)", () => {
  const mockZones: ZoneUsage[] = [
    { zone: "AC", output_kw: 15.4, budget_kw: 22 },
    { zone: "DC", output_kw: 68.2, budget_kw: 78 },
  ];

  it("hiển thị số liệu công suất lưới và từng vùng AC/DC với aria-label hỗ trợ trợ năng", () => {
    render(
      <PowerTiers
        gridInputKw={88}
        gridInputLimitKw={106}
        zones={mockZones}
      />
    );

    // Kiểm tra hiển thị số liệu đầu vào lưới
    expect(screen.getByText(/88/)).toBeTruthy();
    expect(screen.getByText(/106/)).toBeTruthy();

    // Kiểm tra từng vùng
    expect(screen.getByText(/15,4|15\.4/)).toBeTruthy();
    expect(screen.getByText(/22/)).toBeTruthy();
    expect(screen.getByText(/68,2|68\.2/)).toBeTruthy();
    expect(screen.getByText(/78/)).toBeTruthy();

    // Kiểm tra aria-label của các thanh đo
    const meters = screen.getAllByRole("meter");
    expect(meters.length).toBeGreaterThanOrEqual(3);
    const gridMeter = meters[0];
    expect(gridMeter.getAttribute("aria-label")).toMatch(/lưới/i);
  });

  it("đổi màu/tone cảnh báo ở mức >= 85% (gold/cảnh báo) và >= 100% (bad/vượt trần)", () => {
    const dangerZones: ZoneUsage[] = [
      { zone: "AC", output_kw: 19, budget_kw: 22 }, // 86.4% -> warning/gold
      { zone: "DC", output_kw: 80, budget_kw: 78 }, // 102.5% -> danger/bad
    ];

    const { container } = render(
      <PowerTiers
        gridInputKw={108}
        gridInputLimitKw={106} // > 100% -> danger
        zones={dangerZones}
      />
    );

    // Kiểm tra có các phần tử mang class hoặc tone thể hiện trạng thái cảnh báo
    expect(container.querySelectorAll(".meter-warn, .meter-danger, .tag-gold, .tag-bad, [data-tone='gold'], [data-tone='bad']").length).toBeGreaterThan(0);
  });
});
