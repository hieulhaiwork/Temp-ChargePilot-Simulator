"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ErrorPanel } from "@/components/system/ErrorPanel";
import { Tag } from "@/components/ui/blocks";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useSession } from "@/lib/auth/session";

import { active, Commitment, stamp, statusText, WhatIfResult, WhyResult } from "./CopilotPanel";

type Schema = components["schemas"];
type Advisory = NonNullable<Schema["ChatResponse"]["advisory"]>[number];
const timezone = "Asia/Ho_Chi_Minh";
const exact = new Intl.NumberFormat("vi-VN", { maximumSignificantDigits: 16 });
const feasibility = { feasible: "Khả thi", infeasible: "Không khả thi", unknown: "Chưa xác định" };

function Evidence({ evidence }: { evidence: Schema["RecommendationEvidence"] }) {
  const achieved = evidence.subject_goal_target;
  const sla = evidence.original_sla;
  return (
    <div className="stack">
      {evidence.subject_original ? <div>Cam kết gốc <Commitment value={evidence.subject_original} timezone={timezone} /></div> : null}
      {evidence.subject_revised ? <div>Cam kết sửa <Commitment value={evidence.subject_revised} timezone={timezone} /></div> : null}
      {achieved ? <div>Mốc đạt {exact.format(achieved.target_soc)}% · {achieved.already_satisfied_at_snapshot ? "Đã đạt khi chụp trạng thái" : stamp(achieved.target_reached_at, timezone)}</div> : null}
      {evidence.subject_soc_at_deadline_pct != null ? (
        <div>Pin tại hạn {stamp(evidence.subject_soc_observed_at, timezone)} · {exact.format(evidence.subject_soc_at_deadline_pct)}%</div>
      ) : null}
      {evidence.subject_original ? <div>Nhả cổng · {stamp(evidence.subject_release_at, timezone)}</div> : null}
      {sla ? <div>Cam kết gốc đúng hạn · {sla.met_count}/{sla.denominator} · {sla.censored_count} chưa đủ quan sát</div> : null}
    </div>
  );
}

function HowToResult({ reply }: { reply: Schema["HowToReply"] }) {
  const { result } = reply;
  const goal = result.goal;
  const site = goal.goal === "min_tested_site_limit_for_sla";
  const localTime = (value: string) => stamp(value, timezone);
  const valueLabel = (value: number | string) =>
    typeof value === "string" ? localTime(value) : `${exact.format(value)} ${site ? "kW đầu vào lưới" : "%"}`;

  return (
    <section className="stack" aria-label="Kết quả HOW-TO">
      <Tag tone="blue">Mô phỏng · Chỉ tham khảo · Chưa áp dụng</Tag>
      <p>{reply.summary}</p>
      {site ? (
        <p>Mức nguồn thử {valueLabel(goal.min_grid_input_kw)} đến {valueLabel(goal.max_grid_input_kw)} · Mục tiêu đúng hạn {exact.format(goal.min_original_on_time_rate * 100)}%.
          {goal.protect_on_time_ac_bookings ? " Giữ các cam kết AC đang đúng hạn." : ""}
          {goal.hypothetical_infrastructure ? " Cho phép giả định nâng cấp hạ tầng." : ""}
        </p>
      ) : goal.goal === "max_soc_by_deadline" ? (
        <p>Lịch {goal.booking_id} · pin cao nhất tại {localTime(goal.deadline)} · thử {valueLabel(goal.min_target_soc)} đến {valueLabel(goal.max_target_soc)}.</p>
      ) : (
        <p>Lịch {goal.booking_id} · đạt {valueLabel(goal.target_soc)} sớm nhất · thử hạn từ {localTime(goal.earliest_deadline)} đến {localTime(goal.latest_deadline)}.</p>
      )}
      {!site ? (
        <p>Quyền đánh đổi · giảm mục tiêu {goal.allow_lower_target ? "có" : "không"} · dời hạn muộn {goal.allow_later_deadline ? "có" : "không"} · mất cam kết gốc {goal.allow_subject_original_sla_regression ? "có" : "không"}.</p>
      ) : null}
      {result.baseline ? (
        <details><summary>Kịch bản gốc</summary><Evidence evidence={result.baseline} /></details>
      ) : null}
      {result.options.length ? <ol>{result.options.map((option) => (
        <li key={option.value}>
          <strong>{valueLabel(option.value)} · {feasibility[option.feasibility]}</strong>
          {option.hypothetical_infrastructure ? <div>Giả định nâng cấp hạ tầng</div> : null}
          {option.evidence ? <Evidence evidence={option.evidence} /> : null}
        </li>
      ))}</ol> : null}
      <details>
        <summary>Các ứng viên và bằng chứng</summary>
        <ul>{result.candidates.map((candidate) => (
          <li key={candidate.value}>{valueLabel(candidate.value)} · {feasibility[candidate.feasibility]}
            {candidate.reason ? ` · ${candidate.reason}` : ""}
          </li>
        ))}</ul>
        <ul>{reply.claims.filter((claim) => claim.name.includes("target_reached_at") || claim.name.includes("release_at") || claim.name.includes("soc_at_deadline")).map((claim) => (
          <li key={claim.claim_id}><code style={{ overflowWrap: "anywhere" }}>{claim.evidence_refs[0]}</code></li>
        ))}</ul>
      </details>
      {result.assumptions.length ? <details><summary>Giả định</summary><ul>{result.assumptions.map((value) => <li key={value}>{value}</li>)}</ul></details> : null}
    </section>
  );
}

function ChatJob({ initial, sessionId }: { initial: Schema["JobReply"]; sessionId: string }) {
  const jobId = initial.job.job_id;
  const generation = useSession()?.generation;
  const cache = useQueryClient();
  const key = ["chat-job", generation, sessionId, jobId] as const;
  const params = { path: { session_id: sessionId, job_id: jobId } };
  const endpoint = "/api/v1/chat/sessions/{session_id}/jobs/{job_id}" as const;
  const poll = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => unwrap(api.GET(endpoint, { params, signal })),
    enabled: generation !== undefined && active(initial.job),
    placeholderData: initial,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => active(query.state.data?.job) && !query.state.error ? 1000 : false,
  });
  const cancel = useMutation({
    mutationFn: async () => {
      await cache.cancelQueries({ queryKey: key });
      return unwrap(api.DELETE(endpoint, { params }));
    },
    onSuccess: (reply) => { cache.setQueryData(key, reply); },
  });
  const job = (poll.data ?? initial).job;
  return (
    <div className="stack">
      <p role="status">{statusText[job.status]} · {job.job_kind === "how_to" ? "HOW-TO" : "WHAT-IF"}</p>
      {cancel.error || poll.error ? <ErrorPanel error={cancel.error ?? poll.error} /> : null}
      {active(job) ? <button type="button" className="btn btn-secondary small" disabled={cancel.isPending} onClick={() => cancel.mutate()}>Hủy mô phỏng</button> : null}
      {job.result?.kind === "how_to" ? <HowToResult reply={job.result} /> : null}
      {job.result?.kind === "what_if" ? <WhatIfResult reply={job.result} timezone={timezone} /> : null}
    </div>
  );
}

export function ChatAdvisory({ advisory, sessionId }: { advisory: Advisory[]; sessionId: string }) {
  return advisory.map((item, index) => {
    if (item.kind === "why") return <WhyResult key={index} reply={item} timezone={timezone} />;
    if (item.kind !== "job" || advisory.slice(index + 1).some(
      (candidate) => candidate.kind === "job" && candidate.job.job_id === item.job.job_id,
    )) return null;
    return <ChatJob key={item.job.job_id} initial={item} sessionId={sessionId} />;
  });
}
