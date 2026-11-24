# PHASE AI-4.1 — Deterministic WHY Engine (Gate 2 & Remediation)

**Phase AI-4.1 | Status READY_FOR_REVIEW — GATE 2 RE-REVIEW**  
**Branch** `feature/ai-4` · **Local base / workspace HEAD** `490f43300afb05ef7e809099a77e0c7174e272fb`  
**Reviewed G1 mirror (APPROVED)** `fed2c5e395c3a6ac3e1798ce52d0e4b4e4abd009`  
**Reviewed G2 mirror (CHANGES REQUIRED)** `6ba13b8021998e03e15b0ec26cec93d484b70a05`  
**Initial G2 candidate patch SHA-256** `fe89fc04bef12180a10333050770dd64764484fdc56d5accee720427a230c36c` ([initial patch](../../eval/evidence/2026-11-24-ai4-4-1/raw/candidate.patch))  
**Remediation full candidate patch SHA-256** `fb424d5c87028cc01952757062067c3c302eaa5cef2c0b1332a758e941437832` ([remediation candidate patch](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/candidate.patch))  
**Delta patch (reviewed G2 → remediation) SHA-256** `e3abc16b445eb5982e95e994f33ec867f4f1cea1ff93ba8449fc1b24a3889083` ([delta patch](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/reviewed-to-remediation.patch))  
**Lưu ý provenance:** Commit message local `"Approved phase 4.1"` trên `490f433` là tên commit lịch sử ở local và **không có nghĩa** AI-4.1 đã được nghiệm thu. Toàn bộ mã nguồn, tests, docs và raw evidence hiện ở working tree (chưa commit/merge/push).  
[Reproducibility & Evidence](../../eval/evidence/2026-11-24-ai4-4-1-remediation/README.md) · [Exit codes](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/exit-codes.tsv) · [Checksums](../../eval/evidence/2026-11-24-ai4-4-1-remediation/CHECKSUMS.sha256)

---

## 1. Phạm vi thực hiện và thay đổi theo Work Package

Chỉ triển khai **PHASE AI-4.1 — Deterministic WHY Engine (WP2.1 → WP2.7 + Gate 2 Remediation G2-F01–G2-F09)**. Không triển khai WHAT-IF, atomic snapshot, HOW-TO, LLM integration, AI-1, frontend Copilot, R10 billing changes, hay R11 Outcome Ledger. Không thay đổi optimizer, Physical Core, frozen policies, standalone trace serializer (`src/simulator/evaluation/trace.py`), golden fixtures hay database schema migrations.

| WP | Thành phần | Files thay đổi / tạo mới |
|---|---|---|
| **WP2.1** | Typed Contracts | [copilot.py](../../src/models/copilot.py) (`ActorContext`, `TimeWindow`, `WhyQuery` + `cursor`, `WhyFact` + `derivation_kind`/`derivation_op`/`input_evidence_refs`/`time_scope`, `WhyReason`, `EvidenceRef` + `time_scope`, `TraceProvenance`, `WhyAnswer` + `next_cursor`) |
| **WP2.2** | Planned Evidence (`G1-F05`) | [hybrid_station.py](../../src/simulator/hybrid_station.py) (`time_at`, `planned_decision_facts`, `_planned_binding_constraints`); [decision_trace.py](../../src/services/decision_trace.py) (additive `planned`, `safety.by_booking`, `applied.completed_by_booking`, mốc ISO trên `interval`/`applied`/`samples`, giữ `chargepilot.backend_decision_trace/2`) |
| **WP2.3** | Temporal Trace Reader (`G1-F06` / `G2-F01` / `G2-F03` / `G2-F04`) | [repository.py](../../src/services/repository.py) (`list_decision_traces_for_temporal_lookup` tách in-window ASC + prior boundary + station-wide superseding timeline + cursor trên index `0004`); [trace_reader.py](../../src/services/copilot/trace_reader.py) |
| **WP2.4** | Auth, Grounding & Privacy (`G2-F02` / `G2-F07`) | [evidence.py](../../src/services/copilot/evidence.py) (`AuthorizedSubject`, `resolve_evidence_ref` kiểm tra toàn vẹn provenance/subject/temporal/ownership, explicit safe allowlist, `EvidenceCollector` xác minh direct/derived facts và reason provenance) |
| **WP2.5** | Deterministic Explainers (`G2-F05` / `G2-F06`) | [why.py](../../src/services/copilot/why.py) & [__init__.py](../../src/services/copilot/__init__.py) (6 topics, zero LLM, strictly read-only, không rò rỉ completion tương lai, không gán nhầm station violation cho xe, abstention cho `NO_INCIDENT_OBSERVED`, loại bỏ fallback hiệu suất ngầm 0.95/0.98) |
| **WP2.6** | Tests & Independent Eval (`G2-F08`) | [test_why_engine.py](../../tests/test_services/test_why_engine.py) (17 tests), [test_why_temporal_and_auth.py](../../tests/test_services/test_why_temporal_and_auth.py) (6 tests), [test_why_g2_remediation.py](../../tests/test_services/test_why_g2_remediation.py) (14 tests fail-before/pass-after), [run_why_eval.py](../../eval/evidence/2026-11-24-ai4-4-1-remediation/run_why_eval.py) (26 ca + independent oracle + 7 mutations) |
| **WP2.7** | Docs & Handoff (`G2-F09`) | Cập nhật [PROJECT_STATE.md](PROJECT_STATE.md), [PHASE_4_0_REPORT.md](PHASE_4_0_REPORT.md), [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md), [ISSUES.md](ISSUES.md), báo cáo này và [run_gate.sh](../../eval/evidence/2026-11-24-ai4-4-1-remediation/run_gate.sh) |

---

## 2. Gate 2 Remediation Issue Ledger (G2-F01–G2-F09)

Tất cả các phát hiện static review từ mirror `6ba13b8` đều được kiểm chứng bằng bộ tái hiện [test_why_g2_remediation.py](../../tests/test_services/test_why_g2_remediation.py) trước khi sửa mã nguồn sản phẩm. Kết quả fail-before: **14/14 FAILED (exit 1)** ([remediation-before.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/remediation-before.stdout.txt), [regression-before.patch](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/regression-before.patch)). Sau khắc phục: **14/14 PASSED** trong focused & full suite.

| ID | Phân loại | Bằng chứng Fail-before → Pass-after & Cách sửa |
|---|---|---|
| **G2-F01** | **Confirmed bug** (Numerical integration) | Fail-before: cửa sổ `[18:00:30, 18:01:30)` trên 60 kW / 30 kW ra `1.5 kWh` thay vì `0.75 kWh`; truy vấn `at` phát `energy.measured_*`; mẫu trùng bị cộng gấp đôi (`2.5 kWh` thay vì `1.5 kWh`). Sửa trong `trace_reader.py`: tính **exact clipped overlap duration** kèm giả định `piecewise-constant`, chống cộng trùng bằng high-water clipping, và tách hẳn as-of power (`power.measured_actual_output_kw`, không xuất năng lượng tích lũy cho `at`). |
| **G2-F02** | **Confirmed bug** (Evidence grounding) | Fail-before: derived sub-window facts chỉ trỏ tới `samples/0` và `add_fact` chấp nhận giá trị direct fact sai (`999.0 != 30.0`) miễn pointer tồn tại. Sửa trong `copilot.py`, `evidence.py`, `why.py`: bổ sung `derivation_kind` (`direct`/`derived`), `derivation_op` hữu hạn (`sum`, `count`, `average`, `time_integration`, `efficiency_conversion`, `soc_conversion`, `hardware_bound`), `input_evidence_refs` đầy đủ mọi sample & efficiency input, xác minh giá trị canonical cho direct fact và đồng nhất `correlation_id` trên `add_reason`. |
| **G2-F03** | **Confirmed bug** (Temporal fact metadata) | Fail-before: sub-window measured facts (cả booking lẫn station) mang `interval_start/end` của toàn bộ trace, còn decision-time `OBSERVED` snapshot mang planned interval 15 phút. Sửa bằng `TemporalBasis` (`decision_snapshot`, `planned_interval`, `effective_interval`, `measured_coverage`, `derivation_interval`, `sample_interval`, `query_window`): snapshot có `interval=None`; derived measured facts mang đúng `[derivation_start, derivation_end)`; sample refs mang đúng `[sample_start, sample_end)`. |
| **G2-F04** | **Confirmed bug** (Temporal resolution) | Fail-before: `_live_open_trace_state()` trả `live_known=False` khi `runtime._live is None` sau restart; truy vấn lọc `booking_id` bỏ sót station-level superseding decision; candidate limit bị trộn với lookback; chưa cờ hóa truy vấn vượt live physics clock. Sửa: `runtime._live is None` → `(None, True, None)`; `repository.py` tách in-window ASC + keyset `cursor`/`next_cursor` + prior boundary + station-wide superseding timeline (không thêm migration `0005`); phát hiện `query_exceeds_live_physics_clock`. |
| **G2-F05** | **Confirmed bug** (Causal & subject attribution) | Fail-before: completion lúc T+12 rò rỉ vào truy vấn `at=T+5` và trỏ vào pre-decision `state="CHARGING"`; station violation gán `subject=booking_id`; active/incomplete vẫn phát `NO_INCIDENT_OBSERVED`; Business Guard block thiếu `guard_passed`/`violations/*/rule`; pending approval không ghi `approval_id` và thiếu `decision_time_only`; hardware bound chỉ trỏ `remaining_kwh`. Sửa toàn bộ 7 điểm, bổ sung `applied.completed_by_booking` (additive), `STATION_POST_APPLY_HARD_VIOLATION` khi thiếu bằng chứng cấp xe, và abstention nghiêm ngặt cho `NO_INCIDENT_OBSERVED`. |
| **G2-F06** | **Confirmed bug** (Energy conversion provenance) | Fail-before: thiếu `conversion_efficiency` vẫn ngầm chia `0.95`, thiếu `charging_efficiency` vẫn ngầm nhân `0.98`. Sửa: loại bỏ hoàn toàn default ngầm; khi thiếu quyết định-time efficiency thì không tính phép toán phụ thuộc và trả `PARTIAL` với `missing_conversion_efficiency_evidence` / `missing_charging_efficiency_evidence`. Không đụng quote, billing hay frozen energy KPIs. |
| **G2-F07** | **Confirmed bug** (Evidence authorization) | Fail-before: `resolve_evidence_ref` chấp nhận `ref_id`/`source_path` lệch, `subject` lệch, `policy_id` lệch, `interval` ngoài biên, và nhận raw string `own_booking_id` chưa xác minh; allowlist mở cả dict container. Sửa: yêu cầu `AuthorizedSubject` đã xác minh hoặc `Booking` khớp `actor.actor_id`; kiểm đủ 8 bất biến provenance/subject/temporal; thu hẹp allowlist resident xuống các leaf path an toàn; kiểm explicit `reason.subject`/`params`/`summary` + defense-in-depth scan. |
| **G2-F08** | **Confirmed gap** (Independent evaluation) | Mở rộng [run_why_eval.py](../../eval/evidence/2026-11-24-ai4-4-1-remediation/run_why_eval.py) thành **independent oracle** tự giải RFC 6901 pointer, tự tính lại toàn bộ direct & derived facts phát sinh (không dùng production resolver làm nguồn chân lý duy nhất), tách riêng **9 chỉ số** kèm denominator rõ ràng và thực thi **7/7 oracle mutation tests**. |
| **G2-F09** | **Confirmed handoff gap** (Documentation) | Đảm bảo [PHASE_4_1_REPORT.md](PHASE_4_1_REPORT.md) có mặt đầy đủ trong workspace và đồng bộ với [PROJECT_STATE.md](PROJECT_STATE.md), [ISSUES.md](ISSUES.md), [FOUNDATION_CONTRACT.md](FOUNDATION_CONTRACT.md) và gói evidence remediation. |

---

## 3. Kết quả Independent Deterministic Evaluation (G2-F08 — Zero LLM Judge)

Chạy bằng [run_why_eval.py](../../eval/evidence/2026-11-24-ai4-4-1-remediation/run_why_eval.py) trên bản clone sạch (**26 ca** gồm 20 ca gốc + 6 ca remediation; kiểm toán toàn bộ **232 evidence refs** và **223 facts** phát sinh). Kết quả phản ánh phạm vi bộ fixture xác định này và không suy rộng thành độ chính xác tổng quát ngoài các kịch bản đã bao phủ.  
Raw evidence: [why-eval.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/why-eval.stdout.txt) · [why-eval-summary.json](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/why-eval/why-eval-summary.json)

| # | Chỉ số tách biệt (G2-F08) | Kết quả (Denominator rõ ràng) | Đánh giá |
|---|---|---:|---|
| 1 | **Reference existence** (RFC 6901 độc lập trên raw trace) | **232 / 232 (100.0%)** | PASS |
| 2 | **Reference authorization** (provenance, ownership & non-leak độc lập) | **232 / 232 (100.0%)** | PASS |
| 3 | **Direct fact correctness** (toàn bộ direct facts phát sinh khớp canonical raw field) | **201 / 201 (100.0%)** | PASS |
| 4 | **Derived fact correctness** (tự tái lập `sum`/`count`/`average`/`time_integration`/`efficiency_conversion`/`soc_conversion`/`hardware_bound`) | **22 / 22 (100.0%)** | PASS |
| 5 | **Temporal grounding** (`decided_at`, snapshot vs interval bounds, sub-window clipping) | **223 / 223 (100.0%)** | PASS |
| 6 | **Subject attribution** (khớp subject với pointer/scope) | **223 / 223 (100.0%)** | PASS |
| 7 | **Causal correctness** (required reasons + categories, 0 forbidden reasons) | **14 / 14 (100.0%)** | PASS |
| 8 | **Answer usefulness / coverage** (trả `OK` có facts/reasons cho ca đủ dữ kiện) | **12 / 12 (100.0%)** | PASS |
| 9 | **Abstention appropriateness** (trả `PARTIAL`/`NO_DATA`/`UNSUPPORTED`/`FORBIDDEN` đúng `missing_evidence`) | **13 / 13 (100.0%)** | PASS |
| — | **Authorization & privacy violations** (bao gồm non-enumeration equivalence) | **0** | PASS |
| — | **Oracle mutation detection** (7 đột biến bắt buộc: sai direct value, sai derived formula, thiếu input ref, sai measured interval, sai subject, sai reason params, future completion leakage) | **7 / 7 (100.0%)** | PASS |

Ví dụ JSON đầu ra xác định (Resident & Operator): [example-resident_queue.json](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/why-eval/example-resident_queue.json) · [example-resident_power_window.json](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/why-eval/example-resident_power_window.json) · [example-operator_overview.json](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/why-eval/example-operator_overview.json)

---

## 4. Kết quả Gate 2 Remediation Regression Gates (Clean Isolated Clone)

Chạy qua [run_gate.sh](../../eval/evidence/2026-11-24-ai4-4-1-remediation/run_gate.sh) tại base `490f43300afb05ef7e809099a77e0c7174e272fb` + remediation `candidate.patch`, cô lập hoàn toàn khỏi `.env` workspace và thư mục gitignored cục bộ `src/simulator/claude_rd/`.

| Gate / Lệnh chính | Exit | Kết quả xác minh | Raw evidence |
|---|---:|---|---|
| Fail-before remediation (`pytest test_why_g2_remediation.py -q` trên tree reviewed G2) | 1 | **14 failed** (xác nhận thực nghiệm G2-F01..G2-F07) | [remediation-before.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/remediation-before.stdout.txt) |
| Focused WHY + Remediation + Foundation + Architecture | **0** | **151 passed** (19.71s — gồm 14 tests remediation + 23 tests WHY + G1 & architecture) | [focused-why-tests.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/focused-why-tests.stdout.txt) |
| Independent WHY Eval + 7 Oracle Mutations | **0** | **26/26 passed**, 100% cả 9 chỉ số, **0** auth/privacy violations, **7/7** mutations | [why-eval.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/why-eval.stdout.txt) |
| Full backend tests (`python -m pytest tests/ -q -rs`) | **0** | **677 passed, 8 forecast skipped** (72.52s, +14 so với 663 ở G2 ban đầu) | [backend-tests.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/backend-tests.stdout.txt) |
| Full standalone simulator tests (`python -m pytest src/simulator/tests/ -q`) | **0** | **180 passed** (8.34s) | [simulator-tests.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/simulator-tests.stdout.txt) |
| Ruff lint & format (`ruff check` / `ruff format --check`) | **0 / 0** | All checks passed, all files formatted | [ruff-lint.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/ruff-lint.stdout.txt) · [ruff-format.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/ruff-format.stdout.txt) |
| Docs sync (`python scripts/check_docs.py`) & OpenAPI (`export_openapi.py --check`) | **0 / 0** | 50 md files / 131 links PASS; `frontend/openapi.json` khớp code | [docs.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/docs.stdout.txt) · [openapi.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/openapi.stdout.txt) |
| Agent offline eval (`python eval/run_agent_eval.py --offline`) | **0** | 55 cases dataset hợp lệ | [agent-offline.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/agent-offline.stdout.txt) |
| Preserved AST parity (`compare_ast_manifest.py`) | **0** | **114** definitions compared, **0** undeclared, **0** declared changes | [ast-parity.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/ast-parity.stdout.txt) |
| Standalone golden CRLF (`run_sim_kpi_gate.py run` / `compare`) | **0 / 0** | **38/38 OK**, CSV byte-identical với P0 CRLF reference | [golden-compare.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/golden-compare.stdout.txt) |
| Frozen benchmark (`eval/run_benchmark.py --seeds 1,2,3,4,5` + compare + provenance) | **0 / 0 / 0** | **100/100 runs, 0 problems**, 4 policy fingerprints khớp frozen baseline, **0** hard violations / rejected allocations / over-limit minutes | [benchmark-compare.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/benchmark-compare.stdout.txt) · [benchmark-provenance.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/benchmark-provenance.stdout.txt) |
| PostgreSQL runtime probe | 127 | **PENDING** — không có local PostgreSQL binary, `TEST_DATABASE_URL` hay Docker daemon | [postgres-availability.stdout.txt](../../eval/evidence/2026-11-24-ai4-4-1-remediation/raw/postgres-availability.stdout.txt) |

**Timing benchmark (mô tả):** Replan p95 giữa 100 runs có min/median/max **2,7 / 10,5 / 22,3 ms** (0 runs > 2s) trên WSL2 song song các gate, so với **1,5 / 9,05 / 15,9 ms** của frozen baseline trên Windows 11.

---

## 5. Known Limitations, Backlog & Rollback Plan

- **PostgreSQL runtime (PENDING):** SQLite lifecycle, temporal lookup + cursor + station timeline và migration `0004` đã xác minh; PostgreSQL thật chờ môi trường Postgres / CI.
- **Chưa mở Public Evidence API / HTTP Copilot API / LLM / UI (DEFERRED):** Giữ đúng phạm vi Gate 2 (Python service nội bộ).
- **Pending safety registry fork inheritance & admission readiness (DEFERRED to G3):** Ghi nhận trong [ISSUES.md](ISSUES.md) là yêu cầu G3 (AI-4.2A).
- **Historical traces trước remediation không có `completed_by_booking`:** Với trace đóng kiểu cũ chỉ có mảng `applied.completed`, truy vấn `at < effective_end` sẽ báo `completion_timestamp_unknown_for_as_of_query` (`PARTIAL`) thay vì rò rỉ completion tương lai.
- **Rollback Plan:** Áp ngược `reviewed-to-remediation.patch` để trở về snapshot Gate 2 ban đầu, hoặc hoàn tác toàn bộ `candidate.patch` (`git checkout -- src/simulator/hybrid_station.py src/services/decision_trace.py src/services/repository.py` và xóa `src/models/copilot.py`, `src/services/copilot/`, `tests/test_services/test_why_*.py`). Không có migration database nào được thêm trong AI-4.1 hay remediation nên **không cần downgrade schema**.

---

## 6. Acceptance Checklist (Gate 2 Re-Review)

| Tiêu chí | Trạng thái |
|---|---|
| G2-F01 Numerical integration (exact overlap, piecewise-constant, no as-of energy, no double-count) | **CONFIRMED & FIXED (14/14 fail-before → pass-after)** |
| G2-F02 Direct vs derived fact grounding & finite `DerivationOp` + full input refs | **CONFIRMED & FIXED** |
| G2-F03 Temporal fact metadata (6 mốc tách bạch cho cả booking & station) | **CONFIRMED & FIXED** |
| G2-F04 Temporal resolution (default restart path, station supersede, live clock, cursor pagination) | **CONFIRMED & FIXED** |
| G2-F05 Causal & subject attribution (8 điểm kiểm soát, abstention nghiêm ngặt) | **CONFIRMED & FIXED** |
| G2-F06 Energy conversion provenance (loại bỏ silent 0.95 / 0.98 fallbacks) | **CONFIRMED & FIXED** |
| G2-F07 EvidenceRef authorization & adversarial checks (`AuthorizedSubject` + safe leaf allowlist) | **CONFIRMED & FIXED** |
| G2-F08 Independent evaluation (9 chỉ số tách biệt, denominators rõ, 7/7 mutations) | **VERIFIED (26/26, 7/7)** |
| G2-F09 Documentation & `PHASE_4_1_REPORT.md` handoff | **VERIFIED** |
| Full regression gates (677 backend / 151 focused / 180 sim / 114 AST / 38/38 golden / 100/100 benchmark) | **VERIFIED (exit 0)** |
| PostgreSQL runtime verification | **PENDING** |
| WHAT-IF, atomic snapshot, HOW-TO, LLM, AI-1, Frontend Copilot | **DEFERRED (G3+)** |
| Tech Lead Gate 2 Re-Review & Approval | **PENDING** |

**STOP — WAITING_FOR_TECH_LEAD_REVIEW (GATE 2 RE-REVIEW)**
