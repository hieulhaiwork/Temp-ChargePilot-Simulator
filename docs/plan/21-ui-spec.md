# Plan 21 — Đặc tả UI chi tiết: S1–S8, đặt lịch bằng form, thông báo, hồ sơ

> **Hiện trạng 23/11/2026 (ADR-019, refactor Unified Core Phase 4) — đọc trước, ưu tiên hơn nội dung bên dưới:**
> backend chạy `HybridStation` trên một kernel `StationKernel` dùng chung với `HybridSimulator`; `LiveStation` và LP
> backend A–D (`mpc`, `lp_model`, `assignment`, `baselines`, `strategies`) **đã xoá**, A–D bỏ khỏi `StrategyName` /
> OpenAPI / S8. Policy hiện hành: B0 / M2b / M3a / M3b (`src/optimizer/registry.py`). Benchmark S8 = baseline có version
> (`eval/evidence/2026-11-23-refactor-phase3-baseline/`); bảng A–D cũ là archive deprecated. Quote / booking = admission
> trên bản fork, kết quả là ước tính có điều kiện, không phải SLA. Chỗ nào bên dưới còn nhắc `LiveStation` / A–D /
> `lp_model` là plan lịch sử.
>
> **Cập nhật 21/11/2026 theo [ADR-010](../adr/ADR-010-bai-hybrid-ac-dc.md)…[ADR-015](../adr/ADR-015-pham-vi-mvp4-va-quy-tac-bang-chung.md).**
> Bãi không còn là 8 đầu nối × 7 kW / giới hạn 35 kW: số cổng, ID đầu nối, công suất từng cổng và giới hạn **lấy từ
> API** (fixture nền 4 cổng: 2 AC 11 kW + 1 tủ DC 2 cổng 60 kW, ADR-010). ID kiểu A01–A08, A07 và số 35 kW / 7 kW còn
> trong wireframe ASCII là minh hoạ của bản cũ, không hardcode. Phạm vi MVP-4 thêm **màn Copilot WHY / WHAT-IF**
> (vận hành; cư dân chỉ với xe của mình; WHAT-IF luôn hiện "chưa áp dụng") và **thẻ đề nghị AI-1** (Proposal / HITL:
> đồng ý / từ chối, hết hạn thì không áp dụng) — [ADR-014](../adr/ADR-014-decision-trace-counterfactual-hitl.md);
> spec chi tiết chưa viết. Nội dung dưới đây không viết lại.

> Trạng thái: đề xuất, chờ nhóm duyệt (2026-11-17). Bổ sung cho [20-frontend](20-frontend.md). Plan 20 chốt kiến trúc
> web; file này đặc tả **từng màn**: bố cục, nút → endpoint và field, trạng thái, realtime, accessibility.
> Nguồn, theo thứ tự ưu tiên khi mâu thuẫn: code `src/models/*.py`, `src/api/*.py`, `src/services/*.py` (CODE WINS) →
> PRD v0.2 → Wireframe v0.1 (PRD thắng Wireframe) → [20-frontend](20-frontend.md), [10-backend](10-backend.md) §3 §8,
> [ADR](../adr/README.md). PRD và Wireframe đọc trên Drive ngày 2026-11-17.
> Hợp đồng: `frontend/openapi.json` (42 thao tác REST) và `src/api/ws.py` (2 kênh WebSocket; OpenAPI không mô tả được WS).
> Owner: TV4 (giao diện), TV3 (mục 4 — Gap backend). Task: T2.7, T2.8, T3.3, T3.6, T4.3, T2.9.
>
> **Đổi 2026-11-19** (00 §12, chờ nhóm duyệt): (1) nguồn thiết kế cư dân là bộ [`docs/mockups/cu-dan/`](../mockups/cu-dan/HUONG-DAN.md),
> nguồn thiết kế vận hành là nhánh `origin/buivanlam` (§0.5); (2) token đổi sang "Forest & Amber" (§1.1); (3) bãi hybrid
> AC + DC theo [ADR-010](../adr/ADR-010-bai-hybrid-ac-dc.md); (4) thêm S9 Sơ đồ bãi: cư dân §2.8, vận hành §3.5, gap G22–G24.
> Bảng endpoint ↔ field ở §2, §3 vẫn đúng. Chỗ nào mâu thuẫn với bố cục ASCII cũ thì theo mockup mới.

## 0. Cách đọc

### 0.1 Ký hiệu và quy ước

- ✅ chạy thật · 🧩 stub trả 501 (kèm `task_id`) · 🆕 Gxx = UI cần nhưng backend chưa có, chi tiết ở mục 4.
- Endpoint viết **không có** tiền tố `/api/v1`, giống 10 §3. Chỉ `GET /health` và `GET /ready` nằm ở gốc. Tham số path
  viết đúng tên trong OpenAPI: `{booking_id}`, `{approval_id}`, `{connector_id}`, `{notification_id}`.
- Field viết `Model.field` hoặc `Model.field.sub` theo tên schema trong `openapi.json`, vd `ScheduleProposal.slack_minutes`.
  `[]` nghĩa là phần tử của mảng, vd `StationState.connectors[].power_kw`. Trong code TypeScript, kiểu lấy từ
  `components["schemas"][…]` của `src/lib/api/schema.d.ts`, không gõ tay DTO (ADR-009).
- Cột **Task BE** là `task_id` backend trả trong 501 **hôm nay**, đọc từ `NotImplementedError` trong code. Vài chỗ khác
  bảng 10 §3; khi đó theo code. Cột **Task UI** là task làm giao diện (bảng 00 §4).
- Trước khi T1.7 xong, mọi endpoint cần token đều trả **501 `T1.7`**, kể cả `POST /auth/login`, vì `authenticate` và
  `decode_token` còn stub. Gọi không có token thì nhận 401.
- Lỗi chung (mất mạng, 401, 403, 500, 503 `database_unavailable`) xử lý một lần theo mục 1.6. Bảng của từng màn chỉ ghi
  mã lỗi riêng của thao tác đó.
- Wireframe ASCII chỉ thể hiện vùng và thứ tự đọc, không phải kích thước pixel. Số liệu trong wireframe là minh hoạ.

### 0.2 Trạng thái endpoint hôm nay

| Task BE | Endpoint |
|---|---|
| ✅ | `GET /vehicles`, `GET /tariff`, `GET /station/config`, `POST /energy/estimate`, `GET /health`. `GET /simulation/scenarios` cũng chạy thật nhưng cần token operator, nên trước khi xong T1.7 vẫn thấy 501 `T1.7` |
| ✅ có điều kiện | `POST /chat`, `POST /chat/resume`: cần `OPENAI_API_KEY` thật và T1.7. Tool bên trong gọi `charging_service` còn stub (T2.2), nên Agent chưa đặt được lịch |
| T1.7 | `POST /auth/login`, `GET /auth/me`, cùng mọi endpoint cần token |
| T1.6 | `GET /resident/notifications`, `POST /resident/notifications/{notification_id}/read`, `GET /resident/approvals/{approval_id}`, `GET /operator/approvals`, `GET /operator/commands/blocked`, `GET /operator/decision-log` |
| T2.2 | `POST /resident/quote`, `POST /resident/bookings`, `GET /resident/bookings/current`, `DELETE /resident/bookings/{booking_id}`, `GET /resident/session`, `GET /resident/queue` |
| T2.5 | `GET /resident/explanation` |
| T2.6 | `POST /operator/schedule/replan` |
| T2.8 | `PATCH /resident/bookings/{booking_id}`, `GET /resident/profile`, `PUT /resident/profile`, `DELETE /resident/profile` |
| T3.2 | `POST /resident/approvals/{approval_id}`, `POST /operator/approvals/{approval_id}`, `POST /operator/queue/{booking_id}/assign` |
| T3.6 | `GET /operator/station`, `GET /operator/load`, `GET /operator/connectors/{connector_id}`, `GET /operator/events`, `GET /operator/schedule`, `GET /operator/bookings`. Hai kênh `WS /ws/operator` và `WS /ws/resident` hiện mở xong là đóng ngay với mã 1011 |
| T1.5 | `POST /simulation/runs`. Chuỗi lỗi là `[T1.5/T3.4]`; handler trong `src/main.py` lấy task đầu tiên |
| T3.4 | `GET /simulation/benchmark` |
| T3.5 | `POST /simulation/incidents` |
| Không màn nào dùng | `GET /status` (trạng thái Agent, còn từ template), `GET /ready` (readiness cho hạ tầng) |

### 0.3 Điểm cố ý khác Wireframe

| Màn | Wireframe | Spec này | Lý do |
|---|---|---|---|
| Tất cả | Tên "ChargeMind" | "ChargePilot" | PRD; `PROJECT_CONTEXT.md` §0.2 |
| S1 | Có chọn vai trò | Không có; vai trò lấy từ `TokenResponse.role` | Q4; 20 §6 |
| S2 | "Xe: VF8 · 51H-\*\*\*.\*\*" | Chỉ hiện tên mẫu xe, không có biển số | Không field nào chứa biển số; NFR riêng tư (mã giả danh, không thu dữ liệu hành trình) |
| S2 | "Gợi ý giờ rẻ (F6)" | Chip lấy khung `off_peak` từ `GET /tariff`, không dùng ML | Q5 |
| S3 | "A07 (AC 11 kW)" | ID và công suất tối đa lấy từ API `GET /station/config` (fixture nền 4 cổng, ADR-010) | ADR-010; `PROJECT_CONTEXT.md` |
| S4 | "Tự áp dụng sau: 04:12" | "Hết hạn sau mm:ss", kèm câu "không trả lời thì điều chỉnh **không** được áp dụng" | AC4; 20 §8 |
| S4 | "giảm 11 → 7 kW trong 40 phút" | Số lấy từ `Approval.command`; công suất trước và khung giờ chỉ có khi xong G7 | PRD; G7 |
| S5 | "128/150 kW", "14 xe", lưới có D01, D02 | Đầu nối, vùng AC / DC và giới hạn lấy từ API (fixture nền 4 cổng, ADR-010); mọi số lấy từ API | ADR-010; số của wireframe chỉ minh hoạ |
| S5 | Trạng thái chỉ bằng chấm màu | Chữ + icon + màu | WCAG 1.4.1; 20 §9 |
| S7 | Hai tab | Ba tab, thêm "Nhật ký quyết định" | FR14; 20 §3 đã gán `GET /operator/decision-log` cho S7 |
| S8 | "ChargeMind / FCFS", "150 kW" | 5 chiến lược `A_fcfs`, `A_edf`, `B`, `C`, `D`; giới hạn mặc định theo kịch bản, lấy từ API (fixture nền 4 cổng, ADR-010) | FR18; PRD §8 |

### 0.4 Làm rõ thêm so với 20-frontend (không đổi quyết định nào)

| # | Điểm | Lý do |
|---|---|---|
| R1 | Từ S2 sang S3 bằng nút "Xem chi tiết", không tự chuyển trang khi `status = needs_confirmation` | Wireframe có nút này; WCAG 3.2.2 không cho đổi ngữ cảnh ngoài ý người dùng. Vẫn "mang theo proposal" như 20 §8 |
| R2 | S3 có 3 chế độ: chat, form, booking (xem, đổi, huỷ lịch đang có) | 20 §3 gán `PATCH /resident/bookings/{booking_id}`, `DELETE /resident/bookings/{booking_id}` và `GET /resident/explanation` cho S3 |
| R3 | Bản ghi chat giữ trong `sessionStorage` theo `session_id` | 20 §8 đã giữ `session_id` ở đó; backend không có API lịch sử chat |
| R4 | "Sự kiện gần nhất" ở S5 gộp `StationEvent` với lệnh bị Guard chặn | FR12, AC6 yêu cầu "hiện trên dashboard"; ví dụ trong Wireframe chính là một lệnh bị chặn |
| R5 | S5 có nút "Tạm dừng cập nhật trực tiếp" | WCAG 2.2.2 |
| R6 | `QueryBoundary` (20 §3) = `EndpointBlock` hiện có, thêm `children(data)` | Comment trong `EndpointBlock.tsx` đã ghi: thay phần hiện JSON, giữ cách xử lý trạng thái |
| R7 | Chỉ làm giao diện sáng | Ngoài phạm vi. Token đặt trong `@theme` nên thêm dark mode sau không phải sửa component |
| R8 | Thêm một số component (mục 1.5) | Lý do ghi ở từng dòng |

### 0.5 Nguồn thiết kế (đổi 2026-11-19)

Thứ tự ưu tiên về **bố cục và chữ**: mockup mới → spec này → mockup cũ. Về **dữ liệu** (endpoint, field, mã lỗi) vẫn là
CODE WINS và các bảng của spec này. Mockup cũ (`resident*.html`, `operator*.html` ở gốc `docs/mockups/`, `_shared/`, `_figma/`, `design-system.html`) đã xoá ngày 2026-11-19; mọi màn giờ dùng chung template `cu-dan/assets/ui.css` (xem `docs/mockups/index.html`).

**Cư dân: bộ `cu-dan`** (chép từ `ChargePilot_CuDan`; Figma SVG 390 px và 1.440 px nằm ở `cu-dan/figma/`)

| Màn `cu-dan` | File | Route | Spec | Số tình huống | Khác spec cũ |
|---|---|---|---|---|---|
| 1. Trang chủ | `resident.html` | `/resident` | §2.2 | 13 | Thẻ chính đặt **giờ đạt mục tiêu** lên đầu; có 4 mốc (cắm → bắt đầu → đạt → lấy xe); Trợ lý nằm ngay trong trang chủ, không tách màn |
| 2. Đặt lịch sạc | `resident-book.html` | `/resident/book` | §2.4 | 9 | Thêm chế độ "Đến trực tiếp" bên cạnh "Đặt trước"; ước tính điện vào pin / từ lưới / chi phí ngay trong form |
| 3. Phương án và lịch sạc | `resident-plan.html` | `/resident/plan` | §2.3 | 17 | Một màn cho cả "duyệt phương án" lẫn "quản lý lịch"; có dải thời gian với khung thấp điểm; chọn phương án thay thế khi trễ giờ |
| 4. Thông báo | `resident-notifications.html` | `/resident/notifications` | §2.5 | 8 | 3 bộ lọc Tất cả / Chưa đọc / Cần phản hồi; 4 loại tin |
| 5. Đề nghị điều chỉnh | `resident-approval.html` | `/resident/notifications/[approvalId]` | §2.6 | 15 | So sánh trước / sau, ghi chú ≤ 500 ký tự. Cần G7 cho công suất trước và khung giờ |
| 6. Hồ sơ | `resident-profile.html` | `/resident/profile` | §2.7 | 10 | — |
| 7. Sơ đồ bãi (mới) | `resident-map.html` | `/resident/map` | §2.8 | 7 | Màn thứ 7 của bộ `cu-dan`; bộ vẽ `assets/site-map.js` dùng chung với S9 vận hành |

- Khung trang: trên máy tính có sidebar trái 216 px (Trang chủ · Đặt lịch · Lịch sạc · **Sơ đồ bãi** · Thông báo · Hồ sơ),
  trên điện thoại có thanh điều hướng dưới với 5 mục (Trang chủ · Đặt lịch · **Sơ đồ** · Thông báo · Hồ sơ). Khung này
  **thay** chuông + menu ☰ ở §1.4.
- Nút "Kịch bản mẫu" và `scenario-runner.js` chỉ có trong bản mẫu, không đưa vào sản phẩm.
- Số trong bộ `cu-dan` là số cũ (A07, 7 kW → 3,5 kW). Không sửa mockup của người thiết kế (Q16); code lấy số từ API.

**Vận hành: nhánh `origin/buivanlam`** (commit `876607b` mở rộng 4 màn, `d77e628` đổi màu)

- Code sẵn có: `frontend/src/app/operator/{page,schedule/page,approvals/page,simulation/page}.tsx`, `RoleShell.tsx`,
  `globals.css`. Nhánh chưa merge vào `develop`. Merge xong thì dùng làm điểm xuất phát cho S5–S8, thay cho mockup
  `operator*.html`.
- Phải sửa khi nối API thật: các trang đang dùng mảng hằng (`DEFAULT_CONNECTORS` với A01–A08, "35 kW"). Hằng phải đổi sang
  dữ liệu `queries.operatorStation()`, cổng và giới hạn lấy từ `/station/config` (ADR-004: không hardcode).
- Thêm tab "Sơ đồ bãi" vào `NAV.operator` (§3.5).

## 1. Nền tảng chung

### 1.1 Design tokens

> **Đổi 2026-11-19: bộ token "Forest & Amber" thay toàn bộ bảng màu bên dưới.** Đây là bộ token chung của `cu-dan/assets/ui.css`
> và `globals.css` của nhánh `buivanlam`. Bảng màu xanh dương cũ giữ lại bên dưới chỉ để đối chiếu. Font đổi sang
> **Be Vietnam Pro** tự host (OFL, file ở `cu-dan/assets/`). Bo góc thẻ 19 px, nút 11–12 px.
>
> | Token | Hex | Dùng cho | Tương phản (WCAG 2.1, tính 2026-11-19) |
> |---|---|---|---|
> | `--bg` / `--paper` / `--wash` | `#f5f6f2` / `#ffffff` / `#eff3ed` | nền trang / thẻ / khối phụ | — |
> | `--ink` | `#172e29` | chữ chính | trên `--bg` 13,26 |
> | `--sub` | `#52655d` | chữ phụ | trên `--bg` 5,73 · trên trắng 6,22 |
> | `--deep` | `#163d34` | nút chính, header tối, thẻ "xe của bạn" | chữ trắng 11,99 · chữ `--amber` 8,17 |
> | `--green` / `--mint` | `#24654e` / `#dff1e3` | đang sạc | `#163d34` trên `--mint` 10,18 · mark `#24654e` trên `--mint` 5,85 |
> | `--goldink` / `--amberwash` | `#805114` / `#fff2d8` | cảnh báo, giảm công suất | 6,10 · mark `#a86f12` 3,83 |
> | `--red` / `--redwash` | `#963d32` / `#fbece7` | lỗi, huỷ | 6,06 |
> | `--teal` / `--tealwash` | `#23585b` / `#e6efef` | đã đầy, chưa rút; thông tin | 6,86 · mark `#326467` 5,69 |
> | trống (`idle`) | `#3f5249` / `#f4f6f1`, mark `#6f8279` | ô trống | 7,68 · mark 3,75 |
> | vòng focus | `#bc7c19`, 3 px | mọi phần tử tương tác | trên trắng 3,48 · trên `--bg` 3,21 (đạt 3:1 của 2.4.7 / 1.4.11) |
>
> **Chưa đạt, phải sửa khi merge `buivanlam`**: viền nút và ô nhập `#cdd8ce` trên trắng chỉ 1,47:1, viền thẻ `#d9e2d9`
> 1,33:1. Viền thẻ chỉ để trang trí nên không sao. Viền ô nhập, checkbox, radio thì phải đạt 3:1 (1.4.11): dùng
> 🆕 `--line-input: #6f8279` (≈ 4:1 trên trắng). Trạng thái đầu nối vẫn theo quy tắc chữ + icon + màu của mục 1.2.

Khai báo trong khối `@theme` của `frontend/src/app/globals.css`. Tailwind 4 tự sinh utility `bg-*`, `text-*`, `border-*`
từ các biến `--color-*`. Dùng hex cụ thể, không dùng tên trong palette mặc định: Tailwind 4 định nghĩa palette bằng OKLCH
nên giá trị khác bản 3. Tỉ lệ tương phản tính theo công thức WCAG 2.1; mục 7 (E7) tính lại mọi cặp ghi dưới đây.

**Màu chung**

| Token | Hex | Dùng cho | Kiểm tương phản | Ngưỡng |
|---|---|---|---|---|
| `--color-bg` | `#ffffff` | nền trang | — | — |
| `--color-surface` | `#f5f5f5` | nền thẻ, ô đầu nối trống | `#171717` trên `#f5f5f5` → 16,44 · `#525252` trên `#f5f5f5` → 7,17 | 4,5 |
| `--color-fg` | `#171717` | chữ chính | `#171717` trên `#ffffff` → 17,93 | 4,5 |
| `--color-muted` | `#525252` | chữ phụ | `#525252` trên `#ffffff` → 7,81 | 4,5 |
| `--color-subtle` | `#737373` | mã, giờ, chú thích | `#737373` trên `#ffffff` → 4,74 | 4,5 |
| `--color-border-input` | `#767676` | viền ô nhập, checkbox, radio | `#767676` trên `#ffffff` → 4,54 | 3 (1.4.11) |
| `--color-divider` | `#e5e5e5` | đường kẻ trang trí giữa các khối | không mang thông tin | — |
| `--color-primary` | `#1d4ed8` | nút chính, link, vòng focus | `#1d4ed8` trên `#ffffff` → 6,70 · `#ffffff` trên `#1d4ed8` → 6,70 · `#1d4ed8` trên `#f5f5f5` → 6,15 | 3 / 4,5 |
| `--color-danger` | `#b91c1c` | nút "Huỷ lịch", "Xoá tài khoản" | `#ffffff` trên `#b91c1c` → 6,47 | 4,5 |
| `--color-danger-fg` / `-bg` | `#991b1b` / `#fef2f2` | `ErrorPanel` | `#991b1b` trên `#fef2f2` → 7,60 | 4,5 |
| `--color-warning-fg` / `-bg` | `#92400e` / `#fffbeb` | cảnh báo, banner "đang khởi động" | `#92400e` trên `#fffbeb` → 6,84 | 4,5 |
| `--color-notimpl-fg` / `-bg` | `#78350f` / `#fffbeb` | `NotImplementedPanel` | `#78350f` trên `#fffbeb` → 8,75 | 4,5 |
| `--color-success-fg` / `-bg` | `#166534` / `#f0fdf4` | toast thành công | `#166534` trên `#f0fdf4` → 6,81 | 4,5 |
| `--color-info-fg` / `-bg` | `#1e40af` / `#eff6ff` | thông tin, `SimulationNotice` | `#1e40af` trên `#eff6ff` → 8,01 | 4,5 |
| `--color-chart-load` | `#1d4ed8` | đường tải tổng (S5) | `#1d4ed8` trên `#ffffff` → 6,70 | 3 |
| `--color-chart-limit` | `#b91c1c` | vạch giới hạn, nét đứt (S5) | `#b91c1c` trên `#ffffff` → 6,47 | 3 |
| `--color-gantt-full` | `#15803d` | thanh Gantt khi công suất đầy (S6) | `#15803d` trên `#ffffff` → 5,02 | 3 |
| `--color-gantt-reduced` | `#a16207` | sọc chéo của thanh khi công suất giảm (S6) | `#a16207` trên `#ffffff` → 4,92 | 3 |

Viền ô nhập trong code hiện tại là `border-neutral-400`, khoảng `#a1a1a1`: `#a1a1a1` trên `#ffffff` → 2,58, **không đạt**
1.4.11. Khi làm T2.7, đổi sang `--color-border-input`.

**Trạng thái đầu nối**: ô có nền `bg`, chữ màu `fg`, viền và icon màu `mark`.

| `ConnectorStatus` | Nhãn | Icon (SVG, `aria-hidden`) | `fg` / `bg` / `mark` | Kiểm tương phản |
|---|---|---|---|---|
| `idle` | Trống | hình tròn rỗng | `#404040` / `#f5f5f5` / `#737373` | `#404040` trên `#f5f5f5` → 9,51 · `#737373` trên `#f5f5f5` → 4,35 |
| `charging` | Đang sạc | hình tròn đặc | `#166534` / `#dcfce7` / `#15803d` | `#166534` trên `#dcfce7` → 6,49 · `#15803d` trên `#dcfce7` → 4,57 |
| `throttled` | Giảm công suất | tam giác chúc xuống | `#854d0e` / `#fef9c3` / `#a16207` | `#854d0e` trên `#fef9c3` → 6,38 · `#a16207` trên `#fef9c3` → 4,58 |
| `finished` | Đã đầy, chưa rút | dấu ✓ | `#1e40af` / `#dbeafe` / `#2563eb` | `#1e40af` trên `#dbeafe` → 7,15 · `#2563eb` trên `#dbeafe` → 4,24 |
| `fault` | Lỗi | dấu ✕ | `#991b1b` / `#fee2e2` / `#dc2626` | `#991b1b` trên `#fee2e2` → 6,80 · `#dc2626` trên `#fee2e2` → 3,95 |

Token: `--color-st-{idle|charging|throttled|finished|fault}-{fg|bg|mark}`. Chữ đạt 4,5:1; viền và icon đạt 3:1 (1.4.11).

**Chữ**

- Font: system stack đang có trong `globals.css`. Đủ dấu tiếng Việt, không tải font từ bên ngoài.
- Số dùng `font-variant-numeric: tabular-nums` (KPI, bảng, đồng hồ đếm ngược). Đậm 600 cho tiêu đề và nhãn quan trọng.
  Không dùng chữ nghiêng làm tín hiệu duy nhất.

| Utility | Cỡ / line-height (px) | Dùng cho |
|---|---|---|
| `text-xs` | 12 / 16 | chỉ cho mã (`booking_id`, `request_id`); nội dung chính không dùng cỡ này |
| `text-sm` | 14 / 20 | chữ phụ, bảng của vận hành |
| `text-base` | 16 / 24 | nội dung chính. **Ô nhập luôn ≥ 16 px** để iOS không tự phóng to |
| `text-lg` | 18 / 28 | tiêu đề khối (`<h2>`) |
| `text-xl` | 20 / 28 | `<h1>` trên điện thoại |
| `text-2xl` | 24 / 32 | `<h1>` trên máy tính, số KPI |

**Spacing, kích thước, bo góc**

- Dùng thang 4 px của Tailwind: `1` = 4, `2` = 8, `3` = 12, `4` = 16, `6` = 24, `8` = 32.
- Lề trang 16 px (`p-4`). Giữa các khối 12 px (`gap-3`, như code hiện có). Giữa các nhóm lớn 24 px.
- Vùng chạm ≥ 44 × 44 px (`min-h-11`, code đang dùng). Mức này cao hơn AA, theo quyết định ở 20 §9.
- Bo góc `rounded` (4 px) cho nút, ô nhập, thẻ; `rounded-full` cho badge. Viền 1 px.
- Vòng focus 3 px màu `--color-primary`, cách 2 px (đang có trong `globals.css`).

**Breakpoint và khung**

| Vai trò | Thiết kế cho | Bố cục |
|---|---|---|
| Cư dân | Từ 360 px. Ở 320 px vẫn không phải cuộn ngang (WCAG 1.4.10) | Một cột, `max-w-md` (448 px), căn giữa |
| Vận hành | Từ 1024 px (`lg`) | Lưới 2 cột ở `lg`. Hẹp hơn (tablet, zoom 400 %) thì xếp 1 cột. Gantt, biểu đồ và bảng rộng cuộn ngang trong vùng riêng có `tabindex="0"` và `aria-label`, theo ngoại lệ nội dung 2 chiều của 1.4.10 |

**Chuyển động**: không có animation trang trí. Chuyển trạng thái tối đa 150 ms; `prefers-reduced-motion: reduce` tắt hết
(đang có trong `globals.css`). Không có gì nhấp nháy quá 3 lần mỗi giây (2.3.1).

### 1.2 Nhãn cho enum: chữ, icon, màu

Mọi trạng thái hiển thị bằng **chữ**. Icon đặt `aria-hidden="true"`; màu chỉ là tín hiệu phụ (1.4.1). Bảng ánh xạ nằm ở một
chỗ là `src/lib/labels.ts` (mới); component `StatusBadge` đọc từ đó. Icon là SVG 16 px tự vẽ, không thêm thư viện icon.
Bảng `ConnectorStatus` ở mục 1.1.

| Enum | Giá trị → nhãn (icon · màu) |
|---|---|
| `BookingStatus` | `confirmed` → "Đã xác nhận" (✓ · info) · `queued` → "Đang chờ đầu nối" (đồng hồ · warning) · `charging` → "Đang sạc" (tròn đặc · st-charging) · `completed` → "Đã xong" (✓ · success) · `cancelled` → "Đã huỷ" (✕ · muted) |
| `ApprovalStatus` | `pending` → "Chờ trả lời" (đồng hồ · warning) · `approved` → "Đã đồng ý" (S4) / "Đã duyệt" (S7) (✓ · success) · `rejected` → "Đã từ chối" (✕ · muted) · `expired` → "Đã hết hạn — không áp dụng" (đồng hồ gạch chéo · muted) |
| `ApprovalKind` | `resident_consent` → "Cần cư dân đồng ý" · `operator_review` → "Cần vận hành duyệt" |
| `GuardRule` | `total_power_limit` → "Vượt giới hạn tổng công suất" · `connector_power_limit` → "Vượt công suất đầu nối hoặc của xe" · `anti_flapping` → "Bật/tắt liên tục" · `stale_state` → "Dữ liệu trạm đã cũ" · `permission` → "Không có quyền thao tác" · `schedule_version` → "Dựa trên lịch đã cũ" · `conflicting_commands` → "Lệnh mâu thuẫn trên cùng đầu nối" |
| Kết luận Guard | `GuardVerdict.passed` đúng → "✓ Guard: hợp lệ" (success) · sai → "✕ Guard: chặn — {nhãn luật}" (danger) |
| `CommandSource` | `optimizer` → "Bộ tối ưu" · `load_balancer` → "Cân bằng tải" · `emergency` → "Bảo vệ khẩn cấp" · `operator` → "Vận hành" · `agent` → "Trợ lý (Agent)" |
| `CommandType` | `set_power` → "Đặt công suất {connector_id} → {power_kw} kW" · `start` → "Bắt đầu sạc {connector_id}" · `stop` → "Dừng sạc {connector_id}" · `assign_connector` → "Xếp xe #{booking_id rút gọn} vào {connector_id}" |
| `NotificationKind` | `approval_request` → "Cần bạn trả lời" (⚠ · warning) · `schedule_changed` → "Lịch thay đổi" (mũi tên vòng · info) · `emergency_curtailment` → "Đã giảm công suất khẩn cấp" (⚠ · danger) · `info` → "Thông tin" (i · info) |
| `StrategyName` | `A_fcfs` → "A — FCFS (đến trước phục vụ trước)" · `A_edf` → "A — Ưu tiên hạn rời gần nhất (EDF)" · `B` → "B — Bộ tối ưu, không ML" · `C` → "C — Bộ tối ưu + dự báo (phương án chính)" · `D` → "D — Oracle (cận trên lý tưởng)" |
| `IncidentType` | `connector_fault` → "Trụ hỏng" · `connector_restored` → "Trụ hoạt động lại" · `power_limit_change` → "Đổi giới hạn nguồn" |
| `EventType` | `tick` → "Bước định kỳ" (ticker ẩn loại này) · `vehicle_arrived` → "Xe đến" · `vehicle_departed` → "Xe rút đầu nối" · `booking_created` → "Có lịch mới" · `booking_changed` → "Lịch đổi yêu cầu" · `booking_cancelled` → "Lịch bị huỷ" · `connector_fault` → "Đầu nối lỗi" · `connector_restored` → "Đầu nối hoạt động lại" · `power_limit_changed` → "Giới hạn nguồn đổi thành {new_power_limit_kw} kW" · `replan_requested` → "Yêu cầu lập lịch lại" |
| `AlternativeKind` | `other_time` → "Giờ khác" · `lower_target` → "Mức pin thấp hơn" · `join_queue` → "Vào hàng đợi" |
| `ChargeMode` | `reservation` → "Đặt trước" · `walk_in` → "Đến trực tiếp" |
| `SessionSource` | `synthetic` → "Dữ liệu giả lập" · `norway_2024` → "Khu dân cư Na Uy 2024" · `norway_2021` → "Chung cư Na Uy 2021" · `acn` → "ACN-Data (Caltech)" |
| `Role` | `resident` → "Cư dân" · `operator` → "Vận hành trạm" |

`ErrorCode` không có nhãn ở đây; thông điệp theo mã nằm ở mục 1.6.

### 1.3 Định dạng số và giờ

Đặt trong `src/lib/format.ts` (đã có trong cây thư mục của 20 §3, chưa tạo).

| Loại | Quy tắc | Ví dụ |
|---|---|---|
| Công suất | 1 chữ số thập phân, dấu phẩy | `4,2 kW` |
| Điện năng | 1 chữ số thập phân | `32,0 kWh` |
| Tiền | `Intl.NumberFormat("vi-VN", {style: "currency", currency: "VND", maximumFractionDigits: 0})` | `38.400 ₫` |
| Phần trăm | số nguyên + `%` | `84%` |
| Giờ | `Intl.DateTimeFormat("vi-VN", {timeZone, hour: "2-digit", minute: "2-digit"})`, với `timeZone` = `StationConfig.timezone` | `23:00` |
| Ngày + giờ | thêm `day` và `month` (2 chữ số). Mốc không thuộc hôm nay thì luôn ghi ngày | `18/11 07:00` |
| Khoảng thời gian | từ 60 phút trở lên ghi "1 giờ 30 phút"; dưới 60 phút ghi "40 phút" | `còn dư 1 giờ 30 phút` |
| Thời điểm tương đối | chỉ dùng kèm giờ tuyệt đối, trong `<time datetime="…">` | `2 phút trước (19:05)` |
| Mã | 6 ký tự đầu của `booking_id`, có `title` chứa mã đầy đủ | `#9f1c2a` |

- **Giờ người dùng nhập** (`datetime-local`, `date`) hiểu là giờ của **trạm**, không phải giờ trình duyệt. Trước khi gửi,
  đổi sang ISO 8601 có offset (vd `2026-11-17T23:00:00+07:00`): `AwareDatetime` của backend từ chối giá trị không có múi
  giờ. Asia/Ho_Chi_Minh không đổi giờ theo mùa, nhưng vẫn tính offset bằng `Intl` theo `timezone`, vì tham số này nằm
  trong config (ADR-003).
- Số và đơn vị nằm trong cùng một phần tử để trình đọc màn hình đọc liền ("4,2 kW").
- `GET /station/config` gọi một lần (`staleTime: Infinity`) và truyền xuống `format.ts` qua context.

### 1.4 Khung trang theo vai trò

**Cư dân** (`resident/layout.tsx` → `RoleShell`)

```text
+------------------------------------+
| [Bỏ qua tới nội dung chính]        |  skip link, chỉ hiện khi focus
| BackendStatusBanner (khi cần)      |
+------------------------------------+
| ⚡ ChargePilot        [🔔 1]  [☰]   |
| Trực tiếp                          |  LiveIndicator (chữ)
+------------------------------------+
| <main id="main">                   |
|   … nội dung màn …                 |
+------------------------------------+
| Toast (LiveAnnouncer, cố định đáy) |
+------------------------------------+
```

| Thành phần | Hành vi | Dữ liệu |
|---|---|---|
| Chuông 🔔 | Là `<a href="/resident/notifications">` với `aria-label="Thông báo, {n} chưa đọc"`. Số `n` ẩn khi bằng 0 | `n` = số `Notification.read` sai trong `GET /resident/notifications` |
| Menu ☰ | Nút disclosure có `aria-expanded`, `aria-controls`. Mở ra: Trang chủ · Đặt lịch bằng form · Thông báo · Hồ sơ · Đăng xuất. `Esc` đóng menu và đưa focus về nút | — |
| Đăng xuất | `clearSession()` rồi về `/login`. Không có endpoint logout: JWT không giữ trạng thái và hết hạn sau 8 giờ (ADR-006) | — |
| LiveIndicator | Component đã có; hiện chữ theo `SocketStatus` | `useStream("resident")` |

`RoleShell` hiện đặt menu thành hàng link ngang. Khi làm T2.7, đổi sang chuông + menu như 20 §3 đã định.

**Vận hành** (`operator/layout.tsx` → `RoleShell`)

```text
+--------------------------------------------------------------------------------+
| [Bỏ qua tới nội dung chính]                                                     |
| ⚡ ChargePilot · Vận hành — {display_name}            Trực tiếp      [Đăng xuất] |
| [Dashboard] [Sơ đồ bãi] [Hàng đợi & lịch] [Duyệt lệnh (3)] [Mô phỏng]           |
+--------------------------------------------------------------------------------+
| <main id="main"> … </main>                                                      |
+--------------------------------------------------------------------------------+
```

- Thanh tab là **liên kết điều hướng** (`<nav aria-label="Điều hướng chính">`, trang hiện tại có `aria-current="page"`),
  không phải ARIA tabs, vì mỗi tab là một route.
- Số "(3)" là số `Approval` có `Approval.kind` = `operator_review` trong `GET /operator/approvals` (mặc định
  `status=pending`). Đề nghị `resident_consent` không tính vì vận hành không quyết được. `aria-label` của tab:
  "Duyệt lệnh, 3 lệnh chờ duyệt".

**Chung cho mọi route**

- Mỗi route có `<title>` riêng dạng "{Tên màn} · ChargePilot" (2.4.2) và đúng một `<h1>` trùng tên đó; các khối dùng
  `<h2>`. Trang hiện là `"use client"` nên không export `metadata` được. Cách làm: `page.tsx` để là server component,
  export `metadata`, rồi render component client, giống `notifications/[approvalId]/page.tsx` đang làm. Đọc
  `frontend/AGENTS.md` và `node_modules/next/dist/docs/` trước khi sửa, vì Next 16 có thay đổi.
- Mọi trang có `<main id="main">`; skip link là phần tử đầu tiên nhận được focus.
- `BackendStatusBanner` nằm ở layout gốc (đã có).

| Route | `<title>` / `<h1>` |
|---|---|
| `/login` | Đăng nhập |
| `/resident` | Trang chủ |
| `/resident/plan` | Lịch sạc đề xuất (chế độ booking: Lịch sạc của tôi) |
| `/resident/book` | Đặt lịch bằng form |
| `/resident/notifications` | Thông báo |
| `/resident/notifications/[approvalId]` | Đề nghị điều chỉnh sạc |
| `/resident/profile` | Hồ sơ của tôi |
| `/resident/map` | Sơ đồ bãi |
| `/operator` | Dashboard trạm |
| `/operator/map` | Sơ đồ bãi |
| `/operator/schedule` | Hàng đợi & lịch |
| `/operator/approvals` | Duyệt lệnh |
| `/operator/simulation` | Mô phỏng kịch bản |

### 1.5 Component dùng chung

| Component | File | Trạng thái | Dùng ở | Ghi chú / lý do |
|---|---|---|---|---|
| `AuthGate`, `LoginForm` | `components/auth/` | có sẵn | layout, S1 | `LoginForm` sửa thông điệp cho 401 (mục 2.1) |
| `RoleShell` | `components/system/` | có sẵn | layout | cư dân: đổi sang chuông + menu (20 §3) |
| `BackendStatusBanner`, `LiveIndicator` | `components/system/` | có sẵn | layout | giữ nguyên |
| `NotImplementedPanel` | `components/system/` | có sẵn | mọi khối | thêm prop `compact` cho khối nhỏ đặt dưới một nút |
| `ErrorPanel` | `components/system/` | có sẵn | mọi khối | thêm prop `messages` để từng màn ghi đè thông điệp theo `code` |
| `QueryBoundary` | `components/system/QueryBoundary.tsx` | theo 20 §3, chưa tạo | mọi khối đọc dữ liệu | = `EndpointBlock` + `children(data)` + `isEmpty`/`empty`; bỏ phần hiện JSON (R6) |
| `StatusBadge` | `components/system/StatusBadge.tsx` | mới | S2–S8 | một chỗ ánh xạ enum → chữ + icon + màu (mục 1.2, WCAG 1.4.1) |
| `Countdown` | `components/system/Countdown.tsx` | mới | S4, S7 | đếm ngược tới `Approval.expires_at`, `role="timer"`, báo trước 1 phút |
| `ConfirmDialog` | `components/system/ConfirmDialog.tsx` | mới | S3, hồ sơ, S8 | `<dialog>` mở bằng `showModal()`; focus vào nút an toàn; `Esc` là huỷ |
| `LiveAnnouncer` + `Toast` | `components/system/LiveAnnouncer.tsx` | mới | toàn app | một vùng `aria-live="polite"` dùng chung (4.1.3), thay cho nhiều vùng rải rác |
| `DataTableFallback` | `components/system/DataTableFallback.tsx` | mới | biểu đồ tải, Gantt, bảng KPI | bảng số liệu tương đương trong `<details>` (20 §9) |
| `SimulationNotice` | `components/system/SimulationNotice.tsx` | mới | S1, S5, S8, chip giờ rẻ | nhắc "đây là mô phỏng" và cờ `verified` sai của `Tariff`, `VehicleSpec` |
| `useApiMutation` | `lib/api/mutations.ts` | mới | mọi nút ghi | bọc `useMutation` + `unwrap`; trả `ApiError` đã phân loại cho UI |
| `VehicleCard`, `ChatPanel`, `CheapHourChips`, `ProposalCard`, `BookingForm`, `ApprovalPrompt`, `QueueBadge` | `components/resident/` | theo 20 §3 | mục 2 | |
| `NotificationList`, `ChangeBookingDialog`, `ProfileForm`, `ConsentFields` | `components/resident/` | mới | thông báo, S3, hồ sơ, form đặt lịch | `ConsentFields` có dạng sửa (hồ sơ) và dạng chỉ đọc (form, S3) — FR13 |
| `KpiBar`, `LoadChart`, `ConnectorGrid`, `ConnectorDialog`, `EventTicker`, `GanttChart`, `QueueList`, `ApprovalTable`, `BlockedTable`, `ScenarioForm`, `KpiCompareTable` | `components/operator/` | theo 20 §3 | mục 3 | |
| `ManualAssignForm`, `DecisionLogTable`, `IncidentForm` | `components/operator/` | mới | S6, S7, S8 | |
| `format.ts`, `labels.ts` | `lib/` | `format` theo 20 §3; `labels` mới | toàn app | mục 1.2, 1.3 |

Dependency: chỉ có `recharts` (đã duyệt ở D6, cài khi làm T3.6). Không thêm thư viện icon, date picker, Gantt, toast,
MSW hay Storybook.

### 1.6 Trạng thái và mã lỗi

**Trạng thái của một khối đọc dữ liệu** (`QueryBoundary`)

| Trạng thái | Điều kiện | Hiển thị |
|---|---|---|
| Đang tải | `isPending` | Skeleton cùng kích thước khối, kèm `role="status"` "Đang tải…". Khi đang thử lại: "(đang thử lại lần n)", như `EndpointBlock` đang làm |
| Rỗng | Dữ liệu hợp lệ nhưng rỗng (mảng rỗng, `null`) | Câu riêng của khối + hành động gợi ý, ghi trong bảng trạng thái của từng màn |
| 501 | `ApiError.isNotImplemented` | `NotImplementedPanel` (task ID + endpoint). Phần còn lại của trang vẫn chạy |
| Lỗi | Lỗi khác | `ErrorPanel`: thông điệp theo `code`, `request_id`, nút "Thử lại" |
| Dữ liệu cũ | Đang có dữ liệu trong cache nhưng lần tải lại lỗi | Giữ dữ liệu, thêm dòng "Không cập nhật được lúc hh:mm" |
| Mất realtime | `SocketStatus` khác `open` | `LiveIndicator` đổi chữ. Khối realtime hỏi lại REST mỗi 15 giây (`usePollFallback`) và ghi "Cập nhật lúc hh:mm:ss" |
| Disabled | Điều kiện của từng nút | `disabled` kèm lý do bằng chữ ngay cạnh, nối bằng `aria-describedby`; không chỉ làm mờ nút |

**Thao tác ghi** (`useApiMutation`)

- Trong lúc chờ, nút đổi chữ thành "Đang …" và bị khoá; không bấm lặp được.
- Thành công: toast qua `LiveAnnouncer`; ghi response vào cache bằng `setQueryData`, gọi `invalidateQueries` cho dữ liệu
  liên quan.
- 501: hiện `NotImplementedPanel compact` ngay dưới nút; phần khác vẫn dùng được.
- Không tự thử lại (`Providers` đặt `mutations.retry = false`). Riêng `POST /resident/bookings` bấm lại an toàn nhờ
  `Idempotency-Key`.

**Mã lỗi ADR-008 → UI**

| HTTP · `code` | Xử lý chung | Ghi đè ở màn |
|---|---|---|
| 0 · `network_error` (mã của web) | `BackendStatusBanner` + `ErrorPanel` "Không kết nối được máy chủ…"; GET tự thử lại theo backoff (20 §7.1) | — |
| 401 · `unauthenticated` | `unwrap` xoá phiên. Nếu request có gửi token thì đặt cờ `chargepilot.logoutReason = "expired"` trong `sessionStorage`. `AuthGate` chuyển về `/login?next=…`; S1 đọc cờ và hiện "Phiên đăng nhập đã hết hạn" một lần | S1: "Email hoặc mật khẩu không đúng" |
| 403 · `forbidden` | `ErrorPanel` "Bạn không có quyền…" + link về trang của vai trò | S7: "Chỉ cư dân được trả lời đề nghị này" |
| 404 · `not_found` | `ErrorPanel` với `detail` | S4: "Không tìm thấy đề nghị này"; form: gắn vào ô mẫu xe |
| 409 · `booking_conflict` | "Bạn đang có một lịch sạc còn hiệu lực" | S3, form: thêm link "Xem lịch của tôi" |
| 409 · `proposal_expired` | "Trạng thái trạm đã thay đổi" | S3: nút "Xem phương án mới" |
| 409 · `idempotency_mismatch` | "Yêu cầu đã đổi so với lần gửi trước" | S3 form: sinh khoá mới rồi quote lại |
| 409 · `approval_already_decided` | "Yêu cầu này đã được xử lý" | S4, S7: tải lại để hiện trạng thái thật |
| 409 · `no_pending_confirmation` | "Phiên chat không còn chờ xác nhận" | S3 chat: chuyển sang form, điền sẵn từ `pending`. Hôm nay backend chưa trả mã này mà trả 200 `answer` (G1) |
| 422 · `validation_error` (mã của web; `detail` là mảng) | Gắn lỗi vào ô theo `FieldError.path`. Lỗi không có `path` (validator cấp model) hiện ở đầu form | — |
| 500 · `internal_error` | `ErrorPanel` + `request_id` | — |
| 501 · `not_implemented` | `NotImplementedPanel` | — |
| 503 · `llm_unavailable` | "Trợ lý tạm thời không dùng được" + nút "Đặt lịch bằng form" | S2, S3 chat |
| 503 · `database_unavailable` | `ErrorPanel` "Cơ sở dữ liệu tạm thời…". GET tự thử lại; thao tác ghi không tự thử lại | — |
| khác · `http_error` | `ErrorPanel` với `detail` | — |

### 1.7 Realtime

Mỗi vai trò mở **một** kết nối trong `RoleShell` (`useStream`). Hiện `useStream.ts` làm mới mọi truy vấn của vai trò khi có
bất kỳ bản tin nào. Khi làm T3.6, đổi sang xử lý theo từng `type` như bảng dưới:

| `type` | Payload | Kênh | Query key | Cách cập nhật | Màn |
|---|---|---|---|---|---|
| `schedule_changed` | `ResidentSessionView` | resident | `["resident","session"]` | `setQueryData`; `invalidate` `["resident","queue"]`, `["resident","booking"]`, `["resident","explanation"]` | S2, S3 booking |
| `notification` | `Notification` | resident | `["resident","notifications"]` | thêm vào đầu, bỏ trùng theo `notification_id` | chuông, thông báo, S2 |
| `approval_request` | `Approval` | resident, chỉ người có `Approval.requested_from` là mình | `["resident","approval", approval_id]` | `setQueryData`; `invalidate` thông báo | S2 (banner), S4 |
| `station_snapshot` | `StationOverview` | operator | `["operator","station"]` | `setQueryData`; `invalidate` `["operator","load",24]` tối đa 1 lần mỗi 60 giây | S5; S6 dùng để chọn đầu nối |
| `event` | `StationEvent` | operator | `["operator","events"]` | thêm vào đầu, giữ 20 mục | S5 |
| `schedule_changed` | `SchedulePlan` | operator | `["operator","schedule"]` | `setQueryData` nếu đang xem lịch hiện hành; `invalidate` `["operator","bookings"]` | S6 |
| `approval_request` | `Approval` | operator | `["operator","approvals"]` | thêm hoặc thay theo `approval_id`; bỏ khỏi danh sách khi `status` khác `pending` (cần G9) | S7, số trên tab |
| `command_blocked` | `DecisionLogEntry` | operator | `["operator","blocked"]` | thêm vào đầu; toast "Guard đã chặn 1 lệnh" | S5 (ticker), S7 |
| `pong` | `{}` | cả hai | — | `ReconnectingSocket` tự xử lý | — |

- Server lọc bản tin theo vai trò; client vẫn bỏ qua `type` không biết.
- Nối lại thành công thì gọi `invalidateQueries([role])` (đang có), vì server không phát lại bản tin đã lỡ.
- Mã đóng `1011` → trạng thái `not_implemented`: hỏi lại REST mỗi 15 giây (`POLL_FALLBACK_MS`, đang có). `4401` → đăng
  xuất. `4403` → dừng, `LiveIndicator` hiện "Không có quyền nhận dữ liệu trực tiếp".
- Chỉ đọc bằng giọng đọc những thay đổi người dùng cần biết: thông báo mới, đề nghị đang chờ, lệnh bị chặn, lịch của
  mình đổi. **Không** đọc từng snapshot của S5.

### 1.8 WCAG 2.1 AA

| Tiêu chí | Quy tắc trong ChargePilot | Áp ở |
|---|---|---|
| 1.1.1 Non-text content | Icon có `aria-hidden` và luôn có chữ đi kèm. Biểu đồ có `role="img"` + `aria-label` tóm tắt (vd "Tải 24 giờ, cao nhất {x} kW lúc 19:15, giới hạn {y} kW" — số lấy từ API) và bảng số liệu trong `<details>` | mục 1.2, S5, S6, S8 |
| 1.3.1 Info and relationships | `<table>` có `<caption>` và `<th scope>`; nhóm ô nhập bằng `<fieldset>`/`<legend>`; danh sách dùng `<ul>` thật | mọi bảng, form |
| 1.3.2 Meaningful sequence | Thứ tự DOM trùng thứ tự đọc của wireframe | mọi màn |
| 1.3.4 Orientation | Không khoá xoay màn hình | cư dân |
| 1.3.5 Identify input purpose | `autocomplete="username"`, `"current-password"`, `"name"` | S1, hồ sơ |
| 1.4.1 Use of color | Trạng thái đầu nối, kết luận Guard, đạt/chưa đạt KPI, tin chưa đọc: luôn có chữ | mục 1.2 |
| 1.4.3 Contrast (minimum) | Chữ ≥ 4,5:1, theo token mục 1.1 (đã kiểm) | toàn app |
| 1.4.4 Resize text | Phóng chữ 200 % không mất nội dung; cỡ chữ dùng `rem` | toàn app |
| 1.4.10 Reflow | Màn cư dân không cuộn ngang ở 320 px. Màn vận hành xếp 1 cột khi hẹp; Gantt, biểu đồ, bảng cuộn ngang trong vùng riêng | mục 1.1 |
| 1.4.11 Non-text contrast | Viền ô nhập, checkbox, vòng focus, đường biểu đồ, viền và icon trạng thái ≥ 3:1. Viền ô nhập hiện tại **không đạt** (mục 1.1) | mục 1.1, S1 |
| 1.4.12 Text spacing | Không cố định chiều cao khối chữ; tăng giãn dòng không làm chữ bị cắt | toàn app |
| 1.4.13 Content on hover or focus | Tooltip biểu đồ hiện cả khi focus bằng bàn phím, `Esc` đóng, rê chuột vào tooltip không làm nó biến mất | S5, S6 |
| 2.1.1 Keyboard | Mọi thao tác làm được bằng bàn phím: ô đầu nối và chip là `<button>`; vùng cuộn có `tabindex="0"` | toàn app |
| 2.1.2 No keyboard trap | `<dialog>` mở bằng `showModal()`, `Esc` đóng, đóng xong focus về nút đã mở | mọi dialog |
| 2.2.1 Timing adjustable | Đồng hồ ở S4, S7 là hạn của một sự kiện thời gian thực (trạng thái trạm), nên thuộc ngoại lệ real-time. Vẫn ghi rõ "không trả lời = không áp dụng" và báo trước khi còn 1 phút. Phiên đăng nhập kéo dài 8 giờ (ADR-006) | S4, S7 |
| 2.2.2 Pause, stop, hide | S5 có nút "Tạm dừng cập nhật trực tiếp"; ticker không chạy chữ | S5 |
| 2.3.1 Three flashes | Không có gì nhấp nháy | toàn app |
| 2.4.1 Bypass blocks | Skip link "Bỏ qua tới nội dung chính" | layout |
| 2.4.2 Page titled | `<title>` theo bảng mục 1.4 | mọi route |
| 2.4.3 Focus order | Mở dialog: focus vào phần tử đầu tiên hoặc nút an toàn; đóng: focus về nút đã mở. Sang route mới: focus vào `<h1>` | toàn app |
| 2.4.4 Link purpose | Không có link "xem thêm" trơ trọi; thêm ngữ cảnh bằng chữ ẩn, vd "Xem chi tiết lịch sạc A07" | S2, S5 |
| 2.4.6 Headings and labels | Một `<h1>` mỗi trang; `<h2>` cho từng khối | toàn app |
| 2.4.7 Focus visible | Vòng focus 3 px `--color-primary` (đang có) | toàn app |
| 2.5.3 Label in name | Tên truy cập chứa chữ đang hiển thị ("Đồng ý", không phải `aria-label="Approve"`) | toàn app |
| 3.1.1 Language of page | `<html lang="vi">` (đang có) | layout gốc |
| 3.2.1 / 3.2.2 On focus / On input | Focus hay chọn giá trị không làm chuyển trang. Đổi ngày ở S6 chỉ tải lại nội dung tại chỗ; S2 không tự sang S3 | S2, S6 |
| 3.2.3 Consistent navigation | Header và thứ tự menu giống nhau ở mọi trang của cùng vai trò | layout |
| 3.3.1 Error identification | Lỗi hiện bằng chữ, cạnh ô nhập, có `aria-invalid` + `aria-describedby` | mọi form |
| 3.3.2 Labels or instructions | Mọi ô có `<label>`; đơn vị ghi trong nhãn, vd "Pin hiện tại (%)" | mọi form |
| 3.3.3 Error suggestion | Câu báo lỗi nói cách sửa, vd "Mức pin mong muốn phải lớn hơn mức hiện tại" | mọi form |
| 3.3.4 Error prevention | Đặt lịch có bước xác nhận (S3). Huỷ lịch, xoá tài khoản, bơm sự cố đều qua `ConfirmDialog` | S3, hồ sơ, S8 |
| 4.1.2 Name, role, value | Tab của S7 theo mẫu ARIA tabs; menu ☰ có `aria-expanded`; nút tạm dừng có `aria-pressed` | S7, header, S5 |
| 4.1.3 Status messages | Toast, tin chat mới (`role="log"`), thông báo mới, `LiveIndicator` (`role="status"`) không lấy focus | toàn app |

### 1.9 Làm việc khi backend còn 501

- Màn nào cũng dựng được ngay. Khối gặp 501 hiện `NotImplementedPanel`; khối ✅ chạy với dữ liệu thật (`GET /vehicles`,
  `GET /tariff`, `GET /station/config`, `POST /energy/estimate`).
- Test component dùng fixture có type trong `frontend/src/test/fixtures/*.ts`, viết dạng
  `satisfies components["schemas"]["StationOverview"]`. Schema đổi thì `tsc` báo fixture sai.
- Không thêm MSW, Storybook hay mock server: dependency mới phải được duyệt (`CLAUDE.md`). Muốn xem một component với dữ
  liệu, render nó với fixture trong vitest + Testing Library.

## 2. Màn cư dân

Thiết kế từ 360 px, một cột, dùng được ở 320 px. Cột "Task BE / UI" theo quy ước mục 0.1.

### 2.1 S1 · Đăng nhập — `/login`

- **Mục đích**: đăng nhập rồi chuyển tới trang của vai trò (FR1). **Vai trò**: cả hai. **Viewport**: từ 320 px; khối
  `max-w-sm` căn giữa, trên máy tính giữ nguyên bố cục.

```text
+------------------------------------+
| BackendStatusBanner (khi cần)      |
+------------------------------------+
|           ⚡ ChargePilot            |
| Đăng nhập                          |  <h1>
| Hệ thống mô phỏng: dữ liệu không   |  SimulationNotice
| phải của trạm sạc thật.            |
| [!] Phiên đăng nhập đã hết hạn.    |  chỉ khi có cờ logoutReason
|                                    |
| Email                              |
| [______________________________]   |
| Mật khẩu                           |
| [________________________] [Hiện]  |
|                                    |
| [          Đăng nhập          ]    |
| (ErrorPanel / NotImplementedPanel) |
+------------------------------------+
```

**Thành phần tương tác**

| # | Thành phần | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|
| 1 | (mở trang) | Đánh thức backend trong lúc người dùng gõ | `GET /health`, do `BackendStatusBanner` ở layout gốc gọi | — | banner ẩn | banner "đang khởi động" kèm số lần thử | ✅ / T1.2 |
| 2 | Ô Email | `type="email"`, `autocomplete="username"`, `required` | — | — | — | 422 tại `LoginRequest.email` (3–254 ký tự) → dưới ô | — / T2.7 |
| 3 | Ô Mật khẩu + nút "Hiện/Ẩn" | `autocomplete="current-password"`; nút có `aria-pressed` | — | — | — | 422 tại `LoginRequest.password` | — / T2.7 |
| 4 | Nút "Đăng nhập" (Enter cũng gửi) | Gửi form | `POST /auth/login` · `LoginRequest{email, password}` | `TokenResponse.access_token`, `TokenResponse.role`, `TokenResponse.user_id`, `TokenResponse.display_name` | `setSession`. Đi tới `?next=` nếu đường dẫn đó thuộc trang của `role`, không thì tới `/resident` hoặc `/operator` | 401 `unauthenticated` → "Email hoặc mật khẩu không đúng"; giữ email, xoá mật khẩu, focus vào ô mật khẩu. 501 → `NotImplementedPanel` | T1.7 / T2.7 |

**Trạng thái**

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | Không có dữ liệu cần tải. Khi đang gửi, nút đổi thành "Đang đăng nhập…" |
| Rỗng | — |
| Lỗi | `ErrorPanel` dưới nút, thông điệp 401 đã ghi đè |
| 501 | `NotImplementedPanel` "task T1.7" (tình trạng hôm nay) |
| Mất realtime | Không áp dụng: chưa mở WebSocket |
| Disabled | Nút khoá khi email hoặc mật khẩu trống, hoặc đang gửi |
| Đã có phiên | Mở `/login` khi đang đăng nhập → chuyển về trang của vai trò (giống `app/page.tsx` làm với `/`) |

**Realtime**: không.

**Yêu cầu**: FR1, AC8 (đăng nhập được bằng cả hai vai trò trên live URL), NFR khả dụng (đánh thức backend).

### 2.2 S2 · Trang chủ cư dân — `/resident`

- **Mục đích**: xem xe, lịch, hàng đợi của mình; chat với Trợ lý để đặt lịch (FR15, F1). **Vai trò**: resident.
  **Viewport**: từ 360 px, một cột.

```text
+------------------------------------+
| ⚡ ChargePilot        [🔔 1]  [☰]   |
| Trực tiếp                          |
+------------------------------------+
| [!] Có 1 đề nghị điều chỉnh cần bạn|  ApprovalBanner (khi có)
|     trả lời, hết hạn 19:14   [Xem] |
+------------------------------------+
| Xe: Xe mẫu 60 kWh                  |  VehicleCard
| Pin ước tính: 32%  ▓▓▓░░░░░░░      |
| Lịch: A07 · 23:00 → 05:30          |
| Trạng thái: ✓ Đã xác nhận          |
| Hàng đợi: vị trí 2/5 · chờ ~25 phút|  QueueBadge (khi đang chờ)
| [Xem chi tiết]   [Vì sao?]         |
+------------------------------------+
| Trợ lý sạc    [Cuộc trò chuyện mới]|  ChatPanel
| Trợ lý: Bạn cần sạc thế nào?       |  role="log"
| Bạn: cần 80% trước 7h sáng mai     |
| Trợ lý: Mình đã tìm được phương án:|
|  ┌ A07 · 23:00 → 05:30 · ~32,0 kWh┐|  ProposalSummary
|  │ Đúng hạn 07:00 · Giờ thấp điểm │|
|  └ [Xem chi tiết]                 ┘|
+------------------------------------+
| [Nhập yêu cầu sạc…          ] [Gửi]|
| Giờ rẻ (giá mô phỏng): [22h][23h][0h]|  CheapHourChips
+------------------------------------+
```

**Thành phần tương tác**

| # | Thành phần | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|
| 1 | VehicleCard | Tải khi mở trang | `GET /resident/session` | `ResidentSessionView.booking` (`.request.vehicle_model`, `.request.soc_target`, `.request.deadline`, `.connector_id`, `.planned_start`, `.planned_end`, `.status`), `ResidentSessionView.soc_estimate`, `ResidentSessionView.progress.delivered_grid_kwh` | Hiện thẻ. Pin là `soc_estimate` do code tính; `null` thì ghi "Pin lúc đặt: {soc_now}% → mục tiêu {soc_target}%" | — | T2.2 / T2.7 |
| 2 | Tên xe | Tra tên hiển thị | `GET /vehicles` (cache) | `VehicleSpec.vehicle_model` → `VehicleSpec.display_name` | "Xe mẫu 60 kWh" | không tìm thấy → hiện mã `vehicle_model` | ✅ / T2.7 |
| 3 | Thẻ khi chưa có booking | Hiện xe mặc định | `GET /resident/profile`; lỗi hoặc 501 thì dùng `GET /auth/me` | `ResidentProfile.vehicle_model`, `UserProfile.vehicle_model` | "Xe mặc định: …" + nút "Đặt lịch" (mở chat, hoặc link "Đặt bằng form") | cả hai đều trống → "Chưa chọn xe" + link Hồ sơ | T2.8, T1.7 / T2.7 |
| 4 | QueueBadge | Tải khi mở trang | `GET /resident/queue` | `QueueStatus.position`, `QueueStatus.queue_length`, `QueueStatus.estimated_wait_minutes`, `QueueStatus.estimated_start` | "Vị trí 2/5 · dự kiến bắt đầu 19:40 (~25 phút)". `position` là `null` → ẩn | — | T2.2 / T2.7 |
| 5 | "Xem chi tiết" trên thẻ | Điều hướng | → `/resident/plan?view=booking` | — | S3 chế độ booking | — | — / T2.7 |
| 6 | "Vì sao?" trên thẻ | Disclosure; tải khi mở | `GET /resident/explanation` | mảng chuỗi lý do | Danh sách lý do (US3) | mảng rỗng → "Chưa có giải thích cho lịch này" | T2.5 / T3.3 |
| 7 | Ô nhập chat (`<textarea>`, nhãn "Nhập yêu cầu sạc") | Gõ; Enter gửi, Shift+Enter xuống dòng | — | — | — | quá 5000 ký tự → hiện bộ đếm, khoá nút Gửi (`ChatRequest.message` dài 1–5000) | — / T3.3 |
| 8 | Nút "Gửi" | Gửi tin | `POST /chat` · `ChatRequest{message, session_id}`. `session_id` = `crypto.randomUUID()`, lưu trong `sessionStorage` | `ChatResponse.status`, `ChatResponse.response`, `ChatResponse.proposal`, `ChatResponse.pending`, `ChatResponse.session_id` | Xem bảng nhánh `status` bên dưới | 503 `llm_unavailable`, hoặc quá 30 giây (client huỷ bằng `AbortController`) → tin hệ thống "Trợ lý tạm thời không dùng được" + nút "Đặt lịch bằng form" → `/resident/book`. 422 → dưới ô nhập | ✅ có điều kiện / T3.3 |
| 9 | "Xem chi tiết" trong ProposalSummary | Điều hướng | Ghi `sessionStorage["chargepilot.planDraft"] = {mode: "chat", session_id, proposal, pending}` → `/resident/plan` | — | S3 chế độ chat | — | — / T3.3 |
| 10 | "Cuộc trò chuyện mới" | Bắt đầu lại | — (sinh `session_id` mới, xoá bản ghi chat) | — | Khung chat trống, focus vào ô nhập | — | — / T3.3 |
| 11 | Chip giờ rẻ (`<button>`) | Chèn câu "Mình muốn bắt đầu sạc từ 22:00" vào ô nhập, **không** tự gửi | `GET /tariff` (cache) | `Tariff.periods[]`: khung có `TariffPeriod.name` = `off_peak`; không có thì lấy khung có `TariffPeriod.price_per_kwh` thấp nhất. Chip = các giờ tròn tính từ `TariffPeriod.start`, tối đa 3 | Focus vào ô nhập, con trỏ ở cuối câu. Nhãn ghi giá, vd "1.200 ₫/kWh (giá mô phỏng)" | lỗi tải → ẩn hàng chip | ✅ / T2.7 |
| 12 | ApprovalBanner, nút "Xem" | Điều hướng | → `/resident/notifications/{approval_id}` | `Approval.approval_id`, `Approval.expires_at` (từ WS, hoặc từ thông báo `approval_request` chưa đọc; xem G17) | S4 | — | — / T3.3 |

**Nhánh theo `ChatResponse.status`**

| `status` | Hiển thị trong khung chat |
|---|---|
| `answer` | Bong bóng Trợ lý với `response` (text thuần). Khi đã có G5 và `proposal` đi kèm có `ScheduleProposal.feasible` sai: thêm các `alternatives` dạng nút gợi ý; bấm nút = gửi `Alternative.description` như tin của cư dân |
| `needs_confirmation` | **Không hiện `response`**: đây là chuỗi kỹ thuật (G13). Hiện ProposalSummary dựng từ `proposal`: đầu nối, khung giờ, kWh (`ScheduleProposal.energy.grid_energy_kwh`), dòng đúng hạn, lý do đầu tiên trong `ScheduleProposal.reasons`, nút "Xem chi tiết". Đủ bốn thứ AC1 yêu cầu: đầu nối, khung giờ, kWh, lời giải thích |
| `refused` | Bong bóng trung tính "Trợ lý không thực hiện yêu cầu này" + `response`, vd khi cư dân đòi tăng công suất hay bỏ giới hạn trạm (FR5) |

**Quy tắc của khung chat**

- `response` render bằng text node, **không** dùng `dangerouslySetInnerHTML`, không tự biến chữ thành link. Token nằm trong
  `sessionStorage`, nên XSS đồng nghĩa với lộ token (ADR-006). Giữ xuống dòng bằng `white-space: pre-wrap`.
- `ChatResponse.analysis` (tool trace) chỉ hiện trong `<details>` khi `process.env.NODE_ENV === "development"`.
- Bản ghi chat lưu ở `sessionStorage["chargepilot.chat.{session_id}"]`, tối đa 50 tin, bọc try/catch như `session.ts`.
  Đây chỉ là tiện ích hiển thị; nguồn thật là checkpoint của Agent, và checkpoint mất khi backend khởi động lại (30 §3.6).
- Trong lúc chờ: tin "Trợ lý đang trả lời… (n giây)" có `role="status"`. Ô nhập vẫn gõ được; nút Gửi bị khoá.
- Tin mới thêm vào vùng `role="log"` (ngầm định `aria-live="polite"`), không chuyển focus.

**Trạng thái**

| Trạng thái | VehicleCard | QueueBadge | Chat | Chip giờ rẻ |
|---|---|---|---|---|
| Đang tải | skeleton 3 dòng | ẩn | khung trống + lời chào tĩnh | ẩn |
| Rỗng | `ResidentSessionView.booking` là `null` → xe mặc định + "Chưa có lịch sạc" + nút "Đặt lịch" | `QueueStatus.position` là `null` → ẩn | lời chào tĩnh "Bạn cần sạc thế nào?" | không có khung `off_peak` và không xác định được khung rẻ nhất → ẩn |
| Lỗi | `ErrorPanel` trong thẻ | ẩn, không chặn trang | tin hệ thống trong khung + nút "Gửi lại" (gửi lại tin cuối) | ẩn |
| 501 | `NotImplementedPanel` T2.2 | `NotImplementedPanel compact` T2.2 | 501 T1.7 → tin hệ thống + panel | — (✅) |
| Mất realtime | "Cập nhật lúc hh:mm:ss"; hỏi lại mỗi 15 giây | hỏi lại mỗi 15 giây | không ảnh hưởng (REST) | — |
| Disabled | — | — | Gửi bị khoá khi ô trống, quá 5000 ký tự hoặc đang chờ | — |

**Realtime** (kênh resident)

| `type` | Cập nhật |
|---|---|
| `schedule_changed` (`ResidentSessionView`) | Thay dữ liệu VehicleCard; `invalidate` hàng đợi; toast "Lịch sạc của bạn vừa được cập nhật" kèm nút "Vì sao?" (US3) |
| `notification` (`Notification`) | Tăng số trên chuông. Với `Notification.kind` = `emergency_curtailment`: toast "Đã giảm công suất khẩn cấp — xem thông báo" (AC5) |
| `approval_request` (`Approval`, `status` = `pending`) | Hiện ApprovalBanner với hạn `Approval.expires_at` |

**Yêu cầu**: FR15 (lịch, hàng đợi, trạng thái sạc, thông báo, chat), FR2 (Agent trích xuất và hỏi lại chỗ thiếu, hiện qua
`answer`), FR3 (kWh trong ProposalSummary lấy từ `proposal`), FR5 (`refused`), FR17 (thời gian chờ trong `QueueStatus` có
thể dùng dự báo F6; UI chỉ hiển thị số backend tính), US1, US2, US3, US4, AC1, AC2, NFR khả dụng (nút sang form).

### 2.3 S3 · Xác nhận lịch sạc — `/resident/plan`

- **Mục đích**: xem phương án rồi chốt (bước xác nhận của FR2), hoặc xem, đổi, huỷ lịch đang có (FR8). **Vai trò**:
  resident. **Viewport**: từ 360 px.

**Ba chế độ** (R2)

| Chế độ | Vào từ | Ngữ cảnh | Nguồn số liệu |
|---|---|---|---|
| `chat` | S2, nút "Xem chi tiết" khi `status` = `needs_confirmation` | `sessionStorage["chargepilot.planDraft"]` = `{mode: "chat", session_id, proposal, pending, booking_id_before}`. `booking_id_before` = `Booking.booking_id` của lịch đang hiệu lực lúc rời S2 (lấy từ query thẻ xe), không có thì `null`; dùng ở nút #1 (G1) | `ChatResponse.proposal`; yêu cầu lấy từ `ChatResponse.pending.args.request` (G3) |
| `form` | `/resident/book`, nút "Xem phương án" | `planDraft` = `{mode: "form", request, proposal, idempotency_key}` | `POST /resident/quote` |
| `booking` | S2, nút "Xem chi tiết" trên thẻ xe; link từ lỗi `booking_conflict` | `?view=booking`, đọc bằng `useSearchParams` nên phải bọc `<Suspense>` (Next 16) | `GET /resident/bookings/current` + `GET /resident/explanation` |

Không có `planDraft` và cũng không có `?view=booking` → hiện "Chưa có phương án nào" + hai nút "Chat với Trợ lý" và "Đặt
bằng form". `planDraft` bị xoá khi chốt thành công, hoặc khi bấm "Đổi phương án" ở chế độ chat.

```text
chế độ chat / form                       chế độ booking
+------------------------------------+   +------------------------------------+
| [← Quay lại]  Lịch sạc đề xuất     |   | [← Trang chủ]  Lịch sạc của tôi    |
+------------------------------------+   +------------------------------------+
| Đầu nối:   A07 · tối đa 7 kW       |   | Trạng thái: ✓ Đã xác nhận          |
| Khung giờ: 23:00 → 05:30 (17/11)   |   | Đầu nối: A07 · tối đa 7 kW         |
| Pin:       32% → 80%               |   | Khung giờ: 23:00 → 05:30           |
| Điện năng: ~32,0 kWh từ lưới       |   | Pin: 32% → 80% · ~32,0 kWh         |
|            (28,8 kWh vào pin, 90%) |   | Hạn lấy xe: 18/11 07:00            |
| Chi phí ước tính: 38.400 ₫         |   | Chi phí ước tính: 38.400 ₫         |
| ✓ Đúng hạn 07:00 · còn dư 1 giờ 30 |   | Đã nạp: 12,4 kWh (khi đang sạc)    |
| (Vị trí hàng đợi: 2 — khi có)      |   +------------------------------------+
+------------------------------------+   | Vì sao?                            |
| Vì sao?                            |   | • … (GET /resident/explanation)    |
| • Giờ thấp điểm, giá rẻ hơn        |   +------------------------------------+
| • Trạm còn 60% công suất trống     |   | [ Đổi yêu cầu ]     [ Huỷ lịch ]   |
+------------------------------------+   +------------------------------------+
| Không kịp hạn? Phương án thay thế: |   chỉ khi ScheduleProposal.feasible sai
| [Mức pin thấp hơn: 70%] [Giờ khác] |
+------------------------------------+
| Phạm vi bạn đã đồng ý: lùi tối đa  |   ConsentFields chỉ đọc (chế độ form)
| 30 phút · được giảm công suất      |
+------------------------------------+
| [  Xác nhận  ]  [ Đổi phương án ]  |
+------------------------------------+
```

**Dữ liệu hiển thị**

| Dòng | Chế độ chat / form | Chế độ booking |
|---|---|---|
| Đầu nối | `ScheduleProposal.connector_id` + `ConnectorSpec.max_power_kw` (từ `GET /station/config`). `null` → "Chưa có đầu nối — sẽ vào hàng đợi" | `Booking.connector_id` + `Booking.max_charge_power_kw` |
| Khung giờ | `ScheduleProposal.planned_start` → `ScheduleProposal.planned_end` | `Booking.planned_start` → `Booking.planned_end` |
| Pin | `ScheduleProposal.energy.soc_now` → `ScheduleProposal.energy.soc_target` | `Booking.request.soc_now` → `Booking.request.soc_target` |
| Điện năng (FR3) | `ScheduleProposal.energy.grid_energy_kwh` (+ `.battery_energy_kwh`, `.efficiency`) | `Booking.energy.grid_energy_kwh` |
| Chi phí | `ScheduleProposal.estimated_cost_vnd`; `null` → "Chưa ước tính được" | `Booking.estimated_cost_vnd` |
| Đúng hạn | Hạn = `ChargeRequest.deadline` (chat: lấy trong `pending`, G3; form: từ `request`). `ScheduleProposal.feasible` đúng → "✓ Đúng hạn hh:mm · còn dư {slack_minutes}"; sai → "✕ Không kịp hạn hh:mm". Chat mà không đọc được hạn → "✓ Kịp hạn · còn dư …" | `Booking.request.deadline`, ghi "Hạn lấy xe" |
| Hàng đợi | `ScheduleProposal.queue_position` (khi có) | `Booking.status` = `queued` → QueueBadge (`GET /resident/queue`) |
| Tiến độ | — | `ResidentSessionView.progress.delivered_grid_kwh`, `ResidentSessionView.soc_estimate` (dùng lại query của S2) |
| Vì sao? | `ScheduleProposal.reasons` | `GET /resident/explanation` |
| Phương án thay thế (FR4) | `ScheduleProposal.alternatives[]`: `Alternative.kind`, `Alternative.description`, `Alternative.soc_target`, `Alternative.deadline` | — |

**Thành phần tương tác**

| # | Thành phần | Chế độ | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|---|
| 1 | "Xác nhận" | chat | Chốt lịch | `POST /chat/resume` · `ResumeRequest{session_id, resume: "approve"}` | `ChatResponse.status`, `ChatResponse.proposal`, `ChatResponse.response` | `needs_confirmation` → thay phương án mới tại chỗ + báo "Phương án đã được cập nhật". `answer` → tải lại `GET /resident/bookings/current` (G1, G4): có booking `confirmed`, `queued` hoặc `charging` mà `booking_id` khác `planDraft.booking_id_before` thì xoá `planDraft`, về S2 + toast "Đã đặt lịch" (gồm cả lần bấm lặp sau một lần đã thành công). Không có thì **chưa đặt được**: hiện "Chưa đặt được lịch qua Trợ lý" + nút "Đặt bằng form" (điền sẵn từ `pending`). Không dùng `response` làm thông báo chính: khi mất phiên chờ, đó là câu LLM trả lời cho một câu hỏi rỗng (G1) | 409 `no_pending_confirmation` (chỉ có sau khi làm G1) → xử lý như nhánh `answer` không có booking mới. 503 `llm_unavailable` → nút form | ✅ có điều kiện / T3.3 |
| 2 | "Đổi phương án" | chat | Từ chối phương án | `POST /chat/resume` · `ResumeRequest{session_id, resume: "reject"}` | `ChatResponse.response` | Xoá `planDraft`, về S2, nối `response` vào bản ghi chat, focus vào ô nhập | như #1 | ✅ có điều kiện / T3.3 |
| 3 | "Xác nhận" | form | Đặt lịch | `POST /resident/bookings` · body `ChargeRequest` (đúng `request` đã quote) + header `Idempotency-Key` = `planDraft.idempotency_key` | `Booking` (201) | Xoá `planDraft`; `setQueryData(["resident","booking"])`; `invalidate` session và queue; về S2 + toast "Đã đặt lịch A07, 23:00 → 05:30" | 409 `booking_conflict` → panel + link `?view=booking`. 409 `proposal_expired` → nút "Xem phương án mới" (gọi lại `POST /resident/quote`, sinh khoá mới). 409 `idempotency_mismatch` → sinh khoá mới rồi quote lại. 422 hoặc 404 → về `/resident/book`, lỗi gắn vào ô | T2.2 / T2.7 |
| 4 | "Đổi phương án" | form | Sửa yêu cầu | — | — | Về `/resident/book`, giữ dữ liệu form | — | — / T2.7 |
| 5 | Nút phương án thay thế | form | Thử phương án khác | `POST /resident/quote` · `ChargeRequest`, trong đó `soc_target` = `Alternative.soc_target` (`lower_target`) hoặc `deadline` = `Alternative.deadline` (`other_time`) | `ScheduleProposal` | Thay phương án tại chỗ, sinh khoá mới | 422 → hiện ở đầu trang | T2.2 / T2.7 |
| 6 | Phương án `join_queue` | form, chat | — | Chỉ hiện `Alternative.description`; chưa dựng được yêu cầu để chấp nhận (G6) | — | — | — | — / T2.7 |
| 7 | Phương án thay thế | chat | — | Chỉ hiển thị, kèm gợi ý "Bấm Đổi phương án rồi nhắn lựa chọn của bạn" | — | — | — | — / T3.3 |
| 8 | "Đổi yêu cầu" | booking | Mở `ChangeBookingDialog` với `soc_target` (%) và `deadline` (giờ trạm); phải đổi ít nhất một ô | Khi có G2: xem trước bằng `POST /resident/bookings/{booking_id}/quote` 🆕 G2. Sau đó `PATCH /resident/bookings/{booking_id}` · `BookingChangeRequest{soc_target?, deadline?}` | `Booking` | Đóng dialog, `setQueryData`, toast "Đã cập nhật — lịch được tính lại" (FR8) | 409 `proposal_expired` (đề xuất ở G2) → giữ dialog, hiện `detail`. 422 → báo ở ô. 404 → lịch không còn, về S2 | T2.8 / T2.8 |
| 9 | "Huỷ lịch" | booking | `ConfirmDialog` "Huỷ lịch sạc A07, 23:00 → 05:30?"; nút an toàn "Giữ lịch" nhận focus. Khi `Booking.status` = `charging` thì thêm câu "Xe đang sạc, huỷ sẽ dừng sạc" | `DELETE /resident/bookings/{booking_id}` | `Booking` (`status` = `cancelled`) | `setQueryData(["resident","booking"], null)`; `invalidate` session và queue; về S2 + toast "Đã huỷ lịch" | 404 → "Lịch không còn tồn tại", tải lại. Lỗi khi lịch đã hết hiệu lực chưa có mã (G20) | T2.2 / T2.7 |
| 10 | "← Quay lại" | tất cả | Quay lại | — | — | chat → S2 (giữ `planDraft` để mở lại); form → `/resident/book`, giữ dữ liệu; booking → S2 | — | — / T2.7 |

**Trạng thái**

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | chat, form: không cần tải, dữ liệu có sẵn trong `planDraft`. booking: skeleton |
| Rỗng | booking: `GET /resident/bookings/current` trả `null` → "Bạn chưa có lịch sạc" + nút "Chat với Trợ lý" và "Đặt bằng form" |
| Lỗi | `ErrorPanel` thay khối chi tiết; ẩn nút "Xác nhận" |
| 501 | booking: `NotImplementedPanel` T2.2; "Vì sao?" T2.5. Nút ghi gặp 501 → panel compact dưới nút |
| Mất realtime | booking: hỏi lại mỗi 15 giây. chat, form: không áp dụng |
| Disabled | "Xác nhận" khoá khi đang gửi, khi `planDraft` thiếu `proposal`, hoặc khi `ScheduleProposal.feasible` sai, kèm lý do "Phương án không kịp hạn — hãy chọn một phương án thay thế" (chế độ chat: bấm "Đổi phương án" rồi nhắn lựa chọn). Vì `charging_service.book` từ chối phương án không khả thi bằng 409 `proposal_expired`, cho bấm chỉ dẫn tới thông báo sai "Trạng thái trạm đã thay đổi". "Đổi yêu cầu", "Huỷ lịch" chỉ hiện khi `Booking.status` là `confirmed`, `queued` hoặc `charging` |

**Realtime**

| `type` | Cập nhật |
|---|---|
| `schedule_changed` (`ResidentSessionView`) | booking: cập nhật chi tiết, tải lại "Vì sao?". chat, form: giữ phương án đang xem (đây là what-if) nhưng hiện dòng "Trạm vừa thay đổi — phương án có thể không còn đúng" |

**Yêu cầu**: FR2 (xác nhận một lần cho cả dữ liệu trích xuất lẫn phương án, Q12), FR3, FR4, FR8, FR9 (hạn lấy xe luôn hiện, là
ràng buộc cứng), FR13 (phạm vi đã đồng ý hiện trước khi chốt), US1, US3, AC1, AC2 (`queue_position`), NFR khả dụng.

### 2.4 Đặt lịch bằng form — `/resident/book`

- **Mục đích**: đặt lịch không cần LLM (NFR khả dụng), đi cùng `charging_service` với Agent. **Vai trò**: resident.
  **Viewport**: từ 360 px.

```text
+------------------------------------+
| [← Trang chủ]  Đặt lịch bằng form  |
+------------------------------------+
| [!] Bạn đang có lịch A07 23:00 →   |  khi có booking hiệu lực (Q6)
|     05:30.       [Xem / đổi lịch]  |
+------------------------------------+
| Mẫu xe        [Xe mẫu 60 kWh    ▾] |
| Pin hiện tại (%)            [ 32 ] |
| Pin mong muốn (%)           [ 80 ] |
| Cách sạc  (•) Đặt trước            |
|           ( ) Đến trực tiếp        |
| Giờ cắm xe (giờ trạm) [17/11 23:00]|  chỉ khi Đặt trước
| Giờ cần lấy xe        [18/11 07:00]|
| ≈ 32,0 kWh từ lưới                 |  POST /energy/estimate
|   (28,8 kWh vào pin, hiệu suất 90%)|
+------------------------------------+
| Phạm vi bạn đã đồng ý (Hồ sơ):     |  ConsentFields chỉ đọc
| lùi tối đa 30 phút · được giảm     |
| công suất · đồng ý bảo vệ khẩn cấp |
| [Sửa trong Hồ sơ]                  |
+------------------------------------+
| [        Xem phương án        ]    |
+------------------------------------+
```

**Thành phần tương tác**

| # | Ô / nút | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|
| 1 | Mẫu xe (`<select>`) | Chọn | `GET /vehicles` | `VehicleSpec.vehicle_model`, `VehicleSpec.display_name`, `VehicleSpec.verified` | Mặc định = `ResidentProfile.vehicle_model` (hoặc `UserProfile.vehicle_model`). `verified` sai → thêm "(thông số chưa kiểm chứng)" | quote hoặc estimate trả 404 → lỗi ở ô này | ✅ / T2.7 |
| 2 | Pin hiện tại (%) | Nhập số 0–100 (`inputmode="numeric"`) | — | — | — | 422 tại `ChargeRequest.soc_now` | — / T2.7 |
| 3 | Pin mong muốn (%) | Lớn hơn pin hiện tại, tối đa 100. Mặc định `ResidentProfile.default_soc_target` | — | — | — | "Mức pin mong muốn phải lớn hơn mức hiện tại" (validator: `soc_target` > `soc_now`) | — / T2.7 |
| 4 | Cách sạc (radio) | `reservation` hoặc `walk_in` (nhãn ở mục 1.2) | — | — | `walk_in` → ẩn ô giờ cắm xe, gửi `arrival_time` = `null` | — | — / T2.7 |
| 5 | Giờ cắm xe (`datetime-local`) | Bắt buộc khi `reservation` | — | — | — | "Đặt trước cần giờ cắm xe" | — / T2.7 |
| 6 | Giờ cần lấy xe (`datetime-local`) | Bắt buộc; là ràng buộc cứng (FR9) | — | — | — | "Giờ lấy xe phải sau giờ cắm xe". Riêng ở client: cảnh báo nếu mốc đã qua | — / T2.7 |
| 7 | Dòng ước tính kWh | Tự gọi khi đã có xe và hai mức pin hợp lệ (debounce 400 ms; `aria-live="polite"`) | `POST /energy/estimate` · `EnergyEstimateRequest{vehicle_model, soc_now, soc_target}` | `EnergyEstimate.grid_energy_kwh`, `EnergyEstimate.battery_energy_kwh`, `EnergyEstimate.efficiency` | "≈ 32,0 kWh từ lưới (28,8 kWh vào pin, hiệu suất 90%)" | 404 → lỗi ở ô mẫu xe; 422 → để trống dòng này | ✅ / T2.7 |
| 8 | Khối "Phạm vi bạn đã đồng ý" | Chỉ đọc | `GET /resident/profile` | `ResidentProfile.consent`: `ConsentScope.max_start_delay_minutes`, `ConsentScope.allow_power_reduction`, `ConsentScope.emergency_curtailment` | 3 dòng chữ + link "Sửa trong Hồ sơ" | 501 T2.8 → panel compact, không chặn form | T2.8 / T2.7 |
| 9 | "Xem phương án" | Gửi | `POST /resident/quote` · `ChargeRequest{vehicle_model, soc_now, soc_target, arrival_time, deadline, mode}` | `ScheduleProposal` | Ghi `planDraft = {mode: "form", request, proposal, idempotency_key: crypto.randomUUID()}` → `/resident/plan` | 422 → gắn vào ô theo `FieldError.path`; lỗi cấp model (không có `path`) → đầu form. 501 → panel dưới nút | T2.2 / T2.7 |
| 10 | Cảnh báo lịch hiệu lực | Tải khi mở | `GET /resident/bookings/current` | `Booking.status` là `confirmed`, `queued` hoặc `charging` | Banner + link `/resident/plan?view=booking`. Form vẫn dùng được; nếu vẫn đặt, backend trả 409 `booking_conflict` | 501 → bỏ qua banner | T2.2 / T2.7 |

**Điền sẵn**: từ `planDraft.request` khi quay lại từ S3 chế độ form; từ `pending` khi S3 chế độ chat phải lui sang form (G1);
từ hồ sơ cho mẫu xe và mức pin mong muốn. Thời gian nhập theo giờ trạm, gửi đi bằng ISO có offset (mục 1.3).

**Trạng thái**

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | `<select>` mẫu xe hiện "Đang tải danh mục…" và bị khoá |
| Rỗng | Danh mục xe rỗng → "Chưa có mẫu xe nào trong danh mục"; nút "Xem phương án" bị khoá |
| Lỗi | Không tải được danh mục → `ErrorPanel` thay cho `<select>`, nút bị khoá |
| 501 | quote 501 T2.2 → panel dưới nút; khối phạm vi đồng ý 501 T2.8 → panel compact |
| Mất realtime | Không áp dụng |
| Disabled | "Xem phương án" khoá khi thiếu trường bắt buộc, có lỗi ở client hoặc đang gửi; có dòng nêu lý do |

**Realtime**: không.

**Yêu cầu**: FR2 (đủ 6 trường, mẫu xe chọn từ danh mục), FR3, FR9, FR13 (dòng 2: cư dân thấy phạm vi đã đồng ý trước khi
đăng ký), US1, NFR khả dụng.

### 2.5 Thông báo — `/resident/notifications`

- **Mục đích**: xem đề nghị cần trả lời, thay đổi lịch, giảm công suất khẩn cấp (FR15). **Vai trò**: resident.
  **Viewport**: từ 360 px.

```text
+------------------------------------+
| [← Trang chủ]  Thông báo           |
+------------------------------------+
| ⚠ Cần bạn trả lời · Mới     19:10  |
|   Đề nghị giảm công suất A07       |
|   [Mở đề nghị]                     |
+------------------------------------+
| ⚠ Đã giảm công suất khẩn cấp 18:02 |
|   Nguồn giảm 35 → 20 kW… [Xem thêm]|
+------------------------------------+
| ↻ Lịch thay đổi             17:40  |
+------------------------------------+
```

**Thành phần tương tác**

| # | Thành phần | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|
| 1 | Danh sách | Tải khi mở; sắp theo `created_at` giảm dần ở client | `GET /resident/notifications` | `Notification.notification_id`, `Notification.kind`, `Notification.title`, `Notification.body`, `Notification.created_at`, `Notification.read`, `Notification.approval_id` | `NotificationList`. Tin chưa đọc có chữ "Mới" và chữ đậm, không chỉ dùng chấm màu | — | T1.6 / T3.3 |
| 2 | "Mở đề nghị" (khi `kind` = `approval_request` và có `approval_id`) | Đánh dấu đã đọc rồi mở S4 | `POST /resident/notifications/{notification_id}/read` | `Notification.read` | `setQueryData` thay mục đó; → `/resident/notifications/{approval_id}` | Đánh dấu đọc lỗi thì vẫn điều hướng | T1.6 / T3.3 |
| 3 | "Xem thêm" (các `kind` khác) | Mở rộng `body` tại chỗ (`aria-expanded`) và đánh dấu đã đọc | `POST /resident/notifications/{notification_id}/read` | `Notification` | Mục mất chữ "Mới"; số trên chuông giảm | 404 → tải lại danh sách | T1.6 / T3.3 |

Không có nút "Đánh dấu tất cả đã đọc" (G18).

**Trạng thái**

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | skeleton 3 mục |
| Rỗng | "Chưa có thông báo nào." |
| Lỗi | `ErrorPanel` + "Thử lại" |
| 501 | `NotImplementedPanel` T1.6 |
| Mất realtime | Hỏi lại mỗi 15 giây |
| Disabled | — |

**Realtime**

| `type` | Cập nhật |
|---|---|
| `notification` (`Notification`) | Thêm vào đầu danh sách (bỏ trùng theo `notification_id`); giọng đọc báo "Thông báo mới: {title}" |
| `approval_request` (`Approval`) | `invalidate` danh sách |

**Yêu cầu**: FR15 (thông báo phê duyệt), FR13 (với bảo vệ khẩn cấp: thực thi ngay, thông báo sau — `emergency_curtailment`),
AC4, AC5, US4.

### 2.6 S4 · Đề nghị điều chỉnh sạc — `/resident/notifications/[approvalId]`

- **Mục đích**: cư dân đồng ý hoặc từ chối điều chỉnh vượt phạm vi đã đồng ý (FR13 dòng 1, AC4). **Vai trò**: resident;
  chỉ người có `Approval.requested_from` là mình, người khác nhận 404. **Viewport**: từ 360 px.

```text
+------------------------------------+
| [← Thông báo]                      |
| ⚠ Đề nghị điều chỉnh sạc           |  <h1>
+------------------------------------+
| Lý do: Tải trạm đang 92% giới hạn. |  Command.reason
| Đề nghị: Đặt công suất A07 → 3,5 kW|  CommandType + power_kw
| (từ 7 kW, 19:10 → 19:50)           |  chỉ khi có G7
| Ảnh hưởng: Cam kết 80% lúc 07:00:  |  Approval.impact_summary
|            vẫn giữ                 |
| ✓ Guard: hợp lệ (kiểm lúc 19:09)   |  GuardVerdict
+------------------------------------+
| Hết hạn sau 04:12                  |  Countdown (role="timer")
| Nếu bạn không trả lời trước khi hết|
| hạn, điều chỉnh sẽ KHÔNG được áp   |
| dụng.                              |
| [+ Thêm ghi chú]                   |
| [   Đồng ý   ]    [  Từ chối   ]   |
+------------------------------------+
```

**Thành phần tương tác**

| # | Thành phần | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|
| 1 | Chi tiết | Tải khi mở | `GET /resident/approvals/{approval_id}` | `Approval.status`, `Approval.kind`, `Approval.command` (`.type`, `.connector_id`, `.power_kw`, `.reason`, `.source`), `Approval.impact_summary`, `Approval.verdict` (`.passed`, `.checked_at`), `Approval.expires_at`, `Approval.created_at`, `Approval.decided_at` | Hiện như wireframe | 404 → "Không tìm thấy đề nghị này (có thể không thuộc tài khoản của bạn)" + link Thông báo | T1.6 / T3.3 |
| 2 | Countdown | Đếm tới `Approval.expires_at` theo đồng hồ máy; giọng đọc báo khi còn 1 phút | — | — | Về 0 → khoá hai nút, hiện "Đã hết hạn — điều chỉnh không được áp dụng", tải lại #1 | `expires_at` là `null` (thời hạn chưa có tham số, G8) → ẩn đồng hồ, giữ câu "Điều chỉnh chỉ áp dụng khi bạn đồng ý" | — / T3.3 |
| 3 | "Thêm ghi chú" | Disclosure → `<textarea>` tối đa 500 ký tự | — | — | — | quá 500 → hiện bộ đếm | — / T3.3 |
| 4 | "Đồng ý" | Quyết định | `POST /resident/approvals/{approval_id}` · `ApprovalDecisionRequest{decision: "approve", note?}` | `Approval.status` (= `approved`), `Approval.decided_at` | `setQueryData`; về S2 + toast "Đã đồng ý — quyết định đã ghi vào nhật ký" (FR14) | 409 `approval_already_decided` → tải lại, hiện trạng thái thật (vd "Đã hết hạn"). 404 như #1 | T3.2 / T3.3 |
| 5 | "Từ chối" | Quyết định | Như #4 với `decision: "reject"` | `Approval.status` (= `rejected`) | Về S2 + toast "Đã từ chối — hệ thống sẽ tính lại lịch trong phạm vi bạn đã đồng ý" | như #4 | T3.2 / T3.3 |

**Quy tắc**

- `Approval.status` khác `pending` lúc mở: chỉ đọc ("Đã đồng ý lúc 19:12", "Đã từ chối", "Đã hết hạn — không áp dụng"), không
  có nút.
- Đồng hồ chỉ để thông tin. Hạn thật do server kiểm (`approval.expire_overdue`; quyết định muộn nhận 409). Client không tự
  quyết khi hết giờ, và **không** có "tự áp dụng" (AC4; PRD thắng Wireframe).
- Đồng hồ chạy theo giờ của máy; giờ máy lệch thì chỉ số hiển thị sai lệch theo. Header `Date` không đọc được qua CORS nên
  không dùng để bù.
- `Countdown` có `role="timer"` (ngầm định `aria-live="off"`). Một vùng `aria-live="polite"` riêng chỉ đọc "Còn 1 phút để
  trả lời" và "Đề nghị đã hết hạn".
- Response chưa cho biết lệnh có thực sự được áp sau khi đồng ý không, vì Guard kiểm lại lần 2 khi thực thi (G10). Vì vậy
  toast chỉ nói "đã ghi nhận".

**Trạng thái**

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | skeleton; fallback `<Suspense>` hiện có: "Đang tải yêu cầu phê duyệt…" |
| Rỗng | — (404 xử lý như lỗi ở #1) |
| Lỗi | `ErrorPanel` |
| 501 | GET → T1.6; POST → T3.2 (panel dưới nút) |
| Mất realtime | Không chặn gì: đồng hồ vẫn chạy; tải lại khi tab được focus lại |
| Disabled | Hai nút khoá khi đang gửi, khi hết giờ, hoặc khi `status` khác `pending` |

**Realtime**

| `type` | Cập nhật |
|---|---|
| `approval_request` (`Approval`, cùng `approval_id`) | `setQueryData`. Hiện server chỉ phát lúc mở đề nghị; muốn nhận cả khi trạng thái đổi thì cần G9 |

**Yêu cầu**: FR13, FR14 (quyết định được ghi log), US4, AC4.

### 2.7 Hồ sơ — `/resident/profile`

- **Mục đích**: sửa xe mặc định, mức pin hay dùng, phạm vi đồng ý trước (F8, FR13); xoá tài khoản (NFR riêng tư).
  **Vai trò**: resident. **Viewport**: từ 360 px.

```text
+------------------------------------+
| [← Trang chủ]  Hồ sơ của tôi       |
+------------------------------------+
| Mã người dùng (giả danh): res-1a2b…|
| Tên hiển thị     [ Cư dân A      ] |
| Xe mặc định      [Xe mẫu 60 kWh ▾] |
| Mức pin hay dùng (%)       [ 80 ]  |
+------------------------------------+
| Phạm vi bạn đồng ý trước           |  <fieldset>
| Lùi giờ bắt đầu tối đa [30 phút ▾] |
| [x] Cho phép giảm công suất nếu vẫn|
|     kịp hạn                        |
| [x] Đồng ý bảo vệ khẩn cấp (giảm   |
|     ngay khi nguồn giảm, báo sau)  |
| Áp dụng cho các lịch đặt sau khi   |
| lưu.                               |
+------------------------------------+
| [      Lưu thay đổi      ]         |
+------------------------------------+
| Xoá tài khoản                      |  vùng nguy hiểm
| Ẩn danh hoá hồ sơ, huỷ lịch đang   |
| hiệu lực.     [ Xoá tài khoản ]    |
+------------------------------------+
```

**Thành phần tương tác**

| # | Thành phần | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|
| 1 | Form | Tải khi mở | `GET /resident/profile` | `ResidentProfile.user_id`, `ResidentProfile.display_name`, `ResidentProfile.vehicle_model`, `ResidentProfile.default_soc_target`, `ResidentProfile.consent` | Điền form | — | T2.8 / T2.8 |
| 2 | Tên hiển thị | Nhập 1–80 ký tự, `autocomplete="name"` | — | — | — | 422 tại `ProfileUpdateRequest.display_name` | — / T2.8 |
| 3 | Xe mặc định | `<select>` lấy từ danh mục | `GET /vehicles` | `VehicleSpec.vehicle_model`, `VehicleSpec.display_name` | — | xe ngoài danh mục → lỗi ở ô (mã lỗi chưa định, G20) | ✅ / T2.8 |
| 4 | Mức pin hay dùng (%) | 1–100 | — | — | — | `ProfileUpdateRequest.default_soc_target` phải > 0 và ≤ 100 | — / T2.8 |
| 5 | Lùi giờ bắt đầu tối đa | `<select>`: 0, 15, 30, 60, 120 phút | — | — | — | `ConsentScope.max_start_delay_minutes` ≥ 0 | — / T2.8 |
| 6 | Hai checkbox | `ConsentScope.allow_power_reduction`, `ConsentScope.emergency_curtailment` | — | — | Bỏ chọn bảo vệ khẩn cấp → hiện câu giải thích hệ quả (câu hỏi mở O1) | — | — / T2.8 |
| 7 | "Lưu thay đổi" | Chỉ gửi field đã đổi (field `null` nghĩa là giữ nguyên). Đổi bất kỳ ô nào trong phạm vi đồng ý thì gửi cả object `consent` | `PUT /resident/profile` · `ProfileUpdateRequest{display_name?, vehicle_model?, default_soc_target?, consent?}` | `ResidentProfile` | `setQueryData`; cập nhật tên trong phiên để header đổi theo; toast "Đã lưu" | 422 → báo ở ô | T2.8 / T2.8 |
| 8 | "Xoá tài khoản" | `ConfirmDialog` bắt gõ "XOÁ"; nút an toàn "Giữ tài khoản" nhận focus | `DELETE /resident/profile` | 204 | `clearSession()` → `/login` kèm thông báo "Tài khoản đã được xoá (ẩn danh hoá)" | — | T2.8 / T2.8 |

**Quy tắc**

- Phạm vi đồng ý áp dụng cho các lịch **đặt sau** khi lưu: `charging_service.book` (khi `consent` để trống) lấy
  `ConsentScope` của hồ sơ tại lúc đặt và chép vào `Booking.consent`.
- Tên mới hiện ở header ngay. `GET /auth/me` có thể vẫn trả tên cũ tới khi đăng nhập lại (G21).
- "Mã người dùng" là mã giả danh (NFR riêng tư); trang không hiện email.

**Trạng thái**

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | skeleton form |
| Rỗng | — |
| Lỗi | `ErrorPanel`; ẩn form |
| 501 | `NotImplementedPanel` T2.8 cho cả trang, vì mọi thao tác đều thuộc T2.8 |
| Mất realtime | Không áp dụng |
| Disabled | "Lưu" khoá khi chưa đổi gì, có lỗi hoặc đang gửi |

**Realtime**: không.

**Yêu cầu**: FR13 (đồng ý trước), F8, NFR riêng tư (sửa, xoá thông tin; mã giả danh), Q9.

### 2.8 Sơ đồ bãi (cư dân) — `/resident/map` (mới 2026-11-19)

Mockup: [`docs/mockups/cu-dan/resident-map.html`](../mockups/cu-dan/resident-map.html), 3 tình huống: đang
chờ ở làn, đang sạc, đã đầy và nhắc rời ô.

- **Mục đích**: cư dân biết xe mình đang ở đâu (ô nào hoặc làn chờ nào, vị trí mấy), còn bao nhiêu cổng AC / DC trống, và
  đi tới chỗ nào. **Vai trò**: resident. **Viewport**: từ 360 px; trên máy tính nằm trong khung sidebar của `cu-dan`.
- **Riêng tư** (Q17, NFR): ô của người khác chỉ hiện 3 mức "Đang dùng", "Trống", "Tạm ngưng". Không hiện mã xe, SOC, giờ
  rời hay mã booking của cư dân khác. Lọc ở **backend** (G24), client không nhận dữ liệu thừa.

```text
+------------------------------------+
| Sơ đồ bãi · giờ trạm 18:30         |
| [Thẻ tối] Xe của bạn · VF 8 · AC   |
|   Chờ vị trí 1                     |
|   Vào cổng ~20:00 · Đạt 65% ~22:16 |
|   [Dự phòng 59 phút]               |
+------------------------------------+
| Khu sạc lúc này (SVG dọc)          |
|  ↓ Lối vào                         |
|  Vùng AC: [Tủ AC-01][Tủ AC-02]     |
|           [B-A1 Đang dùng][B-A2 …] |
|  Vùng DC: [Tủ DC-01 2 × 60 kW]     |
|           [B-D1 …]      [B-D2 …]   |
|  [Làn chờ AC: (1 Bạn)(2)] [Làn DC] |
|  Chú giải: chữ + icon + màu        |
+------------------------------------+
| Cổng còn trống: AC 0/2 · DC 0/2    |
| Đường tới chỗ của bạn: 1. 2. 3.    |
+------------------------------------+
```

| # | Thành phần | Hành vi | Endpoint | Field |
|---|---|---|---|---|
| 1 | Thẻ "Xe của bạn" | Tải khi mở; cập nhật theo WS | `GET /resident/session`, `GET /resident/queue` | `ChargingSession.connector_id`, `QueueStatus.position`, `QueueStatus.estimated_start`, `ScheduleProposal.estimated_finish`, `Booking.deadline` |
| 2 | `SiteMap` (dọc, chỉ đọc) | `role="img"` + `aria-label` tóm tắt (vị trí xe, số cổng trống mỗi vùng, số xe chờ). Không có phần tử focus được bên trong | 🆕 G22 layout + 🆕 G24 `GET /resident/site-map` | `SiteLayout.bays[]`, `ResidentSiteMap.bays[].public_status`, `.mine`, `ResidentSiteMap.queues[zone].length`, `.my_position` |
| 3 | Cổng còn trống | Đếm từ #2 | (từ #2) | `public_status = idle` theo `zone` |
| 4 | Đường tới chỗ của bạn | Chữ sinh ở client từ #1 + layout (lối vào → vùng → ô / làn). Không phải chỉ đường thật | (từ #1, #2) | `SiteLayout.gates[]`, `bays[].bay_id` |
| 5 | Nhắc rời ô | Khi xe đã đầy: "Cổng vẫn giữ cho bạn tới {deadline}" (AC); DC: "Vui lòng rời ô trong 5 phút" | (từ #1) | `ConnectorStatus.finished`, `StationConfig.dc_unplug_delay_minutes` |

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | Skeleton thẻ + khung SVG xám |
| Rỗng | Không có phiên / booking: ẩn thẻ #1, sơ đồ vẫn hiện, kèm nút "Đặt lịch sạc" |
| Lỗi | `ErrorPanel` riêng cho sơ đồ; thẻ #1 vẫn dùng được |
| 501 | Trước T2.9: `NotImplementedPanel` G24 cho sơ đồ; thẻ #1 theo T2.2 |
| Mất realtime | Chữ "Đang hiển thị dữ liệu lúc {giờ}", giống `cu-dan` "Đang kết nối lại" |
| Disabled | Không có |

**Realtime**: `schedule_changed` (thẻ #1), 🆕 `site_occupancy` (G24, chỉ đổi `public_status`).

**Yêu cầu**: FR15, FR7 (hàng đợi), AC2 (đến trực tiếp khi hết cổng), NFR riêng tư, ADR-010.

## 3. Màn vận hành

Thiết kế từ 1024 px; hẹp hơn thì xếp 1 cột (mục 1.1). Tab điều hướng và số "Duyệt lệnh (n)" theo mục 1.4.

### 3.1 S5 · Dashboard trạm — `/operator`

- **Mục đích**: xem theo thời gian thực các đầu nối (số lượng lấy từ API — fixture nền 4 cổng, ADR-010), tải so với giới hạn, hàng đợi, phiên có nguy cơ trễ hạn, sự cố và lệnh
  bị chặn (FR16, US5). **Vai trò**: operator. **Viewport**: từ 1024 px.

```text
+--------------------------------------------------------------------------------+
| ⚡ ChargePilot · Vận hành  [Dashboard][Hàng đợi & lịch][Duyệt lệnh (3)][Mô phỏng]|
|                                                  Trực tiếp   [Tạm dừng cập nhật] |
+--------------------------------------------------------------------------------+
| Tải tổng 29,4 / 35 kW (84%) ▓▓▓▓▓▓▓▓░░ | Đang sạc 6 · Chờ 3 | Nguy cơ trễ hạn: 1 |
| Chi phí hôm nay 412.000 ₫ (−18% so với FCFS) | Cảnh báo: 1 đầu nối lỗi          |
| Cập nhật lúc 19:05:12                                                           |
+----------------------------------------+---------------------------------------+
| Tải 24 giờ (kW)                        | Đầu nối                               |
|  35 |- - - - - - giới hạn - - - - - -  | [A01 ● Đang sạc  7,0/7 kW  #9f1c2a]   |
|     |         ___/‾‾\___               | [A02 ● Đang sạc  3,5/7 kW  #3b7e01]   |
|   0 |________/          \______        | [A03 ○ Trống]   [A04 ▼ Giảm công suất]|
|     0h    6h    12h    18h    24h      | [A05 ✕ Lỗi]     [A06 ✓ Đã đầy]        |
| ▸ Xem bảng số liệu                     | [A07 ● Đang sạc  ⚠ Nguy cơ trễ hạn]   |
|                                        | [A08 ○ Trống]                         |
+----------------------------------------+---------------------------------------+
| Gần nhất: 19:05 Guard chặn "Bắt đầu sạc A03" — Bật/tắt liên tục   [Xem tất cả] |
+--------------------------------------------------------------------------------+
```

**Thành phần tương tác**

| # | Thành phần | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|
| 1 | KpiBar | Tải khi mở; WS cập nhật | `GET /operator/station` | `StationOverview.state.connectors[].power_kw` (cộng lại thành tải tổng, G14), `StationOverview.state.available_power_kw` (giới hạn hiện hành), `StationOverview.power_limit_kw` (G12), `StationOverview.utilization_pct`, `StationOverview.charging_count`, `StationOverview.queue_length`, `StationOverview.energy_cost_today_vnd`, `StationOverview.cost_vs_fcfs_pct`, `StationOverview.at_risk_booking_ids`, `StationOverview.alerts`, `StationOverview.state.timestamp` | Thanh tải kèm chữ "{tải} / {giới hạn} kW ({%})", số lấy từ API. Khi `available_power_kw` < `power_limit_kw`: hiện "Giới hạn hiện hành {x} kW (cấu hình {y} kW)" + nhãn cảnh báo (AC5). Field `null` → "—" | — | T3.6 / T3.6 |
| 2 | "Cập nhật lúc" | — | (từ #1) + `GET /station/config` | `StationState.timestamp`; ngưỡng `GuardSettings.max_state_age_seconds` | Cũ hơn ngưỡng → "⚠ Dữ liệu cũ (hơn 60 giây)" | — | — / T3.6 |
| 3 | LoadChart (recharts) | Tải khi mở | `GET /operator/load?hours=24` | `LoadPoint.timestamp`, `LoadPoint.total_power_kw`, `LoadPoint.power_limit_kw` | Đường tải + vạch giới hạn nét đứt dạng bậc thang (giới hạn đổi theo thời gian); trục giờ theo giờ trạm; `<details>` "Xem bảng số liệu" | — | T3.6 / T3.6 |
| 4 | Ô đầu nối (`<button>`) | Mở `ConnectorDialog` | `GET /operator/connectors/{connector_id}` | `ConnectorDetail.state`, `ConnectorDetail.booking` (`.request`, `.planned_start`, `.planned_end`, `.status`), `ConnectorDetail.plan.slots`, `ConnectorDetail.recent_decisions[]` | Dialog: trạng thái; xe (mã giả danh), mức pin mục tiêu, hạn; lịch công suất dạng bảng; 5 quyết định gần nhất (lệnh, kết luận Guard, đã thực thi chưa) | 404 → "Không có đầu nối này" | T3.6 / T3.6 |
| 5 | Ô đầu nối (hiển thị) | — | (từ #1) | `ConnectorState.connector_id`, `ConnectorState.status`, `ConnectorState.power_kw`, `ConnectorState.max_power_kw`, `ConnectorState.booking_id`. `booking_id` có trong `at_risk_booking_ids` → badge "Nguy cơ trễ hạn" | `StatusBadge` (mục 1.1). Tên truy cập của nút, vd "A07, Đang sạc, 3,5 trên 7 kW, nguy cơ trễ hạn" | — | — / T3.6 |
| 6 | EventTicker | Tải khi mở | `GET /operator/events?limit=20` + `GET /operator/commands/blocked?limit=5` | `StationEvent.type`, `StationEvent.occurred_at`, `StationEvent.connector_id`, `StationEvent.booking_id`, `StationEvent.new_power_limit_kw`, `StationEvent.detail`; `DecisionLogEntry.timestamp`, `DecisionLogEntry.command`, `DecisionLogEntry.verdict.violations[].rule` | Gộp hai nguồn, sắp theo thời gian giảm dần (R4). Hiện 1 dòng mới nhất; "Xem tất cả" mở danh sách (bỏ loại `tick`) | Một nguồn lỗi hoặc 501 → vẫn hiện nguồn kia, kèm panel compact | T3.6, T1.6 / T3.6 |
| 7 | "Tạm dừng cập nhật" (`aria-pressed`) | Đóng băng phần hiển thị (cache vẫn nhận dữ liệu); bấm lại thì hiện bản mới nhất (R5) | — | — | Nhãn "Đang tạm dừng — bấm để tiếp tục" | — | — / T3.6 |
| 8 | Lối tắt | Ô KPI "Chờ" → S6; "Cảnh báo" và dòng lệnh bị chặn → S7 | — | — | — | — | — / T3.6 |

**Trạng thái**

| Trạng thái | KpiBar | LoadChart | ConnectorGrid | EventTicker |
|---|---|---|---|---|
| Đang tải | skeleton | trục rỗng | Ô xám theo số đầu nối, ID lấy từ `StationConfig.connectors[].connector_id` | "Đang tải…" |
| Rỗng | — | không có điểm → "Chưa có dữ liệu tải trong 24 giờ" | — | "Chưa có sự kiện" |
| Lỗi | `ErrorPanel` (khối khác vẫn chạy) | `ErrorPanel` | `ErrorPanel` | `ErrorPanel` compact |
| 501 | T3.6 | T3.6 | T3.6 (lưới lấy từ `GET /operator/station`) | events T3.6, blocked T1.6 |
| Mất realtime | hỏi lại 15 giây + "Cập nhật lúc" | tải lại mỗi 60 giây | theo KpiBar | hỏi lại 15 giây |
| Disabled | — | — | — | — |

**Realtime** (kênh operator)

| `type` | Cập nhật |
|---|---|
| `station_snapshot` (`StationOverview`) | `setQueryData(["operator","station"])` → KpiBar + lưới; tải lại biểu đồ tối đa 1 lần mỗi 60 giây. Không đọc bằng giọng đọc |
| `event` (`StationEvent`) | Thêm vào ticker. Loại `connector_fault` và `power_limit_changed` thì giọng đọc báo |
| `command_blocked` (`DecisionLogEntry`) | Thêm vào ticker + toast "Guard đã chặn: {lệnh} — {luật}" (AC6) |
| `approval_request` (`Approval`) | Cập nhật số trên tab "Duyệt lệnh" |

**Yêu cầu**: FR16, FR10 (giới hạn đổi thì thấy ngay và tải được phân bổ lại), FR12 + AC6 (lệnh bị chặn hiện trên dashboard),
AC5 (giới hạn giảm), US5, MT4 (biểu đồ cho thấy tải luôn dưới giới hạn), NFR khả dụng (`alerts` có dòng "trạng thái
simulator đã được dựng lại", 10 §5.3).

### 3.2 S6 · Hàng đợi & lịch — `/operator/schedule`

- **Mục đích**: xem lịch theo đầu nối (Gantt) và hàng chờ; lập lịch lại; xếp xe thủ công, lệnh vẫn qua Guard (FR8,
  US6). **Vai trò**: operator. **Viewport**: từ 1024 px; Gantt cuộn ngang trong vùng riêng.

```text
+--------------------------------------------------------------------------------+
| Hàng đợi & lịch        Ngày [17/11/2026] [Hôm nay]                [Lập lịch lại] |
| Lịch v42 · chiến lược C · giải 0,8 giây · tạo lúc 19:05                         |
+--------------------------------------------------------------------------------+
| Đầu nối | 18h     20h     22h     0h      2h      4h      6h   … (96 ô × 15')   |
| A01     | ████#9f1c████          ░░#03ab░░░░                                    |
| A02     |                  │ bây giờ                                            |
| A07     |              ███████#08cd███████                                      |
| …       |                                                                      |
| Chú thích: ████ công suất đầy (≥ 90% tối đa) · ░░░░ công suất giảm             |
| ▸ Xem bảng số liệu                                                             |
+--------------------------------------------------------------------------------+
| Hàng chờ (3)                                                                   |
| (•) 1. #31ab · Đến trực tiếp · Pin 20% → 70% · lấy xe trước 06:00 · chờ 25 phút |
| ( ) 2. #32cd · Đặt trước · Pin 35% → 80% · lấy xe trước 07:30 · chờ 10 phút     |
| Xếp xe đã chọn vào đầu nối [A03 — Trống ▾]                     [Xếp thủ công]   |
| Kết quả: ✓ Đã xếp · hoặc Chờ duyệt (S7) · hoặc ✕ Guard chặn: Vượt giới hạn tổng |
+--------------------------------------------------------------------------------+
```

**Thành phần tương tác**

| # | Thành phần | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|
| 1 | Chọn ngày (`<input type="date">`, giờ trạm) + "Hôm nay" | Đổi ngày → tải lại tại chỗ, không chuyển trang (3.2.2) | `GET /operator/schedule?date=YYYY-MM-DD`; "Hôm nay" = bỏ tham số `date` | `SchedulePlan` | Gantt của ngày đó. Ngày khác hôm nay → nhãn "Chỉ xem", khoá #4 và #6 | 404 → "Không có lịch cho ngày này" (nghĩa của `date` chưa định, G15) | T3.6 / T3.6 |
| 2 | GanttChart (CSS grid) | Hiển thị | (từ #1) + `GET /station/config` | `SchedulePlan.horizon_start`, `SchedulePlan.step_minutes`, `SchedulePlan.sessions[]` (`SessionPlan.booking_id`, `SessionPlan.connector_id`, `SessionPlan.slots[]` gồm `PowerSlot.start`, `PowerSlot.power_kw`), `SchedulePlan.version`, `SchedulePlan.strategy`, `SchedulePlan.solve_time_s`, `SchedulePlan.created_at`. Hàng = `StationConfig.connectors[].connector_id`; số cột = `StationConfig.horizon_hours` × 60 / `step_minutes` (24 × 60 / 15 = 96) | Thanh = chuỗi slot liên tiếp có `power_kw` > 0. `power_kw` ≥ 0,9 × `ConnectorSpec.max_power_kw` → tô đặc `--color-gantt-full`; thấp hơn → sọc chéo `--color-gantt-reduced`. Nhãn `#booking_id` rút gọn đặt trong ô nền trắng. Có vạch "bây giờ". Header hiện phiên bản + `solve_time_s` (MT5) | `sessions` rỗng → "Chưa có phiên nào trong lịch" | T3.6 / T3.6 |
| 3 | QueueList | Tải khi mở | Thứ tự lấy từ `SchedulePlan.queue` (đầu hàng trước); chi tiết từ `GET /operator/bookings` (gọi không lọc rồi lọc ở client, G16) | `Booking.booking_id`, `Booking.request` (`.mode`, `.soc_now`, `.soc_target`, `.deadline`), `Booking.created_at`, `Booking.status` | Danh sách radio; "chờ" = bây giờ trừ `created_at` | Mã trong `queue` không có trong danh sách booking → hiện mã + "Thiếu chi tiết" | T3.6 / T3.6 |
| 4 | "Lập lịch lại" | Tính lại ngay (FR8) | `POST /operator/schedule/replan` (không có body) | `SchedulePlan` | `setQueryData(["operator","schedule"])`; toast "Đã tính lại: v43 · 0,8 giây" | — | T2.6 / T3.6 |
| 5 | Chọn đầu nối (`<select>`) | Chọn | (từ `GET /operator/station`) | `ConnectorState.connector_id`, `ConnectorState.status`. Đầu nối `idle` xếp lên đầu; các đầu nối khác ghi rõ trạng thái trong nhãn ("A05 — Lỗi") | — | — | T3.6 / T3.6 |
| 6 | "Xếp thủ công" | Gửi lệnh của vận hành; lệnh vẫn qua 7 luật của Guard | `POST /operator/queue/{booking_id}/assign` · `ManualAssignRequest{connector_id}` | `DecisionLogEntry.verdict.passed`, `DecisionLogEntry.verdict.violations[]` (`Violation.rule`, `Violation.detail`), `DecisionLogEntry.executed`, `DecisionLogEntry.approval_id`, `DecisionLogEntry.note` | `passed` và `executed` → "✓ Đã xếp #31ab vào A03". `passed` và có `approval_id` → "Chờ duyệt" + link S7. `passed` sai → "✕ Guard chặn: {luật} — {detail}". Trường hợp bị chặn **vẫn là 200**, không phải lỗi (AC6) | 404 → booking hoặc đầu nối không còn. Khi booking đã rời hàng chờ: mã lỗi chưa định (G20) | T3.2 / T3.6 |

**Trạng thái**

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | Gantt: lưới rỗng 8 hàng; QueueList: skeleton |
| Rỗng | Gantt: "Chưa có phiên nào trong lịch". QueueList: "Không có xe chờ"; #6 bị khoá |
| Lỗi | `ErrorPanel` cho từng khối |
| 501 | schedule, bookings: T3.6; replan: T2.6; assign: T3.2 |
| Mất realtime | Hỏi lại mỗi 15 giây, chỉ khi đang xem hôm nay |
| Disabled | "Lập lịch lại" khoá khi đang chạy hoặc ngày khác hôm nay. "Xếp thủ công" khoá khi chưa chọn xe và đầu nối, khi ngày khác hôm nay, hoặc khi đang gửi. Luôn có lý do bằng chữ |

**Realtime**

| `type` | Cập nhật |
|---|---|
| `schedule_changed` (`SchedulePlan`) | Đang xem hôm nay: `setQueryData`, `invalidate` danh sách booking, giọng đọc báo "Lịch đã cập nhật lên v{version}". Đang xem ngày khác: bỏ qua |
| `station_snapshot` (`StationOverview`) | Cập nhật danh sách đầu nối ở #5 |

**Yêu cầu**: FR6 và FR7 (kết quả tối ưu và hàng đợi hiển thị trên Gantt, hàng chờ), FR8, FR12, FR16, US6, AC2 (hàng đợi khi
hết đầu nối), MT5 (`solve_time_s`).

### 3.3 S7 · Duyệt lệnh — `/operator/approvals`

- **Mục đích**: duyệt hoặc từ chối điều chỉnh nhạy cảm; xem lệnh bị chặn kèm lý do; xem nhật ký quyết định (FR13, FR14,
  US7). **Vai trò**: operator. **Viewport**: từ 1024 px; khung chi tiết nằm bên phải khi rộng từ 1280 px, hẹp hơn thì nằm
  dưới bảng.

```text
+--------------------------------------------------------------------------------+
| Duyệt lệnh       [Chờ duyệt (3)] [Bị Guard chặn] [Nhật ký quyết định]            |
+--------------------------------------------------------------------------------+
| Thời gian | Lệnh                       | Nguồn        | Guard    | Hạn   | Hành động          |
| 19:08     | Đặt công suất A07 → 3,5 kW | Cân bằng tải | ✓ Hợp lệ | 04:12 | Chờ cư dân trả lời |
| 19:06     | Xếp xe #31ab vào A03       | Vận hành     | ✓ Hợp lệ | 09:30 | [Duyệt] [Từ chối]  |
+--------------------------------------------------------------------------------+
| Chi tiết: lý do · ảnh hưởng tới cam kết · xe và cư dân (mã giả danh) · phiên bản lịch |
+--------------------------------------------------------------------------------+

Tab "Bị Guard chặn"
| Thời gian | Lệnh              | Nguồn        | Luật vi phạm          |             |
| 19:05     | Bắt đầu sạc A03   | Cân bằng tải | ✕ Bật/tắt liên tục    | [Xem lý do] |
```

**Thành phần tương tác**

| # | Thành phần | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|
| 1 | Thanh tab (ARIA tabs: `role="tablist"`, phím mũi tên, `Home`, `End`) | Đổi tab; ghi tab vào `?tab=` | — | — | — | — | — / T3.6 |
| 2 | Bảng "Chờ duyệt" | Tải khi mở | `GET /operator/approvals?status=pending` | `Approval.approval_id`, `Approval.kind`, `Approval.created_at`, `Approval.command` (`.type`, `.connector_id`, `.power_kw`, `.booking_id`, `.source`, `.issued_by`, `.reason`), `Approval.verdict.passed`, `Approval.expires_at`, `Approval.requested_from`, `Approval.impact_summary` | Mỗi dòng một đề nghị. `kind` = `resident_consent` → cột hành động ghi "Chờ cư dân trả lời", không có nút (chỉ cư dân được quyết). `kind` = `operator_review` → hai nút | — | T1.6 / T3.6 |
| 3 | "Duyệt" / "Từ chối" (ghi chú tuỳ chọn trong khung chi tiết) | Quyết định | `POST /operator/approvals/{approval_id}` · `ApprovalDecisionRequest{decision, note?}` | `Approval.status`, `Approval.decided_at`, `Approval.decided_by` | Bỏ dòng khỏi bảng. Toast "Đã duyệt — xem kết quả thực thi ở Nhật ký" (G10) hoặc "Đã từ chối — hệ thống sẽ tính lại" | 409 `approval_already_decided` → tải lại + toast "Đề nghị đã được xử lý trước đó". 403 → "Chỉ cư dân được trả lời đề nghị này" | T3.2 / T3.6 |
| 4 | Cột "Hạn" (`Countdown`) | Như S4 | — | `Approval.expires_at` | Về 0 → dòng đổi thành "Đã hết hạn — không áp dụng", tải lại | `null` → "—" (G8) | — / T3.6 |
| 5 | Bảng "Bị Guard chặn" | Tải khi mở tab | `GET /operator/commands/blocked?limit=100` | `DecisionLogEntry.timestamp`, `DecisionLogEntry.command`, `DecisionLogEntry.verdict.violations[]` (`Violation.rule`, `Violation.detail`), `DecisionLogEntry.note` | Mỗi dòng: lệnh, nguồn, nhãn luật (mục 1.2) | — | T1.6 / T3.6 |
| 6 | "Xem lý do" | Mở khung chi tiết | — | `Violation.detail` của từng luật, `Command.based_on_schedule_version`, `Command.based_on_state_at`, `Command.issued_by`, `GuardVerdict.checked_at` | Đủ để giải thích vì sao lệnh bị chặn (AC6, US7) | — | — / T3.6 |
| 7 | Bảng "Nhật ký quyết định" | Tải khi mở tab | `GET /operator/decision-log?limit=100` | `DecisionLogEntry.timestamp`, `DecisionLogEntry.command.source`, `DecisionLogEntry.command.issued_by`, `DecisionLogEntry.verdict`, `DecisionLogEntry.approval_id`, `DecisionLogEntry.approved_by`, `DecisionLogEntry.executed`, `DecisionLogEntry.note` | Các cột của FR14: lúc nào · ai hoặc thành phần nào đề xuất · Guard kết luận gì · ai duyệt · có thực thi không. Lọc ở client theo nguồn và kết quả | — | T1.6 / T3.6 |
| 8 | "Tải thêm" (tab 2 và 3) | Lấy trang kế bằng `before` | — | — | **Ẩn** cho tới khi có `DecisionLogEntry.seq` 🆕 G11 | — | T1.6 / T3.6 |
| 9 | Nút "Chi tiết" ở mỗi dòng | Mở khung chi tiết | — | `Command.reason`, `Approval.impact_summary` (cam kết còn giữ không), `Command.booking_id`; xe trên đầu nối xem qua `GET /operator/connectors/{connector_id}` | Khung chi tiết | — | — / T3.6 |

**Trạng thái**

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | skeleton bảng |
| Rỗng | "Không có lệnh nào chờ duyệt" · "Chưa có lệnh nào bị chặn" · "Nhật ký trống" |
| Lỗi | `ErrorPanel` cho từng tab |
| 501 | GET: T1.6; POST: T3.2 |
| Mất realtime | Hỏi lại mỗi 15 giây cho tab đang mở |
| Disabled | Nút duyệt khoá khi đang gửi. Dòng `resident_consent` không có nút |

**Realtime**

| `type` | Cập nhật |
|---|---|
| `approval_request` (`Approval`) | `status` = `pending` → thêm hoặc thay dòng theo `approval_id`, tăng số trên tab. Trạng thái khác → bỏ dòng (cần G9) |
| `command_blocked` (`DecisionLogEntry`) | Thêm vào đầu bảng "Bị Guard chặn". Nếu `Command.command_id` trùng lệnh vừa duyệt → toast "Lệnh đã duyệt nhưng bị Guard chặn khi thực thi" (cách tạm cho G10) |

Nhật ký không có bản tin WS: tải lại khi mở tab và sau mỗi lần duyệt.

**Yêu cầu**: FR12, FR13, FR14, FR16 (hàng chờ duyệt, lệnh bị chặn), US7, AC4 (có log), AC6, MT6.

### 3.4 S8 · Mô phỏng kịch bản — `/operator/simulation`

- **Mục đích**: chạy kịch bản với từng chiến lược A–D, so KPI, bơm sự cố để demo, xuất báo cáo (F7, FR18, US8).
  **Vai trò**: operator. **Viewport**: từ 1024 px.

```text
+--------------------------------------------------------------------------------+
| Mô phỏng kịch bản                                                               |
| ⓘ Kết quả MÔ PHỎNG, không phải số đo của trạm thật. Biểu giá và danh mục xe     |
|   chưa kiểm chứng (verified: false).                                            |
+--------------------------------------------------------------------------------+
| Kịch bản [Trụ A05 hỏng lúc 19:00 (FR18)      ▾]                                  |
|   Như cao điểm tối, nhưng A05 lỗi lúc 19:00 và phục hồi lúc 23:00.              |
| Số xe [30]   Giới hạn (kW) [35]   Seed [42]        (để trống = theo kịch bản)    |
| Chiến lược ( ) A — FCFS   ( ) A — EDF   ( ) B — Tối ưu, không ML                 |
|            (•) C — Tối ưu + dự báo     ( ) D — Oracle                [▶ Chạy]   |
+--------------------------------------------------------------------------------+
| KPI · kịch bản connector_failure | A_fcfs | B     | C     | C so với A_fcfs       |
| MT1 Đúng hạn (mục tiêu ≥ 95%)    | 78% ✕  | 93% ✕ | 96% ✓ | +18 điểm %            |
| MT4 Vượt giới hạn (mục tiêu 0)   | 3 ✕    | 0 ✓   | 0 ✓   |                       |
| …                                                                               |
| ▸ Xem bảng đầy đủ (11 KPI)                      [Xuất CSV] [Xuất JSON]           |
+--------------------------------------------------------------------------------+
| Bơm sự cố vào trạm đang chạy (demo)                                             |
| Loại [Trụ hỏng ▾]   Đầu nối [A05 ▾]   Giới hạn mới (kW) [—]       [Bơm sự cố]   |
+--------------------------------------------------------------------------------+
| ← Dashboard                                                                     |
+--------------------------------------------------------------------------------+
```

**Thành phần tương tác**

| # | Thành phần | Hành động | Endpoint · request | Response dùng | Thành công | Lỗi riêng | Task BE / UI |
|---|---|---|---|---|---|---|---|
| 1 | Kịch bản (`<select>`) | Chọn → điền sẵn số xe, giới hạn, seed | `GET /simulation/scenarios` | `Scenario.scenario_id`, `Scenario.name`, `Scenario.description`, `Scenario.n_vehicles`, `Scenario.power_limit_kw`, `Scenario.seed`, `Scenario.duration_hours`, `Scenario.start_time`, `Scenario.session_source`, `Scenario.incidents[]` (`ScheduledIncident.at_minute`, `ScheduledIncident.type`, `ScheduledIncident.connector_id`, `ScheduledIncident.new_power_limit_kw`) | Mô tả + danh sách sự cố theo giờ, vd "19:00 Trụ hỏng A05" (giờ = `start_time` + `at_minute`) | — | ✅ (cần token) / T3.6 |
| 2 | Số xe, Giới hạn (kW), Seed | Nhập; để trống = giữ giá trị của kịch bản (gửi `null`) | — | — | — | 422 tại `SimulationRunRequest.n_vehicles` (> 0), `SimulationRunRequest.power_limit_kw` (> 0) → báo ở ô | — / T3.6 |
| 3 | Chiến lược (radio) | 5 giá trị `StrategyName`, nhãn ở mục 1.2 | — | — | — | — | — / T3.6 |
| 4 | "▶ Chạy" | Chạy một kịch bản với một chiến lược (đồng bộ) | `POST /simulation/runs` · `SimulationRunRequest{scenario_id, strategy, n_vehicles?, power_limit_kw?, seed?}` | `SimulationRunResult.run_id`, `SimulationRunResult.strategy`, `SimulationRunResult.kpis`, `SimulationRunResult.started_at`, `SimulationRunResult.finished_at`, `SimulationRunResult.notes` | Thêm cột "Lần chạy hh:mm — C" vào bảng; toast "Chạy xong sau n giây" | 404 → "Không có kịch bản này". Chạy lâu → giữ trạng thái chờ, không tự gửi lại (G19) | T1.5 / T3.6 |
| 5 | KpiCompareTable | Tải khi mở | `GET /simulation/benchmark` | `BenchmarkReport.generated_at`, `BenchmarkReport.runs[]` (`SimulationRunResult.scenario_id`, `.strategy`, `.kpis`), `BenchmarkReport.notes` | Cột = các run có cùng `scenario_id` với kịch bản đang chọn + các lần chạy trong phiên (giữ trong state của trang). Hàng theo bảng KPI bên dưới. Cột "so với A_fcfs" tính ở trình duyệt và ghi rõ điều đó | Kịch bản chưa có run nào → "Chưa có bảng đối chứng cho kịch bản này — bấm Chạy" | T3.4 / T3.6 |
| 6 | "Xuất CSV" / "Xuất JSON" | Tạo file ngay ở trình duyệt (`Blob` + `<a download>`), theo 10 §3 | (từ #5 + các lần chạy) | toàn bộ `BenchmarkReport` + lần chạy | File `chargepilot-benchmark-{generated_at}.csv` hoặc `.json` | Không có dữ liệu → nút bị khoá | — / T3.6 |
| 7 | Loại sự cố, Đầu nối, Giới hạn mới | `connector_fault`, `connector_restored` cần đầu nối; `power_limit_change` cần giới hạn mới > 0 (validator của `Incident`) | — | — | Ô không cần cho loại đã chọn thì ẩn | 422 → báo ở ô | — / T3.6 |
| 8 | "Bơm sự cố" | `ConfirmDialog`: "Sự cố sẽ tác động lên trạm mô phỏng đang chạy; cư dân có thể nhận thông báo. Tiếp tục?" | `POST /simulation/incidents` · `Incident{type, connector_id?, new_power_limit_kw?}` | 202 `{status: "accepted"}` | Toast "Đã bơm sự cố" + link "Xem Dashboard"; S5 thấy giới hạn giảm hoặc đầu nối lỗi qua WS | — | T3.5 / T3.6 |

**Hàng của KpiCompareTable**

| Hàng | Field | Mục tiêu (PRD §2) | Đánh dấu |
|---|---|---|---|
| MT1 Tỉ lệ đúng hạn | `KpiReport.on_time_rate` | ≥ 95% | "✓ đạt" / "✕ chưa đạt" |
| MT2 Chờ trung bình | `KpiReport.wait_mean_minutes` | thấp hơn A_fcfs | so với cột A_fcfs |
| MT2 Chờ phân vị 90% | `KpiReport.wait_p90_minutes` | thấp hơn A_fcfs | so với cột A_fcfs |
| Điện thiếu | `KpiReport.unmet_energy_kwh` | — | — |
| Điện đã nạp | `KpiReport.delivered_energy_kwh` | — (để so chi phí ở mức phục vụ tương đương) | — |
| Tỉ lệ phục vụ | `KpiReport.service_rate` | — | — |
| MT3 Chi phí điện | `KpiReport.energy_cost_vnd` | giảm so với A_fcfs và B; con số 15% chưa chốt (PRD §11) | chỉ hiện số và % chênh, không đánh dấu (câu hỏi mở O6) |
| Tải đỉnh | `KpiReport.peak_load_kw` | — | — |
| MT4 Số lần vượt giới hạn | `KpiReport.power_limit_violations` | 0 | "✓ đạt" / "✕ chưa đạt" |
| MT5 Tính lại p95 | `KpiReport.replan_p95_seconds` | ≤ 2 giây | "✓ đạt" / "✕ chưa đạt"; `null` → "—" |
| MT6 Lệnh bị chặn | `KpiReport.blocked_commands` | (đếm) | — |

Ngưỡng MT1, MT4, MT5 là hằng số trong `lib/labels.ts`, có comment trỏ về PRD §2. Web không đọc `eval/thresholds.yaml`, vì
`frontend/src` không được import gì ngoài `frontend/` (ADR-009).

**Trạng thái**

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | `<select>` "Đang tải kịch bản…"; bảng KPI skeleton |
| Rỗng | Không có kịch bản → "Chưa có kịch bản trong config/scenarios", nút Chạy bị khoá. Benchmark rỗng → như #5 |
| Lỗi | `ErrorPanel` cho từng khối |
| 501 | scenarios: 501 T1.7 cho tới khi xong auth; runs: T1.5; benchmark: T3.4; incidents: T3.5 |
| Mất realtime | Không áp dụng: S8 không nghe WS |
| Disabled | "Chạy" khoá khi chưa chọn kịch bản hoặc chiến lược, có ô lỗi, hoặc đang chạy (hiện "Đang chạy… n giây"). "Bơm sự cố" khoá khi thiếu trường. "Xuất" khoá khi chưa có dữ liệu |

**Realtime**: không (20 §3). Bơm sự cố xong thì theo dõi ở S5.

**Yêu cầu**: FR18, FR11 (trạm, xe, nguồn đều là mô phỏng — banner), US6, US8, AC3 (kịch bản `peak_evening`), AC5 (kịch bản
`power_drop`; bơm `power_limit_change`), AC7, MT1–MT6.

### 3.5 S9 · Sơ đồ bãi (vận hành) — `/operator/map` (mới 2026-11-19)

Mockup: [`docs/mockups/van-hanh/operator-map.html`](../mockups/van-hanh/operator-map.html), 3 tình huống:
cao điểm 18:30 (mọi ngân sách chạy đầy), luân chuyển cổng 20:10 (xe đầy nhưng chưa rút), sự cố DC-01-2.

- **Mục đích**: nhìn mặt bằng thật của khu. Phòng điện → đường cấp → vùng AC / DC → tủ → cổng → ô đỗ, cộng hai làn chờ.
  Thấy ngay vùng nào chạm ngân sách, cổng nào giữ xe đã đầy, cổng nào lỗi, xe nào chờ (FR16, US5, ADR-010). S5 trả lời
  câu "bao nhiêu"; S9 trả lời câu "ở đâu".
- **Vai trò**: operator. **Viewport**: từ 1024 px; hẹp hơn thì panel phải xuống dưới sơ đồ.

```text
+--------------------------------------------------------------------------------------+
| Sơ đồ bãi · CP-01 · giờ trạm 18:30                    [Tạm dừng cập nhật] [Hàng đợi] |
| [Lưới 105,3/106 kW ▓▓▓▓] [AC 22/22 kW ▓▓▓▓] [DC 78/78 kW ▓▓▓▓] [4/4 cổng · chờ 2+3]  |
| (banner đỏ khi có cổng lỗi)                                                          |
+-------------------------------------------------------------+------------------------+
| Mặt bằng khu sạc              [Tất cả][Vùng AC][Vùng DC]    | Ô đang chọn: B-D1      |
| ═══ Đường nội khu ═══  ↓Lối vào                   ↑Lối ra   |  DC-01-1 · Giảm c.suất |
| [Phòng điện 105,3/106]  [P01…P13 ô đỗ thường, không sạc]    |  Xe DC-A · 39/60 kW    |
|    │── Vùng AC ──────────┐  ┌── Vùng DC ─────────────────┐  |  Pin 45% → 75%         |
|    │ [Tủ AC-01][Tủ AC-02]│  │      [Tủ DC-01 2 × 60 kW]  │  |  Vì sao: chia đều 78kW |
|    │ [B-A1   ][B-A2   ]  │  │ [B-D1        ][B-D2      ] │  |  [Chi tiết đầu nối]    |
|    └─────────────────────┘  └────────────────────────────┘  +------------------------+
| [Làn chờ AC: 1 AC-C · 2 AC-D] [Làn chờ DC: 1 DC-C · 2 · 3]  | Làn chờ theo vùng      |
| Chú giải · ▸ Bảng số liệu tương đương                       | Sự kiện gần nhất       |
+-------------------------------------------------------------+------------------------+
```

| # | Thành phần | Hành vi | Endpoint | Field |
|---|---|---|---|---|
| 1 | `PowerTiers` (3 thanh + 1 ô) | Lưới, ngân sách AC, ngân sách DC, số cổng có xe. Thanh đổi màu ở 85 % và 100 %; `role="img"` + `aria-label` có số | `GET /operator/station` + 🆕 G23 | `StationOverview.grid_input_kw`, `.grid_input_limit_kw`, `.zones[].output_kw`, `.zones[].budget_kw` |
| 2 | `SiteMap` (ngang) | Mỗi ô là `<g role="button" tabindex="0">`, `aria-pressed` khi chọn. Enter / Space chọn; mũi tên chuyển giữa các ô. `aria-label` đủ: ô, cổng, trạng thái bằng chữ, xe, kW / giới hạn, pin | 🆕 G22 + `GET /operator/station` | `SiteLayout.*`, `StationState.connectors[].status`, `.power_kw`, `.max_power_kw`, `StationState.sessions[]` |
| 3 | Lọc vùng | 3 nút `aria-pressed`. Làm mờ vùng không chọn, không ẩn | — | `ConnectorSpec.zone` |
| 4 | `BayDetail` | Hiện ô đang chọn: trạng thái, tủ / vùng, xe, công suất, pin, giờ đạt mục tiêu, giờ rời, "Vì sao" (lý do giảm hoặc giữ cổng). Nút "Chi tiết đầu nối", "Xếp xe từ làn chờ" (ô trống hoặc đã đầy), "Mở đề nghị chuyển cổng" (ô lỗi) | `GET /operator/connectors/{connector_id}`; nút xếp → `POST /operator/queue/{booking_id}/assign` (đi qua Guard, như S6) | `ConnectorDetail.*`, `Command.reason` |
| 5 | `ZoneQueue` | 2 danh sách FIFO, AC và DC riêng. Mỗi dòng: thứ tự, xe, giờ rời, giờ dự kiến vào cổng | `GET /operator/bookings?status=queued` | `Booking.zone` (T1.10), `QueueStatus.estimated_start` |
| 6 | Sự kiện gần nhất | Dùng chung `EventTicker` của S5; lệnh bị Guard chặn có ⛔ + chữ màu đỏ | `GET /operator/events` | như S5 |
| 7 | Bảng số liệu tương đương | `DataTableFallback` trong `<details>`: 1 dòng mỗi cổng | (từ #2) | như #2 |
| 8 | Tạm dừng cập nhật | Như S5 (R5, WCAG 2.2.2) | — | — |

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | Vẽ khung SVG từ layout trước (G22, layout không đổi theo thời gian); các ô xám "Đang tải" |
| Rỗng | Mọi ô "Trống", làn chờ "Không có xe chờ" |
| Lỗi | Layout lỗi: thay SVG bằng bảng #7. Trạng thái lỗi: giữ layout, ô ghi "Không rõ", kèm `ErrorPanel` |
| 501 | Trước T1.10 / T2.9: `NotImplementedPanel` G22 cho sơ đồ; #1 dùng `power_limit_kw` cũ (một thanh) |
| Mất realtime | Như S5: "Dữ liệu lúc {giờ}", poll 15 giây |
| Disabled | Nút "Xếp xe" khoá khi vùng của ô không có xe chờ |

**Realtime**: `station_snapshot` (ô + tầng công suất), `event`, `command_blocked`.

**Yêu cầu**: FR16, FR7, FR12, AC2, AC5, AC6, US5, ADR-010.

## 4. Gap backend

Mục này chỉ **đề xuất**; spec không sửa code. Mỗi đề xuất chỉ thêm field hoặc endpoint trong `/api/v1` (ADR-008). Làm xong
một mục thì chạy `python scripts/export_openapi.py`, rồi `npm run gen:api` trong `frontend/` (ADR-009), và bỏ cách làm tạm ở UI.

- **P1**: chặn một luồng Must, hoặc một hợp đồng đã chốt ở plan 10 / 20 không làm được như đã viết.
- **P2**: UI có cách làm tạm nhưng mất thông tin hoặc kém tin cậy.
- **P3**: tiện ích hoặc cần làm rõ.

| ID | Mức | Màn | Hiện trạng trong code | Đề xuất | UI làm tạm | Task |
|---|---|---|---|---|---|---|
| G1 | P1 | S3 | `POST /chat/resume` gọi `agent.ainvoke(Command(resume=…))` mà không kiểm thread còn interrupt chờ hay không; mã `no_pending_confirmation` có trong `src/models/api.py` nhưng không nơi nào raise. Đã chạy thử graph thật với LLM giả trên LangGraph 1.2.20 (2026-11-17): thread không còn chờ thì **không lỗi** mà trả 200 `status` = `answer`. (1) Thread không có checkpoint (backend vừa khởi động lại; `MemorySaver` nằm trong RAM, 30 §3.6): graph chạy lại từ `entry` với `query` rỗng và **gọi LLM**; `response` là câu trả lời cho một câu hỏi rỗng. (2) Thread đã xong (bấm lặp, gửi lại): trả lại state cũ, không node nào chạy. Vì vậy đường lui "resume trả 409 → form điền sẵn" của 20 §8 không bao giờ chạy. 500 chỉ xảy ra khi `resume` khác `approve` / `reject` (`ValueError` trong `human_review_node`), vì `ResumeRequest.resume` là `str` | Đầu `chat_resume`: `snapshot = await agent.aget_state(config)`; `snapshot.interrupts` rỗng → `DomainError(ErrorCode.NO_PENDING_CONFIRMATION, …)`. Đã kiểm trên 1.2.20: `interrupts` khác rỗng đúng khi đang chờ (`next` = `("human_review",)`), rỗng ở cả (1) và (2); xong mục rủi ro ở 10 §10. Đổi `ResumeRequest.resume` thành `Literal["approve", "reject"]` để giá trị lạ trả 422 thay vì 500. Test mới: `test_routes.py::test_resume_without_pending_returns_409` | S3 #1: sau `answer`, chỉ báo "Đã đặt lịch" khi `GET /resident/bookings/current` có booking hiệu lực mới (`booking_id` khác `planDraft.booking_id_before`); không có thì chuyển sang form điền sẵn từ `pending`, không hiện `response`. Sau khi làm G1, 409 `no_pending_confirmation` đi cùng nhánh này | T2.5 |
| G2 | P1 | S3 booking | Docstring của `charging_service.change` ghi "Không khả thi → DomainError kèm phương án thay thế (FR4)", và 10 §6.3 vẽ `PATCH` trả "409 kèm phương án thay thế". Nhưng `DomainError` chỉ nhận `code` và `detail`, `ErrorResponse` chỉ có `detail`, `code`, `task_id`, `request_id`, `status`, không chở được `Alternative`; cũng không mã lỗi nào mang nghĩa "không khả thi". Cư dân không xem trước được lịch mới trước khi áp | (a) 🆕 `POST /resident/bookings/{booking_id}/quote` · body `BookingChangeRequest` → `ScheduleProposal`: what-if **thay thế** booking hiện tại, không giữ chỗ (cùng mẫu với quote → book). (b) `PATCH /resident/bookings/{booking_id}` trả 409 `proposal_expired` (mã đã có) khi lúc áp không còn khả thi | PATCH thẳng; gặp 409 thì hiện `detail`, không có phương án thay thế, gợi ý "Huỷ lịch rồi đặt lại" kèm câu "Huỷ sẽ mất chỗ đang giữ" | T2.8 |
| G3 | P2 | S3 chat, form | Yêu cầu đã trích xuất chỉ nằm trong `ChatResponse.pending`, là `dict` không có type, dạng `{tool, args: {request}}` (do `human_review_node` tạo). S3 cần `deadline`, `mode`, `arrival_time` để hiện "Đúng hạn 07:00" và để điền sẵn form | 🆕 `ChatResponse.request: ChargeRequest \| None`, điền khi `pending.tool` = `confirm_booking` | Đọc `pending.args.request`, kiểm kiểu lúc chạy; sai kiểu thì bỏ dòng hạn và để form trống | T2.5, T3.3 |
| G4 | P2 | S3 chat | Sau `resume: "approve"`, lỗi của tool `confirm_booking` (`booking_conflict`, `proposal_expired`) bị `human_review_node` bắt thành chuỗi `TOOL_ERROR`, nên HTTP vẫn 200 với `status` = `answer`. Web không biết lịch đã đặt được chưa | 🆕 `ChatResponse.booking: Booking \| None`, có giá trị khi `confirm_booking` thành công | Gọi lại `GET /resident/bookings/current` ngay sau resume | T3.3 |
| G5 | P2 | S2 | `ChatResponse.proposal` chỉ được điền khi `needs_confirmation`. Khi Agent trả lời một phương án không khả thi (`status` = `answer`), web mất `alternatives` có cấu trúc (FR4) | `_to_chat_response` điền `proposal` từ state (`result["proposal"]`) ở mọi `status` | Chỉ hiện chữ của Agent | T3.3 |
| G6 | P2 | S3 | `Alternative` chỉ có `soc_target` và `deadline` (đều tuỳ chọn): `join_queue` không có tham số nào, `other_time` không có giờ cắm xe mới. Client không dựng được yêu cầu để chấp nhận phương án | 🆕 `Alternative.request: ChargeRequest \| None` — yêu cầu đã chỉnh sẵn, client chỉ việc quote hoặc book lại | `other_time` thay `deadline`, `lower_target` thay `soc_target`; `join_queue` chỉ hiển thị | T2.2 |
| G7 | P2 | S4, S7 | `Approval.command` chỉ có công suất mới (`Command.power_kw`). Không có công suất hiện tại và khung giờ áp dụng mà wireframe S4 hiện ("11 → 7 kW trong 40 phút, 19:10–19:50") | 🆕 `Approval.current_power_kw: float \| None`, `Approval.effective_from`, `Approval.effective_until: AwareDatetime \| None` | Hiện công suất mới + `Command.reason` + `Approval.impact_summary` | T3.2 |
| G8 | P2 | S4, S7 | Thời hạn phê duyệt không có tham số: `expires_at` do `guard.approval.open_approval` đặt, nhưng `config/station.yaml` không có key nào cho việc này (trái ADR-003) | 🆕 khoá `guard.approval_ttl_minutes` trong `station.yaml` + `GuardSettings.approval_ttl_minutes` | `expires_at` là `null` → ẩn đồng hồ | T3.2 |
| G9 | P2 | S4, S7, số trên tab | WS chỉ phát `approval_request` lúc mở đề nghị. Khi đề nghị được quyết hoặc hết hạn thì không có bản tin, nên S7, số "Duyệt lệnh (n)" và S4 không tự cập nhật | Phát lại `approval_request` với `Approval` mới mỗi lần `status` đổi; ghi vào bảng 10 §8, không thêm `type` | Đồng hồ đếm ngược + tải lại khi hết hạn, khi tab được focus lại và sau mỗi thao tác | T3.2, T3.6 |
| G10 | P2 | S4, S7 | `POST /resident/approvals/{approval_id}` và `POST /operator/approvals/{approval_id}` trả `Approval`, không cho biết `execute_approved` (Guard kiểm lần 2) đã áp lệnh hay chặn | 🆕 `Approval.executed: bool \| None` (`null` = chưa xử lý) | S7 so `command_blocked` theo `Command.command_id`; S4 chỉ báo "đã ghi nhận" | T3.2 |
| G11 | P2 | S7 | `GET /operator/commands/blocked` và `GET /operator/decision-log` nhận `before` là con trỏ `seq` (cột `decision_log.seq`, 40 §3), nhưng `DecisionLogEntry` không có `seq`, nên client không lấy được con trỏ cho trang sau | 🆕 `DecisionLogEntry.seq: int \| None`, chỉ đọc, do repository điền | Chỉ hiện trang đầu (`limit=100`), ẩn "Tải thêm" | T1.6 |
| G12 | P2 | S5 | `StationOverview.power_limit_kw` không ghi rõ là giới hạn cấu hình hay hiện hành. `StationState.available_power_kw` là "giới hạn hiện hành". `StationOverview.utilization_pct` là "tải tổng / giới hạn" mà không nói giới hạn nào. AC5 cần thấy giới hạn giảm | Ghi vào docstring: `power_limit_kw` = giới hạn cấu hình (`StationConfig.power_limit_kw`), `available_power_kw` = giới hạn hiện hành, `utilization_pct` tính theo giới hạn hiện hành | Hiện cả hai khi chúng khác nhau | T3.6 |
| G13 | P3 | S2, S3 | Khi `needs_confirmation`, `ChatResponse.response` là chuỗi kỹ thuật "[CẦN PHÊ DUYỆT] {payload}. POST /chat/resume…" | Trả câu dành cho cư dân, dựng từ `proposal` | Bỏ qua `response`, dựng câu ở client | T2.5 |
| G14 | P3 | S5 | `StationState.total_power_kw` là `@property` nên không có trong JSON và OpenAPI | Đổi thành `@computed_field`, hoặc thêm 🆕 `StationOverview.total_power_kw` | Cộng `StationState.connectors[].power_kw`, cùng công thức với property | T3.6 |
| G15 | P3 | S6 | Chưa định nghĩa `GET /operator/schedule?date=` trả gì với ngày quá khứ hoặc tương lai | Trả phiên bản cuối cùng được tạo trong ngày đó (theo giờ trạm); không có thì 404 `not_found` | 404 → "Không có lịch cho ngày này" | T3.6 |
| G16 | P3 | S6 | `GET /operator/bookings?status=` chỉ nhận một giá trị, trong khi S6 cần `queued`, `confirmed` và `charging` | Cho phép lặp tham số `status` (`list[BookingStatus]`) | Gọi không lọc rồi lọc ở client | T3.6 |
| G17 | P3 | S2 | Cư dân không có danh sách đề nghị đang chờ; WS không phát lại, nên tải lại trang là mất banner | 🆕 `GET /resident/approvals?status=pending` → mảng `Approval` của chính cư dân | Suy ra từ `Notification` có `kind` = `approval_request` và chưa đọc | T3.2 |
| G18 | P3 | Thông báo | Không có "đánh dấu tất cả đã đọc" | 🆕 `POST /resident/notifications/read-all` | Không có nút này | T1.6 |
| G19 | P3 | S8 | `POST /simulation/runs` chạy đồng bộ; mô phỏng 24 giờ có thể vượt timeout của hosting | Nếu đo thấy quá 30 giây: trả 202 + 🆕 `GET /simulation/runs/{run_id}` để hỏi kết quả | Chờ, hiện số giây đã chạy, không tự gửi lại | T3.4 |
| G20 | P3 | S3, hồ sơ, S6 | Chưa định mã lỗi cho: `DELETE /resident/bookings/{booking_id}` khi booking đã hết hiệu lực; `PUT /resident/profile` với `vehicle_model` ngoài danh mục; `POST /operator/queue/{booking_id}/assign` khi booking đã rời hàng chờ hoặc đầu nối đang bận | DELETE: trả 200 với trạng thái hiện tại (idempotent). PUT: 422 gắn vào `vehicle_model`. Assign: lệnh vẫn qua Guard, trả `DecisionLogEntry` bị chặn thay vì lỗi HTTP | Hiện `detail`, tải lại dữ liệu | T2.2, T2.8, T3.2 |
| G21 | P3 | S2, header | `UserProfile.vehicle_model` của `GET /auth/me`: claim JWT chỉ có `sub`, `role`, `name`, `iat`, `exp` (ADR-006), nên không rõ giá trị lấy từ đâu; `UserProfile.display_name` giữ tên cũ tới khi đăng nhập lại | `decode_token` đọc bảng `users` để điền, hoặc bỏ field này khỏi `UserProfile` | S2 lấy xe mặc định từ `GET /resident/profile`, chỉ dùng `GET /auth/me` khi cách kia lỗi | T1.7 |

| G22 | P1 | S9 cả hai vai trò | Không có dữ liệu mặt bằng. `ConnectorSpec` chỉ có `connector_id`, `max_power_kw` | 🆕 `config/site_layout.yaml` (ADR-003) + `SiteLayout` (gates, room, zones, cabinets, bays với toạ độ cho khung ngang 1000 × 600 và khung dọc 360 × 640), trả trong `GET /station/config` (field `layout`) hoặc 🆕 `GET /station/layout`. `ConnectorSpec` thêm `cabinet_id`, `zone`, `bay_id` (ADR-010) | Layout cố định trong client, chỉ dùng cho mockup | T1.10, T2.9 |
| G23 | P1 | S5, S9 | `StationOverview` chỉ có một `power_limit_kw` (xem G12), không có tầng vùng / lưới | 🆕 `StationOverview.grid_input_kw`, `grid_input_limit_kw`, `zones: list[ZoneUsage{zone, output_kw, budget_kw}]` | Một thanh duy nhất theo `power_limit_kw` | T1.10, T3.6 |
| G24 | P2 | S9 cư dân | Không endpoint nào cho cư dân xem chiếm dụng của khu, và không được lộ dữ liệu của người khác | 🆕 `GET /resident/site-map` → `ResidentSiteMap{bays[{bay_id, zone, public_status: busy / idle / fault, mine: bool}], queues{AC, DC: {length, my_position}}}`; WS cư dân thêm `type` = `site_occupancy` | Ẩn sơ đồ, chỉ hiện thẻ "Xe của bạn" | T2.9 |

**Không phải gap** (ghi lại để khỏi hỏi lại):

- WebSocket không có trong `openapi.json`: đây là giới hạn của OpenAPI. Payload đều đã có schema (`WS_PAYLOAD_MODELS` trong
  `src/models/events.py`; `frontend/src/lib/ws/types.ts`).
- Không có API lịch sử chat: client giữ bản ghi (R3).
- Không có logout: JWT không giữ trạng thái (ADR-006).
- Số trên chuông: client đếm `Notification.read` sai.
- "Xuất báo cáo" ở S8: làm ở client (10 §3).

## 5. Truy vết yêu cầu → màn → component → test

`＋` = test thêm khi làm task (giữ tên test của 20 §10; tên mới đánh dấu "mới").

| Yêu cầu | Màn | Component | Test |
|---|---|---|---|
| FR1 | S1, cổng vai trò | `LoginForm`, `AuthGate` | ＋ `auth-gate.test.tsx` [T2.7] · ＋ `login-form.test.tsx` (mới: 401 → "sai mật khẩu", không phải "hết phiên") [T2.7] |
| FR2 | S2, form, S3 | `ChatPanel`, `BookingForm`, `ProposalCard` | ＋ `chat-flow.test.tsx` [T3.3] · ＋ `booking-form.test.tsx` (mới: validator, giờ trạm → ISO có offset) [T2.7] |
| FR3 | S3, form, S2 | `ProposalCard`, `BookingForm` | ＋ `proposal-card.test.tsx` (mới: kWh lấy từ `energy`, không lấy từ chữ của LLM) [T2.7] |
| FR4 | S3 (S2 khi có G5) | `ProposalCard` | ＋ `proposal-card.test.tsx` (`feasible` sai → hiện phương án thay thế) [T2.7] |
| FR5 | S2 | `ChatPanel` | ＋ `chat-flow.test.tsx` (`status` = `refused`) [T3.3] |
| FR6 | S6 (hiển thị kết quả tối ưu) | `GanttChart` | ＋ `gantt-chart.test.tsx` (mới: slot → thanh, đầy / giảm) [T3.6] |
| FR7 | S6, S2 (hàng đợi) | `QueueList`, `QueueBadge` | ＋ `queue-badge.test.tsx` [T2.7] |
| FR8 | S3 booking, S6 | `ChangeBookingDialog`, nút "Lập lịch lại" | ＋ `change-booking.test.tsx` (mới) [T2.8] |
| FR9 | Form, S3 | `BookingForm`, `ProposalCard` | ＋ `booking-form.test.tsx` (hạn lấy xe bắt buộc) [T2.7] |
| FR10 | S5 | `KpiBar`, `LoadChart` | ＋ `kpi-bar.test.tsx` (mới: giới hạn hiện hành thấp hơn cấu hình) [T3.6] |
| FR11 | S8, S1 | `SimulationNotice` | — (nội dung tĩnh) |
| FR12 | S5, S6, S7 | `EventTicker`, `ManualAssignForm`, `BlockedTable` | ＋ `blocked-table.test.tsx` [T3.6] |
| FR13 | S4, S7, hồ sơ, form | `ApprovalPrompt`, `ApprovalTable`, `ConsentFields` | ＋ `approval-prompt.test.tsx` [T3.3] |
| FR14 | S7, S4 (ghi log) | `DecisionLogTable` | ＋ `decision-log-table.test.tsx` (mới) [T3.6] |
| FR15 | S2, S3, S4, thông báo | `VehicleCard`, `QueueBadge`, `NotificationList`, `ChatPanel` | `not-implemented.test.tsx` (đã có) [T1.2] · ＋ `vehicle-card.test.tsx` (mới) [T2.7] |
| FR16 (S9) | S9 cả hai vai trò | `SiteMap`, `PowerTiers`, `BayDetail`, `ZoneQueue` | ＋ `site-map.test.tsx` (mới: mỗi ô có trạng thái bằng chữ; chế độ cư dân không render xe / SOC của người khác; phím mũi tên) [T2.9] |
| FR16 | S5, S6, S7 | `ConnectorGrid`, `useStream` | `ws-client.test.ts` (đã có) [T1.2] · ＋ `connector-grid.test.tsx` (mới: trạng thái có chữ) [T3.6] · ＋ `ws-cache.test.ts` (mới: `type` → `setQueryData`) [T3.6] |
| FR17 | S2 (thời gian chờ) | `QueueBadge` | — (chỉ hiển thị số do backend tính) |
| FR18 | S8 | `ScenarioForm`, `KpiCompareTable`, `IncidentForm` | ＋ `kpi-compare.test.tsx` (mới) [T3.6] |
| AC1 | S2 → S3 | `ChatPanel`, `ProposalCard` | ＋ `chat-flow.test.tsx` [T3.3] |
| AC2 | S2, S3, S6 | `QueueBadge`, `QueueList` | ＋ `queue-badge.test.tsx` [T2.7] |
| AC3 | S8 (kịch bản `peak_evening`) | `KpiCompareTable` | ＋ `kpi-compare.test.tsx` [T3.6] |
| AC4 | S4, S7, thông báo | `ApprovalPrompt`, `Countdown` | ＋ `approval-prompt.test.tsx` (hết hạn không tự áp dụng) [T3.3] · ＋ `countdown.test.tsx` (mới) [T3.3] |
| AC5 | S5, S8, thông báo | `KpiBar`, `IncidentForm`, `NotificationList` | ＋ `kpi-bar.test.tsx` [T3.6] |
| AC6 | S5, S6, S7 | `BlockedTable`, `EventTicker`, `ManualAssignForm` | ＋ `blocked-table.test.tsx` [T3.6] |
| AC7 | S8 | `KpiCompareTable` (xuất báo cáo) | ＋ `kpi-compare.test.tsx` (CSV) [T3.6] |
| AC8 | S1 | `LoginForm` | kiểm tay trên live URL [T4.4] |
| US1 | S2, form, S3 | `ChatPanel`, `BookingForm` | như FR2 |
| US2 | S2, S3 | `QueueBadge` | như AC2 |
| US3 | S2 ("Vì sao?"), S3 | `VehicleCard`, `ProposalCard` | ＋ `vehicle-card.test.tsx` |
| US4 | S4, thông báo, hồ sơ | `ApprovalPrompt`, `ConsentFields` | như AC4 |
| US5 | S5 | `KpiBar`, `ConnectorGrid` | như FR16 |
| US6 | S6, S8 | `GanttChart`, `IncidentForm` | như FR6 |
| US7 | S7 | `ApprovalTable`, `BlockedTable` | như AC6 |
| US8 | S8 | `KpiCompareTable` | như FR18 |
| NFR khả dụng | S1 (banner), S2 và S3 (nút sang form), form | `BackendStatusBanner`, `BookingForm` | `api-client.test.ts` (đã có) [T1.2] |
| NFR riêng tư | S2 (không biển số), hồ sơ | `ProfileForm` | ＋ `profile-form.test.tsx` (mới) [T2.8] |
| WCAG 2.1 AA | toàn app | mục 1.8 | dùng thử bằng bàn phím và trình đọc màn hình [T4.3] |

## 6. Câu hỏi mở

| # | Câu hỏi | Mặc định trong spec | Ai trả lời |
|---|---|---|---|
| O1 | Cư dân bỏ chọn `ConsentScope.emergency_curtailment` thì sao? PRD FR13 dòng 2 ghi "cư dân cho phép trước khi đăng ký", và cơ chế FR13 đang chờ BTC xác nhận | Checkbox vẫn hiện, kèm câu giải thích; client không chặn; backend quyết (có thể từ chối đặt lịch) | BTC, qua nhóm |
| O2 | G12: `power_limit_kw` là giới hạn cấu hình hay hiện hành? | Hiện cả hai khi khác nhau | TV3 |
| O3 | Q3: "≤ 2 giây" của AC1 có tính độ trễ LLM không? | UI không đo; ProposalSummary hiện ngay khi có response | mentor |
| O4 | Q12: một lần xác nhận ở S3 cho cả dữ liệu trích xuất lẫn phương án có đúng ý FR2 không? | Theo mặc định của plan: một lần, ở S3 | mentor |
| O5 | Một cư dân có nhiều xe không? `ResidentProfile.vehicle_model` chỉ chứa một xe | Một xe mặc định; ở form vẫn chọn được xe khác | nhóm |
| O7 | S9 cư dân: có nên hiện vị trí trong làn chờ của người khác (ẩn danh "Xe") không? | Chỉ hiện số xe và vị trí của mình; các ô khác ghi "Xe" | nhóm |
| O8 | Toạ độ layout lấy theo bãi thật của khu hay bãi minh hoạ? | Bãi minh hoạ trong `site_layout.yaml`, ghi rõ "mô phỏng" như FR11 | nhóm, mentor |
| O6 | Ngưỡng "đạt" cho chi phí (MT3: 15%?), vì PRD §11 chưa chốt cách nói | Chỉ hiện số tuyệt đối và % chênh so với A_fcfs, không đánh dấu đạt / chưa đạt | nhóm |

## 7. Tự kiểm

Chạy ngày 2026-11-17 trên đúng bản này, bằng một script tạm (không đưa vào repo). Đã thử script trên một bản sao có cài
sẵn lỗi (endpoint sai, field sai, mã lỗi lạ, task lạ, Gxx lạ, tỉ lệ sai, thiếu nhãn enum): bắt đủ.

| # | Kiểm | Kết quả |
|---|---|---|
| E1 | Mọi `METHOD /path` có trong `frontend/openapi.json`, hoặc gắn 🆕 Gxx và được khai ở mục 4. `WS /ws/operator`, `WS /ws/resident` có trong `src/api/ws.py` | Không lỗi trên 153 lần nhắc. 4 endpoint 🆕 (G2, G17, G18, G19). Thao tác OpenAPI không màn nào dùng: `GET /status`, `GET /ready` |
| E2 | Mọi `Model.field` (kể cả `.field` viết tắt đi ngay sau trên cùng dòng) có trong `components.schemas` | Không lỗi trên 341 lần tham chiếu. Field chưa có trong schema chỉ nằm trên dòng có 🆕 Gxx và đều được khai ở mục 4 |
| E3 | Mã lỗi đi sau mã HTTP thuộc `ErrorCode` hoặc 3 mã của web; bảng nhãn ở mục 1.1–1.2 phủ mọi giá trị enum; ma trận ở mục 1.6 có đủ `ErrorCode` | Không lỗi: 29 mã lỗi; 65 giá trị của 15 enum; đủ 13 giá trị `ErrorCode` |
| E4 | Mọi task ID có trong bảng 00 §4 | Không lỗi: 16 task ID |
| E5 | FR1–FR18, AC1–AC8, US1–US8 đều xuất hiện; các FR có bề mặt UI (FR1–5, FR8–10, FR12–16, FR18) nằm trong ít nhất một mục màn hình | Đủ 34 mã. Cả 18 FR đều nằm trong mục 2–3, kể cả FR6, FR7, FR11, FR17 (chỉ thể hiện gián tiếp) |
| E6 | Link tương đối trỏ tới file có thật. `scripts/check_docs.py` chỉ quét `docs/guide/` nên không phủ file này | 4 link, không gãy. `check_docs.py` vẫn PASS (50 file, 131 link) |
| E7 | Tỉ lệ tương phản ghi ở mục 1.1 khớp công thức WCAG 2.1 | 30 cặp, không lệch. Cặp duy nhất dưới 3:1 là viền ô nhập hiện tại (2,58), đã ghi "không đạt" |
| E8 | Bảng 0.2 khớp task trong `NotImplementedError` của service mà từng router gọi | 40 thao tác router, không lệch |
| — | Mọi bảng markdown đúng số cột | 53 bảng, không lệch |
| — | Gxx được nhắc đều có định nghĩa ở mục 4; gap nào cũng được ít nhất một màn nhắc tới | 21 gap, không thiếu |
| — | Duyệt lại sau khi sửa G1, G2 và S3 (2026-11-17): chạy lại E1, E5, số cột bảng, Gxx và `Model.field` ngoài dòng 🆕 (đếm khác cách của E2); chạy `check_docs.py`. Hành vi của `POST /chat/resume` ghi ở G1 được kiểm bằng script chạy graph thật với LLM giả (không đưa vào repo) | Không lỗi: 153 lần nhắc endpoint, 290 tham chiếu field, 53 bảng, 21 gap; `check_docs.py` PASS |

Kiểm lại nhanh E1 và E5 sau khi backend đổi hợp đồng: chạy ở repo root (lưu thành file tạm, không commit).

```python
import json, re

spec = open("docs/plan/21-ui-spec.md", encoding="utf-8").read()
api = json.load(open("frontend/openapi.json", encoding="utf-8"))
ops = {(m.upper(), p) for p, d in api["paths"].items() for m in d}
ws = set(re.findall(r'websocket\("([^"]+)"', open("src/api/ws.py", encoding="utf-8").read()))
gap = spec.split("## 4. Gap backend")[1].split("## 5.")[0]
for line in spec.splitlines():
    for method, path in re.findall(r"\b(GET|POST|PUT|PATCH|DELETE|WS) (/[\w{}\-/.]+)", line):
        path = path.rstrip(".")
        if method == "WS":
            ok = path in ws
        else:
            full = path if path.startswith(("/health", "/ready")) else "/api/v1" + path
            ok = (method, full) in ops or ("🆕" in line and f"{method} {path}" in gap)
        if not ok:
            print("KHÔNG CÓ:", method, path)
need = [f"{p}{i}" for p, n in (("FR", 18), ("AC", 8), ("US", 8)) for i in range(1, n + 1)]
print("Thiếu FR/AC/US:", [r for r in need if not re.search(rf"\b{r}\b", spec)])
```
