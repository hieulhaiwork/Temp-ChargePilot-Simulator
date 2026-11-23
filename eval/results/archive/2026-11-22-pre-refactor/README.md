# [DEPRECATED — ARCHIVE] Bảng benchmark A–D trước refactor (2026-11-22)

> **Không dùng để so sánh với benchmark mới.** Giữ nguyên số làm lưu trữ lịch sử (Phase 4, quyết định 1 và 8 của
> Tech Lead — `docs/refactor/TECHLEAD_PHASE4_DECISIONS.md`).

- `benchmark.json`, `benchmark.md`: sinh bởi `eval/run_benchmark.py` lúc 2026-11-22 18:44 UTC (commit `098877a`), trước
  refactor Unified Core. Trước đây nằm ở `eval/results/` và được `GET /simulation/benchmark` trả về; chuyển vào đây
  bằng `git mv` (nội dung không đổi).
- Chứa A_fcfs / A_edf / B / C / D — chiến lược của **LP backend đã xoá** ở ADR-019 Phase 3
  (`docs/refactor/DELETION_MANIFEST.md`) và đã bỏ khỏi `StrategyName` / OpenAPI / S8 ở Phase 4. Các dòng B0–M3b trong
  file đo bằng runtime cũ (interval quyết định 15' cố định, chưa có kernel dùng chung), khác điều kiện với baseline mới.
- Hợp đồng API hiện hành **không đọc được** file này (enum `StrategyName` không còn A–D). Đọc bằng tay hoặc `json`.
- Baseline hiện hành: [`eval/evidence/2026-11-23-refactor-phase3-baseline/`](../../../evidence/2026-11-23-refactor-phase3-baseline/).
