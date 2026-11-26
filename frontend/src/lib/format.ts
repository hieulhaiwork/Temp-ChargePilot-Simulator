/** Định dạng hiển thị: giờ trạm GMT+7, số kiểu Việt Nam (dấu phẩy thập phân), tiền đồng. */
const TZ = "Asia/Ho_Chi_Minh";

const timeFmt = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: TZ });
const dateFmt = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: TZ });
const num1 = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
const vnd = new Intl.NumberFormat("vi-VN");

/** "23:00" — chuỗi rỗng hoặc ngày không hợp lệ trả "—". */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : timeFmt.format(d);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : dateFmt.format(d);
}

/** "29,4 kW" */
export function formatKw(value: number | null | undefined): string {
  return value == null ? "—" : `${num1.format(value)} kW`;
}

/** "32 kWh" — kWh luôn do backend tính (FR3), web chỉ định dạng. */
export function formatKwh(value: number | null | undefined): string {
  return value == null ? "—" : `${num1.format(value)} kWh`;
}

/** "38.400 ₫" */
export function formatVnd(value: number | null | undefined): string {
  return value == null ? "—" : `${vnd.format(Math.round(value))} ₫`;
}

/** 0,84 → "84%" */
export function formatPct(ratio: number | null | undefined): string {
  return ratio == null ? "—" : `${Math.round(ratio * 100)}%`;
}

/** Số giây còn lại → "mm:ss" (âm thì "00:00"). */
export function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * Định dạng thời lượng theo tiếng Việt dễ đọc:
 * - < 60 phút → "45 phút"
 * - >= 60 phút → "23 giờ 6 phút" hoặc "2 giờ" (nếu tròn giờ)
 */
export function formatDuration(minutes: number | null | undefined): string {
  if (minutes == null || !Number.isFinite(minutes)) return "—";
  const total = Math.max(0, Math.round(minutes));
  if (total < 60) return `${total} phút`;
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  return mins === 0 ? `${hours} giờ` : `${hours} giờ ${mins} phút`;
}

/**
 * Tính số phút dự phòng giữa hai mốc ISO sau khi căn về phút tròn (khớp HH:MM hiển thị trên UI),
 * tránh lệch 1 phút khi timestamp gốc có phần giây lẻ (vd 18:24:38 → 17:30:00 = 1386 phút).
 */
export function computeBufferMinutes(
  plannedEndIso: string | null | undefined,
  deadlineIso: string | null | undefined,
  fallbackMinutes?: number | null,
): number | null {
  if (plannedEndIso && deadlineIso) {
    const endMs = new Date(plannedEndIso).getTime();
    const dlMs = new Date(deadlineIso).getTime();
    if (!Number.isNaN(endMs) && !Number.isNaN(dlMs)) {
      const endMin = Math.floor(endMs / 60_000);
      const dlMin = Math.floor(dlMs / 60_000);
      return Math.max(0, dlMin - endMin);
    }
  }
  return fallbackMinutes ?? null;
}

/** Chuẩn hoá dấu thập phân tiếng Việt (dấu phẩy) cho chuỗi số có đơn vị như "30.7 kWh" → "30,7 kWh". */
export function formatViNumbers(text: string): string {
  return text.replace(/(\d+)\.(\d+)(\s*(?:kWh|kW|%))/gi, "$1,$2$3");
}
