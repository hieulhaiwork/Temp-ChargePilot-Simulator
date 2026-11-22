"use client";

/**
 * S9 · Sơ đồ bãi · vận hành (mockup docs/mockups/van-hanh/operator-map.html; spec 21 §3.5; ADR-010 Proposed).
 * Mặt bằng bố cục ngang, chọn ô bằng chuột hoặc phím mũi tên + Enter, lọc theo vùng AC/DC.
 * Dữ liệu là FIXTURE cho tới khi backend có G22–G24 (docs/plan/22-ui-work-split.md §9).
 */
import Link from "next/link";
import { useState } from "react";

import { OPERATOR_SNAPSHOT as D, SITE, usage, type Zone } from "@/components/site-map/fixture";
import { BAY_STATUS, MapLegend, SiteMap } from "@/components/site-map/SiteMap";
import { KeyValues, Meter, Notice, PageHead, Panel, SectionHead, Tag } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { formatKw } from "@/lib/format";

const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function OperatorMapPage() {
  const [selected, setSelected] = useState("DC-01-1");
  const [filter, setFilter] = useState<"all" | Zone>("all");
  const u = usage(D.ports);
  const port = SITE.ports.find((p) => p.id === selected) ?? SITE.ports[0];
  const st = D.ports[port.id];
  const busy = Object.values(D.ports).filter((p) => p.veh).length;

  return (
    <>
      <PageHead
        title="Sơ đồ bãi"
        sub={`${SITE.name} · 2 tủ AC × 11 kW, 1 tủ DC × 2 cổng × 60 kW · giờ trạm ${D.clock}`}
        actions={
          <Link href="/operator/schedule" className="btn btn-primary">
            <Icon name="queue" />
            Mở Hàng đợi &amp; lịch
          </Link>
        }
      />
      <Notice title="Dữ liệu minh hoạ · bãi hybrid AC/DC (ADR-010, chờ duyệt)" tone="gold" icon="info">
        Trạng thái thật có khi backend xong G22–G24. Dashboard và các màn khác vẫn theo đầu nối của cấu hình trạm hiện hành.
      </Notice>
      <section className="kpis" aria-label="Công suất theo tầng">
        {(
          [
            ["Đầu vào lưới", u.grid, SITE.gridLimitKw, `= (AC + DC) ÷ ${pct(SITE.conversionEff)} hiệu suất`],
            ["Ngân sách vùng AC", u.AC, SITE.budgets.AC, "Đầu ra tủ AC-01 + AC-02"],
            ["Ngân sách vùng DC", u.DC, SITE.budgets.DC, "2 × 60 kW không có nghĩa là 120 kW cùng lúc"],
          ] as const
        ).map(([label, val, max, foot]) => (
          <Panel key={label} className="kpi">
            <div>
              <p className="eyebrow">{label}</p>
              <p className="v num">
                {formatKw(val).replace(" kW", "")} <small>/ {max} kW</small>
              </p>
              <Meter value={val} max={max} label={label} />
            </div>
            <p className="foot">
              <span>{foot}</span>
            </p>
          </Panel>
        ))}
        <Panel className="kpi">
          <div>
            <p className="eyebrow">Cổng · hàng chờ</p>
            <p className="v num">
              {busy}/4 <small>cổng có xe</small>
            </p>
          </div>
          <p className="foot">
            <span>Chờ AC</span>
            <b>{D.queues.AC.length}</b>
            <span>Chờ DC</span>
            <b>{D.queues.DC.length}</b>
          </p>
        </Panel>
      </section>
      <div className="cols">
        <div className="stack">
          <Panel label="Mặt bằng khu sạc">
            <SectionHead
              title="Mặt bằng khu sạc"
              icon="map"
              extra={
                <div className="seg" role="group" aria-label="Lọc theo vùng">
                  {(
                    [
                      ["all", "Tất cả"],
                      ["AC", "Vùng AC"],
                      ["DC", "Vùng DC"],
                    ] as const
                  ).map(([k, l]) => (
                    <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>
                      {l}
                    </button>
                  ))}
                </div>
              }
            />
            <SiteMap layout="landscape" ports={D.ports} queues={D.queues} filter={filter} selected={selected} onSelect={setSelected} title="Sơ đồ bãi: chọn một ô sạc để xem chi tiết" />
            <MapLegend />
            <details style={{ marginTop: 10 }}>
              <summary className="textbtn">Bảng số liệu tương đương</summary>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Ô</th>
                      <th>Cổng</th>
                      <th>Vùng</th>
                      <th>Trạng thái</th>
                      <th>Xe</th>
                      <th className="num">Công suất</th>
                      <th className="num">Pin</th>
                      <th className="num">Giờ rời</th>
                    </tr>
                  </thead>
                  <tbody>
                    {SITE.ports.map((p) => {
                      const s = D.ports[p.id];
                      return (
                        <tr key={p.id}>
                          <td>{p.bay}</td>
                          <td>{p.id}</td>
                          <td>{p.zone}</td>
                          <td>{BAY_STATUS[s.status].label}</td>
                          <td>{s.veh ?? "—"}</td>
                          <td className="num">
                            {formatKw(s.kw ?? 0)} / {p.limitKw} kW
                          </td>
                          <td className="num">{s.soc != null && s.target != null ? `${pct(s.soc)} → ${pct(s.target)}` : "—"}</td>
                          <td className="num">{s.dep ?? "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </details>
          </Panel>
        </div>
        <aside className="stack">
          <Panel label="Ô đang chọn">
            <p className="hint">Ô đang chọn</p>
            <h2 style={{ fontSize: 19, margin: "2px 0 12px" }} aria-live="polite">
              Ô {port.bay} · cổng {port.id}
            </h2>
            <KeyValues
              rows={[
                ["Trạng thái", <Tag key="t" tone={st.status === "charging" ? "good" : st.status === "fault" ? "bad" : st.status === "idle" ? "neutral" : st.status === "finished" ? "blue" : "gold"}>{BAY_STATUS[st.status].label}</Tag>],
                ["Tủ / vùng", `${port.cabinet} · ${port.zone}`],
                ["Xe", st.veh ?? "—"],
                ["Công suất", `${formatKw(st.kw ?? 0)} / ${port.limitKw} kW`],
                ["Pin", st.soc != null && st.target != null ? `${pct(st.soc)} → ${pct(st.target)}` : "—"],
                ["Dự kiến đạt mục tiêu", st.eta ?? "—"],
                ["Giờ rời khai báo", st.dep ?? "—"],
              ]}
            />
            {st.why ? <p className="subcopy" style={{ marginTop: 12 }}>{st.why}</p> : null}
          </Panel>
          <Panel label="Làn chờ">
            <SectionHead title="Làn chờ theo vùng" icon="queue" sub="FIFO riêng cho AC và DC. Xe AC không xếp vào cổng DC." />
            {(["AC", "DC"] as const).map((z) => (
              <div key={z} style={{ marginTop: 10 }}>
                <h3 style={{ fontSize: 13 }}>
                  Vùng {z} · {D.queues[z].length} xe
                </h3>
                {D.queues[z].length ? (
                  <ol style={{ margin: "6px 0 0", paddingLeft: 20, fontSize: 13 }}>
                    {D.queues[z].map((v) => (
                      <li key={v.veh}>
                        <b>{v.veh}</b> · rời {v.dep} <span className="hint">· vào cổng {v.start}</span>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="subcopy">Không có xe chờ.</p>
                )}
              </div>
            ))}
          </Panel>
          <Panel label="Sự kiện gần nhất">
            <SectionHead title="Sự kiện gần nhất" icon="activity" />
            <ul className="stack" style={{ gap: 8, listStyle: "none", margin: 0, padding: 0, fontSize: 13 }}>
              {D.events.map((e) => (
                <li key={e.at + e.text}>
                  <time className="hint">{e.at}</time> {e.blocked ? <Tag tone="bad" icon="ban">Guard chặn</Tag> : null} {e.text}
                </li>
              ))}
            </ul>
          </Panel>
        </aside>
      </div>
    </>
  );
}
