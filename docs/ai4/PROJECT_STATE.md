# AI-4 — Trạng thái review

- **G0 P0 APPROVED**. Tech Lead review evidence tại mirror `d520ffb28b32b94099277c48af9b8f38ec656ac0`. Mapping tuần tự local `ce23136` → mirror `4f1477e` → mirror evidence `d520ffb`. [Báo cáo P0](PHASE_P0_REPORT.md)
- **G1 AI-4.0 APPROVED**. Tech Lead nghiệm thu remediation tại mirror `fed2c5e395c3a6ac3e1798ce52d0e4b4e4abd009` (tương ứng local HEAD `490f43300afb05ef7e809099a77e0c7174e272fb`). Chi tiết ở [báo cáo G1](PHASE_4_0_REPORT.md), [ADR](ADR_AI4_SCOPE.md) và [contract](FOUNDATION_CONTRACT.md).
- **G2 AI-4.1 APPROVED**. Tech Lead nghiệm thu Deterministic WHY Engine tại mirror `aa37ca55978f99009c6d4b25c0676d87eac7fa7b` (tương ứng local HEAD `4658b1f068350c130ed5ed1a744c19a7b8cd522c`; các vòng review trước: `6ba13b8` `CHANGES REQUIRED` → `2d15ca1` `CONDITIONAL PASS` → `aa37ca5` `APPROVED`). Chi tiết ở [báo cáo G2](PHASE_4_1_REPORT.md).
- **G3 AI-4.2A (Counterfactual Foundation) đang triển khai (chưa nghiệm thu)** trên `feature/ai-4`: chỉ bao gồm atomic snapshot, `known_at(T)` event manifest, independent sandbox forks, paired no-op runner và additive Outcome Ledger; chưa triển khai các business patches của WHAT-IF Engine (G4).

G1-F05, G1-F06, G2-F01–G2-F09 và G2-F05a/G2-F05b đã được Tech Lead nghiệm thu tại `aa37ca5`. PostgreSQL runtime, production grounding validator và semantic oracle mở rộng thuộc backlog G6/G7. Business patches của WHAT-IF (AI-4.2B / G4), HOW-TO (G5), LLM integration (G6), AI-1 và frontend Copilot chưa triển khai.
