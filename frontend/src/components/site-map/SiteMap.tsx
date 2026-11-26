"use client";

/**
 * SiteMap — mặt bằng bãi sạc (S9), dùng chung 2 vai trò (docs/plan/22-ui-work-split.md §9):
 *   vận hành: layout="landscape", interactive — chọn ô bằng chuột hoặc phím mũi tên + Enter;
 *   cư dân:   privacy — ô của người khác chỉ còn "Đang dùng / Trống / Tạm ngưng" (NFR riêng tư).
 */
import { useRef, type KeyboardEvent } from "react";

import type { components } from "@/lib/api/schema";

export type Zone = components["schemas"]["ChargerZone"];
export type BayStatus = components["schemas"]["ConnectorStatus"];
export type BayLayout = components["schemas"]["BayLayout"];
export type SiteLayout = components["schemas"]["SiteLayout"];

export type PortState = {
  status: BayStatus;
  veh?: string;
  kw?: number;
  soc?: number;
  target?: number;
  dep?: string;
  eta?: string;
  why?: string;
};

export type QueueCar = {
  veh?: string;
  dep?: string;
  start?: string;
};

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

type Rect = { x: number; y: number; w: number; h: number };
type Gate = { x: number; label: string; dir: "in" | "out" };

type LayoutSpec = {
  w: number;
  h: number;
  road: Rect;
  gates?: Gate[];
  room?: Rect | null;
  zones: Record<Zone, Rect>;
  cabinets: Record<string, Rect>;
  bays: Record<string, Rect>;
  lanes: Record<Zone, Rect>;
  regular: { x: number; y: number; n: number; w: number; h: number } | null;
};

const LAYOUT_SPECS: Record<"landscape" | "portrait", LayoutSpec> = {
  landscape: {
    w: 1000,
    h: 600,
    road: { x: 0, y: 0, w: 1000, h: 64 },
    gates: [
      { x: 60, label: "Lối vào", dir: "in" },
      { x: 940, label: "Lối ra", dir: "out" },
    ],
    room: { x: 24, y: 96, w: 176, h: 150 },
    regular: { x: 230, y: 84, n: 13, w: 52, h: 96 },
    zones: { AC: { x: 230, y: 214, w: 290, h: 262 }, DC: { x: 550, y: 214, w: 420, h: 262 } },
    cabinets: {
      "AC-01": { x: 255, y: 250, w: 110, h: 30 },
      "AC-02": { x: 385, y: 250, w: 110, h: 30 },
      "DC-01": { x: 650, y: 250, w: 220, h: 30 },
    },
    bays: {
      "AC-01-1": { x: 255, y: 300, w: 110, h: 160 },
      "AC-02-1": { x: 385, y: 300, w: 110, h: 160 },
      "DC-01-1": { x: 585, y: 300, w: 165, h: 160 },
      "DC-01-2": { x: 775, y: 300, w: 165, h: 160 },
    },
    lanes: { AC: { x: 230, y: 500, w: 290, h: 76 }, DC: { x: 550, y: 500, w: 420, h: 76 } },
  },
  portrait: {
    w: 360,
    h: 640,
    road: { x: 0, y: 0, w: 360, h: 44 },
    gates: [{ x: 60, label: "Lối vào", dir: "in" }],
    room: null,
    regular: null,
    zones: { AC: { x: 12, y: 58, w: 336, h: 214 }, DC: { x: 12, y: 286, w: 336, h: 214 } },
    cabinets: {
      "AC-01": { x: 32, y: 88, w: 136, h: 26 },
      "AC-02": { x: 192, y: 88, w: 136, h: 26 },
      "DC-01": { x: 32, y: 316, w: 296, h: 26 },
    },
    bays: {
      "AC-01-1": { x: 32, y: 124, w: 136, h: 136 },
      "AC-02-1": { x: 192, y: 124, w: 136, h: 136 },
      "DC-01-1": { x: 32, y: 352, w: 136, h: 136 },
      "DC-01-2": { x: 192, y: 352, w: 136, h: 136 },
    },
    lanes: { AC: { x: 12, y: 514, w: 164, h: 112 }, DC: { x: 184, y: 514, w: 164, h: 112 } },
  },
};

export const DEFAULT_PORTS: Array<{
  id: string;
  cabinet: string;
  zone: Zone;
  bay: string;
  limitKw: number;
}> = [
  { id: "AC-01-1", cabinet: "AC-01", zone: "AC", bay: "B-A1", limitKw: 11 },
  { id: "AC-02-1", cabinet: "AC-02", zone: "AC", bay: "B-A2", limitKw: 11 },
  { id: "DC-01-1", cabinet: "DC-01", zone: "DC", bay: "B-D1", limitKw: 60 },
  { id: "DC-01-2", cabinet: "DC-01", zone: "DC", bay: "B-D2", limitKw: 60 },
];

export const DEFAULT_CABINETS: Array<{
  id: string;
  zone: Zone;
  ports: number;
  portLimitKw: number;
}> = [
  { id: "AC-01", zone: "AC", ports: 1, portLimitKw: 11 },
  { id: "AC-02", zone: "AC", ports: 1, portLimitKw: 11 },
  { id: "DC-01", zone: "DC", ports: 2, portLimitKw: 60 },
];

export function usage(ports: Record<string, PortState>, eff = 0.95) {
  const out: Record<Zone, number> = { AC: 0, DC: 0 };
  for (const [id, st] of Object.entries(ports)) {
    const z: Zone = id.startsWith("DC") ? "DC" : "AC";
    out[z] += st?.kw ?? 0;
  }
  const safeEff = eff > 0 ? eff : 1;
  return { ...out, grid: (out.AC + out.DC) / safeEff };
}

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
  bays?: BayLayout[];
  gridLimitKw?: number;
  budgets?: Record<Zone, number>;
  conversionEff?: number;
};

export function SiteMap({
  layout,
  ports,
  queues,
  title,
  filter = "all",
  privacy = false,
  mine = null,
  mineQueue = null,
  selected,
  onSelect,
  bays,
  gridLimitKw = 106,
  budgets = { AC: 22, DC: 78 },
  conversionEff = 0.95,
}: SiteMapProps) {
  const L = LAYOUT_SPECS[layout];
  const compact = layout === "portrait";
  const interactive = Boolean(onSelect);
  const ref = useRef<SVGSVGElement>(null);
  const dim = (z: Zone) => (filter !== "all" && filter !== z ? 0.35 : 1);

  // Danh sách cổng hiển thị
  const renderedPorts: Array<{
    id: string;
    bay: string;
    zone: Zone;
    limitKw: number;
    cabinet: string;
    x?: number;
    y?: number;
    width?: number;
    height?: number;
  }> = bays && bays.length > 0
    ? bays.map((b) => {
        const id = b.connector_id ?? b.bay_id;
        const defaultMatch = DEFAULT_PORTS.find((p) => p.id === id || p.bay === b.bay_id);
        return {
          id,
          bay: b.bay_id,
          zone: b.zone as Zone,
          limitKw: defaultMatch?.limitKw ?? (b.zone === "AC" ? 11 : 60),
          cabinet: defaultMatch?.cabinet ?? (b.zone === "AC" ? "AC-01" : "DC-01"),
          x: b.x,
          y: b.y,
          width: b.width,
          height: b.height,
        };
      })
    : DEFAULT_PORTS;

  const ids = renderedPorts.map((p) => p.id);

  function onKey(e: KeyboardEvent<SVGGElement>, id: string) {
    if (ids.length === 0) return;
    const i = ids.indexOf(id);
    if (i === -1) return;
    const next =
      e.key === "ArrowRight" || e.key === "ArrowDown"
        ? ids[(i + 1) % ids.length]
        : e.key === "ArrowLeft" || e.key === "ArrowUp"
          ? ids[(i + ids.length - 1) % ids.length]
          : null;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect?.(id);
    } else if (next) {
      e.preventDefault();
      ref.current?.querySelector<SVGGElement>(`[data-port="${next}"]`)?.focus();
    }
  }

  const u = usage(ports, conversionEff);

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
        const yAC = cabAC.y + 15;
        const yDC = cabDC.y + 15;
        const busX = r.x + r.w + 12;
        const isAcFull = u.AC >= (budgets.AC ?? 22) - 0.05;
        const isDcFull = u.DC >= (budgets.DC ?? 78) - 0.05;
        return (
          <g>
            <rect x={r.x} y={r.y} width={r.w} height={r.h} rx={14} fill="#122d27" stroke="#24654e" strokeWidth={1.5} />
            <text x={r.x + 16} y={r.y + 28} fontSize="13" fontWeight="800" fill="#ffce70">⚡ Phòng điện</text>
            <text x={r.x + 16} y={r.y + 48} fontSize="12" fill="#d8edd8">Điểm đấu nối lưới</text>
            <text x={r.x + 16} y={r.y + 84} fontSize="22" fontWeight="800" fill="#fff" className="num">
              {u.grid.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}
            </text>
            <text x={r.x + 16} y={r.y + 104} fontSize="12" fill="#d8edd8">/ {gridLimitKw} kW đầu vào</text>
            <text x={r.x + 16} y={r.y + 132} fontSize="11" fill="#9fc3b1">
              hiệu suất chuyển đổi {Math.round(conversionEff * 100)}%
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
            <text x={b.x + 14} y={b.y + 22} fontSize="12.5" fontWeight="800" fill={z === "AC" ? "#163d34" : "#23585b"} data-zone-title={z}>
              Vùng {z} · {z === "AC" ? "sạc chậm" : "sạc nhanh"}
            </text>
            {compact ? null : (
              <text x={b.x + b.w - 14} y={b.y + 22} textAnchor="end" fontSize="11.5" fill="#52655d" data-zone-budget={z}>
                ngân sách {budgets[z] ?? (z === "AC" ? 22 : 78)} kW
              </text>
            )}
          </g>
        );
      })}

      {DEFAULT_CABINETS.map((c) => {
        const b = L.cabinets[c.id];
        if (!b) return null;
        return (
          <g key={c.id} opacity={dim(c.zone)}>
            <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="8" fill="#163d34" />
            <text x={b.x + 8} y={b.y + b.h / 2 + 4} fontSize={11} fontWeight="800" fill="#fff" data-cabinet-title={c.id}>
              Tủ {c.id}
            </text>
            <text x={b.x + b.w - 8} y={b.y + b.h / 2 + 4} textAnchor="end" fontSize="10.5" fill="#ffce70" data-cabinet-power={c.id}>
              {c.ports > 1 ? `${c.ports} × ` : ""}
              {c.portLimitKw} kW
            </text>
          </g>
        );
      })}

      {renderedPorts.map((p) => {
        const b = L.bays[p.id] ?? {
          x: "x" in p && typeof p.x === "number" ? p.x : 100,
          y: "y" in p && typeof p.y === "number" ? p.y : 300,
          w: "width" in p && typeof p.width === "number" ? p.width : 110,
          h: "height" in p && typeof p.height === "number" ? p.height : 160,
        };
        const st = ports[p.id] ?? ports[p.bay] ?? { status: "idle" };
        const isMine = mine === p.id || mine === p.bay;
        let S: Style;
        let aria: string;
        const lines: string[] = [];
        if (privacy && !isMine) {
          S = st.status === "idle" ? PUBLIC_STATUS.idle : st.status === "fault" ? PUBLIC_STATUS.fault : PUBLIC_STATUS.busy;
          aria = `Ô ${p.bay}, cổng ${p.id}, ${p.zone} ${p.limitKw} kW: ${S.label}`;
          lines.push(`${p.limitKw} kW · ${p.zone}`);
        } else {
          S = BAY_STATUS[st.status] ?? BAY_STATUS.idle;
          if (st.veh) lines.push(privacy ? "Xe của bạn" : `Xe ${st.veh}`);
          if ((st.status === "charging" || st.status === "throttled") && st.kw != null) lines.push(`${kw(st.kw)} / ${p.limitKw} kW`);
          if (st.soc != null && st.target != null) lines.push(`Pin ${pct(st.soc)} → ${pct(st.target)}`);
          if (!lines.length) lines.push(`${p.limitKw} kW · ${p.zone}`);
          aria = `Ô ${p.bay}, cổng ${p.id}: ${S.label}${lines.length ? ", " + lines.join(", ") : ""}`;
        }
        const sel = selected === p.id || selected === p.bay;
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
