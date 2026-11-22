/**
 * FIXTURE cho S9 Sơ đồ bãi — chép từ docs/mockups/cu-dan/assets/site-map.js (topology ADR-010, kịch bản
 * evening_9cars_hybrid_v1 của MVP-1 starter). Mọi số là MINH HOẠ. Bỏ file này khi backend có G22 (layout trong
 * GET /station/config) và G23–G24 (trạng thái theo cổng) — docs/plan/22-ui-work-split.md §9.
 */
export type Zone = "AC" | "DC";
export type BayStatus = "charging" | "throttled" | "idle" | "finished" | "fault";

export type Port = { id: string; cabinet: string; zone: Zone; bay: string; limitKw: number };
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
export type QueueCar = { veh?: string; dep?: string; start?: string };
export type Rect = { x: number; y: number; w: number; h: number };

export const SITE = {
  name: "Bãi sạc khu cư dân CP-01",
  gridLimitKw: 106,
  conversionEff: 0.95,
  budgets: { AC: 22, DC: 78 } as Record<Zone, number>,
  cabinets: [
    { id: "AC-01", zone: "AC" as Zone, ports: 1, portLimitKw: 11 },
    { id: "AC-02", zone: "AC" as Zone, ports: 1, portLimitKw: 11 },
    { id: "DC-01", zone: "DC" as Zone, ports: 2, portLimitKw: 60 },
  ],
  ports: [
    { id: "AC-01-1", cabinet: "AC-01", zone: "AC", bay: "B-A1", limitKw: 11 },
    { id: "AC-02-1", cabinet: "AC-02", zone: "AC", bay: "B-A2", limitKw: 11 },
    { id: "DC-01-1", cabinet: "DC-01", zone: "DC", bay: "B-D1", limitKw: 60 },
    { id: "DC-01-2", cabinet: "DC-01", zone: "DC", bay: "B-D2", limitKw: 60 },
  ] as Port[],
};

export type Gate = { x: number; label: string; dir: "in" | "out" };
export type Layout = {
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

export const LAYOUTS: Record<"landscape" | "portrait", Layout> = {
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

export type ScenarioData = {
  id: string;
  name: string;
  clock: string;
  alert: { title: string; body: string } | null;
  selected: string;
  ports: Record<string, PortState>;
  queues: Record<Zone, QueueCar[]>;
  events: { at: string; text: string; blocked: boolean }[];
};

export const SCENARIOS: Record<string, ScenarioData> = {
  peak: {
    id: "peak",
    name: "18:30 · Cao điểm tối",
    clock: "18:30",
    alert: null,
    selected: "DC-01-1",
    ports: {
      "AC-01-1": { status: "charging", veh: "AC-A", kw: 11, soc: 0.49, target: 0.65, dep: "20:00", eta: "19:28" },
      "AC-02-1": { status: "charging", veh: "AC-B", kw: 11, soc: 0.58, target: 0.7, dep: "20:15", eta: "19:18" },
      "DC-01-1": { status: "throttled", veh: "DC-A", kw: 39, soc: 0.45, target: 0.75, dep: "21:30", eta: "19:12", why: "Chia đều ngân sách DC (78 kW) cho 2 cổng (tối đa cổng 60 kW)." },
      "DC-01-2": { status: "throttled", veh: "DC-B", kw: 39, soc: 0.62, target: 0.7, dep: "21:30", eta: "18:39", why: "Chia đều ngân sách DC (78 kW) cho 2 cổng." },
    },
    queues: {
      AC: [{ veh: "AC-C", dep: "22:15", start: "~20:00" }, { veh: "AC-D", dep: "23:30", start: "~20:15" }],
      DC: [{ veh: "DC-C", dep: "20:00", start: "~19:44" }, { veh: "DC-D", dep: "22:00", start: "~19:12" }, { veh: "DC-E", dep: "22:30", start: "~19:40" }],
    },
    events: [
      { at: "18:25", text: "Guard chặn set_power DC-01-1 = 45 kW (tổng DC 84 kW vượt ngân sách 78 kW)", blocked: true },
      { at: "18:15", text: "Lập lịch lại: 2 cổng DC giữ 39 kW mỗi cổng", blocked: false },
      { at: "18:00", text: "9 xe tới cùng lúc: 4 xe vào cổng, 5 xe vào làn chờ (AC 2, DC 3)", blocked: false },
    ],
  },
  turnover: {
    id: "turnover",
    name: "20:10 · Xe đổi ca",
    clock: "20:10",
    alert: null,
    selected: "AC-02-1",
    ports: {
      "AC-01-1": { status: "charging", veh: "AC-C", kw: 11, soc: 0.33, target: 0.65, dep: "23:15", eta: "22:16" },
      "AC-02-1": { status: "finished", veh: "AC-B", kw: 0, soc: 0.7, target: 0.7, dep: "20:15", why: "Đã đầy lúc 19:18. Cổng AC giữ tới giờ rời đã khai báo (20:15)." },
      "DC-01-1": { status: "charging", veh: "DC-E", kw: 48, soc: 0.71, target: 0.85, dep: "22:30", eta: "20:27", why: "Giảm dần theo mức pin (taper charging)." },
      "DC-01-2": { status: "finished", veh: "DC-D", kw: 0, soc: 0.65, target: 0.65, dep: "22:00", why: "Đã đầy lúc 20:07 · DC rút sau 5 phút (còn 2 phút)." },
    },
    queues: {
      AC: [{ veh: "AC-D", dep: "23:30", start: "~20:15" }],
      DC: [],
    },
    events: [
      { at: "20:07", text: "DC-D đạt 65%, cổng DC-01-2 chờ rút 5 phút", blocked: false },
      { at: "20:00", text: "AC-A rời ô B-A1 theo giờ khai báo. AC-C vào AC-01-1", blocked: false },
      { at: "19:18", text: "AC-B đạt 70%. Cổng AC-02-1 chưa giải phóng (chờ 20:15)", blocked: false },
    ],
  },
  fault: {
    id: "fault",
    name: "19:05 · Sự cố DC-01-2",
    clock: "19:05",
    alert: { title: "Cổng DC-01-2 lỗi", body: "18 kW ngân sách DC không dùng được. DC-D đang chờ chuyển cổng; đề nghị đã nằm ở Duyệt lệnh." },
    selected: "DC-01-2",
    ports: {
      "AC-01-1": { status: "charging", veh: "AC-A", kw: 11, soc: 0.6, target: 0.65, dep: "20:00", eta: "19:28" },
      "AC-02-1": { status: "charging", veh: "AC-B", kw: 11, soc: 0.68, target: 0.7, dep: "20:15", eta: "19:18" },
      "DC-01-1": { status: "charging", veh: "DC-C", kw: 60, soc: 0.58, target: 0.75, dep: "22:00", eta: "19:20", why: "Một cổng DC còn chạy: lên tối đa cổng 60 kW." },
      "DC-01-2": { status: "fault", veh: "DC-D", kw: 0, soc: 0.31, target: 0.65, dep: "22:00", why: "Mất liên lạc với cổng lúc 19:02. Phiên dừng, Guard chặn mọi lệnh tới cổng này." },
    },
    queues: {
      AC: [{ veh: "AC-C", dep: "23:15", start: "~20:00" }, { veh: "AC-D", dep: "23:30", start: "~20:15" }],
      DC: [{ veh: "DC-E", dep: "22:30", start: "~19:25" }],
    },
    events: [
      { at: "19:03", text: "Đề nghị chờ duyệt: chuyển DC-D sang DC-01-1 sau DC-C (≈ 19:25)", blocked: false },
      { at: "19:02", text: "Guard chặn set_power DC-01-2: đầu nối ở trạng thái lỗi", blocked: true },
      { at: "19:02", text: "DC-01-2 báo lỗi: mất liên lạc với cổng", blocked: true },
    ],
  },
};

/** Vận hành · 18:30 cao điểm tối (mockup van-hanh/operator-map.html, kịch bản "peak"). */
export const OPERATOR_SNAPSHOT = {
  clock: "18:30",
  ports: {
    "AC-01-1": { status: "charging", veh: "AC-A", kw: 11, soc: 0.49, target: 0.65, dep: "20:00", eta: "19:28" },
    "AC-02-1": { status: "charging", veh: "AC-B", kw: 11, soc: 0.58, target: 0.7, dep: "20:15", eta: "19:18" },
    "DC-01-1": { status: "throttled", veh: "DC-A", kw: 39, soc: 0.45, target: 0.75, dep: "21:30", eta: "19:12", why: "Chia đều ngân sách DC 78 kW cho 2 cổng (tối đa cổng 60 kW)." },
    "DC-01-2": { status: "throttled", veh: "DC-B", kw: 39, soc: 0.62, target: 0.7, dep: "21:30", eta: "18:39", why: "Chia đều ngân sách DC 78 kW cho 2 cổng." },
  } as Record<string, PortState>,
  queues: {
    AC: [{ veh: "AC-C", dep: "23:15", start: "~20:00" }, { veh: "AC-D", dep: "23:30", start: "~20:15" }],
    DC: [{ veh: "DC-C", dep: "22:00", start: "~18:44" }, { veh: "DC-D", dep: "22:00", start: "~19:17" }, { veh: "DC-E", dep: "22:30", start: "~19:40" }],
  } as Record<Zone, QueueCar[]>,
  events: [
    { at: "18:25", text: "Guard chặn set_power DC-01-1 = 45 kW: tổng DC 84 kW vượt ngân sách 78 kW", blocked: true },
    { at: "18:15", text: "Lập lịch lại: 2 cổng DC giữ 39 kW mỗi cổng", blocked: false },
    { at: "18:00", text: "9 xe tới cùng lúc: 4 xe vào cổng, 5 xe vào làn chờ (AC 2, DC 3)", blocked: false },
  ],
};

/** Cư dân · 18:30 đang chờ ở làn AC vị trí 1 (mockup cu-dan/resident-map.html, kịch bản "queued"). */
export const RESIDENT_SNAPSHOT = {
  clock: "18:30",
  ports: {
    "AC-01-1": { status: "charging" },
    "AC-02-1": { status: "charging" },
    "DC-01-1": { status: "throttled" },
    "DC-01-2": { status: "throttled" },
  } as Record<string, PortState>,
  queues: { AC: [{}, {}], DC: [{}, {}, {}] } as Record<Zone, QueueCar[]>,
  mine: null as string | null,
  mineQueue: { zone: "AC" as Zone, pos: 1 },
  card: {
    eyebrow: "Xe của bạn · vùng AC",
    big: "Chờ vị trí 1",
    rows: [
      ["Dự kiến vào cổng", "~20:00"],
      ["Đạt 65%", "~22:16"],
      ["Lấy xe", "23:15"],
    ],
    chip: "Dự phòng 59 phút",
  },
  steps: [
    "Vào bằng Lối vào phía đường nội khu.",
    "Đi thẳng tới Làn chờ AC, đỗ ở vạch số 1.",
    "Ứng dụng báo khi một cổng AC trống. Bạn có 10 phút để chuyển xe vào ô.",
  ],
};

export function usage(ports: Record<string, PortState>) {
  const out: Record<Zone, number> = { AC: 0, DC: 0 };
  for (const p of SITE.ports) out[p.zone] += ports[p.id]?.kw ?? 0;
  const eff = SITE.conversionEff > 0 ? SITE.conversionEff : 1;
  return { ...out, grid: (out.AC + out.DC) / eff };
}
