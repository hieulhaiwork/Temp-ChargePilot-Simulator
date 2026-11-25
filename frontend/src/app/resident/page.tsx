"use client";

/**
 * S2 · Trang chủ cư dân (mockup docs/mockups/cu-dan/resident.html; spec 21 §2.2; FR15, FR2, FR3, FR5, FR17).
 * Thẻ chính đặt giờ đạt mục tiêu lên đầu; vị trí hàng chờ; chip "giờ rẻ" lấy khung từ GET /tariff (không dùng ML,
 * docs/plan/00-overview.md Q5); Trợ lý sạc nằm ngay trong trang. Mỗi khối xử lý 501 / lỗi riêng.
 */
import Link from "next/link";

import { CopilotPanel } from "@/components/copilot/CopilotPanel";
import { ChatPanel } from "@/components/resident/ChatPanel";
import { DataBlock } from "@/components/system/DataBlock";
import { EmptyState, KeyValues, PageHead, Panel, SectionHead, Tag } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { queries } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";
import { formatDate, formatKwh, formatTime, formatVnd } from "@/lib/format";
import { usePollFallback } from "@/lib/ws/useStream";

type BookingStatus = components["schemas"]["BookingStatus"];
const BOOKING_LABEL: Record<BookingStatus, [string, "good" | "gold" | "neutral" | "blue"]> = {
  confirmed: ["Đã xác nhận", "good"],
  queued: ["Trong hàng chờ", "gold"],
  charging: ["Đang sạc", "good"],
  completed: ["Đã xong", "blue"],
  cancelled: ["Đã huỷ", "neutral"],
};

export default function ResidentHomePage() {
  const poll = usePollFallback();
  return (
    <>
      <PageHead
        title="Tổng quan sạc"
        sub="Lịch sạc đêm nay, hàng chờ và Trợ lý sạc."
        actions={
          <Link href="/resident/book" className="btn btn-primary">
            <Icon name="calendar" />
            Đặt lịch sạc
          </Link>
        }
      />
      <div className="cols">
        <div className="stack">
          <Panel className="hero" label="Lịch sạc của tôi">
            <SectionHead title="Lịch sạc của tôi" icon="moon" sub="Giờ dự kiến đạt mức pin mục tiêu" />
            <DataBlock endpoint="GET /api/v1/resident/session" query={queries.residentSession()} refetchInterval={poll}>
              {(view) =>
                view.booking ? (
                  <div className="stack" style={{ gap: 14 }}>
                    <div>
                      <Tag tone={BOOKING_LABEL[view.booking.status][1]}>{BOOKING_LABEL[view.booking.status][0]}</Tag>
                      <p className="metric num" style={{ marginTop: 8 }}>
                        {formatTime(view.booking.planned_end)}
                      </p>
                      <p className="hint">
                        Đạt {view.booking.request.soc_target}% · lấy xe {formatTime(view.booking.request.deadline)} ngày{" "}
                        {formatDate(view.booking.request.deadline)}
                      </p>
                    </div>
                    <KeyValues
                      rows={[
                        ["Đầu nối", view.booking.connector_id ?? "Chờ xếp"],
                        ["Khung sạc", `${formatTime(view.booking.planned_start)}–${formatTime(view.booking.planned_end)}`],
                        ["Điện vào pin", formatKwh(view.booking.energy.battery_energy_kwh)],
                        ["Điện lấy từ lưới", formatKwh(view.booking.energy.grid_energy_kwh)],
                        ["Chi phí ước tính", formatVnd(view.booking.estimated_cost_vnd)],
                      ]}
                    />
                    <Link href="/resident/plan" className="textbtn" style={{ color: "#ffda8a" }}>
                      Xem chi tiết lịch
                      <Icon name="arrow" />
                    </Link>
                  </div>
                ) : (
                  <EmptyState icon="calendar" title="Chưa có lịch sạc">
                    Đặt lịch bằng biểu mẫu hoặc nhờ Trợ lý sạc tìm khung giờ phù hợp.
                  </EmptyState>
                )
              }
            </DataBlock>
          </Panel>
          <ChatPanel />
          <CopilotPanel role="resident" />
        </div>
        <aside className="stack">
          <Panel label="Hàng chờ">
            <SectionHead title="Hàng chờ" icon="queue" />
            <DataBlock endpoint="GET /api/v1/resident/queue" query={queries.residentQueue()} refetchInterval={poll} loadingLines={2}>
              {(q) =>
                q.position ? (
                  <KeyValues
                    rows={[
                      ["Vị trí của bạn", `${q.position} / ${q.queue_length}`],
                      ["Dự kiến bắt đầu", formatTime(q.estimated_start)],
                      ["Chờ thêm", q.estimated_wait_minutes != null ? `${q.estimated_wait_minutes} phút` : "—"],
                    ]}
                  />
                ) : (
                  <p className="subcopy">Bạn không ở trong hàng chờ. Có {q.queue_length} xe đang chờ.</p>
                )
              }
            </DataBlock>
          </Panel>
          <Panel label="Giờ điện rẻ">
            <SectionHead title="Khung giá điện" icon="clock" sub="Gợi ý giờ rẻ theo biểu giá của trạm" />
            <DataBlock endpoint="GET /api/v1/tariff" query={queries.tariff()} loadingLines={2}>
              {(tariff) => {
                const cheapest = Math.min(...tariff.periods.map((p) => p.price_per_kwh));
                return (
                  <div className="stack" style={{ gap: 10 }}>
                    <div className="chips">
                      {tariff.periods.map((p) => (
                        <Tag key={`${p.name}-${p.start}`} tone={p.price_per_kwh === cheapest ? "good" : "neutral"} icon={p.price_per_kwh === cheapest ? "check" : undefined}>
                          {p.name} · {p.start}–{p.end} · {formatVnd(p.price_per_kwh)}/kWh
                        </Tag>
                      ))}
                    </div>
                    {!tariff.verified ? <p className="hint">Giá mẫu, chưa đối chiếu biểu giá thật ({tariff.source}).</p> : null}
                  </div>
                );
              }}
            </DataBlock>
          </Panel>
        </aside>
      </div>
    </>
  );
}
