"use client";

/**
 * Lưới đầu nối của S5 (spec 21 §3.1) — một ô / đầu nối, đọc từ StationOverview.state.connectors.
 * Ô có viền vàng = booking nằm trong at_risk_booking_ids (nguy cơ trễ hạn). Bấm ô → onSelect (ConnectorDialog).
 */
import type { components } from "@/lib/api/schema";
import { formatKw } from "@/lib/format";

import { CONNECTOR_STATUS, StatusIcon } from "./status";

type ConnectorState = components["schemas"]["ConnectorState"];

export function ConnectorGrid({
  connectors,
  atRisk = [],
  onSelect,
}: {
  connectors: ConnectorState[];
  atRisk?: string[];
  onSelect?: (connectorId: string) => void;
}) {
  if (connectors.length === 0) return <p className="subcopy">Trạm chưa khai báo đầu nối nào.</p>;
  return (
    <div className="tiles">
      {connectors.map((c) => {
        const meta = CONNECTOR_STATUS[c.status];
        const risk = c.booking_id ? atRisk.includes(c.booking_id) : false;
        return (
          <button
            key={c.connector_id}
            type="button"
            className={`tile st-${c.status} ${risk ? "at-risk" : ""}`}
            onClick={() => onSelect?.(c.connector_id)}
            aria-label={`${c.connector_id}, ${meta.label}, ${formatKw(c.power_kw)}${risk ? ", nguy cơ trễ hạn" : ""}. Xem chi tiết`}
          >
            <span className="tid">{c.connector_id}</span>
            <span>
              <span className="tst">
                <StatusIcon status={c.status} />
                {meta.label}
              </span>
              <span className="hint" style={{ color: "inherit", opacity: 0.85 }}>
                {c.booking_id ? `Lịch ${c.booking_id}` : c.status === "fault" ? "Không nhận lệnh" : "Sẵn sàng đón xe"}
                {risk ? " · nguy cơ trễ" : ""}
              </span>
            </span>
            <span className="tkw num">
              {formatKw(c.power_kw)} / {formatKw(c.max_power_kw)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
