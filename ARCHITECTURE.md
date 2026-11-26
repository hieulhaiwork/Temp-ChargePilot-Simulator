# Architecture Document — ChargePilot

> Điều phối lịch và công suất cho một bãi sạc EV hỗn hợp AC + DC — đề tài SC-16, nhóm T019. Hệ thống là
> **simulation-only**.
> **Nguồn hiện trạng (24/11):** chức năng nào đã làm, test và bằng chứng nào → [`docs/FEATURE_REGISTRY.md`](docs/FEATURE_REGISTRY.md).
> Hiểu hệ thống theo 4 tầng (nghiệp vụ → kiến trúc → nguyên lý → kiểm chứng), sơ đồ hiện trạng và 3 luồng chính →
> [`docs/architecture_diagram.md`](docs/architecture_diagram.md). File này giữ sườn thư mục, ranh giới module,
> persistence, bảo mật. Một số đoạn dưới đây viết ngày 21–23/11; chỗ mâu thuẫn với registry hoặc code thì registry /
> code đúng.
> Quyết định kiến trúc + phân loại cần duyệt: [`docs/adr/`](docs/adr/README.md) (ADR-001 … ADR-019).
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
> **Hiện trạng 23/11 (ADR-018, ADR-019 — refactor Unified Core, Phase 4):** backend — chạy thật, mô phỏng S8,
> `eval/run_benchmark.py`, admission (quote / booking trên bản fork) — chạy `HybridStation` trên **một kernel**
> `StationKernel` dùng chung với `HybridSimulator`. `LiveStation` và LP backend A–D đã xoá
> (`docs/refactor/DELETION_MANIFEST.md`); policy = B0 / M2b / M3a / M3b (`src/optimizer/registry.py`). Cây thư mục bên
> dưới đã sửa các mục optimizer / simulator; bản đồ đầy đủ sau refactor sẽ ở `docs/refactor/FINAL_MAP.md`.

Kiến trúc 3 tầng: Frontend Next.js (`frontend/`) → Backend FastAPI (`src/`) → lõi tính toán, cộng tầng lưu trữ
SQLAlchemy (`src/db/`). Hướng đích ([ADR-013](docs/adr/ADR-013-workflow-xac-dinh-llm-hai-dau.md)): **workflow xác
định là xương sống** — Dispatch → AC/DC Optimizer → Global Coordinator → Guard. Đã chạy thật trên kernel chung
([ADR-019](docs/adr/ADR-019-unified-core-hop-dong-dung-chung.md), thay [ADR-016](docs/adr/ADR-016-livestation-cho-backend.md)). LLM chỉ ở hai đầu: hiểu câu (intake,
intent, patch có schema) và diễn đạt kết quả đã tính. LangGraph giữ cho hội thoại + HITL interrupt.

Nguyên tắc 3 trụ của Brief vẫn giữ:

1. **AI hiểu yêu cầu và giải thích** (chat cư dân `src/llm_chat/`; AI-1 / Copilot WHY/WHAT-IF theo ADR-014 sẽ ở
   `src/agents/`)
2. **Bộ tối ưu tính phương án** (`src/optimizer/`; `src/forecast/` **HOÃN** theo ADR-015)
3. **Bộ kiểm tra an toàn kiểm soát thực thi** (`src/guard/`): cửa duy nhất tới trạm giả lập (`src/simulator/`);
   ADR-011 tách hai lớp vật lý + chính sách

Quy ước contract-first (ADR-004) vẫn giữ: phần chưa làm `raise NotImplementedError("[Txx] …")` và API trả HTTP 501
kèm `task_id`. Hiện chỉ còn dự báo (F12, "F6 cũ") dùng quy ước này. Simulator đã nằm trong `src/simulator/` (kernel
chung với backend, ADR-019).

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
│   │   │                              ConsentScope, ScheduleProposal (FR4, certainty), SchedulePlan, StrategyName B0–M3b
│   │   ├── control.py                 Role, Command, GuardRule (7 luật), GuardVerdict, Approval, DecisionLogEntry
│   │   ├── events.py                  EventType (FR8), StationEvent, WsMessage + payload có kiểu (FR16)
│   │   ├── simulation.py              Scenario, Incident, SimulationTrace, KpiReport (MT1–MT6), BenchmarkReport
│   │   └── api.py                     DTO của API: Login, ErrorResponse/ErrorCode, ReadinessReport, QueueStatus, …
│   ├── agents/                     dành cho AI-1 / AI-4 (ADR-019) — chỉ có __init__.py, chưa có code
│   ├── llm_chat/                   TRỤ 1 — F1 chat cư dân (TV3)
│   │   ├── graph.py                ✅ entry → guardrail_check → reason → act → (human_review) → assess → finalize
│   │   ├── state.py                ✅ AgentState: vòng ReAct + turn_context, history, draft_request, proposal
│   │   ├── prompts.py              ✅ load_prompt / render (fail khi thiếu biến)
│   │   ├── schemas.py              ✅ AgentDecision / FinalAnswer / AgentAnswer (nội bộ, không ở OpenAPI)
│   │   ├── guardrails.py           ✅ chặn injection (có mẫu tiếng Việt) · 🧩 check_grounded_numbers (T2.5)
│   │   ├── nodes/                  ✅ reason, act, human_review, assess, finalize (nhận RunnableConfig)
│   │   │                              (giữ) safety, validate — pipeline RAG template còn test dùng
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
│   │   ├── admission.py            ✅ quote / booking / đổi yêu cầu trên bản fork, ước tính có điều kiện (ADR-019)
│   │   └── simulation_service.py   ✅ chạy kịch bản S8 + benchmark B0–M3b + baseline có version (T3.4, T3.5)
│   ├── db/                         TẦNG LƯU TRỮ (ADR-005) — chỉ repository.py được gọi vào
│   │   ├── base.py, types.py       ✅ DeclarativeBase, UtcDateTime (từ chối datetime không múi giờ)
│   │   ├── tables.py               ✅ 10 bảng: users, bookings, idempotency_keys, schedule_plans, approvals,
│   │   │                              decision_log, notifications, station_events, load_points, decision_traces
│   │   ├── session.py              ✅ engine + session_scope; chuẩn hoá URL Neon → postgresql+psycopg://
│   │   └── mappers.py              🧩 Row ↔ model Pydantic (T1.6)
│   ├── optimizer/                  TRỤ 2 — F2/F3 (TV1) — code thuần
│   │   ├── dispatch/, zones/       ✅ dispatch FCFS / EDF / LLF; LP vùng AC / DC (HiGHS), equal share — gốc simulator
│   │   ├── coordination/           ✅ Global Coordinator (fixed share / dynamic slack)
│   │   └── registry.py             ✅ POLICIES B0 / M2b / M3a / M3b (version 1). A–D (LP backend) đã xoá ở ADR-019
│   ├── forecast/                   F12 (= "F6 cũ") — HOÃN khỏi sprint 20–26/11 (ADR-015); stub giữ nguyên, không làm
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
│   │   ├── core/                   ✅ MỘT StationKernel (kernel.py) + queue / ev2gym_adapter / charging_models / algorithms — ADR-019
│   │   ├── hybrid.py               ✅ HybridSimulator = kernel + trace / report (CLI, benchmark MVP-1/2/3, golden)
│   │   ├── hybrid_station.py       ✅ HybridStation: trạm backend trên cùng kernel (StationReader / StationActuator ở src/models/station_protocols.py)
│   │   ├── evaluation/             ✅ KPI, DecisionTrace (schema dùng chung simulator ↔ backend)
│   │   ├── run.py, benchmark*.py   ✅ CLI chạy HybridSimulator standalone
│   │   └── tests/                  ✅ bộ test R&D (golden regression), job CI `simulator`
│   └── api/                        REST + WebSocket — router chỉ gọi src/services
│       ├── deps.py                 ✅ get_current_user, ResidentUser, OperatorUser (401/403)
│       ├── catalog.py              ✅ /vehicles, /energy-estimates, /station/config, /tariff (công khai)
│       ├── routes.py               ✅ /chat, /chat/sessions/{id} (PATCH resume, token cư dân), /status
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
│   ├── test_models/, test_services/, test_guard/, test_optimizer/, test_forecast/, test_simulator/, test_llm_chat/
├── eval/
│   ├── run_agent_eval.py           ✅ --offline (kiểm dataset + ngưỡng) · 🧩 chạy Agent thật (T4.2)
│   ├── run_benchmark.py            ✅ benchmark B0 / M2b / M3a / M3b → results/benchmark.{md,json}, source generated (T3.4)
│   ├── evidence/*-baseline/        📄 baseline có version (manifest.json) — S8 đọc; results/archive/: bảng A–D deprecated
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

### Thành phần đích theo ADR-011 … ADR-014 (bảng lịch sử 21/11)

> **Lỗi thời một phần (24/11):** simulator, bộ thuật toán chung, Guard hai lớp và DecisionTrace **đã có**;
> `src/simulator/base.py` và `SimulatorGateway` **không được làm** (thay bằng `StationKernel`, ADR-019); sandbox, Proposal
> / HITL, Copilot, bảng AI-1 **chưa có**. Hiện trạng đúng: [`docs/FEATURE_REGISTRY.md`](docs/FEATURE_REGISTRY.md) §2, §4.

| Thành phần | Vai trò | Nguồn / ADR |
|---|---|---|
| Simulator v1.2 (`src/simulator/core/kernel.py`, `hybrid.py`, `core/queue.py`, `core/ev2gym_adapter.py`) | `HybridSimulator` + `QueueController`; AC native EV2Gym, DC = `SyntheticTaperV1` hoặc `VehicleProfilesDCModel` | Đã merge; backend dùng cùng kernel qua `HybridStation` (ADR-018, ADR-019) |
| `src/simulator/base.py` (bản mới) | Bề mặt công khai duy nhất của simulator; thay `StationReader` / `StationActuator` | ADR-011 |
| `Algorithms` (`src/simulator/core/algorithms.py`) | Một registry DispatchPolicy / ZonePowerOptimizer / GlobalCoordinator, dùng chung live / benchmark / what-if | ADR-011 |
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
| `src/llm_chat` | `simulator`, `guard`, `optimizer`, `forecast`, `db`, `api`, `agents` | FR5: chat chỉ đi qua `services` |
| `src/agents` | `simulator`, `guard`, `optimizer`, `forecast`, `db`, `api`, `llm_chat` | ADR-019: AI-1 / AI-4 chỉ đi qua `services` |
| `src/api` | `guard`, `optimizer`, `simulator`, `forecast`, `db` | ADR-007: router chỉ gọi `services` (và `llm_chat.graph` cho `/chat`) |
| `src/guard` | `agents`, `services.llm`, `api`, `db`, `optimizer`, `forecast`, `simulator` | F4: chạy được khi LLM sập; không import simulator để tránh vòng (ADR-019) |
| `src/optimizer` | `agents`, `api`, `services`, `simulator`, `guard`, `db`, `forecast` | thuần: context vào → plan ra |
| `src/forecast` | `agents`, `api`, `services`, `simulator`, `guard`, `optimizer`, `db` | thuần, train/eval offline |
| `src/simulator` | `agents`, `api`, `services`, `db`, `forecast` | chạy standalone; được dùng `optimizer` và Guard vật lý (ADR-019) |
| `src/db` | mọi package khác trừ `models`, `config` | ADR-005: persistence chỉ biết hợp đồng dữ liệu |
| `src/models` | mọi package khác trong `src/` (kể cả `config`) | hợp đồng dữ liệu đứng độc lập |

Các khoá bổ sung:

- Chỉ `src/guard/dispatcher.py` được import `StationActuator` hoặc gọi `.apply_commands` (ADR-002).
- Chỉ `src/db/` và `src/services/repository.py` được import `sqlalchemy` / `alembic` / `src.db`; chữ ký hàm của
  repository không lộ kiểu ORM (ADR-005).
- `src/models/` không dùng `sqlalchemy`, `fastapi`, `langchain`, `langgraph`, `openai`, `yaml`.
- `src/llm_chat/` và `src/agents/` chỉ import `src.services`, `src.models`, `src.config`, không tạo `Command`; tool
  của chat chỉ gọi `src/services`. `src/agents/` thêm: không `sqlalchemy` / `src.db` / `services.repository` /
  `StationActuator` / `src.guard`. Ngoài `src/llm_chat`, chỉ `src/api` import `src.llm_chat.graph` (ADR-019).
- `frontend/src` không import gì ngoài `frontend/`, không đặt token trên URL (ADR-006, ADR-009).

`src/services` là tầng tích hợp (không có quy tắc cấm riêng): nó nối các trụ lại với nhau qua `StationRuntime`.

## Truy vết yêu cầu → module → test

Đã chuyển sang [`docs/FEATURE_REGISTRY.md`](docs/FEATURE_REGISTRY.md) §3 (2026-11-24). Bảng cũ ở đây dùng hệ mã
skeleton (FR12 = Guard, FR17 = dự báo…), dẫn 4 test không tồn tại và ghi nhiều test là "skip" trong khi chúng đang
chạy, nên đã gỡ. Ánh xạ mã cũ → mã PRD v0.4: registry §1. Bản cũ: `git log -p -- ARCHITECTURE.md`.

## API contract (theo màn hình)

Swagger tại `/docs` hiện đủ schema request/response. Tiền tố `/api/v1`; `/health` và `/ready` ở gốc.
Snapshot hợp đồng: `frontend/openapi.json` (`python scripts/export_openapi.py`; test `test_openapi_snapshot.py` báo khi lệch).

| Màn | Endpoint | Trạng thái |
|---|---|---|
| hệ thống | `GET /health`, `GET /ready` (config + database), `GET /api/v1/status` | ✅ |
| danh mục | `GET /vehicles`, `GET /energy-estimates`, `GET /station/config`, `GET /tariff` | ✅ công khai |
| S1 | `POST /auth/login`, `GET /auth/me` | 🧩 T1.7 |
| S2 | `POST /chat`, `PATCH /chat/sessions/{id}` (token cư dân) · `GET /resident/bookings/current`, `/resident/session`, `/resident/notifications`, `PATCH /resident/notifications/{id}` | chat ✅ khi có LLM key + T1.7 · còn lại 🧩 |
| S3 | `POST /resident/quotes`, `POST /resident/bookings` (`Idempotency-Key`), `PATCH`/`DELETE /resident/bookings/{id}`, `GET /resident/explanation` | 🧩 T2.2, T2.8, T2.5 |
| S4 | `GET`/`PATCH /resident/approvals/{id}` | 🧩 T3.2 |
| US2 | `GET /resident/queue` | 🧩 T2.2 |
| hồ sơ (NFR riêng tư) | `GET`/`PUT`/`DELETE /resident/profile` | 🧩 T2.8 |
| S5 | `GET /operator/station`, `/operator/load`, `/operator/connectors/{id}`, `/operator/events` | 🧩 T3.6 |
| S6 | `GET /operator/schedule`, `/operator/bookings`, `POST /operator/schedule/replans`, `POST /operator/bookings/{id}/assignments` | 🧩 T3.6, T3.2 |
| S7 | `GET /operator/approvals`, `PATCH /operator/approvals/{id}`, `GET /operator/commands/blocked`, `/operator/decision-log` | 🧩 T3.2, T1.6 |
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
| Form đặt lịch (không cần LLM) | `/resident/book` | `/energy-estimates` → `/resident/quotes` |
| S3 Xác nhận lịch | `/resident/plan` | `proposal` của `/chat` → `PATCH /chat/sessions/{id}`, hoặc `/resident/bookings` |
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

Luồng dữ liệu hiện trạng (đặt lịch, vòng điều khiển, sự cố) có sơ đồ tuần tự tại
[`docs/architecture_diagram.md`](docs/architecture_diagram.md) §2.5. Phần AI-4 / AI-1 (WHY, WHAT-IF, Proposal) **chưa có
code**: xem PRD §6.7–6.9 cho yêu cầu, registry §2 cho hiện trạng.

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
- Input LLM: guardrail ở code (`llm_chat/guardrails.py`) và ở prompt (`prompts/charging_safeguards.md`).
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
| Simulator (hiện tại) | Một kernel `StationKernel`: `HybridStation` (backend) + `HybridSimulator` (CLI / golden); `LiveStation` đã xoá; không trộn số khác `TimeConfig` | [ADR-018](docs/adr/ADR-018-backend-chay-engine-simulator.md), [ADR-019](docs/adr/ADR-019-unified-core-hop-dong-dung-chung.md) (thay ADR-016) |
| Dữ liệu cấu hình | Một danh mục xe có provenance từng trường + mọi kịch bản trong `config/scenarios/` | [ADR-012](docs/adr/ADR-012-mot-danh-muc-xe-va-kich-ban.md) |
| Vai trò LLM | Workflow xác định là xương sống; LLM ở hai đầu; LangGraph cho hội thoại + HITL | [ADR-013](docs/adr/ADR-013-workflow-xac-dinh-llm-hai-dau.md) |
| AI-4 / AI-1 | `DecisionTrace`, counterfactual không apply, Proposal/HITL, Copilot theo role, job nền | [ADR-014](docs/adr/ADR-014-decision-trace-counterfactual-hitl.md) |
| Phạm vi + bằng chứng | MVP-4, hạng mục hoãn, số liệu chỉ từ `eval/evidence/` | [ADR-015](docs/adr/ADR-015-pham-vi-mvp4-va-quy-tac-bang-chung.md) |
