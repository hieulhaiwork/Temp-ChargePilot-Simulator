"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { KeyValues, Notice, SectionHead, Tag } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { formatKwh, formatTime, formatVnd } from "@/lib/format";
import { useVehicleName } from "@/lib/vehicles";

type Booking = components["schemas"]["Booking"];
type ScheduleProposal = components["schemas"]["ScheduleProposal"];

interface Props {
  booking: Booking;
  onClose: () => void;
  onUpdated?: (booking: Booking) => void;
}

export function ChangeBookingDialog({ booking, onClose, onUpdated }: Props) {
  const queryClient = useQueryClient();
  const vehicleName = useVehicleName(booking.request.vehicle_model);
  const minSoc = Math.min(100, Math.floor(booking.request.soc_now) + 1);
  const [socTarget, setSocTarget] = useState(() => Math.max(booking.request.soc_target, minSoc));
  const [deadline, setDeadline] = useState(booking.request.deadline);
  const [previewProposal, setPreviewProposal] = useState<ScheduleProposal | null>(null);

  const quoteMutation = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/resident/bookings/{booking_id}/quotes", {
          params: { path: { booking_id: booking.booking_id } },
          body: {
            soc_target: socTarget !== booking.request.soc_target ? Number(socTarget) : undefined,
            deadline: deadline !== booking.request.deadline ? deadline : undefined,
          },
        }),
      ),
    onSuccess: (data) => {
      setPreviewProposal(data);
    },
  });

  const applyMutation = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/v1/resident/bookings/{booking_id}", {
          params: { path: { booking_id: booking.booking_id } },
          body: {
            soc_target: socTarget !== booking.request.soc_target ? Number(socTarget) : undefined,
            deadline: deadline !== booking.request.deadline ? deadline : undefined,
          },
        }),
      ),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: ["resident"] });
      onUpdated?.(updated);
      onClose();
    },
  });

  const hasChanges = socTarget !== booking.request.soc_target || deadline !== booking.request.deadline;

  function handleQuote(e: FormEvent) {
    e.preventDefault();
    if (!hasChanges) return;
    quoteMutation.mutate();
  }

  const applyError = applyMutation.error;
  const isConflict = applyError instanceof ApiError && applyError.status === 409;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="change-booking-title"
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: 16,
      }}
    >
      <div
        className="panel"
        style={{
          maxWidth: 540,
          width: "100%",
          maxHeight: "90vh",
          overflowY: "auto",
          backgroundColor: "#fff",
          borderRadius: 16,
          boxShadow: "0 10px 25px rgba(0,0,0,0.15)",
        }}
      >
        <SectionHead
          title="Đổi yêu cầu sạc"
          icon="adjust"
          extra={
            <button type="button" className="textbtn" onClick={onClose} aria-label="Đóng">
              <Icon name="close" />
            </button>
          }
        />
        <p className="subcopy" style={{ marginTop: 4 }}>
          Mã đặt lịch: <strong className="num">{booking.booking_id}</strong> ({vehicleName})
        </p>

        <form onSubmit={handleQuote} className="stack" style={{ gap: 14, marginTop: 16 }}>
          <div className="field">
            <label htmlFor="change-soc-target">Mức pin mục tiêu (%)</label>
            <input
              id="change-soc-target"
              type="number"
              min={minSoc}
              max={100}
              value={socTarget}
              onChange={(e) => {
                setSocTarget(Number(e.target.value));
                setPreviewProposal(null);
              }}
              required
            />
            <span className="hint">Mức hiện tại lúc đặt: {booking.request.soc_now}%</span>
          </div>

          <div className="field">
            <label htmlFor="change-deadline">Giờ lấy xe mong muốn</label>
            <input
              id="change-deadline"
              type="datetime-local"
              value={deadline.slice(0, 16)}
              onChange={(e) => {
                const val = e.target.value;
                if (val) {
                  setDeadline(new Date(val).toISOString());
                  setPreviewProposal(null);
                }
              }}
              required
            />
          </div>

          <div className="actions">
            <button
              type="submit"
              className="btn btn-secondary"
              disabled={!hasChanges || quoteMutation.isPending}
            >
              <Icon name="activity" />
              {quoteMutation.isPending ? "Đang tính phương án…" : "Xem trước phương án"}
            </button>
          </div>
        </form>

        {quoteMutation.isError ? (
          <div style={{ marginTop: 14 }}>
            {quoteMutation.error instanceof ApiError && quoteMutation.error.isNotImplemented ? (
              <NotImplementedPanel
                endpoint="POST /api/v1/resident/bookings/{booking_id}/quotes"
                taskId={quoteMutation.error.taskId}
                detail={quoteMutation.error.detail}
              />
            ) : (
              <ErrorPanel error={quoteMutation.error} />
            )}
          </div>
        ) : null}

        {previewProposal ? (
          <div className="stack" style={{ gap: 12, marginTop: 18, borderTop: "1px solid var(--wash)", paddingTop: 14 }}>
            <SectionHead
              title="Phương án mới dự kiến"
              icon="calendar"
              extra={
                previewProposal.feasible ? (
                  <Tag tone="good" icon="check">
                    Kịp giờ lấy xe
                  </Tag>
                ) : (
                  <Tag tone="bad" icon="alert">
                    Chưa kịp giờ lấy xe
                  </Tag>
                )
              }
            />

            <KeyValues
              rows={[
                ["Đầu nối", previewProposal.connector_id ?? "Chờ xếp"],
                ["Bắt đầu", formatTime(previewProposal.planned_start)],
                [`Đạt ${socTarget}%`, formatTime(previewProposal.planned_end)],
                ["Điện vào pin", formatKwh(previewProposal.energy.battery_energy_kwh)],
                ["Chi phí ước tính", formatVnd(previewProposal.estimated_cost_vnd)],
              ]}
            />

            <div className="actions" style={{ marginTop: 10 }}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!previewProposal.feasible || applyMutation.isPending}
                onClick={() => applyMutation.mutate()}
              >
                <Icon name="check" />
                {applyMutation.isPending ? "Đang áp dụng…" : "Áp dụng thay đổi"}
              </button>
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Giữ lịch cũ
              </button>
            </div>
          </div>
        ) : null}

        {applyMutation.isError ? (
          <div style={{ marginTop: 14 }}>
            {isConflict ? (
              <Notice title="Không thể cập nhật" tone="gold" icon="alert">
                <span>
                  {(applyMutation.error as ApiError).detail || "Trạm vừa thay đổi, phương án không còn khả thi."}
                  <br />
                  Bạn có thể thử chọn mức pin thấp hơn, lùi giờ nhận xe hoặc{" "}
                  <strong>Huỷ lịch rồi đặt lại</strong> (lưu ý: huỷ sẽ mất vị trí đang giữ).
                </span>
              </Notice>
            ) : applyMutation.error instanceof ApiError && applyMutation.error.isNotImplemented ? (
              <NotImplementedPanel
                endpoint="PATCH /api/v1/resident/bookings/{booking_id}"
                taskId={applyMutation.error.taskId}
                detail={applyMutation.error.detail}
              />
            ) : (
              <ErrorPanel error={applyMutation.error} />
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
