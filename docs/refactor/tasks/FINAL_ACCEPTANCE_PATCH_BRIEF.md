# Brief — Nhóm patch cuối trước khi đóng băng baseline Unified Core (Final Acceptance 2026-11-24)

Nguồn: review Final Acceptance của Tech Lead trên mirror `b9a6668` (= P-019 `3e47d13`), đã chấp nhận kiến trúc,
registry, DC model, observation interface, fork isolation, strict-incidents. Điều phối: claude chính (gộp + nghiệm thu +
tài liệu + đóng băng baseline). Gốc nhánh: `feature/unified-core` HEAD.

Đọc trước: `CLAUDE.md`, `docs/refactor/FINAL_REVIEW_FIX_REPORT.md`, `FINAL_REVIEW_FIX_A_REPORT.md`,
`FINAL_REVIEW_FIX_B_REPORT.md`, `docs/refactor/tasks/FINAL_REVIEW_FIX_BRIEF.md` (luật bất biến + cổng kiểm vẫn áp
dụng, trừ ngoại lệ ghi dưới đây), `tests/test_architecture.py`.

## Phân công

| Nhánh | Người | Việc |
|---|---|---|
| `feature/unified-core-accept-b` | claude3 | §1 P0 Safety event delivery · §2 P1 Admission consistency |
| `feature/unified-core-accept-a` | claude2 | §3 P1 Config parity + provenance · §4 P2 Xoá hardcode + hoàn thiện isolation |

Không làm: tài liệu chung (`CLAUDE.md`, ADR, `FINAL_MAP`, `README`, `PROJECT_STATE.md` — điều phối làm); thuật toán
MVP-3.5, observation noise thật, BMS V / I, uncertainty-aware scheduling, QoS coordinator, AI-4; đổi objective / tham
số solver / vật lý gốc; kiến trúc mới không cần thiết; distributed locking.

## Luật bất biến (như brief trước) + ngoại lệ

- Baseline policy đóng băng B0 / M2b / M3a / M3b không đổi; AST 114 SAME; golden simulator 0 unexpected; evidence cũ
  không sửa; test cũ không đổi assertion (buộc phải đổi ⇒ ESCALATION + lý do trong báo cáo); API chỉ thêm.
- **Ngoại lệ được duyệt:** `guard.after_apply_failsafe: true` mặc định trong `config/station.yaml` (§1). Benchmark backend
  so baseline 2026-11-24 phải vẫn 0 problems; nếu lệch thì giải thích từng run bằng log.
- Commit nhỏ, mỗi patch một commit độc lập, `type(scope): mô tả` tiếng Việt, KHÔNG trailer Co-Authored-By / Claude-Session.

## Nhánh B — claude3

**§1 P0 Safety event delivery**
1. Bật `guard.after_apply_failsafe: true` mặc định (config vận hành). Test cũ dựa trên `false` giữ bằng cách truyền
   tường minh, không sửa assertion.
2. Mọi consumer gọi `rt.sync_clock()` (vd. `quote`, `book`, `change`, `session_view`, `queue_status`, … — tìm hết bằng
   grep) không được bỏ event trả về: event phải tới `control_loop` / `event_bus` (đặc biệt `hard_limit_violated`,
   `CHARGE_COMPLETED`). Một đường dùng chung (vd. helper đồng bộ đồng hồ + đẩy event) thay vì sửa rải rác.
3. Catch-up nhiều phút (`sync_clock` / `advance` qua nhiều phút): sau vi phạm cứng vật lý, KHÔNG tiếp tục tích phân các
   phút còn lại khi chưa xử lý an toàn — dừng ở phút vi phạm, trả event, để fail-safe xử lý rồi mới chạy tiếp.
4. Xác minh `emergency.curtail_to_hard_limits` đưa trạm về trong mọi trần (test). Phân biệt **aggregate power
   violation** (tủ / vùng / lưới — xử lý bằng giảm tải) với **lỗi charging model / acceptance / SOC** (giảm tải không
   sửa được — vd. ngắt cổng / đánh dấu fault / báo vận hành, ghi rõ loại vi phạm trong event + trace).
5. Giữ toàn bộ partial-batch safety tests; thêm test: event phát sinh từ đường đọc (quote / session_view …) tới được
   fail-safe; catch-up nhiều phút dừng đúng ở phút vi phạm; lỗi không xử lý được bằng giảm tải thông thường.

**§2 P1 Admission consistency**
1. `change` dùng optimistic concurrency tương đương `book` (admission ngoài khoá, commit dưới `booking_lock`, kiểm lại
   version, chạy lại có giới hạn / `PROPOSAL_EXPIRED`).
2. `change` / `cancel`: kiểm lại trạng thái booking dưới khoá (booking đã huỷ / kết thúc không được "sống lại" do
   `change` ghi đè; `cancel` hai lần đồng thời chỉ một lần đổi trạng thái + một event).
3. Bảo vệ admission trước thay đổi nguồn / cổng (power limit, fault, connector) hoặc trạng thái planning quan trọng
   giữa snapshot và commit (vd. đưa vào version / fingerprint được kiểm khi commit).
4. Consent: `book` và `change` chạy admission trên consent thật của booking; `quote` / `quote` đổi lịch chưa có consent
   cuối ⇒ thể hiện rõ giả định consent trong `ScheduleProposal` (trường / assumption có sẵn), không âm thầm.
5. Test: concurrent book / change / cancel; power-limit change trong lúc admission.
6. Không giữ runtime lock suốt rollout. Ghi rõ giới hạn single-worker (docstring + báo cáo), chưa làm distributed lock.

## Nhánh A — claude2

**§3 P1 Config parity + experiment provenance**
1. `build_sim_runtime()` (và mọi đường dựng runtime benchmark / admission / live) truyền đúng optimizer parameters như
   runtime live.
2. Một **resolved experiment configuration** tường minh cho mỗi policy / run (policy id + version, component ids +
   versions, parameters, DC model, `TimeConfig`, config fingerprint = hash ổn định của cấu hình đã resolve).
3. Ghi các trường đó vào evidence / report benchmark (trường mới, tuỳ chọn) và manifest.
4. Test non-default parameters: cùng policy + config ⇒ cùng kết quả ở backend live, benchmark và admission trong cùng
   điều kiện.
5. Phân biệt KPI "tổng công suất lấy mẫu vượt giới hạn" với hard physical violations thực tế từ kernel
   (`applied_constraint_violation_count`) — hai trường riêng, tên rõ.

**§4 P2 Xoá hardcode + hoàn thiện isolation**
1. Frontend S8 (`frontend/src/app/operator/simulation/page.tsx`) lấy policy options từ `GET /api/v1/simulation/policies`,
   gửi `policy_id`; thêm policy mới không cần sửa dropdown. Các chỗ hiển thị `strategy` trong frontend dùng
   `policy_id ?? strategy`.
2. `HybridSimulator.fork()` không chia sẻ mutable events / frames / trace với bản gốc (test).
3. Stateful fallback DC model được cô lập đúng; `isolation.fork_component` từ chối (lỗi rõ ràng) stateful closure /
   hàm có trạng thái không có cơ chế fork — test.
4. Không đổi baseline policy đóng băng.

## Cổng kiểm + báo cáo

Như `FINAL_REVIEW_FIX_BRIEF.md` (ruff, pytest `tests` + `src/simulator/tests`, AST, golden, benchmark 100 run vs
`eval/evidence/2026-11-24-unified-core-final-baseline/`, OpenAPI `--check` sau khi sinh lại, `check_docs`, eval offline,
frontend nếu đổi API / UI). Log: `docs/refactor/raw/final-acceptance-<a|b>/`. Báo cáo ngắn:
`docs/refactor/FINAL_ACCEPTANCE_<A|B>_REPORT.md` (mỗi mục → commit, test, kết quả cổng, ESCALATION, đề xuất tài liệu).
Không commit `eval/results/`. Dòng cuối stdout: `DONE <commit sha>`.
