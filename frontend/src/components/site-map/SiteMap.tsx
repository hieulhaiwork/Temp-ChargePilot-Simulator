"use client";

/**
 * SiteMap — mặt bằng bãi sạc (S9), dùng chung 2 vai trò (docs/plan/22-ui-work-split.md §9):
 *   vận hành: layout="landscape", interactive — chọn ô bằng chuột hoặc phím mũi tên + Enter;
 *   cư dân:   privacy — ô của người khác chỉ còn "Đang dùng / Trống / Tạm ngưng" (NFR riêng tư).
 * Port 1-1 từ docs/mockups/cu-dan/assets/site-map.js (renderMap).
 */
import { useRef, type KeyboardEvent } from "react";

import { LAYOUTS, SITE, usage, type BayStatus, type PortState, type QueueCar, type Zone } from "./fixture";

type Style = { label: string; short?: string; fg: string; bg: string; mark: string; symbol: string };

export const BAY_STATUS: Record<BayStatus, Style> = {
  charging: { label: "Đang sạc", fg: "#163d34", bg: "#dff1e3", mark: "#24654e", symbol: "●" },
  throttled: { label: "Giảm công suất", short: "Giảm tải", fg: "#805114", bg: "#fff2d8", mark: "#a86f12", symbol: "▼" },
  idle: { label: "Trống", fg: "#3f5249", bg: "#f4f6f1", mark: "#6f8279", symbol: "○" },
  finished: { label: "Đã đầy, chưa rút", short: "Đã đầy", fg: "#23585b", bg: "#e6efef", mark: "#326467", symbol: "✓" },
  fault: { label: "Lỗi", fg: "#963d32", bg: "#fbece7", mark: "#963d32", symbol: "✕" },
};
export const PUBLIC_STATUS = {
  busy: { label: "Đang dùng", fg: "#3f5249", bg: "#e3e8e1", mark: "#6f8279", symbol: "●" },
  idle: BAY_STATUS.idle,
  fault: { label: "Tạm ngưng", fg: "#963d32", bg: "#fbece7", mark: "#963d32", symbol: "✕" },
} satisfies Record<string, Style>;

const pct = (v: number) => `${Math.round(v * 100)}%`;
const kw = (v: number) => `${v.toLocaleString("vi-VN", { maximumFractionDigits: 1 })} kW`;

function Car({ x, y, w, h, color, mine }: { x: number; y: number; w: number; h: number; color: string; mine: boolean }) {
  const cw = Math.min(w * 0.56, 70);
  const ch = Math.min(h * 0.62, 96);
  const cx = x + (w - cw) / 2;
  const cy = y + h - ch - 10;
  return (
    <g aria-hidden="true">
      <rect x={cx} y={cy} width={cw} height={ch} rx={cw * 0.28} fill={color} stroke={mine ? "#ffce70" : undefined} strokeWidth={mine ? 4 : 0} />
      <rect x={cx + cw * 0.14} y={cy + ch * 0.14} width={cw * 0.72} height={ch * 0.2} rx="6" fill="#fff" opacity=".55" />
    </g>
  );
}

export type SiteMapProps = {
  layout: "landscape" | "portrait";
  ports: Record<string, PortState>;
  queues: Record<Zone, QueueCar[]>;
  title: string;
  filter?: "all" | Zone;
  privacy?: boolean;
  mine?: string | null;
  mineQueue?: { zone: Zone; pos: number } | null;
  selected?: string;
  onSelect?: (portId: string) => void;
};

export function SiteMap({ layout, ports, queues, title, filter = "all", privacy = false, mine = null, mineQueue = null, selected, onSelect }: SiteMapProps) {
  const L = LAYOUTS[layout];
  const compact = layout === "portrait";
  const interactive = Boolean(onSelect);
  const ref = useRef<SVGSVGElement>(null);
  const dim = (z: Zone) => (filter !== "all" && filter !== z ? 0.35 : 1);
  const ids = SITE.ports.map((p) => p.id);

  function onKey(e: KeyboardEvent<SVGGElement>, id: string) {
    const i = ids.indexOf(id);
    const next = e.key === "ArrowRight" || e.key === "ArrowDown" ? ids[(i + 1) % ids.length] : e.key === "ArrowLeft" || e.key === "ArrowUp" ? ids[(i + ids.length - 1) % ids.length] : null;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect?.(id);
    } else if (next) {
      e.preventDefault();
      ref.current?.querySelector<SVGGElement>(`[data-port="${next}"]`)?.focus();
    }
  }

  return (
    <svg ref={ref} className="map-svg" viewBox={`0 0 ${L.w} ${L.h}`} role={interactive ? "group" : "img"} aria-label={title}>
      <title>{title}</title>
      <rect x={L.road.x} y={L.road.y} width={L.road.w} height={L.road.h} fill="#c3cbc0" />
      <line x1="0" y1={L.road.h / 2} x2={L.w} y2={L.road.h / 2} stroke="#fff" strokeWidth="3" strokeDasharray="18 14" />
      <text x={L.w / 2} y={L.road.h / 2 - 8} textAnchor="middle" fontSize="12" fontWeight="700" fill="#3f5249">
        Đường nội khu
      </text>

      {/* Cổng Lối vào / Lối ra */}
      {L.gates?.map((g, idx) => (
        <g key={idx} aria-hidden="true">
          <rect x={g.x - 44} y={L.road.h - 22} width={88} height={22} rx={6} fill="#163d34" />
          <text x={g.x} y={L.road.h - 7} textAnchor="middle" fontSize="12" fontWeight="700" fill="#ffce70">
            {g.dir === "in" ? "↓ " : "↑ "}{g.label}
          </text>
        </g>
      ))}

      {/* Phòng điện + đường cấp (chỉ bố cục ngang, không privacy) */}
      {L.room && !privacy && L.cabinets?.["AC-01"] && L.cabinets?.["DC-01"] && L.zones?.DC ? (() => {
        const r = L.room;
        const cabAC = L.cabinets["AC-01"];
        const cabDC = L.cabinets["DC-01"];
        const zoneDC = L.zones.DC;
        const u = usage(ports);
        const yAC = cabAC.y + 15;
        const yDC = cabDC.y + 15;
        const busX = r.x + r.w + 12;
        const isAcFull = u.AC >= SITE.budgets.AC - 0.05;
        const isDcFull = u.DC >= SITE.budgets.DC - 0.05;
        return (
          <g>
            <rect x={r.x} y={r.y} width={r.w} height={r.h} rx={14} fill="#122d27" stroke="#24654e" strokeWidth={1.5} />
            <text x={r.x + 16} y={r.y + 28} fontSize="13" fontWeight="800" fill="#ffce70">⚡ Phòng điện</text>
            <text x={r.x + 16} y={r.y + 48} fontSize="12" fill="#d8edd8">Điểm đấu nối lưới</text>
            <text x={r.x + 16} y={r.y + 84} fontSize="22" fontWeight="800" fill="#fff" className="num">
              {u.grid.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}
            </text>
            <text x={r.x + 16} y={r.y + 104} fontSize="12" fill="#d8edd8">/ {SITE.gridLimitKw} kW đầu vào</text>
            <text x={r.x + 16} y={r.y + 132} fontSize="11" fill="#9fc3b1">
              hiệu suất chuyển đổi {Math.round(SITE.conversionEff * 100)}%
            </text>

            {/* Bus line sang AC */}
            <path
              d={`M${r.x + r.w} ${r.y + 60} H${busX} V${yAC} H${cabAC.x}`}
              fill="none"
              stroke={isAcFull ? "#163d34" : "#24654e"}
              strokeWidth={isAcFull ? 5 : 3.5}
              strokeLinejoin="round"
            />
            {/* Bus line sang DC */}
            <path
              d={`M${busX} ${yAC} V${yDC + 34} H${zoneDC.x + 18} V${yDC} H${cabDC.x}`}
              fill="none"
              stroke={isDcFull ? "#163d34" : "#24654e"}
              strokeWidth={isDcFull ? 5 : 3.5}
              strokeLinejoin="round"
            />
          </g>
        );
      })() : null}

      {L.regular ? (
        <g aria-hidden="true">
          {Array.from({ length: L.regular.n }, (_, i) => {
            const g = L.regular!;
            const x = g.x + i * (g.w + 4);
            return (
              <g key={i}>
                <rect x={x} y={g.y} width={g.w} height={g.h} fill="none" stroke="#fff" strokeWidth="2" />
                {[1, 2, 4, 7, 8, 11].includes(i) ? <Car x={x} y={g.y} w={g.w} h={g.h} color="#a9b5ad" mine={false} /> : null}
              </g>
            );
          })}
          <text x={L.regular.x + 2} y={L.regular.y + L.regular.h + 18} fontSize="12" fill="#52655d">
            Ô đỗ thường P01–P13 · không có sạc, ngoài phạm vi điều khiển
          </text>
        </g>
      ) : null}

      {(["AC", "DC"] as Zone[]).map((z) => {
        const b = L.zones[z];
        return (
          <g key={z} opacity={dim(z)}>
            <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="16" fill={z === "AC" ? "#eef4ea" : "#eaf0ef"} stroke={z === "AC" ? "#b8dabf" : "#c0d8d8"} strokeWidth="1.5" />
            <text x={b.x + 14} y={b.y + 22} fontSize="13" fontWeight="800" fill={z === "AC" ? "#163d34" : "#23585b"}>
              Vùng {z} · {z === "AC" ? "sạc chậm, đỗ dài" : "sạc nhanh, đỗ ngắn"}
            </text>
            {compact ? null : (
              <text x={b.x + b.w - 14} y={b.y + 22} textAnchor="end" fontSize="12" fill="#52655d">
                ngân sách {SITE.budgets[z]} kW
              </text>
            )}
          </g>
        );
      })}

      {SITE.cabinets.map((c) => {
        const b = L.cabinets[c.id];
        return (
          <g key={c.id} opacity={dim(c.zone)}>
            <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="8" fill="#163d34" />
            <text x={b.x + 10} y={b.y + b.h / 2 + 4} fontSize={compact ? 11 : 12} fontWeight="800" fill="#fff">
              Tủ {c.id}
            </text>
            <text x={b.x + b.w - 10} y={b.y + b.h / 2 + 4} textAnchor="end" fontSize="11" fill="#ffce70">
              {c.ports > 1 ? `${c.ports} × ` : ""}
              {c.portLimitKw} kW
            </text>
          </g>
        );
      })}

      {SITE.ports.map((p) => {
        const b = L.bays[p.id];
        const st = ports[p.id] ?? { status: "idle" };
        const isMine = mine === p.id;
        let S: Style;
        let aria: string;
        const lines: string[] = [];
        if (privacy && !isMine) {
          S = st.status === "idle" ? PUBLIC_STATUS.idle : st.status === "fault" ? PUBLIC_STATUS.fault : PUBLIC_STATUS.busy;
          aria = `Ô ${p.bay}, cổng ${p.id}, ${p.zone} ${p.limitKw} kW: ${S.label}`;
          lines.push(`${p.limitKw} kW · ${p.zone}`);
        } else {
          S = BAY_STATUS[st.status];
          if (st.veh) lines.push(privacy ? "Xe của bạn" : `Xe ${st.veh}`);
          if ((st.status === "charging" || st.status === "throttled") && st.kw != null) lines.push(`${kw(st.kw)} / ${p.limitKw} kW`);
          if (st.soc != null && st.target != null) lines.push(`Pin ${pct(st.soc)} → ${pct(st.target)}`);
          if (!lines.length) lines.push(`${p.limitKw} kW · ${p.zone}`);
          aria = `Ô ${p.bay}, cổng ${p.id}: ${S.label}${lines.length ? ", " + lines.join(", ") : ""}`;
        }
        const sel = selected === p.id;
        const fs = compact ? 11.5 : 12.5;
        const showCar = Boolean(st.veh) || (privacy && st.status !== "idle" && st.status !== "fault");
        return (
          <g
            key={p.id}
            className={`bay ${sel ? "sel" : ""}`}
            data-port={p.id}
            tabIndex={interactive ? 0 : -1}
            role={interactive ? "button" : "img"}
            aria-label={aria}
            aria-pressed={interactive ? sel : undefined}
            opacity={dim(p.zone)}
            onClick={interactive ? () => onSelect?.(p.id) : undefined}
            onKeyDown={interactive ? (e) => onKey(e, p.id) : undefined}
          >
            <rect className="bay-ring" x={b.x} y={b.y} width={b.w} height={b.h} rx="10" fill={S.bg} stroke={isMine ? "#bc7c19" : S.mark} strokeWidth={isMine ? 4 : 2} />
            {showCar ? <Car x={b.x} y={b.y + 92} w={b.w} h={b.h - 92} color={isMine ? "#163d34" : privacy ? "#9aa79f" : S.mark} mine={isMine} /> : null}
            <text x={b.x + 10} y={b.y + 20} fontSize={fs + 1} fontWeight="800" fill={S.fg}>
              {p.bay}
              <tspan fontWeight="600" fontSize={fs - 1} fill="#52655d">
                {" "}
                · {p.id}
              </tspan>
            </text>
            <text x={b.x + 10} y={b.y + 39} fontSize={fs - 0.5} fontWeight="700" fill={S.fg}>
              <tspan fill={S.mark} fontWeight="800">{S.symbol} </tspan>
              {b.w < 130 && S.short ? S.short : S.label}
            </text>
            {lines.map((t, i) => (
              <text key={t} x={b.x + 10} y={b.y + 58 + i * 15} fontSize={fs - 1} fontWeight="600" fill={S.fg}>
                {t}
              </text>
            ))}
          </g>
        );
      })}

      {(["AC", "DC"] as Zone[]).map((z) => {
        const b = L.lanes[z];
        const q = queues[z] ?? [];
        const slots = compact ? 3 : 5;
        const sw = (b.w - 28) / slots;
        return (
          <g key={z} opacity={dim(z)} role="img" aria-label={`Làn chờ ${z}: ${q.length} xe${mineQueue?.zone === z ? `, xe của bạn ở vị trí ${mineQueue.pos}` : ""}`}>
            <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="14" fill="#cfd6cc" stroke="#fff" strokeWidth="2" strokeDasharray="8 6" />
            <text x={b.x + 14} y={b.y + 20} fontSize="12" fontWeight="800" fill="#3f5249">
              Làn chờ {z} · {q.length} xe
            </text>
            {q.slice(0, slots).map((v, i) => {
              const x = b.x + 14 + i * sw;
              const y = b.y + 28;
              const h = b.h - 36;
              const me = mineQueue?.zone === z && mineQueue.pos === i + 1;
              return (
                <g key={i}>
                  <rect x={x + 3} y={y} width={sw - 6} height={h} rx="9" fill={me ? "#163d34" : "#fff"} stroke={me ? "#ffce70" : "#b6c2b8"} strokeWidth={me ? 3 : 1} />
                  <text x={x + sw / 2} y={y + h / 2 - 2} textAnchor="middle" fontSize="12" fontWeight="800" fill={me ? "#ffce70" : "#163d34"}>
                    {i + 1}
                  </text>
                  <text x={x + sw / 2} y={y + h / 2 + 14} textAnchor="middle" fontSize="10.5" fontWeight="600" fill={me ? "#fff" : "#52655d"}>
                    {me ? "Bạn" : privacy ? "Xe" : v.veh}
                  </text>
                </g>
              );
            })}
            {q.length === 0 ? (
              <text x={b.x + b.w / 2} y={b.y + b.h / 2 + 12} textAnchor="middle" fontSize="12" fill="#52655d">
                Không có xe chờ
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

export function MapLegend({ publicView = false }: { publicView?: boolean }) {
  const items = publicView ? Object.values(PUBLIC_STATUS) : Object.values(BAY_STATUS);
  return (
    <ul className="legend-row" aria-label="Chú giải">
      {items.map((s) => (
        <li key={s.label}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: s.bg, border: `2px solid ${s.mark}` }} />
          {s.label}
        </li>
      ))}
      {publicView ? (
        <li>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: "#163d34", border: "2px solid #bc7c19" }} />
          Xe của bạn
        </li>
      ) : null}
    </ul>
  );
}
