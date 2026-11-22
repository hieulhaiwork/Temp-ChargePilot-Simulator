"use client";

/**
 * S8 · Mô phỏng kịch bản (mockup docs/mockups/van-hanh/operator-simulation.html; spec 21 §3.4; FR18, FR11 · US6, US8 · AC3, AC5, AC7 · MT1–MT6).
 * Chạy kịch bản trong config/scenarios với chiến lược A–D (POST /simulation/runs, chạy đồng bộ — không tự gửi lại),
 * bơm sự cố (POST /simulation/incidents, luôn hỏi xác nhận), bảng đối chứng từ GET /simulation/benchmark.
 * Giá trị trên màn này là kết quả MÔ PHỎNG, không phải số đo của trạm sạc thật.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { EmptyState, Notice, PageHead, Panel, SectionHead } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";
import { formatKw, formatKwh, formatVnd } from "@/lib/format";

type Strategy = components["schemas"]["StrategyName"];
type Run = components["schemas"]["SimulationRunResult"];
type IncidentType = components["schemas"]["IncidentType"];

const STRATEGIES: [Strategy, string][] = [
  ["A_fcfs", "A · FCFS"],
  ["A_edf", "A · EDF"],
  ["B", "B · Tối ưu, không ML"],
  ["C", "C · Tối ưu + dự báo"],
  ["D", "D · Biết trước"],
];
const label = (s: Strategy) => STRATEGIES.find(([k]) => k === s)?.[1] ?? s;

/** Hàng của bảng đối chứng: [tên, mục tiêu, giá trị, kiểm đạt (null = chỉ theo dõi)]. */
const KPI_ROWS: [string, string, (r: Run) => string, ((r: Run) => boolean) | null][] = [
  ["MT1 · Tỉ lệ đúng hạn", "≥ 95%", (r) => `${Math.round(r.kpis.on_time_rate * 100)}%`, (r) => r.kpis.on_time_rate >= 0.95],
  ["MT2 · Chờ trung bình / p90", "thấp hơn FCFS", (r) => `${Math.round(r.kpis.wait_mean_minutes)} / ${Math.round(r.kpis.wait_p90_minutes)} phút`, null],
  ["MT3 · Chi phí điện", "thấp hơn FCFS", (r) => formatVnd(r.kpis.energy_cost_vnd), null],
  ["Điện đã nạp", "—", (r) => formatKwh(r.kpis.delivered_energy_kwh), null],
  ["Đỉnh tải", "≤ giới hạn", (r) => formatKw(r.kpis.peak_load_kw), null],
  ["MT4 · Vi phạm giới hạn", "= 0", (r) => String(r.kpis.power_limit_violations), (r) => r.kpis.power_limit_violations === 0],
  ["MT5 · Lập lịch lại p95", "≤ 2 giây", (r) => (r.kpis.replan_p95_seconds != null ? `${r.kpis.replan_p95_seconds.toLocaleString("vi-VN")} giây` : "—"), (r) => r.kpis.replan_p95_seconds == null || r.kpis.replan_p95_seconds <= 2],
  ["MT6 · Lệnh bị Guard chặn", "theo dõi", (r) => String(r.kpis.blocked_commands), null],
];

function MutationError({ error, endpoint }: { error: unknown; endpoint: string }) {
  if (!error) return null;
  return error instanceof ApiError && error.isNotImplemented ? (
    <NotImplementedPanel endpoint={endpoint} taskId={error.taskId} detail={error.detail} />
  ) : (
    <ErrorPanel error={error} />
  );
}

function BenchTable({ runs }: { runs: Run[] }) {
  if (!runs.length) {
    return (
      <EmptyState icon="chart" title="Chưa có bảng đối chứng cho kịch bản này">
        Bấm Chạy để tạo cột đầu tiên.
      </EmptyState>
    );
  }
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <caption>Cùng tập phiên, cùng biểu giá · {runs[0].scenario_id}</caption>
        <thead>
          <tr>
            <th>Chỉ số</th>
            <th>Mục tiêu</th>
            {runs.map((r) => (
              <th key={r.run_id} className="num">
                {label(r.strategy)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {KPI_ROWS.map(([name, target, value, ok]) => (
            <tr key={name}>
              <td>
                <b>{name}</b>
              </td>
              <td className="hint">{target}</td>
              {runs.map((r) => (
                <td key={r.run_id} className="num">
                  {value(r)}{" "}
                  {ok ? (ok(r) ? <span className="pass">✓<span className="sr-only"> đạt</span></span> : <span className="fail">✕<span className="sr-only"> chưa đạt</span></span>) : null}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function downloadCsv(runs: Run[]) {
  const head = ["Chỉ số", ...runs.map((r) => label(r.strategy))];
  const lines = [head, ...KPI_ROWS.map(([name, , value]) => [name, ...runs.map(value)])].map((row) => row.map((c) => `"${c.replaceAll('"', '""')}"`).join(","));
  const url = URL.createObjectURL(new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "benchmark.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export default function OperatorSimulationPage() {
  const queryClient = useQueryClient();
  const scenarios = useQuery(queries.scenarios());
  const benchmark = useQuery(queries.benchmark());
  const [scenario, setScenario] = useState("");
  const [strategy, setStrategy] = useState<Strategy>("C");
  const [nVehicles, setNVehicles] = useState(30);
  const [seed, setSeed] = useState(42);
  const [extraRuns, setExtraRuns] = useState<Run[]>([]);
  const [incType, setIncType] = useState<IncidentType>("connector_fault");
  const [incConnector, setIncConnector] = useState("A03");
  const [incKw, setIncKw] = useState(20);
  const [asking, setAsking] = useState(false);

  const scenarioId = scenario || scenarios.data?.[0]?.scenario_id || "";
  const current = scenarios.data?.find((s) => s.scenario_id === scenarioId);
  const nError = !Number.isInteger(nVehicles) || nVehicles <= 0 ? "Số xe phải lớn hơn 0." : "";
  const run = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/simulation/runs", { body: { scenario_id: scenarioId, strategy, n_vehicles: nVehicles, seed } })),
    onSuccess: (r) => setExtraRuns((prev) => [...prev, r]),
  });
  const inject = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/simulation/incidents", {
          body: incType === "power_limit_change" ? { type: incType, new_power_limit_kw: incKw } : { type: incType, connector_id: incConnector },
        }),
      ),
    onSuccess: () => {
      setAsking(false);
      void queryClient.invalidateQueries({ queryKey: ["operator"] });
    },
  });
  const runs = [...(benchmark.data?.runs.filter((r) => r.scenario_id === scenarioId) ?? []), ...extraRuns.filter((r) => r.scenario_id === scenarioId)];

  return (
    <>
      <PageHead
        title="Mô phỏng kịch bản"
        sub="Chạy lại kịch bản, bơm sự cố và so chiến lược A–D. Kết quả là mô phỏng, không phải số đo của trạm thật."
        actions={
          <button type="button" className="btn btn-secondary" disabled={!runs.length} onClick={() => downloadCsv(runs)}>
            <Icon name="download" />
            Xuất CSV
          </button>
        }
      />
      <div className="cols">
        <Panel label="Chạy kịch bản">
          <SectionHead title="Chạy kịch bản" icon="flask" sub="POST /simulation/runs chạy đồng bộ" />
          {scenarios.isError ? (
            scenarios.error instanceof ApiError && scenarios.error.isNotImplemented ? (
              <NotImplementedPanel endpoint="GET /api/v1/simulation/scenarios" taskId={scenarios.error.taskId} detail={scenarios.error.detail} />
            ) : (
              <ErrorPanel error={scenarios.error} onRetry={() => void scenarios.refetch()} />
            )
          ) : null}
          <div className="fieldgrid" style={{ marginTop: 12 }}>
            <div className="field">
              <label htmlFor="sim-scen">Kịch bản</label>
              <select id="sim-scen" value={scenarioId} onChange={(e) => setScenario(e.target.value)} disabled={!scenarios.data?.length}>
                {scenarios.isPending ? <option>Đang tải kịch bản…</option> : null}
                {scenarios.data?.length === 0 ? <option>Chưa có kịch bản trong config/scenarios</option> : null}
                {scenarios.data?.map((s) => (
                  <option key={s.scenario_id} value={s.scenario_id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="sim-strat">Chiến lược</label>
              <select id="sim-strat" value={strategy} onChange={(e) => setStrategy(e.target.value as Strategy)}>
                {STRATEGIES.map(([k, l]) => (
                  <option key={k} value={k}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="sim-n">Số xe</label>
              <input id="sim-n" type="number" min={1} value={nVehicles} onChange={(e) => setNVehicles(Number(e.target.value))} aria-invalid={Boolean(nError) || undefined} aria-describedby="err-sim-n" />
              <span className="error" id="err-sim-n">{nError}</span>
            </div>
            <div className="field">
              <label htmlFor="sim-seed">Seed</label>
              <input id="sim-seed" type="number" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
            </div>
          </div>
          {current ? <p className="hint" style={{ marginTop: 10 }}>{current.description}</p> : null}
          <div className="actions">
            <button type="button" className="btn btn-primary" disabled={!scenarioId || Boolean(nError) || run.isPending} onClick={() => run.mutate()}>
              <Icon name="play" />
              {run.isPending ? "Đang chạy…" : "Chạy"}
            </button>
            {run.isSuccess ? <span role="status" className="hint">Chạy xong · đã thêm cột kết quả.</span> : null}
          </div>
          <MutationError error={run.error} endpoint="POST /api/v1/simulation/runs" />
        </Panel>
        <Panel dark label="Bơm sự cố">
          <SectionHead title="Bơm sự cố" icon="alert" sub="Tác động ngay lên trạm mô phỏng đang chạy" />
          <div className="stack" style={{ gap: 12 }}>
            <div className="field">
              <label htmlFor="inc-type">Loại sự cố</label>
              <select id="inc-type" value={incType} onChange={(e) => setIncType(e.target.value as IncidentType)}>
                <option value="connector_fault">Đầu nối lỗi</option>
                <option value="connector_restored">Đầu nối phục hồi</option>
                <option value="power_limit_change">Đổi giới hạn nguồn</option>
              </select>
            </div>
            {incType === "power_limit_change" ? (
              <div className="field">
                <label htmlFor="inc-kw">Giới hạn mới (kW)</label>
                <input id="inc-kw" type="number" min={0.5} step={0.5} value={incKw} onChange={(e) => setIncKw(Number(e.target.value))} />
              </div>
            ) : (
              <div className="field">
                <label htmlFor="inc-conn">Đầu nối</label>
                <input id="inc-conn" value={incConnector} onChange={(e) => setIncConnector(e.target.value.toUpperCase())} />
              </div>
            )}
          </div>
          {asking ? (
            <div role="alertdialog" aria-labelledby="inc-q" className="notice notice-gold" style={{ marginTop: 14 }}>
              <div>
                <strong id="inc-q">Bơm sự cố vào trạm mô phỏng?</strong>
                <p>Xe đang sạc có thể bị dừng hoặc giảm công suất, và lịch sẽ được tính lại.</p>
                <div className="actions" style={{ marginTop: 8 }}>
                  <button type="button" className="btn btn-secondary" autoFocus onClick={() => setAsking(false)}>
                    Không bơm
                  </button>
                  <button type="button" className="btn btn-danger" disabled={inject.isPending} onClick={() => inject.mutate()}>
                    {inject.isPending ? "Đang gửi…" : "Bơm sự cố"}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="actions">
              <button type="button" className="btn btn-warm" disabled={incType === "power_limit_change" ? !(incKw > 0) : !incConnector} onClick={() => setAsking(true)}>
                <Icon name="bolt" />
                Bơm sự cố
              </button>
            </div>
          )}
          {inject.isSuccess ? (
            <p role="status" style={{ marginTop: 10 }}>
              Đã bơm sự cố.{" "}
              <Link href="/operator" className="textbtn" style={{ color: "#ffda8a" }}>
                Xem Dashboard
              </Link>
            </p>
          ) : null}
          <div style={{ marginTop: 10 }}>
            <MutationError error={inject.error} endpoint="POST /api/v1/simulation/incidents" />
          </div>
        </Panel>
      </div>
      <Panel label="Bảng đối chứng">
        <SectionHead title="Bảng đối chứng A–D" icon="chart" sub="✓ đạt mục tiêu · ✕ chưa đạt" />
        <DataBlock endpoint="GET /api/v1/simulation/benchmark" query={queries.benchmark()} loadingLines={6}>
          {() => <BenchTable runs={runs} />}
        </DataBlock>
        {runs.some((r) => r.kpis.on_time_rate < 0.95) ? (
          <div style={{ marginTop: 12 }}>
            <Notice title="Có lần chạy chưa đạt MT1" tone="gold" icon="alert">
              Tỉ lệ đúng hạn dưới 95%. Xem ghi chú của lần chạy trong eval/results.
            </Notice>
          </div>
        ) : null}
      </Panel>
    </>
  );
}
