/**
 * Query key + query function cho từng endpoint GET mà các màn S1–S8 dùng (docs/plan/20-frontend.md §3).
 * Mỗi mục là một `queryOptions` của TanStack Query: dùng cho useQuery, invalidateQueries và setQueryData
 * (khi WebSocket đẩy dữ liệu mới) với cùng một khoá.
 */
import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "./client";

export const queries = {
  // Hệ thống
  health: () =>
    queryOptions({
      queryKey: ["system", "health"],
      queryFn: ({ signal }) => unwrap(api.GET("/health", { signal })),
    }),

  // Dữ liệu tham chiếu công khai
  vehicles: () => queryOptions({ queryKey: ["catalog", "vehicles"], queryFn: () => unwrap(api.GET("/api/v1/vehicles")) }),
  tariff: () => queryOptions({ queryKey: ["catalog", "tariff"], queryFn: () => unwrap(api.GET("/api/v1/tariff")) }),
  stationConfig: () =>
    queryOptions({ queryKey: ["catalog", "station-config"], queryFn: () => unwrap(api.GET("/api/v1/station/config")) }),

  // Phiên đăng nhập
  me: () => queryOptions({ queryKey: ["auth", "me"], queryFn: () => unwrap(api.GET("/api/v1/auth/me")) }),

  // Cư dân — S2, S3, S4
  residentSession: () =>
    queryOptions({ queryKey: ["resident", "session"], queryFn: () => unwrap(api.GET("/api/v1/resident/session")) }),
  residentBooking: () =>
    queryOptions({
      queryKey: ["resident", "booking"],
      queryFn: () => unwrap(api.GET("/api/v1/resident/bookings/current")),
    }),
  residentQueue: () =>
    queryOptions({ queryKey: ["resident", "queue"], queryFn: () => unwrap(api.GET("/api/v1/resident/queue")) }),
  residentNotifications: () =>
    queryOptions({
      queryKey: ["resident", "notifications"],
      queryFn: () => unwrap(api.GET("/api/v1/resident/notifications")),
    }),
  residentExplanation: () =>
    queryOptions({
      queryKey: ["resident", "explanation"],
      queryFn: () => unwrap(api.GET("/api/v1/resident/explanation")),
    }),
  residentProfile: () =>
    queryOptions({ queryKey: ["resident", "profile"], queryFn: () => unwrap(api.GET("/api/v1/resident/profile")) }),
  residentApproval: (approvalId: string) =>
    queryOptions({
      queryKey: ["resident", "approval", approvalId],
      queryFn: () =>
        unwrap(
          api.GET("/api/v1/resident/approvals/{approval_id}", { params: { path: { approval_id: approvalId } } }),
        ),
    }),

  // Vận hành — S5, S6, S7
  operatorStation: () =>
    queryOptions({ queryKey: ["operator", "station"], queryFn: () => unwrap(api.GET("/api/v1/operator/station")) }),
  operatorLoad: (hours = 24) =>
    queryOptions({
      queryKey: ["operator", "load", hours],
      queryFn: () => unwrap(api.GET("/api/v1/operator/load", { params: { query: { hours } } })),
    }),
  operatorEvents: () =>
    queryOptions({ queryKey: ["operator", "events"], queryFn: () => unwrap(api.GET("/api/v1/operator/events")) }),
  operatorSchedule: () =>
    queryOptions({ queryKey: ["operator", "schedule"], queryFn: () => unwrap(api.GET("/api/v1/operator/schedule")) }),
  operatorQueue: () =>
    queryOptions({
      queryKey: ["operator", "bookings", "queued"],
      queryFn: () => unwrap(api.GET("/api/v1/operator/bookings", { params: { query: { status: "queued" } } })),
    }),
  operatorApprovals: () =>
    queryOptions({
      queryKey: ["operator", "approvals"],
      queryFn: () => unwrap(api.GET("/api/v1/operator/approvals")),
    }),
  operatorBlocked: () =>
    queryOptions({
      queryKey: ["operator", "blocked"],
      queryFn: () => unwrap(api.GET("/api/v1/operator/commands/blocked")),
    }),
  operatorDecisionLog: () =>
    queryOptions({
      queryKey: ["operator", "decision-log"],
      queryFn: () => unwrap(api.GET("/api/v1/operator/decision-log")),
    }),

  // Mô phỏng — S8
  scenarios: () =>
    queryOptions({
      queryKey: ["simulation", "scenarios"],
      queryFn: () => unwrap(api.GET("/api/v1/simulation/scenarios")),
    }),
  benchmark: () =>
    queryOptions({
      queryKey: ["simulation", "benchmark"],
      queryFn: () => unwrap(api.GET("/api/v1/simulation/benchmark")),
    }),
  policies: () =>
    queryOptions({
      queryKey: ["simulation", "policies"],
      queryFn: () => unwrap(api.GET("/api/v1/simulation/policies")),
    }),
};
