"use client";

/**
 * S6 · Hàng đợi & lịch (mockup docs/mockups/van-hanh/operator-schedule.html; spec 21 §3.2; FR6, FR7, FR8, FR12, FR16 · US6 · AC2 · MT5).
 * Gantt theo đầu nối dựng từ SchedulePlan.sessions[].slots (mỗi slot dài step_minutes), kèm bảng số liệu tương đương.
 * Lệnh của vận hành vẫn đi qua Guard: "Xếp thủ công" trả DecisionLogEntry cho biết được áp, chờ duyệt hay bị chặn.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { EmptyState, Notice, PageHead, Panel, SectionHead, Tag } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";
import { formatKw, formatTime } from "@/lib/format";
import { policyOf } from "@/lib/policies";
import { usePollFallback } from "@/lib/ws/useStream";

type Plan = components["schemas"]["SchedulePlan"];
type Booking = components["schemas"]["Booking"];
type Decision = components["schemas"]["DecisionLogEntry"];

function MutationError({ error, endpoint }: { error: unknown; endpoint: string }) {
  if (!error) return null;
  return error instanceof ApiError && error.isNotImplemented ? (
    <NotImplementedPanel endpoint={endpoint} taskId={error.taskId} detail={error.detail} />
  ) : (
    <ErrorPanel error={error} />
  );
}

function Gantt({ plan, connectorIds }: { plan: Plan; connectorIds: string[] }) {
  const sessions = plan.sessions ?? [];
  if (sessions.length === 0) {
    return (
      <EmptyState icon="calendar" title={`Chưa có phiên nào trong lịch v${plan.version}`}>
        Bấm “Lập lịch lại” khi có xe mới.
      </EmptyState>
    );
  }
  const start = new Date(plan.horizon_start).getTime();
  const stepMs = plan.step_minutes * 60_000;
  const slots = sessions.flatMap((s) => (s.slots ?? []).map((sl) => ({ ...sl, booking: s.booking_id, connector: s.connector_id ?? "—" })));
  const end = Math.max(start + 12 * 3600_000, ...slots.map((s) => new Date(s.start).getTime() + stepMs));
  const span = end - start;
  const pos = (t: number) => `${(((t - start) / span) * 100).toFixed(2)}%`;
  const hours = Array.from({ length: Math.floor(span / 3600_000) + 1 }, (_, i) => start + i * 3600_000);
  const rows = Array.from(new Set([...connectorIds, ...slots.map((s) => s.connector)]));
  const maxKw = Math.max(...slots.map((s) => s.power_kw), 1);

  return (
    <>
      <div className="tbl-wrap">
        <div className="gantt" role="img" aria-label={`Lịch v${plan.version}: ${sessions.length} phiên trên ${rows.length} đầu nối. Bảng số liệu ở dưới.`}>
          <div />
          <div className="gh" aria-hidden="true">
            {hours.map((h) => (
              <span key={h} style={{ left: pos(h) }}>
                {formatTime(new Date(h).toISOString())}
              </span>
            ))}
          </div>
          {rows.map((c) => (
            <div key={c} style={{ display: "contents" }}>
              <div className="gl">{c}</div>
              <div className="gt">
                {slots
                  .filter((s) => s.connector === c)
                  .map((s) => {
                    const t = new Date(s.start).getTime();
                    const reduced = s.power_kw < maxKw * 0.9;
                    return (
                      <span
                        key={`${s.booking}-${s.start}`}
                        className={`gb ${reduced ? "reduced" : "full"}`}
                        style={{ left: pos(t), width: `calc(${pos(t + stepMs)} - ${pos(t)})` }}
                        title={`${s.booking} · ${formatTime(s.start)} · ${formatKw(s.power_kw)}`}
                      />
                    );
                  })}
              </div>
            </div>
          ))}
        </div>
      </div>
      <p className="legend-row">
        <span>
          <span className="gb-sw full" />
          Đủ công suất
        </span>
        <span>
          <span className="gb-sw reduced" />
          Giảm công suất
        </span>
      </p>
      <details style={{ marginTop: 8 }}>
        <summary className="textbtn">Bảng số liệu tương đương</summary>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Lịch (mã)</th>
                <th>Đầu nối</th>
                <th>Bắt đầu</th>
                <th>Kết thúc</th>
                <th className="num">Số khung {plan.step_minutes} phút</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => {
                const sl = s.slots ?? [];
                return (
                  <tr key={s.booking_id}>
                    <td>{s.booking_id}</td>
                    <td>{s.connector_id ?? "—"}</td>
                    <td>{formatTime(sl[0]?.start)}</td>
                    <td>{sl.length ? formatTime(new Date(new Date(sl[sl.length - 1].start).getTime() + stepMs).toISOString()) : "—"}</td>
                    <td className="num">{sl.length}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}

function AssignResult({ entry }: { entry: Decision }) {
  if (entry.verdict && !entry.verdict.passed) {
    const v = entry.verdict.violations?.[0];
    return (
      <Notice title={`Guard chặn${v ? `: ${v.rule}` : ""}`} tone="bad" icon="ban" role="alert">
        {v?.detail ?? "Lệnh không được gửi tới trạm."}
      </Notice>
    );
  }
  if (entry.approval_id && !entry.executed) {
    return (
      <Notice title="Chờ duyệt" tone="gold" icon="shield" role="status">
        Guard cho qua nhưng cần người duyệt. <Link href="/operator/approvals" className="textbtn">Mở Duyệt lệnh</Link>
      </Notice>
    );
  }
  return (
    <Notice title={`Đã xếp ${entry.command.booking_id ?? ""} vào ${entry.command.connector_id}`} tone="good" icon="checkcircle" role="status">
      Guard đạt · {entry.executed ? "đã thực thi" : "chưa thực thi"} lúc {formatTime(entry.timestamp)}.
    </Notice>
  );
}

function QueueItem({ booking, index, connectorIds }: { booking: Booking; index: number; connectorIds: string[] }) {
  const queryClient = useQueryClient();
  const [to, setTo] = useState(connectorIds[0] ?? "");
  const assign = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/operator/bookings/{booking_id}/assignments", { params: { path: { booking_id: booking.booking_id } }, body: { connector_id: to } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["operator"] }),
  });
  return (
    <li className="queue-item">
      <h3>
        <span>
          {index + 1}. {booking.booking_id}
        </span>
        <span style={{ display: "inline-flex", gap: 6 }}>
          <Tag tone={booking.status === "charging" ? "good" : booking.status === "confirmed" ? "gold" : "neutral"}>
            {booking.status === "charging" ? "Đang sạc" : booking.status === "confirmed" ? "Đã chốt" : "Chờ xếp"}
          </Tag>
          <Tag>{booking.request.vehicle_model}</Tag>
        </span>
      </h3>
      <p className="hint">
        {booking.request.soc_now}% → {booking.request.soc_target}% · hạn {formatTime(booking.request.deadline)} · dự kiến bắt đầu {formatTime(booking.planned_start)}
      </p>
      <div className="assign">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`to-${booking.booking_id}`}>Xếp vào đầu nối</label>
          <select id={`to-${booking.booking_id}`} value={to} onChange={(e) => setTo(e.target.value)} disabled={assign.isPending}>
            {connectorIds.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
        <button type="button" className="btn btn-primary small" disabled={assign.isPending || !to} onClick={() => assign.mutate()}>
          {assign.isPending ? "Đang gửi…" : "Xếp thủ công"}
        </button>
      </div>
      {assign.data ? <AssignResult entry={assign.data} /> : null}
      <MutationError error={assign.error} endpoint="POST /api/v1/operator/bookings/{booking_id}/assignments" />
    </li>
  );
}

export default function OperatorSchedulePage() {
  const poll = usePollFallback();
  const queryClient = useQueryClient();
  const config = useQuery(queries.stationConfig());
  const connectorIds = config.data?.connectors.map((c) => c.connector_id) ?? [];
  const replan = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/operator/schedule/replans")),
    onSuccess: (plan) => queryClient.setQueryData(queries.operatorSchedule().queryKey, plan),
  });

  return (
    <>
      <PageHead
        title="Hàng đợi & lịch"
        sub={config.data ? `${config.data.name} · ${connectorIds.length} đầu nối · bước ${config.data.step_minutes} phút` : "Lịch công suất theo đầu nối và xe đang chờ."}
        actions={
          <button type="button" className="btn btn-primary" disabled={replan.isPending} onClick={() => replan.mutate()}>
            <Icon name="refresh" />
            {replan.isPending ? "Đang lập lịch lại…" : "Lập lịch lại"}
          </button>
        }
      />
      {replan.data ? (
        <Notice title={`Đã tính lại: lịch v${replan.data.version}`} tone="good" icon="checkcircle" role="status">
          {replan.data.solve_time_s != null ? `Thời gian tính ${replan.data.solve_time_s.toLocaleString("vi-VN")} giây.` : null}
        </Notice>
      ) : null}
      <MutationError error={replan.error} endpoint="POST /api/v1/operator/schedule/replans" />
      <div className="cols">
        <div className="stack">
          <Panel label="Lịch công suất">
            <DataBlock endpoint="GET /api/v1/operator/schedule" query={queries.operatorSchedule()} refetchInterval={poll} loadingLines={6}>
              {(plan) => (
                <>
                  <SectionHead
                    title="Lịch công suất theo đầu nối"
                    icon="calendar"
                    extra={<Tag tone="good">{`Lịch v${plan.version} · ${policyOf(plan)} · tính lúc ${formatTime(plan.created_at)}`}</Tag>}
                  />
                  <Gantt plan={plan} connectorIds={connectorIds} />
                </>
              )}
            </DataBlock>
          </Panel>
        </div>
        <aside className="stack">
          <Panel label="Hàng đợi xe chờ">
            <SectionHead title="Hàng đợi & danh sách xe" icon="queue" sub="Lệnh xếp thủ công vẫn đi qua Guard." />
            <DataBlock
              endpoint="GET /api/v1/operator/bookings?status=queued,confirmed,charging"
              query={queries.operatorQueue(["queued", "confirmed", "charging"])}
              refetchInterval={poll}
              loadingLines={4}
            >
              {(queue) =>
                queue.length ? (
                  <ul style={{ listStyle: "none", margin: 0, padding: 0 }} className="stack">
                    {queue.map((b, i) => (
                      <QueueItem key={b.booking_id} booking={b} index={i} connectorIds={connectorIds} />
                    ))}
                  </ul>
                ) : (
                  <EmptyState icon="checkcircle" title="Không có xe chờ">
                    Mọi yêu cầu đã có đầu nối.
                  </EmptyState>
                )
              }
            </DataBlock>
          </Panel>
        </aside>
      </div>
    </>
  );
}
