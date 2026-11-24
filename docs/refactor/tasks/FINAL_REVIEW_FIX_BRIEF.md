# Brief — Sửa các vấn đề của Final Review (2026-11-24)

Nguồn: `docs/refactor/raw/final-review/FINAL_REVIEW_2026-11-24.md` §4 (đọc toàn bộ trước khi làm). Điều phối: claude
chính (gộp nhánh + nghiệm thu). §4.5 phần "lô lệnh bị chặn một phần" ĐÃ sửa ở `3255aee` — không làm lại.

Đọc trước: `CLAUDE.md`, `docs/refactor/REFACTOR_REPORT.md`, `docs/refactor/FINAL_MAP.md`,
`docs/adr/` (ADR-002, 005, 008, 009, 017, 018, 019), `tests/test_architecture.py`.

## Phạm vi — CHỈ những gì review đã nêu

| Nhánh | Người | Mục review |
|---|---|---|
| `feature/unified-core-review-a` | claude2 | 4.1 Registry / policy · 4.2 DC vehicle profile ở backend · 4.7 benchmark nghiên cứu fail-fast |
| `feature/unified-core-review-b` | claude3 | 4.3 Ground truth vs observed · 4.4 fork isolation · 4.5b fail-safe vi phạm sau apply (+ negative test lô rejected / expired / stale) · 4.6 booking concurrency + consent parity |

Không làm việc ngoài bảng: không refactor thêm, không tối ưu hiệu năng (§5), không thêm tính năng MVP-3.5 khác
(nhiễu SOC thật, robust optimizer, scenario mới, ...). Chỉ dựng **cơ chế / điểm cắm** và test chứng minh.

## Luật bất biến — "không thay đổi những gì cũ"

1. **Hành vi mặc định giữ nguyên.** Mọi cơ chế mới là opt-in, mặc định = hành vi hiện tại.
2. **Không sửa** thuật toán, objective, tham số solver, vật lý: `src/optimizer/**` (trừ phần đăng ký / metadata của
   `registry.py` cho 4.1), `src/guard/physical/validator.py`, các class model sạc hiện có trong
   `src/simulator/core/charging_models/`. Không sửa evidence cũ trong `eval/evidence/**`.
3. **Test cũ không được sửa assertion.** Chỉ thêm test mới. Nếu một test cũ buộc phải đổi → ghi ESCALATION + lý do,
   không tự đổi.
4. **API / public interface tương thích ngược**: chỉ thêm (endpoint / trường tuỳ chọn). Field / enum cũ giữ nguyên
   giá trị và ngữ nghĩa. Đổi model / endpoint → `python scripts/export_openapi.py` rồi `cd frontend && npm run gen:api`
   (ADR-009). Schema DB chỉ đổi qua Alembic (ADR-005), migration có downgrade, không xoá dữ liệu.
5. **Ranh giới kiến trúc** giữ nguyên (`tests/test_architecture.py`); chỉ `src/guard/dispatcher.py` gửi lệnh tới trạm
   (ADR-002) — fail-safe mới cũng phải đi qua dispatcher. Tham số vào `config/*.yaml` (ADR-003), prompt không đổi.
6. Không thêm dependency.

## Cổng kiểm bắt buộc (log vào `docs/refactor/raw/final-review-<a|b>/`)

- `ruff check src tests scripts` + `ruff format --check src tests scripts`
- `pytest tests -q` và `pytest src/simulator/tests -q` (0 fail; số pass ≥ trước: 521 / 163)
- AST: `scripts/refactor/compare_ast_manifest.py docs/refactor/raw/phase4-final/preserved_baseline_manifest.txt --moves docs/refactor/raw/phase4-final/moves.txt -- src`
  → 114 compared, 0 undeclared.
- Golden simulator MVP-1/2/3: chạy lại như `docs/refactor/raw/phase4-final/` (`run_mvp1*.txt`, `kpi_gate.txt`;
  `scripts/refactor/run_sim_kpi_gate.py`, `compare_sim_output.py` với `eval/evidence/2026-11-22/raw/sim-hardware/`) → 0 unexpected.
- Benchmark backend: `eval/run_benchmark.py --seeds 1,2,3,4,5` (ghi vào `eval/results/`, KHÔNG commit thư mục đó) rồi
  `scripts/refactor/compare_backend_benchmark.py eval/evidence/2026-11-24-unified-core-final-baseline/benchmark.json eval/results/benchmark.json`
  → 0 problems. Chép output so sánh vào log.
- `scripts/export_openapi.py --check` (sau khi đã regenerate nếu đổi API), `scripts/check_docs.py`,
  `eval/run_agent_eval.py --offline`. Nhánh A đổi API → thêm `cd frontend && npm ci && npm run lint && npm run typecheck && npm test && npm run build`.

## Nhánh A — claude2

**4.1 Policy lấy từ registry.** `src/optimizer/registry.py` là nguồn duy nhất: mỗi policy có id, version (policy cũ
giữ `"1"` để DecisionTrace / baseline không đổi), thành phần dispatch / optimizer / coordinator. Backend
(`src/services/hybrid_planner.py`, `runtime`, `simulation_service`, API) tra policy qua registry thay vì danh sách cứng
4 policy; `StrategyName` cũ giữ nguyên giá trị (tương thích), nhưng policy mới đăng ký vào registry phải chạy được
trên backend mà **không sửa orchestration**. Thêm endpoint đọc danh sách policy hợp lệ từ cùng nguồn (vd.
`GET /api/v1/simulation/policies`). Config (`config/station.yaml` hoặc file config phù hợp, khoá tuỳ chọn) chọn policy
id / version / DC model / tham số; thiếu khoá = như hiện tại. Test bắt buộc: đăng ký một policy HOÀN TOÀN mới (trong
test, ghép từ thành phần có sẵn) → `HybridStation` / planner / API nhận và chạy được, KHÔNG ghi đè M2b / M3a; policy
cũ không đổi kết quả. Nếu giữ enum ở schema request mà không nhận được id mới → thiết kế đường tương thích
(vd. trường string tuỳ chọn) và giải thích trong báo cáo.

**4.2 DC charging model ở backend.** `HybridStation` chọn DC model theo tên từ cùng registry mà simulator offline dùng
(`vinfast_profiles_v0_1`, synthetic mặc định); cài `with_vinfast_profiles` (bỏ `NotImplementedError`) bằng một
vehicle-profile provider hỗ trợ **xe đến động** (resolve profile khi xe được upsert, không cần danh sách xe biết trước).
Mặc định vẫn `SyntheticTaperV1()`. Test: cùng kịch bản + profile VinFast, `HybridSimulator` và `HybridStation` cho
cùng công suất / SOC từng phút (hoặc giải thích chênh lệch có lý do); xe đến động nhận đúng profile.

**4.7 Benchmark nghiên cứu fail-fast.** Thêm chế độ strict (vd. `run_benchmark.py --strict-incidents` / tham số service):
incident không hợp lệ ⇒ lỗi ngay. Mọi chế độ ghi số incident dự kiến / thực thi / bỏ qua (trường mới, tuỳ chọn). Chế
độ mặc định giữ hành vi skip + note như cũ (baseline không đổi). Test: strict fail trên incident trỏ đầu nối không tồn
tại; non-strict giữ nguyên; số đếm đúng. Không sửa evidence cũ, không tạo suite / scenario mới.

## Nhánh B — claude3

**4.3 Ground truth vs observed state.** Tách lớp: ground truth (physics, adapter, KPI) / declared (cư dân khai) /
observation (noise, delay, missing, stale — điểm cắm) / estimated (giá trị + timestamp + uncertainty). Thêm trường
tuỳ chọn vào hợp đồng (`src/models/scheduling/observations.py`, thuần stdlib theo ADR-019), một protocol observation
model cắm vào `StationKernel.observe`; mặc định `PerfectObservation` (identity ⇒ kết quả cũ y hệt). Optimizer chỉ nhận
estimated state. Test chống leakage: với observation model lệch / nhiễu cố định, input của optimizer = giá trị quan sát,
không phải SOC thật; physics / KPI vẫn dùng SOC thật. Không cài mô hình nhiễu "thật" (việc MVP-3.5).

**4.4 Fork isolation.** Quy định rõ (code + docstring) thành phần nào được chia sẻ khi `StationKernel.fork`: chỉ thành
phần khai báo immutable / stateless; thành phần có trạng thái phải có `fork()` / snapshot riêng (hoặc deep copy).
Đánh dấu các thành phần hiện tại đúng thực tế (chúng stateless ⇒ hành vi cũ không đổi). Test mutation isolation:
optimizer / model / RNG giả có trạng thái, bị đổi trong bản fork (admission / WHAT-IF) không làm đổi bản live.

**4.5b Fail-safe khi phát hiện vi phạm cứng sau apply.** Chế độ backend (non-strict) hiện chỉ log ở
`_after_apply_violation`. Thêm hành động khẩn cấp: phát sự kiện / tín hiệu để runtime sinh lệnh giảm tải qua
`guard/dispatcher.py` (dùng đường emergency / safety reduction có sẵn, không gửi thẳng actuator từ kernel). Strict mode
giữ nguyên (raise). Test: gây vi phạm ⇒ lệnh giảm tải được dispatch, có log / trace. Thêm negative test dispatcher:
lô có lệnh bị rejected, approval expired, lệnh stale ⇒ tập lệnh thực gửi tới actuator luôn an toàn (bổ sung cho test
`test_increase_that_relies_on_a_reduction_blocked_by_guard_is_not_applied`).

**4.6 Booking concurrency + consent parity.** `services/charging_service.book`: hai yêu cầu đồng thời không được cùng
qua kiểm tra trên trạng thái thiếu booking của nhau (cùng cư dân ⇒ đúng 1 booking; trạm chỉ đủ chỗ cho 1 ⇒ không
overbook). Ưu tiên optimistic concurrency: admission ngoài lock, commit trong lock + kiểm lại version trạng thái /
booking, đổi thì chạy lại có giới hạn hoặc trả `PROPOSAL_EXPIRED`; không khoá cả trạm suốt rollout dài. Nếu cần ràng
buộc DB thì qua Alembic. Consent parity: admission của `book` chạy trên consent thực tế sẽ lưu vào booking. `quote`
giữ hành vi cũ. Test: `asyncio.gather` hai booking đồng thời (cùng cư dân; khác cư dân tranh chỗ cuối), consent parity.

## Quy trình

- Commit nhỏ, `type(scope): mô tả` tiếng Việt, KHÔNG thêm trailer Co-Authored-By / Claude-Session.
- Không push / merge / rebase / reset / checkout. Không sửa `CLAUDE.md`, ADR, `REFACTOR_REPORT.md`, `FINAL_MAP.md`
  (điều phối cập nhật khi gộp) — ghi đề xuất sửa tài liệu vào báo cáo.
- Báo cáo: `docs/refactor/FINAL_REVIEW_FIX_<A|B>_REPORT.md`: mỗi mục review → đã làm gì (file, commit), test chứng
  minh, kết quả cổng (trỏ log), chênh lệch so baseline (phải 0 ngoài latency), ESCALATION, đề xuất sửa tài liệu.
- Dòng cuối stdout: `DONE <commit sha>`.
