"use client";

/**
 * S7 · Duyệt lệnh (mockup docs/mockups/van-hanh/operator-approvals.html; spec 21 §3.3; FR12, FR13, FR14, FR16 · US7 · AC4, AC6 · MT6).
 * Ba tab: Chờ duyệt · Bị Guard chặn (luật, phiên bản lịch, thời điểm trạng thái, ai ra lệnh) · Nhật ký quyết định.
 * Đề nghị loại resident_consent chỉ theo dõi — chỉ cư dân được trả lời (403 nếu vận hành gửi).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { EmptyState, KeyValues, PageHead, Panel, SectionHead, Tag } from "@/components/ui/blocks";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";
import { formatKw, formatTime } from "@/lib/format";
import { usePollFallback } from "@/lib/ws/useStream";

type Approval = components["schemas"]["Approval"];
type Entry = components["schemas"]["DecisionLogEntry"];
type Command = components["schemas"]["Command"];
type Rule = components["schemas"]["GuardRule"];
type Source = components["schemas"]["CommandSource"];

/** Tên luật theo src/models/control.py (GuardRule) — hiện kèm mã luật để đối chiếu nhật ký. */
const RULE: Record<Rule, string> = {
  total_power_limit: "Giới hạn tổng công suất",
  connector_power_limit: "Giới hạn công suất đầu nối",
  anti_flapping: "Chống đổi lệnh liên tục",
  stale_state: "Dữ liệu trạng thái cũ",
  permission: "Quyền ra lệnh",
  schedule_version: "Phiên bản lịch",
  conflicting_commands: "Lệnh xung đột",
};
const SOURCE: Record<Source, string> = {
  optimizer: "Optimizer",
  load_balancer: "Cân bằng tải",
  emergency: "Bảo vệ khẩn cấp",
  operator: "Vận hành",
  agent: "Trợ lý (Agent)",
};
const cmdText = (c: Command) => `${c.type} ${c.connector_id}${c.power_kw != null ? ` = ${formatKw(c.power_kw)}` : ""}${c.booking_id ? ` ← ${c.booking_id}` : ""}`;
type TabKey = "pending" | "blocked" | "log";

function MutationError({ error }: { error: unknown }) {
  if (!error) return null;
  return error instanceof ApiError && error.isNotImplemented ? (
    <NotImplementedPanel endpoint="POST /api/v1/operator/approvals/{approval_id}" taskId={error.taskId} detail={error.detail} />
  ) : (
    <ErrorPanel error={error} />
  );
}

function PendingTab({ items }: { items: Approval[] }) {
  const queryClient = useQueryClient();
  const pending = items.filter((a) => a.status === "pending");
  const [sel, setSel] = useState<string | undefined>(pending[0]?.approval_id);
  const [note, setNote] = useState("");
  const current = pending.find((a) => a.approval_id === sel) ?? pending[0];
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) =>
      unwrap(api.POST("/api/v1/operator/approvals/{approval_id}", { params: { path: { approval_id: id } }, body: { decision, note: note.trim() || null } })),
    onSuccess: () => {
      setNote("");
      void queryClient.invalidateQueries({ queryKey: ["operator"] });
    },
  });
  if (!pending.length) {
    return (
      <Panel>
        <EmptyState icon="checkcircle" title="Không có lệnh nào chờ duyệt">
          Đề nghị mới hiện ở đây ngay khi Guard cho qua và cần người duyệt.
        </EmptyState>
      </Panel>
    );
  }
  return (
    <div className="cols">
      <Panel label="Đề nghị chờ duyệt">
        <div className="tbl-wrap">
          <table className="tbl">
            <caption>Mỗi đề nghị đã qua Guard. Hết hạn mà chưa duyệt thì không thực thi.</caption>
            <thead>
              <tr>
                <th>Đề nghị</th>
                <th>Loại</th>
                <th>Nguồn</th>
                <th>Hết hạn</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((a) => (
                <tr key={a.approval_id} className={a === current ? "sel" : ""}>
                  <td>
                    <button type="button" className="textbtn" style={{ color: "var(--ink)" }} aria-pressed={a === current} onClick={() => setSel(a.approval_id)}>
                      {cmdText(a.command)}
                    </button>
                    <small className="hint" style={{ display: "block" }}>
                      {a.impact_summary}
                    </small>
                  </td>
                  <td>{a.kind === "resident_consent" ? <Tag>Cư dân đồng ý</Tag> : <Tag tone="gold">Vận hành duyệt</Tag>}</td>
                  <td>{SOURCE[a.command.source]}</td>
                  <td className="num">{a.expires_at ? formatTime(a.expires_at) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {current ? (
        <Panel label="Chi tiết đề nghị">
          <SectionHead title={cmdText(current.command)} icon="shield" />
          <p className="subcopy">{current.impact_summary}</p>
          <div style={{ marginTop: 12 }}>
            <KeyValues
              rows={[
                ["Nguồn", `${SOURCE[current.command.source]} · ${current.command.issued_by}`],
                ["Guard", current.verdict.passed ? <Tag key="g" tone="good">Đạt</Tag> : <Tag key="g" tone="bad">Chặn</Tag>],
                ["Dựa trên lịch", `v${current.command.based_on_schedule_version}`],
                ["Dựa trên trạng thái lúc", formatTime(current.command.based_on_state_at)],
                ["Hết hạn", current.expires_at ? formatTime(current.expires_at) : "Không có thời hạn"],
              ]}
            />
          </div>
          {current.kind === "resident_consent" ? (
            <p className="hint" style={{ marginTop: 12 }}>
              Chỉ cư dân được trả lời đề nghị này. Vận hành chỉ theo dõi.
            </p>
          ) : (
            <>
              <div className="field" style={{ marginTop: 14 }}>
                <label htmlFor="ap-note">Ghi chú (không bắt buộc)</label>
                <textarea id="ap-note" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
              </div>
              <div className="actions">
                <button type="button" className="btn btn-primary" disabled={decide.isPending} onClick={() => decide.mutate({ id: current.approval_id ?? "", decision: "approve" })}>
                  {decide.isPending ? "Đang gửi…" : "Duyệt"}
                </button>
                <button type="button" className="btn btn-secondary" disabled={decide.isPending} onClick={() => decide.mutate({ id: current.approval_id ?? "", decision: "reject" })}>
                  Từ chối
                </button>
              </div>
              {decide.isSuccess ? (
                <p role="status" className="hint">
                  Đã ghi nhận quyết định · xem kết quả thực thi ở Nhật ký.
                </p>
              ) : null}
              <MutationError error={decide.error} />
            </>
          )}
        </Panel>
      ) : null}
    </div>
  );
}

function BlockedTab({ entries }: { entries: Entry[] }) {
  const [sel, setSel] = useState(0);
  if (!entries.length) {
    return (
      <Panel>
        <EmptyState icon="shield" title="Chưa có lệnh nào bị chặn" />
      </Panel>
    );
  }
  const e = entries[Math.min(sel, entries.length - 1)];
  const v = e.verdict?.violations ?? [];
  return (
    <div className="cols">
      <Panel label="Lệnh bị chặn">
        <div className="tbl-wrap">
          <table className="tbl">
            <caption>Lệnh Guard đã chặn. Không lệnh nào trong đây được gửi tới trạm.</caption>
            <thead>
              <tr>
                <th>Lúc</th>
                <th>Lệnh</th>
                <th>Luật</th>
                <th>Nguồn</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((x, i) => (
                <tr key={x.entry_id ?? x.timestamp} className={i === sel ? "sel" : ""}>
                  <td>{formatTime(x.timestamp)}</td>
                  <td>
                    <button type="button" className="textbtn" style={{ color: "var(--ink)" }} aria-pressed={i === sel} onClick={() => setSel(i)}>
                      {cmdText(x.command)}
                    </button>
                  </td>
                  <td>
                    {(x.verdict?.violations ?? []).map((vi) => (
                      <Tag key={vi.rule} tone="bad" icon="ban">
                        {RULE[vi.rule]}
                      </Tag>
                    ))}
                  </td>
                  <td>{SOURCE[x.command.source]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel label="Lý do bị chặn">
        <SectionHead title="Lý do bị chặn" icon="ban" />
        {v.map((vi) => (
          <p key={vi.rule} className="subcopy">
            <b>{RULE[vi.rule]}</b> (<code>{vi.rule}</code>): {vi.detail}
          </p>
        ))}
        <div style={{ marginTop: 12 }}>
          <KeyValues
            rows={[
              ["Lệnh", cmdText(e.command)],
              ["Mã lệnh", e.command.command_id ?? "—"],
              ["Dựa trên lịch", `v${e.command.based_on_schedule_version}`],
              ["Dựa trên trạng thái lúc", formatTime(e.command.based_on_state_at)],
              ["Người / thành phần ra lệnh", e.command.issued_by],
              ["Guard kiểm lúc", formatTime(e.verdict?.checked_at)],
            ]}
          />
        </div>
      </Panel>
    </div>
  );
}

function LogTab({ entries }: { entries: Entry[] }) {
  const [f, setF] = useState<"all" | "passed" | "blocked" | "human">("all");
  const rows = entries.filter((e) =>
    f === "all" ? true : f === "blocked" ? e.verdict?.passed === false : f === "human" ? Boolean(e.approved_by) || e.command.source === "operator" : e.verdict?.passed !== false,
  );
  return (
    <Panel label="Nhật ký quyết định">
      <div className="seg" role="group" aria-label="Lọc nhật ký" style={{ marginBottom: 12 }}>
        {(
          [
            ["all", "Tất cả"],
            ["passed", "Guard cho qua"],
            ["blocked", "Bị chặn"],
            ["human", "Có người quyết"],
          ] as const
        ).map(([k, l]) => (
          <button key={k} type="button" aria-pressed={f === k} onClick={() => setF(k)}>
            {l}
          </button>
        ))}
      </div>
      {rows.length ? (
        <div className="tbl-wrap">
          <table className="tbl">
            <caption>Ai đề xuất · Guard kết luận gì · ai duyệt · có thực thi không (FR14).</caption>
            <thead>
              <tr>
                <th>Lúc</th>
                <th>Nguồn</th>
                <th>Lệnh</th>
                <th>Guard</th>
                <th>Người duyệt</th>
                <th>Thực thi</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.entry_id ?? e.timestamp}>
                  <td>{formatTime(e.timestamp)}</td>
                  <td>{SOURCE[e.command.source]}</td>
                  <td>{cmdText(e.command)}</td>
                  <td>{e.verdict ? e.verdict.passed ? <Tag tone="good">Đạt</Tag> : <Tag tone="bad">Chặn</Tag> : "—"}</td>
                  <td>{e.approved_by ?? (e.approval_id ? "Chờ duyệt" : "Tự động")}</td>
                  <td>{e.executed ? "Đã thực thi" : "Không"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="subcopy">Nhật ký trống.</p>
      )}
    </Panel>
  );
}

export default function OperatorApprovalsPage() {
  const poll = usePollFallback();
  const [tab, setTab] = useState<TabKey>("pending");
  return (
    <>
      <PageHead
        title="Duyệt lệnh"
        sub="Đề nghị cần người duyệt, lệnh Guard đã chặn và nhật ký mọi quyết định."
        actions={
          <div className="seg" role="tablist" aria-label="Loại danh sách">
            {(
              [
                ["pending", "Chờ duyệt"],
                ["blocked", "Bị Guard chặn"],
                ["log", "Nhật ký quyết định"],
              ] as const
            ).map(([k, l]) => (
              <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
                {l}
              </button>
            ))}
          </div>
        }
      />
      <div role="tabpanel">
        {tab === "pending" ? (
          <DataBlock endpoint="GET /api/v1/operator/approvals" query={queries.operatorApprovals()} refetchInterval={poll} loadingLines={5}>
            {(items) => <PendingTab items={items} />}
          </DataBlock>
        ) : tab === "blocked" ? (
          <DataBlock endpoint="GET /api/v1/operator/commands/blocked" query={queries.operatorBlocked()} refetchInterval={poll} loadingLines={5}>
            {(entries) => <BlockedTab entries={entries} />}
          </DataBlock>
        ) : (
          <DataBlock endpoint="GET /api/v1/operator/decision-log" query={queries.operatorDecisionLog()} refetchInterval={poll} loadingLines={5}>
            {(entries) => <LogTab entries={entries} />}
          </DataBlock>
        )}
      </div>
    </>
  );
}
