# ADR AI-4 — Phạm vi Decision Copilot và HOW-TO hữu hạn

**Trạng thái** Proposed, chờ Tech Lead duyệt G0.  
**Ngày** 2026-11-24.  
**Quan hệ** Đề xuất thay một phần phạm vi trong ADR-015 §1, dựa trên ADR-013, ADR-014 và ADR-019. Giữ số thứ tự ADR chính thức cho lúc duyệt và đưa vào `docs/adr/`.

## Phạm vi đề xuất

AI-4 gồm WHY dựa trên trace, WHAT-IF ghép cặp và HOW-TO trên một tập ứng viên hữu hạn. Cả Resident và Operator có đường hỏi bằng ngôn ngữ tự nhiên, giao diện tối thiểu và đường nhập có cấu trúc khi provider không khả dụng. AI-1 negotiation, đề nghị và apply chuyển backlog riêng. Các mục hoãn còn lại của ADR-015 giữ chính sách hiện hành. Zone-budget patch và so sánh policy là SHOULD, cần duyệt phạm vi riêng.

- WHY trả facts theo subject và interval cùng reason codes có chứng cứ. Thiếu dữ kiện trả trạng thái rõ.
- WHAT-IF gồm target SOC, deadline, site grid input limit và connector outage có thời lượng. Từng cặp dùng chung snapshot, known events, policy và horizon. Site limit chỉ hỗ trợ shared supply ở MVP. Tăng vượt nguồn lắp đặt mang nhãn giả định hạ tầng.
- HOW-TO thử một biến cho mỗi mục tiêu. Resident có `max_soc_by_deadline` và `earliest_completion_for_target`. Operator có `min_tested_site_limit_for_sla`. Giới hạn đề xuất là 8 ứng viên và 1 baseline, horizon tối đa mặc định 24 giờ. Báo tập đã thử, trạng thái từng run, trade-off và SLA gốc/revised. Kết luận chỉ áp dụng cho các ứng viên đã đánh giá.
- Workflow gọi kernel, optimizer và Guard hiện có. LLM parse intent và diễn đạt facts qua grounding. JWT và server xác định role và ownership. Mọi đề xuất/rollout là advisory, `applied: false`.

## API thiết kế và ownership

| Thiết kế API dưới `/api/v1/copilot` | Quyền và kết quả |
|---|---|
| `POST /query`, `POST /why` | Resident truy xuất booking của mình và dữ kiện tổng hợp được phép. Operator truy xuất trong scope trạm. WHY trả facts có refs, missing evidence và planned/measured stage. |
| `POST /what-if`, `POST /how-to` | Tạo job có giới hạn, trả 202 và job ID. Resident chỉ `revise_vehicle` cho booking của mình. Operator có `site_limit` và `outage`. |
| `GET /jobs/{job_id}` | Kiểm ownership từ server, trả trạng thái và kết quả đã lọc. Job trong một worker có TTL. |

`src/models/` sở hữu contract, `src/services/copilot/` sở hữu workflow deterministic, `src/agents/` sở hữu intent/grounded rendering. `src/services/repository.py` và Alembic sở hữu persistence. `src/api/` và frontend dùng convention router/DTO hiện hành. MVP-3.5 sở hữu thuật toán AC/DC và Coordinator. Nhánh đề xuất `feature/ai-4` từ baseline đã đối chiếu, từng pha review riêng.

## Quyết định cần duyệt

- Postgres JSON payload + indexed lookup theo ID, booking và thời gian làm nguồn detailed trace cho WHY. JSONL dùng export debug. Chốt retention, truy xuất summary-only và schema backend có version mà vẫn giữ v2 golden.
- Chốt thứ tự khóa và tiêu chí snapshot sẵn sàng khi outbox còn sự kiện an toàn. Xác định `known_at(T)`, metric/cohort và giới hạn job trên solver single-thread.
- Duyệt canonical patch names, horizon/candidate cap, ngưỡng eval trong Master Plan, semantics target thấp hơn SOC thật, và quyền hypothetical `revise_vehicle` của Operator. Quyền này đang chờ phê duyệt.
