/**
 * Biểu đồ tải 24 giờ (S5) — SVG tự vẽ, không thêm thư viện: đường tải thực tế + vạch giới hạn theo từng điểm
 * (vạch xuống bậc khi nguồn giảm, AC5). Kèm bảng số liệu tương đương cho trình đọc màn hình.
 */
import type { components } from "@/lib/api/schema";
import { formatKw, formatTime } from "@/lib/format";

type LoadPoint = components["schemas"]["LoadPoint"];

const W = 760;
const H = 250;
const L = 44;
const T = 18;
const B = 34;
const R = 26;
const MIN_LABEL_GAP_PX = 76;

type AxisTick = { key: string; x: number; label: string };

function pickAxisTicks(points: LoadPoint[], xOf: (iso: string) => number): AxisTick[] {
  const first = points[0];
  const firstTick: AxisTick = { key: `${first.timestamp}-0`, x: xOf(first.timestamp), label: formatTime(first.timestamp) };
  if (points.length === 1) return [firstTick];

  const lastIdx = points.length - 1;
  const last = points[lastIdx];
  const lastTick: AxisTick = { key: `${last.timestamp}-${lastIdx}`, x: xOf(last.timestamp), label: formatTime(last.timestamp) };
  if (lastTick.x - firstTick.x < MIN_LABEL_GAP_PX) return [firstTick];

  const out: AxisTick[] = [firstTick];
  for (let i = 1; i < lastIdx; i++) {
    const p = points[i];
    const px = xOf(p.timestamp);
    const label = formatTime(p.timestamp);
    const prev = out[out.length - 1];
    if (
      px - prev.x >= MIN_LABEL_GAP_PX &&
      lastTick.x - px >= MIN_LABEL_GAP_PX &&
      label !== prev.label &&
      label !== lastTick.label
    ) {
      out.push({ key: `${p.timestamp}-${i}`, x: px, label });
    }
  }
  if (lastTick.label !== out[out.length - 1].label) {
    out.push(lastTick);
  }
  return out;
}

export function LoadChart({ points }: { points: LoadPoint[] }) {
  if (points.length === 0) return <p className="subcopy">Chưa có dữ liệu tải trong 24 giờ.</p>;
  const max = Math.max(10, ...points.map((p) => Math.max(p.total_power_kw, p.power_limit_kw))) * 1.15;
  const t0 = new Date(points[0].timestamp).getTime();
  const t1 = new Date(points[points.length - 1].timestamp).getTime();
  const span = Math.max(t1 - t0, 1);
  const x = (iso: string) => L + ((W - L - R) * (new Date(iso).getTime() - t0)) / span;
  const y = (v: number) => T + (H - T - B) * (1 - v / max);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(p.timestamp).toFixed(1)} ${y(p.total_power_kw).toFixed(1)}`).join(" ");
  const limit = points
    .map((p, i) => `${i ? "H" : "M"}${x(p.timestamp).toFixed(1)}${i ? ` V${y(p.power_limit_kw).toFixed(1)}` : ` ${y(p.power_limit_kw).toFixed(1)}`}`)
    .join(" ");
  const last = points[points.length - 1];
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f));
  const xTicks = pickAxisTicks(points, x);

  return (
    <>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="chart"
        role="img"
        aria-label={`Tải trạm 24 giờ. Hiện tại ${formatKw(last.total_power_kw)}, giới hạn ${formatKw(last.power_limit_kw)}. Bảng số liệu ở dưới.`}
        style={{ width: "100%", height: "auto", display: "block" }}
      >
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="#e3e9e1" />
            <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#52655d">
              {v}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t.key} data-axis-tick="x" x={t.x} y={H - 12} textAnchor="middle" fontSize="11" fill="#52655d">
            {t.label}
          </text>
        ))}
        <path d={`${line} L${x(last.timestamp)} ${y(0)} L${L} ${y(0)} Z`} fill="#24654e" opacity="0.12" />
        <path d={line} fill="none" stroke="#24654e" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
        <path d={limit} fill="none" stroke="#963d32" strokeWidth="2.5" strokeDasharray="6 5" />
        <circle cx={x(last.timestamp)} cy={y(last.total_power_kw)} r="6" fill="#24654e" stroke="#fff" strokeWidth="3" />
      </svg>
      <details style={{ marginTop: 8 }}>
        <summary className="textbtn">Bảng số liệu tương đương</summary>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Giờ</th>
                <th className="num">Tải</th>
                <th className="num">Giới hạn</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p, i) => (
                <tr key={`${p.timestamp}-${i}`}>
                  <td>{formatTime(p.timestamp)}</td>
                  <td className="num">{formatKw(p.total_power_kw)}</td>
                  <td className="num">{formatKw(p.power_limit_kw)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
