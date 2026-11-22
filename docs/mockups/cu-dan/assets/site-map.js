/* Sơ đồ bãi ChargePilot — dữ liệu mẫu + bộ vẽ SVG dùng chung cho cu-dan (resident-map) và van-hanh (operator-map).
 *
 * Topology theo ADR-010 (MVP-1 starter, kịch bản evening_9cars_hybrid_v1):
 *   lưới 106 kW · hiệu suất chuyển đổi 95 % · ngân sách AC 22 kW / DC 78 kW
 *   AC-01, AC-02: mỗi tủ 1 cổng 11 kW · DC-01: 2 cổng × 60 kW
 * Mọi số ở đây là MINH HOẠ. Bản thật đọc từ GET /station/config (+ G22 layout) và GET /operator/station.
 */
(function () {
  "use strict";

  const SITE = {
    name: "Bãi sạc khu cư dân CP-01",
    gridLimitKw: 106,
    conversionEff: 0.95,
    budgets: { AC: 22, DC: 78 },
    cabinets: [
      { id: "AC-01", zone: "AC", ports: 1, portLimitKw: 11, outputLimitKw: 11 },
      { id: "AC-02", zone: "AC", ports: 1, portLimitKw: 11, outputLimitKw: 11 },
      { id: "DC-01", zone: "DC", ports: 2, portLimitKw: 60, outputLimitKw: 120 },
    ],
    ports: [
      { id: "AC-01-1", cabinet: "AC-01", zone: "AC", bay: "B-A1", limitKw: 11 },
      { id: "AC-02-1", cabinet: "AC-02", zone: "AC", bay: "B-A2", limitKw: 11 },
      { id: "DC-01-1", cabinet: "DC-01", zone: "DC", bay: "B-D1", limitKw: 60 },
      { id: "DC-01-2", cabinet: "DC-01", zone: "DC", bay: "B-D2", limitKw: 60 },
    ],
  };

  /* Toạ độ = khối `layout` đề xuất ở G22 (config/site_layout.yaml). Hai bố cục: ngang (máy tính) và dọc (điện thoại). */
  const LAYOUTS = {
    landscape: {
      w: 1000, h: 600,
      road: { x: 0, y: 0, w: 1000, h: 64 },
      gates: [{ x: 60, label: "Lối vào", dir: "in" }, { x: 940, label: "Lối ra", dir: "out" }],
      room: { x: 24, y: 96, w: 176, h: 150 },
      regular: { x: 230, y: 84, n: 13, w: 52, h: 96 },
      zones: { AC: { x: 230, y: 214, w: 290, h: 262 }, DC: { x: 550, y: 214, w: 420, h: 262 } },
      cabinets: { "AC-01": { x: 255, y: 250, w: 110, h: 30 }, "AC-02": { x: 385, y: 250, w: 110, h: 30 }, "DC-01": { x: 650, y: 250, w: 220, h: 30 } },
      bays: { "AC-01-1": { x: 255, y: 300, w: 110, h: 160 }, "AC-02-1": { x: 385, y: 300, w: 110, h: 160 }, "DC-01-1": { x: 585, y: 300, w: 165, h: 160 }, "DC-01-2": { x: 775, y: 300, w: 165, h: 160 } },
      lanes: { AC: { x: 230, y: 500, w: 290, h: 76 }, DC: { x: 550, y: 500, w: 420, h: 76 } },
    },
    portrait: {
      w: 360, h: 640,
      road: { x: 0, y: 0, w: 360, h: 44 },
      gates: [{ x: 60, label: "Lối vào", dir: "in" }],
      room: null,
      regular: null,
      zones: { AC: { x: 12, y: 58, w: 336, h: 214 }, DC: { x: 12, y: 286, w: 336, h: 214 } },
      cabinets: { "AC-01": { x: 32, y: 88, w: 136, h: 26 }, "AC-02": { x: 192, y: 88, w: 136, h: 26 }, "DC-01": { x: 32, y: 316, w: 296, h: 26 } },
      bays: { "AC-01-1": { x: 32, y: 124, w: 136, h: 136 }, "AC-02-1": { x: 192, y: 124, w: 136, h: 136 }, "DC-01-1": { x: 32, y: 352, w: 136, h: 136 }, "DC-01-2": { x: 192, y: 352, w: 136, h: 136 } },
      lanes: { AC: { x: 12, y: 514, w: 164, h: 112 }, DC: { x: 184, y: 514, w: 164, h: 112 } },
    },
  };

  /* Trạng thái: chữ + icon + màu (WCAG 1.4.1). Khớp ConnectorStatus hiện có trong src/models/station.py. */
  const STATUS = {
    charging: { label: "Đang sạc", fg: "#163d34", bg: "#dff1e3", mark: "#24654e", icon: "dot" },
    throttled: { label: "Giảm công suất", short: "Giảm tải", fg: "#805114", bg: "#fff2d8", mark: "#a86f12", icon: "down" },
    idle: { label: "Trống", fg: "#3f5249", bg: "#f4f6f1", mark: "#6f8279", icon: "ring" },
    finished: { label: "Đã đầy, chưa rút", short: "Đã đầy", fg: "#23585b", bg: "#e6efef", mark: "#326467", icon: "check" },
    fault: { label: "Lỗi", fg: "#963d32", bg: "#fbece7", mark: "#963d32", icon: "cross" },
  };
  /* Cư dân chỉ thấy 3 mức cho ô của người khác — không lộ xe, SOC hay giờ rời của cư dân khác (NFR riêng tư). */
  const PUBLIC = {
    busy: { label: "Đang dùng", fg: "#3f5249", bg: "#e3e8e1", mark: "#6f8279", icon: "dot" },
    idle: STATUS.idle,
    fault: { label: "Tạm ngưng", fg: "#963d32", bg: "#fbece7", mark: "#963d32", icon: "cross" },
  };

  const ICON_PATHS = {
    dot: '<circle cx="8" cy="8" r="5" fill="currentColor"/>',
    ring: '<circle cx="8" cy="8" r="5" fill="none" stroke="currentColor" stroke-width="2"/>',
    down: '<path d="M2.5 4h11L8 13z" fill="currentColor"/>',
    check: '<path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    cross: '<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>',
  };
  const icon = (name, color) => `<svg viewBox="0 0 16 16" aria-hidden="true" style="color:${color}">${ICON_PATHS[name]}</svg>`;

  const nf1 = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
  const kw = (v) => `${nf1.format(v)} kW`;
  const pct = (v) => `${Math.round(v * 100)}%`;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function usage(ports) {
    const out = { AC: 0, DC: 0 };
    for (const p of SITE.ports) out[p.zone] += ports[p.id]?.kw || 0;
    const grid = (out.AC + out.DC) / SITE.conversionEff;
    return { ...out, grid };
  }

  /* ---------- Vẽ SVG ---------- */
  function car(x, y, w, h, color, mine) {
    const cw = Math.min(w * 0.56, 70), ch = Math.min(h * 0.62, 96);
    const cx = x + (w - cw) / 2, cy = y + h - ch - 10;
    return `<g aria-hidden="true">
      <rect x="${cx}" y="${cy}" width="${cw}" height="${ch}" rx="${cw * 0.28}" fill="${color}" ${mine ? 'stroke="#ffce70" stroke-width="4"' : ""}/>
      <rect x="${cx + cw * 0.14}" y="${cy + ch * 0.14}" width="${cw * 0.72}" height="${ch * 0.2}" rx="6" fill="#ffffff" opacity=".55"/>
      <rect x="${cx + cw * 0.14}" y="${cy + ch * 0.66}" width="${cw * 0.72}" height="${ch * 0.14}" rx="5" fill="#ffffff" opacity=".4"/>
    </g>`;
  }

  function svgIcon(name, x, y, size, color) {
    return `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="0 0 16 16" aria-hidden="true" style="color:${color}">${ICON_PATHS[name]}</svg>`;
  }

  function renderMap(el, opts) {
    const L = LAYOUTS[opts.layout];
    const filter = opts.filter || "all";
    const parts = [];
    const compact = opts.layout === "portrait";
    const fs = compact ? 1 : 1.05;

    // Đường nội khu + cổng
    parts.push(`<rect x="${L.road.x}" y="${L.road.y}" width="${L.road.w}" height="${L.road.h}" fill="#c3cbc0"/>`);
    parts.push(`<line x1="0" y1="${L.road.h / 2}" x2="${L.w}" y2="${L.road.h / 2}" stroke="#fff" stroke-width="3" stroke-dasharray="18 14"/>`);
    parts.push(`<text class="svg-t" x="${L.w / 2}" y="${L.road.h / 2 - 8}" text-anchor="middle" font-size="${12 * fs}" font-weight="700" fill="#3f5249">Đường nội khu</text>`);
    for (const g of L.gates) {
      parts.push(`<g aria-hidden="true"><rect x="${g.x - 44}" y="${L.road.h - 22}" width="88" height="22" rx="6" fill="#163d34"/>
        <text class="svg-t" x="${g.x}" y="${L.road.h - 7}" text-anchor="middle" font-size="12" font-weight="700" fill="#ffce70">${g.dir === "in" ? "↓ " : "↑ "}${g.label}</text></g>`);
    }

    // Phòng điện + đường cấp (chỉ bố cục ngang)
    if (L.room && !opts.privacy) {
      const r = L.room, u = usage(opts.ports);
      parts.push(`<g><rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" rx="14" fill="#122d27"/>
        <text class="svg-t" x="${r.x + 16}" y="${r.y + 28}" font-size="13" font-weight="800" fill="#ffce70">⚡ Phòng điện</text>
        <text class="svg-t" x="${r.x + 16}" y="${r.y + 48}" font-size="12" fill="#d8edd8">Điểm đấu nối lưới</text>
        <text class="svg-t num" x="${r.x + 16}" y="${r.y + 84}" font-size="22" font-weight="800" fill="#fff">${nf1.format(u.grid)}</text>
        <text class="svg-t" x="${r.x + 16}" y="${r.y + 104}" font-size="12" fill="#d8edd8">/ ${SITE.gridLimitKw} kW đầu vào</text>
        <text class="svg-t" x="${r.x + 16}" y="${r.y + 132}" font-size="11" fill="#9fc3b1">hiệu suất chuyển đổi ${pct(SITE.conversionEff)}</text></g>`);
      const yAC = L.cabinets["AC-01"].y + 15, yDC = L.cabinets["DC-01"].y + 15;
      const busX = r.x + r.w + 12;
      const line = (x1, y1, x2, y2, label, val, budget) => {
        const full = val >= budget - 0.05;
        return `<path d="M${x1} ${y1} H${busX} V${y2} H${x2}" fill="none" stroke="${full ? "#163d34" : "#24654e"}" stroke-width="${full ? 5 : 3.5}" stroke-linejoin="round"/>
`;
      };
      parts.push(line(r.x + r.w, r.y + 60, L.cabinets["AC-01"].x, yAC, "AC", u.AC, SITE.budgets.AC));
      parts.push(`<path d="M${busX} ${yAC} V${yDC + 34} H${L.zones.DC.x + 18} V${yDC} H${L.cabinets["DC-01"].x}" fill="none" stroke="${u.DC >= SITE.budgets.DC - 0.05 ? "#163d34" : "#24654e"}" stroke-width="${u.DC >= SITE.budgets.DC - 0.05 ? 5 : 3.5}" stroke-linejoin="round"/>`);
    }

    // Ô đỗ thường (không có sạc) — cho thấy đây là một phần của bãi xe khu
    if (L.regular) {
      const g = L.regular;
      for (let i = 0; i < g.n; i++) {
        const x = g.x + i * (g.w + 4);
        parts.push(`<rect x="${x}" y="${g.y}" width="${g.w}" height="${g.h}" fill="none" stroke="#fff" stroke-width="2"/>`);
        if ([1, 2, 4, 7, 8, 11].includes(i)) parts.push(car(x, g.y, g.w, g.h, "#a9b5ad", false));
      }
      parts.push(`<text class="svg-t" x="${g.x + 2}" y="${g.y + g.h + 18}" font-size="12" fill="#52655d">Ô đỗ thường P01–P13 · không có sạc, ngoài phạm vi điều khiển</text>`);
    }

    // Vùng AC / DC
    for (const z of ["AC", "DC"]) {
      const b = L.zones[z];
      const dim = filter !== "all" && filter !== z;
      parts.push(`<g opacity="${dim ? 0.35 : 1}"><rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="16" fill="${z === "AC" ? "#eef4ea" : "#eaf0ef"}" stroke="${z === "AC" ? "#b8dabf" : "#c0d8d8"}" stroke-width="1.5"/>
        <text class="svg-t" x="${b.x + 14}" y="${b.y + 22}" font-size="${13 * fs}" font-weight="800" fill="${z === "AC" ? "#163d34" : "#23585b"}">Vùng ${z} · ${z === "AC" ? (compact ? "sạc chậm, đỗ dài" : "sạc chậm") : (compact ? "sạc nhanh, đỗ ngắn" : "sạc nhanh, đỗ ngắn")}</text>
        ${compact ? "" : `<text class="svg-t num" x="${b.x + b.w - 14}" y="${b.y + 22}" text-anchor="end" font-size="12" fill="#52655d">ngân sách ${SITE.budgets[z]} kW</text>`}</g>`);
    }

    // Tủ
    for (const c of SITE.cabinets) {
      const b = L.cabinets[c.id];
      const dim = filter !== "all" && filter !== c.zone;
      parts.push(`<g opacity="${dim ? 0.35 : 1}"><rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="8" fill="#163d34"/>
        <text class="svg-t" x="${b.x + 10}" y="${b.y + b.h / 2 + 4}" font-size="${compact ? 11 : 12}" font-weight="800" fill="#fff">Tủ ${c.id}</text>
        <text class="svg-t num" x="${b.x + b.w - 10}" y="${b.y + b.h / 2 + 4}" text-anchor="end" font-size="11" fill="#ffce70">${c.ports > 1 ? c.ports + " × " : ""}${c.portLimitKw} kW</text></g>`);
    }

    // Ô sạc
    for (const p of SITE.ports) {
      const b = L.bays[p.id];
      const st = opts.ports[p.id] || { status: "idle" };
      const mine = opts.mine && opts.mine === p.id;
      let S, aria, lines;
      if (opts.privacy && !mine) {
        const pub = st.status === "idle" ? "idle" : st.status === "fault" ? "fault" : "busy";
        S = PUBLIC[pub];
        aria = `Ô ${p.bay}, cổng ${p.id}, ${p.zone} ${p.limitKw} kW: ${S.label}`;
        lines = [p.limitKw + " kW · " + p.zone];
      } else {
        S = STATUS[st.status];
        const who = st.veh ? (opts.privacy ? "Xe của bạn" : st.veh) : "";
        aria = `Ô ${p.bay}, cổng ${p.id}: ${S.label}${who ? ", " + who : ""}${st.kw ? ", " + kw(st.kw) + " trên " + kw(p.limitKw) : ""}${st.soc != null ? ", pin " + pct(st.soc) : ""}`;
        lines = [];
        if (st.veh) lines.push(opts.privacy ? "Xe của bạn" : `Xe ${st.veh}`);
        if (st.status === "charging" || st.status === "throttled") lines.push(`${nf1.format(st.kw)}/${p.limitKw} kW`);
        if (st.soc != null) lines.push(`Pin ${pct(st.soc)} → ${pct(st.target)}`);
        if (!lines.length) lines.push(`${p.limitKw} kW · ${p.zone}`);
      }
      const dim = filter !== "all" && filter !== p.zone;
      const sel = opts.selected === p.id;
      const label = compact ? 11.5 : 12.5;
      parts.push(`<g class="bay${sel ? " sel" : ""}" data-port="${p.id}" tabindex="${opts.interactive ? 0 : -1}" role="${opts.interactive ? "button" : "img"}" aria-label="${esc(aria)}"${opts.interactive ? ` aria-pressed="${sel}"` : ""} opacity="${dim ? 0.35 : 1}">
        <rect class="bay-ring" x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="10" fill="${S.bg}" stroke="${mine ? "#bc7c19" : S.mark}" stroke-width="${mine ? 4 : 2}"/>
        <line x1="${b.x + 8}" y1="${b.y + b.h - 6}" x2="${b.x + b.w - 8}" y2="${b.y + b.h - 6}" stroke="#fff" stroke-width="3"/>
        ${st.veh || (opts.privacy && st.status !== "idle" && st.status !== "fault") ? car(b.x, b.y + 92, b.w, b.h - 92, mine ? "#163d34" : opts.privacy ? "#9aa79f" : S.mark, mine) : ""}
        <text class="svg-t" x="${b.x + 10}" y="${b.y + 20}" font-size="${label + 1}" font-weight="800" fill="${S.fg}">${p.bay}<tspan font-weight="600" font-size="${label - 1}" fill="#52655d"> · ${p.id}</tspan></text>
        ${svgIcon(S.icon, b.x + 10, b.y + 28, 13, S.mark)}
        <text class="svg-t" x="${b.x + 28}" y="${b.y + 39}" font-size="${label - 0.5}" font-weight="700" fill="${S.fg}">${b.w < 130 && S.short ? S.short : S.label}</text>
        ${lines.map((t, i) => `<text class="svg-t num" x="${b.x + 10}" y="${b.y + 58 + i * 15}" font-size="${label - 1}" font-weight="600" fill="${S.fg}">${esc(t)}</text>`).join("")}
      </g>`);
    }

    // Làn chờ
    for (const z of ["AC", "DC"]) {
      const b = L.lanes[z];
      const q = opts.queues[z] || [];
      const dim = filter !== "all" && filter !== z;
      const slots = compact ? 3 : 5;
      const sw = (b.w - 28) / slots;
      parts.push(`<g opacity="${dim ? 0.35 : 1}" role="img" aria-label="Làn chờ ${z}: ${q.length} xe${opts.mineQueue && opts.mineQueue.zone === z ? ", xe của bạn ở vị trí " + opts.mineQueue.pos : ""}">
        <rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="14" fill="#cfd6cc" stroke="#fff" stroke-width="2" stroke-dasharray="8 6"/>
        <text class="svg-t" x="${b.x + 14}" y="${b.y + 20}" font-size="12" font-weight="800" fill="#3f5249">Làn chờ ${z} · ${q.length} xe</text>`);
      q.slice(0, slots).forEach((v, i) => {
        const x = b.x + 14 + i * sw, y = b.y + 28, h = b.h - 36;
        const isMine = opts.mineQueue && opts.mineQueue.zone === z && opts.mineQueue.pos === i + 1;
        parts.push(`<rect x="${x + 3}" y="${y}" width="${sw - 6}" height="${h}" rx="9" fill="${isMine ? "#163d34" : "#ffffff"}" stroke="${isMine ? "#ffce70" : "#b6c2b8"}" stroke-width="${isMine ? 3 : 1}"/>
          <text class="svg-t num" x="${x + sw / 2}" y="${y + h / 2 - 2}" text-anchor="middle" font-size="12" font-weight="800" fill="${isMine ? "#ffce70" : "#163d34"}">${i + 1}</text>
          <text class="svg-t" x="${x + sw / 2}" y="${y + h / 2 + 14}" text-anchor="middle" font-size="10.5" font-weight="600" fill="${isMine ? "#fff" : "#52655d"}">${isMine ? "Bạn" : opts.privacy ? "Xe" : esc(v.veh)}</text>`);
      });
      if (!q.length) parts.push(`<text class="svg-t" x="${b.x + b.w / 2}" y="${b.y + b.h / 2 + 12}" text-anchor="middle" font-size="12" fill="#52655d">Không có xe chờ</text>`);
      parts.push(`</g>`);
    }

    el.setAttribute("viewBox", `0 0 ${L.w} ${L.h}`);
    el.innerHTML = `<title>${esc(opts.title)}</title>` + parts.join("");
  }

  function legend(el, set) {
    const src = set === "public" ? PUBLIC : STATUS;
    el.innerHTML = Object.values(src).map((s) => `<li>${icon(s.icon, s.mark)}${s.label}</li>`).join("") +
      (set === "public" ? `<li><svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1.5" y="1.5" width="13" height="13" rx="3" fill="#163d34" stroke="#bc7c19" stroke-width="2.5"/></svg>Xe của bạn</li>` : "");
  }

  function badge(status, set) {
    const s = (set === "public" ? PUBLIC : STATUS)[status];
    return `<span class="badge" style="background:${s.bg};color:${s.fg};border-color:${s.mark}55">${icon(s.icon, s.mark)}${s.label}</span>`;
  }

  /* Chọn kịch bản mẫu qua ?state= ; giữ nguyên trên URL để chia sẻ link. */
  function stateFromUrl(states, fallback) {
    try {
      const k = new URLSearchParams(location.search).get("state");
      return states[k] ? k : fallback;
    } catch (e) { return fallback; }
  }
  function mountSwitcher(select, states, current, onChange) {
    select.innerHTML = Object.entries(states).map(([k, s]) => `<option value="${k}"${k === current ? " selected" : ""}>${esc(s.label)}</option>`).join("");
    select.addEventListener("change", () => {
      try { const u = new URL(location.href); u.searchParams.set("state", select.value); history.replaceState(null, "", u); } catch (e) { /* file:// */ }
      onChange(select.value);
    });
  }

  window.SiteMap = { SITE, STATUS, PUBLIC, renderMap, legend, badge, usage, kw, pct, nf1, esc, stateFromUrl, mountSwitcher, icon };
})();
