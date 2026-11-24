# PHASE P0 — Baseline Verification (G0)

**Phase P0 | Status READY_FOR_REVIEW**  
**Branch** `feature/ai-4` · **Code thực chạy / local base** `ce23136d50ad08abb7c9fdc98eff791875d24516`  
**Mirror base** `4f1477e84ac818549a69a74eb00e4b827fae230e` · **Workspace HEAD cuối** `d2b5d4869bff35ad9e417bee504c6dbf652258b1`  
**Evidence commit** Chưa commit gói evidence P0 hoàn chỉnh.  
**Working tree** Báo cáo và evidence P0 hiện diện trong workspace.

Baseline thực thi tương đương mirror đã review. Full backend và simulator đều chạy. Golden chính thức tái lập đủ 38/38 với byte representation CRLF của fixture lịch sử. Benchmark backend 100/100 khớp toàn bộ KPI ngoài timing và khớp các bộ đếm vi phạm. R01–R05 đã tái hiện trên baseline. G0 đang chờ Tech Lead xác nhận ledger, branch và phạm vi.

## Baseline, phạm vi và diff

So path/mode/blob cho hai commit ban đầu thấy 12 path quản trị chỉ có trong repo chính, gồm CI và hooks. Tất cả file còn lại khớp. Workspace HEAD tiến trong khi chạy tới commit thêm Master Plan, `collaboration_chat.md` rỗng và bản đầu của runner evidence. Các lần kiểm tra tiếp tục dùng checkout tạm pin tại code base ở đầu báo cáo. Diff product, config, migrations, frontend, tests và frozen baseline so với commit thực chạy rỗng. [Baseline và module map](BASELINE.md) · [Diff commit phát sinh](../../eval/evidence/2026-11-24-ai4-p0/raw/concurrent-commit-paths.stdout.txt)

| File thay đổi trong P0 | Nội dung |
|---|---|
| `docs/ai4/PHASE_P0_REPORT.md`, `BASELINE.md` | Gate report, đối chiếu Git/môi trường, module map, API và topology |
| `docs/ai4/ISSUES.md`, `ADR_AI4_SCOPE.md`, `PROJECT_STATE.md` | Ledger R01–R09, scope/API thiết kế Proposed và trạng thái pending |
| `eval/evidence/2026-11-24-ai4-p0/` | Repro harness, probe, verifier manifest, raw logs/outputs và checksums. `run.sh` có chỉnh thêm tham số pin commit và tùy chọn bỏ lượt async ban đầu phục vụ tái lập khi sandbox hạn chế. |

Phạm vi thực hiện là P0. Diff do lượt này tạo nằm trong tài liệu và evidence. Kiến trúc, sản phẩm, test suite và mọi baseline hộp chuẩn đã track nằm ngoài diff P0. Không có commit, merge hoặc push do lượt triển khai này thực hiện.

## Regression và gate

| Kiểm tra thực chạy | Exit | Kết quả |
|---|---:|---|
| `python -m pytest tests/ -q -rs` | 0 | **604 passed, 8 skipped** ở F6/T2.3 và ca FR9 forecast. Bao gồm architecture, admission, safety delivery, fork và DecisionTrace. |
| `python -m pytest src/simulator/tests/ -q` | 0 | **180 passed** |
| `ruff check src tests scripts/refactor eval` và `ruff format --check src tests scripts/refactor eval` | 0 / 0 | Pass trên checkout pin baseline. Hai Python helper evidence cũng qua Ruff. |
| `python scripts/check_docs.py` và `python scripts/export_openapi.py --check` | 0 / 0 | Docs và OpenAPI snapshot đạt |
| `python eval/run_agent_eval.py --offline` | 0 | 55 mẫu hợp lệ và đạt ngưỡng kích thước dataset. Đây là F1 offline. |
| `python scripts/refactor/compare_ast_manifest.py docs/refactor/raw/phase4-final/preserved_baseline_manifest.txt -- src` | 0 | 114 định nghĩa so khớp, 0 undeclared / 0 declared changes |
| `run_sim_kpi_gate.py run` và `compare` với module map đã duyệt | 1 LF / 0 CRLF | **35/38 LF**, **38/38 CRLF**. Cả 32 cặp với historical checkout khớp ở cả hai lần. |
| `python eval/run_benchmark.py --seeds 1,2,3,4,5` | 0 | 100 lượt hoàn thành |
| `compare_backend_benchmark.py <frozen> <candidate>` và verifier provenance | 0 / 0 | **100/100, 0 problems**. Cùng resolved experiments và fingerprint theo 4 policy, cùng time config, đủ 100 khóa duy nhất, cùng từng bộ đếm vi phạm. |

**602/604.** Raw log Final Acceptance lưu **602/8**, báo cáo lịch sử ghi **604/8**. Diff `a9def2f..ce23136` có thêm một test provenance và một case parametrize cho frozen baseline. Lượt P0 có **604/8** thực chạy. Git diff giải thích chênh hai case trên hai cây, còn raw log 602 không ghi SHA nên commit chính xác của log đó chưa được xác minh. [Historical log](../../docs/refactor/raw/final-acceptance-merged/pytest_tests.txt) · [Diff test](../../eval/evidence/2026-11-24-ai4-p0/raw/frozen-additional-tests.stdout.txt) · [P0 pytest](../../eval/evidence/2026-11-24-ai4-p0/raw/backend-tests-retry.stdout.txt)

**Golden.** Lần LF báo ba `/metadata/scenario_sha256` lệch trên report của `mvp1`, `mvp1_m3` và VinFast. CLI băm bytes input. Hash CRLF của hai fixture khớp chính xác hash lưu trong evidence lịch sử, và JSON parse của LF/CRLF bằng nhau. Rerun bằng checkout tạm với `core.autocrlf=true` trên cả baseline candidate và historical `70d0eaf4f326b9a9317258bec44d7d71bbe60ffe` đạt 38/38 với comparator nguyên bản, gồm CSV byte-identical. Kết quả LF vẫn được giữ trong evidence. [LF](../../eval/evidence/2026-11-24-ai4-p0/raw/golden-compare.stdout.txt) · [SHA fixture](../../eval/evidence/2026-11-24-ai4-p0/raw/golden-scenario-hashes.stdout.txt) · [CRLF](../../eval/evidence/2026-11-24-ai4-p0/raw/crlf-golden-compare.stdout.txt)

**Benchmark.** 5 scenario, 4 policy v1 B0/M2b/M3a/M3b, seed 1–5. Physics step 1 phút, decision interval 15 phút và 4 cổng. Configuration hashes và per-policy experiment fingerprints khớp frozen. Cả hai bộ có 0 phút vượt công suất lấy mẫu, 0 post-apply hard violations và 0 rejected allocations. Comparator loại đúng `replan_p95_seconds`. Trong 100 lượt, min/median/max của p95 từng lượt là **1,9 / 8,55 / 16,2 ms** ở P0 và **1,5 / 9,05 / 15,9 ms** ở frozen. Không lượt nào vượt 2 s. Phép đo wall-time khác OS, CPU/mức tải chưa đối chứng và phiên bản Python/NumPy, nên chênh timing chỉ mô tả hai lần chạy. Đây là benchmark replan của topology 4 cổng. [So KPI](../../eval/evidence/2026-11-24-ai4-p0/raw/benchmark-compare-retry.stdout.txt) · [Manifest và provenance](../../eval/evidence/2026-11-24-ai4-p0/raw/backend-benchmark/manifest.json) · [Timing và violations](../../eval/evidence/2026-11-24-ai4-p0/raw/benchmark-provenance.stdout.txt)

### Fail → pass và tái lập

- Sandbox ban đầu trả EPERM khi gửi qua Unix socketpair. Các lượt backend/benchmark đầu bị dừng; backend, benchmark và probe hoàn tất sau khi được phép chạy ngoài sandbox trong checkout tạm với SQLite riêng. Exit 130 của phiên dừng, timeout 124 và log partial được lưu. Một retry probe exit 1 do assertion về độ dài trace đặt sai. Probe cuối exit 0 và xác nhận R01–R05. Sản phẩm vẫn chạy đúng code baseline trong mọi lần. [Raw](../../eval/evidence/2026-11-24-ai4-p0/raw/interrupted-sessions.txt) · [Exit codes](../../eval/evidence/2026-11-24-ai4-p0/raw/exit-codes.tsv)
- Lệnh, stdout/stderr, seed/scenario, config hashes, benchmark manifest, raw golden JSON/CSV trong archive và môi trường nằm cùng thư mục evidence. Hướng dẫn chạy lại pin code commit và ghi output vào scratch. [Reproduce](../../eval/evidence/2026-11-24-ai4-p0/README.md)

## Issue, giới hạn và quyết định chờ duyệt

- **R01–R05 confirmed** gồm fork mất safety hold, default thiếu detailed trace, v2 báo guard pass khi có vi phạm/zero samples, safety hold mang nhãn pending approval và power stage v2 mơ hồ. Probe dùng fixture tổng hợp và đi qua control loop. Dispatcher-only, isolation stateful và delivery regressions được kiểm qua suite hiện có. [Ledger](ISSUES.md) · [Probe](../../eval/evidence/2026-11-24-ai4-p0/raw/issue-probe-final.stdout.txt)
- **R07 hypothesis** về atomic capture/read/outbox. **R06** là paired WHAT-IF chưa triển khai. **R08** còn xác minh Postgres/provider/deploy thật ở G7. **R09** thuộc MVP-3.5. Chưa chạy frontend lint/typecheck/test/build trong P0 vì scope không đổi API/schema/UI. PDF Research SC-16 không có trong workspace. Các mục này không cản các gate P0 đã liệt kê. [Ledger](ISSUES.md)
- Tech Lead cần duyệt baseline/branch mapping, mức ưu tiên ledger, Postgres JSON payload và indexed lookup, schema backend có version, snapshot locking/outbox readiness, cách ghi SOC/energy/cost và quyền Operator, canonical API, giới hạn job và phạm vi HOW-TO hữu hạn/AI-1 deferred. [ADR Proposed](ADR_AI4_SCOPE.md)

## Acceptance checklist

| G0 | Kết quả |
|---|---|
| HEAD đúng hoặc có mapping mirror rõ, environment và topology xác minh | **PASS** |
| Module map, API, kiến trúc và full regression có raw log | **PASS** |
| Golden full và benchmark đầy đủ, nguyên baseline/threshold | **PASS** với golden CRLF phù hợp provenance. Lượt LF ghi **FAIL** ở metadata. |
| R01–R09 phân loại, lỗi baseline và giới hạn có evidence | **PASS** |
| Scope ADR Proposed, ownership và API design | **PASS**, tài liệu sẵn để duyệt |
| Postgres/LLM/deploy thật và frontend full build | **NOT RUN**, xem giới hạn trên |
| Tech Lead xác nhận ledger, scope/branch và cho phép phase tiếp theo | **PENDING** |

**Rollback** Có thể hoàn tác riêng các file báo cáo, evidence và diff runner P0. Hai file đầu vào, commit hiện có và frozen artifact lịch sử được giữ theo trạng thái workspace. Không cần rollback app hoặc DB. Các DB thử nghiệm chỉ nằm trong thư mục tạm.

**STOP — WAITING_FOR_TECH_LEAD_REVIEW**
