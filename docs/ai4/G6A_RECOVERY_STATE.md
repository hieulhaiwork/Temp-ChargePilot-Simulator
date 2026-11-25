# G6A recovery

## Baseline và architecture audit

- G4 APPROVED tại mirror `eb5967ae720b46b089b09e03063aa2c727ca5fd8`. G6A bắt đầu từ branch `feature/ai-4`, local HEAD `4658b1f068350c130ed5ed1a744c19a7b8cd522c`, G3 accepted patch rồi G4 final `e8ae5cedbbe5af0a0a05d63f3dbb4ea6ac22fda40a4628a2cf7abca82be10d0f`. Xác minh 332 product/test/config/frontend paths, 12/12 candidate blobs và 5/5 remediation blobs. PostgreSQL runtime PENDING.
- FastAPI mount feature routers dưới prefix `/api/v1`. JWT xác thực user và role qua dependency hiện có. Deployment hiện có một station do config server xác định. `src/api/routes.py` giữ chat booking F1. WHY dùng DecisionTrace và có authorization/privacy projection. WHAT-IF có atomic snapshot và `WhatIfJobs` trên single-worker solver.
- G6A thêm adapter gọi structured intent provider, orchestration typed và router riêng. Grounding dùng authorized engine output, kiểm claim theo evidence và dựng response deterministic. Frontend dùng panel chung trên dashboard hai role và client OpenAPI hiện có.
- Đang thực hiện Checkpoint A. [Gate 4 acceptance](PHASE_4_2B_REPORT.md)

## Checkpoint A–D · Backend implementation

- Typed intent union và structured provider adapter đã có. HOW-TO đi qua handler unavailable. Parser có deterministic fallback và làm rõ subject/time/unit. Mốc relative được resolve ở snapshot T khi tạo WHAT-IF.
- Router G6A dùng JWT dependency hiện hành, server station scope, một integration instance trong FastAPI lifespan và job wrapper có kind. WHY và WHAT-IF gọi engine đã duyệt, cùng workload bounds và solver.
- Grounding dùng claim projection, kiểm evidence references và dấu delta, render bằng template. Provider nhận câu hỏi do user nhập cùng giờ và timezone của trạm.
- OpenAPI đã export lần đầu. Đang bổ sung tests tích hợp, role UI và demo fixture.
