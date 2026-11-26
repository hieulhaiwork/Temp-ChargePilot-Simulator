"use client";

/**
 * S9 · Sơ đồ bãi · vận hành (mockup docs/mockups/van-hanh/operator-map.html; spec 21 §3.5; ADR-010 Proposed).
 * Mặt bằng bố cục ngang, chọn ô bằng chuột hoặc phím mũi tên + Enter, lọc theo vùng AC/DC.
 * Tiêu thụ GET /station/config (G22) và GET /operator/station (G23).
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import {
  BAY_STATUS,
  MapLegend,
  SiteMap,
  type PortState,
  type QueueCar,
  type Zone,
} from "@/components/site-map/SiteMap";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { KeyValues, Meter, PageHead, Panel, SectionHead, Tag } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import { formatKw } from "@/lib/format";
import { usePollFallback } from "@/lib/ws/useStream";

const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function OperatorMapPage() {
  const poll = usePollFallback();
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | Zone>("all");

  const configQuery = useQuery(queries.stationConfig());
  const stationQuery = useQuery({
    ...queries.operatorStation(),
    refetchInterval: poll,
  });

  const siteName = configQuery.data?.name ?? "Bãi sạc thông minh";
  const layout = configQuery.data?.layout;
  const configBays = layout?.bays ?? [];
  const connectors = configQuery.data?.connectors ?? [];
  const connectorStates = stationQuery.data?.state.connectors ?? [];

  const isLayoutAvailable = Boolean(layout && configBays.length > 0);

  // Xây dựng ports từ API
  const ports: Record<string, PortState> = {};
  configBays.forEach((b) => {
    const pId = b.connector_id ?? b.bay_id;
    const connState = connectorStates.find((c) => c.connector_id === pId);
    const connSpec = connectors.find((c) => c.connector_id === pId);
    const maxPower = connState?.max_power_kw ?? connSpec?.max_power_kw ?? (b.zone === "AC" ? 11 : 60);

    if (connState) {
      const isThrottled =
        connState.status === "throttled" ||
        (connState.status === "charging" &&
          maxPower > 0 &&
          connState.power_kw < maxPower * 0.9);
      ports[pId] = {
        status:
          connState.status === "fault"
            ? "fault"
            : isThrottled
              ? "throttled"
              : connState.status === "charging"
                ? "charging"
                : connState.status === "finished"
                  ? "finished"
                  : "idle",
        kw: connState.power_kw,
        veh: connState.booking_id ?? "",
      };
    } else {
      ports[pId] = { status: "idle", kw: 0 };
    }
  });

  const selectedBay =
    configBays.find((b) => (b.connector_id ?? b.bay_id) === selected || b.bay_id === selected) ??
    configBays[0];
  const selectedPortId = selectedBay?.connector_id ?? selectedBay?.bay_id ?? "";
  const selectedConnSpec = connectors.find((c) => c.connector_id === selectedPortId);
  const st = ports[selectedPortId] ?? { status: "idle", kw: 0 };
  const busyCount = Object.values(ports).filter((p) => p.status === "charging" || p.status === "throttled" || p.veh).length;

  const gridLimit = stationQuery.data?.grid_input_limit_kw ?? configQuery.data?.power_limit_kw ?? 106;
  const gridInput = stationQuery.data?.grid_input_kw ?? 0;
  const eff = configQuery.data?.power_conversion_efficiency ?? 0.95;

  const acZone = stationQuery.data?.zones?.find((z) => z.zone === "AC");
  const dcZone = stationQuery.data?.zones?.find((z) => z.zone === "DC");
  const acBudget = acZone?.budget_kw ?? configQuery.data?.zone_budgets_kw?.AC ?? 22;
  const dcBudget = dcZone?.budget_kw ?? configQuery.data?.zone_budgets_kw?.DC ?? 78;
  const acUsage = acZone?.output_kw ?? 0;
  const dcUsage = dcZone?.output_kw ?? 0;

  const queues: Record<Zone, QueueCar[]> = { AC: [], DC: [] };

  const isStub =
    (configQuery.error instanceof ApiError && configQuery.error.isNotImplemented) ||
    (stationQuery.error instanceof ApiError && stationQuery.error.isNotImplemented);

  return (
    <>
      <PageHead
        title="Sơ đồ bãi"
        sub={`${siteName} · sơ đồ trạng thái các cổng sạc theo thời gian thực.`}
        actions={
          <Link href="/operator/schedule" className="btn btn-primary">
            <Icon name="queue" />
            Mở Hàng đợi &amp; lịch
          </Link>
        }
      />

      {isStub ? (
        <div style={{ marginBottom: 16 }}>
          <NotImplementedPanel
            endpoint="GET /api/v1/operator/station"
            taskId="T2.8"
            detail="Đang chờ backend hoàn thiện hợp đồng G22 và G23."
          />
        </div>
      ) : stationQuery.isError ? (
        <div style={{ marginBottom: 16 }}>
          <ErrorPanel error={stationQuery.error} />
        </div>
      ) : null}

      <section className="kpis" aria-label="Công suất theo tầng">
        <Panel className="kpi">
          <div>
            <p className="eyebrow">Đầu vào lưới</p>
            <p className="v num">
              {formatKw(gridInput).replace(" kW", "")} <small>/ {gridLimit} kW</small>
            </p>
            <Meter value={gridInput} max={gridLimit} label="Đầu vào lưới" />
          </div>
          <p className="foot">
            <span>= (AC + DC) ÷ {pct(eff)} hiệu suất</span>
          </p>
        </Panel>

        <Panel className="kpi">
          <div>
            <p className="eyebrow">Ngân sách vùng AC</p>
            <p className="v num">
              {formatKw(acUsage).replace(" kW", "")} <small>/ {acBudget} kW</small>
            </p>
            <Meter value={acUsage} max={acBudget} label="Ngân sách vùng AC" />
          </div>
          <p className="foot">
            <span>Đầu ra tủ AC-01 + AC-02</span>
          </p>
        </Panel>

        <Panel className="kpi">
          <div>
            <p className="eyebrow">Ngân sách vùng DC</p>
            <p className="v num">
              {formatKw(dcUsage).replace(" kW", "")} <small>/ {dcBudget} kW</small>
            </p>
            <Meter value={dcUsage} max={dcBudget} label="Ngân sách vùng DC" />
          </div>
          <p className="foot">
            <span>Tối đa theo trần công suất DC</span>
          </p>
        </Panel>

        <Panel className="kpi">
          <div>
            <p className="eyebrow">Cổng · hàng chờ</p>
            <p className="v num">
              {busyCount}/{configBays.length || 4} <small>cổng có xe</small>
            </p>
          </div>
          <p className="foot">
            <span>Hàng chờ</span>
            <b>{stationQuery.data?.queue_length ?? 0} xe</b>
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
            {!isLayoutAvailable ? (
              <NotImplementedPanel
                endpoint="GET /api/v1/station/config"
                taskId="G22"
                detail="Mặt bằng bãi sạc (layout) chưa được cấu hình từ trạm."
              />
            ) : (
              <>
                <SiteMap
                  layout="landscape"
                  ports={ports}
                  queues={queues}
                  filter={filter}
                  bays={configBays}
                  selected={selectedPortId}
                  onSelect={setSelected}
                  title="Sơ đồ bãi: chọn một ô sạc để xem chi tiết"
                />
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
                        </tr>
                      </thead>
                      <tbody>
                        {configBays.map((b) => {
                          const pId = b.connector_id ?? b.bay_id;
                          const s = ports[pId];
                          const cSpec = connectors.find((c) => c.connector_id === pId);
                          const limit = cSpec?.max_power_kw ?? (b.zone === "AC" ? 11 : 60);
                          return (
                            <tr
                              key={b.bay_id}
                              className={pId === selectedPortId ? "sel" : ""}
                              style={{ cursor: "pointer" }}
                              onClick={() => setSelected(pId)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  setSelected(pId);
                                }
                              }}
                              tabIndex={0}
                              role="button"
                              aria-label={`Chọn ô ${b.bay_id}`}
                            >
                              <td>
                                <strong>{b.bay_id}</strong>
                              </td>
                              <td>{pId}</td>
                              <td>{b.zone}</td>
                              <td>{BAY_STATUS[s?.status ?? "idle"]?.label ?? "Trống"}</td>
                              <td>{s?.veh || "—"}</td>
                              <td className="num">
                                {formatKw(s?.kw ?? 0)} / {limit} kW
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </details>
              </>
            )}
          </Panel>
        </div>

        <aside className="stack">
          <Panel label="Ô đang chọn">
            <p className="hint">Ô đang chọn</p>
            <h2 style={{ fontSize: 19, margin: "2px 0 12px" }} aria-live="polite">
              {selectedBay ? `Ô ${selectedBay.bay_id} · cổng ${selectedPortId}` : "Chưa chọn ô"}
            </h2>
            {selectedBay ? (
              <KeyValues
                rows={[
                  [
                    "Trạng thái",
                    <Tag
                      key="t"
                      tone={
                        st.status === "charging"
                          ? "good"
                          : st.status === "fault"
                            ? "bad"
                            : st.status === "idle"
                              ? "neutral"
                              : st.status === "finished"
                                ? "blue"
                                : "gold"
                      }
                    >
                      {BAY_STATUS[st.status]?.label ?? "Trống"}
                    </Tag>,
                  ],
                  ["Tủ / vùng", `${selectedConnSpec?.cabinet_id ?? (selectedBay.zone === "AC" ? "AC-01" : "DC-01")} · ${selectedBay.zone}`],
                  ["Lịch / Xe", st.veh || "—"],
                  ["Công suất", `${formatKw(st.kw ?? 0)} / ${selectedConnSpec?.max_power_kw ?? (selectedBay.zone === "AC" ? 11 : 60)} kW`],
                ]}
              />
            ) : null}
          </Panel>
        </aside>
      </div>
    </>
  );
}
