# PHASE AI-4.0 — Foundation Hardening (G1)

**Phase AI-4.0 | Status READY_FOR_REVIEW**  
**Branch** `feature/ai-4` · **Local base / workspace HEAD** `d2b5d4869bff35ad9e417bee504c6dbf652258b1`  
**Mirror baseline** `4f1477e84ac818549a69a74eb00e4b827fae230e` · **P0 evidence được duyệt** `d520ffb28b32b94099277c48af9b8f38ec656ac0`  
**Code thực chạy** Local base + candidate patch SHA-256 `986fd42e0d00e57e8bbad2a085bba1df9508e2b2b34786e967d7105062644873`. Code và evidence G1 đang ở working tree.  
**Evidence commit G1** Chưa tạo. Không có merge/push từ lượt này. [Baseline mapping](BASELINE.md) · [Candidate patch](../../eval/evidence/2026-11-24-ai4-4-0/raw/candidate.patch)

## Scope và code changes

| Hạng mục | File và thay đổi |
|---|---|
| R01 fork isolation | `src/services/runtime.py`, `src/simulator/hybrid_station.py` sao chép safety holds, DTO lồng nhau, config, tariff, plan, commands và scheduler metadata/params. Giữ kernel isolation hiện có cho DC model, stateful optimizer và RNG. Dùng store, sinks, clock và recorder của fork. |
| R02 persistence | `src/db/{tables,mappers}.py`, `src/services/repository.py`, `migrations/versions/0004_full_decision_traces.py` thêm full payload JSONB/JSON, booking/time index và transaction active→closed. Lookup theo correlation ID hoặc cửa sổ thời gian. Summary-only trả thiếu detail. `decision_trace.py` cách ly lỗi DB/export khỏi vòng điều khiển. |
| R03–R05 trace v2 backend | `src/models/decision_trace.py`, `src/services/decision_trace.py`, `src/services/control_loop.py`, `src/simulator/hybrid_station.py` ghi rõ validation stages, command exclusions, power stages, subject/interval, decision-time policy, evidence refs và experiment fingerprint. Trace vi phạm vẫn còn kể cả fail-safe dispatch thành công. |
| R07 safety ordering | `src/services/{runtime,control_loop,charging_service}.py` nối step/enqueue/drain vào cùng thread-safe lock, lấy outbox dưới decision lock, trì hoãn read step khi solver đang chờ và giữ hard violation pending tới khi handler xử lý. Handler raise thì requeue hard event. Hai ca barrier fail trước và pass sau. |
| Tests và tài liệu | 16 backend test mới ở `tests/test_db/test_migrations.py` và `tests/test_services/test_{decision_trace,fork_isolation,safety_event_delivery}.py`. Cập nhật P0 APPROVED, baseline mapping, ADR, ledger R10/R11, PROJECT_STATE, Foundation contract, CLAUDE và tài liệu DB. Raw evidence/harness ở `eval/evidence/2026-11-24-ai4-4-0/`. |

Dispatcher vẫn là live actuator chokepoint. Freeze giữ nguyên AC/DC Optimizer, Coordinator, objective, hard constraints, standalone v2, configs, frozen KPIs và evidence lịch sử. Phạm vi này kết thúc ở Foundation. UI/API Copilot, WHY, rollout, outcome evaluator, HOW-TO và AI-1 nằm ở các gate sau.

## Fail trước → pass sau

| Issue | Ca baseline | Kết quả G1 |
|---|---|---|
| R01 | Fork của xe bị charging-model fault mất safety hold thật | Hold copy độc lập, setpoint vẫn 0 kW. Tests bổ sung cho nested booking/approval/config/tariff/plan, rejected IDs, recent commands, optimizer và DC model có state. |
| R02 | Default config chỉ truy xuất summary. Full lookup chưa tồn tại. | Detail truy xuất sau repository reopen, indexed booking/window, active→closed, retry idempotent, historical migration up/down, serialization failure, DB write failure và JSONL export failure. |
| R03 | `guard.status=pass` trong trace có post-apply hard violation | `violation` giữ nguyên với details. Zero samples báo `no_samples`, active báo `not_evaluated`. Fail-safe response và historical post-apply tách riêng. |
| R04 | Safety hold bị dán nhãn pending approval khi pending bằng 0 | Exclusion theo command, ghi tất cả lý do theo precedence đã nêu. Emergency reduction vẫn qua dispatcher. |
| R07 | Hai read thread đưa clock từ phút 0 tới 6 dù violation xảy ra ở phút 1. Ca read/solver làm mốc dịch từ phút 0 tới 2. | Hai barrier tests pass. Read thứ hai dừng ở phút 1 tới fail-safe. Read trong replan giữ phút 0 tới khi ranh giới trace được ghi. Retry khi handler raise cũng pass. |

Sáu regression trên code base trả exit **1**, đủ 6 fail đã dự kiến. Final focused suite trả exit **0**, **94 pass**, gồm R05 test đo power theo interval, đối chiếu kWh và giữ policy/fingerprint khi scheduler được đổi trước close. [Fail-before](../../eval/evidence/2026-11-24-ai4-4-0/raw/regression-before.stdout.txt) · [Pass-after](../../eval/evidence/2026-11-24-ai4-4-0/raw/focused-tests.stdout.txt)

## Regression và provenance

| Kiểm đã chạy | Exit | Kết quả |
|---|---:|---|
| `python -m pytest tests/ -q -rs` | 0 | **620 passed, 8 forecast skipped**. SQLite tạm, architecture suite bao gồm trong full và focused. |
| `python -m pytest src/simulator/tests/ -q` | 0 | **180 passed** |
| Ruff lint/format, `check_docs.py`, `export_openapi.py --check`, F1 eval offline | 0 mỗi lệnh | Đạt, offline F1 55 cases dataset hợp lệ |
| Preserved AST manifest | 0 | **114** định nghĩa, 0 undeclared, 0 declared changes |
| `run_sim_kpi_gate.py run`/compare với module map hiện có | 0 / 0 | **38/38 CRLF**, CSV byte-identical. Reference historical `70d0eaf` từ archive P0. Bằng chứng LF 35/38 giữ ở P0. |
| `eval/run_benchmark.py --seeds 1,2,3,4,5`, frozen comparator, provenance verifier | 0 / 0 / 0 | **100/100, 0 problems**, đủ 5 scenarios × 4 policies × 5 seeds. Fingerprints và violation counters khớp. |
| SQLite migrations, indexed retrieval và lifecycle | 0 | Pass trong backend/focused suite, gồm upgrade từ 0003 và downgrade giữ summary |
| PostgreSQL offline DDL | 0 | Migration render JSONB, FK và booking/time index |
| PostgreSQL runtime | NOT RUN | Không thấy server binaries hay `TEST_DATABASE_URL`. Docker API không có daemon. **Pending verification** trên PostgreSQL thật. |

Benchmark dùng topology 4 cổng, physics step 1 phút và decision interval 15 phút. Cả candidate và frozen có 0 hard violations, 0 rejected allocations và 0 phút vượt giới hạn lấy mẫu. Min/median/max của p95 replan từng lượt là **2,4 / 10,8 / 23,3 ms** ở G1 và **1,5 / 9,05 / 15,9 ms** ở frozen. G1 chạy song song các gate trên WSL2, frozen chạy Windows. Chênh timing là quan sát của hai lần chạy, chưa cô lập overhead. [KPI diff](../../eval/evidence/2026-11-24-ai4-4-0/raw/benchmark-compare.stdout.txt) · [Fingerprint và timing](../../eval/evidence/2026-11-24-ai4-4-0/raw/benchmark-provenance.stdout.txt) · [Golden](../../eval/evidence/2026-11-24-ai4-4-0/raw/golden-compare.stdout.txt)

Lệnh chính xác, mã thoát, OS/CPU/Python/deps, code patch hash, test logs, golden outputs và benchmark manifest đều lưu kèm. Các phép thử async chạy ngoài sandbox sau khi được duyệt để Unix socketpair hoạt động. Cấu hình được cô lập khỏi `.env` workspace. [Tái lập](../../eval/evidence/2026-11-24-ai4-4-0/README.md) · [Exit codes](../../eval/evidence/2026-11-24-ai4-4-0/raw/exit-codes.tsv)

## Known limitations và quyết định chờ review

- Full trace PostgreSQL runtime còn pending. SQLite lifecycle, SQL schema và offline PostgreSQL DDL đã xác minh. F1 eval chạy offline. Chưa triển khai thực tế trên Render.
- Active trace còn mở sau restart giữ trạng thái planned. Optional JSONL có thể chứa dòng trùng khi retry. Lookup detail nội bộ cần caller áp quyền khi có API. G1 dùng storage error log theo correlation ID, chưa có dashboard theo dõi lỗi trace.
- Trong lúc replan, read đồng bộ có thể trả snapshot của phút hiện hành và catch up sau quyết định. Phạm vi chặn race là read clock và safety delivery. Atomic capture liên store, workload fairness và durable outbox chưa được xác minh.
- R10 ghi contract energy/cost. Billing owner và Tech Lead cần quyết định trước khi sửa semantics quote/billing hiện có. R11 mở outcome ledger additive tại G3. Frozen definitions tiếp tục dùng như baseline. [Ledger R10/R11](ISSUES.md) · [Contract](FOUNDATION_CONTRACT.md)

## Acceptance checklist

| G1 | Kết quả |
|---|---|
| R01–R04 fail trước/pass sau | **PASS** |
| R05 power stages, sources, evidence refs và decision-time provenance | **PASS** |
| R07 barrier-based safety/trace checks và fail-safe retry | **PASS** |
| Full backend, standalone, architecture, lint, format, docs, OpenAPI và offline eval | **PASS** |
| Golden và full benchmark parity theo frozen provenance | **PASS** |
| SQLite migration/persistence, legacy summary, lỗi ghi | **PASS** |
| PostgreSQL runtime | **PENDING** |
| Tech Lead review G1 và cho phép pha sau | **PENDING** |

**Rollback** Hoàn tác G1 product patch cùng test changes. Với môi trường đã migrate thật, downgrade `0004 → 0003` giữ summary và bỏ full payload/index của G1. Export hoặc sao lưu detail cần giữ trước khi downgrade. Gate này chỉ dùng DB tạm.

**STOP — WAITING_FOR_TECH_LEAD_REVIEW (GATE 1)**
