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
