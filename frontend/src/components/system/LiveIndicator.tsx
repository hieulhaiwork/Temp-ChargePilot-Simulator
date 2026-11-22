import type { StreamState } from "@/lib/ws/useStream";

/** Trạng thái kết nối realtime ở header. Dùng CHỮ, không chỉ dựa vào màu (accessibility). */
const LABELS: Record<StreamState["status"], string> = {
  idle: "Chưa kết nối",
  connecting: "Đang kết nối…",
  open: "Trực tiếp",
  reconnecting: "Đang kết nối lại…",
  closed: "Ngoại tuyến",
  unauthorized: "Hết phiên đăng nhập",
  forbidden: "Không có quyền nhận dữ liệu trực tiếp",
  not_implemented: "Realtime chưa cài [T3.6] · làm mới định kỳ",
};

/** Màu đi kèm chữ: xanh = trực tiếp, vàng = đang nối / thăm dò, đỏ = không nhận được dữ liệu trực tiếp. */
const TONE: Record<StreamState["status"], "" | "gold" | "off"> = {
  idle: "gold",
  connecting: "gold",
  open: "",
  reconnecting: "gold",
  closed: "off",
  unauthorized: "off",
  forbidden: "off",
  not_implemented: "gold",
};

export function LiveIndicator({ state }: { state: StreamState }) {
  return (
    <span role="status" aria-live="polite" className={`live ${TONE[state.status]}`}>
      <i aria-hidden="true" />
      {LABELS[state.status]}
    </span>
  );
}
