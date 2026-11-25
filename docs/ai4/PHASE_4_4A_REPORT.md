# PHASE AI-4.4A (Gate 6A) — Shared Integration Foundation & WHY/WHAT-IF End-to-End

**G6A — READY_FOR_REVIEW**

| Thuộc tính trạng thái (tách biệt, không đánh đồng) | Trạng thái thực tế |
|---|---|
| **Implementation complete** | **YES** (WHY + WHAT-IF end-to-end qua NL, biểu mẫu có cấu trúc, REST API + JWT, `GroundingGate` và `CopilotPanel` trên `/resident` & `/operator`; HOW-TO trả `feature_not_available`) |
| **Demo ready (cho buổi demo mentor tối 25/11/2026)** | **YES** (FastAPI + JWT + SQLite + DecisionTrace + WHY G2 + WHAT-IF G4 + Guard + Next.js UI chạy thật; intent NL dùng deterministic fallback khi chưa cấu hình API key) |
| **Real LLM provider smoke** | **PENDING (`PENDING_NO_AUTHORIZED_KEY`)** — Môi trường không có `OPENAI_API_KEY` / provider key hợp lệ và không có local LLM server tại `localhost:11434`; **không** tính `LLM_PROVIDER=mock` là kết quả LLM thật |
| **PostgreSQL runtime verification** | **PENDING** — Môi trường không có PostgreSQL binaries / `TEST_DATABASE_URL` / Docker daemon (theo backlog G7) |
| **Mandatory G6A verification complete** | **YES** — Backend 12/12 checks PASS, Frontend 6/6 checks PASS (`35/35` tests + Webpack & workspace Turbopack build), Final Chromium smoke PASS (`exit 0`), 356/356 clean-tree byte parity |
| **Tech Lead Gate 6A acceptance** | **WAITING_FOR_TECH_LEAD_REVIEW (CHƯA NGHIỆM THU)** |

---

## 1. Điểm dừng của Codex và hành động Recovery của Carbon

- **Điểm dừng của Codex:** Codex triển khai AI-4.4A trên `P-019` (`feature/ai-4`, local `HEAD` `4658b1f068350c130ed5ed1a744c19a7b8cd522c`, interrupted mirror `1a07b5ea0fbd4b9dc8a4a1a76a989f8356f2268c`). Lúc `16:21`, Codex xuất `candidate.patch` lịch sử `eb773daf282482e67adce09689ff5f6559db1ea4f82143bec31f39daf5014048` (19 tệp), sau đó bổ sung `browser_smoke.mjs` và cập nhật thêm 5 tệp (`src/agents/copilot_intent.py`, `tests/test_api/test_copilot.py`, `frontend/src/components/copilot/CopilotPanel.tsx`, `frontend/src/test/copilot.test.tsx`, `eval/evidence/2026-11-26-ai4-4-4a/verify.sh`) rồi hết quota trước khi cập nhật lại patch ứng viên cuối, chạy lại cổng frontend sau khi thêm test cô lập tài khoản, kiểm tra phản hồi trễ/in-flight khi logout/đổi tài khoản và hoàn thiện bộ tài liệu bàn giao.
- **Hành động Recovery của Carbon:**
  1. Kiểm toán đầy đủ `git status`, tiến trình nền (không còn tiến trình treo) và đối chiếu toàn bộ workspace với cây G4 đã duyệt (`eb5967ae720b46b089b09e03063aa2c727ca5fd8`).
  2. Bảo tồn nguyên vẹn toàn bộ log lịch sử của Codex trong `eval/evidence/2026-11-26-ai4-4-4a/raw/` và lưu bản sao patch lịch sử tại [codex-interrupted-candidate.patch](../../eval/evidence/2026-11-26-ai4-4-4a/raw/codex-interrupted-candidate.patch) ([SHA-256](../../eval/evidence/2026-11-26-ai4-4-4a/raw/codex-interrupted-candidate.sha256)).
  3. Giữ nguyên 100% các thay đổi sau patch của Codex và bổ sung khóa cô lập phản hồi trễ/in-flight trong `CopilotPanel.tsx` + regression test + kiểm tra chuyển tài khoản trên cùng một tab Chromium.
  4. Dựng lại final G6A `candidate.patch` từ baseline G3+G4 đã duyệt, xác minh áp xuôi/ngược trên cây sạch `/tmp/p019-g6a-clean-verify` và chạy lại đầy đủ backend gate, frontend gate, kiểm tra trạng thái provider và final Chromium smoke trên đúng ứng viên cuối.

---

## 2. Provenance ứng viên cuối và SHA-256

| Hạng mục | Giá trị xác minh |
|---|---|
| Local workspace & branch | `/home/lehieu/Projects/P-019` · `feature/ai-4` · `HEAD` `4658b1f068350c130ed5ed1a744c19a7b8cd522c` |
| Approved G3 base patch | `59a92d326cfaae6cd8bb3d2b94b4124765b3efdcb3551b2c48d36e60ca73dc5d` (mirror `d0fcf5d11cfd75b677eeaed00e5b5264ab828744`) |
| Approved G4 base patch | `e8ae5cedbbe5af0a0a05d63f3dbb4ea6ac22fda40a4628a2cf7abca82be10d0f` (mirror `eb5967ae720b46b089b09e03063aa2c727ca5fd8`) |
| Reconstructed G4 write-tree | `5f7e86292514ed9c19d9a7f43e3d436b0b5a9bb0` |
| Historical Codex G6A patch (preserved) | `eb773daf282482e67adce09689ff5f6559db1ea4f82143bec31f39daf5014048` ([codex-interrupted-candidate.patch](../../eval/evidence/2026-11-26-ai4-4-4a/raw/codex-interrupted-candidate.patch)) |
| **Final G6A candidate patch (20 paths)** | **`218ef89b033a155542deccb7cfbeb9f8380c9ed97ff402cfb6ff05b81d91f706`** ([candidate.patch](../../eval/evidence/2026-11-26-ai4-4-4a/candidate.patch) · [candidate.sha256](../../eval/evidence/2026-11-26-ai4-4-4a/candidate.sha256)) |
| Clean-tree byte parity & reverse check | **356/356** tệp `src/`, `tests/`, `config/`, `migrations/`, `scripts/`, `prompts/`, `frontend/` khớp từng byte; `git apply --reverse --check` PASS ([candidate-provenance.log](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/candidate-provenance.log)) |
| Unified Core & G2–G4 engine diff | **0 byte thay đổi** trên `src/simulator/**`, `src/optimizer/**`, `src/guard/**`, `src/services/{runtime,control_loop,solver}.py`, `src/llm_chat/**`, `config/**`, `migrations/**`, `src/services/copilot/{why,evidence,trace_reader,snapshot,outcome_ledger,counterfactual,what_if,jobs}.py` |

Vì diff chứng minh **0 thay đổi** trên Unified Core và các engine G2–G4 đã được Tech Lead nghiệm thu tại `eb5967ae720b46b089b09e03063aa2c727ca5fd8`, G6A kế thừa hợp lệ các bằng chứng nền đã duyệt từ [báo cáo G4](PHASE_4_2B_REPORT.md): **Standalone simulator 180/180**, **Golden CRLF 38/38**, **Frozen backend benchmark 100/100 (0 comparator problems, 0 hard violations)** và **Preserved AST parity 114/114**.

---

## 3. Tệp thay đổi trong G6A và phần chỉnh sửa của Carbon

### 3.1 Toàn bộ 20 đường dẫn trong Final G6A Candidate (`218ef89b...`)
- **Backend mới (6):** [copilot_integration.py](../../src/models/copilot_integration.py), [copilot_intent.py](../../src/agents/copilot_intent.py), [copilot_grounding.py](../../src/agents/copilot_grounding.py), [integration.py](../../src/services/copilot/integration.py), [copilot.py](../../src/api/copilot.py), [test_copilot.py](../../tests/test_api/test_copilot.py).
- **Backend chỉnh sửa tối thiểu để gắn router/JWT/error codes (4):** [deps.py](../../src/api/deps.py), [main.py](../../src/main.py), [api.py](../../src/models/api.py), [errors.py](../../src/services/errors.py).
- **Frontend & OpenAPI (6):** [openapi.json](../../frontend/openapi.json), [schema.d.ts](../../frontend/src/lib/api/schema.d.ts), [resident/page.tsx](../../frontend/src/app/resident/page.tsx), [operator/page.tsx](../../frontend/src/app/operator/page.tsx), [CopilotPanel.tsx](../../frontend/src/components/copilot/CopilotPanel.tsx), [copilot.test.tsx](../../frontend/src/test/copilot.test.tsx).
- **Demo & cổng xác minh G6A (4):** [G6A_DEMO.md](G6A_DEMO.md), [run_demo.py](../../eval/evidence/2026-11-26-ai4-4-4a/run_demo.py), [verify.sh](../../eval/evidence/2026-11-26-ai4-4-4a/verify.sh), [browser_smoke.mjs](../../eval/evidence/2026-11-26-ai4-4-4a/browser_smoke.mjs).

### 3.2 Các tệp do Carbon chỉnh sửa/hoàn thiện trong pha Recovery
1. [CopilotPanel.tsx](../../frontend/src/components/copilot/CopilotPanel.tsx): Khóa `actorKey = "${role}:${session.userId}:${sessionToken}"`, truyền `{ signal }` cho truy vấn context, xóa sạch và hủy truy vấn `["copilot"]` trên `QueryClient` khi logout/unmount, và bổ sung `mountedRef` + `submitEpochRef` chặn phản hồi `submit` / `cancel` trễ từ phiên trước ghi đè lên phiên sau (chỉ sửa riêng trong Copilot, không đụng hệ thống auth dùng chung).
2. [copilot.test.tsx](../../frontend/src/test/copilot.test.tsx): Thêm ca kiểm thử `drops delayed in-flight query and cancel responses across logout and re-login` dùng deferred promises xác minh phản hồi trễ sau khi logout/đổi tài khoản hoặc đăng nhập lại bằng token mới bị loại bỏ hoàn toàn.
3. [browser_smoke.mjs](../../eval/evidence/2026-11-26-ai4-4-4a/browser_smoke.mjs): Bổ sung kiểm tra đăng xuất và đăng nhập sang `second-resident@g6a.example` ngay trên **cùng một tab trình duyệt** (xác nhận không còn `resident-demo` trong dropdown lịch sạc và không còn vùng kết quả WHY/WHAT-IF của cư dân trước) cùng kiểm đếm `apply_button_count === 0` ở cả hai vai trò.
4. Tài liệu & provenance: [G6A_DEMO.md](G6A_DEMO.md), [PHASE_4_4A_REPORT.md](PHASE_4_4A_REPORT.md), [G6A_RECOVERY_STATE.md](G6A_RECOVERY_STATE.md), [PROJECT_STATE.md](PROJECT_STATE.md), [ISSUES.md](ISSUES.md), [collaboration_chat.md](collaboration_chat.md) và gói bằng chứng cuối trong `eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/`.

---

## 4. Kết quả xác minh Backend & Frontend trên Final Candidate (`218ef89b...`)

### 4.1 Backend Mandatory Gate (`verify.sh backend` trên `/tmp/p019-g6a-clean-verify`)
Bảng tổng hợp mã thoát: [backend-exits.tsv](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/backend-exits.tsv) (toàn bộ **12/12 PASS, exit 0**).

| Hạng mục | Exit | Kết quả thực chạy | Raw log |
|---|---:|---|---|
| `focused-g6a` (`pytest -vv tests/test_api/test_copilot.py`) | **0** | **9 passed** (NL hypothetical infrastructure 120 kW, explicit off-grid deadline 422, auth/ownership/cancel/TTL, playground JWT enforcement, `GroundingGate` 8 mutations, unsafe no-delta, `non_comparable_sample`, parser timeout, zero live mutation) | [focused-g6a.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/focused-g6a.stdout.txt) |
| `demo-fallback` (`run_demo.py --out ...`) | **0** | Chạy trọn luồng Resident WHY, Resident SOC 75%, Operator DC outage 30m, Operator site limit 15 kW, Operator HOW-TO `feature_not_available` | [demo-fallback.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/demo-fallback.stdout.txt) |
| `legacy-f1` (`tests/test_llm_chat` + `test_routes.py`) | **0** | **91 passed** (luồng chat đặt lịch F1 hiện hữu giữ nguyên) | [legacy-f1.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/legacy-f1.stdout.txt) |
| `regression-g2-g3-g4` | **0** | **128 passed** (toàn bộ WHY G2, Counterfactual G3 và WHAT-IF G4) | [regression-g2-g3-g4.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/regression-g2-g3-g4.stdout.txt) |
| `g3-eval` (`run_g3_eval.py`) | **0** | **8/8 cases PASS, 6/6 mutations caught** | [g3-eval.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/g3-eval.stdout.txt) |
| `architecture` (`tests/test_architecture.py`) | **0** | **43 passed** (ranh giới import, single actuator chokepoint, ORM isolation, standalone simulator isolation) | [architecture.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/architecture.stdout.txt) |
| `backend-tests` (`pytest tests/ -q -rs`) | **0** | **777 passed, 8 forecast skipped** | [backend-tests.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/backend-tests.stdout.txt) |
| `ruff-lint` & `ruff-format` | **0 / 0** | All checks passed; 178 files already formatted | [ruff-lint.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/ruff-lint.stdout.txt) · [ruff-format.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/ruff-format.stdout.txt) |
| `docs` (`check_docs.py`) & `openapi` (`export_openapi.py --check`) | **0 / 0** | Markdown links hợp lệ; `frontend/openapi.json` khớp schema FastAPI | [docs.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/docs.stdout.txt) · [openapi.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/openapi.stdout.txt) |
| `f1-offline` (`run_agent_eval.py --offline`) | **0** | **55/55** mẫu dataset F1 hợp lệ | [f1-offline.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/backend/f1-offline.stdout.txt) |

### 4.2 Frontend Mandatory Gate (`G6A_WEBPACK=1 verify.sh frontend` + Turbopack Probe)
Bảng tổng hợp mã thoát: [frontend-exits.tsv](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/frontend/frontend-exits.tsv) (toàn bộ **6/6 PASS, exit 0**).

| Hạng mục | Lệnh & Bundler | Exit | Kết quả thực chạy | Raw log |
|---|---|---:|---|---|
| `frontend-lint` | `npm run lint` (`eslint`) | **0** | PASS (0 lỗi / cảnh báo) | [frontend-lint.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/frontend/frontend-lint.stdout.txt) |
| `frontend-typecheck` | `npm run typecheck` (`next typegen && tsc --noEmit`) | **0** | PASS | [frontend-typecheck.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/frontend/frontend-typecheck.stdout.txt) |
| `frontend-tests` | `npm test` (`vitest run`) | **0** | **6 files / 35 tests PASS** (gồm **5/5** tests trong `copilot.test.tsx`, bao gồm ca logout/account-switch + delayed in-flight response) | [frontend-tests.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/frontend/frontend-tests.stdout.txt) |
| `frontend-build` (clean scratch tree) | `npm run build -- --webpack` (`Next.js 16.4.6 webpack`, `G6A_WEBPACK=1`) | **0** | **17/17 routes built**, `BUILD_ID=og6lswycxJFfzwMckocBx` | [frontend-build.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/frontend/frontend-build.stdout.txt) |
| `frontend-api-types` & `compare` | `openapi-typescript ./openapi.json` + `cmp ... src/lib/api/schema.d.ts` | **0 / 0** | Byte-identical với `src/lib/api/schema.d.ts` | [frontend-api-types.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/frontend/frontend-api-types.stdout.txt) · [frontend-api-compare.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/frontend/frontend-api-compare.stdout.txt) |
| Turbopack probe (clean `/tmp` symlinked `node_modules`) | `npm run build` (`Next.js 16.4.6 Turbopack`) | 1 | Từ chối symlink `node_modules` xuyên phân vùng ngoài workspace root (hermetic root check của Turbopack) | [turbopack-build.stderr.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/turbopack-probe/turbopack-build.stderr.txt) |
| Turbopack probe (in-place `P-019/frontend`) | `npm run build` (`Next.js 16.4.6 Turbopack`) | **0** | **17/17 routes built in 2.7s** khi chạy trên `node_modules` thật và môi trường cho phép bind loopback (xác nhận lỗi `binding to a port — Operation not permitted` trước đó ở [frontend-build.stderr.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/frontend-build.stderr.txt) là giới hạn sandbox của Codex, không phải lỗi mã nguồn) | [workspace-turbopack.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/turbopack-probe/workspace-turbopack.stdout.txt) |

---

## 5. Trạng thái Real LLM Provider (Priority 4)

Kiểm tra an toàn qua `src/config.py` và `src/services/llm.py` (không đọc/in bất kỳ giá trị bí mật nào) tại [provider-status.json](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/provider-status.json):
- `configured_provider`: `openai` (`model_classify = gpt-4o-mini`, `model_generate = gpt-4o`, endpoint mặc định `api.openai.com`).
- `openai_api_key_configured`: `false` (các biến `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` đều trống).
- `local_llm_base_url`: `http://localhost:11434/v1` (`local_llm_reachable = false`).
- **Kết luận minh bạch:** Real LLM provider smoke ở trạng thái **`PENDING` (`PENDING_NO_AUTHORIZED_KEY`)**. Demo CLI và Chromium browser smoke sử dụng `LLM_PROVIDER=mock` (`parse_source="deterministic"` fallback cho tầng trích xuất ý định, trong khi FastAPI, JWT, SQLite, DecisionTrace, WHY G2, WHAT-IF G4, Optimizer và Guard chạy thật 100%). Tuyệt đối **không** tính `LLM_PROVIDER=mock` là kết quả kiểm thử LLM thật.

---

## 6. Kết quả Final Chromium Browser Smoke (Priority 5)

Chạy bằng Chromium Headless Shell `136.0.7103.25` ([browser_smoke.mjs](../../eval/evidence/2026-11-26-ai4-4-4a/browser_smoke.mjs)) trực tiếp trên bản build Webpack của cây ứng viên cuối (`/tmp/p019-g6a-clean-verify`, `candidate.patch` `218ef89b033a155542deccb7cfbeb9f8380c9ed97ff402cfb6ff05b81d91f706`, `BUILD_ID=og6lswycxJFfzwMckocBx`) kết nối API thật `run_demo.py --serve --port 8000`:
- Provenance & logs: [browser-smoke-provenance.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/browser-smoke-provenance.txt) · [browser-smoke.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/browser-smoke.stdout.txt) · [browser-smoke.exit](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/browser-smoke.exit) (`0`) · [browser-api.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/browser-api.stdout.txt) · [browser-web.stdout.txt](../../eval/evidence/2026-11-26-ai4-4-4a/raw/final-carbon/browser-web.stdout.txt).
- Kết quả xác nhận (`exit 0`):
  1. **Resident WHY:** HTTP `200`, `result.status = "partial"`, hiển thị thực tế **9 grounded claims** kèm evidence refs.
  2. **Resident WHAT-IF:** HTTP `202` → poll `succeeded`, `applied = false`, hiển thị song song cam kết gốc **90%** và cam kết sửa **75%**.
  3. **Cô lập phiên trên cùng một tab trình duyệt:** Đăng xuất khỏi `res-resident-demo@g6a.example` và đăng nhập `second-resident@g6a.example` ngay trên cùng `page` → `prior_booking_visible = false` (`resident-demo` biến mất khỏi danh sách lịch sạc) và `prior_results_visible = false` (vùng kết quả WHY/WHAT-IF của phiên trước bị xóa sạch).
  4. **Operator WHAT-IF outage:** Chọn `DC-01-1`, mô phỏng lỗi 30 phút → `completed`, bảng lịch ảnh hưởng hiển thị `operator-dc-second`.
  5. **Operator HOW-TO:** HTTP `200`, trả thông báo `code = "feature_not_available"`.
  6. **Advisory-only UI:** `apply_button_count = 0` trên cả dashboard Resident lẫn Operator.

---

## 7. Bằng chứng Bảo mật, Phân quyền, Cô lập và Grounding

- **JWT bắt buộc & Server-owned Actor:** `src/api/copilot.py` dùng `AuthenticatedUser` (`get_authenticated_user` trong `src/api/deps.py`), từ chối `401` khi thiếu token hoặc gửi `Bearer demo` ngay cả khi `AGENT_PLAYGROUND=true` (`test_playground_does_not_bypass_copilot_jwt`). `ActorContext` gắn cứng vào `station_id` của server.
- **Phân quyền & Non-enumerating Job Ownership:** Resident hỏi lịch người khác (`private-holder-a`) hoặc gửi thao tác hạ tầng (`outage`, `site_limit`) bị chặn `403`. Truy vấn/hủy/follow-up `job_id` của người dùng khác (kể cả giữa Resident khác và Operator) trả `404` (`test_resident_why_and_what_if_uses_real_engines_and_preserves_live_state`, `test_job_cancellation_expiry_and_shutdown_ownership`).
- **Chống Prompt Injection & Hostile Provider Output:** `ParsedCopilotIntent` đặt `extra="forbid"`; đầu ra provider giả mạo `actor_role="operator"` bị từ chối và chuyển về `structured_fallback`; chuỗi injection tiếng Việt/Anh bị chặn về `unsupported`; tham số NL được đối chiếu chặt với văn bản gốc (`_supported_provider_output`), chặn explicit off-grid deadline bằng `422 copilot_invalid_patch` và yêu cầu cờ `hypothetical_infrastructure` rõ ràng khi vượt công suất lắp đặt (`test_off_grid_relative_time_roles_and_hostile_provider_output`, `test_operator_outage_offline_site_limit_and_deferred_how_to`).
- **Grounding Gate tất định:** `GroundingGate` dựng tập `GroundedClaim` chuẩn tắc từ kết quả đã phân quyền, kiểm khớp từng trường (`value`, dấu `patched_minus_baseline`, `subject`, `observed_at`, `unit`, `stage`, `evidence_refs`), giữ nguyên `reason_code="non_comparable_sample"` với `value=None` khi khác mẫu booking, và loại bỏ mọi claim `delta` khi kết quả `unsafe`/`incomplete` (`test_grounding_rejects_wrong_number_subject_time_unit_stage_and_delta`, `test_unsafe_paired_engine_returns_no_delta`, `test_non_comparable_actual_wait_samples_keep_coverage`).
- **Zero Live State Mutation:** Kiểm chứng trực tiếp bằng spy trên `rt.store`, `rt.sinks`, `realtime.broadcast`, `repository` và `rt.simulator.snapshot_physics_state()` trước/sau WHY & WHAT-IF (`0` ghi DB nghiệp vụ, `0` phát WS, `0` đổi trạng thái vật lý live).

---

## 8. Lệnh chạy Demo cho Mentor (Tối 25/11/2026)

Chi tiết kịch bản và tài khoản mẫu nằm tại [G6A_DEMO.md](G6A_DEMO.md). Tóm tắt nhanh từ thư mục gốc `/home/lehieu/Projects/P-019`:

```bash
# 1) Chạy nhanh toàn bộ kịch bản qua CLI (xuất JSON đã lọc theo quyền):
.simulator/bin/python eval/evidence/2026-11-26-ai4-4-4a/run_demo.py --out /tmp/chargepilot-g6a-demo.json

# 2) Chạy trực tiếp Dashboard Web (2 terminal):
# Terminal 1 — Backend API kèm dữ liệu fixture tại 127.0.0.1:8000:
.simulator/bin/python eval/evidence/2026-11-26-ai4-4-4a/run_demo.py --serve

# Terminal 2 — Frontend tại http://localhost:3000/login (mật khẩu chung: fixture-only-passphrase):
cd frontend && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

---

## 9. Giới hạn còn lại (Known Limitations)

1. **Real LLM Provider (`PENDING`):** Chưa có API key được cấp phép trong môi trường hiện tại; cần chạy smoke với provider thật và bộ đánh giá độc lập ở G7 trước khi đóng release.
2. **PostgreSQL Runtime (`PENDING`):** Các cổng kiểm thử và demo hiện chạy trên SQLite tạm qua Alembic `head`; xác minh PostgreSQL thật thuộc G7.
3. **HOW-TO Engine (`DEFERRED` sang G5/G6B):** Hiện nhận diện đúng `HowToIntent` nhưng trả `feature_not_available` theo đúng ranh giới phạm vi G6A.
4. **In-memory Single-Worker Jobs & Native Solver:** `WhatIfJobs` lưu trong RAM của một tiến trình ứng dụng (tối đa 4 job chờ, giữ tối đa 64 bản ghi, TTL 300 giây); hủy job dừng coroutine ngay và chặn bước tiếp theo, nhưng một lệnh giải LP HiGHS đơn lẻ đang chạy trong worker thread có thể hoàn tất nốt bước hiện tại.
5. **Advisory-Only (`applied=false`):** Mọi kết quả Copilot chỉ để tham khảo, không tự động áp lệnh hay sửa lịch thật (AI-1 nằm ngoài phạm vi).

---

## 10. Khả năng mở rộng cho HOW-TO (G5 & G6B)

- **Intent & Transport:** `CopilotIntent` đã định nghĩa sẵn `HowToIntent` với các mục tiêu chuẩn (`max_soc_by_deadline`, `earliest_completion_for_target`, `min_tested_site_limit_for_sla`, `other`). Khi G5 hoàn tất, G6B chỉ cần bổ sung `HowToReply` vào discriminated union `CopilotResult`, mở rộng `CopilotJob.job_kind` (`"what_if" | "how_to"`) và nối handler trong `CopilotIntegration` mà không phá vỡ hợp đồng WHY/WHAT-IF.
- **Engine & Workload Sharing:** G5 có thể chụp **một** `CapturedSnapshot` duy nhất, chạy **một** nhánh `baseline` dùng chung cho tối đa 8 ứng viên tìm kiếm hữu hạn (tái sử dụng nguyên vẹn cơ chế replay `known_at(T)` và `WhatIfJobs` + single-worker `solver.run_async`). `GroundingGate` mở rộng bằng phương thức `for_how_to()` chiếu danh sách ứng viên đã kiểm chứng sang `GroundedClaim`.

---

## 11. Hướng dẫn Rollback

- Trên cây sạch đã áp G3 và G4, kiểm tra và gỡ riêng toàn bộ G6A bằng một lệnh:
  ```bash
  git apply --reverse --check eval/evidence/2026-11-26-ai4-4-4a/candidate.patch
  git apply --reverse eval/evidence/2026-11-26-ai4-4-4a/candidate.patch
  ```
- Thao tác này hoàn tác trọn vẹn cả 20 đường dẫn G6A (gỡ mount `/api/v1/copilot` trong `src/main.py`, khôi phục `deps.py`/`api.py`/`errors.py`, khôi phục `frontend/openapi.json`, `schema.d.ts`, trang `/resident` & `/operator`, và xóa các tệp mới của G6A), đưa hệ thống trở về đúng trạng thái **Approved G4** (`5f7e86292514ed9c19d9a7f43e3d436b0b5a9bb0`) đồng thời giữ nguyên luồng đặt lịch F1. G6A **không** thêm migration Alembic nào nên không cần downgrade cơ sở dữ liệu.

**STOP — WAITING_FOR_TECH_LEAD_REVIEW (GATE 6A)**
