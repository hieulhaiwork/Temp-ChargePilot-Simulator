# AI-4 — Trạng thái review

- **G0 P0 APPROVED**. Tech Lead review evidence tại mirror `d520ffb28b32b94099277c48af9b8f38ec656ac0`. Mapping tuần tự local `ce23136` → mirror `4f1477e` → mirror evidence `d520ffb`. [Báo cáo P0](PHASE_P0_REPORT.md)
- **G1 AI-4.0 APPROVED**. Tech Lead nghiệm thu remediation tại mirror `fed2c5e395c3a6ac3e1798ce52d0e4b4e4abd009` (tương ứng local HEAD `490f43300afb05ef7e809099a77e0c7174e272fb`). Chi tiết ở [báo cáo G1](PHASE_4_0_REPORT.md), [ADR](ADR_AI4_SCOPE.md) và [contract](FOUNDATION_CONTRACT.md).
- **G2 AI-4.1 (Deterministic WHY Engine) READY_FOR_REVIEW (chưa nghiệm thu)** trên `feature/ai-4`. Lưu ý: commit message local `"Approved phase 4.1"` trên `490f433` là tên commit lịch sử ở local và **không có nghĩa** AI-4.1 đã hoàn thành hay được nghiệm thu. Chi tiết triển khai, kết quả đánh giá xác định và regression gates ở [báo cáo G2](PHASE_4_1_REPORT.md).

G1-F05 và G1-F06 đã được triển khai trong candidate AI-4.1 (chờ Tech Lead review Gate 2). PostgreSQL runtime vẫn PENDING (chờ môi trường Postgres thật / CI). WHAT-IF (AI-4.2A/4.2B), HOW-TO, LLM integration, AI-1 và frontend Copilot chưa triển khai.
