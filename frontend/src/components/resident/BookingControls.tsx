"use client";

/**
 * Các điều khiển chọn trực quan cho màn Đặt lịch (/resident/book):
 * - BatteryBarSlider: thanh pin vuông cố định thang 0–100%, kéo mượt bằng chuột/chạm.
 * - AndroidTimePicker: đồng hồ trượt kiểu Android Clock (kéo lên/xuống trên Giờ và Phút + khung giá điện).
 */
import { useEffect, useRef, useState } from "react";

import { formatVnd } from "@/lib/format";

export type ClockSlot = {
  hour: number;
  minute: number;
  dayOffset: 0 | 1; // 0 = hôm nay, 1 = ngày mai
};

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5); // 00, 05, ..., 55
const MAX_TOTAL_MINUTES = 47 * 60 + 55; // 23:55 ngày mai

export function nowRoundedMinutes(): number {
  const now = new Date();
  const raw = now.getHours() * 60 + now.getMinutes();
  return Math.ceil(raw / 5) * 5;
}

export function slotToTotal(slot: ClockSlot): number {
  return slot.dayOffset * 24 * 60 + slot.hour * 60 + slot.minute;
}

export function slotFromTotal(total: number): ClockSlot {
  const clamped = Math.max(0, Math.min(MAX_TOTAL_MINUTES, Math.round(total / 5) * 5));
  const dayOffset: 0 | 1 = clamped >= 24 * 60 ? 1 : 0;
  const rem = clamped - dayOffset * 24 * 60;
  return {
    hour: Math.floor(rem / 60),
    minute: rem % 60,
    dayOffset,
  };
}

/** Chuyển ClockSlot (giờ trạm +07:00) sang chuỗi ISO 8601 có offset `+07:00` gửi backend. */
export function slotToIso(slot: ClockSlot): string {
  const d = new Date(Date.now() + 7 * 3600_000 + slot.dayOffset * 86400_000);
  const ymd = d.toISOString().slice(0, 10);
  const hh = String(slot.hour).padStart(2, "0");
  const mm = String(slot.minute).padStart(2, "0");
  return `${ymd}T${hh}:${mm}:00+07:00`;
}

function parseHm(hm: string): number {
  const [h, m] = hm.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

type TariffInfo = {
  label: string;
  price: number;
  tone: "good" | "bad" | "neutral";
};

function lookupTariffAt(
  hour: number,
  minute: number,
  periods?: Array<{ name: string; start: string; end: string; price_per_kwh: number }>,
): TariffInfo {
  const t = hour * 60 + minute;
  const list =
    periods && periods.length > 0
      ? periods
      : [
          { name: "off_peak", start: "22:00", end: "04:00", price_per_kwh: 1200 },
          { name: "normal", start: "04:00", end: "09:30", price_per_kwh: 2000 },
          { name: "peak", start: "09:30", end: "11:30", price_per_kwh: 3500 },
          { name: "normal", start: "11:30", end: "17:00", price_per_kwh: 2000 },
          { name: "peak", start: "17:00", end: "20:00", price_per_kwh: 3500 },
          { name: "normal", start: "20:00", end: "22:00", price_per_kwh: 2000 },
        ];

  const found = list.find((p) => {
    const s = parseHm(p.start);
    const e = parseHm(p.end);
    return s <= e ? t >= s && t < e : t >= s || t < e;
  });

  if (!found) return { label: "Bình thường", price: 2000, tone: "neutral" };
  if (found.name === "off_peak") return { label: "Thấp điểm (rẻ nhất)", price: found.price_per_kwh, tone: "good" };
  if (found.name === "peak") return { label: "Cao điểm", price: found.price_per_kwh, tone: "bad" };
  return { label: "Bình thường", price: found.price_per_kwh, tone: "neutral" };
}

/** Thanh kéo pin dạng khối vuông mô phỏng thanh pin EV (thang cố định 0–100%). */
export function BatteryBarSlider({
  label,
  value,
  minAllowed,
  maxAllowed,
  baseFillPercent,
  fillColor,
  onChange,
  presets,
}: {
  label: string;
  value: number;
  minAllowed: number;
  maxAllowed: number;
  baseFillPercent?: number;
  fillColor: string;
  onChange: (next: number) => void;
  presets?: number[];
}) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);

  function updateFromClientX(clientX: number) {
    const el = trackRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const rawPct = Math.round(ratio * 100);
    const clamped = Math.max(minAllowed, Math.min(maxAllowed, rawPct));
    onChange(clamped);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.88rem", fontWeight: 600 }}>{label}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {presets?.map((preset) => (
            <button
              key={preset}
              type="button"
              disabled={preset < minAllowed}
              className={`btn small ${value === preset ? "btn-primary" : "btn-secondary"}`}
              style={{ padding: "1px 8px", fontSize: "0.75rem" }}
              onClick={() => onChange(preset)}
            >
              {preset}%
            </button>
          ))}
          <strong style={{ minWidth: 42, textAlign: "right", fontSize: "0.98rem" }}>{value}%</strong>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
        <div
          ref={trackRef}
          role="slider"
          tabIndex={0}
          aria-label={label}
          aria-valuemin={minAllowed}
          aria-valuemax={maxAllowed}
          aria-valuenow={value}
          onPointerDown={(e) => {
            draggingRef.current = true;
            e.currentTarget.setPointerCapture(e.pointerId);
            updateFromClientX(e.clientX);
          }}
          onPointerMove={(e) => {
            if (!draggingRef.current) return;
            updateFromClientX(e.clientX);
          }}
          onPointerUp={(e) => {
            draggingRef.current = false;
            if (e.currentTarget.hasPointerCapture(e.pointerId)) {
              e.currentTarget.releasePointerCapture(e.pointerId);
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight" || e.key === "ArrowUp") {
              e.preventDefault();
              onChange(Math.min(maxAllowed, value + 1));
            } else if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
              e.preventDefault();
              onChange(Math.max(minAllowed, value - 1));
            }
          }}
          style={{
            position: "relative",
            flex: 1,
            height: 32,
            borderRadius: 6,
            border: "2px solid var(--ink-2, #374151)",
            background: "var(--surface, #fff)",
            overflow: "hidden",
            cursor: "ew-resize",
            touchAction: "none",
            userSelect: "none",
          }}
        >
          {baseFillPercent !== undefined && baseFillPercent > 0 ? (
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                bottom: 0,
                width: `${baseFillPercent}%`,
                background: "rgba(20, 83, 45, 0.28)",
                borderRight: "2px dashed rgba(20, 83, 45, 0.65)",
                pointerEvents: "none",
              }}
            />
          ) : null}

          <div
            style={{
              position: "absolute",
              top: 0,
              left: baseFillPercent !== undefined ? `${baseFillPercent}%` : 0,
              bottom: 0,
              width: `${Math.max(0, value - (baseFillPercent ?? 0))}%`,
              background: fillColor,
              pointerEvents: "none",
            }}
          />

          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "grid",
              gridTemplateColumns: "repeat(10, 1fr)",
              pointerEvents: "none",
            }}
          >
            {Array.from({ length: 10 }, (_, i) => (
              <div key={i} style={{ borderRight: i < 9 ? "1px solid rgba(255,255,255,0.4)" : "none" }} />
            ))}
          </div>

          <div
            style={{
              position: "absolute",
              top: 2,
              bottom: 2,
              left: `calc(${value}% - 5px)`,
              width: 10,
              borderRadius: 3,
              background: "#fff",
              border: "2px solid var(--brand, #14532d)",
              boxShadow: "0 1px 3px rgba(0,0,0,0.28)",
              pointerEvents: "none",
            }}
          />
        </div>

        <div
          style={{
            width: 5,
            height: 15,
            borderRadius: "0 3px 3px 0",
            background: "var(--ink-2, #374151)",
          }}
        />
      </div>
    </div>
  );
}

/** Cột cuộn kiểu Android Clock: kéo chuột/ngón tay lên xuống hoặc lăn con lăn chuột đều mượt. */
function AndroidClockDrum({
  values,
  selected,
  onSelect,
  ariaLabel,
}: {
  values: number[];
  selected: number;
  onSelect: (val: number) => void;
  ariaLabel: string;
}) {
  const drumRef = useRef<HTMLDivElement | null>(null);
  const dragStartY = useRef<number | null>(null);
  const dragStartIdx = useRef<number>(0);
  const movedRef = useRef(false);
  const stepPx = 24;

  const idx = Math.max(0, values.indexOf(selected));
  const prevVal = values[(idx - 1 + values.length) % values.length];
  const nextVal = values[(idx + 1) % values.length];

  function stepBy(delta: number) {
    const nextIdx = (idx + delta + values.length * 10) % values.length;
    onSelect(values[nextIdx]);
  }

  // Native non-passive wheel listener: React onWheel là passive nên preventDefault bị bỏ qua và cuộn cả trang.
  useEffect(() => {
    const el = drumRef.current;
    if (!el) return;
    const onNativeWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const delta = e.deltaY > 0 ? 1 : -1;
      const nextIdx = (idx + delta + values.length * 10) % values.length;
      onSelect(values[nextIdx]);
    };
    el.addEventListener("wheel", onNativeWheel, { passive: false });
    return () => el.removeEventListener("wheel", onNativeWheel);
  }, [idx, values, onSelect]);

  return (
    <div
      ref={drumRef}
      role="spinbutton"
      tabIndex={0}
      aria-label={ariaLabel}
      aria-valuenow={selected}
      onPointerDown={(e) => {
        dragStartY.current = e.clientY;
        dragStartIdx.current = idx;
        movedRef.current = false;
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (dragStartY.current === null) return;
        const dy = dragStartY.current - e.clientY;
        const steps = Math.trunc(dy / stepPx);
        if (steps !== 0) {
          movedRef.current = true;
          const targetIdx = (dragStartIdx.current + steps + values.length * 100) % values.length;
          if (values[targetIdx] !== selected) {
            onSelect(values[targetIdx]);
          }
        }
      }}
      onPointerUp={(e) => {
        dragStartY.current = null;
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowUp") {
          e.preventDefault();
          stepBy(1);
        } else if (e.key === "ArrowDown") {
          e.preventDefault();
          stepBy(-1);
        }
      }}
      style={{
        width: 64,
        borderRadius: 8,
        border: "1px solid var(--line)",
        background: "var(--surface, #fff)",
        overflow: "hidden",
        userSelect: "none",
        touchAction: "none",
        cursor: "ns-resize",
        display: "flex",
        flexDirection: "column",
      }}
      title="Kéo lên/xuống hoặc lăn chuột để chỉnh"
    >
      <div
        onClick={() => {
          if (!movedRef.current) stepBy(-1);
        }}
        style={{
          height: 28,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "0.84rem",
          opacity: 0.45,
        }}
      >
        {String(prevVal).padStart(2, "0")}
      </div>
      <div
        style={{
          height: 36,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--brand, #14532d)",
          color: "#fff",
          fontWeight: 700,
          fontSize: "1.05rem",
        }}
      >
        {String(selected).padStart(2, "0")}
      </div>
      <div
        onClick={() => {
          if (!movedRef.current) stepBy(1);
        }}
        style={{
          height: 28,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "0.84rem",
          opacity: 0.45,
        }}
      >
        {String(nextVal).padStart(2, "0")}
      </div>
    </div>
  );
}

export function AndroidTimePicker({
  label,
  value,
  minAllowedTotal,
  onChange,
  onQuickAdd,
  tariffPeriods,
  showQuickAdd = false,
}: {
  label: string;
  value: ClockSlot;
  minAllowedTotal: number;
  onChange: (next: ClockSlot) => void;
  onQuickAdd?: (deltaMinutes: number) => void;
  tariffPeriods?: Array<{ name: string; start: string; end: string; price_per_kwh: number }>;
  showQuickAdd?: boolean;
}) {
  const tariff = lookupTariffAt(value.hour, value.minute, tariffPeriods);
  const badgeColor =
    tariff.tone === "good" ? "#15803d" : tariff.tone === "bad" ? "#b91c1c" : "var(--ink-2, #4b5563)";
  const badgeBg =
    tariff.tone === "good"
      ? "rgba(21,128,61,0.12)"
      : tariff.tone === "bad"
        ? "rgba(185,28,28,0.12)"
        : "rgba(0,0,0,0.05)";

  const [rolledOverNotice, setRolledOverNotice] = useState<string | null>(null);
  const todayCandidateTotal = value.hour * 60 + value.minute;
  const canPickToday = todayCandidateTotal >= minAllowedTotal;

  function applyHourMinute(hour: number, minute: number) {
    const todayTotal = hour * 60 + minute;
    if (value.dayOffset === 0 && todayTotal < minAllowedTotal) {
      const hhmm = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
      setRolledOverNotice(
        `Giờ ${hhmm} đã qua hoặc sớm hơn mốc bắt đầu của hôm nay — đã chuyển sang Ngày mai. Vui lòng kiểm tra lại ngày lấy xe.`,
      );
      onChange({ hour, minute, dayOffset: 1 });
      return;
    }
    if (value.dayOffset === 0) {
      setRolledOverNotice(null);
    }
    onChange({ hour, minute, dayOffset: value.dayOffset });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
        <span style={{ fontSize: "0.88rem", fontWeight: 600 }}>{label}</span>
        <span
          style={{
            fontSize: "0.76rem",
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: 999,
            color: badgeColor,
            background: badgeBg,
          }}
        >
          {tariff.label} · {formatVnd(tariff.price)}/kWh
        </span>
      </div>

      {showQuickAdd && onQuickAdd ? (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <button type="button" className="btn btn-secondary small" onClick={() => onQuickAdd(-60)}>
            -1 giờ
          </button>
          <button type="button" className="btn btn-secondary small" onClick={() => onQuickAdd(-30)}>
            -30 phút
          </button>
          <button type="button" className="btn btn-secondary small" onClick={() => onQuickAdd(30)}>
            +30 phút
          </button>
          <button type="button" className="btn btn-secondary small" onClick={() => onQuickAdd(60)}>
            +1 giờ
          </button>
          <span className="hint" style={{ fontSize: "0.75rem" }}>
            (Kéo lên/xuống trên ô giờ và phút để chỉnh)
          </span>
        </div>
      ) : null}

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <AndroidClockDrum
          values={HOURS}
          selected={value.hour}
          onSelect={(h) => applyHourMinute(h, value.minute)}
          ariaLabel={`${label} — giờ`}
        />
        <span style={{ fontWeight: 700, fontSize: "1.15rem" }}>:</span>
        <AndroidClockDrum
          values={MINUTES}
          selected={value.minute}
          onSelect={(m) => applyHourMinute(value.hour, m)}
          ariaLabel={`${label} — phút`}
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginLeft: 4 }}>
          <button
            type="button"
            disabled={!canPickToday}
            title={!canPickToday ? "Giờ này đã qua hoặc sớm hơn giờ bắt đầu của hôm nay" : undefined}
            className={`btn small ${value.dayOffset === 0 ? "btn-primary" : "btn-secondary"}`}
            onClick={() => {
              setRolledOverNotice(null);
              onChange({ ...value, dayOffset: 0 });
            }}
          >
            Hôm nay
          </button>
          <button
            type="button"
            className={`btn small ${value.dayOffset === 1 ? "btn-primary" : "btn-secondary"}`}
            onClick={() => {
              setRolledOverNotice(null);
              onChange({ ...value, dayOffset: 1 });
            }}
          >
            Ngày mai
          </button>
        </div>
      </div>
      {rolledOverNotice ? (
        <div
          role="status"
          data-testid="date-rollover-notice"
          style={{
            fontSize: "0.78rem",
            padding: "6px 10px",
            borderRadius: 8,
            background: "rgba(217,119,6,0.12)",
            color: "#92400e",
          }}
        >
          {rolledOverNotice}
        </div>
      ) : null}
    </div>
  );
}
