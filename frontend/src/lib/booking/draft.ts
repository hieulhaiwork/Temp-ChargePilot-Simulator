/**
 * Phương án đang xem (chưa đặt) — chuyển từ /resident/book sang /resident/plan.
 * Giữ trong sessionStorage của tab: không lưu lâu, không gửi đi đâu, mất khi đóng tab. Đặt lịch xong thì xoá.
 */
import type { components } from "@/lib/api/schema";

export type ChargeRequest = components["schemas"]["ChargeRequest"];
export type ScheduleProposal = components["schemas"]["ScheduleProposal"];
export type Draft = { request: ChargeRequest; proposal: ScheduleProposal; createdAt: string };

const KEY = "chargepilot.draft";

export function saveDraft(draft: Draft): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(draft));
  } catch {
    /* chế độ riêng tư chặn storage — màn S3 sẽ báo "chưa có phương án" */
  }
}

export function loadDraft(): Draft | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Draft) : null;
  } catch {
    return null;
  }
}

export function clearDraft(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* bỏ qua */
  }
}
