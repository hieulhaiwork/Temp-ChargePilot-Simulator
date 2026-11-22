"use client";

/**
 * S4 · Đề nghị điều chỉnh (mockup cu-dan/resident-approval.html; spec 21 §2.6; FR13, FR14 · US4 · AC4).
 * QUAN TRỌNG (AC4, PRD thắng Wireframe): đồng hồ là "Hết hạn sau mm:ss". Hết hạn mà cư dân chưa trả lời
 * thì điều chỉnh KHÔNG được áp dụng — không có "tự áp dụng". expires_at = null → không hiện đồng hồ (G8).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { KeyValues, Notice, PageHead, Panel, SectionHead, Tag } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";
import { formatCountdown, formatKw, formatTime } from "@/lib/format";

type Approval = components["schemas"]["Approval"];

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function ApprovalBody({ approval }: { approval: Approval }) {
  const queryClient = useQueryClient();
  const now = useNow();
  const [note, setNote] = useState("");
  const left = approval.expires_at ? (new Date(approval.expires_at).getTime() - now) / 1000 : null;
  const expired = approval.status === "expired" || (left != null && left <= 0);
  const decided = approval.status === "approved" || approval.status === "rejected";
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      unwrap(
        api.POST("/api/v1/resident/approvals/{approval_id}", {
          params: { path: { approval_id: approval.approval_id ?? "" } },
          body: { decision, note: note.trim() || null },
        }),
      ),
    onSuccess: (updated) => queryClient.setQueryData(queries.residentApproval(approval.approval_id ?? "").queryKey, updated),
  });
  const cmd = approval.command;

  return (
    <div className="cols">
      <div className="stack">
        <Panel label="Tác động tới lịch">
          <SectionHead title="Tác động tới lịch của bạn" icon="clock" extra={<Tag tone={approval.verdict.passed ? "good" : "bad"}>{approval.verdict.passed ? "Guard đã kiểm: đạt" : "Guard chặn"}</Tag>} />
          <p style={{ fontSize: 15 }}>{approval.impact_summary}</p>
          <div style={{ marginTop: 14 }}>
            <KeyValues
              rows={[
                ["Đầu nối", cmd.connector_id],
                ["Công suất đề nghị", cmd.power_kw != null ? formatKw(cmd.power_kw) : "—"],
                ["Đề nghị lúc", formatTime(approval.created_at)],
                ["Lý do", cmd.reason || "—"],
              ]}
            />
          </div>
        </Panel>
      </div>
      <aside className="stack">
        <Panel label="Quyết định">
          <SectionHead title="Quyết định của bạn" icon="adjust" />
          {decided ? (
            <Notice title={approval.status === "approved" ? "Bạn đã đồng ý" : "Bạn đã từ chối"} tone="good" icon="checkcircle">
              Ghi nhận lúc {formatTime(approval.decided_at)}. {approval.status === "approved" ? "Trạm kiểm lại điều kiện trước khi áp dụng." : "Lịch trước đề nghị được giữ nguyên."}
            </Notice>
          ) : expired ? (
            <Notice title="Đề nghị đã hết hạn" tone="gold" icon="clock">
              Điều chỉnh không được áp dụng. Lịch trước đề nghị được giữ nguyên.
            </Notice>
          ) : (
            <>
              {left != null ? (
                <p role="timer" aria-live="off" className="num" style={{ fontSize: 28, fontWeight: 700, color: left <= 60 ? "var(--red)" : undefined }}>
                  Hết hạn sau {formatCountdown(left)}
                </p>
              ) : (
                <p className="hint">Đề nghị này chưa có thời hạn trả lời.</p>
              )}
              <p className="hint">Nếu bạn không trả lời trước khi hết hạn, điều chỉnh sẽ không được áp dụng.</p>
              <div className="field" style={{ marginTop: 12 }}>
                <label htmlFor="answer-note">Ghi chú (không bắt buộc)</label>
                <textarea id="answer-note" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
                <span className="hint">{note.length}/500 ký tự</span>
              </div>
              <div className="actions">
                <button type="button" className="btn btn-primary" disabled={decide.isPending} onClick={() => decide.mutate("approve")}>
                  <Icon name="check" />
                  Đồng ý
                </button>
                <button type="button" className="btn btn-secondary" disabled={decide.isPending} onClick={() => decide.mutate("reject")}>
                  Từ chối
                </button>
              </div>
            </>
          )}
          {decide.isError ? (
            <div style={{ marginTop: 12 }}>
              {decide.error instanceof ApiError && decide.error.isNotImplemented ? (
                <NotImplementedPanel endpoint="POST /api/v1/resident/approvals/{approval_id}" taskId={decide.error.taskId} detail={decide.error.detail} />
              ) : (
                <ErrorPanel error={decide.error} />
              )}
            </div>
          ) : null}
        </Panel>
      </aside>
    </div>
  );
}

export function ApprovalScreen() {
  const { approvalId } = useParams<{ approvalId: string }>();
  return (
    <>
      <Link href="/resident/notifications" className="textbtn">
        <Icon name="back" />
        Về thông báo
      </Link>
      <PageHead title="Đề nghị điều chỉnh" sub="Trạm muốn điều chỉnh lịch của bạn ngoài phạm vi đã đồng ý trước." />
      <DataBlock endpoint={`GET /api/v1/resident/approvals/${approvalId}`} query={queries.residentApproval(approvalId)}>
        {(approval) => <ApprovalBody approval={approval} />}
      </DataBlock>
    </>
  );
}
