"use client";

/**
 * Hồ sơ cư dân (mockup cu-dan/resident-profile.html; spec 21 §2.7; F8, FR13). Xe mặc định, mức pin hay dùng,
 * phạm vi đã đồng ý trước (ConsentScope). NFR riêng tư: sửa và xoá được (xoá = ẩn danh hoá). Task: T2.8.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { DataBlock } from "@/components/system/DataBlock";
import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { Notice, PageHead, Panel, SectionHead } from "@/components/ui/blocks";
import { Icon } from "@/components/ui/Icon";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { queries } from "@/lib/api/queries";
import type { components } from "@/lib/api/schema";
import { clearSession } from "@/lib/auth/session";

type Profile = components["schemas"]["ResidentProfile"];

function MutationError({ error, endpoint }: { error: unknown; endpoint: string }) {
  if (!error) return null;
  return error instanceof ApiError && error.isNotImplemented ? (
    <NotImplementedPanel endpoint={endpoint} taskId={error.taskId} detail={error.detail} />
  ) : (
    <ErrorPanel error={error} />
  );
}

function ProfileForm({ profile }: { profile: Profile }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const vehicles = useQuery(queries.vehicles());
  const [draft, setDraft] = useState<Profile>(profile);
  const [confirmWord, setConfirmWord] = useState("");
  const [asking, setAsking] = useState(false);
  const consent = draft.consent ?? { max_start_delay_minutes: 30, allow_power_reduction: true, emergency_curtailment: true };
  const dirty = JSON.stringify(draft) !== JSON.stringify(profile);
  const nameError = !draft.display_name.trim() || draft.display_name.length > 80 ? "Tên hiển thị cần từ 1 đến 80 ký tự." : "";
  const socError = draft.default_soc_target != null && (draft.default_soc_target < 1 || draft.default_soc_target > 100) ? "Nhập mức pin từ 1 đến 100%." : "";

  const save = useMutation({
    mutationFn: (p: Profile) =>
      unwrap(
        api.PUT("/api/v1/resident/profile", {
          body: { display_name: p.display_name.trim(), vehicle_model: p.vehicle_model, default_soc_target: p.default_soc_target, consent: p.consent },
        }),
      ),
    onSuccess: (saved) => queryClient.setQueryData(queries.residentProfile().queryKey, saved),
  });
  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/resident/profile")),
    onSuccess: () => {
      try {
        sessionStorage.setItem("chargepilot.logoutReason", "deleted");
      } catch {
        /* bỏ qua */
      }
      clearSession();
      router.replace("/login");
    },
  });
  const setConsent = (patch: Partial<typeof consent>) => setDraft({ ...draft, consent: { ...consent, ...patch } });
  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!nameError && !socError) save.mutate(draft);
  }

  return (
    <div className="cols">
      <form className="stack" onSubmit={onSubmit} noValidate>
        <Panel label="Thông tin của tôi">
          <SectionHead title="Thông tin của tôi" icon="user" />
          <div className="stack" style={{ gap: 14 }}>
            <div className="field">
              <label htmlFor="p-name">Tên hiển thị</label>
              <input id="p-name" value={draft.display_name} maxLength={80} autoComplete="name" onChange={(e) => setDraft({ ...draft, display_name: e.target.value })} aria-invalid={Boolean(nameError) || undefined} aria-describedby="err-p-name" />
              <span className="error" id="err-p-name">{nameError}</span>
            </div>
            <div className="fieldgrid">
              <div className="field">
                <label htmlFor="p-vehicle">Xe mặc định</label>
                <select id="p-vehicle" value={draft.vehicle_model ?? ""} onChange={(e) => setDraft({ ...draft, vehicle_model: e.target.value || null })}>
                  <option value="">Chưa chọn</option>
                  {vehicles.data?.map((v) => (
                    <option key={v.vehicle_model} value={v.vehicle_model}>
                      {v.display_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="p-soc">Mức pin thường dùng (%)</label>
                <input id="p-soc" type="number" min={1} max={100} value={draft.default_soc_target ?? ""} onChange={(e) => setDraft({ ...draft, default_soc_target: e.target.value ? Number(e.target.value) : null })} aria-invalid={Boolean(socError) || undefined} aria-describedby="err-p-soc" />
                <span className="error" id="err-p-soc">{socError}</span>
              </div>
            </div>
          </div>
        </Panel>
        <Panel label="Quyền điều chỉnh của trạm">
          <SectionHead title="Quyền điều chỉnh của trạm" icon="shield" sub="Phạm vi trạm được tự điều chỉnh cho các lịch đặt sau khi lưu." />
          <div className="stack" style={{ gap: 14 }}>
            <div className="field">
              <label htmlFor="p-delay">Lùi giờ bắt đầu tối đa</label>
              <select id="p-delay" value={consent.max_start_delay_minutes} onChange={(e) => setConsent({ max_start_delay_minutes: Number(e.target.value) })}>
                {[0, 15, 30, 60, 120].map((m) => (
                  <option key={m} value={m}>
                    {m ? `${m} phút` : "Giữ nguyên giờ"}
                  </option>
                ))}
              </select>
            </div>
            <label className="switch-row">
              <span>
                <strong>Giảm công suất khi vẫn kịp hạn</strong>
                <small>Xe vẫn phải đạt mức pin bạn yêu cầu trước giờ lấy.</small>
              </span>
              <input type="checkbox" role="switch" checked={consent.allow_power_reduction} onChange={(e) => setConsent({ allow_power_reduction: e.target.checked })} />
            </label>
            <label className="switch-row">
              <span>
                <strong>Bảo vệ khẩn cấp</strong>
                <small>Cho phép trạm giảm công suất khi nguồn giảm và thông báo sau.</small>
              </span>
              <input type="checkbox" role="switch" checked={consent.emergency_curtailment} onChange={(e) => setConsent({ emergency_curtailment: e.target.checked })} />
            </label>
            {!consent.emergency_curtailment ? (
              <Notice title="Bạn chưa đồng ý trước với bảo vệ khẩn cấp" tone="gold" icon="shield">
                Quyền này được ghi nhận cho các lịch đặt sau.
              </Notice>
            ) : null}
          </div>
          <div className="actions">
            <button type="submit" className="btn btn-primary" disabled={!dirty || save.isPending}>
              <Icon name="check" />
              {save.isPending ? "Đang lưu…" : "Lưu thay đổi"}
            </button>
            <span className="hint" role="status">
              {save.isSuccess && !dirty ? "Đã lưu hồ sơ." : dirty ? "Có thay đổi chưa lưu." : "Đã lưu thông tin hiện tại."}
            </span>
          </div>
          <MutationError error={save.error} endpoint="PUT /api/v1/resident/profile" />
        </Panel>
      </form>
      <aside className="stack">
        <Panel label="Quản lý tài khoản">
          <SectionHead title="Quản lý tài khoản" icon="user" />
          <button type="button" className="btn btn-secondary" onClick={clearSession}>
            <Icon name="exit" />
            Đăng xuất
          </button>
          <h3 style={{ marginTop: 18 }}>Xoá tài khoản</h3>
          <p className="hint">Hồ sơ được ẩn danh hoá. Lịch sử sạc không còn gắn với bạn.</p>
          {asking ? (
            <div className="stack" style={{ gap: 10, marginTop: 10 }}>
              <div className="field">
                <label htmlFor="del-word">
                  Gõ <b>XOÁ</b> để xác nhận
                </label>
                <input id="del-word" value={confirmWord} autoComplete="off" onChange={(e) => setConfirmWord(e.target.value)} autoFocus />
              </div>
              <div className="actions" style={{ marginTop: 0 }}>
                <button type="button" className="btn btn-secondary" onClick={() => setAsking(false)}>
                  Giữ tài khoản
                </button>
                <button type="button" className="btn btn-danger" disabled={confirmWord.trim().normalize("NFC") !== "XOÁ" || remove.isPending} onClick={() => remove.mutate()}>
                  {remove.isPending ? "Đang xoá…" : "Xoá tài khoản"}
                </button>
              </div>
            </div>
          ) : (
            <div className="actions">
              <button type="button" className="btn btn-secondary" style={{ color: "var(--red)" }} onClick={() => setAsking(true)}>
                <Icon name="trash" />
                Xoá tài khoản
              </button>
            </div>
          )}
          <MutationError error={remove.error} endpoint="DELETE /api/v1/resident/profile" />
        </Panel>
      </aside>
    </div>
  );
}

export default function ResidentProfilePage() {
  return (
    <>
      <PageHead title="Hồ sơ của tôi" sub="Thông tin xe và lựa chọn cho các lần sạc tiếp theo." />
      <DataBlock endpoint="GET /api/v1/resident/profile" query={queries.residentProfile()} loadingLines={5}>
        {(profile) => <ProfileForm profile={profile} />}
      </DataBlock>
    </>
  );
}
