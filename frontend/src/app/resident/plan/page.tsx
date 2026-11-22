"use client";

/**
 * S3 · Phương án và lịch sạc (mockup cu-dan/resident-plan.html; spec 21 §2.3; FR2, FR3, FR4, FR8, FR9, FR13).
 * Một màn cho cả "duyệt phương án" (?view=draft, từ /resident/book) lẫn "lịch của tôi".
 * Số liệu LUÔN từ dữ liệu có cấu trúc (ScheduleProposal / Booking), không đọc từ câu chữ của LLM (FR3).
 * Xác nhận = POST /resident/bookings kèm Idempotency-Key: bấm hai lần không tạo hai lịch (ADR-008).
 * Luồng chat xác nhận ngay trong Trợ lý ở trang chủ (POST /chat/resume).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState, useSyncExternalStore } from "react";

import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { EmptyState, KeyValues, Notice, PageHead, Panel, PendingAction, SectionHead, Tag } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, newIdempotencyKey, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";
import { clearDraft, type Draft } from "@/lib/booking/draft";
import { formatDate, formatKwh, formatTime, formatVnd } from "@/lib/format";

type Booking = components["schemas"]["Booking"];

const noop = () => () => {};
function useDraft(): Draft | null {
  const raw = useSyncExternalStore(
    noop,
    () => {
      try {
        return sessionStorage.getItem("chargepilot.draft");
      } catch {
        return null;
      }
    },
    () => null,
  );
  return useMemo(() => (raw ? (JSON.parse(raw) as Draft) : null), [raw]);
}

function MutationError({ error, endpoint }: { error: unknown; endpoint: string }) {
  if (!error) return null;
  return (
    <div style={{ marginTop: 12 }}>
      {error instanceof ApiError && error.isNotImplemented ? (
        <NotImplementedPanel endpoint={endpoint} taskId={error.taskId} detail={error.detail} />
      ) : (
        <ErrorPanel error={error} />
      )}
    </div>
  );
}

function DraftView({ draft }: { draft: Draft }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [key] = useState(newIdempotencyKey);
  const p = draft.proposal;
  const confirm = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/resident/bookings", { body: draft.request, params: { header: { "Idempotency-Key": key } } })),
    onSuccess: () => {
      clearDraft();
      void queryClient.invalidateQueries({ queryKey: ["resident"] });
      router.replace("/resident/plan");
    },
  });

  return (
    <div className="cols">
      <div className="stack">
        <Panel label="Phương án sạc">
          <SectionHead
            title="Phương án sạc"
            icon="activity"
            extra={p.feasible ? <Tag tone="good" icon="check">Kịp giờ lấy xe</Tag> : <Tag tone="bad" icon="alert">Chưa kịp giờ lấy xe</Tag>}
          />
          <KeyValues
            rows={[
              ["Đầu nối", p.connector_id ?? (p.queue_position ? `Hàng chờ, vị trí ${p.queue_position}` : "Chờ xếp")],
              ["Bắt đầu", formatTime(p.planned_start)],
              [`Đạt ${draft.request.soc_target}%`, formatTime(p.planned_end)],
              ["Giờ lấy xe", `${formatTime(draft.request.deadline)} · ${formatDate(draft.request.deadline)}`],
              ["Dự phòng", p.slack_minutes != null ? `${p.slack_minutes} phút` : "—"],
              ["Điện vào pin", formatKwh(p.energy.battery_energy_kwh)],
              ["Điện lấy từ lưới", formatKwh(p.energy.grid_energy_kwh)],
              ["Chi phí ước tính", formatVnd(p.estimated_cost_vnd)],
            ]}
          />
          {p.reasons?.length ? (
            <ul className="stack" style={{ gap: 6, margin: "14px 0 0", paddingLeft: 18, fontSize: 13 }}>
              {p.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          ) : null}
          <div className="actions">
            <button type="button" className="btn btn-primary" disabled={!p.feasible || confirm.isPending} onClick={() => confirm.mutate()} aria-describedby="confirm-why">
              <Icon name="check" />
              {confirm.isPending ? "Đang xác nhận…" : "Xác nhận lịch"}
            </button>
            <Link href="/resident/book" className="btn btn-secondary">
              Sửa yêu cầu
            </Link>
          </div>
          {!p.feasible ? (
            <span id="confirm-why" className="hint">
              Chọn một phương án thay thế bên cạnh hoặc sửa yêu cầu.
            </span>
          ) : null}
          <MutationError error={confirm.error} endpoint="POST /api/v1/resident/bookings" />
        </Panel>
      </div>
      <aside className="stack">
        {p.alternatives?.length ? (
          <Panel label="Phương án thay thế">
            <SectionHead title="Phương án thay thế" icon="adjust" />
            <ul className="stack" style={{ gap: 8, listStyle: "none", margin: 0, padding: 0 }}>
              {p.alternatives.map((a) => (
                <li key={a.description} className="notice">
                  <div>
                    <strong>{a.description}</strong>
                    <p className="hint">
                      {a.soc_target != null ? `Mục tiêu ${a.soc_target}%` : ""}
                      {a.deadline ? ` · lấy xe ${formatTime(a.deadline)}` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        ) : null}
        <Notice title="Lịch chỉ được giữ chỗ khi bạn xác nhận" icon="info">
          Phương án tính lúc {formatTime(draft.createdAt)}. Nếu trạm thay đổi trước khi xác nhận, hệ thống sẽ báo để bạn xem phương án mới.
        </Notice>
      </aside>
    </div>
  );
}

function BookingView({ booking }: { booking: Booking }) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const cancel = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/resident/bookings/{booking_id}", { params: { path: { booking_id: booking.booking_id } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["resident"] }),
  });
  return (
    <div className="cols">
      <div className="stack">
        <Panel label="Lịch đã xác nhận">
          <SectionHead title={`Lịch ${booking.booking_id}`} icon="calendar" extra={<Tag tone={booking.status === "queued" ? "gold" : "good"}>{booking.status === "queued" ? "Trong hàng chờ" : booking.status === "charging" ? "Đang sạc" : "Đã xác nhận"}</Tag>} />
          <KeyValues
            rows={[
              ["Đầu nối", booking.connector_id ?? "Chờ xếp"],
              ["Khung sạc", `${formatTime(booking.planned_start)}–${formatTime(booking.planned_end)}`],
              ["Mục tiêu", `${booking.request.soc_now}% → ${booking.request.soc_target}%`],
              ["Giờ lấy xe", `${formatTime(booking.request.deadline)} · ${formatDate(booking.request.deadline)}`],
              ["Điện lấy từ lưới", formatKwh(booking.energy.grid_energy_kwh)],
              ["Chi phí ước tính", formatVnd(booking.estimated_cost_vnd)],
            ]}
          />
          <div className="actions">
            <PendingAction label="Đổi yêu cầu" task="T2.8" icon="adjust" />
            {asking ? (
              <span role="group" aria-label="Xác nhận huỷ" className="actions" style={{ margin: 0 }}>
                <span className="subcopy">Huỷ lịch {booking.booking_id}?</span>
                <button type="button" className="btn btn-secondary" onClick={() => setAsking(false)} autoFocus>
                  Giữ lịch
                </button>
                <button type="button" className="btn btn-danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
                  {cancel.isPending ? "Đang huỷ…" : "Huỷ lịch sạc"}
                </button>
              </span>
            ) : (
              <button type="button" className="btn btn-secondary" onClick={() => setAsking(true)}>
                <Icon name="trash" />
                Huỷ lịch
              </button>
            )}
          </div>
          <MutationError error={cancel.error} endpoint="DELETE /api/v1/resident/bookings/{booking_id}" />
        </Panel>
      </div>
      <aside className="stack">
        <Panel label="Vì sao có lịch này">
          <SectionHead title="Vì sao có lịch này" icon="info" />
          <DataBlock endpoint="GET /api/v1/resident/explanation" query={queries.residentExplanation()} loadingLines={2}>
            {(reasons) =>
              reasons.length ? (
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }} className="stack">
                  {reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              ) : (
                <p className="subcopy">Chưa có giải thích cho lịch này.</p>
              )
            }
          </DataBlock>
        </Panel>
      </aside>
    </div>
  );
}

function PlanScreen() {
  const params = useSearchParams();
  const draft = useDraft();
  const showDraft = params.get("view") === "draft" && draft;
  return (
    <>
      <PageHead
        title={showDraft ? "Phương án sạc" : "Lịch sạc của tôi"}
        sub={showDraft ? "Kiểm tra phương án trước khi giữ chỗ." : "Thời gian, điện năng và chi phí của phiên sạc."}
      />
      {showDraft ? (
        <DraftView draft={draft} />
      ) : (
        <DataBlock endpoint="GET /api/v1/resident/bookings/current" query={queries.residentBooking()}>
          {(booking) =>
            booking ? (
              <BookingView booking={booking} />
            ) : (
              <Panel>
                <EmptyState icon="calendar" title="Chưa có phương án">
                  Đặt lịch bằng biểu mẫu hoặc hỏi Trợ lý sạc ở trang chủ.
                </EmptyState>
                <div className="actions" style={{ justifyContent: "center" }}>
                  <Link href="/resident/book" className="btn btn-primary">
                    Đặt lịch sạc
                  </Link>
                </div>
              </Panel>
            )
          }
        </DataBlock>
      )}
    </>
  );
}

export default function ResidentPlanPage() {
  return (
    <Suspense fallback={<p role="status">Đang tải lịch sạc…</p>}>
      <PlanScreen />
    </Suspense>
  );
}
