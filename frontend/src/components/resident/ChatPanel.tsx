"use client";

/**
 * Trợ lý sạc trên trang chủ cư dân (S2, mockup cu-dan/resident.html) — POST /chat/stream, /chat/resume, /chat/transcribe, PATCH /chat/sessions/{session_id}.
 * Số liệu phương án LUÔN lấy từ ChatResponse.proposal (dữ liệu có cấu trúc), không đọc từ câu chữ của LLM (FR3).
 * UX hiện đại:
 *   - Nhập giọng nói tiếng Việt đa vùng miền (Bắc/Trung/Nam) qua /api/v1/chat/transcribe (có điểm cắm fallback PhoWhisper).
 *   - Thanh theo dõi thông tin đã thu thập (Draft Slot Tracker) phía trên ô nhập.
 *   - Thanh kéo % pin hiện tại nội tuyến (Inline Battery Slider) khi thiếu soc_now — thay vì ép con số % giả định.
 *   - Nút so sánh nhanh AC tiết kiệm ↔ DC nhanh ngay trên thẻ phương án đề xuất.
 * 503 llm_unavailable → mời dùng form đặt lịch (NFR khả dụng). Task: T3.3.
 */
import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ChatAdvisory } from "@/components/copilot/ChatAdvisory";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { Notice, SectionHead } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { ApiError, toApiError, type ApiErrorCode } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { clearSessionIfCurrent, getSession, useSession, type Role } from "@/lib/auth/session";
import { API_URL } from "@/lib/env";
import { formatKwh, formatTime, formatVnd } from "@/lib/format";

type ChatResponse = components["schemas"]["ChatResponse"];
type DraftSlots = {
  vehicle_model?: string;
  soc_now?: number;
  soc_target?: number;
  zone?: string;
  mode?: string;
  arrival_time?: string;
  deadline?: string;
};
type Line = { id: string; who: "me" | "bot"; text: string; reply?: ChatResponse };

const MAX_LEN = 5000;
const MAX_RECORD_SECONDS = 45;
const MAX_AUDIO_BYTES = 5 * 1024 * 1024;
const OPERATOR_SUGGESTIONS = ["Vì sao các xe bị trễ?", "Nếu giới hạn nguồn còn 50 kW thì sao?", "Cần nguồn điện bao nhiêu để đáp ứng các cam kết?"];
const SUGGESTIONS = ["Cần 80% trước 07:00 sáng mai.", "Vì sao lịch của tôi bắt đầu lúc 23:00?", "Đổi giờ lấy xe sang 06:30."];

function normalizeEvTranscript(raw: string): string {
  return raw
    .replace(/\b(trụ\s*sạc|sạc|trụ|cổng|vùng)\s*pc\b/gi, "$1 DC")
    .replace(/\bđi\s*xi\b/gi, "DC")
    .replace(/\ba\s*xi\b/gi, "AC")
    .trim();
}

function blobToBase64(blob: Blob, onReader?: (reader: FileReader | null) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    onReader?.(reader);
    reader.onloadend = () => {
      onReader?.(null);
      const result = typeof reader.result === "string" ? reader.result : "";
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => {
      onReader?.(null);
      reject(new Error("Không đọc được bản ghi âm."));
    };
    reader.onabort = () => {
      onReader?.(null);
      reject(new DOMException("Aborted", "AbortError"));
    };
    reader.readAsDataURL(blob);
  });
}

interface ChatPanelProps {
  initialConfirmingSession?: string;
  role?: Role;
}

export function ChatPanel(props: ChatPanelProps = {}) {
  const session = useSession();
  return <ChatConversation key={session?.generation ?? "anonymous"} {...props} />;
}

function ChatConversation({ initialConfirmingSession, role = "resident" }: ChatPanelProps) {
  const resident = role === "resident";
  const mountedRef = useRef(true);
  const streamAbort = useRef<AbortController | null>(null);
  const voiceEpochRef = useRef(0);
  const transcribeAbortRef = useRef<AbortController | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const fileReaderRef = useRef<FileReader | null>(null);
  const [lines, setLines] = useState<Line[]>(() =>
    initialConfirmingSession
      ? [
          {
            id: "initial-confirm",
            who: "bot",
            text: "Vui lòng xác nhận lịch sạc đề xuất.",
            reply: {
              response: "Vui lòng xác nhận lịch sạc đề xuất.",
              analysis: "",
              session_id: initialConfirmingSession,
              status: "needs_confirmation",
              suggestions: [],
            },
          },
        ]
      : [],
  );
  const [text, setText] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>(initialConfirmingSession);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamStatus, setStreamStatus] = useState("Trợ lý đang trả lời…");
  const [streamError, setStreamError] = useState<Error | null>(null);

  // Inline Battery Slider state (hiển thị khi chỉ/đang thiếu soc_now — Option B)
  const [sliderSoc, setSliderSoc] = useState<number>(35);

  // Voice input state (MediaRecorder -> POST /api/v1/chat/transcribe)
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const speechRecRef = useRef<{
    stop: () => void;
    onresult?: unknown;
    onerror?: unknown;
    onend?: unknown;
  } | null>(null);
  const [preferBrowserSpeech, setPreferBrowserSpeech] = useState(false);
  const chunksRef = useRef<Blob[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);

  function cleanupVoiceResources() {
    voiceEpochRef.current += 1;
    transcribeAbortRef.current?.abort();
    transcribeAbortRef.current = null;
    try {
      fileReaderRef.current?.abort?.();
    } catch {
      // ignore
    }
    fileReaderRef.current = null;
    const rec = recorderRef.current;
    recorderRef.current = null;
    if (rec) {
      rec.ondataavailable = null;
      rec.onstop = null;
      try {
        if (rec.state !== "inactive") rec.stop();
      } catch {
        // ignore
      }
    }
    const activeStream = mediaStreamRef.current;
    mediaStreamRef.current = null;
    activeStream?.getTracks().forEach((t) => {
      try {
        t.stop();
      } catch {
        // ignore
      }
    });
    const sr = speechRecRef.current;
    speechRecRef.current = null;
    if (sr) {
      sr.onresult = null;
      sr.onerror = null;
      sr.onend = null;
      try {
        sr.stop();
      } catch {
        // ignore
      }
    }
    chunksRef.current = [];
  }

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      streamAbort.current?.abort();
      cleanupVoiceResources();
    };
  }, []);

  useEffect(() => {
    if (!isRecording) return;
    const timer = window.setInterval(() => {
      setRecordSeconds((s) => {
        if (s + 1 >= MAX_RECORD_SECONDS) {
          recorderRef.current?.stop();
          speechRecRef.current?.stop();
          setIsRecording(false);
          setVoiceNotice(`Đã tự dừng ghi âm (tối đa ${MAX_RECORD_SECONDS} giây).`);
          return MAX_RECORD_SECONDS;
        }
        return s + 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isRecording]);

  const send = useMutation({
    mutationFn: async ({ message, botLineId }: { message: string; botLineId: string }) => {
      const requestSession = getSession();
      const requestGeneration = requestSession?.generation;
      const isTurnCurrent = () => mountedRef.current && getSession()?.generation === requestGeneration;
      setIsStreaming(true);
      setStreamError(null);
      setVoiceNotice(null);
      setStreamStatus("Đang gửi yêu cầu…");
      const controller = new AbortController();
      streamAbort.current = controller;
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (requestSession) headers.Authorization = `Bearer ${requestSession.token}`;

      const res = await fetch(`${API_URL}/api/v1/chat/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({ message, session_id: sessionId }),
        signal: controller.signal,
      });
      if (res.status === 401) clearSessionIfCurrent(requestGeneration);
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
        if (done || !isTurnCurrent()) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const rawEvent of events) {
          if (!isTurnCurrent()) break;
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
      if (!isTurnCurrent()) return null;
      if (!finalReply) {
        throw new ApiError({ status: 500, code: "internal_error", detail: "Luồng phản hồi kết thúc bất ngờ." });
      }
      return finalReply;
    },
    onError: (err) => {
      if (!mountedRef.current || (err instanceof DOMException && err.name === "AbortError")) return;
      setStreamError(err instanceof Error ? err : new Error(String(err)));
    },
    onSettled: () => {
      if (mountedRef.current) setIsStreaming(false);
    },
  });

  const resume = useMutation({
    mutationFn: async (decision: "approve" | "reject") => {
      const requestGeneration = getSession()?.generation;
      const reply = await unwrap(
        api.PATCH("/api/v1/chat/sessions/{session_id}", {
          params: { path: { session_id: sessionId ?? "" } },
          body: { resume: decision },
        }),
      );
      return { reply, requestGeneration };
    },
    onSuccess: ({ reply, requestGeneration }) => {
      if (!mountedRef.current || getSession()?.generation !== requestGeneration) return;
      setLines((prev) => [...prev, { id: crypto.randomUUID(), who: "bot", text: reply.response, reply }]);
    },
  });

  function startBrowserSpeech(epoch: number, capturedGeneration: number | undefined): boolean {
    if (typeof window === "undefined") return false;
    type SpeechRecCtor = new () => {
      lang: string;
      interimResults: boolean;
      maxAlternatives: number;
      onresult: ((ev: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
      onerror: (() => void) | null;
      onend: (() => void) | null;
      start: () => void;
      stop: () => void;
    };
    const w = window as unknown as { SpeechRecognition?: SpeechRecCtor; webkitSpeechRecognition?: SpeechRecCtor };
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Ctor) return false;
    const isVoiceCurrent = () =>
      mountedRef.current && voiceEpochRef.current === epoch && getSession()?.generation === capturedGeneration;
    try {
      const rec = new Ctor();
      rec.lang = "vi-VN";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.onresult = (ev) => {
        if (!isVoiceCurrent()) return;
        const rawTranscript = ev.results?.[0]?.[0]?.transcript?.trim() ?? "";
        const transcript = normalizeEvTranscript(rawTranscript);
        if (transcript) {
          setText((prev) => (prev.trim() ? `${prev.trim()} ${transcript}` : transcript));
          setVoiceNotice("Đã nhận dạng bằng trình duyệt — kiểm tra lại rồi bấm Gửi.");
          inputRef.current?.focus();
        }
      };
      rec.onerror = () => {
        if (!isVoiceCurrent()) return;
        setVoiceNotice("Không nhận dạng được giọng nói lúc này. Bạn vui lòng nhập văn bản trực tiếp nhé.");
      };
      rec.onend = () => {
        if (!isVoiceCurrent()) return;
        setIsRecording(false);
        speechRecRef.current = null;
      };
      speechRecRef.current = rec;
      setRecordSeconds(0);
      setIsRecording(true);
      rec.start();
      return true;
    } catch {
      return false;
    }
  }

  async function toggleVoiceRecording() {
    setVoiceNotice(null);
    if (isRecording) {
      recorderRef.current?.stop();
      speechRecRef.current?.stop();
      setIsRecording(false);
      return;
    }
    const capturedSession = getSession();
    const capturedGeneration = capturedSession?.generation;
    const epoch = ++voiceEpochRef.current;
    const isVoiceCurrent = () =>
      mountedRef.current && voiceEpochRef.current === epoch && getSession()?.generation === capturedGeneration;

    if (preferBrowserSpeech && startBrowserSpeech(epoch, capturedGeneration)) {
      return;
    }
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      if (!startBrowserSpeech(epoch, capturedGeneration) && isVoiceCurrent()) {
        setVoiceNotice("Trình duyệt chưa hỗ trợ ghi âm trực tiếp. Bạn có thể nhập văn bản bên dưới.");
      }
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!isVoiceCurrent()) {
        stream.getTracks().forEach((t) => {
          try {
            t.stop();
          } catch {
            // ignore
          }
        });
        return;
      }
      mediaStreamRef.current = stream;
      const preferredMime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/mp4")
          ? "audio/mp4"
          : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType: preferredMime });
      chunksRef.current = [];
      recorder.ondataavailable = (ev) => {
        if (!isVoiceCurrent()) return;
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => {
          try {
            t.stop();
          } catch {
            // ignore
          }
        });
        if (mediaStreamRef.current === stream) mediaStreamRef.current = null;
        if (recorderRef.current === recorder) recorderRef.current = null;
        if (!isVoiceCurrent()) return;
        const blob = new Blob(chunksRef.current, { type: preferredMime });
        if (blob.size < 100) {
          setVoiceNotice("Bản ghi âm quá ngắn, vui lòng nói lại.");
          return;
        }
        if (blob.size > MAX_AUDIO_BYTES) {
          setVoiceNotice("Bản ghi âm vượt quá giới hạn 5 MB, vui lòng nói ngắn hơn.");
          return;
        }
        setIsTranscribing(true);
        let controller: AbortController | null = null;
        try {
          const audioBase64 = await blobToBase64(blob, (reader) => {
            fileReaderRef.current = reader;
          });
          if (!isVoiceCurrent() || !capturedSession) return;
          controller = new AbortController();
          transcribeAbortRef.current = controller;
          const headers: Record<string, string> = {
            "Content-Type": "application/json",
            Authorization: `Bearer ${capturedSession.token}`,
          };
          const res = await fetch(`${API_URL}/api/v1/chat/transcribe`, {
            method: "POST",
            headers,
            body: JSON.stringify({ audio_base64: audioBase64, mime_type: preferredMime }),
            signal: controller.signal,
          });
          const body = await res.json().catch(() => null);
          if (res.status === 401) clearSessionIfCurrent(capturedGeneration);
          if (!isVoiceCurrent()) return;
          if (!res.ok) {
            throw toApiError(res.status, body, res.headers.get("X-Request-ID"));
          }
          const transcribed = typeof body?.text === "string" ? body.text.trim() : "";
          if (transcribed) {
            setText((prev) => (prev.trim() ? `${prev.trim()} ${transcribed}` : transcribed));
            setVoiceNotice("Đã chuyển giọng nói thành chữ — kiểm tra lại số % pin/giờ rồi bấm Gửi.");
            inputRef.current?.focus();
          } else {
            setVoiceNotice("Chưa nghe rõ lời nói, vui lòng thử lại.");
          }
        } catch (err) {
          if (!isVoiceCurrent() || (err instanceof DOMException && err.name === "AbortError")) return;
          const w = typeof window !== "undefined" ? (window as unknown as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown }) : null;
          const hasBrowserStt = Boolean(w?.SpeechRecognition ?? w?.webkitSpeechRecognition);
          if (hasBrowserStt) {
            setPreferBrowserSpeech(true);
            setVoiceNotice("Dịch vụ giọng nói máy chủ đang bận — đã tự chuyển sang nhận dạng trình duyệt, bấm micro để nói lại.");
          } else {
            const msg = err instanceof ApiError ? err.detail : "Không nhận dạng được giọng nói lúc này. Bạn có thể gõ trực tiếp.";
            setVoiceNotice(msg);
          }
        } finally {
          if (controller && transcribeAbortRef.current === controller) {
            transcribeAbortRef.current = null;
          }
          if (mountedRef.current && voiceEpochRef.current === epoch) {
            setIsTranscribing(false);
          }
        }
      };
      recorderRef.current = recorder;
      setRecordSeconds(0);
      setIsRecording(true);
      recorder.start();
    } catch {
      if (!isVoiceCurrent()) return;
      if (!startBrowserSpeech(epoch, capturedGeneration)) {
        setVoiceNotice("Chưa được cấp quyền micro. Vui lòng cho phép micro hoặc nhập chữ.");
      }
    }
  }

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
    setVoiceNotice(null);
    send.mutate({ message: m, botLineId });
  }
  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    submit(text);
  }

  const lastBot = [...lines].reverse().find((l) => l.who === "bot");
  const waitingConfirm = resident && lastBot?.reply?.status === "needs_confirmation" && !resume.isSuccess;
  const effectiveError = streamError ?? send.error ?? resume.error;
  const llmDown = effectiveError instanceof ApiError && effectiveError.code === "llm_unavailable";
  const error = effectiveError;
  const tooLong = text.length > MAX_LEN;
  const quickReplies =
    lines.length === 0
      ? (resident ? SUGGESTIONS : OPERATOR_SUGGESTIONS)
      : !waitingConfirm && !isStreaming && !send.isPending
        ? (lastBot?.reply?.suggestions ?? [])
        : [];

  const draft = (resident && !lastBot?.reply?.advisory?.length ? lastBot?.reply?.draft ?? null : null) as DraftSlots | null;
  const hasMissingDraftSlots =
    !waitingConfirm &&
    !isStreaming &&
    !send.isPending &&
    lastBot?.reply?.status === "answer" &&
    !lastBot?.reply?.proposal &&
    draft !== null &&
    (draft.soc_now === undefined ||
      draft.soc_target === undefined ||
      !draft.zone ||
      !draft.mode ||
      (draft.mode === "reservation" && !draft.arrival_time) ||
      !draft.deadline);

  return (
    <section className="panel" aria-labelledby="chat-h">
      <SectionHead
        title={<span id="chat-h">Trợ lý sạc</span>}
        icon="chat"
        sub={resident ? "Nói hoặc nhập nhu cầu bằng tiếng Việt. Lịch chỉ được giữ chỗ khi bạn xác nhận." : "Giải thích tình trạng trạm, mô phỏng hạ tầng và kiểm chứng phương án."}
        extra={
          lines.length ? (
            <button
              type="button"
              className="textbtn"
              disabled={isStreaming || send.isPending || resume.isPending}
              onClick={() => {
                setLines([]);
                setSessionId(undefined);
                setStreamError(null);
                setVoiceNotice(null);
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
        {lines.length === 0 && resident ? <p className="subcopy">Nhập yêu cầu hoặc bấm nút micro để nói.</p> : null}
        {lines.map((l) =>
          l.who === "bot" && !l.text && !l.reply ? null : (
            <div key={l.id} className={`chat-line ${l.who}`}>
              <p style={{ whiteSpace: "pre-line", margin: 0 }}>{l.text}</p>
              {l.reply?.advisory?.length ? <ChatAdvisory advisory={l.reply.advisory} sessionId={l.reply.session_id} /> : null}
              {resident && l.reply?.advisory?.some((item) => item.kind === "job" && item.job.job_kind === "how_to") ? (
                <Link href="/resident/plan" className="textbtn">Mở lịch sạc để yêu cầu chỉnh sửa</Link>
              ) : null}
              {l.reply?.request ? (
                <p className="hint" style={{ marginTop: 4 }}>
                  Mục tiêu {l.reply.request.soc_target}% · lấy xe {formatTime(l.reply.request.deadline)}
                </p>
              ) : null}
              {l.reply?.booking ? (
                <p className="hint" style={{ marginTop: 6, color: "var(--green)", fontWeight: 600 }}>
                  Đã chốt lịch thành công · Mã đặt lịch {l.reply.booking.booking_id}
                </p>
              ) : null}
              {l.reply?.proposal ? (
                <ProposalSummary
                  proposal={l.reply.proposal}
                  onCompareZone={
                    !waitingConfirm && !isStreaming && !send.isPending
                      ? (targetZone) =>
                          submit(
                            targetZone === "DC"
                              ? "Đổi sang sạc nhanh DC giúp mình"
                              : "Đổi sang sạc tiết kiệm AC giúp mình",
                          )
                      : undefined
                  }
                />
              ) : null}
            </div>
          ),
        )}
        {send.isPending || isStreaming || resume.isPending ? (
          <p role="status" className="hint">
            {resume.isPending ? "Đang xử lý xác nhận…" : streamStatus}
          </p>
        ) : null}
      </div>

      {draft ? <DraftSlotBar draft={draft} /> : null}

      {hasMissingDraftSlots && draft ? (
        <MissingSlotsQuickFill
          key={lastBot?.id ?? "quick-fill"}
          draft={draft}
          sliderSoc={sliderSoc}
          onSliderSocChange={setSliderSoc}
          onSubmit={(msg) => submit(msg)}
        />
      ) : null}

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
      {resume.error instanceof ApiError && resume.error.status === 409 ? (
        <div style={{ marginTop: 12 }}>
          <Notice title="Chưa đặt được lịch qua Trợ lý" tone="gold" icon="alert">
            <span>
              {resume.error.detail || "Phiên chat không còn yêu cầu nào đang chờ xác nhận."}
              <br />
              <Link href="/resident/book" className="btn btn-primary small" style={{ display: "inline-flex", marginTop: 8 }}>
                Đặt lịch bằng biểu mẫu
                <Icon name="arrow" />
              </Link>
            </span>
          </Notice>
        </div>
      ) : null}
      {error && !(resume.error instanceof ApiError && resume.error.status === 409) ? (
        <div style={{ marginTop: 12 }}>
          {error instanceof ApiError && error.isNotImplemented ? (
            <NotImplementedPanel endpoint="POST /api/v1/chat" taskId={error.taskId} detail={error.detail} />
          ) : (
            <ErrorPanel error={error} />
          )}
          {resident && (llmDown || (error instanceof ApiError && error.status === 409)) ? (
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
        {resident ? <button
          type="button"
          className={`btn ${isRecording ? "btn-primary" : "btn-secondary"}`}
          onClick={toggleVoiceRecording}
          disabled={isTranscribing || send.isPending || isStreaming}
          aria-label={isRecording ? "Dừng ghi âm" : "Nói bằng giọng tiếng Việt"}
          title={isRecording ? "Bấm để dừng ghi âm" : "Nhập bằng giọng nói (Bắc/Trung/Nam)"}
        >
          <Icon name={isRecording ? "stop" : "mic"} />
          {isRecording ? `${recordSeconds}s` : null}
        </button> : null}
        <input
          ref={inputRef}
          id="chat-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            isRecording
              ? "Đang nghe giọng nói tiếng Việt…"
              : isTranscribing
                ? "Đang nhận dạng giọng nói…"
                : resident ? "Nhập hoặc nói nhu cầu sạc…" : "Nhập câu hỏi về trạm…"
          }
          aria-invalid={tooLong || undefined}
          aria-describedby="chat-hint"
        />
        <button type="submit" className="btn btn-primary" disabled={!text.trim() || tooLong || send.isPending} aria-label="Gửi">
          <Icon name="arrow" />
        </button>
      </form>
      <span id="chat-hint" className="hint" style={{ color: tooLong ? "var(--red)" : undefined }}>
        {tooLong ? "Tin nhắn tối đa 5.000 ký tự." : voiceNotice ?? ""}
      </span>
    </section>
  );
}

function DraftSlotBar({ draft }: { draft: DraftSlots }) {
  const pills: Array<{ label: string; filled: boolean }> = [
    { label: draft.vehicle_model ? `Xe ${draft.vehicle_model}` : "Xe ?", filled: Boolean(draft.vehicle_model) },
    {
      label: `Pin ${draft.soc_now !== undefined ? `${draft.soc_now}%` : "?%"} → ${draft.soc_target !== undefined ? `${draft.soc_target}%` : "?%"}`,
      filled: draft.soc_now !== undefined && draft.soc_target !== undefined,
    },
    {
      label: draft.zone ? `Vùng ${draft.zone}` : "AC / DC ?",
      filled: Boolean(draft.zone),
    },
    {
      label: draft.mode === "walk_in" ? "Đang ở bãi" : draft.mode === "reservation" ? "Đặt trước" : "Hình thức ?",
      filled: Boolean(draft.mode),
    },
    {
      label: draft.deadline ? `Hạn ${formatTime(draft.deadline)}` : "Giờ lấy xe ?",
      filled: Boolean(draft.deadline),
    },
  ];
  return (
    <div
      aria-label="Thông tin yêu cầu đã nhận"
      style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}
    >
      {pills.map((p) => (
        <span
          key={p.label}
          style={{
            fontSize: "0.75rem",
            padding: "2px 8px",
            borderRadius: 999,
            border: "1px solid var(--line)",
            opacity: p.filled ? 1 : 0.65,
            fontWeight: p.filled ? 600 : 400,
          }}
        >
          {p.label}
        </span>
      ))}
    </div>
  );
}

function addMinutesHHMM(addMin: number): { hhmm: string; dayLabel: "hôm nay" | "ngày mai" } {
  const now = new Date();
  const target = new Date(now.getTime() + addMin * 60_000);
  const hh = String(target.getHours()).padStart(2, "0");
  const mm = String(target.getMinutes()).padStart(2, "0");
  const isTomorrow = target.getDate() !== now.getDate();
  return { hhmm: `${hh}:${mm}`, dayLabel: isTomorrow ? "ngày mai" : "hôm nay" };
}

function shiftSelectedTime(
  currentHHMM: string,
  currentDay: "hôm nay" | "ngày mai",
  deltaMin: number,
): { hhmm: string; dayLabel: "hôm nay" | "ngày mai" } {
  const now = new Date();
  const nowTotal = now.getHours() * 60 + now.getMinutes();
  const [hStr, mStr] = currentHHMM.split(":");
  const curH = Number.parseInt(hStr ?? "0", 10) || 0;
  const curM = Number.parseInt(mStr ?? "0", 10) || 0;
  const curTotal = (currentDay === "ngày mai" ? 1440 : 0) + curH * 60 + curM;
  const minTotal = nowTotal + 10;
  const nextTotal = Math.max(minTotal, Math.min(2879, curTotal + deltaMin));
  const nextDay: "hôm nay" | "ngày mai" = nextTotal >= 1440 ? "ngày mai" : "hôm nay";
  const inDay = nextTotal % 1440;
  const hh = String(Math.floor(inDay / 60)).padStart(2, "0");
  const mm = String(inDay % 60).padStart(2, "0");
  return { hhmm: `${hh}:${mm}`, dayLabel: nextDay };
}

function MissingSlotsQuickFill({
  draft,
  sliderSoc,
  onSliderSocChange,
  onSubmit,
}: {
  draft: DraftSlots;
  sliderSoc: number;
  onSliderSocChange: (v: number) => void;
  onSubmit: (message: string) => void;
}) {
  const needSocNow = draft.soc_now === undefined;
  const needSocTarget = draft.soc_target === undefined;
  const needZone = !draft.zone;
  const needMode = !draft.mode;
  const needArrival = draft.mode === "reservation" && !draft.arrival_time;
  const needDeadline = !draft.deadline;

  const [pickedSocNow, setPickedSocNow] = useState(false);
  const [socTarget, setSocTarget] = useState<number>(80);
  const [zone, setZone] = useState<"AC" | "DC" | null>(null);
  const [mode, setMode] = useState<"walk_in" | "reservation" | null>(null);
  const [arrivalHHMM, setArrivalHHMM] = useState(() => addMinutesHHMM(30).hhmm);
  const [deadlineHHMM, setDeadlineHHMM] = useState("07:00");
  const [deadlineDay, setDeadlineDay] = useState<"hôm nay" | "ngày mai">("ngày mai");

  function handleSend() {
    const parts: string[] = [];
    if (needSocNow && pickedSocNow) parts.push(`pin hiện tại ${sliderSoc}%`);
    if (needSocTarget) parts.push(`sạc lên ${socTarget}%`);
    if (needZone && zone) parts.push(zone === "DC" ? "sạc nhanh DC" : "sạc tiết kiệm AC");
    if (needMode && mode) {
      if (mode === "walk_in") {
        parts.push("đang ở bãi");
      } else {
        parts.push(`đặt lịch hẹn đến lúc ${arrivalHHMM} hôm nay`);
      }
    } else if (needArrival) {
      parts.push(`đến bãi lúc ${arrivalHHMM} hôm nay`);
    }
    if (needDeadline && deadlineHHMM) {
      parts.push(`cần lấy xe lúc ${deadlineHHMM} ${deadlineDay}`);
    }
    if (parts.length > 0) {
      onSubmit(parts.join(", "));
    }
  }

  const canSend =
    (needSocNow && pickedSocNow) ||
    needSocTarget ||
    (needZone && zone !== null) ||
    (needMode && mode !== null) ||
    needArrival ||
    needDeadline;

  return (
    <div
      style={{
        marginTop: 10,
        padding: "10px 12px",
        borderRadius: 10,
        border: "1px solid var(--line)",
        background: "var(--surface-2, rgba(0,0,0,0.03))",
        display: "grid",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span className="hint" style={{ fontWeight: 600 }}>
          Điền nhanh phần còn thiếu (gửi 1 lần để tiết kiệm lượt)
        </span>
        <Link href="/resident/book" className="textbtn" style={{ fontSize: "0.8rem" }}>
          Mở form đầy đủ
        </Link>
      </div>

      {needSocNow ? (
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className="hint" style={{ minWidth: 96 }}>Pin hiện tại:</span>
          <input
            type="range"
            min={1}
            max={95}
            step={1}
            value={sliderSoc}
            aria-label="Phần trăm pin hiện tại"
            onChange={(e) => {
              onSliderSocChange(Number(e.target.value));
              setPickedSocNow(true);
            }}
            style={{ flex: 1 }}
          />
          <strong style={{ minWidth: 38, textAlign: "right" }}>{sliderSoc}%</strong>
        </div>
      ) : null}

      {needSocTarget ? (
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span className="hint" style={{ minWidth: 96 }}>Pin mục tiêu:</span>
          {[80, 90, 100].map((v) => (
            <button
              key={v}
              type="button"
              className={`btn small ${socTarget === v ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setSocTarget(v)}
            >
              {v}%
            </button>
          ))}
        </div>
      ) : null}

      {needZone ? (
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span className="hint" style={{ minWidth: 96 }}>Loại trụ:</span>
          <button
            type="button"
            className={`btn small ${zone === "AC" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setZone("AC")}
          >
            AC · 11 kW
          </button>
          <button
            type="button"
            className={`btn small ${zone === "DC" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setZone("DC")}
          >
            DC · 60 kW
          </button>
        </div>
      ) : null}

      {needMode ? (
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span className="hint" style={{ minWidth: 96 }}>Hình thức:</span>
          <button
            type="button"
            className={`btn small ${mode === "walk_in" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setMode("walk_in")}
          >
            Đang ở bãi
          </button>
          <button
            type="button"
            className={`btn small ${mode === "reservation" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setMode("reservation")}
          >
            Đặt lịch hẹn
          </button>
          {mode === "reservation" ? (
            <input
              type="time"
              aria-label="Giờ dự kiến đến bãi"
              value={arrivalHHMM}
              onChange={(e) => setArrivalHHMM(e.target.value)}
              style={{ width: 105 }}
            />
          ) : null}
        </div>
      ) : needArrival ? (
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span className="hint" style={{ minWidth: 96 }}>Giờ đến bãi:</span>
          <input
            type="time"
            aria-label="Giờ dự kiến đến bãi"
            value={arrivalHHMM}
            onChange={(e) => setArrivalHHMM(e.target.value)}
            style={{ width: 105 }}
          />
        </div>
      ) : null}

      {needDeadline ? (
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span className="hint" style={{ minWidth: 96 }}>Giờ lấy xe:</span>
          {([-60, -30, 30, 60] as const).map((delta) => (
            <button
              key={delta}
              type="button"
              className="btn btn-secondary small"
              onClick={() => {
                const next = shiftSelectedTime(deadlineHHMM, deadlineDay, delta);
                setDeadlineHHMM(next.hhmm);
                setDeadlineDay(next.dayLabel);
              }}
            >
              {delta === -60 ? "-1 giờ" : delta === -30 ? "-30 phút" : delta === 30 ? "+30 phút" : "+1 giờ"}
            </button>
          ))}
          <input
            type="time"
            aria-label="Giờ cần lấy xe"
            value={deadlineHHMM}
            onChange={(e) => setDeadlineHHMM(e.target.value)}
            style={{ width: 105 }}
          />
          <button
            type="button"
            className="btn btn-secondary small"
            onClick={() => setDeadlineDay((d) => (d === "hôm nay" ? "ngày mai" : "hôm nay"))}
          >
            {deadlineDay === "hôm nay" ? "Hôm nay" : "Ngày mai"}
          </button>
        </div>
      ) : null}

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button type="button" className="btn btn-primary small" disabled={!canSend} onClick={handleSend}>
          Gửi thông tin còn thiếu
        </button>
      </div>
    </div>
  );
}

function ProposalSummary({
  proposal,
  onCompareZone,
}: {
  proposal: components["schemas"]["ScheduleProposal"];
  onCompareZone?: (zone: "AC" | "DC") => void;
}) {
  const isDc = proposal.connector_id?.toUpperCase().startsWith("DC");
  const altZone: "AC" | "DC" = isDc ? "AC" : "DC";
  return (
    <div>
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
      {onCompareZone ? (
        <div style={{ marginTop: 8 }}>
          <button
            type="button"
            className="btn btn-secondary small"
            onClick={() => onCompareZone(altZone)}
          >
            <Icon name="bolt" />
            {altZone === "DC" ? "So sánh sạc nhanh DC" : "So sánh sạc tiết kiệm AC"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
