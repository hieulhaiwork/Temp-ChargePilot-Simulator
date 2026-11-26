"use client";

/**
 * Sơ đồ bãi · cư dân (mockup cu-dan/resident-map.html; spec 21 §2.8; ADR-010).
 * Chỉ lộ xe của chính cư dân; ô của người khác chỉ hiện "Đang dùng / Trống / Tạm ngưng" (NFR riêng tư).
 * Tiêu thụ GET /station/config và GET /resident/site-map (G22, G24).
 */
import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

import { MapLegend, SiteMap, type PortState, type QueueCar, type Zone } from "@/components/site-map/SiteMap";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { PageHead, Panel, SectionHead, Tag } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";

const query = "(max-width: 720px)";
function useNarrow(): boolean {
  return useSyncExternalStore(
    (cb) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => {};
      const m = window.matchMedia(query);
      m.addEventListener?.("change", cb);
      return () => m.removeEventListener?.("change", cb);
    },
    () => (typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(query).matches : false),
    () => false,
  );
}

export default function ResidentMapPage() {
  const narrow = useNarrow();
  const configQuery = useQuery(queries.stationConfig());
  const siteMapQuery = useQuery(queries.residentSiteMap());

  const siteName = configQuery.data?.name ?? "Bãi sạc thông minh";
  const layout = configQuery.data?.layout;
  const configBays = layout?.bays ?? [];
  const isLayoutAvailable = Boolean(layout && configBays.length > 0);

  const isStub = siteMapQuery.error instanceof ApiError && siteMapQuery.error.isNotImplemented;

  const free: Record<Zone, number> = { AC: 0, DC: 0 };
  const ports: Record<string, PortState> = {};
  let mineBayId: string | null = null;
  let minePortId: string | null = null;

  configBays.forEach((b) => {
    const bayData = siteMapQuery.data?.bays?.find((s) => s.bay_id === b.bay_id);
    const pubStatus = bayData?.public_status ?? "idle";
    const isMine = Boolean(bayData?.mine);
    const pId = b.connector_id ?? b.bay_id;

    if (isMine) {
      mineBayId = b.bay_id;
      minePortId = pId;
    }
    if (pubStatus === "idle") {
      free[b.zone] = (free[b.zone] ?? 0) + 1;
    }

    ports[pId] = {
      status: pubStatus === "busy" ? "charging" : pubStatus === "fault" ? "fault" : "idle",
      kw: 0,
      soc: 0,
      veh: isMine ? "VF8" : "",
    };
  });

  const totalBays: Record<Zone, number> = {
    AC: configBays.filter((b) => b.zone === "AC").length,
    DC: configBays.filter((b) => b.zone === "DC").length,
  };

  let mineQueue: { zone: Zone; pos: number } | null = null;
  const queues: Record<Zone, QueueCar[]> = { AC: [], DC: [] };
  if (siteMapQuery.data?.queues) {
    if (siteMapQuery.data.queues.AC) {
      const qAc = siteMapQuery.data.queues.AC;
      queues.AC = Array.from({ length: qAc.length }, () => ({}));
      if (qAc.my_position != null) {
        mineQueue = { zone: "AC", pos: qAc.my_position };
      }
    }
    if (siteMapQuery.data.queues.DC) {
      const qDc = siteMapQuery.data.queues.DC;
      queues.DC = Array.from({ length: qDc.length }, () => ({}));
      if (qDc.my_position != null) {
        mineQueue = { zone: "DC", pos: qDc.my_position };
      }
    }
  }

  const where = mineBayId
    ? `Xe của bạn ở ô ${mineBayId}`
    : mineQueue
      ? `Xe của bạn ở làn chờ ${mineQueue.zone}, vị trí ${mineQueue.pos}`
      : "Xe của bạn chưa vào bãi";

  return (
    <>
      <PageHead title="Sơ đồ bãi" sub={`${siteName} · chỗ của xe bạn và cổng còn trống.`} />
      {isStub ? (
        <div style={{ marginBottom: 16 }}>
          <NotImplementedPanel endpoint="GET /api/v1/resident/site-map" taskId="G24" detail="Sơ đồ đang chờ backend cài đặt hợp đồng G24." />
        </div>
      ) : siteMapQuery.isError ? (
        <div style={{ marginBottom: 16 }}>
          <ErrorPanel error={siteMapQuery.error} />
        </div>
      ) : null}

      <div className="cols">
        <div className="stack">
          <Panel label="Khu sạc">
            <SectionHead title="Khu sạc" icon="map" extra={<Tag>Bãi hybrid AC/DC</Tag>} />
            {!isLayoutAvailable ? (
              <NotImplementedPanel
                endpoint="GET /api/v1/station/config"
                taskId="G22"
                detail="Mặt bằng bãi sạc (layout) chưa được cấu hình từ trạm."
              />
            ) : (
              <>
                <SiteMap
                  layout={narrow ? "portrait" : "landscape"}
                  ports={ports}
                  queues={queues}
                  bays={configBays}
                  privacy
                  mine={minePortId ?? mineBayId}
                  mineQueue={mineQueue}
                  title={`Sơ đồ khu sạc. ${where}. Cổng AC trống ${free.AC} trên ${totalBays.AC}, cổng DC trống ${free.DC} trên ${totalBays.DC}.`}
                />
                <MapLegend publicView />
                <p className="hint" style={{ marginTop: 10 }}>
                  Bạn chỉ thấy ô nào đang dùng hay còn trống, không thấy xe của cư dân khác.
                </p>
              </>
            )}
          </Panel>
        </div>
        <aside className="stack">
          <Panel className="hero" label="Xe của bạn">
            <p className="hint">{minePortId ? "Xe đang ở cổng sạc" : mineQueue ? "Đang trong làn chờ" : "Chưa có xe tại bãi"}</p>
            <p className="metric num">
              {mineBayId ? `Ô ${mineBayId}` : mineQueue ? `Làn ${mineQueue.zone}` : "—"}
            </p>
            {mineBayId ? (
              <p style={{ marginTop: 12 }}>
                <span className="tag tag-gold">
                  <Icon name="check" />
                  Xe của bạn
                </span>
              </p>
            ) : mineQueue ? (
              <p style={{ marginTop: 12 }}>
                <span className="tag tag-gold">
                  <Icon name="clock" />
                  Vị trí {mineQueue.pos}
                </span>
              </p>
            ) : null}
          </Panel>
          <Panel label="Cổng còn trống">
            <SectionHead title="Cổng còn trống" icon="plug" />
            <div className="fieldgrid">
              {(["AC", "DC"] as const).map((z) => {
                const total = totalBays[z] || 0;
                return (
                  <div key={z} className="notice" style={{ display: "block" }}>
                    <b className="num" style={{ fontSize: 21 }}>
                      {free[z]}/{total}
                    </b>
                    <p className="hint">
                      cổng {z} · {z === "AC" ? "11 kW" : "tới 60 kW"} · Cổng {z} trống {free[z]}/{total}
                    </p>
                  </div>
                );
              })}
            </div>
          </Panel>
          <Panel label="Đường tới chỗ của bạn">
            <SectionHead title="Đường tới chỗ của bạn" icon="pin" />
            <ol className="stack" style={{ gap: 10, margin: 0, paddingLeft: 20, fontSize: 13 }}>
              <li>Từ cổng vào, rẽ vào làn đón xe theo biển chỉ dẫn.</li>
              <li>Kiểm tra đúng số ô và cắm đầu nối tương ứng.</li>
              <li>Xác nhận đèn báo trên trụ chuyển sang màu xanh lá.</li>
            </ol>
          </Panel>
        </aside>
      </div>
    </>
  );
}
