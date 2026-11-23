# Architecture Document — ChargePilot

> Điều phối lịch và công suất cho một bãi sạc EV hỗn hợp AC + DC — đề tài SC-16, nhóm T019. Hệ thống là
> **simulation-only**.
> **Cập nhật 21/11/2026 theo ADR-010…015.** Mô tả bài toán và hướng kiến trúc đã đổi; sườn thư mục và bảng truy vết
> vẫn mô tả **code hiện có** của skeleton (`8f6f08a`), phần đích ghi riêng là "chưa có trong code".
> Sơ đồ chi tiết: [`docs/architecture_diagram.md`](docs/architecture_diagram.md).
> Quyết định kiến trúc: [`docs/adr/`](docs/adr/README.md) (ADR-001 … ADR-015).
> Plan chi tiết theo mảng: [`docs/plan/`](docs/plan/00-overview.md). Yêu cầu: PRD v0.4 [`docs/PRD.md`](docs/PRD.md).
> Nguồn sự thật kỹ thuật là code trong `src/`; khi tài liệu mâu thuẫn với code, code thắng.

## System Overview

ChargePilot là web app hai vai trò (cư dân / vận hành) cho **một** bãi sạc mô phỏng hỗn hợp AC + DC
([ADR-010](docs/adr/ADR-010-bai-hybrid-ac-dc.md)). Fixture nền `mvp1` (`evening_9cars_hybrid_v1`): 2 tủ AC × 1 cổng
11 kW; 1 tủ DC × 2 cổng 60 kW, giới hạn tủ 120 kW; lưới 106 kW; ngân sách chính sách AC 22 / DC 78 kW, trần vùng thiết bị AC 22 / DC 120 kW (Guard áp,
[ADR-017](docs/adr/ADR-017-guard-theo-hop-dong-an-toan-simulator.md)); η chuyển đổi
0,95, η sạc 0,98; bước 1 phút; 9 lượt xe (4 AC, 5 DC). Topology này là fixture regression, **không phải chốt cuối**;
nguồn chung AC/DC (`supply_mode: shared`) là **[GIẢ ĐỊNH]**. Mọi số topology lấy từ `config/` / API, không hardcode.

> (cũ, thay bởi ADR-010) Bản 17/11 mô tả bãi 8 đầu nối × 7 kW, giới hạn tổng 35 kW. Từ 22/11 code và `config/`
> đã theo fixture `mvp1` (4 đầu nối, lưới 106 kW).
>
> **Hiện trạng 22/11 (ADR-016):** backend — cả chạy thật lẫn mô phỏng S8 / `eval/run_benchmark.py` — chạy trên
> **`LiveStation`** (`src/simulator/live.py`). `HybridSimulator` (`src/simulator/src/`) là công cụ R&D offline với bộ
> test riêng; backend **không** gọi nó. Các mục "đích theo ADR-011" bên dưới là hướng dài hạn, chưa có trong code.

Kiến trúc 3 tầng: Frontend Next.js (`frontend/`) → Backend FastAPI (`src/`) → lõi tính toán, cộng tầng lưu trữ
SQLAlchemy (`src/db/`). Hướng đích ([ADR-013](docs/adr/ADR-013-workflow-xac-dinh-llm-hai-dau.md)): **workflow xác
định là xương sống** — Dispatch → AC/DC Optimizer → Global Coordinator → Guard. Hiện chạy trên `LiveStation`
([ADR-016](docs/adr/ADR-016-livestation-cho-backend.md)); đích dài hạn là một `HybridSimulator` EV2Gym-first sau cùng
bề mặt ([ADR-011](docs/adr/ADR-011-mot-simulator-sau-be-mat-cong-khai.md)). LLM chỉ ở hai đầu: hiểu câu (intake,
intent, patch có schema) và diễn đạt kết quả đã tính. LangGraph giữ cho hội thoại + HITL interrupt.

Nguyên tắc 3 trụ của Brief vẫn giữ:

1. **AI hiểu yêu cầu và giải thích** (`src/agents/`; Copilot WHY/WHAT-IF theo ADR-014)
2. **Bộ tối ưu tính phương án** (`src/optimizer/`; `src/forecast/` **HOÃN** theo ADR-015)
3. **Bộ kiểm tra an toàn kiểm soát thực thi** (`src/guard/`): cửa duy nhất tới trạm giả lập (`src/simulator/`);
   ADR-011 tách hai lớp vật lý + chính sách

Trạng thái hiện tại là **skeleton contract-first** (ADR-004): đủ schema, đủ endpoint, đủ chữ ký hàm; phần chưa làm
`raise NotImplementedError("[Txx] …")` và API trả HTTP 501 kèm `task_id`. Simulator v1.2 thật nằm ở branch
`feature/simulator` @ `d15871a`, **chưa merge**; `src/simulator/` dưới đây là bản cũ của skeleton.

## Sườn thư mục

Ký hiệu: ✅ chạy thật · 🧩 stub có hợp đồng (API trả 501) · 📄 tài liệu/cấu hình · (giữ) = có từ template.

```text
P-019/
├── config/                         📄 THAM SỐ MÔ PHỎNG — đổi ở đây, không hardcode (ADR-003)
│   ├── station.yaml                   (cũ) 8 × 7 kW, giới hạn 35 kW, bước 15' — sẽ thay bằng fixture hybrid (ADR-010/012)
│   ├── vehicles.yaml                  danh mục xe (FR2) — hiện chỉ có DEMO-60, verified: false
│   ├── tariff.yaml                    biểu giá MÔ PHỎNG theo khung giờ (MT3) — verified: false
│   └── scenarios/                     peak_evening (AC3) · connector_failure (FR18) · power_drop (AC5)
├── prompts/                        📄 PROMPT của Agent — file .md, biến {{placeholder}} (không nhúng trong Python)
│   ├── reason.md, finalize.md         prompt 2 node của vòng ReAct
│   ├── charging_domain.md             kiến thức miền + quy tắc trích ChargeRequest
│   ├── charging_safeguards.md         quy tắc an toàn của ChargePilot
│   └── system_prompt.md, safeguards.md, citation_rules.md   (giữ) pipeline RAG của template — gỡ ở T2.5
├── src/
│   ├── main.py                     ✅ app FastAPI: router, CORS, X-Request-ID, envelope lỗi, /health, /ready
│   ├── config.py                   ✅ Settings (env) — DB, JWT, LLM, control loop, CORS
│   ├── models/                     ✅ HỢP ĐỒNG DỮ LIỆU — Pydantic thuần, không import tầng nào khác
│   │   ├── schemas.py                 ChatRequest/ChatResponse (status, proposal, pending) + AgentDecision
│   │   ├── identity.py                UserProfile (danh tính đã xác thực)
│   │   ├── station.py                 StationConfig, ConnectorState, StationState, Tariff, LoadPoint
│   │   ├── charging.py                VehicleSpec, ChargeRequest (FR2), EnergyEstimate (FR3), Booking,
│   │   │                              ConsentScope, ScheduleProposal (FR4), SchedulePlan, StrategyName A–D
│   │   ├── control.py                 Role, Command, GuardRule (7 luật), GuardVerdict, Approval, DecisionLogEntry
│   │   ├── events.py                  EventType (FR8), StationEvent, WsMessage + payload có kiểu (FR16)
│   │   ├── simulation.py              Scenario, Incident, SimulationTrace, KpiReport (MT1–MT6), BenchmarkReport
│   │   └── api.py                     DTO của API: Login, ErrorResponse/ErrorCode, ReadinessReport, QueueStatus, …
│   ├── agents/                     TRỤ 1 — F1 (TV3)
│   │   ├── graph.py                ✅ entry → guardrail_check → reason → act → (human_review) → assess → finalize
│   │   ├── state.py                ✅ AgentState: vòng ReAct + turn_context, history, draft_request, proposal
│   │   ├── prompts.py              ✅ load_prompt / render (fail khi thiếu biến)
│   │   ├── guardrails.py           ✅ chặn injection (có mẫu tiếng Việt) · 🧩 check_grounded_numbers (T2.5)
│   │   ├── nodes/                  ✅ reason, act, human_review, assess, finalize (nhận RunnableConfig)
│   │   │                              (giữ) safety, retrieve, synthesize, validate — pipeline RAG, gỡ ở T2.5
│   │   └── tools/
│   │       ├── charging.py         ✅ 6 tool sạc; resident_id lấy từ config["configurable"] (ADR-006);
│   │       │                          tool gọi src/services — service còn stub thì tool nổi 501
│   │       ├── risky_tools.py         RISKY_TOOL_NAMES gồm confirm_booking → HITL
│   │       └── knowledge.py, mcp_tool.py   (giữ) tool demo của template — gỡ ở T2.5
│   ├── services/                   TẦNG ỨNG DỤNG — API và Agent cùng gọi vào đây
│   │   ├── catalog.py              ✅ nạp + validate config/*.yaml
│   │   ├── energy.py               ✅ FR3: kWh = dung lượng × Δ%pin; lưới = pin ÷ hiệu suất
│   │   ├── llm.py                  ✅ cascade router (timeout, max_retries=1) — cần OPENAI_API_KEY thật
│   │   ├── errors.py               ✅ DomainError + bảng mã lỗi → HTTP status (ADR-008)
│   │   ├── repository.py           ✅ init / dispose / ping · 🧩 25 hàm CRUD (T1.6) — nơi DUY NHẤT ngoài src/db dùng ORM
│   │   ├── auth.py                 🧩 JWT 2 vai trò, băm scrypt, seed tài khoản demo, hồ sơ (T1.7, T2.8)
│   │   ├── charging_service.py     🧩 quote / book / cancel / change / queue_status / explain (T2.2, T2.5, T2.8)
│   │   ├── station_service.py      🧩 overview / load_history / replan / manual_assign … (T2.6, T3.2, T3.6)
│   │   ├── runtime.py              🧩 StationRuntime — composition root live vs benchmark (ADR-007; T2.6, T1.5)
│   │   ├── control_loop.py         🧩 on_event(event, rt), run_forever, resolve_approval (T2.6, T3.2)
│   │   ├── event_bus.py            🧩 pub/sub in-process (T2.6)
│   │   ├── realtime.py             🧩 sổ kết nối WebSocket: register / unregister / broadcast (T3.6)
│   │   └── simulation_service.py   🧩 chạy kịch bản S8 + benchmark A–D (T1.5, T3.4, T3.5)
│   ├── db/                         TẦNG LƯU TRỮ (ADR-005) — chỉ repository.py được gọi vào
│   │   ├── base.py, types.py       ✅ DeclarativeBase, UtcDateTime (từ chối datetime không múi giờ)
│   │   ├── tables.py               ✅ 9 bảng: users, bookings, idempotency_keys, schedule_plans, approvals,
│   │   │                              decision_log, notifications, station_events, load_points
│   │   ├── session.py              ✅ engine + session_scope; chuẩn hoá URL Neon → postgresql+psycopg://
│   │   └── mappers.py              🧩 Row ↔ model Pydantic (T1.6)
│   ├── optimizer/                  TRỤ 2 — F2/F3 (TV1) — code thuần
│   │   ├── __init__.py, base.py    ✅ get_scheduler(A_fcfs | A_edf | B | C | D), PlanningContext, Scheduler
│   │   ├── baselines.py            🧩 FCFS, EDF (A — T1.5), Oracle (D — T3.4)
│   │   ├── mpc.py, lp_model.py     🧩 MPC cửa sổ trượt B/C + LP một bước (T2.1)
│   │   └── assignment.py           🧩 gán đầu nối + hàng đợi (FR7, T2.2)
│   ├── forecast/                   F6 — HOÃN khỏi sprint 20–26/11 (ADR-015); stub giữ nguyên, không làm
│   │   ├── datasets.py, features.py   🧩 nạp dữ liệu phiên sạc, feature không rò rỉ nhãn (T1.3, T2.3)
│   │   ├── predict.py, train.py, evaluate.py   🧩 3 forecaster cùng interface, CLI train, MAE (T2.3)
│   │   └── artifacts/              📄 mô hình đã huấn luyện (nhỏ, commit được)
│   ├── guard/                      TRỤ 3 — F4 (TV3) — xác định, độc lập AI
│   │   ├── checker.py              ✅ chạy mọi luật, gom đủ vi phạm → GuardVerdict
│   │   ├── rules.py                ✅ 7 luật FR12 + GuardContext; 2 luật công suất gọi physical.py
│   │   ├── physical.py             ✅ lớp vật lý = Guard của HybridSimulator (safety/guard.py), ADR-017
│   │   ├── approval.py             🧩 FR13: phân loại + vòng đời phê duyệt (T3.2)
│   │   ├── emergency.py            🧩 AC5: hạ công suất ngay khi nguồn giảm (T3.2)
│   │   └── dispatcher.py           🧩 CHOKEPOINT duy nhất gọi apply_commands; DispatchSinks (T3.1, T3.2)
│   ├── simulator/                  FR11 (TV3 + TV1)
│   │   ├── base.py                 ✅ StationReader (đọc) / StationActuator (ghi) + VehicleVisit — ADR-002, ADR-016
│   │   ├── live.py                 ✅ LiveStation: trạm backend dùng cho live + mô phỏng S8 + benchmark (ADR-016)
│   │   ├── run.py, benchmark*.py   ✅ CLI R&D chạy HybridSimulator offline (không phải đường của backend)
│   │   ├── src/                    ✅ HybridSimulator v1.2 (engine/hybrid.py, queue.py, ev2gym_adapter.py…) — R&D
│   │   └── tests/                  ✅ bộ test R&D (golden regression), job CI `simulator`
│   └── api/                        REST + WebSocket — router chỉ gọi src/services
│       ├── deps.py                 ✅ get_current_user, ResidentUser, OperatorUser (401/403)
│       ├── catalog.py              ✅ /vehicles, /energy/estimate, /station/config, /tariff (công khai)
│       ├── routes.py               ✅ /chat, /chat/resume (token cư dân), /status
│       ├── auth.py                 🧩 /auth/login, /auth/me
│       ├── resident.py             🧩 /resident/* — S2–S4 + hồ sơ (15 thao tác)
│       ├── operations.py           🧩 /operator/* — S5–S7 (12 thao tác)
│       ├── simulation.py           🧩 /simulation/* — S8
│       └── ws.py                   🧩 /ws/operator, /ws/resident (đóng 1011 kèm lý do)
├── migrations/                     ✅ Alembic: env.py dùng chung engine với app; versions/0001_initial_schema.py
├── alembic.ini                     📄 chỉ ASCII; KHÔNG chứa chuỗi kết nối
├── frontend/                       WEB (TV4) — Next.js 16 App Router + TypeScript (ADR-009)
│   ├── openapi.json                📄 snapshot hợp đồng — thứ DUY NHẤT web nhận từ backend
│   └── src/
│       ├── app/                       13 route: /login · /resident/* · /operator/*
│       ├── components/                auth/ (AuthGate, LoginForm) · system/ (banner backend, khối 501, lỗi, khung vai trò)
│       ├── lib/api/                   schema.d.ts (SINH TỰ ĐỘNG) · client.ts · errors.ts · queries.ts
│       ├── lib/auth/, lib/ws/         phiên đăng nhập · WebSocket tự nối lại
│       └── test/                      vitest
├── tests/                          pytest — 247 passed / 94 skipped (mỗi skip ghi lý do + task ID)
│   ├── test_architecture.py        ✅ khoá ranh giới import, chokepoint Guard, ORM, frontend
│   ├── test_api/                   ✅ hợp đồng OpenAPI + snapshot, envelope lỗi, 401/403/501 · ⏭ luồng AC1–AC6
│   ├── test_db/                    ✅ migration lên/xuống, ràng buộc DB, datetime có múi giờ
│   ├── test_models/, test_services/, test_guard/, test_optimizer/, test_forecast/, test_simulator/, test_agents/
├── eval/
│   ├── run_agent_eval.py           ✅ --offline (kiểm dataset + ngưỡng) · 🧩 chạy Agent thật (T4.2)
│   ├── run_benchmark.py            🧩 benchmark A–D → results/benchmark.{md,json} (T3.4)
│   ├── datasets/charging_requests.jsonl  📄 25 câu có nhãn cho F1 (PRD cần ≥ 50 — T4.2)
│   └── run_eval.py, judge.py, …       (giữ) eval pipeline RAG của template
├── scripts/export_openapi.py       ✅ ghi / kiểm frontend/openapi.json
├── docs/
│   ├── PRD.md                      📄 PRD v0.4 (đang viết song song)
│   ├── business-overview.md        📄 tổng quan nghiệp vụ
│   ├── design/                     📄 kien-truc-tra-loi-3-tang.md (tầng 0/1 + job nền)
│   ├── plan/                       📄 00-overview … 55-ci-runner
│   ├── adr/                        📄 ADR-001 … ADR-015
│   ├── handoff/                    📄 HANDOFF.md (trạng thái mới nhất) + CHANGELOG.md
│   └── architecture_diagram.md     📄 sơ đồ Mermaid (deliverable #3)
├── requirements-runtime.txt        📄 dependency lúc chạy (image Docker cài file này)
├── requirements.txt                📄 `-r requirements-runtime.txt` + công cụ dev/test
├── Dockerfile, docker-compose.yml, render.yaml, render.test.yaml
└── data/                              (gitignore) raw/ dữ liệu tải về, app.db
```

Liệt kê toàn bộ việc còn stub, theo task (hiện 129 stub):

```bash
grep -rn 'NotImplementedError("\[T' src/ --include=*.py | sort -t'[' -k2
```

### Thành phần đích theo ADR-011 … ADR-014 (chưa có trong code của branch này)

Tên dưới đây lấy từ master context §5, §10 và ADR; chữ ký **chưa khoá**. Không có file nào trong số này tồn tại ở
`8f6f08a`.

| Thành phần | Vai trò | Nguồn / ADR |
|---|---|---|
| Simulator v1.2 (`src/simulator/src/engine/hybrid.py`, `queue.py`, `ev2gym_adapter.py`) | `HybridSimulator` + `QueueController`; AC native EV2Gym, DC = `SyntheticTaperV1` hoặc `VehicleProfilesDCModel` | Đã merge, **chỉ chạy R&D offline** — backend dùng `LiveStation` (ADR-016) · ADR-011 |
| `src/simulator/base.py` (bản mới) | Bề mặt công khai duy nhất của simulator; thay `StationReader` / `StationActuator` | ADR-011 |
| `Algorithms` (`src/simulator/src/algorithms.py`) | Một registry DispatchPolicy / ZonePowerOptimizer / GlobalCoordinator, dùng chung live / benchmark / what-if | ADR-011 |
| Guard hai lớp | Lớp vật lý (lưới, tủ, cổng, xe; pre-apply + post-apply) và lớp chính sách (ngân sách vùng, quyền, phê duyệt) | ADR-011 (sửa một phần ADR-002) |
| `SimulatorGateway` | Adapter hợp đồng giữa service và engine: `create_session`, `get_state`, `submit_request`, `advance`, `replan`, `get_decision_trace`, `simulate_what_if`, `apply_approved_revision`, `get_kpis` | master context §10.3 · ADR-011 |
| `DecisionTrace` | Trace từng interval: request / allowed / actual kW, constraint binding, reason code, `evidence_ref` | ADR-014 |
| Counterfactual sandbox | Chạy WHAT-IF trên session cách ly, cùng engine/seed; **luôn `applied=false`** | ADR-014 |
| Proposal / HITL | `PROPOSED → APPROVED / REJECTED / EXPIRED → APPLIED / APPLY_FAILED`; TTL, `state_version`, re-verify trước apply | ADR-014 |
| Copilot service | AI-4 WHY + WHAT-IF theo role; AI-1 đề nghị có HITL; tác vụ dài chạy job nền | ADR-014, ADR-015 |
| Bảng `proposals`, `consents`, `vehicle_revisions`, `audit_log` | Lưu vòng đời đề nghị, đồng ý, sửa cam kết theo thời điểm, audit | ADR-014 — **chưa có migration** ([40-database](docs/plan/40-database.md) §0) |

## Ranh giới module

Khoá bằng `tests/test_architecture.py`. Muốn nới một quy tắc thì sửa test đó **và** ghi ADR.

| Package | KHÔNG được import | Lý do |
|---|---|---|
| `src/agents` | `simulator`, `guard`, `optimizer`, `forecast`, `db`, `api` | FR5: Agent chỉ đi qua `services` |
| `src/api` | `guard`, `optimizer`, `simulator`, `forecast`, `db` | ADR-007: router chỉ gọi `services` (và `agents.graph` cho `/chat`) |
| `src/guard` | `agents`, `services.llm`, `api`, `db`, `optimizer`, `forecast` | F4: chạy được khi LLM sập |
| `src/optimizer` | `agents`, `api`, `services`, `simulator`, `guard`, `db`, `forecast` | thuần: context vào → plan ra |
| `src/forecast` | `agents`, `api`, `services`, `simulator`, `guard`, `optimizer`, `db` | thuần, train/eval offline |
| `src/simulator` | `agents`, `api`, `services`, `optimizer`, `guard`, `db`, `forecast` | adapter thuần |
| `src/db` | mọi package khác trừ `models`, `config` | ADR-005: persistence chỉ biết hợp đồng dữ liệu |
| `src/models` | mọi package khác trong `src/` (kể cả `config`) | hợp đồng dữ liệu đứng độc lập |

Các khoá bổ sung:

- Chỉ `src/guard/dispatcher.py` được import `StationActuator` hoặc gọi `.apply_commands` (ADR-002).
- Chỉ `src/db/` và `src/services/repository.py` được import `sqlalchemy` / `alembic` / `src.db`; chữ ký hàm của
  repository không lộ kiểu ORM (ADR-005).
- `src/models/` không dùng `sqlalchemy`, `fastapi`, `langchain`, `langgraph`, `openai`, `yaml`.
- `src/agents/` không tạo `Command`; tool của Agent chỉ gọi `src/services`.
- `frontend/src` không import gì ngoài `frontend/`, không đặt token trên URL (ADR-006, ADR-009).

`src/services` là tầng tích hợp (không có quy tắc cấm riêng): nó nối các trụ lại với nhau qua `StationRuntime`.

## Truy vết yêu cầu → module → test

`✅` = test đang chạy · `⏭` = test đã viết, đang `skip` kèm lý do + task ID (bỏ `skip` khi làm task đó).

| Yêu cầu | Module chính | Owner | Task | Test / bằng chứng |
|---|---|---|---|---|
| FR1 đăng nhập 2 vai trò | `api/auth.py`, `api/deps.py`, `services/auth.py` | TV3 | T1.7 | ✅ `test_api/test_contract.py`, `test_errors.py` (401/403) · ⏭ `test_service_contracts.py::test_token_roundtrip` |
| FR2 trích xuất yêu cầu | `models/charging.py:ChargeRequest`, `agents/tools/charging.py`, `prompts/charging_domain.md` | TV3 | T2.5 | ✅ `test_models/test_contracts.py`, `test_agents/test_charging_agent.py` · ⏭ `test_flows.py::test_chat_asks_for_missing_field_then_continues` |
| FR3 kWh do code tính | `services/energy.py` | TV3 | — | ✅ `test_services/test_energy.py` · ⏭ `test_flows.py::test_chat_booking_kwh_matches_fr3` |
| FR4 phương án thay thế | `ScheduleProposal` validator, `charging_service.quote` | TV1/TV3 | T2.2 | ✅ `test_models` · ⏭ `test_infeasible_quote_has_alternative` |
| FR5 Agent không ra lệnh trạm | ranh giới import | TV3 | — | ✅ `test_architecture.py` |
| FR6 tối ưu công suất (LP liên tục + receding horizon; không phải MILP) | `optimizer/mpc.py`, `lp_model.py` (đích: ZonePowerOptimizer AC/DC trong simulator, ADR-011) | TV1 | T2.1 | ⏭ `test_optimizer/test_optimizer_contracts.py` (giới hạn tổng, giá rẻ, tất định) |
| FR7, AC2 gán đầu nối, hàng đợi | `optimizer/assignment.py`, `simulator/parking_queue.py` | TV1/TV3 | T2.2 | ⏭ `test_waiting_cars_are_ordered_by_earliest_deadline`, `test_flows.py::test_walk_in_when_full_gets_queue_position` |
| FR8 tính lại khi có sự kiện | `services/control_loop.py`, `event_bus.py`, `runtime.py` | TV3 | T2.6 | ⏭ `test_every_event_type_triggers_replan`, `test_concurrent_events_are_serialized`, `test_change_booking_triggers_replan` |
| FR9 deadline là ràng buộc cứng | `PlanningContext`, `lp_model` | TV1 | T2.1 | ⏭ `test_forecast_never_relaxes_declared_deadline`, `test_no_energy_is_scheduled_after_declared_deadline` |
| FR10–11 cân bằng tải, simulator | `simulator/*` | TV3/TV1 | T1.4 | ✅ `test_simulator/test_factory.py` · ⏭ `test_adapter_contract_*` |
| FR12, AC6 7 luật Guard | `guard/rules.py`, `checker.py`, `dispatcher.py` | TV3 | T3.1 | ✅ `test_guard/test_checker.py` · ⏭ `test_each_rule_blocks_its_violation`, `test_blocked_command_never_reaches_actuator` |
| FR13, AC4 phê duyệt | `guard/approval.py`, `control_loop.resolve_approval` | TV3 | T3.2 | ⏭ `test_guard/test_dispatcher.py` (trong/ngoài phạm vi đồng ý, re-check), `test_expired_approval_is_never_applied` |
| AC5 bảo vệ khẩn cấp | `guard/emergency.py` | TV3 | T3.2 | ⏭ `test_emergency_command_is_never_held_for_approval`, `test_power_drop_is_curtailed_before_replan` |
| FR14 nhật ký quyết định | `DecisionLogEntry`, `repository.append_decision`, bảng `decision_log` | TV3 | T1.6 | ✅ `test_decision_log_has_no_update_or_delete_function` · ⏭ `test_decision_log_is_append_only_and_ordered` |
| FR15–16 web 2 vai trò, WS | `api/resident.py`, `operations.py`, `ws.py`, `services/realtime.py`, `frontend/` | TV4 | T2.7, T3.6 | ✅ `test_contract.py`, `test_openapi_snapshot.py`, vitest (24 test) · ⏭ `test_ws_requires_auth_message` |
| FR17, MT7 dự báo F6 — **HOÃN** (ADR-015) | `forecast/*` | TV2 | T2.3 | HOÃN; test hiện có giữ nguyên: ✅ `test_label_is_forbidden_as_feature` · ⏭ `test_unplug_time_never_leaks`, `test_split_is_temporal_not_random` |
| FR18, AC7 sự cố + đối chứng A–D | `config/scenarios/`, `simulation_service`, `simulator/kpi.py`, `eval/run_benchmark.py` | TV1 | T3.4, T3.5 | ✅ `test_services/test_catalog.py`, `test_kpi_report_covers_every_prd_metric` · ⏭ KPI theo từng bước |
| AC1 đặt lịch qua chat | `api/routes.py`, `agents/graph.py`, `charging_service` | TV3 | T2.5 | ✅ `test_charging_agent.py` (interrupt mang phương án, xác nhận một lần) · ⏭ `test_flows.py::test_chat_booking_kwh_matches_fr3` |
| AC3 cao điểm tối | `simulation_service.run_scenario` | TV1 | T3.4 | ⏭ `test_peak_evening_respects_limit_and_meets_deadlines` |
| AC8 deploy + 2 vai trò | `Dockerfile`, `render.yaml`, `.github/workflows/ci.yml`, Vercel | TV4 | T4.4 | job CI `docker-smoke`: build image + `/health`, `/ready` trong container |
| MT5 tính lại ≤ 2 s | `control_loop.on_event` | TV1/TV3 | T3.7 | ⏭ `test_replan_p95_under_two_seconds` |
| Idempotency đặt lịch (ADR-008) | `charging_service.book`, bảng `idempotency_keys` | TV3 | T2.2 | ✅ `test_one_active_booking_per_resident_is_enforced_by_database` · ⏭ `test_double_confirm_creates_one_booking` |

Ghi chú 21/11: AC3 và AC5 trong bảng trên còn viết theo giới hạn 35 kW của bản cũ; con số nghiệm thu mới lấy theo
PRD v0.4 và fixture ADR-010. Phần hướng mới **chưa có module hay test** trong branch này:

| Yêu cầu (hướng mới) | Module đích | ADR | Test |
|---|---|---|---|
| MVP-1 hồi quy `mvp1` (9/9, năng lượng khớp) | simulator v1.2 (`feature/simulator`) | ADR-010, ADR-011 | `src/simulator/tests` ở branch `feature/simulator` (112 passed với `PYTHONUTF8=1`, `eval/evidence/2026-11-21/`) — chưa có trong branch này |
| MVP-2/3 DC LP, AC optimizer, Global Coordinator | `Algorithms` (ADR-011) | ADR-011 | chưa có |
| AI-4 WHY | `DecisionTrace` + Copilot service | ADR-014 | chưa có |
| AI-4 WHAT-IF, isolation | counterfactual sandbox | ADR-014 | chưa có |
| AI-1 Proposal + HITL | proposal lifecycle, bảng `proposals` / `consents` / `vehicle_revisions` / `audit_log` | ADR-014 | chưa có |
| F14 chiếm cổng `FINISHED_PLUGGED` (Should) | simulator v1.2 (đã mô phỏng AC giữ cổng, DC rút sau 5 phút) | ADR-015 | chưa có trong branch này |

## API contract (theo màn hình)

Swagger tại `/docs` hiện đủ schema request/response. Tiền tố `/api/v1`; `/health` và `/ready` ở gốc.
Snapshot hợp đồng: `frontend/openapi.json` (`python scripts/export_openapi.py`; test `test_openapi_snapshot.py` báo khi lệch).

| Màn | Endpoint | Trạng thái |
|---|---|---|
| hệ thống | `GET /health`, `GET /ready` (config + database), `GET /api/v1/status` | ✅ |
| danh mục | `GET /vehicles`, `POST /energy/estimate`, `GET /station/config`, `GET /tariff` | ✅ công khai |
| S1 | `POST /auth/login`, `GET /auth/me` | 🧩 T1.7 |
| S2 | `POST /chat`, `POST /chat/resume` (token cư dân) · `GET /resident/bookings/current`, `/resident/session`, `/resident/notifications`, `POST /resident/notifications/{id}/read` | chat ✅ khi có LLM key + T1.7 · còn lại 🧩 |
| S3 | `POST /resident/quote`, `POST /resident/bookings` (`Idempotency-Key`), `PATCH`/`DELETE /resident/bookings/{id}`, `GET /resident/explanation` | 🧩 T2.2, T2.8, T2.5 |
| S4 | `GET`/`POST /resident/approvals/{id}` | 🧩 T3.2 |
| US2 | `GET /resident/queue` | 🧩 T2.2 |
| hồ sơ (NFR riêng tư) | `GET`/`PUT`/`DELETE /resident/profile` | 🧩 T2.8 |
| S5 | `GET /operator/station`, `/operator/load`, `/operator/connectors/{id}`, `/operator/events` | 🧩 T3.6 |
| S6 | `GET /operator/schedule`, `/operator/bookings`, `POST /operator/schedule/replan`, `POST /operator/queue/{id}/assign` | 🧩 T3.6, T3.2 |
| S7 | `GET /operator/approvals`, `POST /operator/approvals/{id}`, `GET /operator/commands/blocked`, `/operator/decision-log` | 🧩 T3.2, T1.6 |
| S8 | `GET /simulation/scenarios`, `POST /simulation/runs`, `POST /simulation/incidents`, `GET /simulation/benchmark` | 🧩 T3.4, T3.5 |
| realtime | `WS /api/v1/ws/operator`, `WS /api/v1/ws/resident` | 🧩 T3.6 (đóng 1011) |

Quy ước (ADR-008):

- **Envelope lỗi**: `{"detail", "code", "request_id"}` + `task_id` (và `status: "not_implemented"`) khi 501.
  Lỗi nghiệp vụ là `DomainError(code, detail)`; bảng `code` → HTTP status ở `src/services/errors.py`.
- **`X-Request-ID`**: nhận từ client nếu hợp lệ, không thì tự sinh; trả lại ở header và trong thân lỗi.
- **Auth**: thiếu token → 401, sai vai trò → 403. Mọi endpoint cần đăng nhập hiện trả **501 `T1.7`** khi có token,
  vì `services.auth.decode_token` còn là stub — T1.7 là cửa của gần hết API.
- **`/chat`**: lỗi nhà cung cấp LLM → 503 `llm_unavailable` (web chuyển sang form `/resident/book`).

## Frontend (TV4)

`frontend/` — Next.js 16 (App Router, Cache Components), React 19, TypeScript, Tailwind 4, TanStack Query,
`openapi-fetch`. Chi tiết: [`frontend/README.md`](frontend/README.md), [`docs/plan/20-frontend.md`](docs/plan/20-frontend.md).

| Màn | Route | Dữ liệu |
|---|---|---|
| S1 Đăng nhập | `/login` | `/auth/login`; resident → `/resident`, operator → `/operator` |
| S2 Trang chủ cư dân | `/resident` | `/chat`, `/vehicles`, `/resident/bookings/current`, WS resident |
| Form đặt lịch (không cần LLM) | `/resident/book` | `/energy/estimate` → `/resident/quote` |
| S3 Xác nhận lịch | `/resident/plan` | `proposal` của `/chat` → `/chat/resume`, hoặc `/resident/bookings` |
| S4 Thông báo HITL | `/resident/notifications`, `/resident/notifications/[approvalId]` | `/resident/notifications`, `/resident/approvals/{id}` |
| Hồ sơ | `/resident/profile` | `/resident/profile` |
| S5 Dashboard | `/operator` | `/operator/station`, `/operator/load`, WS operator |
| S6 Hàng đợi & lịch | `/operator/schedule` | `/operator/schedule`, `/operator/bookings` |
| S7 Duyệt lệnh | `/operator/approvals` | `/operator/approvals`, `/operator/commands/blocked`, `/operator/decision-log` |
| S8 Mô phỏng | `/operator/simulation` | `/simulation/*` |

- **Type**: `src/lib/api/schema.d.ts` sinh từ `openapi.json` (`npm run gen:api`), không gõ tay.
- **501**: mỗi trang gọi đúng endpoint của mình; backend trả 501 thì hiện khối "chưa được cài đặt — task Txx".
- **Backend ngủ** (Render free): banner gọi `/health` ở layout gốc để đánh thức; truy vấn có chính sách thử lại.
- **Env**: `NEXT_PUBLIC_API_URL` (+ `NEXT_PUBLIC_WS_URL`); Vercel đặt **Root Directory = `frontend`**; backend đặt
  `CORS_ORIGINS` = domain Vercel (bản test dùng thêm `CORS_ORIGIN_REGEX` cho URL preview).
- **AI-log**: luôn mở Claude Code / Cursor / Codex… ở **repo root** `P-019/`, không mở ở `frontend/` (hook dùng đường
  dẫn tương đối `scripts/…`).

## Data Flow

### Đích theo ADR-011 / ADR-013 / ADR-014 (chưa có trong code)

1. Cư dân chat (LLM trích trường, hỏi lại chỗ thiếu) hoặc điền form → `ChargeRequest` có schema → cư dân xác nhận.
2. `charging_service.quote` / `book` → `SimulatorGateway.submit_request` → `HybridSimulator` + `QueueController`.
3. Mỗi interval: DispatchPolicy (cổng trống) → ZonePowerOptimizer AC/DC → GlobalCoordinator → Guard vật lý (pre-apply)
   → EV2Gym adapter → kiểm công suất thực (post-apply) → `DecisionTrace`, KPI, sự kiện.
4. WHY đọc `DecisionTrace`; WHAT-IF chạy counterfactual sandbox (`applied=false`); AI-1 sinh option đã mô phỏng →
   Proposal → cư dân / vận hành duyệt → re-verify → `vehicle_revisions` + audit.
5. LLM chỉ diễn đạt facts đã tính; không có đường nào từ LLM tới công suất.

### Hiện có trong code (đúng tới 22/11)

1. Cư dân chat hoặc điền form → `ChargeRequest` (validator chặn dữ liệu sai ngay tại ranh giới).
2. `charging_service.quote` → optimizer what-if → `ScheduleProposal` (S3). Không giữ chỗ.
3. Xác nhận (interrupt của graph / form) → `charging_service.book` (async, idempotent) → lưu `Booking` →
   `event_bus.publish(BOOKING_CREATED)`.
4. `control_loop.on_event(event, rt)`: `build_planning_context` → (forecast) → `rt.scheduler.plan` → `diff_commands`.
5. `guard.dispatcher.submit(commands, ctx, actuator, sinks)`: checker → (approval) → `apply_commands` → `DecisionLogEntry`.
6. `sinks.notify` → `services.realtime.broadcast` → WebSocket đẩy `schedule_changed` / `approval_request` /
   `command_blocked` lên web.
7. Trạm là `LiveStation`; vòng nền `control_loop.run_forever` (bật trên deploy) tiến đồng hồ trạm, phát `TICK` để tính
   lại lịch và cho phê duyệt quá hạn hết hiệu lực.

Benchmark chạy **cùng** `on_event` và cùng đường Guard, chỉ khác `StationRuntime`
(`build_sim_runtime`: đồng hồ mô phỏng, sinks vào bộ nhớ) — ADR-007.

## Persistence (ADR-005)

- SQLAlchemy 2 (đồng bộ) + Alembic. Local / CI: SQLite (`DATABASE_URL` rỗng → `sqlite:///./data/app.db`).
  Deploy: Postgres trên Neon (`postgresql://…` được chuẩn hoá thành `postgresql+psycopg://`).
- Schema chỉ đổi qua migration: sửa `src/db/tables.py` → `alembic revision --autogenerate` → **đọc lại file sinh ra**.
- Container chạy `alembic upgrade head` trước `uvicorn` (migration lỗi → container không lên → hosting giữ bản cũ).
- Trạng thái trong RAM (runtime của trạm, sổ WebSocket, checkpoint chat) không bền → container chạy **một** worker.

## Security

- Secret chỉ ở `.env` (không commit) hoặc biến môi trường trên hosting (`sync: false`). `APP_ENV=production` mà thiếu
  `OPENAI_API_KEY` → app từ chối khởi động.
- Danh tính (ADR-006): JWT HS256 hai vai trò; mật khẩu băm bằng `hashlib.scrypt`; tài khoản demo seed từ
  `SEED_USERS_JSON`. `resident_id` đi trong `config["configurable"]` — **LLM không đọc, không ghi được**.
- WebSocket xác thực bằng bản tin đầu `{"type": "auth", "token"}`; không nhận token qua query string.
- Input LLM: guardrail ở code (`agents/guardrails.py`) và ở prompt (`prompts/charging_safeguards.md`).
  Lệnh trạm: Guard 7 luật (`guard/`), không phụ thuộc LLM.
- Dữ liệu: chỉ dùng dữ liệu công khai hoặc giả lập; xoá tài khoản = ẩn danh hoá, giữ nhật ký (NFR riêng tư).
- CORS chỉ mở cho domain frontend (`CORS_ORIGINS`).

## Design Decisions

| Quyết định | Lựa chọn | ADR |
|---|---|---|
| Agent framework | Giữ LangGraph ReAct harness của template (sửa một phần bởi ADR-013: LangGraph chỉ cho hội thoại + HITL) | [ADR-001](docs/adr/ADR-001-giu-langgraph-cho-f1.md) |
| Đường tới trạm | Guard dispatcher là chokepoint duy nhất; simulator tách Reader/Actuator | [ADR-002](docs/adr/ADR-002-guard-chokepoint.md) |
| Tham số mô phỏng | `config/*.yaml` + Pydantic validate | [ADR-003](docs/adr/ADR-003-tham-so-trong-config.md) |
| Skeleton | Contract-first: đủ schema, stub trả 501 kèm mã task | [ADR-004](docs/adr/ADR-004-contract-first-501.md) |
| Persistence | SQLAlchemy 2 + Alembic sau `services/repository.py`; SQLite local, Neon Postgres khi deploy | [ADR-005](docs/adr/ADR-005-persistence-sqlalchemy-alembic.md) |
| Danh tính | JWT, `resident_id` phía server, WebSocket xác thực bằng bản tin đầu | [ADR-006](docs/adr/ADR-006-danh-tinh-jwt-resident-id-server-side.md) |
| Điều phối | `StationRuntime` là composition root; sự kiện xử lý ngay trong request | [ADR-007](docs/adr/ADR-007-station-runtime-va-control-loop.md) |
| Quy ước API | Envelope lỗi, idempotency, versioning, `/ready` | [ADR-008](docs/adr/ADR-008-quy-uoc-api.md) |
| Frontend | Next.js trong `frontend/`, chỉ nhận `openapi.json` từ backend | [ADR-009](docs/adr/ADR-009-frontend-nextjs.md) |
| Bài toán | Bãi hybrid AC/DC, fixture nền `mvp1`, ràng buộc ba tầng, `supply_mode` | [ADR-010](docs/adr/ADR-010-bai-hybrid-ac-dc.md) |
| Simulator (đích) | Một `HybridSimulator` sau `src/simulator/base.py` + `SimulatorGateway`; một bộ `Algorithms`; Guard hai lớp | [ADR-011](docs/adr/ADR-011-mot-simulator-sau-be-mat-cong-khai.md) |
| Simulator (hiện tại) | `LiveStation` cho backend (live + benchmark backend); `HybridSimulator` là R&D offline; không trộn số liệu | [ADR-016](docs/adr/ADR-016-livestation-cho-backend.md) |
| Dữ liệu cấu hình | Một danh mục xe có provenance từng trường + mọi kịch bản trong `config/scenarios/` | [ADR-012](docs/adr/ADR-012-mot-danh-muc-xe-va-kich-ban.md) |
| Vai trò LLM | Workflow xác định là xương sống; LLM ở hai đầu; LangGraph cho hội thoại + HITL | [ADR-013](docs/adr/ADR-013-workflow-xac-dinh-llm-hai-dau.md) |
| AI-4 / AI-1 | `DecisionTrace`, counterfactual không apply, Proposal/HITL, Copilot theo role, job nền | [ADR-014](docs/adr/ADR-014-decision-trace-counterfactual-hitl.md) |
| Phạm vi + bằng chứng | MVP-4, hạng mục hoãn, số liệu chỉ từ `eval/evidence/` | [ADR-015](docs/adr/ADR-015-pham-vi-mvp4-va-quy-tac-bang-chung.md) |
