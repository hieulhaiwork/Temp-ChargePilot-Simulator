"use client";

/**
 * S3 · Phương án và lịch sạc (mockup cu-dan/resident-plan.html; spec 21 §2.3; FR2, FR3, FR4, FR8, FR9, FR13).
 * Một màn cho cả "duyệt phương án" (?view=draft, từ /resident/book) lẫn "lịch của tôi".
 * Số liệu LUÔN từ dữ liệu có cấu trúc (ScheduleProposal / Booking), không đọc từ câu chữ của LLM (FR3).
 * Xác nhận = POST /resident/bookings kèm Idempotency-Key: bấm hai lần không tạo hai lịch (ADR-008).
 * Luồng chat xác nhận ngay trong Trợ lý ở trang chủ (PATCH /chat/sessions/{session_id}).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState, useSyncExternalStore } from "react";

import { ChangeBookingDialog } from "@/components/resident/ChangeBookingDialog";
import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { EmptyState, KeyValues, Notice, PageHead, Panel, SectionHead, Tag } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, newIdempotencyKey, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";
import { clearDraft, type Draft } from "@/lib/booking/draft";
import {
  computeBufferMinutes,
  formatDate,
  formatDuration,
  formatKwh,
  formatTime,
  formatViNumbers,
  formatVnd,
} from "@/lib/format";
import { useVehicleName } from "@/lib/vehicles";

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

function isPeakStart(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const hhmm = formatTime(iso);
  if (hhmm === "—") return false;
  const [h, m] = hhmm.split(":").map(Number);
  const mins = (h || 0) * 60 + (m || 0);
  // Khung giờ cao điểm theo config/tariff.yaml: 09:30–11:30 và 17:00–20:00
  return (mins >= 9 * 60 + 30 && mins < 11 * 60 + 30) || (mins >= 17 * 60 && mins < 20 * 60);
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

  const bufferMinutes = computeBufferMinutes(p.planned_end, draft.request.deadline, p.slack_minutes);
  const isDcZone = draft.request.zone === "DC" || Boolean(p.connector_id?.toUpperCase().startsWith("DC"));
  const excessiveDcIdle = Boolean(p.feasible && isDcZone && bufferMinutes != null && bufferMinutes >= 120);
  const longDwellDuringPeak = Boolean(
    p.feasible && bufferMinutes != null && bufferMinutes >= 120 && isPeakStart(p.planned_start),
  );
  const formattedReasons = (p.reasons ?? []).map(formatViNumbers);
  const formattedAssumptions = (p.assumptions ?? []).map(formatViNumbers);

  return (
    <div className="cols">
      <div className="stack">
        <Panel label="Phương án sạc">
          <SectionHead
            title="Phương án sạc"
            icon="activity"
            extra={
              <>
                {p.feasible ? <Tag tone="good" icon="check">Ước tính kịp giờ lấy xe</Tag> : <Tag tone="bad" icon="alert">Chưa kịp giờ lấy xe</Tag>}
                {p.certainty === "conditional" ? (
                  <Tag tone="gold" icon="alert">
                    Phụ thuộc phê duyệt
                  </Tag>
                ) : null}
              </>
            }
          />
          {p.certainty === "conditional" ? (
            <div style={{ marginBottom: 12 }} data-testid="proposal-conditional">
              <Notice title="Phương án có thể thay đổi khi duyệt yêu cầu đang chờ" tone="gold" icon="alert">
                {p.approvals_pending_for_booking ? `Có ${p.approvals_pending_for_booking} đề xuất điều chỉnh của xe bạn đang chờ bạn xác nhận. ` : ""}
                {p.approvals_pending_for_others ? `Có ${p.approvals_pending_for_others} điều chỉnh của xe khác đang chờ duyệt. ` : ""}
                Khi các yêu cầu đó được duyệt hoặc từ chối, khung giờ sạc có thể được cập nhật lại.
              </Notice>
            </div>
          ) : null}
          {excessiveDcIdle ? (
            <div style={{ marginBottom: 12 }} data-testid="dc-idle-warning">
              <Notice title="Cảnh báo đỗ lâu tại trụ sạc nhanh DC" tone="gold" icon="alert">
                Xe dự kiến đạt {draft.request.soc_target}% lúc {formatTime(p.planned_end)}, sớm hơn{" "}
                <strong>{formatDuration(bufferMinutes)}</strong> so với giờ lấy xe ({formatTime(draft.request.deadline)}{" "}
                · {formatDate(draft.request.deadline)}). Trụ sạc nhanh DC cần nhường chỗ sớm sau khi sạc xong (thường
                rút cáp sau 5 phút). Bạn nên{" "}
                <Link href="/resident/book" className="textbtn">
                  đổi sang trụ AC (sạc qua đêm) hoặc chọn giờ lấy xe sớm hơn
                </Link>
                .
              </Notice>
            </div>
          ) : null}
          {longDwellDuringPeak ? (
            <div style={{ marginBottom: 12 }} data-testid="smart-delay-hint">
              <Notice title="Gợi ý tiết kiệm chi phí điện" tone="neutral" icon="bolt">
                Xe đang bắt đầu sạc trong khung giờ cao điểm (3.500 ₫/kWh) dù bạn có tới{" "}
                <strong>{formatDuration(bufferMinutes)}</strong> dự phòng. Bạn có thể hẹn giờ cắm từ 22:00 (giá thấp
                điểm 1.200 ₫/kWh) hoặc bật cho phép lùi giờ bắt đầu trong{" "}
                <Link href="/resident/profile" className="textbtn">
                  Hồ sơ cá nhân
                </Link>
                .
              </Notice>
            </div>
          ) : null}
          <KeyValues
            rows={[
              ["Đầu nối", p.connector_id ?? (p.queue_position ? `Hàng chờ, vị trí ${p.queue_position}` : "Chờ xếp")],
              ["Bắt đầu", `${formatTime(p.planned_start)} · ${formatDate(p.planned_start)}`],
              [`Đạt ${draft.request.soc_target}%`, `${formatTime(p.planned_end)} · ${formatDate(p.planned_end)}`],
              ["Giờ lấy xe", `${formatTime(draft.request.deadline)} · ${formatDate(draft.request.deadline)}`],
              ["Thời gian dư trước hạn", formatDuration(bufferMinutes)],
              ["Điện vào pin", formatKwh(p.energy.battery_energy_kwh)],
              ["Điện tiêu thụ dự kiến", formatKwh(p.energy.grid_energy_kwh)],
              ["Chi phí ước tính", formatVnd(p.estimated_cost_vnd)],
            ]}
          />
          <p className="hint" style={{ marginTop: 12 }}>
            Phương án dự kiến nạp {formatKwh(p.energy.battery_energy_kwh)} vào pin (tiêu thụ khoảng{" "}
            {formatKwh(p.energy.grid_energy_kwh)} điện năng) tại đầu nối {p.connector_id ?? "đang chờ xếp"}.
          </p>
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
              {p.alternatives.map((a, i) => (
                <li key={`${i}-${a.description}`} className="notice">
                  <div>
                    <strong>{formatViNumbers(a.description)}</strong>
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
          Phương án được tính lúc {formatTime(draft.createdAt)}. Nếu tình trạng trạm thay đổi trước khi bạn bấm xác nhận, hệ thống sẽ cập nhật phương án mới.
        </Notice>
        <Notice title="Lưu ý về ước tính sạc" icon="info">
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            <li>Khung giờ và chi phí được ước tính theo tình trạng trạm sạc tại thời điểm hiện tại.</li>
            <li>Nếu có xe phát sinh đột xuất hoặc sự cố nguồn điện, hệ thống sẽ tự động điều chỉnh để đảm bảo an toàn.</li>
          </ul>
        </Notice>
        {formattedReasons.length || formattedAssumptions.length ? (
          <details
            style={{
              border: "1px solid var(--line)",
              borderRadius: 10,
              padding: "10px 12px",
              fontSize: 13,
            }}
          >
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>Chi tiết kỹ thuật (Debug)</summary>
            {formattedReasons.length ? (
              <ul className="stack" style={{ gap: 4, margin: "8px 0 0", paddingLeft: 18 }}>
                {formattedReasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            ) : null}
            {formattedAssumptions.length ? (
              <ul style={{ margin: "8px 0 0", paddingLeft: 18 }} data-testid="proposal-assumptions">
                {formattedAssumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            ) : null}
          </details>
        ) : null}
      </aside>
    </div>
  );
}

function BookingView({ booking }: { booking: Booking }) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [changing, setChanging] = useState(false);
  const vehicleName = useVehicleName(booking.request.vehicle_model);
  const cancel = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/resident/bookings/{booking_id}", { params: { path: { booking_id: booking.booking_id } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["resident"] }),
  });
  return (
    <div className="cols">
      <div className="stack">
        <Panel label="Lịch đã xác nhận">
          <SectionHead title={`Phiên sạc · ${vehicleName}`} icon="calendar" extra={<Tag tone={booking.status === "queued" ? "gold" : "good"}>{booking.status === "queued" ? "Trong hàng chờ" : booking.status === "charging" ? "Đang sạc" : "Đã xác nhận"}</Tag>} />
          <KeyValues
            rows={[
              ["Mã đặt lịch", booking.booking_id],
              ["Đầu nối", booking.connector_id ?? "Chờ xếp"],
              ["Khung sạc", `${formatTime(booking.planned_start)}–${formatTime(booking.planned_end)}`],
              ["Mục tiêu", `${booking.request.soc_now}% → ${booking.request.soc_target}%`],
              ["Giờ lấy xe", `${formatTime(booking.request.deadline)} · ${formatDate(booking.request.deadline)}`],
              ["Điện lấy từ lưới", formatKwh(booking.energy.grid_energy_kwh)],
              ["Chi phí ước tính", formatVnd(booking.estimated_cost_vnd)],
            ]}
          />
          <div className="actions">
            <button type="button" className="btn btn-secondary" onClick={() => setChanging(true)}>
              <Icon name="adjust" />
              Đổi yêu cầu
            </button>
            {changing ? <ChangeBookingDialog booking={booking} onClose={() => setChanging(false)} /> : null}
            {asking ? (
              <span role="group" aria-label="Xác nhận huỷ" className="actions" style={{ margin: 0 }}>
                <span className="subcopy">Huỷ lịch sạc này?</span>
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
                  {reasons.map((r, i) => (
                    <li key={`${i}-${r}`}>{r}</li>
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
