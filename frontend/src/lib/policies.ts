/**
 * Policy của Planning Core lấy từ registry backend (GET /api/v1/simulation/policies — Final Acceptance §4.1).
 * Không có danh sách cứng: policy mới đăng ký ở `src/optimizer/registry.py` tự hiện trong dropdown, gửi đi bằng `policy_id`.
 */
import type { components } from "@/lib/api/schema";

export type PolicyInfo = components["schemas"]["PolicyInfo"];

/** Policy mặc định của runtime live (LIVE_STRATEGY) — chọn sẵn nếu registry có. */
export const DEFAULT_POLICY_ID = "M3a";

export type PolicyOption = { id: string; label: string };

/** Nhãn dropdown: `id · mô tả` (+ version nếu không phải "1", + "thử nghiệm" nếu không phải bản đóng băng). */
export function policyLabel(policy: PolicyInfo): string {
  const parts = [policy.policy_id];
  if (policy.description) parts.push(policy.description);
  let label = parts.join(" · ");
  if (policy.version !== "1") label += ` (v${policy.version})`;
  if (!policy.frozen) label += " — thử nghiệm";
  if (policy.policy_id === DEFAULT_POLICY_ID) label += " (mặc định)";
  return label;
}

export function policyOptions(policies: PolicyInfo[] | undefined): PolicyOption[] {
  return (policies ?? []).map((p) => ({ id: p.policy_id, label: policyLabel(p) }));
}

/** Policy được chọn: lựa chọn của người dùng nếu còn hợp lệ, không thì M3a, không thì policy đầu tiên. */
export function selectedPolicy(policies: PolicyInfo[] | undefined, chosen: string): string {
  const ids = (policies ?? []).map((p) => p.policy_id);
  if (chosen && ids.includes(chosen)) return chosen;
  if (ids.includes(DEFAULT_POLICY_ID)) return DEFAULT_POLICY_ID;
  return ids[0] ?? "";
}

/** Id policy của một run / lịch: `policy_id` (registry, có cả policy mới); `strategy` chỉ là enum cũ B0–M3b. */
export function policyOf(item: { policy_id?: string | null; strategy?: string | null }): string {
  return item.policy_id ?? item.strategy ?? "?";
}
