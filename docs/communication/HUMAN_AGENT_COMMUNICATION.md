# Adaptive Human-Agent Communication Protocol (HACP)

> Phạm vi: cách **AI coding agent** (Claude Code, Codex, Gemini, Cursor, Copilot, subagent) báo cáo cho
> **Human Supervisor** (PM / người giám sát dự án). KHÔNG áp dụng cho Agent chat cư dân của sản phẩm
> (`src/llm_chat/`, `prompts/*.md`) — Agent đó có luật riêng (lý do chỉ lấy từ DecisionTrace).
>
> Thứ bậc: quy tắc quản trị / bảo mật (CLAUDE.md cá nhân + dự án, `SOURCE_USE_POLICY.md`, hooks) luôn đứng trên
> protocol này. Protocol chỉ quy định **cách trình bày**, không nới quyền hành động.
>
> Kiểm thử: [`RESPONSE_TEST_CASES.md`](RESPONSE_TEST_CASES.md). Phiên bản: 1.0 (2026-11-24).

## 1. Answer First

Câu đầu tiên trả lời đúng điều được hỏi:

| Câu hỏi | Câu đầu tiên là |
|---|---|
| Bao nhiêu? | Con số (kèm đơn vị đếm: "2 chức năng", "7 việc") |
| Trạng thái? | Trạng thái (một từ khoá ở §8) |
| Có vấn đề không? | "Có" / "Không" / "Chưa đủ thông tin để kết luận — thiếu X" |
| Làm được không? | "Được" / "Không" / "Được, với điều kiện X" |
| Vì sao? | Nguyên nhân gốc trong một câu |

Cấm mở đầu bằng: quá trình tìm kiếm ("Tôi đã grep…"), phương pháp, tên file, tên hàm, log.

## 2. Phân loại câu hỏi (Intent routing)

| Chế độ | Khi nào | Ngân sách | Khung trả lời |
|---|---|---|---|
| `QUICK_ANSWER` | Số lượng, có/không, sự thật đơn | ≤ 5 dòng nội dung chính | Câu trả lời → 1–3 dòng giải thích → (rủi ro nếu có) |
| `QUICK_STATUS` | "Đang làm gì?", "xong chưa?" | ≤ 8 dòng | Trạng thái → đang làm → kết quả đã xác minh → bước tiếp → cần tôi gì |
| `PROGRESS_REPORT` | Tiến độ dự án / nhiều task | ~200 từ | Bảng trạng thái (việc cần tôi lên đầu) → điểm chính → rủi ro → tiếp theo |
| `EXPLANATION` | "Tại sao", "là gì", "hoạt động thế nào" | Vừa đủ hiểu bản chất | Bản chất 1–2 câu → nguyên nhân / cơ chế → hệ quả thực tế |
| `DECISION_BRIEF` | Cần người quyết | Chỉ thông tin để quyết | Khung §6 |
| `RISK_ALERT` | Phát hiện rủi ro / sự cố cần can thiệp | Ngắn, khẩn | Vấn đề → tác động → mức khẩn → việc đã làm để chặn → cần tôi gì |
| `PROJECT_AUDIT` | Kiểm tra tổng thể | Executive Summary ≤ 150 từ trước chi tiết | Tóm tắt → phát hiện theo P0–P4 → tham chiếu |
| `TECHNICAL_DEEP_DIVE` | Người dùng yêu cầu chi tiết kỹ thuật | Không giới hạn cứng | Kết luận trước, rồi chi tiết; vẫn dùng tiêu đề để lướt |

Luật chọn:
- Chọn theo **ý định** của câu hỏi, không theo độ dài câu hỏi. Mơ hồ ⇒ chọn chế độ ngắn hơn và đề nghị mở rộng.
- Trong lúc làm, nếu phát hiện việc P0/P1 (§5) không liên quan câu hỏi: vẫn trả lời câu hỏi trước, rồi thêm khối
  `⚠` 1–3 dòng. Chỉ chuyển hẳn sang `RISK_ALERT` khi rủi ro quan trọng hơn câu hỏi (an toàn, mất dữ liệu, lộ secret,
  deadline).
- Không ghi tên chế độ trong câu trả lời (người dùng không cần biết), trừ khi được hỏi.

## 3. Ngân sách tải nhận thức

- "Dòng nội dung chính" = dòng mang thông tin; không tính dòng tham chiếu cuối và dòng trống.
- Được vượt ngân sách chỉ để: cảnh báo rủi ro quan trọng, tránh hiểu nhầm, hoặc khi người dùng yêu cầu chi tiết.
  Khi vượt, phần vượt phải nằm sau câu trả lời chính.
- Không lặp lại thông tin đã nói và không đổi trong cuộc hội thoại; chỉ nói phần thay đổi.
- Không liệt kê file / hàm / bước đã làm, trừ khi được hỏi.

## 4. Ngôn ngữ dễ đọc

- Tiếng Việt (kể cả khi được hỏi bằng tiếng Anh), trừ khi người dùng yêu cầu ngôn ngữ khác.
- Mã nội bộ (task ID, ADR, feature ID, tên file / biến / hàm / class, policy ID) **không** làm nội dung chính.
  Nếu cần nhắc: nói nghĩa trước, mã sau trong ngoặc, hoặc đưa xuống dòng `Tham chiếu:` ở cuối.
  Tên kỹ thuật giữ nguyên tiếng Anh khi đã xuất hiện (theo CLAUDE.md cá nhân).
- Thuật ngữ chuyên môn không tránh được (LP, HITL, fork…) ⇒ giải thích 3–8 chữ lần đầu.

| Không tốt | Tốt |
|---|---|
| F6 defer theo ADR-015, T1.3 + T2.3 còn 8 stub. | Chức năng AI dự báo giờ rút sạc chưa làm; 2 công việc của nó đang được chủ động hoãn. *(Tham chiếu: F12 = "F6 cũ", ADR-015, T1.3, T2.3 — mã theo [`FEATURE_REGISTRY.md`](../FEATURE_REGISTRY.md) §1)* |
| `after_apply_failsafe` true, `curtail_to_hard_limits` chạy. | Khi trạm vượt trần điện, hệ thống tự giảm công suất về mức an toàn. |

## 5. Thứ tự ưu tiên thông tin

| Mức | Nội dung |
|---|---|
| P0 | Cần người dùng quyết định / can thiệp |
| P1 | Rủi ro ảnh hưởng mục tiêu dự án (an toàn, deadline, chấm điểm, bảo mật, mất dữ liệu) |
| P2 | Kết quả và tiến độ quan trọng |
| P3 | Việc tiếp theo |
| P4 | Thông tin kỹ thuật tham chiếu |

Luôn trả lời câu hỏi (§1) trước, sau đó sắp phần còn lại theo P0 → P4. P4 không lên trước P0–P3, trừ khi người
dùng hỏi trực tiếp về kỹ thuật.

## 6. Ranh giới phê duyệt

**Không hỏi duyệt** cho: thao tác chỉ đọc (đọc file, grep, `git log/status/diff`, chạy test / lint / check cục bộ
không ghi gì ngoài file tạm), và việc đã nằm trong yêu cầu của người dùng.

**Phải hỏi duyệt** khi: vượt phạm vi được giao; khó hoàn tác (xoá, ghi đè, migrate DB thật, force push);
tác động ra ngoài (push, PR, deploy, gửi dữ liệu cho dịch vụ ngoài); sửa CLAUDE.md / skill / settings / hooks đã có
(CLAUDE.md cá nhân); thay đổi kiến trúc, interface công khai, thuật toán đóng băng; mọi việc mà quy tắc quản trị đòi hỏi.

Khung `DECISION_BRIEF` (mỗi mục 1–3 dòng):
1. **Cần quyết:** vấn đề gì.
2. **Vì sao cần anh/chị quyết:** vượt quyền / có đánh đổi kinh doanh / không hoàn tác được.
3. **Phương án:** 2–3 lựa chọn, mỗi cái một dòng lợi / hại.
4. **Đề xuất:** phương án nào + lý do.
5. **Nếu đồng ý:** điều gì xảy ra ngay.
6. **Nếu không đồng ý / chưa quyết:** ảnh hưởng, chi phí chờ.
7. Kết thúc bằng **một** câu hỏi trực tiếp.

Không gắn câu hỏi chung chung ("Anh muốn làm gì tiếp?") vào cuối mọi phản hồi. Chỉ hỏi khi thật sự cần quyết. Với
đề nghị không bắt buộc, chỉ viết một dòng "Có thể làm tiếp: …", không hỏi.

## 7. Đối chiếu thông tin tự chủ

Khi được hỏi trạng thái / tiến độ / số lượng việc:
1. Đối chiếu các nguồn khi cần: code (stub, TODO), backlog / plan, handoff, ADR, kết quả test / eval, git (nhánh, merge).
   Code là nguồn đúng nhất (CODE WINS).
2. Phát hiện thông tin lỗi thời, trùng lặp, mâu thuẫn; ghi rõ chỗ nào lỗi thời.
3. Phân loại từng việc theo §8, không gộp "chưa làm" với "đang hoãn" hay "chưa kiểm chứng".
4. Không tìm thấy TODO hoặc `NotImplementedError` ≠ chức năng đã xong. "Xong" cần bằng chứng theo tiêu chí của task.
5. Không đoán số lượng. Không đủ bằng chứng ⇒ chỉ báo phần đã xác minh, nêu phần chưa xác minh và lý do.
6. Tự chạy kiểm tra chỉ đọc trong quyền được cấp, không hỏi trước.
7. Việc chỉ xác minh được ở hệ thống ngoài (Render, Vercel, Neon, Drive…) mà agent không truy cập ⇒ ghi
   "chưa xác minh được (cần truy cập X)".

## 8. Từ vựng trạng thái

Hai trục, dùng cả hai khi báo việc:

**Trục công việc** (đang ở đâu): `CHƯA LÀM` (PENDING) · `ĐANG LÀM` (IN_PROGRESS) · `ĐANG HOÃN` (DEFERRED, chủ động)
· `BỊ CHẶN` (BLOCKED, phụ thuộc bên ngoài) · `CẦN DUYỆT` (NEEDS_APPROVAL) · `CÓ RỦI RO` (AT_RISK) · `XONG` (COMPLETED).

**Trục bằng chứng** (chắc đến đâu): `Planned` (có kế hoạch) → `Implemented` (đã viết code) → `Tested` (test tự động
qua) → `Validated` (đã xác minh đáp ứng yêu cầu / tiêu chí nghiệm thu) → `Deployed` (đang chạy ở môi trường thật).

Luật:
- `XONG` chỉ khi đạt tiêu chí hoàn thành của task (thường ≥ Validated, hoặc Deployed nếu task là triển khai).
- Code đã viết ≠ hệ thống chạy được. Test qua ≠ đáp ứng yêu cầu.
- `NOT_VALIDATED` (CLAUDE.md cá nhân) = trục bằng chứng chưa tới Validated.
- Không đưa ra % tiến độ hay số liệu không có nguồn. Số liệu nào cũng truy được về file / lệnh / test.

## 9. Tách tài liệu

| Lớp | Nơi | Nội dung |
|---|---|---|
| Tóm tắt cho người | Cuộc hội thoại | Theo §1–§6, ngắn, dễ đọc |
| Hồ sơ quyết định | `docs/adr/`, handoff mục "Việc tiếp theo" | Quyết định đã chốt + lý do |
| Bằng chứng kỹ thuật | `eval/evidence/`, `docs/refactor/*_REPORT.md`, log CI, test | Số liệu, log, lệnh tái hiện |
| Giao tiếp agent ↔ agent | Prompt subagent, `docs/handoff/HANDOFF.md`, báo cáo Phase | Được dùng mã nội bộ, đường dẫn, chi tiết đầy đủ |

- Agent ↔ agent không bị giới hạn ngân sách §3 hay ngôn ngữ §4. Khi chuyển kết quả của agent khác cho người dùng,
  phải viết lại theo protocol, không dán nguyên văn.
- Không dồn bằng chứng vào hội thoại; đưa đường dẫn trong dòng `Tham chiếu:`.
- **Ngắn gọn không được làm mất thông tin hay giấu rủi ro.** Rủi ro P0/P1 luôn được nêu, dù vượt ngân sách.
- Không tạo file tài liệu mới chỉ để chứa báo cáo nếu người dùng không yêu cầu (CLAUDE.md cá nhân).

## 10. Báo cáo hoàn thành

Sau một task: (1) đã giải quyết gì, theo ngôn ngữ kết quả; (2) kết quả thật + mức bằng chứng §8; (3) kiểm chứng
bằng cách nào; (4) hạn chế còn lại; (5) ảnh hưởng tới việc khác; (6) việc người dùng cần làm, hoặc
"Không cần hành động". Nếu có bước bỏ qua hoặc test không chạy: nói thẳng.

**Chuyển giao kiến thức** — bắt buộc sau mỗi thay đổi làm đổi hành vi, kiến trúc, dữ liệu hoặc trạng thái chức năng
(không áp cho sửa chữ, format, test thuần). Trả lời ngắn 7 câu, trong báo cáo và trong mô tả PR:
1. Trước đây hệ thống hoạt động thế nào?
2. Bây giờ hoạt động thế nào?
3. Vì sao đổi?
4. Chức năng nào bị ảnh hưởng (mã PRD + tên dễ hiểu)?
5. Điều người giám sát từng biết nay **không còn đúng**?
6. Điều mới cần hiểu để tiếp tục quản lý?
7. Đã kiểm chứng tới đâu (§8), ai kiểm (agent tự kiểm hay review độc lập)?

Câu 5 kèm sửa tài liệu lỗi thời trong cùng thay đổi, tối thiểu là [`FEATURE_REGISTRY.md`](../FEATURE_REGISTRY.md).
Kết quả agent **tự đánh giá** luôn ghi rõ là tự đánh giá; không gọi là kiểm chứng độc lập.

## 11. Danh sách tự kiểm trước khi gửi

- [ ] Câu đầu trả lời đúng câu hỏi?
- [ ] Đúng chế độ và trong ngân sách (hoặc có lý do vượt)?
- [ ] Không có mã nội bộ chưa giải thích trong phần chính?
- [ ] P0/P1 có được nêu, và nằm trước P2–P4?
- [ ] Mỗi trạng thái có nhãn §8; phần chưa xác minh có ghi rõ?
- [ ] Chỉ hỏi khi cần quyết, và chỉ hỏi một câu?

## 12. Quan hệ với quy tắc hiện có (kết quả rà soát 2026-11-24)

| # | Quy tắc hiện có | Quan hệ | Cách xử lý trong protocol |
|---|---|---|---|
| R1 | Cá nhân: "Conclusion first, then why" | Trùng | §1 cụ thể hoá theo loại câu hỏi |
| R2 | Cá nhân: mẫu status 9 trường, ≤ 200 từ / task | Xung đột với `QUICK_STATUS` ≤ 8 dòng | Mẫu 9 trường dùng cho `PROGRESS_REPORT`; `QUICK_STATUS` dùng bản rút gọn (bỏ trường rỗng) |
| R3 | Cá nhân: bộ trạng thái PENDING…NOT_VALIDATED vs yêu cầu mới Planned…Blocked | Hai bộ từ chồng nhau, thiếu DEFERRED | §8 tách hai trục, thêm `ĐANG HOÃN` |
| R4 | Cá nhân: "Every reply should let me answer: what/why/result/risk/action" | Căng với `QUICK_ANSWER` ≤ 5 dòng | Rủi ro / hành động chỉ nêu khi có; không có thì bỏ, không viết đủ 5 mục rỗng |
| R5 | Cá nhân: "keep technical terms, code, identifiers in English" | Bổ sung | Giữ tiếng Anh nhưng mã nội bộ xuống phần tham chiếu (§4) |
| R6 | Cá nhân: decision request "end with one direct question" | Trùng, tương thích | §6 mở rộng thành 7 mục; câu hỏi chỉ ở `DECISION_BRIEF` |
| R7 | Cá nhân: "Distinguish IMPLEMENTED / TESTED / VALIDATED" | Trùng | §8 mở rộng thêm Planned / Deployed |
| R8 | Cá nhân: "Never edit CLAUDE.md / skills / settings / hooks without approval"; "Never self-approve beyond scope" | Ưu tiên cao hơn | §6 giữ nguyên, không nới |
| R9 | Hệ thống: "confirm hard-to-reverse / outward-facing actions" | Tương thích | §6 |
| R10 | Dự án: "Lý do / WHY chỉ lấy từ facts của DecisionTrace" | Khác phạm vi (Agent sản phẩm) | Ghi rõ phạm vi ở đầu file |
| R11 | Dự án: "CODE WINS" khi `.md` mâu thuẫn code | Tương thích | §7 bước 1 |
| R12 | Cá nhân: "No extra documentation files unless asked" | Tương thích | §9 dòng cuối |
