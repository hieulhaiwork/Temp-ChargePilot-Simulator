# ADR AI-4 — Phạm vi Decision Copilot và HOW-TO hữu hạn

**Trạng thái** Approved tại G0, mirror `d520ffb28b32b94099277c48af9b8f38ec656ac0`.  
**Ngày** 2026-11-24.  
**Quan hệ** Đề xuất thay một phần phạm vi trong ADR-015 §1, dựa trên ADR-013, ADR-014 và ADR-019. Quyết định bổ sung này ghi riêng để bảo toàn lịch sử ADR-013/014/015/019.

## Phạm vi đã duyệt

AI-4 gồm WHY dựa trên trace, WHAT-IF ghép cặp và HOW-TO trên một tập ứng viên hữu hạn. Cả Resident và Operator có đường hỏi bằng ngôn ngữ tự nhiên, giao diện tối thiểu và đường nhập có cấu trúc khi provider không khả dụng. AI-1 negotiation, đề nghị và apply chuyển backlog riêng. Các mục hoãn còn lại của ADR-015 giữ chính sách hiện hành. Zone-budget patch và so sánh policy là SHOULD, cần duyệt phạm vi riêng.

- WHY trả facts theo subject và interval cùng reason codes có chứng cứ. Thiếu dữ kiện trả trạng thái rõ.
- WHAT-IF gồm target SOC, deadline, site grid input limit và connector outage có thời lượng. Từng cặp dùng chung snapshot, known events, policy và horizon. Site limit chỉ hỗ trợ shared supply ở MVP. Tăng vượt nguồn lắp đặt mang nhãn giả định hạ tầng.
- HOW-TO thử một biến cho mỗi mục tiêu. Resident có `max_soc_by_deadline` và `earliest_completion_for_target`. Operator có `min_tested_site_limit_for_sla`. Mặc định tối đa 8 ứng viên và 1 baseline, horizon tối đa 24 giờ và có thể cấu hình. Báo tập đã thử, trạng thái từng run, trade-off và SLA gốc/revised. Kết luận chỉ áp dụng cho các ứng viên đã đánh giá.
- Workflow gọi kernel, optimizer và Guard hiện có. LLM parse intent và diễn đạt facts qua grounding. JWT và server xác định role và ownership. Mọi đề xuất/rollout là advisory, `applied: false`.

## API thiết kế và ownership

| Thiết kế API dưới `/api/v1/copilot` | Quyền và kết quả |
|---|---|
| `POST /query`, `POST /why` | Resident truy xuất booking của mình và dữ kiện tổng hợp được phép. Operator truy xuất trong scope trạm. WHY trả facts có refs, missing evidence và planned/measured stage. |
| `POST /what-if`, `POST /how-to` | Tạo job có giới hạn, trả 202 và job ID. Resident chỉ `revise_vehicle` cho booking của mình. Operator có `site_limit`, `outage` và hypothetical `revise_vehicle` cho booking thuộc trạm mình quản lý. |
| `GET /jobs/{job_id}` | Kiểm ownership từ server, trả trạng thái và kết quả đã lọc. Job trong một worker có TTL. |

`src/models/` sở hữu contract, `src/services/copilot/` sở hữu workflow deterministic, `src/agents/` sở hữu intent/grounded rendering. `src/services/repository.py` và Alembic sở hữu persistence. `src/api/` và frontend dùng convention router/DTO hiện hành. MVP-3.5 sở hữu thuật toán AC/DC và Coordinator. Nhánh được duyệt `feature/ai-4` từ baseline đã đối chiếu, từng pha review riêng.

## Quyết định Foundation đã duyệt

- Postgres JSON payload + indexed lookup theo correlation ID, booking và thời gian là nguồn full trace. SQLite hỗ trợ dev/test. Migration additive, giữ summary-only lịch sử và vòng đời active/closed. JSONL là export tùy chọn.
- Backend trace có version riêng. Tách pre-apply Physical Guard, business Guard, post-apply và fail-safe. Phân biệt proposed, approved, dispatched, held setpoint và actual measured. Lưu evidence refs và experiment provenance tại quyết định. Standalone v2 và frozen artifacts tiếp tục dùng schema/công thức lịch sử.
- Dùng patch `revise_vehicle`, `site_limit`, `outage` dưới scope typed của Copilot. Trong MVP, site limit chỉ cho nguồn shared. Target thấp hơn hoặc bằng SOC thật được ghi already attained, giữ SOC, energy counters và lifecycle rút xe.
- Concurrency ở G1 chỉ xử lý lỗi safety ordering và trace attribution có bằng chứng. Snapshot capture/rollout, outcome ledger và auth projection thuộc phase sau. R10 xác định contract năng lượng và chi phí. R11 định nghĩa phần evaluator cần bổ sung. [Foundation contract](FOUNDATION_CONTRACT.md) · [Issue ledger](ISSUES.md)
