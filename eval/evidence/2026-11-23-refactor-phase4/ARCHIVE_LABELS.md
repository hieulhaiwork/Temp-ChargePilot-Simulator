# Nhãn archive / deprecated cho evidence lịch sử (Phase 4, nhánh `feature/unified-core-p4-api`)

> Quyết định 1, 8, 9 của Tech Lead (`docs/refactor/TECHLEAD_PHASE4_DECISIONS.md`): evidence A–D lịch sử giữ nguyên số,
> gắn nhãn deprecated / archive, **không trộn** với benchmark mới. Quy tắc refactor cấm sửa `eval/evidence/**` đã có,
> nên nhãn được ghi ở đây (sổ nhãn trung tâm) thay vì sửa README của từng thư mục.

| Thư mục / file | Chứa | Nhãn | Vì sao |
|---|---|---|---|
| `eval/evidence/2026-11-21/` | R&D trước ADR-016 (simulator offline, latency, AI-1…AI-4) | **archive** | Kiến trúc trước Unified Core |
| `eval/evidence/2026-11-22/` (+ `raw/benchmark.*`, `raw/sim-hardware/live_benchmark.*`, `SIMULATOR_EVAL_EVIDENCE.*`) | Benchmark A–D trên `LiveStation` + HybridSimulator R&D | **deprecated (A–D, `LiveStation`) / archive** | `LiveStation` và LP backend A–D đã xoá (ADR-019 Phase 3), A–D bỏ khỏi hợp đồng (Phase 4). Số `HybridSimulator` (`raw/sim-hardware/`) vẫn là golden của simulator — **không** deprecated |
| `eval/evidence/2026-11-23/` (`raw/benchmark.*`) | Backend `HybridStation` (ADR-018) trước refactor, có dòng A–D | **deprecated (dòng A–D) / archive** | Runtime trước kernel chung (interval 15' cố định); A–D đã bỏ |
| `eval/evidence/2026-11-23-refactor-phase1/`, `-phase2/` (`raw/backend_benchmark_seeds1-5.*`) | Benchmark backend Phase 1–2 (225 run, gồm A–D) | **archive — cổng kiểm của Phase 1–2** | Đo ở semantics trước Phase 3; dòng A–D deprecated. Giữ vì `compare_backend_benchmark.py` của Phase 1–2 dựa vào |
| `eval/evidence/2026-11-23-refactor-phase3/` | Benchmark backend Phase 3 (B0–M3b, 100 run) + cổng kiểm | **hiện hành** (nguồn của baseline) | Chép thành baseline có version ↓ |
| `eval/evidence/2026-11-23-refactor-phase3-baseline/` | Baseline `backend-phase3` / `2026-11-23-phase3` (manifest + số) | **hiện hành, provisional** | `GET /simulation/benchmark` đọc thư mục này |
| `eval/results/archive/2026-11-22-pre-refactor/` | Bảng A–D từng được API trả (trước đây `eval/results/benchmark.*`) | **deprecated / archive** | README riêng trong thư mục |

Không so chéo: Phase 2 ↔ Phase 3 khác cấu hình thời gian (ADR-019 P1); bảng A–D (LP backend) khác mô hình thực thi.
