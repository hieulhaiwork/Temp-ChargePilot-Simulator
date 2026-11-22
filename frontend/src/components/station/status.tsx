/**
 * Trạng thái đầu nối (ConnectorStatus của backend) → chữ + icon + màu. Luôn hiện CHỮ, không chỉ dựa vào màu
 * (WCAG 1.4.1) — cùng bảng với docs/mockups/cu-dan/assets/site-map.js (STATUS) và mockup van-hanh.
 */
import type { ReactNode } from "react";

import type { Tone } from "@/components/ui/blocks";
import type { components } from "@/lib/api/schema";

export type ConnectorStatus = components["schemas"]["ConnectorStatus"];

export const CONNECTOR_STATUS: Record<ConnectorStatus, { label: string; tone: Tone; mark: string }> = {
  charging: { label: "Đang sạc", tone: "good", mark: "#24654e" },
  throttled: { label: "Giảm công suất", tone: "gold", mark: "#a86f12" },
  idle: { label: "Trống", tone: "neutral", mark: "#6f8279" },
  finished: { label: "Đã đầy", tone: "blue", mark: "#326467" },
  fault: { label: "Lỗi", tone: "bad", mark: "#963d32" },
};

const SHAPES: Record<ConnectorStatus, ReactNode> = {
  charging: <circle cx="8" cy="8" r="5" fill="currentColor" />,
  idle: <circle cx="8" cy="8" r="5" fill="none" stroke="currentColor" strokeWidth="2" />,
  throttled: <path d="M2.5 4h11L8 13z" fill="currentColor" />,
  finished: (
    <path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
  ),
  fault: <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />,
};

/** Hình riêng cho từng trạng thái (tròn đặc, tròn rỗng, tam giác, dấu tích, dấu nhân). */
export function StatusIcon({ status }: { status: ConnectorStatus }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" style={{ color: CONNECTOR_STATUS[status].mark, flex: "none" }}>
      {SHAPES[status]}
    </svg>
  );
}

export function StatusTag({ status }: { status: ConnectorStatus }) {
  const meta = CONNECTOR_STATUS[status];
  return (
    <span className={`tag tag-${meta.tone}`}>
      <StatusIcon status={status} />
      {meta.label}
    </span>
  );
}

export function StatusLegend() {
  return (
    <ul className="legend-row" aria-label="Chú giải trạng thái">
      {(Object.keys(CONNECTOR_STATUS) as ConnectorStatus[]).map((s) => (
        <li key={s}>
          <StatusIcon status={s} />
          {CONNECTOR_STATUS[s].label}
        </li>
      ))}
    </ul>
  );
}
