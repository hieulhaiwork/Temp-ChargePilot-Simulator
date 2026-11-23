# PHASE4 — nhánh `feature/unified-core-p4-core` (quyết định 2, 3, 6, 7)

> Gốc `70d0eaf`. Báo cáo viết khi phiên bị giới hạn sử dụng: phần "Còn lại" liệt kê rõ việc chưa chạy.

## 1. Commit

| Commit | Quyết định | Nội dung |
|---|---|---|
| `c458f68` | 7 | `StationKernel` → `src/simulator/core/kernel.py` (+ `algorithms`, `queue`, `ev2gym_adapter`, `charging_models/`); `HybridSimulator` → `src/simulator/hybrid.py`; `evaluation/` → `src/simulator/evaluation/`. Xoá toàn bộ `src/simulator/src/` (shim), `src/simulator/base.py`, `__getattr__` của `src/guard/physical`. Test chủ simulator chỉ đổi import. Luật kiến trúc mới (chặt hơn) |
| `ce13153` | 2 | `EventType.CHARGE_COMPLETED`; `HybridStation` dịch đúng loại; `run_forever` gộp sự kiện một lượt vào `on_minute` (một lần tính lại); OpenAPI + `gen:api`; nhãn "Sạc xong" ở danh sách sự kiện vận hành (bảng nhãn sự kiện nằm ở `frontend/src/app/operator/page.tsx`, S6 không có bảng nhãn riêng) |
| `ec53892` | 3 | Root-cause + sửa sai lệch AC +1,97 kW; tách deadband / budget deviation / vi phạm cứng; ưu tiên giảm tải |
| `8e0690a` | 6 | DecisionTrace backend, `Command.correlation_id`, bảng `decision_traces` (migration `0002`), artifact JSONL |

Chi tiết xoá / di chuyển: `DELETION_MANIFEST.md` mục Phase 4.

## 2. Root-cause sai lệch AC +1,97 kW (quyết định 3)

Tái hiện: `peak_evening` (và `connector_failure`, cùng số) seed 2 M3b, phút 560. Kế hoạch đã qua Physical Guard dùng
**đúng** trần 33,25 kW đầu ra (= 35 kW lưới × 0,95): AC 7,278906, DC-01-2 22,372009, DC-01-1 (xe mới) 3,599085.
Lịch / lệnh làm tròn **gần nhất** 3 chữ số → AC 7,279 (+0,094 W); cộng trạng thái làm tròn 6 chữ số → lô = 35,0000095
kW lưới > 35 + 1e-7 → luật `total_power_limit` chặn cả lô, **kể cả lệnh giảm AC** 9,25 → 7,28; setpoint cũ chạy tiếp
→ AC vượt budget 1,971 kW (không vượt trần cứng).

Sửa (không nới trần cứng, TOL vẫn 1e-7):
- `quantize_kw` (`src/models/control.py`): setpoint trong lịch / Command làm tròn **xuống** 0,001 kW.
- `total_power_limit` không chặn lệnh không tăng công suất cổng (lệnh tăng vẫn bị chặn).
- Giảm tải khi trạm đang vượt trần cứng hoặc lệnh khẩn cấp: không bị anti_flapping / HITL giữ (ghi chú "Giảm tải an
  toàn", báo sau). Lệnh tăng chỉ hợp lệ nhờ lệnh giảm đang chờ duyệt thì **không** áp (fail-safe chặt hơn trước).
- Kernel: `AppliedResult.command_deadband_kw` / `budget_deviation_kw` / `stale_setpoint_kw` / `violations` riêng,
  `deviation_metrics()`, log riêng.

Test: `tests/test_guard/test_load_reduction.py` (lô phút 560 với round-nearest bị chặn, floor qua; giảm tải / HITL /
anti-flapping), `tests/test_simulator/test_replan_events.py` (chạy lại kịch bản: không còn deviation).

## 3. Benchmark backend trước / sau (B0/M2b/M3a/M3b × 5 kịch bản × seed 1–5)

So `eval/evidence/2026-11-23-refactor-phase3/raw/backend_benchmark_seeds1-5.json` (P3) với bản sau sửa (3).
`compare_backend_benchmark.py` **lệch** (có chủ ý, sửa lỗi thật). Trung bình 5 seed, chỉ dòng đổi đáng kể:

| kịch bản | policy | on_time P3 → P4 | giao kWh P3 → P4 | chi phí VND P3 → P4 | đỉnh kW | lệnh bị chặn |
|---|---|---|---|---|---|---|
| peak_evening / connector_failure | B0 | 0.151 → 0.198 | 193.1 → 265.8 | 452,170 → 679,750 | 32.48 → 33.25 | 63.4 → 0.6 |
| peak_evening / connector_failure | M2b | 0.172 → 0.205 | 216.2 → 272.3 | 526,081 → 693,915 | 32.86 → 33.25 | 25.4 → 0.2 |
| power_drop | B0 | 0.158 → 0.192 | 213.3 → 245.8 | 506,863 → 613,831 | 32.48 → 33.25 | 38.2 → 1.0 |
| power_drop | M2b | 0.179 → 0.199 | 216.1 → 248.9 | 526,854 → 620,946 | 32.86 → 33.25 | 21.0 → 0.2 |

Các dòng khác (M3a/M3b mọi kịch bản; mọi policy ở `hybrid_*`) chỉ lệch ≤ 0,2 kWh / ≤ 500 VND. `power_limit_violations`
= 0 ở mọi run; đỉnh 33,25 kW = đúng trần. **Lý do:** B0/M2b (equal share) thường dùng đúng trần lưới; làm tròn lên khiến
Guard chặn lệnh hợp lệ ~60 lần / run ở Phase 3. Quy khác biệt (evidence `eval/evidence/2026-11-23-refactor-phase4/raw/`):
biến thể chỉ lượng tử hoá xuống cho số **giống hệt** bản đầy đủ; biến thể chỉ ưu tiên giảm tải: B0 on_time 0.151 → 0.144
(lệnh giảm qua, lệnh tăng cùng lô vẫn bị chặn). Bảng sinh bằng `scripts/refactor/summarize_backend_benchmark.py`.

## 4. Cổng kiểm

| Kiểm | Kết quả | Log |
|---|---|---|
| AST (manifest phase3-merged trừ `__all__` của shim `charging_models/base.py` đã xoá; `moves.txt`) | 114/114 SAME, rc=0 | `raw/phase4-p4core/ast_gate_step7.txt` |
| Golden: `pytest src/simulator/tests` + `run_sim_kpi_gate.py` (38 so sánh: output gốc `70d0eaf` + evidence 2026-11-22, module map + `charging_models`) | 163 passed; 38/38 OK, CSV trùng byte (sau bước 7) | `raw/phase4-p4core/kpi_gate_step7.txt` |
| `pytest src/simulator/tests tests` (sau bước 6) | 659 passed, 8 skipped | — |
| ruff check + format `src tests scripts/refactor` | pass | — |
| `export_openapi.py --check` | khớp | — |
| frontend `lint`, `typecheck`, `test` | pass (28 test) | — |

## 5. Còn lại (chưa làm do hết hạn mức phiên)

- Chạy lại cổng golden + AST **sau** bước 3 và 6 (kernel chỉ đổi nhánh non-strict của backend; chưa có log).
- Benchmark backend **sau** bước 6 (DecisionTrace không đổi quyết định; chưa đo xác nhận) và lưu JSON bản đầy đủ vào
  `eval/evidence/2026-11-23-refactor-phase4/raw/`.
- `npm run build`; ghi log cổng kiểm vào `docs/refactor/raw/phase4-p4core/`.
- Cập nhật ADR-019 (mục Phase 4), `CLAUDE.md` (DecisionTrace), `EXPECTED_FAILURES.md`.

## 6. Expected failures

Không có test fail. `compare_backend_benchmark.py` lệch có chủ ý (§3).

## 7. ESCALATION

- Ưu tiên giảm tải bỏ qua HITL **chỉ** khi trạm đang vượt trần cứng hoặc lệnh khẩn cấp — dựa trên quyết định 3 của
  Tech Lead. Đề nghị chủ dự án xác nhận định nghĩa "giảm tải cần cho an toàn" này.
- KPI B0/M2b tăng mạnh (§3) do sửa lỗi thật; baseline chính thức cuối cần sinh lại sau khi gộp.
