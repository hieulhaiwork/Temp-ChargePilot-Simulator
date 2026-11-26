"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { ErrorPanel } from "@/components/system/ErrorPanel";
import { Notice, Panel, SectionHead, Tag } from "@/components/ui/blocks";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useSession } from "@/lib/auth/session";

type Schema = components["schemas"];
type Reply = Schema["WhyReply"] | Schema["JobReply"] | Schema["CopilotNotice"];
type FormMode = "why" | "revise_vehicle" | "site_limit" | "outage";
export const statusText: Record<Schema["WhatIfJobStatus"], string> = {
  queued: "Đang chờ chạy", running: "Đang mô phỏng", succeeded: "Đã có kết quả",
  failed: "Tác vụ thất bại", cancelled: "Đã hủy", expired: "Tác vụ đã hết hạn",
};
const stages = {
  observed: "Quan sát", planned: "Kế hoạch", approved: "Đã duyệt", dispatched: "Đã gửi lệnh",
  effective_setpoint: "Mức lệnh đang giữ", measured: "Đo thực tế", config: "Cấu hình", simulated: "Mô phỏng",
} satisfies Record<Schema["GroundedClaim"]["stage"], string>;
const reasonLabels = {
  observed: "Lý do theo quan sát", policy_reason: "Lý do theo quyết định của chính sách",
  binding_constraint: "Ràng buộc đang giới hạn", inference_bound: "Suy luận có điều kiện",
} satisfies Record<Schema["EvidenceCategory"], string>;
const metricLabels = {
  "sla.on_time_rate": "SLA gốc toàn trạm",
  "sla.AC.on_time_rate": "SLA gốc AC",
  "sla.DC.on_time_rate": "SLA gốc DC",
  horizon_battery_kwh: "Năng lượng lưu vào pin (kWh)",
  horizon_output_kwh: "Năng lượng đầu ra bộ sạc (kWh)",
  horizon_grid_input_kwh: "Năng lượng lấy từ lưới (kWh)",
  horizon_energy_cost_vnd: "Chi phí điện (VND)",
  peak_grid_input_kw: "Đỉnh công suất đầu vào lưới (kW)",
  plug_wait_mean_minutes: "Chờ cắm trung bình (phút)",
  charge_wait_mean_minutes: "Chờ bắt đầu sạc trung bình (phút)",
  unmet_original_battery_kwh: "Năng lượng còn thiếu tới mục tiêu gốc khi kết thúc quan sát (kWh)",
};
const whyTopics = {
  queue: "Hàng chờ", power: "Công suất", deadline_risk: "Rủi ro trễ hạn",
  incident: "Sự cố", policy: "Chính sách", overview: "Tổng quan",
};
const number = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 6 });
const percent = new Intl.NumberFormat("vi-VN", { style: "percent", maximumFractionDigits: 2 });

export function stamp(value: string | null | undefined, timezone: string) {
  if (!value) return "Chưa quan sát";
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: timezone, dateStyle: "short", timeStyle: "medium", hourCycle: "h23",
  }).format(new Date(value));
}

function claimValue(value: Schema["GroundedClaim"]["value"] | undefined, unit?: string | null) {
  if (value == null) return "Chưa có dữ liệu";
  if (typeof value === "boolean") return value ? "Có" : "Không";
  if (typeof value === "number") return unit === "fraction" ? percent.format(value) : number.format(value);
  return value;
}

export function WhyResult({ reply, timezone }: { reply: Schema["WhyReply"]; timezone: string }) {
  const reasons = reply.claims.filter((claim) => claim.reason_code);
  const facts = reply.claims.filter((claim) => !claim.reason_code);
  return (
    <section aria-label="Kết quả WHY" className="stack">
      <p role="status">{reply.summary}</p>
      {reasons.length ? (
        <ul>
          {reasons.map((claim) => (
            <li key={claim.claim_id}>{claim.value} <small>· {stamp(claim.observed_at, timezone)}</small></li>
          ))}
        </ul>
      ) : null}
      {reply.claims.length ? (
        <details open={reasons.length === 0}>
          <summary>Bằng chứng ({reply.claims.length})</summary>
          <ul>
            {[...facts, ...reasons].map((claim) => (
              <li key={claim.claim_id}>
                {claim.reason_code ?? claim.name} · {claim.reason_category ? reasonLabels[claim.reason_category] : stages[claim.stage]} ·{" "}
                {claimValue(claim.value, claim.unit)} {claim.unit !== "fraction" ? claim.unit : ""} ·{" "}
                {stamp(claim.observed_at, timezone)}
                {claim.interval_start && claim.interval_end ? (
                  <small> · {stamp(claim.interval_start, timezone)} → {stamp(claim.interval_end, timezone)}</small>
                ) : null}
                <ul>{claim.evidence_refs.map((ref) => <li key={ref}><code style={{ overflowWrap: "anywhere" }}>{ref}</code></li>)}</ul>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {reply.result.missing_evidence?.length ? (
        <details><summary>Dữ liệu còn thiếu</summary><ul>{reply.result.missing_evidence?.map((item) => <li key={item}>{item}</li>)}</ul></details>
      ) : null}
    </section>
  );
}

export function Commitment({ value, timezone }: { value: Schema["CommitmentOutcome"]; timezone: string }) {
  const sla = value.met_deadline === true ? "Đúng hạn" : value.met_deadline === false ? "Trễ hạn" : "Chưa xác định SLA";
  return (
    <div>
      <strong>{number.format(value.target_soc)}% · {sla}</strong>
      <div>Hạn: {stamp(value.deadline, timezone)}</div>
      <div>Đạt mục tiêu: {value.already_satisfied_at_snapshot ? "Đã đạt khi chụp trạng thái" : stamp(value.target_reached_at, timezone)}</div>
    </div>
  );
}

export function WhatIfResult({ reply, timezone }: { reply: Schema["WhatIfReply"]; timezone: string }) {
  const { result, claims } = reply;
  const byId = new Map(claims.map((claim) => [claim.claim_id, claim]));
  return (
    <section aria-label="Kết quả WHAT-IF" className="stack">
      <div>
        <Tag tone={result.status === "completed" ? "blue" : "gold"}>Mô phỏng · Chỉ tham khảo</Tag>
        {result.hypothetical_infrastructure ? <Tag tone="gold">Giả định nâng cấp hạ tầng</Tag> : null}
        <p role="status">{reply.summary}</p>
        <p className="hint">Cửa sổ {result.horizon_minutes} phút · {stamp(result.snapshot_time, timezone)} → {stamp(result.horizon_end, timezone)}</p>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <caption>Chênh lệch = mô phỏng thay đổi trừ cơ sở</caption>
          <thead><tr><th>Chỉ số</th><th>Cơ sở</th><th>Thay đổi</th><th>Chênh lệch</th></tr></thead>
          <tbody>
            {Object.entries(metricLabels).map(([name, label]) => {
              const a = byId.get(`baseline:${name}`);
              const b = byId.get(`patched:${name}`);
              const diff = byId.get(`delta:${name}`);
              let delta = "Chưa thể so sánh";
              if (diff?.reason_code === "non_comparable_sample") delta = "Khác tập booking";
              else if (diff?.reason_code === "missing_data") delta = "Thiếu dữ liệu";
              else if (typeof diff?.value === "number") {
                const rate = diff.unit === "fraction";
                delta = `${diff.value > 0 ? "+" : ""}${number.format(rate ? diff.value * 100 : diff.value)}${rate ? " đ.%": ""}`;
              }
              return (
                <tr key={name}>
                  <th scope="row">{label}</th>
                  <td>{claimValue(a?.value, a?.unit)}</td>
                  <td>{claimValue(b?.value, b?.unit)}</td>
                  <td>{delta}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {result.affected_vehicles.length ? (
        <details open>
          <summary>Lịch sạc có thay đổi ({result.affected_vehicles.length})</summary>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Lịch</th><th>Cơ sở · cam kết gốc</th><th>Thay đổi · cam kết gốc</th><th>Cam kết sửa</th><th>Rời cổng cơ sở → thay đổi</th></tr></thead>
              <tbody>
                {result.affected_vehicles.map((row) => (
                  <tr key={row.booking_id}>
                    <th scope="row">{row.booking_id}</th>
                    <td><Commitment value={row.baseline_original} timezone={timezone} /></td>
                    <td><Commitment value={row.patched_original} timezone={timezone} /></td>
                    <td>{row.patched_revised ? <Commitment value={row.patched_revised} timezone={timezone} /> : "—"}</td>
                    <td>{stamp(row.baseline_release_at, timezone)} → {stamp(row.patched_release_at, timezone)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
      <details>
        <summary>Giả định, an toàn và nguồn mô phỏng</summary>
        <p className="hint" style={{ overflowWrap: "anywhere" }}>Snapshot {result.snapshot_id} · {result.snapshot_digest}</p>
        {([["Cơ sở", result.baseline], ["Thay đổi", result.patched]] as const).map(([label, branch]) => (
          <p key={label} className="hint">
            {label} · quan sát đến {stamp(branch.observed_until, timezone)} · vi phạm {branch.hard_violations} ·
            chưa xử lý {branch.unresolved_safety_count} · lệnh bị chặn {branch.blocked_commands} ·
            phê duyệt đang chờ {branch.pending_approvals} · lệnh chờ phê duyệt {branch.pending_approval_commands}
          </p>
        ))}
        <ul>{result.assumptions.map((text) => <li key={text}>{text}</li>)}</ul>
      </details>
    </section>
  );
}

export function active(job?: Schema["CopilotJob"]) {
  return job?.status === "queued" || job?.status === "running";
}

export function CopilotPanel({ role, structuredOnly = false }: { role: Schema["CopilotContext"]["role"]; structuredOnly?: boolean }) {
  const session = useSession();
  const cache = useQueryClient();
  useEffect(() => {
    if (!session) {
      void cache.cancelQueries({ queryKey: ["copilot"] });
      cache.removeQueries({ queryKey: ["copilot"] });
    }
  }, [cache, session]);
  if (!session || session.role !== role) return null;
  const actorKey = `${role}:${session.userId}:${session.generation}`;
  return <CopilotForActor key={actorKey} role={role} userId={session.userId} actorKey={actorKey} structuredOnly={structuredOnly} />;
}

function CopilotForActor({
  role,
  userId,
  actorKey,
  structuredOnly,
}: {
  role: Schema["CopilotContext"]["role"];
  userId: string;
  actorKey: string;
  structuredOnly: boolean;
}) {
  const id = useId();
  const cache = useQueryClient();
  const mountedRef = useRef(true);
  const submitEpochRef = useRef(0);
  const [reply, setReply] = useState<Reply>();
  const [message, setMessage] = useState("");
  const [booking, setBooking] = useState("");
  const [connector, setConnector] = useState("");
  const [mode, setMode] = useState<FormMode>("why");
  const [formOpen, setFormOpen] = useState(structuredOnly);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      submitEpochRef.current += 1;
      void cache.cancelQueries({ queryKey: ["copilot", "context", role, userId, actorKey] });
      void cache.cancelQueries({ queryKey: ["copilot", "job", userId, actorKey] });
      cache.removeQueries({ queryKey: ["copilot", "context", role, userId, actorKey] });
      cache.removeQueries({ queryKey: ["copilot", "job", userId, actorKey] });
    };
  }, [actorKey, cache, role, userId]);
  const context = useQuery({
    queryKey: ["copilot", "context", role, userId, actorKey],
    queryFn: ({ signal }) => unwrap(api.GET("/api/v1/copilot/context", { signal })),
  });
  const submit = useMutation({
    mutationFn: async (request: () => Promise<Reply>) => {
      const epoch = ++submitEpochRef.current;
      const result = await request();
      return { epoch, result };
    },
    onSuccess({ epoch, result }) {
      if (!mountedRef.current || epoch !== submitEpochRef.current) return;
      setReply(result);
      if (result.kind === "notice" && result.code === "structured_fallback") setFormOpen(true);
    },
  });
  const initial = reply?.kind === "job" ? reply : undefined;
  const jobId = initial?.job.job_id ?? "";
  const jobKey = ["copilot", "job", userId, actorKey, jobId] as const;
  const poll = useQuery({
    queryKey: jobKey,
    enabled: active(initial?.job),
    refetchOnWindowFocus: false,
    placeholderData: initial,
    queryFn: ({ signal }) => unwrap(api.GET("/api/v1/copilot/jobs/{job_id}", { params: { path: { job_id: jobId } }, signal })),
    refetchInterval: (query) => active(query.state.data?.job) ? Math.min(4000, 750 + query.state.dataUpdateCount * 250) : false,
  });
  const job = (poll.data ?? initial)?.job;
  const cancel = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/copilot/jobs/{job_id}", { params: { path: { job_id: jobId } } })),
    onSuccess: (result) => {
      if (mountedRef.current) cache.setQueryData(jobKey, result);
    },
  });
  const timezone = context.data?.timezone ?? "Asia/Ho_Chi_Minh";
  const choices = context.data;

  function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit.mutate(() => unwrap(api.POST("/api/v1/copilot/query", {
      body: { message: message.trim(), selected_booking_id: booking || null, selected_connector_id: connector || null },
    })));
  }

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!choices) return;
    const inputs = new FormData(event.currentTarget);
    if (mode === "why") {
      const topic = String(inputs.get("topic"));
      submit.mutate(() => unwrap(api.POST("/api/v1/copilot/why", {
        body: { topic, limit: 20, at: String(inputs.get("at") || choices.as_of), subject_scope: booking ? "booking" : role === "operator" ? "station" : "own_booking", booking_id: booking || null },
      })));
      return;
    }
    const target = String(inputs.get("target") ?? "");
    const deadline = String(inputs.get("deadline") ?? "").trim();
    let patch: Schema["WhatIfRequest"]["patch"];
    if (mode === "revise_vehicle") {
      patch = { op: "revise_vehicle", booking_id: booking, target_soc: target ? Number(target) : null, deadline: deadline || null };
    } else if (mode === "site_limit") {
      patch = { op: "site_limit", grid_input_kw: Number(inputs.get("grid")), hypothetical_infrastructure: inputs.has("hypothetical") };
    } else {
      patch = { op: "outage", connector_id: connector, duration_minutes: Number(inputs.get("duration")) };
    }
    submit.mutate(() => unwrap(api.POST("/api/v1/copilot/what-if", { body: { patch, horizon_minutes: Number(inputs.get("horizon")) } })));
  }

  const busy = submit.isPending || active(job);
  return (
    <Panel label="Copilot trạm sạc">
      <div className="stack">
        <SectionHead title={structuredOnly ? "Biểu mẫu phân tích" : "Copilot trạm sạc"} sub="Xem lý do hoặc mô phỏng một thay đổi." />
        <div className="fieldgrid">
          <label className="field">
            <span className="label">Lịch sạc</span>
            <select value={booking} onChange={(event) => setBooking(event.target.value)}>
              <option value="">{role === "resident" ? "Lịch của tôi" : "Chọn khi cần"}</option>
              {choices?.booking_ids.map((key) => <option key={key}>{key}</option>)}
            </select>
          </label>
          {role === "operator" ? (
            <label className="field">
              <span className="label">Đầu nối</span>
              <select value={connector} onChange={(event) => setConnector(event.target.value)}>
                <option value="">Chọn khi mô phỏng lỗi đầu nối</option>
                {choices?.connectors.map(({ connector_id }) => <option key={connector_id}>{connector_id}</option>)}
              </select>
            </label>
          ) : null}
        </div>
        {context.isError ? <ErrorPanel error={context.error} onRetry={() => void context.refetch()} /> : null}
        {!structuredOnly ? <form onSubmit={submitMessage} className="stack">
          <div className="field">
            <label htmlFor={id}>Câu hỏi</label>
            <textarea id={id} required maxLength={1000} value={message} onChange={(event) => setMessage(event.target.value)}
              placeholder={role === "resident" ? "Tại sao xe của tôi vẫn chưa được sạc?" : "Nếu một cổng DC bị lỗi trong 30 phút thì sao?"} />
          </div>
          <div className="actions">
            <button className="btn btn-primary" disabled={busy || !message.trim()} type="submit">Gửi câu hỏi</button>
            <button className="btn btn-secondary" type="button" aria-expanded={formOpen} onClick={() => setFormOpen(!formOpen)}>Dùng biểu mẫu</button>
          </div>
        </form> : null}
        {formOpen && choices ? (
          <form onSubmit={submitForm} className="stack" aria-label="Biểu mẫu Copilot">
            <label className="field"><span className="label">Thao tác</span>
              <select value={mode} onChange={(event) => setMode(event.target.value as FormMode)}>
                <option value="why">Xem lý do</option><option value="revise_vehicle">Đổi mức pin hoặc hạn sạc</option>
                {role === "operator" ? <><option value="site_limit">Đổi giới hạn lưới</option><option value="outage">Mô phỏng lỗi đầu nối</option></> : null}
              </select>
            </label>
            {mode === "why" ? (
              <div className="fieldgrid">
                <label className="field"><span className="label">Chủ đề</span><select name="topic">
                  {Object.entries(whyTopics).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </select></label>
                <label className="field"><span className="label">Thời điểm tại trạm (ISO có múi giờ)</span><input name="at" defaultValue={choices.as_of} required /></label>
              </div>
            ) : null}
            {mode === "revise_vehicle" ? (
              <div className="fieldgrid">
                <label className="field"><span className="label">Mức pin mới (%)</span><input type="number" name="target" min="0" max="100" step="any" /></label>
                <label className="field"><span className="label">Hạn mới (ISO có múi giờ)</span><input name="deadline" placeholder={choices.as_of} /></label>
              </div>
            ) : null}
            {mode === "site_limit" ? (
              <>
                <label className="field"><span className="label">Giới hạn đầu vào lưới (kW)</span><input name="grid" type="number" required min="0.001" step="any" /></label>
                <label><input name="hypothetical" type="checkbox" /> Giả định nâng cấp hạ tầng</label>
              </>
            ) : null}
            {mode === "outage" ? <label className="field"><span className="label">Thời lượng lỗi (phút)</span><input name="duration" type="number" required min="1" max={choices.max_horizon_minutes} defaultValue={30} /></label> : null}
            {mode !== "why" ? <label className="field"><span className="label">Cửa sổ mô phỏng (phút)</span><input name="horizon" type="number" required min="1" max={choices.max_horizon_minutes} defaultValue={choices.default_horizon_minutes} /></label> : null}
            <button className="btn btn-primary" type="submit" disabled={busy || (mode === "revise_vehicle" && !booking) || (mode === "outage" && !connector)}>
              {mode === "why" ? "Xem bằng chứng" : "Chạy mô phỏng"}
            </button>
          </form>
        ) : null}
        {submit.isPending ? <p className="hint" role="status">Đang xử lý yêu cầu…</p> : null}
        {submit.isError ? <ErrorPanel error={submit.error} /> : null}
        {reply?.kind === "notice" ? <Notice role="status" title={reply.message} /> : null}
        {reply?.kind === "why" ? <WhyResult reply={reply} timezone={timezone} /> : null}
        {job ? (
          <div className="stack">
            <p role="status">{statusText[job.status]}{job.error === "timeout" ? " · Hết thời gian" : ""}</p>
            {active(job) ? <button className="btn btn-secondary" type="button" disabled={cancel.isPending} onClick={() => cancel.mutate()}>Hủy mô phỏng</button> : null}
            {poll.isError ? <ErrorPanel error={poll.error} onRetry={() => void poll.refetch()} /> : null}
            {cancel.isError ? <ErrorPanel error={cancel.error} /> : null}
            {job.result?.kind === "what_if" ? <WhatIfResult reply={job.result} timezone={timezone} /> : null}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
