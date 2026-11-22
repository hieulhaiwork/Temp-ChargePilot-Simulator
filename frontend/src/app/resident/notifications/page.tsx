"use client";

/**
 * Thông báo (mockup cu-dan/resident-notifications.html; spec 21 §2.5; FR15, FR13 · AC4, AC5 · US4).
 * Ba bộ lọc Tất cả / Chưa đọc / Cần phản hồi; mở chi tiết thì đánh dấu đã đọc (POST …/read).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { EmptyState, PageHead, Panel, Tag, type Tone } from "@/components/ui/blocks";
import { Icon, type IconName } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { queries } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";
import { formatDate, formatTime } from "@/lib/format";
import { usePollFallback } from "@/lib/ws/useStream";

type Kind = components["schemas"]["NotificationKind"];
const KIND: Record<Kind, [string, Tone, IconName]> = {
  approval_request: ["Cần phản hồi", "gold", "adjust"],
  emergency_curtailment: ["Bảo vệ khẩn cấp", "bad", "shield"],
  schedule_changed: ["Lịch đã đổi", "blue", "calendar"],
  info: ["Thông tin", "neutral", "info"],
};
type Filter = "all" | "unread" | "action";

export default function ResidentNotificationsPage() {
  const poll = usePollFallback();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);
  const markRead = useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/api/v1/resident/notifications/{notification_id}/read", { params: { path: { notification_id: id } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["resident", "notifications"] }),
  });

  return (
    <>
      <PageHead title="Thông báo" sub="Cập nhật của trạm và những đề nghị cần bạn quyết định." />
      <Panel label="Hộp thư">
        <DataBlock endpoint="GET /api/v1/resident/notifications" query={queries.residentNotifications()} refetchInterval={poll} loadingLines={5}>
          {(items) => {
            const unread = items.filter((n) => !n.read).length;
            const shown = items.filter((n) => (filter === "unread" ? !n.read : filter === "action" ? n.kind === "approval_request" : true));
            return (
              <>
                <div className="seg" role="group" aria-label="Lọc thông báo" style={{ marginBottom: 16 }}>
                  {(
                    [
                      ["all", "Tất cả"],
                      ["unread", `Chưa đọc (${unread})`],
                      ["action", "Cần phản hồi"],
                    ] as const
                  ).map(([k, l]) => (
                    <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>
                      {l}
                    </button>
                  ))}
                </div>
                {shown.length === 0 ? (
                  <EmptyState icon="bell" title={items.length ? "Không có tin phù hợp" : "Hộp thư trống"}>
                    Tin mới của trạm sẽ hiện ở đây.
                  </EmptyState>
                ) : (
                  <ul className="stack" style={{ gap: 10, listStyle: "none", margin: 0, padding: 0 }}>
                    {shown.map((n) => {
                      const [label, tone, icon] = KIND[n.kind];
                      const expanded = open === n.notification_id;
                      return (
                        <li key={n.notification_id} className="notice" style={{ background: n.read ? "#fff" : undefined }}>
                          <Icon name={icon} />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <p style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                              <Tag tone={tone}>{label}</Tag>
                              {!n.read ? <Tag tone="gold">Chưa đọc</Tag> : null}
                              <span className="hint">
                                {formatTime(n.created_at)} · {formatDate(n.created_at)}
                              </span>
                            </p>
                            <strong style={{ marginTop: 6 }}>{n.title}</strong>
                            {expanded ? <p>{n.body}</p> : null}
                            <div className="actions" style={{ marginTop: 6 }}>
                              <button
                                type="button"
                                className="textbtn"
                                aria-expanded={expanded}
                                onClick={() => {
                                  setOpen(expanded ? null : n.notification_id);
                                  if (!n.read) markRead.mutate(n.notification_id);
                                }}
                              >
                                {expanded ? "Thu gọn" : "Xem thêm"}
                              </button>
                              {n.approval_id ? (
                                <Link href={`/resident/notifications/${n.approval_id}`} className="btn btn-primary small">
                                  Trả lời đề nghị
                                </Link>
                              ) : null}
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {markRead.isError ? <ErrorPanel error={markRead.error} /> : null}
              </>
            );
          }}
        </DataBlock>
      </Panel>
    </>
  );
}
