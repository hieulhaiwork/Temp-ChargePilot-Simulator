"use client";

/**
 * Trợ lý sạc trên trang chủ cư dân (S2, mockup cu-dan/resident.html) — POST /chat, xác nhận bằng POST /chat/resume.
 * Số liệu phương án LUÔN lấy từ ChatResponse.proposal (dữ liệu có cấu trúc), không đọc từ câu chữ của LLM (FR3).
 * 503 llm_unavailable → mời dùng form đặt lịch (NFR khả dụng). Task: T3.3.
 */
import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { SectionHead } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { ApiError, toApiError, type ApiErrorCode } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { getToken } from "@/lib/auth/session";
import { API_URL } from "@/lib/env";
import { formatKwh, formatTime, formatVnd } from "@/lib/format";

type ChatResponse = components["schemas"]["ChatResponse"];
type Line = { id: string; who: "me" | "bot"; text: string; reply?: ChatResponse };

const MAX_LEN = 5000;
const SUGGESTIONS = ["Cần 80% trước 07:00 sáng mai.", "Vì sao lịch của tôi bắt đầu lúc 23:00?", "Đổi giờ lấy xe sang 06:30."];

export function ChatPanel() {
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamStatus, setStreamStatus] = useState("Trợ lý đang trả lời…");
  const [streamError, setStreamError] = useState<Error | null>(null);

  const send = useMutation({
    mutationFn: async ({ message, botLineId }: { message: string; botLineId: string }) => {
      setIsStreaming(true);
      setStreamError(null);
      setStreamStatus("Đang gửi yêu cầu…");
      const token = getToken();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`${API_URL}/api/v1/chat/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({ message, session_id: sessionId }),
      });
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => null);
        throw toApiError(res.status, body, res.headers.get("X-Request-ID"));
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalReply: ChatResponse | null = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const rawEvent of events) {
          const dataLine = rawEvent
            .split("\n")
            .find((line) => line.startsWith("data: "));
          if (!dataLine) continue;
          const evt = JSON.parse(dataLine.slice(6)) as {
            type: string;
            label?: string;
            text?: string;
            data?: ChatResponse;
            code?: string;
            detail?: string;
          };
          if (evt.type === "status" && evt.label) {
            setStreamStatus(evt.label);
          } else if (evt.type === "delta" && evt.text) {
            const deltaText = evt.text;
            setLines((prev) =>
              prev.map((l) => (l.id === botLineId ? { ...l, text: l.text + deltaText } : l)),
            );
          } else if (evt.type === "done" && evt.data) {
            finalReply = evt.data;
            const reply = evt.data;
            setSessionId(reply.session_id);
            setLines((prev) =>
              prev.map((l) => (l.id === botLineId ? { ...l, text: reply.response, reply } : l)),
            );
          } else if (evt.type === "error") {
            setLines((prev) => prev.filter((l) => l.id !== botLineId || l.text !== ""));
            throw new ApiError({
              status: 503,
              code: (evt.code as ApiErrorCode | undefined) ?? "llm_unavailable",
              detail: evt.detail ?? "Trợ lý tạm thời không dùng được.",
            });
          }
        }
      }
      if (!finalReply) {
        throw new ApiError({ status: 500, code: "internal_error", detail: "Luồng phản hồi kết thúc bất ngờ." });
      }
      return finalReply;
    },
    onError: (err) => {
      setStreamError(err instanceof Error ? err : new Error(String(err)));
    },
    onSettled: () => {
      setIsStreaming(false);
    },
  });
  const resume = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      unwrap(api.POST("/api/v1/chat/resume", { body: { session_id: sessionId ?? "", resume: decision } })),
    onSuccess: (reply) =>
      setLines((prev) => [...prev, { id: crypto.randomUUID(), who: "bot", text: reply.response, reply }]),
  });

  function submit(message: string) {
    const m = message.trim();
    if (!m || m.length > MAX_LEN || send.isPending || isStreaming) return;
    const turnId = crypto.randomUUID();
    const botLineId = `${turnId}:bot`;
    setLines((prev) => [
      ...prev,
      { id: `${turnId}:me`, who: "me", text: m },
      { id: botLineId, who: "bot", text: "" },
    ]);
    setText("");
    send.mutate({ message: m, botLineId });
  }
  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    submit(text);
  }

  const lastBot = [...lines].reverse().find((l) => l.who === "bot");
  const waitingConfirm = lastBot?.reply?.status === "needs_confirmation" && !resume.isSuccess;
  const effectiveError = streamError ?? send.error ?? resume.error;
  const llmDown = effectiveError instanceof ApiError && effectiveError.code === "llm_unavailable";
  const error = effectiveError;
  const tooLong = text.length > MAX_LEN;
  const quickReplies =
    lines.length === 0
      ? SUGGESTIONS
      : !waitingConfirm && !isStreaming && !send.isPending
        ? (lastBot?.reply?.suggestions ?? [])
        : [];

  return (
    <section className="panel" aria-labelledby="chat-h">
      <SectionHead
        title={<span id="chat-h">Trợ lý sạc</span>}
        icon="chat"
        sub="Nói nhu cầu bằng lời. Lịch chỉ được giữ chỗ khi bạn xác nhận."
        extra={
          lines.length ? (
            <button
              type="button"
              className="textbtn"
              onClick={() => {
                setLines([]);
                setSessionId(undefined);
                setStreamError(null);
                send.reset();
                resume.reset();
              }}
            >
              Cuộc trò chuyện mới
            </button>
          ) : null
        }
      />
      <div aria-live="polite" className="stack" style={{ gap: 10, maxHeight: 360, overflowY: "auto" }}>
        {lines.length === 0 ? <p className="subcopy">Ví dụ: “Cần 80% trước 07:00 sáng mai.”</p> : null}
        {lines.map((l) =>
          l.who === "bot" && !l.text && !l.reply ? null : (
            <div key={l.id} className={`chat-line ${l.who}`}>
              <p>{l.text}</p>
              {l.reply?.proposal ? <ProposalSummary proposal={l.reply.proposal} /> : null}
            </div>
          ),
        )}
        {send.isPending || isStreaming || resume.isPending ? (
          <p role="status" className="hint">
            {resume.isPending ? "Đang xử lý xác nhận…" : streamStatus}
          </p>
        ) : null}
      </div>
      {waitingConfirm ? (
        <div className="actions">
          <button type="button" className="btn btn-primary" disabled={resume.isPending} onClick={() => resume.mutate("approve")}>
            <Icon name="check" />
            Xác nhận lịch
          </button>
          <button type="button" className="btn btn-secondary" disabled={resume.isPending} onClick={() => resume.mutate("reject")}>
            Đổi phương án
          </button>
        </div>
      ) : null}
      {error ? (
        <div style={{ marginTop: 12 }}>
          {error instanceof ApiError && error.isNotImplemented ? (
            <NotImplementedPanel endpoint="POST /api/v1/chat" taskId={error.taskId} detail={error.detail} />
          ) : (
            <ErrorPanel error={error} />
          )}
          {llmDown || (error instanceof ApiError && error.status === 409) ? (
            <p style={{ marginTop: 8 }}>
              <Link href="/resident/book" className="textbtn">
                Đặt lịch bằng biểu mẫu
                <Icon name="arrow" />
              </Link>
            </p>
          ) : null}
        </div>
      ) : null}
      {quickReplies.length > 0 ? (
        <div className="actions" style={{ marginTop: 12 }}>
          {quickReplies.map((s) => (
            <button key={s} type="button" className="btn btn-secondary small" onClick={() => submit(s)}>
              {s}
            </button>
          ))}
        </div>
      ) : null}
      <form onSubmit={onSubmit} className="chat-form">
        <label htmlFor="chat-input" className="sr-only">
          Tin nhắn cho Trợ lý sạc
        </label>
        <input
          id="chat-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Nhập nhu cầu sạc…"
          aria-invalid={tooLong || undefined}
          aria-describedby="chat-hint"
        />
        <button type="submit" className="btn btn-primary" disabled={!text.trim() || tooLong || send.isPending} aria-label="Gửi">
          <Icon name="arrow" />
        </button>
      </form>
      <span id="chat-hint" className="hint" style={{ color: tooLong ? "var(--red)" : undefined }}>
        {tooLong ? "Tin nhắn tối đa 5.000 ký tự." : ""}
      </span>
    </section>
  );
}

function ProposalSummary({ proposal }: { proposal: components["schemas"]["ScheduleProposal"] }) {
  return (
    <dl className="kv" style={{ marginTop: 8 }}>
      <dt>Đầu nối</dt>
      <dd>{proposal.connector_id ?? "Trong hàng chờ"}</dd>
      <dt>Khung sạc</dt>
      <dd>
        {formatTime(proposal.planned_start)}–{formatTime(proposal.planned_end)}
      </dd>
      <dt>Điện lấy từ lưới</dt>
      <dd>{formatKwh(proposal.energy.grid_energy_kwh)}</dd>
      <dt>Chi phí ước tính</dt>
      <dd>{formatVnd(proposal.estimated_cost_vnd)}</dd>
      <dt>Kịp giờ lấy xe</dt>
      <dd>{proposal.feasible ? "Kịp (ước tính, không phải cam kết)" : "Chưa kịp"}</dd>
      {proposal.certainty === "conditional" ? (
        <>
          <dt>Điều kiện</dt>
          <dd>Phụ thuộc phê duyệt đang chờ — lịch có thể đổi khi được duyệt hoặc từ chối</dd>
        </>
      ) : null}
    </dl>
  );
}
