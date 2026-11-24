# Architecture Decision Records — ChargePilot

Mỗi quyết định kiến trúc lớn có một file `ADR-XXX-<tên>.md` theo cấu trúc
**Bối cảnh → Lựa chọn → Quyết định → Hệ quả** (Technical Book chương 3).
Trạng thái: `Proposed` (đề xuất, chờ nhóm/mentor), `Accepted`, `Superseded by ADR-YYY`.

| ADR | Quyết định | Trạng thái |
|---|---|---|
| [ADR-001](ADR-001-giu-langgraph-cho-f1.md) | Giữ LangGraph ReAct harness của template cho Agent F1 | Proposed — chờ mentor (PRD §11); sửa đổi một phần bởi ADR-013 |
| [ADR-002](ADR-002-guard-chokepoint.md) | Guard dispatcher là cửa duy nhất tới simulator; tách StationReader/StationActuator | Proposed — sửa đổi một phần bởi ADR-011 |
| [ADR-003](ADR-003-tham-so-trong-config.md) | Tham số mô phỏng nằm trong `config/*.yaml`, validate bằng Pydantic | Proposed — sửa đổi một phần bởi ADR-010, ADR-012 |
| [ADR-004](ADR-004-contract-first-501.md) | Skeleton contract-first: đủ schema, stub trả HTTP 501 kèm mã task | Proposed |
| [ADR-005](ADR-005-persistence-sqlalchemy-alembic.md) | Persistence: SQLAlchemy 2 + Alembic sau `services/repository.py`; SQLite local, Neon Postgres khi deploy | Proposed — nhóm đã duyệt; sửa đổi một phần bởi ADR-014 |
| [ADR-006](ADR-006-danh-tinh-jwt-resident-id-server-side.md) | Danh tính: JWT, `resident_id` phía server, WebSocket xác thực bằng bản tin đầu | Proposed — nhóm đã duyệt; sửa đổi một phần bởi ADR-014 |
| [ADR-007](ADR-007-station-runtime-va-control-loop.md) | `StationRuntime` là composition root; sự kiện xử lý ngay trong request | Proposed — nhóm đã duyệt; sửa đổi một phần bởi ADR-011, ADR-014 |
| [ADR-008](ADR-008-quy-uoc-api.md) | Quy ước API: error envelope, idempotency, versioning, `/ready` | Proposed — nhóm đã duyệt; sửa đổi một phần bởi ADR-014 |
| [ADR-009](ADR-009-frontend-nextjs.md) | Frontend Next.js trong `frontend/`, chỉ nhận `openapi.json` từ backend | Proposed — nhóm đã duyệt |
| [ADR-010](ADR-010-bai-hybrid-ac-dc.md) | Bãi hybrid AC + DC; fixture nền `mvp1`; ràng buộc ba tầng; `supply_mode` shared / independent | Proposed — chờ nhóm và mentor |
| [ADR-011](ADR-011-mot-simulator-sau-be-mat-cong-khai.md) | Một `HybridSimulator` sau `src/simulator/base.py` + `SimulatorGateway`; một bộ `Algorithms` cho live / benchmark / what-if; Guard hai lớp | Proposed — sửa đổi một phần bởi ADR-016, ADR-019 |
| [ADR-012](ADR-012-mot-danh-muc-xe-va-kich-ban.md) | Một danh mục xe (provenance theo từng trường) và mọi kịch bản trong `config/scenarios/` | Proposed — chờ nhóm |
| [ADR-018](ADR-018-backend-chay-engine-simulator.md) | Backend chạy engine simulator R&D: `HybridStation` + thuật toán B0 / M2b / M3a / M3b; simulator là gốc | Proposed — chờ nhóm; thay phần quyết định của ADR-016; điểm 4 sửa đổi bởi ADR-019 |
| [ADR-019](ADR-019-unified-core-hop-dong-dung-chung.md) | Unified Core: hợp đồng core thuần ở `src/models`, một lõi vật lý + một nguồn thuật toán cho backend và standalone; di chuyển theo phase có shim + hash AST | Proposed — người phụ trách duyệt Phase 0–1 |
| [ADR-013](ADR-013-workflow-xac-dinh-llm-hai-dau.md) | Workflow xác định là xương sống; LLM chỉ ở hai đầu; LangGraph cho hội thoại + HITL | Proposed — chờ nhóm |
| [ADR-014](ADR-014-decision-trace-counterfactual-hitl.md) | DecisionTrace, counterfactual không bao giờ apply, vòng đời đề nghị HITL (AI-4, AI-1), Copilot theo role, job nền | Proposed — chờ nhóm |
| [ADR-015](ADR-015-pham-vi-mvp4-va-quy-tac-bang-chung.md) | Phạm vi MVP-4, hạng mục hoãn (F6/F12, F13, HOW-TO, AI-2 ML, AI-3) và quy tắc bằng chứng | Proposed — chờ nhóm |
| [ADR-016](ADR-016-livestation-cho-backend.md) | `LiveStation` — simulator chạy liên tục cho backend; HybridSimulator giữ vai trò R&D offline | Proposed — chờ nhóm; sửa đổi một phần ADR-011; **bị thay bởi ADR-018, rồi ADR-019 (LiveStation đã xoá)** |
| [ADR-017](ADR-017-guard-theo-hop-dong-an-toan-simulator.md) | Guard backend dùng cùng hợp đồng an toàn vật lý với HybridSimulator (trần vùng thiết bị, nguồn độc lập, chỉ cấp điện / gán xe hợp lệ) | Proposed — chờ nhóm; sửa đổi bởi ADR-019 (Guard → `src/guard/physical/`) |

Quy tắc: đổi một quyết định thì viết ADR mới đánh dấu `Superseded`, không sửa lịch sử.
Sửa đổi một phần thì ghi rõ ở đầu ADR cũ, trỏ tới ADR mới; phần quyết định gốc giữ nguyên.
Mọi con số trong ADR phải trỏ tới `eval/evidence/` (ADR-015).
Nới ranh giới trong `tests/test_architecture.py` cũng phải có ADR.
