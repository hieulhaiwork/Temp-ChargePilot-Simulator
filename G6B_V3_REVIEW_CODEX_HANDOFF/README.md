# ChargePilot SC-16 / G6B — final independent review of Carbon V3 & Codex handoff
**Date:** 2026-11-26 (VN)  
**Published mirror candidate:** [92f091343770c24ba017c343c5a326c86bc622bb](https://github.com/hieulhaiwork/Temp-ChargePilot-Simulator/commit/92f091343770c24ba017c343c5a326c86bc622bb)  
**Verdict for published V3:** CONDITIONAL PASS — two implementation-level blockers in the bounded clarification and SSE admission lifecycle. All prior semantic binding findings are closed in their independently exercised scope.  
**Local remediation candidate:** validated separately, **not pushed, committed or officially accepted**. Use v3-targeted-fix.patch to close the residual issues in actual branch. Do not restart broad NLP work.

## 1. Published V3 independent verification (actual run)

| Gate | Result |
|---|---|
| Full backend | 861 passed, 8 pre-existing forecast skips, 77.89 s |
| Focused G6B | 23 passed |
| G2–G5 + G6A | 167 passed |
| Legacy F1 | 97 passed |
| Architecture | 43 passed |
| Standalone simulator | 180 passed |
| Original independent probes: 3 single-turn + 2 negative multi-turn + 2 positive multi-turn | 7 passed |
| Ruff lint/format, OpenAPI, offline F1 dataset (55) | pass |
| Docs | mirror FAIL, only .env.example missing (known from former mirror; Carbon reports original file present in private base). Do not fabricate file. |
| FE Vitest / lint / typecheck / gen:api and schema parity / Webpack / Turbopack | 66 passed; all seven gates passed |
| Chromium two roles + ranked | both pass; Chromium 158.0.8127.0; 94 kW, partial, applied=false |
| B1/B2 additional probes | three cases fail as described below |

Focused, regression, legacy and architecture are subset counts. No changes in Unified Core/engines vs approved G5 or frontend/prompts vs V2. Tests use temporary SQLite and scripted model seam, real HTTP/API and engine, no production LLM/PG or 1000-user load claim.

Provenance: candidate.patch SHA256 fe10d8325fac0ccffb2b2b543f0463979aaebe390ca5a6c4240a869e3bdc4ee1; verification-bundle.zip SHA256 e00c04e654af1881484da9f6a5fbc902e085d9d0ab61b7471081016ee896be98. Outer and inner CONTENTS checksums pass, three historic patch hashes match. 50/51 candidate file hashes+Git blob IDs and 39/40 executed-file hashes match mirror; only .gitignore differs. Forward and reverse apply check excluding .gitignore passed. Mirror still tracks 129 unbundled raw files. Primary private branch is not independently inspected; don't include raw logs/internal collab history in product PR. Preserve baseline .env.example and run docs gate on intended private branch.

## 2. Two implementation blockers and local remedy

### B1 — truncation of pending request
- API accepts up to 5000 chars. finalize_node stored only first 1000 chars of a user turn.
- Reproducer: 1266-character valid question, simple site SLA request first, explicit future start ("Bắt đầu từ ngày mai lúc 18h00.") after char 1000. Model asks bounds. User supplies "Thử 22 đến 106 kW." Result job succeeds immediately because the scheduled condition was removed before validation. This is deterministic data loss, not held-out NLP capability.
- Local fix: reject an oversized *pending clarification* with unsupported/restate message rather than silently truncate. Preserve 3-turn/1000-char/300s cap and public ChatRequest contract. A complete valid single-turn request is unaffected.
- Regression explicitly checks no snapshot/job after rejection.

### B2 — real ASGI SSE disconnect leaks admission permit
- Carbon's test called generator.aclose() directly. Under actual Starlette ASGI 2.3 streaming response path, disconnect cancels the AnyIO task group. Awaiting _abort_turn_state in cancelled scope raises cancellation before _release_thread; result after disconnect: global turns=1, actor count=1, active threads=1, pending persisted and turn_in_progress=True.
- Immediate disconnect before generator start also leaves counters at 1 because reservation happened before generator execution.
- This is a release/cancellation regression, not a performance benchmark. Repeated disconnects can exhaust the configured 8 global turns even when the jobs have stopped.
- Local fix: idempotent cleanup function shared by the iterator and a StreamingResponse subclass wrapping the ASGI call; bounded 2s shield for async state cleanup and unconditional synchronous permit release in finally. Normal complete response preserves legitimately pending clarification, HITL interrupt stays protected. No contract or engine change.

## 3. Tested patch ready for Codex
File: v3-targeted-fix.patch  
SHA256: 3fbf0bdb01e73628a423715a09eaf4b492ffae7bdbcdabdf65cde48ea5d6f9d5  
Exact base source: published mirror V3 92f0913, which corresponds to Carbon V3 patch + private base.
Only 3 files: src/api/routes.py, src/llm_chat/nodes/finalize_node.py, tests/test_api/test_g6b_v3_bounds_and_disconnect.py.
`git apply --check` succeeded against unmodified mirror.
Evidence for local patch in independent detached worktree:
- 3 new regression tests passed individually.
- Full backend **864 passed, 8 skipped in 84.32 s** (includes all existing 861 tests).
- Ruff lint/format for changed files pass, OpenAPI parity pass, git diff --check pass.
- Both Chromium two-role and ranked smoke pass using unchanged frontend production build. Browser 158.0.8127.0.
- FE unchanged; full 66 tests and both builds independently passed on V3.

### Instructions to Codex (next session)
1. Work in actual private feature branch; check it matches the V3 candidate executable sources. **Do not reset or overwrite teammate work.** Preserve all existing Carbon edits.
2. Use `git apply --check /path/to/v3-targeted-fix.patch` then `git apply /path/to/v3-targeted-fix.patch` only if cleanly applicable. Review diff and test cases; if parity differs, stop and reconcile, don't force.
3. Run `pytest -q tests/test_api/test_g6b_v3_bounds_and_disconnect.py tests/test_api/test_unified_copilot.py` and all established verify gates on clean export of actual private base + final patch. Ensure docs with genuine .env.example. Regenerate patch/bundle/hashes, preserve V3 history and frozen scope. Don't publish secrets or raw collaboration log.
4. Report exact SHA and evidence for independent final approval. No merge or G7 implementation before approved. No further speculative rewrites.

## 4. Proposed plan for 27/11/2026 (Gate 7 validation, after gate closure)

A. Preflight: close B1/B2 with supplied tested patch; verify private clean-export parity, CI and actual .env.example; freeze reviewed commit, scenario/config, package versions and test dataset. Save rollback ref/tag only if owner approves. Check develop update and FE integration conflicts before PR.

B. Functional end-to-end (real LLM provider + isolated test DB/runtime; no production actions):
- Resident: WHY queue/charging/deadline; WHAT-IF target/deadline; HOW-TO max SOC by deadline and earliest completion; clarification, no sacrifice without consent, no live change; booking/HITL confirm/reject, logout voice.
- Operator: WHY station/booking; WHAT-IF source/outage; HOW-TO finite site power/SLA/AC constraints ranked 94kW oracle; validate evidence refs, partial/unknown states. 
- ≥60 prewritten held-out Vietnamese cases, expected intent/tool and exact parameters or expected clarification/unsupported; separate dev/test corpus. Judge tool selection, slot exact-match, fail-closed behavior, grounded claims, role access, applied=false and engine result vs independent oracle. No claims based just on LLM text.
- Edge cases: malformed/ambiguous units, relative time crossing simulator clock, unclear scope, expired clarification, refusal/reset, multi-turn, conflicting constraints, permission/foreign job, job cancel/expiry, no feasible option, stale snapshot, source drop, sensor noise and outage. Verify live state not mutated by simulation.

C. Load and resilience (G7): progressive 1→10→50→100→500→1000 concurrent arrivals against isolated environment with scripted provider first, then controlled authorized live LLM. Separate success latency and immediate 429/capacity rejection. Measure accepted job rate, throughput/queue wait, p50/p95/p99 end-to-end, live replan p95 against ≤2s target, CPU/RAM and growth, cancellations, request/timeouts, provider quota and cost; confirm permits return to zero and memory/checkpointer policy. Rate-limit 1000-user provider test, avoid uncontrolled spend. Burst acceptance ≠ 1000 simulations simultaneously; capacity rejection is expected while preventing crash. No declaration of production capacity until tested.

D. Summarize pass/fail and prioritize severity. No new features during verification. Test in isolated environment; don't merge based on green unit tests alone.

**Decision:** the published V3 source is not yet formally approved. The local patch has already closed both known implementation issues in the independently tested scope. Stop feature development tonight; tomorrow start with the small validated handoff rather than another broad remediation cycle.
