import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LoadChart } from "@/components/station/LoadChart";

afterEach(cleanup);

describe("LoadChart", () => {
  it("không dồn nhãn trục X khi các điểm đo tập trung ở cuối dải thời gian", () => {
    const points = [
      { timestamp: "2026-11-25T16:18:00+07:00", total_power_kw: 0, power_limit_kw: 106 },
      { timestamp: "2026-11-25T16:19:00+07:00", total_power_kw: 12, power_limit_kw: 106 },
      { timestamp: "2026-11-25T16:31:00+07:00", total_power_kw: 2, power_limit_kw: 106 },
      { timestamp: "2026-11-25T16:31:30+07:00", total_power_kw: 2, power_limit_kw: 106 },
      { timestamp: "2026-11-25T16:32:00+07:00", total_power_kw: 1, power_limit_kw: 106 },
      { timestamp: "2026-11-25T16:32:30+07:00", total_power_kw: 0, power_limit_kw: 106 },
      { timestamp: "2026-11-25T16:33:00+07:00", total_power_kw: 0, power_limit_kw: 106 },
      { timestamp: "2026-11-25T16:33:30+07:00", total_power_kw: 0, power_limit_kw: 106 },
    ];
    const { container } = render(<LoadChart points={points} />);
    const ticks = Array.from(container.querySelectorAll<SVGTextElement>('text[data-axis-tick="x"]'));
    expect(ticks.length).toBeGreaterThanOrEqual(2);
    const xs = ticks.map((t) => Number(t.getAttribute("x")));
    for (let i = 1; i < xs.length; i++) {
      expect(xs[i] - xs[i - 1]).toBeGreaterThanOrEqual(76);
    }
    const labels = ticks.map((t) => t.textContent);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("hiển thị duy nhất 1 nhãn khi các điểm có cùng phút", () => {
    const points = [
      { timestamp: "2026-11-25T16:31:05+07:00", total_power_kw: 5, power_limit_kw: 106 },
      { timestamp: "2026-11-25T16:31:45+07:00", total_power_kw: 7, power_limit_kw: 106 },
    ];
    const { container } = render(<LoadChart points={points} />);
    const ticks = container.querySelectorAll('text[data-axis-tick="x"]');
    expect(ticks.length).toBe(1);
  });
});
