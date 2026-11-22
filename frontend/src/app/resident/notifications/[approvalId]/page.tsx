import { Suspense } from "react";

import { ApprovalScreen } from "./ApprovalScreen";

/** S4 · Thông báo HITL — đề nghị điều chỉnh vượt phạm vi cư dân đã đồng ý (AC4). */
export default function ResidentApprovalPage() {
  return (
    <Suspense fallback={<p role="status">Đang tải yêu cầu phê duyệt…</p>}>
      <ApprovalScreen />
    </Suspense>
  );
}
