# AI-4 — Baseline P0

## Git và nguồn đọc

| Đối tượng | Commit | Git tree |
|---|---|---|
| P-019, `feature/ai-4` | `ce23136d50ad08abb7c9fdc98eff791875d24516` | `9c70798ce922e9ff5df5240394df4bb6d1d2c803` |
| GitHub mirror, `main` | `4f1477e84ac818549a69a74eb00e4b827fae230e` | `7b68bb5118f1a94364f7a0ee36bc04bb726d1619` |

GitHub connector xác nhận SHA tại repository được chỉ định. Clone mirror liền kề `../P-019-chatgpt` trỏ về cùng origin và `origin/main` ở đúng SHA. Đối chiếu toàn bộ `git ls-tree -r` theo path, mode và blob SHA. Mirror thiếu 12 path chỉ có trong P-019, thuộc `.agents/`, `.ai-log/.gitkeep`, `.claude/`, `.codex/`, `.cursor/`, `.gemini/` và `.github/` (gồm CI). Tất cả path khác khớp, gồm source, cấu hình, migration, dependency, frontend, test và evidence đã track. P-019 là nguồn kiểm tra P0. Tại lúc bắt đầu, diff tracked rỗng và `docs/ai4/` chứa hai file người dùng cung cấp. Không cần tạo branch mới. [Tree diff](../../eval/evidence/2026-11-24-ai4-p0/raw/mirror-tree-diff.stdout.txt) · [Commit mirror](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/commit/4f1477e84ac818549a69a74eb00e4b827fae230e)

Đã đối chiếu Master Plan, `CLAUDE.md`, `README.md`, `AGENTS.md` theo phạm vi, ADR-013/014/015/019 và các ADR về Guard, auth, API và runtime, Final Acceptance/Final Map, simulator PROJECT_STATE, HANDOFF và `tests/test_architecture.py`. `collaboration_chat.md` rỗng. Không tìm thấy PDF Research SC-16 trong workspace. Phạm vi research được tham chiếu qua Master Plan và ADR, chưa đối chiếu trực tiếp theo trang PDF. Mô tả `LiveStation` trong chỉ dẫn simulator và đoạn lịch sử HANDOFF đã được ADR-018/019 và code hiện hành thay thế.

## G0 review và nguồn G1

Tech Lead duyệt P0 trên mirror `d520ffb28b32b94099277c48af9b8f38ec656ac0` (tree `777fcb80ca1713117d42cbbfaaf88e6741848e3c`). Đây là commit evidence P0 được review. Diff từ mirror `4f1477e` trong source, config, migrations, tests và frontend rỗng. Nhánh local `feature/ai-4` bắt đầu G1 tại `d2b5d4869bff35ad9e417bee504c6dbf652258b1`. Các path product của `d2b5d48` khớp baseline local `ce23136`. Mirror có các root files bị loại do thay đổi `.rsync-exclude` theo Tech Lead. Commit review G1 `6667dead49d047c4971f73a95ff47229dc8dc4e9` khớp 337 blob scope chung với snapshot local `d2b5d48` + patch G1 ban đầu. [Đối chiếu G1](../../eval/evidence/2026-11-24-ai4-4-0-remediation/raw/mirror-product-mapping.stdout.txt) [Báo cáo G1](PHASE_4_0_REPORT.md)

## Module map Unified Core

| Tầng | Đường thực thi tại HEAD |
|---|---|
| Contracts | `src/models/{simulation_core,scheduling,physical_constraints,physical_limits,charging_physics,decisions,station_protocols}` cho core. DTO API Pydantic tại `src/models/`. |
| Physical Core | `src/simulator/core/kernel.py::StationKernel` dùng cho cả `HybridSimulator` standalone và `HybridStation` backend. Queue, EV2Gym adapter và DC model nằm trong `src/simulator/core/`. Legacy `LiveStation`, simulator shim và LP A–D đã được gỡ. |
| Planning Core | `src/optimizer/{dispatch,zones,coordination,registry.py}`. Một registry cho B0, M2b, M3a, M3b v1. `hybrid_planner.py` nối scheduler vào kernel. `solver.py` dùng một thread LP. |
| Safety | `src/guard/physical/validator.py` kiểm trần vật lý. Guard nghiệp vụ và approval/dispatcher áp dụng cho backend. `dispatcher.py` là live actuator chokepoint. Sau hard violation, cấu hình mặc định bật fail-safe. |
| Integration | `runtime.py` dựng live/simulation/fork. `control_loop.py` xử lý sự kiện, gọi scheduler và ghi trace. `admission.py` chạy quote trên fork, qua cùng loop và Guard. `simulation_service.py` chạy workload theo seed và phục vụ frozen benchmark. |
| Trace | `src/services/decision_trace.py` mở/đóng, ghi summary và export JSONL có cấu hình. `src/simulator/evaluation/trace.py` định dạng facts v2. `repository.py` sở hữu đường ORM truy xuất traces. |
| AI/UI | `src/llm_chat/` là luồng chat cư dân đang chạy. `src/services/llm.py` cấp provider. `src/agents/` chỉ có `__init__.py`. Web dùng schema sinh từ OpenAPI. |

Architecture gate khóa chiều import kể cả tương đối, core contracts stdlib, một kernel và registry, dispatcher-only, ORM qua repository, cấm AI tạo `Command` hoặc truy cập core/DB trực tiếp. Standalone probe chặn các thư viện backend. AST gate bảo toàn 114 định nghĩa gốc. [Architecture tests](../../tests/test_architecture.py) · [AST raw](../../eval/evidence/2026-11-24-ai4-p0/raw/ast-parity.stdout.txt)

## API hiện có

REST nghiệp vụ dùng tiền tố `/api/v1`. `/auth` cung cấp login và me. Catalog có `/vehicles`, `/energy/estimate`, `/station/config`, `/tariff`. `/resident` có quote, booking, session, queue, explanation, notification, approval và profile. `/operator` có station/load, connectors, events, bookings, schedule/replan, gán thủ công, approvals, blocked commands và decision log. `/simulation` dành cho Operator với scenarios, runs, policies, incidents và benchmark. F1 có `/chat`, `/chat/stream`, `/chat/resume`, `/status`. Realtime có WebSocket theo hai role. Health và readiness ở `/health`, `/ready`. OpenAPI snapshot liệt kê REST hiện hành. Copilot API, paired rollout và trace retrieval API vẫn ở mức kế hoạch. [OpenAPI](../../frontend/openapi.json)

## Môi trường và topology đã xác minh

- Dùng venv sẵn có `.simulator` theo Python 3.12 của repo. Runtime WSL2 Ubuntu 24.04.5 LTS x86-64, AMD Ryzen 7 6800H, 8 core / 16 logical CPU, Python 3.12.3, EV2Gym 2.0.0, NumPy 2.4.6, SciPy 1.18.1, Ruff 0.17.5. Chạy trên checkout tạm, với môi trường được làm sạch và SQLite riêng của pytest. [Môi trường](../../eval/evidence/2026-11-24-ai4-p0/raw/environment.stdout.txt)
- Fixture shared supply có 2 AC × 11 kW, 2 DC × 60 kW, grid input 106 kW, AC/DC zone budgets đầu ra 22/78 kW, physical caps đầu ra 22/120 kW, conversion 0,95. AC adapter dùng EV2Gym, DC extension mặc định `synthetic_taper_v1`. Các thông số là giả định mô phỏng. Backend frozen dùng physics step 1 phút và decision interval 15 phút. Golden standalone dùng time config của fixture và CLI tương ứng. [Cấu hình trạm](../../config/station.yaml) · [Manifest frozen](../../eval/evidence/2026-11-24-unified-core-frozen-baseline/manifest.json)
