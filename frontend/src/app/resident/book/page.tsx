"use client";

/**
 * Đặt lịch sạc bằng biểu mẫu (mockup cu-dan/resident-book.html; spec 21 §2.4; FR2, FR3, FR9, FR13).
 * Đường dự phòng khi Trợ lý không dùng được (NFR khả dụng). Đi CÙNG charging_service với đường chat:
 * GET /energy-estimates (kWh do code tính, FR3) → POST /resident/quotes → S3 (/resident/plan).
 *
 * Nâng cấp UX:
 * - Thanh kéo pin dạng hộp vuông EV (thang cố định 0–100%, Mục tiêu luôn > Pin hiện tại).
 * - Nút chọn loại trừ nhau cho Vùng sạc (AC · 11 kW vs DC · 60 kW) và Hình thức (Đang ở bãi vs Đặt trước).
 * - Đồng hồ trượt kiểu Android Clock (-1h / -30p / +30p / +1h, live khung giá điện từ /api/v1/tariff, chặn giờ vô lý).
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import {
  AndroidTimePicker,
  BatteryBarSlider,
  nowRoundedMinutes,
  slotFromTotal,
  slotToIso,
  slotToTotal,
  type ClockSlot,
} from "@/components/resident/BookingControls";
import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { KeyValues, Notice, PageHead, Panel, SectionHead } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import { saveDraft, type ChargeRequest } from "@/lib/booking/draft";
import { formatKwh } from "@/lib/format";

export default function ResidentBookPage() {
  const router = useRouter();
  const vehicles = useQuery(queries.vehicles());
  const tariff = useQuery(queries.tariff());
  const me = useQuery(queries.me());

  const [vehicle, setVehicle] = useState("");
  const [socNow, setSocNow] = useState(30);
  const [socTarget, setSocTarget] = useState(80);
  const [zone, setZone] = useState<"AC" | "DC">("DC");
  const [mode, setMode] = useState<"reservation" | "walk_in">("walk_in");

  const [arrivalSlot, setArrivalSlot] = useState<ClockSlot>(() => slotFromTotal(nowRoundedMinutes() + 30));
  const [deadlineSlot, setDeadlineSlot] = useState<ClockSlot>(() => slotFromTotal(nowRoundedMinutes() + 30));

  const model = vehicle || me.data?.vehicle_model || vehicles.data?.[0]?.vehicle_model || "";
  const minTarget = Math.min(100, socNow + 5);
  const nowTotal = nowRoundedMinutes();
  const minArrivalTotal = nowTotal + 5;
  const startTotal = mode === "reservation" ? Math.max(minArrivalTotal, slotToTotal(arrivalSlot)) : nowTotal;
  const minDeadlineTotal = startTotal + 15;

  const request: ChargeRequest = {
    vehicle_model: model,
    soc_now: socNow,
    soc_target: socTarget,
    mode,
    zone,
    arrival_time: mode === "reservation" ? slotToIso(arrivalSlot) : null,
    deadline: slotToIso(deadlineSlot),
  };

  const estimate = useQuery({
    queryKey: ["energy-estimate", model, socNow, socTarget],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/energy-estimates", {
          params: { query: { vehicle_model: model, soc_now: socNow, soc_target: socTarget } },
        }),
      ),
    enabled: Boolean(model) && socTarget > socNow && socTarget <= 100,
  });

  const quote = useMutation({
    mutationFn: (body: ChargeRequest) => unwrap(api.POST("/api/v1/resident/quotes", { body })),
    onSuccess: (proposal, body) => {
      saveDraft({ request: body, proposal, createdAt: new Date().toISOString() });
      router.push("/resident/plan?view=draft");
    },
  });

  function handleSocNowChange(nextNow: number) {
    const clampedNow = Math.max(0, Math.min(95, nextNow));
    setSocNow(clampedNow);
    const nextMin = Math.min(100, clampedNow + 5);
    if (socTarget < nextMin) {
      setSocTarget(nextMin);
    }
  }

  function handleSocTargetChange(nextTarget: number) {
    setSocTarget(Math.max(minTarget, Math.min(100, nextTarget)));
  }

  function handleZoneChange(nextZone: "AC" | "DC") {
    setZone(nextZone);
    const defaultOffset = nextZone === "DC" ? 30 : 60;
    const base = mode === "reservation" ? slotToTotal(arrivalSlot) : nowRoundedMinutes();
    setDeadlineSlot(slotFromTotal(base + defaultOffset));
  }

  function handleModeChange(nextMode: "walk_in" | "reservation") {
    setMode(nextMode);
    const baseNow = nowRoundedMinutes();
    const defaultOffset = zone === "DC" ? 30 : 60;
    if (nextMode === "reservation") {
      const nextArr = slotFromTotal(baseNow + 30);
      setArrivalSlot(nextArr);
      const minDl = slotToTotal(nextArr) + defaultOffset;
      if (slotToTotal(deadlineSlot) < minDl) {
        setDeadlineSlot(slotFromTotal(minDl));
      }
    } else {
      const minDl = baseNow + 15;
      if (slotToTotal(deadlineSlot) < minDl) {
        setDeadlineSlot(slotFromTotal(baseNow + defaultOffset));
      }
    }
  }

  function handleArrivalChange(nextArr: ClockSlot) {
    const validArr = slotToTotal(nextArr) < minArrivalTotal ? slotFromTotal(minArrivalTotal) : nextArr;
    setArrivalSlot(validArr);
    const minDl = slotToTotal(validArr) + 15;
    if (slotToTotal(deadlineSlot) < minDl) {
      setDeadlineSlot(slotFromTotal(slotToTotal(validArr) + (zone === "DC" ? 30 : 60)));
    }
  }

  function handleDeadlineChange(nextDl: ClockSlot) {
    if (slotToTotal(nextDl) < minDeadlineTotal) {
      setDeadlineSlot(slotFromTotal(minDeadlineTotal));
      return;
    }
    setDeadlineSlot(nextDl);
  }

  function handleQuickAddDeadline(deltaMinutes: number) {
    const currentDlTotal = Math.max(minDeadlineTotal, slotToTotal(deadlineSlot));
    const nextTotal = Math.max(minDeadlineTotal, currentDlTotal + deltaMinutes);
    setDeadlineSlot(slotFromTotal(nextTotal));
  }

  function onSubmit(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    if (!model) return;
    quote.mutate(request);
  }

  const currentBatteryColor = socNow <= 20 ? "#dc2626" : socNow <= 45 ? "#d97706" : "#16a34a";
  const chargePowerKw = zone === "DC" ? 60 : 11;
  const estMinutes = estimate.data
    ? Math.max(5, Math.round((estimate.data.battery_energy_kwh / (chargePowerKw * 0.98)) * 60))
    : null;
  const availableMinutes = Math.max(0, slotToTotal(deadlineSlot) - startTotal);
  const acLikelyTight = zone === "AC" && estMinutes !== null && availableMinutes > 0 && availableMinutes < estMinutes;

  return (
    <>
      <PageHead title="Đặt lịch sạc" sub="Chọn mức pin, vùng sạc AC/DC và thời điểm bạn cần lấy xe." />
      <DataBlock endpoint="GET /api/v1/resident/bookings/current" query={queries.residentBooking()} loadingLines={1}>
        {(booking) =>
          booking ? (
            <Notice title="Xe đang có lịch hiệu lực" tone="gold" icon="calendar">
              Mỗi xe chỉ giữ một lịch.{" "}
              <Link href="/resident/plan" className="textbtn">
                Xem lịch đang giữ
              </Link>
            </Notice>
          ) : null
        }
      </DataBlock>
      <div className="cols">
        <form className="stack" onSubmit={onSubmit} noValidate>
          <Panel label="Xe và mức pin">
            <SectionHead title="Xe và mức pin" icon="car" />
            <div className="stack" style={{ gap: 16 }}>
              <div className="field">
                <label htmlFor="vehicle">Mẫu xe</label>
                {vehicles.isError ? (
                  vehicles.error instanceof ApiError && vehicles.error.isNotImplemented ? (
                    <NotImplementedPanel endpoint="GET /api/v1/vehicles" taskId={vehicles.error.taskId} />
                  ) : (
                    <ErrorPanel error={vehicles.error} onRetry={() => void vehicles.refetch()} />
                  )
                ) : (
                  <select
                    id="vehicle"
                    value={model}
                    onChange={(e) => setVehicle(e.target.value)}
                    disabled={vehicles.isPending || !vehicles.data?.length}
                  >
                    {vehicles.isPending ? <option>Đang tải danh mục xe…</option> : null}
                    {vehicles.data?.length === 0 ? <option>Danh mục xe trống</option> : null}
                    {vehicles.data?.map((v) => (
                      <option key={v.vehicle_model} value={v.vehicle_model}>
                        {v.display_name} · {v.usable_capacity_kwh} kWh
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <BatteryBarSlider
                label="Pin hiện tại"
                value={socNow}
                minAllowed={0}
                maxAllowed={95}
                fillColor={currentBatteryColor}
                onChange={handleSocNowChange}
              />

              <BatteryBarSlider
                label="Pin mục tiêu (luôn > pin hiện tại)"
                value={socTarget}
                minAllowed={minTarget}
                maxAllowed={100}
                baseFillPercent={socNow}
                fillColor="#15803d"
                onChange={handleSocTargetChange}
                presets={[80, 90, 100]}
              />
            </div>
          </Panel>

          <Panel label="Vùng sạc và thời gian">
            <SectionHead title="Vùng sạc & Thời gian ở trạm" icon="clock" />
            <div className="stack" style={{ gap: 16 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 }}>
                <div>
                  <div style={{ fontSize: "0.86rem", fontWeight: 600, marginBottom: 6 }}>Vùng sạc (chọn 1)</div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      type="button"
                      className={`btn small ${zone === "AC" ? "btn-primary" : "btn-secondary"}`}
                      style={{ flex: 1 }}
                      onClick={() => handleZoneChange("AC")}
                    >
                      AC · 11 kW
                    </button>
                    <button
                      type="button"
                      className={`btn small ${zone === "DC" ? "btn-primary" : "btn-secondary"}`}
                      style={{ flex: 1 }}
                      onClick={() => handleZoneChange("DC")}
                    >
                      DC · 60 kW
                    </button>
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: "0.86rem", fontWeight: 600, marginBottom: 6 }}>Hình thức</div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      type="button"
                      className={`btn small ${mode === "walk_in" ? "btn-primary" : "btn-secondary"}`}
                      style={{ flex: 1 }}
                      onClick={() => handleModeChange("walk_in")}
                    >
                      Đang ở bãi
                    </button>
                    <button
                      type="button"
                      className={`btn small ${mode === "reservation" ? "btn-primary" : "btn-secondary"}`}
                      style={{ flex: 1 }}
                      onClick={() => handleModeChange("reservation")}
                    >
                      Hẹn giờ tới
                    </button>
                  </div>
                </div>
              </div>

              {mode === "reservation" ? (
                <AndroidTimePicker
                  label="Giờ dự kiến đến bãi"
                  value={arrivalSlot}
                  minAllowedTotal={minArrivalTotal}
                  onChange={handleArrivalChange}
                  tariffPeriods={tariff.data?.periods}
                  showQuickAdd={false}
                />
              ) : null}

              <AndroidTimePicker
                label="Giờ cần lấy xe"
                value={deadlineSlot}
                minAllowedTotal={minDeadlineTotal}
                onChange={handleDeadlineChange}
                onQuickAdd={handleQuickAddDeadline}
                tariffPeriods={tariff.data?.periods}
                showQuickAdd={true}
              />

              <div className="actions">
                <button type="submit" className="btn btn-primary" disabled={quote.isPending || !model}>
                  <Icon name="arrow" />
                  {quote.isPending ? "Đang tính phương án…" : "Xem phương án"}
                </button>
              </div>
              {quote.isError ? (
                <div style={{ marginTop: 8 }}>
                  {quote.error instanceof ApiError && quote.error.isNotImplemented ? (
                    <NotImplementedPanel endpoint="POST /api/v1/resident/quote" taskId={quote.error.taskId} detail={quote.error.detail} />
                  ) : (
                    <ErrorPanel error={quote.error} />
                  )}
                </div>
              ) : null}
            </div>
          </Panel>
        </form>

        <aside className="stack">
          <Panel label="Ước tính">
            <SectionHead title="Ước tính trước khi đặt" icon="bolt" sub="Điện năng do hệ thống tính, không do Trợ lý" />
            {!model || socTarget <= socNow ? (
              <p className="subcopy">Chọn mẫu xe và mức pin để xem ước tính.</p>
            ) : estimate.isPending ? (
              <p role="status" className="hint">
                Đang tính…
              </p>
            ) : estimate.isError ? (
              estimate.error instanceof ApiError && estimate.error.isNotImplemented ? (
                <NotImplementedPanel endpoint="GET /api/v1/energy-estimates" taskId={estimate.error.taskId} />
              ) : (
                <ErrorPanel error={estimate.error} onRetry={() => void estimate.refetch()} />
              )
            ) : (
              <div className="stack" style={{ gap: 12 }}>
                <KeyValues
                  rows={[
                    ["Vùng sạc", zone === "DC" ? "DC · Sạc nhanh (60 kW)" : "AC · Sạc chậm (11 kW)"],
                    ["Điện vào pin", formatKwh(estimate.data.battery_energy_kwh)],
                    ["Điện lấy từ lưới", formatKwh(estimate.data.grid_energy_kwh)],
                    ["Thời gian sạc ước tính", estMinutes !== null ? `~${estMinutes} phút` : "—"],
                    ["Quỹ thời gian đã chọn", `${availableMinutes} phút`],
                  ]}
                />
                {acLikelyTight ? (
                  <div
                    style={{
                      padding: "10px 12px",
                      borderRadius: 8,
                      background: "rgba(217,119,6,0.12)",
                      color: "#92400e",
                      fontSize: "0.84rem",
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                    }}
                  >
                    <span>Quỹ thời gian ({availableMinutes} phút) có thể không kịp với sạc AC (~{estMinutes} phút).</span>
                    <div>
                      <button type="button" className="btn btn-primary small" onClick={() => handleZoneChange("DC")}>
                        <Icon name="bolt" />
                        Chuyển sang sạc nhanh DC
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            )}
            <p className="hint" style={{ marginTop: 12 }}>
              Chi phí và đầu nối chính xác sẽ hiện ở bước xem phương án.
            </p>
          </Panel>
        </aside>
      </div>
    </>
  );
}
