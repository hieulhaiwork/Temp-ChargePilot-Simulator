import { Icon } from "@/components/ui/Icon";

/**
 * Hiện rõ "backend chưa cài phần này" (HTTP 501, ADR-004) kèm task ID để nhóm biết việc còn thiếu.
 * Bọc theo TỪNG KHỐI dữ liệu: một endpoint 501 không làm hỏng phần còn lại của trang.
 */
export function NotImplementedPanel({
  endpoint,
  taskId,
  detail,
}: {
  endpoint: string;
  taskId: string | null;
  detail?: string;
}) {
  return (
    <div role="status" className="notice notice-gold">
      <Icon name="plug" />
      <div>
        <strong>
          Chức năng này chưa được cài đặt{taskId ? <span> — task {taskId}</span> : null}
        </strong>
        <p className="num" style={{ fontSize: 12 }}>
          {endpoint}
        </p>
        {detail ? <p style={{ fontSize: 12 }}>{detail}</p> : null}
      </div>
    </div>
  );
}
