# HANDOFF — ChargePilot

> Chỉ giữ trạng thái **mới nhất** + bẫy còn đúng. Lịch sử các phiên trước (16–21/11: plan Pha A–C, skeleton, mockup,
> căn chỉnh SC-16) xem `git log -- docs/handoff/`. Quyết định kỹ thuật nằm ở `docs/adr/`, không lặp lại ở đây.

## Trạng thái 23/11 (mới nhất) — refactor Unified Core, Phase 4

Đọc `docs/refactor/TECHLEAD_PHASE4_DECISIONS.md` + `docs/refactor/PHASE4_*_REPORT.md`. Hiện trạng kiến trúc (thay mọi
mô tả `LiveStation` / A–D ở mục 22/11 bên dưới):
- Backend = `HybridStation` trên **một kernel** `StationKernel` dùng chung với `HybridSimulator` (ADR-018, ADR-019).
  `LiveStation`, LP backend A–D (`lp_model`, `assignment`, `mpc`, `baselines`, `strategies`) **đã xoá**;
  `STATION_ENGINE` chỉ còn `hybrid`. `LIVE_STRATEGY` ∈ B0 / M2b / M3a / M3b (A–D bị từ chối khi đọc cấu hình).
- Quote / booking / đổi yêu cầu = admission trên bản fork của trạm (`src/services/admission.py`), trả **ước tính có
  điều kiện** (`ScheduleProposal.certainty`, `assumptions`, số phê duyệt chờ) — không phải SLA.
- S8 + `GET /simulation/benchmark` = baseline có version `eval/evidence/2026-11-23-refactor-phase3-baseline/` (tạm;
  baseline nghiệm thu cuối sinh sau khi nhánh core sửa budget deviation). Bảng A–D cũ: archive deprecated ở
  `eval/results/archive/2026-11-22-pre-refactor/`.
- Alembic `0002_drop_lp_strategy_plans` xoá lịch lưu của A–D → sau deploy chạy `make migrate` / `alembic upgrade head`.

## Trạng thái 22/11 (lịch sử — kiến trúc `LiveStation` / A–D nay đã bỏ)

**Đã merge vào `develop`:** PR #8 (backend chạy thật: DB, auth, Guard, optimizer, `LiveStation`, WebSocket), PR #9
(job CI `deploy` qua Docker Hub + Render Deploy Hook), PR #10 (hiện trạng deploy, `docs/plan/56`).

**Đang chạy:** web https://p019-web.vercel.app (Vercel CLI, team *SWP391's projects*) → backend test
https://p019-backend-develop.onrender.com (Render Free, image `minhmama/p019-backend`) → Neon nhánh `dev`. CI chạy trên
runner `team-19` = VM `p019-runner` trên laptop (phải bật mới có CI / deploy). Chi tiết: `docs/plan/56` §0.

**Nhánh `fix/booking-charging-state`** (PR vào `develop`):
- `fix(optimizer)`: LP tôn trọng `consent.max_start_delay_minutes` (trước đó xe walk-in cắm cổng 0 kW hàng giờ).
- `feat(ops)`: deploy bật `CONTROL_LOOP_ENABLED=true` — trạm tự chạy theo thời gian; test hành vi cho `run_forever`.
- `docs`: rà toàn bộ tài liệu theo hiện trạng (backend dùng `LiveStation`, ADR-016); dọn tài liệu cũ.

**Nhánh `fix/guard-simulator-contract`** (PR vào `develop`): lớp vật lý của Guard backend gọi thẳng Guard của
HybridSimulator qua `src/guard/physical.py` (ADR-017) — trần vùng `physical_zone_cap_kw` 22/120 thay cho ngân sách 22/78, nguồn `independent`, không cấp điện
cổng trống / xe đầy, chỉ gán xe đang chờ. Benchmark A–D: 0 lệnh bị chặn, 0 vi phạm. Chưa làm: hạ trần tủ theo sự kiện,
công suất nhận theo đường sạc DC (cần nối HybridSimulator).

**Nhánh `feature/hybrid-backend`** (chưa commit, gồm cả phần Guard ở trên): backend chạy engine simulator (ADR-018) —
`src/simulator/hybrid_station.py` (trạm dựng từ QueueController + EV2GymAdapter, phát lại `mvp1` khớp HybridSimulator),
`src/services/hybrid_planner.py` (B0 / M2b / M3a / M3b từ `benchmark_mvp3.POLICIES`), `STATION_ENGINE` / `LIVE_STRATEGY`,
ev2gym `--no-deps` trong Dockerfile / CI / `make install`. Bằng chứng `eval/evidence/2026-11-23/`. Còn: đo RAM image trong
Docker, profile DC VinFast cho xe đến dần (`with_vinfast_profiles` TODO), consent cư dân trong thuật toán simulator, nhóm chọn
`LIVE_STRATEGY` (M3a rẻ hơn nhưng đúng hạn thấp hơn A_edf trên kịch bản backend).

**Việc tiếp theo:**
1. Sau merge: Render → Environment đặt `CONTROL_LOOP_ENABLED=true` (service tạo từ image, không đọc `render.yaml`).
2. Nhóm chốt chính sách tạm dừng: với `allow_power_reduction=true`, LP sạc bước đầu rồi tạm dừng tới giờ thấp điểm
   (booking vẫn "đang sạc"). Chọn: giữ + sửa UI / mức công suất tối thiểu / mặc định không cho giảm.
3. ~~Nhóm duyệt ADR-016~~ — đã giải quyết: ADR-018 thay ADR-016, ADR-019 xoá `LiveStation` (differential test
   CLI ↔ backend thay cho "live = research").
4. Production: PR `develop` → `main`, service Render riêng (Starter trước demo), Neon nhánh `main`,
   `RENDER_DEPLOY_HOOK_PROD`, đổi `NEXT_PUBLIC_API_URL` Production trên Vercel (plan 56 §3.5).
5. Giới hạn tần suất `/chat` theo user; sửa regex phút trong `src/llm_chat/mock_llm.py` (nhận tới 99).
6. Runner: giữ VM laptop hay thuê VPS x86_64 (4 vCPU / 8 GB) — nhóm quyết.
7. Deliverable BTC: `README.md`, `JOURNAL.md`, `WORKLOG.md` đã điền theo dự án (22/11). Còn thiếu: mã sinh viên trong
   README, phần tuần 1 của JOURNAL ("[nhóm bổ sung]"), video demo, pitch deck, `eval/results/report.md` với LLM thật.
8. `docs/mockups/` + `docs/plan/22-ui-work-split.md`: bản thiết kế / kế hoạch UI đã xong, giữ làm **tham khảo**; UI thật
   là `frontend/`, spec là `docs/plan/21-ui-spec.md`.
9. Câu hỏi mở cho nhóm / mentor: Guard bao nhiêu luật, FR4a, FR23b, F15, F9 Should hay Must; redesign "đêm sạc" của
   mockup chưa vào spec 21 §1.1.

## Xác minh nhanh khi tiếp tục

```bash
git status --short && git log --oneline -5
.venv/Scripts/python.exe -m ruff check src tests && .venv/Scripts/python.exe -m ruff format --check src tests
.venv/Scripts/python.exe -m pytest tests/ -q                    # 22/11: 405 passed, 8 skipped
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/check_docs.py
curl https://p019-backend-develop.onrender.com/ready            # Free ngủ: lần đầu chờ ~50 s
cd frontend && npm run typecheck && npm test
```

## Bẫy đã gặp (lỗi + cách xử lý)

**Môi trường Windows / công cụ**
- `python` / `ruff` / `pytest` trên PATH không có package → luôn dùng `.venv/Scripts/python.exe -m …`.
- Console cp1258: đặt `PYTHONIOENCODING=utf-8` (`python -I` bỏ qua biến này → `python -I -X utf8`). `alembic.ini` phải ASCII.
- `.env` của máy dev trỏ Postgres local → `tests/__init__.py` ép SQLite tạm; chạy app local thì đặt `DATABASE_URL` cho phiên.
- Shell của công cụ có thể đổi thư mục sau `cd` → luôn `cd /d/VIN/P-019` ở đầu lệnh. Git Bash + `docker exec … sh -c
  '/đường/dẫn'` bị đổi đường dẫn → `MSYS_NO_PATHCONV=1`.
- Python trong `.venv` trên Windows là launcher: đo RAM / PID phải lấy process **con**.
- `ruff check .` báo lỗi sẵn có ở `scripts/` — CI chỉ kiểm `src/ tests/`.

**Backend**
- Autogenerate Alembic sinh `astext_type=Text()` thiếu `sa.` → sửa tay. Không có relationship ORM → flush user trước booking.
- Tool async của LangChain không hỗ trợ `.invoke` (raise NotImplementedError — dễ nhầm thành 501) → node dùng `ainvoke`.
- `eval/run_eval.py` ghi đè file được track trong `eval/results/` → chạy thử thì `--out` ra thư mục tạm.
  `eval/run_benchmark.py` ghi `eval/results/benchmark.{json,md}` (kind `generated`); S8 không đọc file này mà đọc
  baseline có version — muốn đổi baseline thì tạo thư mục `eval/evidence/<ngày>-...-baseline/` có `manifest.json`.
- HiGHS lỗi native khi đổi thread → mọi lần giải LP qua `src/services/solver.py` (một worker thread).
- Lỗi không phải `OpenAIError` trong `/chat/stream` làm luồng đứt im lặng (web chỉ thấy "Máy chủ gặp lỗi") → xem log Render.
  Ví dụ đã gặp: `OPENAI_API_KEY` còn chuỗi mẫu tiếng Việt → `UnicodeEncodeError: 'ascii'` khi dựng header.

**Deploy / CI**
- VM runner treo ở `Loading essential drivers` khi máy có Hyper-V và thiếu RAM → `VBoxManage controlvm p019-runner reset`;
  bật VM khi máy còn ≥ 6 GB trống. Lỗi mạng tạm (`DeadlineExceeded`, `ConnectionTimeout`) → `gh run rerun --failed`.
- Pip cache tải mãi `Received 0 of …` → `SEGMENT_DOWNLOAD_TIMEOUT_MINS=2` (đã có trong `ci.yml`).
- `pytest` trần không thấy package `src` ở `src/simulator/tests` → `pytest.ini` có `pythonpath = .`.
- Render *Existing Image*: tag dùng dấu `:`; báo "credential invalid" khi tag **chưa được push**; region không đổi được.
- Org BTC chặn GitHub App → Render / Vercel không nối repo; Vercel tạo team mới cần thẻ thanh toán.
- Secret (JWT, key, chuỗi Neon) không tạo / dán trong khung chat AI — hook ai-log gửi prompt lên server BTC.

**Frontend / tài liệu**
- Next 16 bật Cache Components: tham số động bọc `<Suspense>`; `LayoutProps<"/route">` cần `next typegen` trước `tsc`;
  đọc `frontend/AGENTS.md` trước khi viết code web. `frontend/.gitignore` chặn `.env*` → có `!.env.example`.
- `.dockerignore`: mẫu không có `**/` chỉ khớp ở thư mục gốc.
- Mermaid `sequenceDiagram`: không đặt alias participant là `OPT` / `ALT` / `LOOP` / `PAR` / `END` (trùng từ khoá).
- Mockup / xuất Figma (`docs/mockups/_figma/`): `export.mjs --only …` ghi đè `plugin/code.js` → chạy lại bản đầy đủ trước
  khi bàn giao; SVG không nhận biến CSS → dùng mã hex.
