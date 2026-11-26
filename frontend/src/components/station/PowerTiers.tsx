"use client";

import { Panel, SectionHead, Tag, type Tone } from "@/components/ui/blocks";
import type { components } from "@/lib/api/schema";
import { formatKw } from "@/lib/format";

type ZoneUsage = components["schemas"]["ZoneUsage"];

interface PowerTiersProps {
  gridInputKw: number;
  gridInputLimitKw?: number | null;
  zones?: ZoneUsage[];
  className?: string;
}

export function PowerTiers({
  gridInputKw,
  gridInputLimitKw,
  zones = [],
  className = "",
}: PowerTiersProps) {
  const limitKw = gridInputLimitKw ?? 106;
  const gridRatio = limitKw > 0 ? gridInputKw / limitKw : 0;
  const gridPct = Math.round(gridRatio * 100);

  const getTierTone = (ratio: number): { tone: Tone; label: string; meterClass: string } => {
    if (ratio >= 1) {
      return { tone: "bad", label: "Vượt giới hạn", meterClass: "meter-danger bar full" };
    }
    if (ratio >= 0.85) {
      return { tone: "gold", label: "Cảnh báo cao", meterClass: "meter-warn bar warn" };
    }
    return { tone: "good", label: "Bình thường", meterClass: "bar" };
  };

  const gridTier = getTierTone(gridRatio);

  return (
    <Panel label="Phân bổ công suất theo tầng" className={`power-tiers ${className}`}>
      <SectionHead
        title="Công suất theo tầng (Lưới & Vùng)"
        icon="bolt"
        extra={<Tag tone={gridTier.tone}>{`Lưới: ${gridPct}%`}</Tag>}
      />

      <div className="stack" style={{ gap: 16, marginTop: 12 }}>
        {/* Tầng 1: Lưới tổng */}
        <div className="tier-card" style={{ padding: 12, backgroundColor: "var(--bg-subtle, #f5f7f5)", borderRadius: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
            <span style={{ fontWeight: 600 }}>Đầu vào lưới (Tổng trạm)</span>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className="num" style={{ fontWeight: 700 }}>
                {formatKw(gridInputKw)} / {formatKw(limitKw)}
              </span>
              <Tag tone={gridTier.tone}>{gridTier.label}</Tag>
            </div>
          </div>
          <div
            role="meter"
            aria-label={`Đầu vào lưới: ${formatKw(gridInputKw)} trên ${formatKw(limitKw)} (${gridPct}%)`}
            aria-valuenow={gridInputKw}
            aria-valuemin={0}
            aria-valuemax={limitKw}
            data-tone={gridTier.tone}
            className={gridTier.meterClass}
          >
            <i style={{ width: `${Math.min(gridRatio * 100, 100)}%` }} />
          </div>
        </div>

        {/* Tầng 2: Từng vùng */}
        {zones.length > 0 ? (
          <div className="fieldgrid" style={{ gap: 12 }}>
            {zones.map((z) => {
              const bKw = z.budget_kw ?? (z.zone === "AC" ? 22 : 78);
              const zRatio = bKw > 0 ? z.output_kw / bKw : 0;
              const zPct = Math.round(zRatio * 100);
              const zTier = getTierTone(zRatio);

              return (
                <div
                  key={z.zone}
                  className="tier-card"
                  style={{
                    padding: 12,
                    backgroundColor: "var(--bg-subtle, #f5f7f5)",
                    borderRadius: 10,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                    <span style={{ fontWeight: 600 }}>Vùng {z.zone}</span>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <span className="num" style={{ fontSize: 13, fontWeight: 700 }}>
                        {formatKw(z.output_kw)} / {formatKw(bKw)}
                      </span>
                      <Tag tone={zTier.tone}>{zTier.label}</Tag>
                    </div>
                  </div>
                  <div
                    role="meter"
                    aria-label={`Vùng ${z.zone}: ${formatKw(z.output_kw)} trên ${formatKw(bKw)} (${zPct}%)`}
                    aria-valuenow={z.output_kw}
                    aria-valuemin={0}
                    aria-valuemax={bKw}
                    data-tone={zTier.tone}
                    className={zTier.meterClass}
                  >
                    <i style={{ width: `${Math.min(zRatio * 100, 100)}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
