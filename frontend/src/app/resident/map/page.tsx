"use client";

/**
 * Sơ đồ bãi · cư dân (mockup cu-dan/resident-map.html; spec 21 §2.8; ADR-010 Proposed).
 * Chỉ lộ xe của chính cư dân; ô của người khác còn "Đang dùng / Trống / Tạm ngưng" (NFR riêng tư).
 * Dữ liệu là FIXTURE cho tới khi backend có G22–G24 (docs/plan/22-ui-work-split.md §9).
 */
import { useSyncExternalStore } from "react";

import { RESIDENT_SNAPSHOT as D, SITE } from "@/components/site-map/fixture";
import { MapLegend, SiteMap } from "@/components/site-map/SiteMap";
import { Notice, PageHead, Panel, SectionHead, Tag } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";

const query = "(max-width: 720px)";
function useNarrow(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

export default function ResidentMapPage() {
  const narrow = useNarrow();
  const free = { AC: 0, DC: 0 };
  SITE.ports.forEach((p) => {
    if (D.ports[p.id]?.status === "idle") free[p.zone] += 1;
  });
  const where = D.mine ? `Xe của bạn ở ô ${SITE.ports.find((p) => p.id === D.mine)?.bay}` : `Xe của bạn ở làn chờ ${D.mineQueue.zone}, vị trí ${D.mineQueue.pos}`;

  return (
    <>
      <PageHead title="Sơ đồ bãi" sub={`${SITE.name} · chỗ của xe bạn và cổng còn trống.`} />
      <Notice title="Dữ liệu minh hoạ" tone="gold" icon="info">
        Sơ đồ theo phương án bãi hybrid AC/DC (ADR-010, chờ duyệt). Trạng thái thật có khi backend xong G22–G24.
      </Notice>
      <div className="cols">
        <div className="stack">
          <Panel label="Khu sạc">
            <SectionHead title={`Khu sạc lúc ${D.clock}`} icon="map" extra={<Tag>Bãi hybrid AC/DC</Tag>} />
            <SiteMap
              layout={narrow ? "portrait" : "landscape"}
              ports={D.ports}
              queues={D.queues}
              privacy
              mine={D.mine}
              mineQueue={D.mineQueue}
              title={`Sơ đồ khu sạc. ${where}. Cổng AC trống ${free.AC} trên 2, cổng DC trống ${free.DC} trên 2.`}
            />
            <MapLegend publicView />
            <p className="hint" style={{ marginTop: 10 }}>
              Bạn chỉ thấy ô nào đang dùng hay còn trống, không thấy xe của cư dân khác.
            </p>
          </Panel>
        </div>
        <aside className="stack">
          <Panel className="hero" label="Xe của bạn">
            <p className="hint">{D.card.eyebrow}</p>
            <p className="metric">{D.card.big}</p>
            <dl className="kv" style={{ marginTop: 12 }}>
              {D.card.rows.map(([k, v]) => (
                <div key={k} style={{ display: "contents" }}>
                  <dt>{k}</dt>
                  <dd className="num">{v}</dd>
                </div>
              ))}
            </dl>
            <p style={{ marginTop: 12 }}>
              <span className="tag tag-gold">
                <Icon name="clock" />
                {D.card.chip}
              </span>
            </p>
          </Panel>
          <Panel label="Cổng còn trống">
            <SectionHead title="Cổng còn trống" icon="plug" />
            <div className="fieldgrid">
              {(["AC", "DC"] as const).map((z) => (
                <div key={z} className="notice" style={{ display: "block" }}>
                  <b className="num" style={{ fontSize: 21 }}>
                    {free[z]}/2
                  </b>
                  <p className="hint">
                    cổng {z} · {z === "AC" ? "11 kW" : "tới 60 kW"} · chờ {D.queues[z].length} xe
                  </p>
                </div>
              ))}
            </div>
          </Panel>
          <Panel label="Đường tới chỗ của bạn">
            <SectionHead title="Đường tới chỗ của bạn" icon="pin" />
            <ol className="stack" style={{ gap: 10, margin: 0, paddingLeft: 20, fontSize: 13 }}>
              {D.steps.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
          </Panel>
        </aside>
      </div>
    </>
  );
}
