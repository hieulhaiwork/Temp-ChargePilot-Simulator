# AI-4.4B — Tích hợp công cụ vào Chat Agent

**G6B — IN_PROGRESS.** Báo cáo triển khai của Codex. Tech Lead tiếp nhận review sau khi hoàn tất các cổng.

## Baseline và phạm vi

Local `feature/ai-4-how-to` tại `64c85f1624ee2893eff776a1e82fbdd893d3fe4d`. Local và remote develop đã được đối chiếu tại `0f877f196db7b89759af08aab825f0fff82f7c3c`. G5 được Tech Lead duyệt tại mirror `42438430ee49f404e90080c49a76e4c6446530da`. Sáu blob code và tests khớp patch, sáu SHA-256 khớp danh sách file đã chạy và 26 checksum khớp trong bundle G5. [Nghiệm thu G5](PHASE_4_3_REPORT.md) · [Audit và checkpoint](G6B_RECOVERY_STATE.md)

## Thiết kế và thực thi

- Chat Agent hiện có chọn typed WHY, WHAT-IF, HOW-TO và job lookup. Adapter gọi service đã phân quyền. G6A standalone dùng cùng services và tiếp tục có biểu mẫu dự phòng. Giải thích lịch qua tên legacy được chuyển sang DecisionTrace trong chat thật.
- Backend cung cấp vai trò và danh tính. Job thuộc actor và phiên chat đã xác thực. Mỗi actor chỉ có một mô phỏng chat active và nộp cách nhau tối thiểu 15 giây. Một lượt chat có tối đa 4 lần gọi công cụ phân tích và 1 lần thử nộp mô phỏng. Tác vụ trả handle để giao diện poll hoặc hủy. Giữ một worker cho queue và một solver chung.
- Advice đi qua typed claims và dựng câu tất định từ dữ kiện được quyền xem. WHY giữ causal reason code. WHAT-IF giữ hướng chênh lệch, cửa sổ và lý do thiếu phép so sánh. HOW-TO phân biệt cam kết, target, SOC tại hạn, attainment, release, feasibility và tình trạng search. Gate so toàn bộ claim với bằng chứng gắn ref và JSON Pointer.
- Cả hai vai trò dùng ChatPanel. Cư dân có luồng xác nhận hiện hành và có thể mở màn Lịch sạc để yêu cầu sửa sau khi xem tư vấn. Giữ advisory-only với `applied=false`. UI hiển thị cam kết, trạng thái job, các lựa chọn xếp hạng và lý do kết quả còn một phần.
- G6A-F01 dùng session generation cho React Query. G6A-F02 gắn phản hồi 401 với generation đã gửi request. Hai test mới đã tái hiện lỗi trên bản trước sửa và chạy đạt trên candidate. G6A-F03 có ca ngôn ngữ linh hoạt gọi engine, ca giữ đủ target và deadline và ca provider thử bỏ điều kiện kết hợp bị chặn trước capture. Các trường mơ hồ cần hỏi lại. Phạm vi kiểm ngữ nghĩa NL gồm các fixture đã chạy.

[Hợp đồng công cụ](G6B_TOOL_CONTRACTS.md) · [Demo và fixture](G6B_DEMO.md)

## Kiểm chứng

Các lượt mock provider chạy graph, JWT, SQLite, truy vấn DecisionTrace và sandbox engines thật. Hai trường hợp WHY + HOW-TO ở cả hai vai trò có trace và output thực trong JUnit. Các phép kiểm quyền bao gồm role escalation, cùng actor tại session khác, cùng tài khoản đăng nhập mới, account khác, cross-scope từ fallback, poll và cancel. Luồng WHY + HOW-TO không ghi thay đổi live. Một test chạy live replan khi search đang active và giữ tác vụ trong trạng thái running. Per-turn admission, khả năng hủy và hồi quy timeout/TTL/shutdown được kiểm qua suite dùng chung.

| Cổng | Kết quả |
|---|---:|
| Focused G6B | 11 pass |
| G2–G5 và G6A | 167 pass |
| Legacy booking Agent và HITL | 97 pass |
| Architecture | 43 pass |
| Backend đầy đủ | 849 pass, 8 forecast skips đã có |
| Simulator độc lập | 180 pass |
| Unified Core | Golden 38/38, frozen backend 100/100, 253 AST definitions giữ tương đương |
| Ruff, tài liệu, OpenAPI | Pass trong phạm vi production, tests, scripts và chương trình eval |
| Frontend | 61 pass, lint/typecheck/generated types/build Webpack pass |
| Chromium | Đang xác minh |
| F1 offline | 55 câu hợp lệ |

Kiểm architecture chạy trên bản xuất sạch. Cây làm việc có thư mục R&D bị Git ignore chứa imports thử nghiệm từ phiên bản simulator cũ. Kiểm Ruff loại trừ đúng thư mục raw G5 đã nghiệm thu vì probe lưu trữ trong đó lỗi lint/format từ baseline. Turbopack có lỗi bind cổng ở lần thử sandbox. Production build Webpack tạo thành công 17/17 static pages. [Gate runner](../../eval/evidence/2026-11-26-ai4-g6b/verify.sh)

## Kết luận từ oracle

- M3a giữ trường hợp T+31 khả thi dù T+35 không khả thi. Hai nhánh có thể khác quyết định và không thể suy diễn kết quả thử kế tiếp từ deadline.
- Giữ trường hợp baseline đã đáp ứng và giữ phương án hiện tại. So mốc đạt cùng 75%, nên T+29 không được gọi là cải thiện khi baseline đạt tại T+18. Release có field riêng.
- Fixture SOC tại hạn đo 74,999930% trong nhánh target 75% và engine gắn infeasible. Grounding từ chối nhánh này nếu bị đưa vào ranked options.
- M3b trả 94 kW là mức thấp nhất **đã thử và xác minh khả thi**, với tìm kiếm một phần vì có nhánh thấp hơn chưa xác minh được. Tập thử và mức dung sai chạy theo G5 được duyệt.

## Trạng thái review và giới hạn

- Real provider **PENDING_NO_AUTHORIZED_KEY**. Cấu hình OpenAI có `gpt-4o-mini` cho chọn công cụ và `gpt-4o` cho phát sinh trả lời F1. Lượt xác minh này dùng provider scripted/fixture cho LLM và code tất định cho render. Token/cost provider thật chưa có.
- PostgreSQL runtime **PENDING**. Bằng chứng dùng SQLite tạm và cùng migrations.
- G7 dành cho ablation, held-out, kiểm môi trường production và release. PRD §5/§6/§8 và ADR-015 cần nhóm duyệt đồng bộ phạm vi HOW-TO hữu hạn cho hai vai trò, giữ cụm “mức thấp nhất đã thử và xác minh khả thi” và tiêu chí UI thống nhất. Bộ nguyên tắc ADR-013/014 về quyền, bằng chứng và cách ly vẫn áp dụng.

## Bàn giao

Trước đây booking chat và phân tích standalone phục vụ hai đường hội thoại. Candidate đưa công cụ phân tích vào chat để người dùng hỏi nối tiếp và phối hợp giải thích với một mô phỏng có giới hạn. Thay đổi tác động F8 và phần chat F5, với F1 được hồi quy. Mô tả cũ cho rằng HOW-TO chỉ có service nay đã được cập nhật trong registry. Khi demo, chú ý job chạy bất đồng bộ theo phiên và advice có thể chỉ trả phần đã kiểm chứng. Các cổng do Codex tự chạy. Tech Lead sẽ review độc lập.

Gói bàn giao gồm patch lấy `64c85f1` làm base, SHA-256, raw evidence và danh sách checksum. Gói ZIP chứa bản sao patch và phần cập nhật collaboration log cục bộ. [Patch](../../eval/evidence/2026-11-26-ai4-g6b/candidate.patch) · [Checksum](../../eval/evidence/2026-11-26-ai4-g6b/SHA256SUMS) · [Verification bundle](../../eval/evidence/2026-11-26-ai4-g6b/verification-bundle.zip)
