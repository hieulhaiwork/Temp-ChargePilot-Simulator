"use client";

/**
 * S5 · Dashboard trạm (mockup docs/mockups/van-hanh/operator.html; spec 21 §3.1; FR16, FR10, FR12 · AC5, AC6 · US5 · MT4).
 * Bố cục theo nhánh buivanlam: 4 KPI · trái: lưới đầu nối + tải 24 giờ · phải: đề nghị cần duyệt + sự kiện.
 * Mọi số đọc từ API (StationOverview, LoadPoint[], StationEvent[]) — không có hằng "35 kW" trong code.
 * Giới hạn hiện hành = state.available_power_kw; nhỏ hơn power_limit_kw nghĩa là nguồn đang giảm (AC5).
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { ConnectorGrid } from "@/components/station/ConnectorGrid";
import { LoadChart } from "@/components/station/LoadChart";
import { StatusLegend, StatusTag } from "@/components/station/status";
import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { KeyValues, Meter, Notice, PageHead, Panel, SectionHead, Tag, type Tone } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";
import { formatKw, formatTime, formatVnd } from "@/lib/format";
import { usePollFallback } from "@/lib/ws/useStream";

type EventType = components["schemas"]["EventType"];
const EVENT: Partial<Record<EventType, [string, Tone]>> = {
  vehicle_arrived: ["Xe đến", "good"],
  vehicle_departed: ["Xe rời", "neutral"],
  booking_created: ["Đặt lịch", "neutral"],
  booking_changed: ["Đổi lịch", "neutral"],
  booking_cancelled: ["Huỷ lịch", "neutral"],
  connector_fault: ["Lỗi", "bad"],
  connector_restored: ["Phục hồi", "good"],
  power_limit_changed: ["Nguồn", "gold"],
  replan_requested: ["Lập lịch", "good"],
};

function ConnectorDetailPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const detail = useQuery({
    queryKey: ["operator", "connector", id],
    queryFn: () => unwrap(api.GET("/api/v1/operator/connectors/{connector_id}", { params: { path: { connector_id: id } } })),
  });
  return (
    <Panel label={`Chi tiết ${id}`}>
      <SectionHead
        title={`Đầu nối ${id}`}
        icon="plug"
        extra={
          <button type="button" className="textbtn" onClick={onClose}>
            Đóng
          </button>
        }
      />
      {detail.isPending ? (
        <p role="status" className="hint">Đang tải…</p>
      ) : detail.isError ? (
        detail.error instanceof ApiError && detail.error.isNotImplemented ? (
          <NotImplementedPanel endpoint="GET /api/v1/operator/connectors/{connector_id}" taskId={detail.error.taskId} />
        ) : (
          <ErrorPanel error={detail.error} onRetry={() => void detail.refetch()} />
        )
      ) : (
        <div className="stack" style={{ gap: 14 }}>
          <KeyValues
            rows={[
              ["Trạng thái", <StatusTag key="s" status={detail.data.state.status} />],
              ["Công suất", `${formatKw(detail.data.state.power_kw)} / ${formatKw(detail.data.state.max_power_kw)}`],
              ["Lịch (mã)", detail.data.booking?.booking_id ?? "—"],
              ["Pin", detail.data.booking ? `${detail.data.booking.request.soc_now}% → ${detail.data.booking.request.soc_target}%` : "—"],
              ["Hạn lấy xe", formatTime(detail.data.booking?.request.deadline)],
            ]}
          />
          <div className="tbl-wrap">
            <table className="tbl">
              <caption>Quyết định gần nhất</caption>
              <thead>
                <tr>
                  <th>Lúc</th>
                  <th>Lệnh</th>
                  <th>Guard</th>
                  <th>Thực thi</th>
                </tr>
              </thead>
              <tbody>
                {(detail.data.recent_decisions ?? []).slice(0, 5).map((d) => (
                  <tr key={d.entry_id ?? d.timestamp}>
                    <td>{formatTime(d.timestamp)}</td>
                    <td>
                      {d.command.type} {d.command.connector_id}
                      {d.command.power_kw != null ? ` = ${formatKw(d.command.power_kw)}` : ""}
                    </td>
                    <td>{d.verdict ? (d.verdict.passed ? <Tag tone="good">Đạt</Tag> : <Tag tone="bad">Chặn</Tag>) : "—"}</td>
                    <td>{d.executed ? "Đã thực thi" : "Không"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">Màn này chỉ xem. Lệnh tới đầu nối do Optimizer đề xuất và Guard kiểm trước khi gửi.</p>
        </div>
      )}
    </Panel>
  );
}

export default function OperatorDashboardPage() {
  const poll = usePollFallback();
  const [paused, setPaused] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  // Tạm dừng: đóng băng phần hiển thị (WCAG 2.2.2); cache vẫn được làm mới khi bấm Tiếp tục.
  const interval = paused ? undefined : poll;

  return (
    <>
      <PageHead
        title="Dashboard trạm"
        sub="Tải, đầu nối và các quyết định của Optimizer + Guard."
        actions={
          <>
            <button type="button" className="btn btn-secondary" aria-pressed={paused} onClick={() => setPaused(!paused)}>
              <Icon name={paused ? "play" : "pause"} />
              {paused ? "Tiếp tục" : "Tạm dừng"}
            </button>
            <Link href="/operator/map" className="btn btn-primary">
              <Icon name="map" />
              Mở sơ đồ bãi
            </Link>
          </>
        }
      />
      {paused ? (
        <Notice title="Đã tạm dừng cập nhật" tone="gold" icon="pause" role="status">
          Màn hình đứng yên để bạn đọc. Bấm Tiếp tục để xem bản mới nhất.
        </Notice>
      ) : null}
      <DataBlock endpoint="GET /api/v1/operator/station" query={queries.operatorStation()} refetchInterval={interval} loadingLines={4}>
        {(o) => {
          const limit = o.state.available_power_kw;
          const load = o.state.connectors.reduce((s, c) => s + c.power_kw, 0);
          const drop = limit < o.power_limit_kw;
          const count = (s: string) => o.state.connectors.filter((c) => c.status === s).length;
          return (
            <>
              {drop ? (
                <Notice title={`Nguồn cấp giảm còn ${formatKw(limit)}`} tone="bad" icon="alert" role="alert">
                  Giới hạn hiện hành thấp hơn cấu hình {formatKw(o.power_limit_kw)}. Tải được phân bổ lại theo giới hạn mới.
                </Notice>
              ) : null}
              {o.alerts?.map((a) => (
                <Notice key={a} title={a} tone="gold" icon="alert" />
              ))}
              <section className="kpis" aria-label="Chỉ số vận hành">
                <Panel className="kpi">
                  <div>
                    <p className="eyebrow">
                      Tải trạm <Tag tone={load / limit >= 0.95 ? "bad" : load / limit >= 0.8 ? "gold" : "good"}>{Math.round((load / Math.max(limit, 1)) * 100)}%</Tag>
                    </p>
                    <p className="v num">
                      {formatKw(load).replace(" kW", "")} <small>/ {formatKw(limit)}</small>
                    </p>
                    <Meter value={load} max={limit} label="Tải trạm so với giới hạn" />
                  </div>
                  <p className="foot">
                    <span>{drop ? `Cấu hình ${formatKw(o.power_limit_kw)}` : "Giới hạn cấu hình"}</span>
                    <b>{formatKw(o.power_limit_kw)}</b>
                  </p>
                </Panel>
                <Panel className="kpi">
                  <div>
                    <p className="eyebrow">Đầu nối</p>
                    <p className="v num">
                      {o.charging_count} <small>đang nạp</small>
                    </p>
                    <p className="hint">
                      {count("idle")} trống · {count("finished")} đã đầy · {count("fault")} lỗi
                    </p>
                  </div>
                  <p className="foot">
                    <span>Hiệu suất sử dụng</span>
                    <b>{Math.round(o.utilization_pct)}%</b>
                  </p>
                </Panel>
                <Panel className="kpi">
                  <div>
                    <p className="eyebrow">
                      Hàng chờ {o.at_risk_booking_ids?.length ? <Tag tone="gold">{o.at_risk_booking_ids.length} nguy cơ trễ</Tag> : null}
                    </p>
                    <p className="v num">
                      {o.queue_length} <small>xe chờ</small>
                    </p>
                  </div>
                  <p className="foot">
                    <span>Chi phí điện hôm nay</span>
                    <b>{formatVnd(o.energy_cost_today_vnd)}</b>
                  </p>
                </Panel>
                <Panel className="kpi" dark>
                  <div>
                    <p className="eyebrow">Optimizer + Guard</p>
                    <p className="v">Lịch v{o.state.schedule_version} đang áp dụng</p>
                    <p className="hint" style={{ color: "#ccdad1" }}>
                      Trạng thái lúc {formatTime(o.state.timestamp)}
                    </p>
                  </div>
                  <p className="foot">
                    <span>So với FCFS</span>
                    <b>{o.cost_vs_fcfs_pct != null ? `${o.cost_vs_fcfs_pct > 0 ? "+" : ""}${Math.round(o.cost_vs_fcfs_pct)}% chi phí` : "—"}</b>
                  </p>
                </Panel>
              </section>
            </>
          );
        }}
      </DataBlock>
      {/* Mỗi khối gọi dữ liệu riêng: station 501 không làm mất biểu đồ, đề nghị hay sự kiện. Cùng query key → không gọi trùng. */}
      <div className="cols">
        <div className="stack">
          <Panel label="Đầu nối">
            <SectionHead title="Đầu nối" icon="grid" extra={<span className="hint">Chọn một ô để xem chi tiết</span>} />
            <DataBlock endpoint="GET /api/v1/operator/station" query={queries.operatorStation()} refetchInterval={interval}>
              {(o) => <ConnectorGrid connectors={o.state.connectors} atRisk={o.at_risk_booking_ids} onSelect={setSelected} />}
            </DataBlock>
            <StatusLegend />
          </Panel>
          {selected ? <ConnectorDetailPanel id={selected} onClose={() => setSelected(null)} /> : null}
          <Panel label="Tải 24 giờ">
            <SectionHead title="Tải 24 giờ so với giới hạn" icon="chart" />
            <DataBlock endpoint="GET /api/v1/operator/load?hours=24" query={queries.operatorLoad(24)} refetchInterval={paused ? undefined : 60_000}>
              {(points) => <LoadChart points={points} />}
            </DataBlock>
          </Panel>
        </div>
        <SideColumn interval={interval} />
      </div>
    </>
  );
}

function SideColumn({ interval }: { interval?: number }) {
  return (
    <aside className="stack">
      <Panel label="Cần duyệt">
        <SectionHead
          title="Cần duyệt"
          icon="shield"
          extra={
            <Link href="/operator/approvals" className="textbtn">
              Mở Duyệt lệnh
              <Icon name="arrow" />
            </Link>
          }
        />
        <DataBlock endpoint="GET /api/v1/operator/approvals" query={queries.operatorApprovals()} refetchInterval={interval} loadingLines={2}>
          {(items) => {
            const pending = items.filter((a) => a.status === "pending");
            return pending.length ? (
              <ul className="stack" style={{ gap: 8, listStyle: "none", margin: 0, padding: 0 }}>
                {pending.slice(0, 3).map((a) => (
                  <li key={a.approval_id} className="notice notice-gold">
                    <div>
                      <strong>
                        {a.command.type} {a.command.connector_id}
                        {a.command.power_kw != null ? ` = ${formatKw(a.command.power_kw)}` : ""}
                      </strong>
                      <p>{a.impact_summary}</p>
                      <p className="hint">{a.kind === "resident_consent" ? "Chờ cư dân trả lời" : `Hết hạn ${formatTime(a.expires_at)}`}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="subcopy">Không có đề nghị nào chờ duyệt.</p>
            );
          }}
        </DataBlock>
      </Panel>
      <Panel label="Sự kiện gần nhất">
        <SectionHead title="Sự kiện gần nhất" icon="activity" />
        <DataBlock endpoint="GET /api/v1/operator/events" query={queries.operatorEvents()} refetchInterval={interval} loadingLines={4}>
          {(events) => {
            const shown = events.filter((e) => e.type !== "tick").slice(0, 8);
            return shown.length ? (
              <ul className="stack" style={{ gap: 0, listStyle: "none", margin: 0, padding: 0 }}>
                {shown.map((e) => {
                  const [label, tone] = EVENT[e.type] ?? ["Sự kiện", "neutral"];
                  return (
                    <li key={e.event_id ?? e.occurred_at} style={{ display: "grid", gridTemplateColumns: "46px 1fr", gap: 10, padding: "10px 0", borderBottom: "1px solid var(--line)", fontSize: 13 }}>
                      <time className="hint">{formatTime(e.occurred_at)}</time>
                      <span>
                        <Tag tone={tone}>{label}</Tag> {e.detail}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="subcopy">Chưa có sự kiện.</p>
            );
          }}
        </DataBlock>
      </Panel>
    </aside>
  );
}
