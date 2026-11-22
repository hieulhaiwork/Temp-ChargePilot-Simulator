import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OPERATOR_SNAPSHOT } from "@/components/site-map/fixture";
import { SiteMap } from "@/components/site-map/SiteMap";
import { ConnectorGrid } from "@/components/station/ConnectorGrid";

afterEach(cleanup);

describe("SiteMap (S9, docs/plan/22-ui-work-split.md §9)", () => {
  it("trạng thái ô hiện bằng chữ, không chỉ bằng màu (WCAG 1.4.1)", () => {
    render(<SiteMap layout="landscape" ports={OPERATOR_SNAPSHOT.ports} queues={OPERATOR_SNAPSHOT.queues} title="Sơ đồ" onSelect={() => {}} />);
    expect(screen.getByRole("button", { name: /B-A1.*Đang sạc/ })).toBeTruthy();
    expect(screen.getAllByText("Giảm công suất").length).toBe(2);
  });

  it("chế độ cư dân không lộ xe, pin hay công suất của người khác (NFR riêng tư)", () => {
    const { container } = render(
      <SiteMap layout="portrait" ports={OPERATOR_SNAPSHOT.ports} queues={OPERATOR_SNAPSHOT.queues} title="Sơ đồ" privacy mine={null} />,
    );
    const text = container.textContent ?? "";
    for (const leaked of ["AC-A", "DC-B", "Pin ", "39 kW"]) expect(text).not.toContain(leaked);
    expect(text).toContain("Đang dùng");
  });

  it("phím mũi tên chuyển ô, Enter chọn ô", () => {
    const onSelect = vi.fn();
    render(<SiteMap layout="landscape" ports={OPERATOR_SNAPSHOT.ports} queues={OPERATOR_SNAPSHOT.queues} title="Sơ đồ" onSelect={onSelect} />);
    const first = screen.getByRole("button", { name: /B-A1/ });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(document.activeElement?.getAttribute("data-port")).toBe("AC-02-1");
    fireEvent.keyDown(document.activeElement as Element, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("AC-02-1");
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
