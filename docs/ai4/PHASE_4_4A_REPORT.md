# AI-4.4A · Shared Integration Foundation và WHY/WHAT-IF end-to-end

## Baseline

Local source of truth là `P-019`, branch `feature/ai-4`, HEAD `4658b1f068350c130ed5ed1a744c19a7b8cd522c`. Tech Lead đã duyệt G4 tại mirror `eb5967ae720b46b089b09e03063aa2c727ca5fd8`, candidate SHA-256 `e8ae5cedbbe5af0a0a05d63f3dbb4ea6ac22fda40a4628a2cf7abca82be10d0f` và remediation-only `1cdb630cc10a4bfd1fb96d1ac2264dbd4a9515f3dbfe7153780f0c6fd33160bf`. Dựng lại baseline bằng G3 approved patch rồi G4 final patch, đối chiếu 332 paths và đủ 12/12, 5/5 blob prefixes. [G4 acceptance](PHASE_4_2B_REPORT.md) · [Recovery](G6A_RECOVERY_STATE.md)

## Architecture và thay đổi

| Tầng | Thay đổi |
|---|---|
| `src/models/copilot_integration.py` | Intent union cho WHY, WHAT-IF, HOW-TO, clarify và unsupported. Typed time selection, public result discrimination, authorized context, claim và job envelope. |
| `src/agents/copilot_intent.py` | Dùng structured classifier hiện có, bounded timeout và concurrency. Input gồm câu hỏi và station time/timezone. Typed contract từ chối actor hoặc tool fields. Rule subset kiểm cách gắn parameter với câu hỏi và cung cấp fallback. |
| `src/services/copilot/integration.py` | Explicit handlers cho WHY, WHAT-IF và HOW-TO unavailable. Server bind actor vào single configured station. Scope booking và connector trước capture, rồi G4 kiểm quyền và patch trên snapshot. Relative WHAT-IF resolve tại snapshot T. |
| `src/api/copilot.py`, `src/api/deps.py`, `src/main.py` | Mount dưới `/api/v1/copilot`, dùng JWT server xác thực kể cả khi legacy playground được bật. Một integration instance và một `WhatIfJobs` mỗi app lifespan. Lifecycle gồm bounded submit, poll, cancel, TTL, follow-up và shutdown. |
| `src/agents/copilot_grounding.py` | WHY claim projection giữ validated facts, causal reason semantics và refs G2. WHAT-IF projection kiểm cutoff, branch, đơn vị, signed delta và reason code từ G4. Khi evidence bất nhất, trả trạng thái lỗi rõ. |
| `frontend` | Panel trên resident/operator dashboard dùng generated types, client hiện có, NL và biểu mẫu. Render stage/evidence, comparison, commitments, job trạng thái và null reasons. |
| Tests và demo | Integration qua JWT + FastAPI + trace/simulator thật trên SQLite tạm. Web tests kiểm UI behavior riêng. Demo CLI và hướng dẫn chạy dashboard. |

Structured parser dùng văn phạm bảo thủ cho giả định thay đổi. Câu ngoài subset có thể nhận clarify, unsupported hoặc chuyển sang typed form. G6A dùng deterministic rendering cho toàn bộ numerical và causal statements. Provider chỉ phân tích intent. Authorization và evidence construction chạy ở server qua service deterministic.

## Handoff

G6A giữ WHY và WHAT-IF hoạt động qua ba lối NL, typed API và dashboard. HOW-TO nhận diện qua contract riêng với `feature_not_available`. Tiếp theo theo roadmap là G5, G6B và G7 sau review tương ứng. [Master Plan](AI-4_MASTER_IMPLEMENTATION_PLAN.md)

Job envelope có kind và result union. G5 có thể gọi runner từ một snapshot, dùng lại một baseline cho toàn bộ bounded search và dùng announced replay semantics của WHAT-IF. G6B mở rộng result/job kinds và claim projection cho candidate evidence, dùng chung workload bounds và solver. Engine hiện có vẫn độc lập với HTTP, LLM và UI.

Rollback theo G6A diff trên cây scratch đã áp G3/G4. Rollback cả router mount và generated API DTO cùng panel, giữ accepted G4 engine và booking flow làm baseline. [Commands, tài khoản fixture và API examples](G6A_DEMO.md)
