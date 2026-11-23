# PROJECT_CONTEXT.md (C5)

> Inspire team 001 (Memio) — Quick Rehydrate + Current Invariants.
> Đây là file agent đọc ĐẦU TIÊN khi resume session. Giữ < 60 giây để đọc.
> Đang làm dở giữa chừng? Đọc [`docs/handoff/HANDOFF.md`](docs/handoff/HANDOFF.md) trước file này.
> **Cập nhật 21/11/2026 theo ADR-010…015** (hướng nghiên cứu SC-16 mới). Bản 17/11 (bãi 8 × 7 kW) xem git history.
> **Cập nhật 23/11/2026 theo ADR-018 / ADR-019 (Unified Core, Phase 4):** backend chạy `HybridStation` trên **một
> kernel** `StationKernel` dùng chung với `HybridSimulator`; `LiveStation` và LP backend A–D **đã xoá** (ADR-016 bị
> thay). Policy: B0 / M2b / M3a / M3b (registry). Quote / booking = admission trên bản fork của trạm, kết quả là ước
> tính có điều kiện (không phải SLA). Benchmark S8 = baseline có version
> ([`eval/evidence/2026-11-23-refactor-phase3-baseline/`](eval/evidence/2026-11-23-refactor-phase3-baseline/README.md)).
> Bản test đã deploy (Render + Vercel + Neon, [`docs/plan/56`](docs/plan/56-deploy-render-image.md)).

## 0. Quick Rehydrate (≤ 60s)

- **Project**: ChargePilot (SC-16, nhóm T019) — điều phối lịch và công suất cho **một bãi sạc hỗn hợp AC + DC**,
  phục vụ cư dân và vận hành. **Simulation-only**: không điều khiển EVSE thật, không OCPP, không thanh toán.
- **Fixture nền `mvp1`** (`scenario_id` = `evening_9cars_hybrid_v1`, [ADR-010](docs/adr/ADR-010-bai-hybrid-ac-dc.md)):
  2 tủ AC × 1 cổng 11 kW · 1 tủ DC × 2 cổng 60 kW, tủ DC giới hạn 120 kW (cap vật lý) · lưới 106 kW · ngân sách chính
  sách AC 22 / DC 78 kW · η chuyển đổi 0,95, η sạc 0,98 · bước 1 phút · 9 lượt xe (4 AC, 5 DC) trên 4 đầu nối.
  Đây là fixture ổn định cho regression, **không phải topology chốt cuối**. `supply_mode: shared | independent`;
  nguồn chung AC/DC là **[GIẢ ĐỊNH]**.
- **Nguồn ngữ cảnh**: master context v1.0 của Hiếu, 20/11 — **chưa đưa vào repo**. Yêu cầu: PRD v0.4
  [`docs/PRD.md`](docs/PRD.md) (đang viết song song). Nghiệp vụ: [`docs/business-overview.md`](docs/business-overview.md).
- **Stack**: Python 3.12 / FastAPI / LangGraph 1.x / Pydantic v2 / SQLAlchemy 2 + Alembic (SQLite local, Postgres Neon)
  · web Next.js 16 + TypeScript trong `frontend/`. Simulator: **một kernel** `StationKernel`
  (`src/simulator/src/engine/hybrid.py`, EV2Gym 2.0.0 AC native + DC extension) — `HybridStation` cho backend,
  `HybridSimulator` cho CLI / golden (ADR-018, ADR-019).
- **Trạng thái code** (nhánh refactor `feature/unified-core*`, 23/11; chi tiết `docs/refactor/`):
  - Backend chạy thật: DB (Neon/SQLite), auth JWT, Guard 7 luật, Planning Core B0 / M2b / M3a / M3b, `HybridStation`, WebSocket, chat
    (LLM qua API tương thích OpenAI — OpenAI hoặc Gemini). Stub còn lại chỉ F6 forecast `[T1.3]` / `[T2.3]` (hoãn,
    ADR-015) → 501. pytest **405 passed / 8 skipped**.
  - `config/station.yaml` = fixture `mvp1` (4 đầu nối AC 11 kW ×2 + DC 60 kW ×2, lưới 106 kW).
  - Luồng backend: booking → `charging_service` (admission trên bản fork) → `event_bus` → `control_loop.on_event` →
    `kernel.propose` → consent → `kernel.approve` → Guard `dispatcher` → `HybridStation.apply_commands`. Mô phỏng S8
    (`/simulation/runs`) và `eval/run_benchmark.py` dùng cùng `on_minute` trên một `HybridStation` riêng.
  - `HybridSimulator` (golden MVP-1/2/3, `src/simulator/tests`, job CI `simulator`) và `HybridStation` dùng cùng
    kernel; khác cấu hình thời gian (`TimeConfig`) nên số liệu hai bên **không trộn** vào cùng một bảng.
  - R&D Claude (`experiment/claude-chargepilot-fullstack-ai`) **chưa merge, chưa được duyệt**; chỉ là nguồn tham khảo.
- **Dev**: `make migrate && make run` → http://localhost:8000/docs · `cd frontend && npm run dev` → :3000.
- **Check**: `make check` · `make check-all` · `make web-check`. Backlog: `grep -rn 'NotImplementedError("\[T' src/ --include=*.py`.
- **Kiến trúc**: [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`docs/architecture_diagram.md`](docs/architecture_diagram.md) ·
  [`docs/adr/`](docs/adr/README.md) · [`docs/plan/`](docs/plan/00-overview.md).

## 0.1 Hướng mới đã duyệt (ADR-010 … ADR-015)

| ADR | Nội dung | Sửa một phần |
|---|---|---|
| [ADR-010](docs/adr/ADR-010-bai-hybrid-ac-dc.md) | Bãi hybrid AC/DC, fixture `mvp1`, ràng buộc ba tầng (lưới · tủ · cổng/xe), `supply_mode` | ADR-003 |
| [ADR-011](docs/adr/ADR-011-mot-simulator-sau-be-mat-cong-khai.md) | Một `HybridSimulator` sau `src/simulator/base.py` + `SimulatorGateway`; một bộ `Algorithms` dùng chung live / benchmark / what-if; Guard hai lớp vật lý + chính sách | ADR-002, ADR-007 |
| [ADR-012](docs/adr/ADR-012-mot-danh-muc-xe-va-kich-ban.md) | Một danh mục xe `config/vehicles.yaml` (provenance từng trường) + mọi kịch bản trong `config/scenarios/` | ADR-003 |
| [ADR-013](docs/adr/ADR-013-workflow-xac-dinh-llm-hai-dau.md) | Workflow xác định là xương sống; LLM ở hai đầu; LangGraph chỉ cho hội thoại + HITL | ADR-001 |
| [ADR-014](docs/adr/ADR-014-decision-trace-counterfactual-hitl.md) | `DecisionTrace` + counterfactual sandbox (không bao giờ apply) + vòng đời Proposal/HITL; Copilot theo role; job nền | ADR-005, 006, 007, 008 |
| [ADR-015](docs/adr/ADR-015-pham-vi-mvp4-va-quy-tac-bang-chung.md) | Phạm vi MVP-4, hạng mục hoãn, quy tắc bằng chứng `eval/evidence/` | — |
| [ADR-016](docs/adr/ADR-016-livestation-cho-backend.md) | ~~`LiveStation` cho backend~~ — **bị thay** bởi ADR-018; `LiveStation` đã xoá ở ADR-019 Phase 3 | ADR-011 |
| [ADR-018](docs/adr/ADR-018-backend-chay-engine-simulator.md) | Backend chạy engine simulator (`HybridStation`) | ADR-016 |
| [ADR-019](docs/adr/ADR-019-unified-core-hop-dong-dung-chung.md) | Unified Core: một kernel, một Planning Core, một registry; xoá LP backend A–D | ADR-011, ADR-018 |

**Lộ trình MVP**: MVP-1 hybrid + FIFO/FCFS (đang hardening) → MVP-2 DC queue-aware LP + AC baseline → MVP-3 AC + DC
optimizer + Global Coordinator (fixed vs dynamic) → **MVP-4 = AI-4 Decision Copilot (WHY + WHAT-IF)** là trục chính,
AI-1 SLA negotiation + HITL là luồng bổ trợ. HOW-TO tối ưu đa chiều: HOÃN.

**HOÃN khỏi sprint** (ADR-015): F6/F12 dự báo lúc rút (LightGBM), F13 mức linh hoạt học được, AI-2 ML anomaly (chỉ
có thể giữ luật advisory), AI-3 learned scheduling (không chọn), RAG, vector DB, RL, multi-agent, FR30a câu hỏi mở
nhiều bước. F14 chiếm cổng: Should, chỉ trạng thái `FINISHED_PLUGGED` (AC giữ cổng tới giờ rời, DC rút sau 5 phút).

**Sprint 20–26/11/2026** (5 gate, master context §13) — thay lịch W1–W4 tới 13/12:

| Gate | Ngày | Definition of Done (tóm tắt) |
|---|---|---|
| Contract freeze | 20/11 | `SimulatorGateway`, request/state/trace/patch, role scope, đơn vị/giờ thống nhất |
| Integration Gate 1 | 22/11 | Form/chat → backend → simulator thật (hoặc gateway gắn nhãn fixture); MVP-2 có CLI benchmark + trace |
| MVP-3 + AI-4 | 24/11 | AC + DC optimized, Global Coordinator, Guard/KPI; WHY/WHAT-IF trên simulator thật, isolation |
| HITL E2E | 25/11 | Conflict → option đã mô phỏng → proposal → approval → re-verify → revision + audit qua API |
| Release Candidate | 26/11 | E2E trình duyệt 2 vai trò, benchmark gắn commit, hồi quy MVP-1, không mock trong luồng nghiệm thu |

Mọi gate là **[MỤC TIÊU]**; chưa gate nào được ghi nhận là đạt.

## 0.2 Current Invariants (để không drift)

- **Source of truth kỹ thuật**: code trong `src/`. File `.md` chỉ tóm tắt — mâu thuẫn thì CODE WINS và phải báo lệch.
- **Simulator (ADR-018, ADR-019)**: một kernel `StationKernel` cho cả `HybridSimulator` và `HybridStation`;
  differential test chứng minh cùng plan / kết quả thực thi. Báo cáo phải ghi rõ cấu hình thời gian và nguồn (baseline
  có version); không trộn số khác điều kiện, không dùng bảng A–D (archive).
- **LLM không nằm trên đường cấp công suất**: không tự đặt kW, không tạo `Command`, không tắt Guard, không tự duyệt
  SLA, không apply WHAT-IF. kWh và mọi số liệu do code tính (`src/services/energy.py`, simulator).
- **Guard là chokepoint**: mọi lệnh tới simulator, kể cả benchmark, đi qua Guard (ADR-002; ADR-011 tách hai lớp
  vật lý + chính sách). Hiện code: chỉ `src/guard/dispatcher.py` gọi `StationActuator.apply_commands`.
- **Setpoint ≠ công suất thực nhận**; hiệu suất sạc và chuyển đổi chỉ tính **một lần**.
- **WHAT-IF luôn `applied=false`**; thay đổi cam kết chỉ qua Proposal đã duyệt + re-verify (ADR-014).
- **`resident_id` lấy phía server** (ADR-006): JWT → `config["configurable"]`; LLM không đọc / ghi được.
- **Tham số mô phỏng ở `config/`** (ADR-003, ADR-012); không hardcode topology trong code hay UI.
- **ORM chỉ ở `src/db/` và `src/services/repository.py`** (ADR-005); schema chỉ đổi qua Alembic.
- **Router chỉ gọi `src/services`**; lỗi theo envelope `{detail, code, request_id}` (ADR-008).
- **Web chỉ nhận `frontend/openapi.json`** (ADR-009). Đổi model → `python scripts/export_openapi.py` → `npm run gen:api`.
- **Prompts ở `prompts/*.md`**; không nhúng prompt dài trong Python.
- **Container 1 worker**: trạng thái trạm, WebSocket, checkpoint chat nằm trong RAM (ADR-007).
- **Bằng chứng**: số liệu chỉ lấy từ lần chạy có lưu ở `eval/evidence/<ngày>/`. Số R&D chưa chạy lại ghi
  **[R&D — CHƯA XÁC MINH]**; mục tiêu ghi **[MỤC TIÊU]**; giả định ghi **[GIẢ ĐỊNH]** (ADR-015).
- **AI-log hooks**: KHÔNG disable, KHÔNG `--no-verify`, luôn mở AI tool ở repo root.

### Invariant cũ đã thay (giữ để truy vết)

| Invariant 17/11 | Thay bởi |
|---|---|
| 1 bãi 8 đầu nối × 7 kW, giới hạn 35 kW | Bãi hybrid, fixture `mvp1` 4 cổng / lưới 106 kW (ADR-010) |
| "Deadline cứng; dự báo F6 không được nới; F6 cấm `unplug_time`" | Deadline khai báo vẫn là ràng buộc cứng; F6 **HOÃN** (ADR-015) |
| Agent ReAct graph điều phối tool | Workflow xác định là xương sống, LLM ở hai đầu (ADR-013). Graph ReAct hiện vẫn có trong code |
| `StationReader` / `StationActuator` là bề mặt simulator | `src/simulator/base.py` mới + `SimulatorGateway` (ADR-011) — chưa có trong code |

## 0.3 Known Ambiguities / Mismatches

- **Tài liệu đi trước code**: `config/station.yaml`, `config/scenarios/*.yaml`, test và `CLAUDE.md` còn ghi 8 × 7 kW /
  35 kW. Sửa code và config là việc theo ADR-010/012, chưa làm.
- **Simulator test trên Windows**: `pytest src/simulator/tests` = 112 passed khi `PYTHONUTF8=1`; 109 passed / 3 failed
  với encoding mặc định cp1258 (test đọc file không ghi `encoding`).
- **Fixture `mvp1` không phân biệt được chính sách**: FIFO/FCFS và EDF đều 9/9 đúng hạn. Cần workload khó hơn để
  chứng minh MVP-2/3.
- **FR13** (phê duyệt cư dân vs bảo vệ khẩn cấp) và **Q3** (AC1 ≤ 2 s có gồm LLM không) vẫn chờ xác nhận.
- **LLM không có mock**: `/chat` cần `OPENAI_API_KEY` thật; test và eval offline dùng LLM giả qua injection.
- **`.env` máy dev**: `OPENAI_API_KEY` placeholder bị coi là key thật; mẫu đúng ở `.env.example`.
- **CI** 4 job chưa từng chạy trên GitHub; `.github/` thuộc CODEOWNERS của BTC.
- Danh mục xe: VF3 curve synthetic, VF8 proxy EVKX, VF9/UNKNOWN generic Simolin 2025 — **không curve nào là đo OEM**.

## 1. Bẫy đã gặp

- Windows: `python` trên PATH có thể không phải venv → dùng `.venv/Scripts/python.exe -m …`; console cp1258 →
  đặt `PYTHONIOENCODING=utf-8`; test simulator cần `PYTHONUTF8=1`.
- Tool async của LangChain không hỗ trợ `.invoke` (raise `NotImplementedError`, dễ nhầm thành 501) → node dùng `ainvoke`.
- Autogenerate của Alembic có thể sinh `astext_type=Text()` thiếu `sa.` → đọc lại file migration trước khi dùng.
- Next 16 bật Cache Components: tham số động phải bọc `<Suspense>`; đọc `frontend/AGENTS.md` trước khi viết code web.
- `eval/run_eval.py` mặc định ghi `eval/results/report.md` (file được track) → chạy thử thì thêm `--out <thư mục tạm>`.

## 2. Cập nhật file này

Khi đổi stack/invariant → UPDATE FILE NÀY TRƯỚC, rồi mới sửa code. Giữ lịch sử ở bảng "Invariant cũ đã thay".
