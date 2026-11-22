import { Icon } from "@/components/ui/Icon";
import { ApiError, type ApiErrorCode } from "@/lib/api/errors";

/** Thông điệp cho người dùng theo mã lỗi của backend (ADR-008). Mã không có ở đây → dùng `detail`. */
const MESSAGES: Partial<Record<ApiErrorCode, string>> = {
  network_error: "Không kết nối được máy chủ. Máy chủ có thể đang khởi động — thử lại sau ít phút.",
  unauthenticated: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
  forbidden: "Bạn không có quyền xem nội dung này.",
  booking_conflict: "Bạn đang có một lịch sạc còn hiệu lực.",
  proposal_expired: "Trạng thái trạm đã thay đổi — vui lòng xem lại phương án mới.",
  approval_already_decided: "Yêu cầu này đã được xử lý.",
  no_pending_confirmation: "Phiên chat không còn chờ xác nhận. Bạn có thể đặt lịch bằng form.",
  llm_unavailable: "Trợ lý tạm thời không dùng được. Bạn có thể đặt lịch bằng form.",
  database_unavailable: "Cơ sở dữ liệu tạm thời không truy cập được. Thử lại sau ít phút.",
  internal_error: "Máy chủ gặp lỗi. Vui lòng thử lại.",
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return MESSAGES[error.code] ?? error.detail;
  return "Đã xảy ra lỗi không xác định.";
}

export function ErrorPanel({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof ApiError ? error : null;
  return (
    <div role="alert" className="notice notice-bad">
      <Icon name="wifi" />
      <div>
        <strong>{errorMessage(error)}</strong>
        {apiError && apiError.fields.length > 0 ? (
          <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 12 }}>
            {apiError.fields.map((field) => (
              <li key={`${field.path}:${field.message}`}>
                {field.path ? `${field.path}: ` : ""}
                {field.message}
              </li>
            ))}
          </ul>
        ) : null}
        {apiError?.requestId ? <p className="num" style={{ fontSize: 12 }}>Mã yêu cầu: {apiError.requestId}</p> : null}
        {onRetry ? (
          <button type="button" onClick={onRetry} className="textbtn" style={{ color: "var(--red)" }}>
            <Icon name="refresh" />
            Thử lại
          </button>
        ) : null}
      </div>
    </div>
  );
}
