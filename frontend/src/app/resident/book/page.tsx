"use client";

/**
 * Đặt lịch sạc bằng biểu mẫu (mockup cu-dan/resident-book.html; spec 21 §2.4; FR2, FR3, FR9, FR13).
 * Đường dự phòng khi Trợ lý không dùng được (NFR khả dụng). Đi CÙNG charging_service với đường chat:
 * POST /energy/estimate (kWh do code tính, FR3) → POST /resident/quote → S3 (/resident/plan).
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { KeyValues, Notice, PageHead, Panel, SectionHead } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import { saveDraft, type ChargeRequest } from "@/lib/booking/draft";
import { formatKwh } from "@/lib/format";

/** "2026-11-17T23:00" (giờ trạm) → ISO có múi giờ +07:00 cho backend. */
const toIso = (local: string) => (local ? `${local}:00+07:00` : "");

function tomorrowAt(hhmm: string, addDays: number): string {
  const d = new Date(Date.now() + 7 * 3600_000 + addDays * 86400_000);
  return `${d.toISOString().slice(0, 10)}T${hhmm}`;
}

type Errors = Partial<Record<"soc_now" | "soc_target" | "deadline", string>>;

export default function ResidentBookPage() {
  const router = useRouter();
  const vehicles = useQuery(queries.vehicles());
  const [vehicle, setVehicle] = useState("");
  const [socNow, setSocNow] = useState(32);
  const [socTarget, setSocTarget] = useState(80);
  const [mode, setMode] = useState<"reservation" | "walk_in">("reservation");
  const [arrival, setArrival] = useState(() => tomorrowAt("23:00", 0));
  const [deadline, setDeadline] = useState(() => tomorrowAt("07:00", 1));
  const [errors, setErrors] = useState<Errors>({});

  const model = vehicle || vehicles.data?.[0]?.vehicle_model || "";
  const request: ChargeRequest = {
    vehicle_model: model,
    soc_now: socNow,
    soc_target: socTarget,
    mode,
    zone: "AC",
    arrival_time: mode === "reservation" ? toIso(arrival) : null,
    deadline: toIso(deadline),
  };

  const estimate = useQuery({
    queryKey: ["energy-estimate", model, socNow, socTarget],
    queryFn: () => unwrap(api.POST("/api/v1/energy/estimate", { body: { vehicle_model: model, soc_now: socNow, soc_target: socTarget } })),
    enabled: Boolean(model) && socTarget > socNow && socTarget <= 100,
  });

  const quote = useMutation({
    mutationFn: (body: ChargeRequest) => unwrap(api.POST("/api/v1/resident/quote", { body })),
    onSuccess: (proposal, body) => {
      saveDraft({ request: body, proposal, createdAt: new Date().toISOString() });
      router.push("/resident/plan?view=draft");
    },
  });

  function validate(): Errors {
    const e: Errors = {};
    if (!Number.isInteger(socNow) || socNow < 0 || socNow > 99) e.soc_now = "Nhập pin hiện tại từ 0 đến 99%.";
    if (!Number.isInteger(socTarget) || socTarget <= socNow || socTarget > 100) e.soc_target = "Mục tiêu phải cao hơn pin hiện tại và tối đa 100%.";
    if (!deadline) e.deadline = "Chọn giờ cần lấy xe.";
    else if (mode === "reservation" && arrival && deadline <= arrival) e.deadline = "Giờ lấy xe phải sau giờ cắm xe.";
    return e;
  }
  function onSubmit(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length === 0) quote.mutate(request);
  }
  // Lỗi 422 của backend gắn vào đúng ô (ApiError.fields.path = tên trường).
  const serverField = (name: string) =>
    quote.error instanceof ApiError ? quote.error.fields.find((f) => f.path.endsWith(name))?.message : undefined;
  const err = (name: keyof Errors) => errors[name] ?? serverField(name);

  return (
    <>
      <PageHead title="Đặt lịch sạc" sub="Chọn mức pin và thời điểm bạn cần lấy xe." />
      <DataBlock endpoint="GET /api/v1/resident/bookings/current" query={queries.residentBooking()} loadingLines={1}>
        {(booking) =>
          booking ? (
            <Notice title="Xe đang có lịch hiệu lực" tone="gold" icon="calendar">
              Mỗi xe chỉ giữ một lịch. <Link href="/resident/plan" className="textbtn">Xem lịch đang giữ</Link>
            </Notice>
          ) : null
        }
      </DataBlock>
      <div className="cols">
        <form className="stack" onSubmit={onSubmit} noValidate>
          <Panel label="Xe và mức pin">
            <SectionHead title="Xe và mức pin" icon="car" />
            <div className="stack" style={{ gap: 14 }}>
              <div className="field">
                <label htmlFor="vehicle">Mẫu xe</label>
                {vehicles.isError ? (
                  vehicles.error instanceof ApiError && vehicles.error.isNotImplemented ? (
                    <NotImplementedPanel endpoint="GET /api/v1/vehicles" taskId={vehicles.error.taskId} />
                  ) : (
                    <ErrorPanel error={vehicles.error} onRetry={() => void vehicles.refetch()} />
                  )
                ) : (
                  <select id="vehicle" value={model} onChange={(e) => setVehicle(e.target.value)} disabled={vehicles.isPending || !vehicles.data?.length}>
                    {vehicles.isPending ? <option>Đang tải danh mục xe…</option> : null}
                    {vehicles.data?.length === 0 ? <option>Danh mục xe trống</option> : null}
                    {vehicles.data?.map((v) => (
                      <option key={v.vehicle_model} value={v.vehicle_model}>
                        {v.display_name} · {v.usable_capacity_kwh} kWh
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <div className="fieldgrid">
                <div className="field">
                  <label htmlFor="soc-now">Pin hiện tại (%)</label>
                  <input id="soc-now" type="number" inputMode="numeric" min={0} max={99} value={socNow} onChange={(e) => setSocNow(Number(e.target.value))} aria-invalid={Boolean(err("soc_now")) || undefined} aria-describedby="err-soc-now" />
                  <span className="error" id="err-soc-now">{err("soc_now")}</span>
                </div>
                <div className="field">
                  <label htmlFor="soc-target">Pin mong muốn (%)</label>
                  <input id="soc-target" type="number" inputMode="numeric" min={1} max={100} value={socTarget} onChange={(e) => setSocTarget(Number(e.target.value))} aria-invalid={Boolean(err("soc_target")) || undefined} aria-describedby="err-soc-target" />
                  <span className="error" id="err-soc-target">{err("soc_target")}</span>
                </div>
              </div>
            </div>
          </Panel>
          <Panel label="Thời gian ở trạm">
            <SectionHead title="Thời gian ở trạm" icon="clock" />
            <fieldset className="seg" style={{ marginBottom: 14 }}>
              <legend className="sr-only">Cách đến trạm</legend>
              {(
                [
                  ["reservation", "Đặt trước"],
                  ["walk_in", "Đến trực tiếp"],
                ] as const
              ).map(([value, label]) => (
                <button key={value} type="button" aria-pressed={mode === value} onClick={() => setMode(value)}>
                  {label}
                </button>
              ))}
            </fieldset>
            <div className="fieldgrid">
              <div className="field">
                <label htmlFor="arrival">Giờ cắm xe</label>
                <input id="arrival" type="datetime-local" value={arrival} disabled={mode === "walk_in"} onChange={(e) => setArrival(e.target.value)} />
                {mode === "walk_in" ? <span className="hint">Lấy giờ bạn tới trạm.</span> : null}
              </div>
              <div className="field">
                <label htmlFor="deadline">Giờ cần lấy xe</label>
                <input id="deadline" type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} aria-invalid={Boolean(err("deadline")) || undefined} aria-describedby="err-deadline" />
                <span className="error" id="err-deadline">{err("deadline")}</span>
              </div>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn-primary" disabled={quote.isPending || !model}>
                <Icon name="arrow" />
                {quote.isPending ? "Đang tính phương án…" : "Xem phương án"}
              </button>
            </div>
            {quote.isError && !(quote.error instanceof ApiError && quote.error.fields.length) ? (
              <div style={{ marginTop: 12 }}>
                {quote.error instanceof ApiError && quote.error.isNotImplemented ? (
                  <NotImplementedPanel endpoint="POST /api/v1/resident/quote" taskId={quote.error.taskId} detail={quote.error.detail} />
                ) : (
                  <ErrorPanel error={quote.error} />
                )}
              </div>
            ) : null}
          </Panel>
        </form>
        <aside className="stack">
          <Panel label="Ước tính">
            <SectionHead title="Ước tính trước khi đặt" icon="bolt" sub="Điện năng do hệ thống tính, không do Trợ lý" />
            {!model || socTarget <= socNow ? (
              <p className="subcopy">Nhập mẫu xe và mức pin để xem ước tính.</p>
            ) : estimate.isPending ? (
              <p role="status" className="hint">Đang tính…</p>
            ) : estimate.isError ? (
              estimate.error instanceof ApiError && estimate.error.isNotImplemented ? (
                <NotImplementedPanel endpoint="POST /api/v1/energy/estimate" taskId={estimate.error.taskId} />
              ) : (
                <ErrorPanel error={estimate.error} onRetry={() => void estimate.refetch()} />
              )
            ) : (
              <KeyValues
                rows={[
                  ["Điện vào pin", formatKwh(estimate.data.battery_energy_kwh)],
                  ["Điện lấy từ lưới", formatKwh(estimate.data.grid_energy_kwh)],
                ]}
              />
            )}
            <p className="hint" style={{ marginTop: 12 }}>
              Chi phí và khung giờ có ở bước xem phương án.
            </p>
          </Panel>
        </aside>
      </div>
    </>
  );
}
