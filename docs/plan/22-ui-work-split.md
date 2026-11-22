# Plan 22 — Chia việc giao diện: 2 người, 2 ngày, 11 màn

> **Cập nhật 21/11/2026 theo [ADR-010](../adr/ADR-010-bai-hybrid-ac-dc.md)…[ADR-015](../adr/ADR-015-pham-vi-mvp4-va-quy-tac-bang-chung.md).**
> Bãi không còn là 8 đầu nối × 7 kW / giới hạn 35 kW: số cổng, ID đầu nối, công suất từng cổng và giới hạn **lấy từ
> API** (fixture nền 4 cổng: 2 AC 11 kW + 1 tủ DC 2 cổng 60 kW, ADR-010). ID kiểu A01–A08, A07 và số 35 kW / 7 kW còn
> trong wireframe ASCII là minh hoạ của bản cũ, không hardcode. Phạm vi MVP-4 thêm **màn Copilot WHY / WHAT-IF**
> (vận hành; cư dân chỉ với xe của mình; WHAT-IF luôn hiện "chưa áp dụng") và **thẻ đề nghị AI-1** (Proposal / HITL:
> đồng ý / từ chối, hết hạn thì không áp dụng) — [ADR-014](../adr/ADR-014-decision-trace-counterfactual-hitl.md);
> spec chi tiết chưa viết. Nội dung dưới đây không viết lại.

> Đầu vào: [21-ui-spec.md](21-ui-spec.md) (đặc tả từng màn) và mockup HTML trong `docs/mockups/`.
> Phạm vi: **code giao diện** trong `frontend/`. Không đổi backend, không đổi `openapi.json`.
> Ngày mặc định: Ngày 1 = T4 18/11/2026, Ngày 2 = T5 19/11/2026. Sửa lại nếu nhóm chọn ngày khác.

## 1. Mục tiêu khi hết Ngày 2

Mở được 11 route và thấy đúng bố cục của mockup. Mỗi khối hiện đủ các trạng thái trong bảng "Trạng thái" của spec:
đang tải, rỗng, lỗi, 501, mất realtime, disabled.

- Endpoint ✅ chạy với dữ liệu thật: `GET /vehicles`, `/tariff`, `/station/config`, `POST /energy/estimate`, `/health`.
- Khối gặp 501 hiện `NotImplementedPanel` kèm task ID (spec §1.9).
- Trạng thái có dữ liệu được kiểm bằng fixture có type trong vitest (`satisfies components["schemas"][…]`).

**Không** thuộc 2 ngày này:
- Nối API thật cho các endpoint 🧩: làm dần khi backend xong T1.7, T2.2, T3.6… Phần UI đã sẵn nên chỉ còn bỏ fixture.
- Xử lý WebSocket theo từng `type` (spec §1.7): làm cùng T3.6.
- Các gap 🆕 G1–G21: UI dùng cách làm tạm đã ghi ở spec §4.
- Dùng thử với người dùng và trình đọc màn hình: thuộc T4.3.

## 2. Ước lượng và mức độ rủi ro

Ước lượng tổng khoảng **32,5 giờ code**, trong khi 2 người × 2 ngày × 8 giờ = 32 giờ. Còn phải trừ khoảng 2 giờ mỗi
người cho review chéo và merge ở các mốc. Vì vậy kế hoạch **chỉ vừa khít khi sẵn sàng cắt theo mục 6**.

| Người | Phần | Giờ |
|---|---|---|
| Dev A | Nền tảng A + 7 màn cư dân | ~16,5 |
| Dev B | Nền tảng B + 4 màn vận hành | ~16 |

Hai phần nặng như nhau theo hai kiểu khác nhau. Màn cư dân nhiều nhưng nhẹ, có nhiều form và luồng chat. Màn vận hành ít
nhưng mỗi màn nặng hơn: biểu đồ, Gantt, bảng nhiều tab.

## 3. Chuẩn bị trước — Ngày 0 (chiều tối 17/11)

| Việc | Ai | Xong khi |
|---|---|---|
| Duyệt mockup S2 [`docs/mockups/cu-dan/resident.html`](../mockups/cu-dan/resident.html) | nhóm | Chốt hướng thiết kế |
| Sinh mockup 10 màn còn lại theo cùng khung | Claude | Đủ 11 file trong `docs/mockups/` |
| Pull `develop`, `npm ci`, `npm run dev` chạy được | A, B | Mở `http://localhost:3000` |
| Đọc spec §1 (nền tảng chung) + phần màn của mình | A, B | — |

Nếu mockup chưa xong sáng Ngày 1 thì vẫn bắt đầu được: buổi sáng chỉ làm nền tảng, chưa cần mockup.

## 4. Lịch theo buổi

### Ngày 1

| Buổi | Dev A — Cư dân | Dev B — Vận hành |
|---|---|---|
| Sáng (4 giờ) | **Nền tảng A** (branch `feature/ui-foundation-a`): token §1.1 vào `@theme` của `globals.css` + đổi viền ô nhập sang `--color-border-input` · `lib/format.ts` + test · `lib/labels.ts` · `StatusBadge` · `RoleShell` cư dân (chuông + menu ☰) · `LiveAnnouncer` + `Toast` | **Nền tảng B** (branch `feature/ui-foundation-b`): `QueryBoundary` (từ `EndpointBlock`, R6) · `lib/api/mutations.ts` (`useApiMutation`) · prop `compact` cho `NotImplementedPanel`, prop `messages` cho `ErrorPanel` · `ConfirmDialog` · `Countdown` · `RoleShell` vận hành (tab + số chờ duyệt) · thư mục `src/test/fixtures/` |
| 11:30 | **Mốc 1**: review chéo, merge cả hai nhánh nền tảng vào `develop`, rồi cả hai rebase | ← |
| Chiều (4 giờ) | **S1** `/login` (0,5 giờ: thông điệp 401, `logoutReason`, nút Hiện/Ẩn) · **S2** `/resident` (3,5 giờ: `VehicleCard`, `QueueBadge`, `ChatPanel` 3 nhánh `status`, `CheapHourChips`, ApprovalBanner) | **S5** `/operator`: `KpiBar`, `LoadChart` (cài `recharts`, đã duyệt ở D6), `ConnectorGrid` + `ConnectorDialog`, `EventTicker`, nút tạm dừng cập nhật |
| 17:30 | **Mốc 2**: demo nhanh S1, S2, S5, mỗi người 5 phút; PR từng màn | ← |

### Ngày 2

| Buổi | Dev A — Cư dân | Dev B — Vận hành |
|---|---|---|
| Sáng (4 giờ) | **S3** `/resident/plan`, 3 chế độ chat / form / booking: `ProposalCard`, `ChangeBookingDialog`, huỷ lịch qua `ConfirmDialog` | **S6** `/operator/schedule`: `GanttChart` (CSS grid 8 × 96), `QueueList`, `ManualAssignForm`, nút "Lập lịch lại" |
| 12:00 | **Mốc 3**: merge S1, S2, S3, S5, S6 | ← |
| Chiều (4 giờ) | **Form đặt lịch** `/resident/book` (`BookingForm`, giờ trạm → ISO có offset) · **S4** `/resident/notifications/[approvalId]` (`ApprovalPrompt` + `Countdown`) · **Thông báo** (`NotificationList`) · **Hồ sơ** (`ProfileForm`, `ConsentFields`) | **S7** `/operator/approvals`, 3 tab ARIA: `ApprovalTable`, `BlockedTable`, `DecisionLogTable` · **S8** `/operator/simulation`: `ScenarioForm`, `KpiCompareTable` (xuất CSV), `IncidentForm` |
| 16:30 | **Mốc 4**: `make web-check` xanh trên `develop`; mở 11 route kiểm DoD; liệt kê phần chuyển sang hôm sau | ← |

## 5. Quy tắc làm chung để không đụng nhau

- **Sở hữu file dùng chung.** Muốn sửa file của người kia thì nhắn trước, hoặc mở PR nhỏ riêng.

  | File | Chủ |
  |---|---|
  | `globals.css`, `lib/format.ts`, `lib/labels.ts`, `StatusBadge`, `LiveAnnouncer` | A |
  | `QueryBoundary`, `lib/api/mutations.ts`, `ErrorPanel`, `NotImplementedPanel`, `ConfirmDialog`, `Countdown`, `src/test/fixtures/` | B |
  | `RoleShell` | Mỗi người sửa nhánh vai trò của mình. Merge Mốc 1 trước khi làm màn |

- **Branch:** `feature/ui-<màn>` tách từ `develop` (vd `feature/ui-s2-resident-home`). Commit dạng
  `feat(frontend): …`, không `--no-verify`, mở công cụ AI ở repo root.
- **Một PR một màn**, kèm ảnh chụp trạng thái chính và trạng thái 501. Người kia review trong 30 phút.
- **Không thêm dependency** ngoài `recharts` (spec §1.5). Không dùng thư viện icon, date picker, Gantt hay toast.
- **Không gõ tay DTO.** Lấy kiểu từ `components["schemas"]` (ADR-009).
- Gặp chỗ spec không nói: theo mockup. Mockup cũng không nói: ghi vào PR mục "❓ giả định", không tự thêm tính năng.

## 6. Thứ tự cắt khi trễ

Cắt từ trên xuống. Phần bị cắt chuyển sang Ngày 3 hoặc gộp vào T4.3.

1. `DataTableFallback` (bảng số liệu tương đương cho biểu đồ và Gantt): tạm dùng `aria-label` tóm tắt.
2. Tooltip của `LoadChart` và Gantt khi focus bằng bàn phím (1.4.13).
3. Hồ sơ `/resident/profile`: backend còn 501 `T2.8`, chưa ai dùng được.
4. Tab "Nhật ký quyết định" của S7: chỉ để `NotImplementedPanel`.
5. Xuất CSV ở S8.

**Không cắt:** S2 → S3 (AC1), S4 không tự áp dụng khi hết hạn (AC4), `BlockedTable` (AC6), panel 501 trên mọi khối, nhãn chữ
cho trạng thái đầu nối (WCAG 1.4.1).

## 7. Definition of Done của mỗi màn

- [ ] Bố cục và chữ khớp mockup ở 360 px (cư dân) hoặc 1280 px (vận hành); không cuộn ngang ở 320 px (cư dân).
- [ ] Mọi hàng của bảng "Thành phần tương tác" trong spec có trên UI, gọi đúng endpoint qua `api` + `unwrap`.
- [ ] Mọi hàng của bảng "Trạng thái" hiện đúng (kiểm bằng fixture hoặc bằng backend hôm nay).
- [ ] Mở trên backend thật hôm nay: khối 🧩 hiện 501 kèm task ID, phần còn lại vẫn dùng được.
- [ ] Thao tác được bằng bàn phím, focus thấy rõ, mỗi trang có đúng một `<h1>` và `<title>` theo spec §1.4.
- [ ] Test của màn trong spec §5 đã viết (ít nhất test ghi `[T2.7]`, `[T3.3]`, `[T3.6]` cho màn đó).
- [ ] `npm run lint`, `npx tsc --noEmit`, `npm test`, `npm run build` xanh.

## 8. Bảng giao việc

| Màn | Route | Mockup | Spec | Người | Buổi | Giờ | Test bắt buộc |
|---|---|---|---|---|---|---|---|
| Nền tảng A | — | — | §1.1–1.4 | A | N1 sáng | 4 | `format.test.ts` (mới) |
| Nền tảng B | — | — | §1.5–1.6 | B | N1 sáng | 4 | `query-boundary.test.tsx` (mới) |
| S1 Đăng nhập | `/login` | [`login.html`](../mockups/login.html) | §2.1 | A | N1 chiều | 0,5 | `login-form.test.tsx` |
| S2 Trang chủ | `/resident` | [`cu-dan/resident.html`](../mockups/cu-dan/resident.html) | §2.2 | A | N1 chiều | 3,5 | `vehicle-card.test.tsx`, `queue-badge.test.tsx` |
| S3 Xác nhận lịch | `/resident/plan` | [`cu-dan/resident-plan.html`](../mockups/cu-dan/resident-plan.html) | §2.3 | A | N2 sáng | 4 | `chat-flow.test.tsx`, `proposal-card.test.tsx` |
| Đặt lịch bằng form | `/resident/book` | [`cu-dan/resident-book.html`](../mockups/cu-dan/resident-book.html) | §2.4 | A | N2 chiều | 1,5 | `booking-form.test.tsx` |
| Thông báo | `/resident/notifications` | [`cu-dan/resident-notifications.html`](../mockups/cu-dan/resident-notifications.html) | §2.5 | A | N2 chiều | 0,5 | — |
| S4 Đề nghị điều chỉnh | `/resident/notifications/[approvalId]` | [`cu-dan/resident-approval.html`](../mockups/cu-dan/resident-approval.html) | §2.6 | A | N2 chiều | 1,5 | `approval-prompt.test.tsx`, `countdown.test.tsx` |
| Hồ sơ | `/resident/profile` | [`cu-dan/resident-profile.html`](../mockups/cu-dan/resident-profile.html) | §2.7 | A | N2 chiều | 1 | `profile-form.test.tsx` |
| S5 Dashboard | `/operator` | [`van-hanh/operator.html`](../mockups/van-hanh/operator.html) | §3.1 | B | N1 chiều | 4 | `kpi-bar.test.tsx`, `connector-grid.test.tsx` |
| S6 Hàng đợi & lịch | `/operator/schedule` | [`van-hanh/operator-schedule.html`](../mockups/van-hanh/operator-schedule.html) | §3.2 | B | N2 sáng | 4 | `gantt-chart.test.tsx` |
| S7 Duyệt lệnh | `/operator/approvals` | [`van-hanh/operator-approvals.html`](../mockups/van-hanh/operator-approvals.html) | §3.3 | B | N2 chiều | 2 | `blocked-table.test.tsx`, `decision-log-table.test.tsx` |
| S8 Mô phỏng | `/operator/simulation` | [`van-hanh/operator-simulation.html`](../mockups/van-hanh/operator-simulation.html) | §3.4 | B | N2 chiều | 2 | `kpi-compare.test.tsx` |

Mockup dùng chung một template từ 2026-11-19: cư dân ở `docs/mockups/cu-dan/` (7 màn), vận hành ở `docs/mockups/van-hanh/` (5 màn, bố cục theo nhánh `buivanlam`), đăng nhập ở `docs/mockups/login.html`. Toàn cảnh ở [`docs/mockups/index.html`](../mockups/index.html). Bộ Figma cũ (`_figma/`, `design-system.html`) đã bỏ; Figma SVG của cư dân ở `cu-dan/figma/`.

## 9. Cập nhật 2026-11-19 (chờ nhóm duyệt)

Nguồn: 00 §12 (C2–C5), 21 §0.5, §2.8, §3.5. Bảng mục 8 giữ nguyên route và test; chỉ đổi **mockup tham chiếu** và thêm S9.

| Thay đổi | Dev | Việc cụ thể | Giờ thêm |
|---|---|---|---|
| Mockup cư dân đổi sang bộ `cu-dan` | A | Dựng 6 màn cư dân theo [`cu-dan/`](../mockups/cu-dan/HUONG-DAN.md) thay cho `resident*.html`. Khung trang: sidebar trên máy tính + thanh điều hướng dưới trên điện thoại (21 §0.5). Font Be Vietnam Pro qua `next/font/local` | +2 (khung trang mới) |
| Vận hành lấy nhánh `buivanlam` làm nền | B | Merge `origin/buivanlam` vào `develop` qua PR (`876607b`, `d77e628`). Thay hằng `DEFAULT_CONNECTORS` / "35 kW" bằng dữ liệu API. Sửa viền ô nhập sang `--line-input` (21 §1.1) | +2 |
| Token "Forest & Amber" | A | `globals.css` lấy theo nhánh `buivanlam` (cùng token với `cu-dan`); bỏ bảng token xanh dương ở 21 §1.1 | 0 (thay cho việc token cũ) |
| **S9 vận hành** `/operator/map` | B | `SiteMap` (SVG, bố cục ngang), `PowerTiers`, `BayDetail`, `ZoneQueue`; tab "Sơ đồ bãi" trong `RoleShell`. Mockup [`van-hanh/operator-map.html`](../mockups/van-hanh/operator-map.html) | +4 |
| **S9 cư dân** `/resident/map` | A | Dùng lại `SiteMap` (bố cục dọc, `privacy`), thẻ "Xe của bạn", cổng còn trống, đường đi. Mockup [`cu-dan/resident-map.html`](../mockups/cu-dan/resident-map.html) | +2 |
| Test | A + B | `site-map.test.tsx`: trạng thái bằng chữ, chế độ cư dân không có dữ liệu người khác, phím mũi tên | +1 |

- Phần thêm khoảng **11 giờ**, nên không vừa 2 ngày cũ (đã kín 32,5 / 32 giờ). Đề xuất xếp thành **Ngày 3**: sáng B
  merge `buivanlam` + S9 vận hành, A làm khung trang `cu-dan`; chiều A làm S9 cư dân, cả hai viết test và review chéo.
- `SiteMap` là component **dùng chung**, B làm chủ (bản ngang làm trước). A thêm bố cục dọc qua prop `layout` và
  `privacy`, không tách component riêng.
- Cho tới khi xong G22–G24 (T1.10, T2.9), S9 dựng bằng fixture có type giống mục 1, layout lấy từ
  `docs/mockups/cu-dan/assets/site-map.js` (`LAYOUTS`). Khi có API thì bỏ fixture.
- **Không cắt** ở S9: nhãn chữ cho trạng thái ô (WCAG 1.4.1), lọc dữ liệu riêng tư cho bản cư dân. Có thể cắt: lọc vùng,
  "Đường tới chỗ của bạn", bảng số liệu tương đương.
