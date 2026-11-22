# Worklog — Team T019 (ChargePilot, SC-16)

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.
> Nguồn: commit và PR trên GitHub (`git log --all`, `gh pr list`). Cột **Time** để "—" vì repo không ghi nhận số giờ;
> thành viên tự bổ sung nếu cần. Tên thành viên = tên trong commit.

---

## 2026-11-22

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| LufkyMama | Backend chạy thật: repository + auth JWT, Guard 7 luật + phê duyệt + khẩn cấp, optimizer FCFS/EDF/LP/MPC, LiveStation, control loop, WebSocket | ✅ Done | PR #8 (405 test) | — |
| LufkyMama | Sửa CI: job simulator không import được `src`, nới timeout cho runner VM; chạy lại job lỗi do mạng | ✅ Done | `pytest.ini`, `ci.yml`; CI 6/6 xanh | — |
| LufkyMama | Deploy bản test: job CI `deploy` (Docker Hub + Render Deploy Hook), Render Existing Image, Neon, Vercel CLI | ✅ Done | PR #9, #10; <https://p019-web.vercel.app> | — |
| LufkyMama | ADR-016 LiveStation cho backend; benchmark A–D có bằng chứng | ✅ Done | `docs/adr/ADR-016…`, `eval/evidence/2026-11-22/` | — |
| LufkyMama | LP tôn trọng consent lùi giờ; bật vòng nền để trạm tự vận hành; rà và dọn tài liệu; điền deliverable | 🔄 WIP | Nhánh `fix/booking-charging-state` (chưa merge) | — |
| HaiVuu | Sửa các vấn đề review của Agent / DB, thêm bằng chứng eval thủ công Agent F1 | 🔄 WIP | PR #12 (mở) | — |

**Tổng kết ngày:** Backend chạy đầu-cuối và có bản test online (web + API + DB). CI xanh trên `develop`, merge là tự
deploy backend. Còn chờ merge nhánh sửa consent / vòng nền và PR #12.

---

## 2026-11-21

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| LufkyMama | Căn chỉnh hướng nghiên cứu SC-16: ADR-010…015, PRD v0.4, business overview, thiết kế trả lời 3 tầng | ✅ Done | PR #5 | — |
| LufkyMama | Chuyển topology sang bãi hybrid AC/DC (fixture `mvp1`) — T1.10; lưu bằng chứng chạy lại R&D | ✅ Done | PR #5, `eval/evidence/2026-11-21/` | — |
| Le Hien Hieu | Optimizer DC (MVP-2), AC Optimizer + Global Optimizer (MVP-3, bản chưa cuối); hướng dẫn tích hợp cho backend | ✅ Done | PR #7 | — |
| HaiVuu | Agent: streaming SSE, gợi ý trả lời nhanh, prompt bãi hybrid AC/DC | ✅ Done | PR #6 | — |
| LamBui | SiteMap (sơ đồ bãi), hook pre-push gửi log AI, sửa lỗi UI, khôi phục tích hợp API phê duyệt | ✅ Done | PR #4 | — |

**Tổng kết ngày:** Cả nhóm chuyển sang bãi hybrid AC/DC; simulator, Agent và giao diện được merge vào nhánh chính.

---

## 2026-11-20

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| LamBui | Màn vận hành cho bãi AC/DC: dashboard, phê duyệt, mô phỏng; sửa lỗi FR3 đặt lịch, ESLint | ✅ Done | Nhánh UI (PR #3, đã đóng) | — |
| LamBui | Bộ quét log cho Antigravity IDE + cấu hình hook | ✅ Done | `scripts/log_antigravity.py` | — |
| LufkyMama | R&D: song song hoá đánh giá phương án AI-1; ablation độ bền AI-2 | ✅ Done | Nhánh `experiment/…` (không merge) | — |

**Tổng kết ngày:** Giao diện vận hành theo bãi hybrid; nhánh R&D thử thêm độ bền mô hình.

---

## 2026-11-19

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Le Hien Hieu | Simulator EV2Gym hybrid: hardening MVP-1 (v1.1), kiến trúc AC/DC module hoá, profile sạc DC VinFast, bộ test + tài liệu | ✅ Done | `src/simulator/` (PR #7) | — |
| Le Hien Hieu | Trang replay tĩnh cho simulator | ✅ Done | `frontend/public/chargepilot-replay.html` | — |
| LufkyMama | Dựng giao diện theo template mockup (Forest & Amber); gộp mockup về một template cư dân + bộ vận hành + sơ đồ bãi | ✅ Done | `frontend/`, `docs/mockups/` | — |
| LufkyMama | ADR-010 bãi hybrid AC/DC; cập nhật plan / UI spec | ✅ Done | `docs/adr/ADR-010…` | — |
| LufkyMama | Nhánh R&D: AI-1 xung đột + what-if có kiểm chứng + HITL, AI-2 telemetry / phát hiện bất thường, AI-3, AI-4 copilot, báo cáo kỹ thuật | ✅ Done | Nhánh `experiment/…` (không merge) | — |
| LufkyMama | Merge skeleton vào nhánh chính | ✅ Done | PR #1, #2 | — |
| LamBui | Cấu hình hook log AI cho Antigravity; cập nhật màu giao diện | ✅ Done | — | — |

**Tổng kết ngày:** Simulator thật và giao diện đầu tiên ra đời; R&D thử 4 hướng AI.

---

## 2026-11-18

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| LamBui | Mở rộng 4 màn vận hành desktop | ✅ Done | Nhánh UI | — |

**Tổng kết ngày:** Bắt đầu làm giao diện vận hành trên skeleton.

---

## 2026-11-17

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| LufkyMama | Skeleton contract-first: Agent / Optimizer / Guard, DB 9 bảng + Alembic, API REST + WebSocket, Next.js, Docker | ✅ Done | Commit skeleton | — |
| LufkyMama | CI trên self-hosted runner `team-19`; hướng dẫn dựng runner trong VM | ✅ Done | `.github/workflows/ci.yml`, `docs/plan/55-ci-runner.md` | — |
| LufkyMama | Đặc tả UI 11 màn, mockup HTML + design system + plugin Figma, plan chia việc UI | ✅ Done | `docs/plan/21…`, `22…`, `docs/mockups/` | — |
| LufkyMama | Sinh lại `package-lock.json` bằng Node 22 cho `npm ci` trên CI | ✅ Done | Job frontend xanh | — |

**Tổng kết ngày:** Có skeleton chạy được, CI và đặc tả UI để cả nhóm làm song song.

---

## 2026-11-16

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| LufkyMama | Pha A: khảo sát template, lập plan backend / frontend / AI / database / DevOps, ADR-005…009 | ✅ Done | `docs/plan/00…50`, `docs/adr/` (commit ngày 17/11) | — |

**Tổng kết ngày:** Có plan chi tiết để dựng skeleton.

---

## 2026-11-05

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| (BTC) | Tạo repo `P-019` từ AI20K Agent Template | ✅ Done | Initial commit | — |

**Tổng kết ngày:** Nhận repo của đội. Công việc 05/11 – 15/11 chưa được ghi trong repo — [nhóm bổ sung].

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
