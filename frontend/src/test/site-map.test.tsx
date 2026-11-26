import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SiteMap, type PortState, type QueueCar, type Zone } from "@/components/site-map/SiteMap";
import { ConnectorGrid } from "@/components/station/ConnectorGrid";

afterEach(cleanup);

const mockPorts: Record<string, PortState> = {
  "AC-01-1": { status: "charging", veh: "AC-A", kw: 11, soc: 0.49, target: 0.65, dep: "20:00", eta: "19:28" },
  "AC-02-1": { status: "charging", veh: "AC-B", kw: 11, soc: 0.58, target: 0.7, dep: "20:15", eta: "19:18" },
  "DC-01-1": { status: "throttled", veh: "DC-A", kw: 39, soc: 0.45, target: 0.75, dep: "21:30", eta: "19:12" },
  "DC-01-2": { status: "throttled", veh: "DC-B", kw: 39, soc: 0.62, target: 0.7, dep: "21:30", eta: "18:39" },
};

const mockQueues: Record<Zone, QueueCar[]> = {
  AC: [{ veh: "AC-C", dep: "23:15", start: "~20:00" }, { veh: "AC-D", dep: "23:30", start: "~20:15" }],
  DC: [{ veh: "DC-C", dep: "22:00", start: "~18:44" }, { veh: "DC-D", dep: "22:00", start: "~19:17" }],
};

describe("SiteMap (S9, docs/plan/22-ui-work-split.md §9)", () => {
  it("trạng thái ô hiện bằng chữ, không chỉ bằng màu (WCAG 1.4.1)", () => {
    render(<SiteMap layout="landscape" ports={mockPorts} queues={mockQueues} title="Sơ đồ" onSelect={() => {}} />);
    expect(screen.getByRole("button", { name: /B-A1.*Đang sạc/ })).toBeTruthy();
    expect(screen.getAllByText("Giảm công suất").length).toBe(2);
  });

  it("chế độ cư dân không lộ xe, pin hay công suất của người khác (NFR riêng tư)", () => {
    const { container } = render(
      <SiteMap layout="portrait" ports={mockPorts} queues={mockQueues} title="Sơ đồ" privacy mine={null} />,
    );
    const text = container.textContent ?? "";
    for (const leaked of ["AC-A", "DC-B", "Pin ", "39 kW"]) expect(text).not.toContain(leaked);
    expect(text).toContain("Đang dùng");
  });

  it("phím mũi tên chuyển ô, Enter chọn ô", () => {
    const onSelect = vi.fn();
    render(<SiteMap layout="landscape" ports={mockPorts} queues={mockQueues} title="Sơ đồ" onSelect={onSelect} />);
    const first = screen.getByRole("button", { name: /B-A1/ });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(document.activeElement?.getAttribute("data-port")).toBe("AC-02-1");
    fireEvent.keyDown(document.activeElement as Element, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("AC-02-1");
  });

  it("rút gọn tiêu đề Vùng AC và cỡ chữ pill Tủ AC để không đè chữ trong khung 290px", () => {
    const { container } = render(<SiteMap layout="landscape" ports={mockPorts} queues={mockQueues} title="Sơ đồ" />);
    expect(container.querySelector('[data-zone-title="AC"]')?.textContent).toBe("Vùng AC · sạc chậm");
    expect(container.querySelector('[data-zone-budget="AC"]')?.textContent).toContain("ngân sách 22 kW");
    expect(container.querySelector('[data-cabinet-title="AC-01"]')?.getAttribute("font-size")).toBe("11");
  });
});

describe("ConnectorGrid (S5)", () => {
  it("mỗi ô có tên đầu nối, trạng thái bằng chữ và cảnh báo trễ hạn", () => {
    const onSelect = vi.fn();
    render(
      <ConnectorGrid
        connectors={[
          { connector_id: "A01", status: "charging", power_kw: 7, max_power_kw: 7, booking_id: "b1" },
          { connector_id: "A05", status: "fault", power_kw: 0, max_power_kw: 7 },
        ]}
        atRisk={["b1"]}
        onSelect={onSelect}
      />,
    );
    const a01 = screen.getByRole("button", { name: /A01, Đang sạc.*nguy cơ trễ hạn/ });
    expect(screen.getByRole("button", { name: /A05, Lỗi/ })).toBeTruthy();
    fireEvent.click(a01);
    expect(onSelect).toHaveBeenCalledWith("A01");
  });
});
