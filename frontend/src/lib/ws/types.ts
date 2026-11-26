/**
 * Kiểu bản tin WebSocket. Phong bì và payload KHÔNG tự có trên OpenAPI, nên file này (viết tay, ngắn)
 * ánh xạ `type` → model ĐÃ được sinh trong schema.d.ts. Bảng gốc: src/models/events.py:WS_PAYLOAD_MODELS
 * và docs/plan/10-backend.md §8 — đổi ở backend thì sửa ở đây.
 */
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];

export type WsPayloads = {
  station_snapshot: Schemas["StationOverview"];
  event: Schemas["StationEvent"];
  /** Vận hành nhận SchedulePlan; cư dân nhận ResidentSessionView của chính mình. */
  schedule_changed: Schemas["SchedulePlan"] | Schemas["ResidentSessionView"];
  approval_request: Schemas["Approval"];
  command_blocked: Schemas["DecisionLogEntry"];
  notification: Schemas["Notification"];
  /** G24: sơ đồ bãi đổi — cư dân làm mới /resident/site-map (chỉ chứa trạng thái công khai). */
  site_occupancy: Schemas["ResidentSiteMap"];
  pong: Record<string, never>;
};

export type WsMessageType = keyof WsPayloads;

export type WsMessage = {
  [Type in WsMessageType]: { type: Type; payload: WsPayloads[Type]; sent_at: string };
}[WsMessageType];

/** Bản tin client gửi lên. Token đi trong bản tin đầu, KHÔNG nằm trên URL (ADR-006). */
export type WsClientMessage = { type: "auth"; token: string } | { type: "ping" };

/** Mã đóng do backend quy ước (src/api/ws.py). */
export const WS_CLOSE = {
  UNAUTHENTICATED: 4401,
  FORBIDDEN: 4403,
  NOT_IMPLEMENTED: 1011,
} as const;
