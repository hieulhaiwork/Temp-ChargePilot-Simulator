# HANDOFF — ChargePilot

> **File này là trạng thái bền của dự án.** Mọi Agent (Claude Code, Codex, mọi tài khoản) đọc §0 + §1 là tiếp tục được
> Phase hiện tại, không cần lịch sử hội thoại. §1 là checkpoint; phần sau §1 là lịch sử và bẫy đã gặp.
> Quyết định kỹ thuật ở `docs/adr/`, hiện trạng chức năng ở `docs/FEATURE_REGISTRY.md` — không lặp lại ở đây.
> Lịch sử 16–21/11 xem `git log -- docs/handoff/`.

## 0. Giao thức tiếp nhận và checkpoint (bắt buộc cho mọi Agent)

**Tiếp nhận (takeover)** — làm đúng thứ tự, chỉ đọc cho tới bước 7:
1. Đọc `CLAUDE.md` (Codex vào qua `AGENTS.md` ở gốc, file đó trỏ về đây).
2. Đọc §1 dưới đây và các file nó trỏ tới **khi task cần**; không đọc lại toàn bộ tài liệu.
3. Kiểm Git **trước mọi việc**: `git status --short`, `git diff --stat`, `git rev-parse --abbrev-ref HEAD`,
   `git rev-parse --short HEAD`.
4. Đối chiếu §1.8 với kết quả bước 3. Lệch (commit khác, file lạ, file thiếu) ⇒ **phân loại** theo mục "Sai lệch"
   dưới đây rồi xử lý theo loại; chỉ dừng thao tác bị ảnh hưởng.
5. Xác định task chưa xong gần nhất trong §1.3 và người đang giữ khoá chỉnh sửa (§1.9).
6. Kiểm phạm vi quyền (§1.2) và quyết định đã duyệt (§1.5). Việc ngoài phạm vi ⇒ hỏi, không làm.
7. Nhận khoá ở §1.9 (ghi tên Agent + thời điểm), rồi tiếp tục từ checkpoint hợp lệ gần nhất.

Không làm lại audit khi bằng chứng ở §1.4 còn hiệu lực (cùng commit code, test chưa đổi). Kết luận của Agent trước chỉ
được tin khi có bằng chứng kèm commit; thiếu thì ghi "chưa xác minh", không lặp lại như sự thật.

**Checkpoint** — cập nhật §1 (ít nhất §1.3, §1.8, §1.10, §1.11) **ngay** khi: xong một task / subtask quan trọng; có
quyết định ảnh hưởng hệ thống; phát hiện rủi ro / blocker; chạy xong test; chuẩn bị đổi Phase; người dùng yêu cầu chuyển
Agent. Viết sao cho session bị ngắt đột ngột vẫn khôi phục được: task nào dở, file nào đã sửa, bước kế tiếp là gì.
Checkpoint là sửa file, **không** tự commit / push / merge (§1.2). Mọi agent chạy trên **cùng một máy, cùng thư mục
`D:\VIN\P-019`**: handoff dựa trên file đã lưu trong workspace, **không cần commit**. Thay đổi chưa commit là trạng thái
hợp lệ, phải giữ nguyên.

**Checkpoint có thể khôi phục:** §1 là bản ghi trạng thái, **không** phải nguồn sự thật tuyệt đối. Mâu thuẫn với
repository (Git, thời điểm sửa file, nội dung file, file kết quả) ⇒ repository thắng; Agent tiếp nhận tự đối chiếu và ghi
lại chênh lệch, không lặp lại checkpoint cũ như sự thật.

**Hoàn tất bắt buộc (Mandatory Completion Checkpoint):** hai trạng thái tách riêng:
- `WORK_COMPLETED` — sản phẩm của task đã lưu vào workspace.
- `HANDOFF_READY` — thêm đủ 4 việc: (1) bằng chứng ghi ở §1.4 hoặc file kết quả có đường dẫn; (2) §1.3 cập nhật trạng
  thái; (3) §1.10 ghi việc tiếp theo và ai làm; (4) §1.9 nhả hoặc chuyển khoá; kèm một dòng §1.11.

Không báo Human "xong" khi mới `WORK_COMPLETED`; phải nói rõ "đã xong việc, chưa xong bàn giao". **Mọi** Agent tạo file
trong `docs/handoff/` (kể cả reviewer, auditor) phải ghi file đó vào §1.8 và một dòng §1.11. Nếu HANDOFF đang bị khoá:
ghi mục "Checkpoint cần đồng bộ" ở **đầu file kết quả của mình**; người giữ khoá (hoặc Agent nhận khoá kế tiếp) phải
chép vào §1 trước khi làm việc khác. Khoá review **chỉ** chặn sửa tài liệu đang được review, không chặn §1.3 / §1.8 /
§1.9 / §1.10 / §1.11.

**Sai lệch (Discrepancy) — phân loại và xử lý:**

| Loại | Dấu hiệu | Xử lý |
|---|---|---|
| MINOR | Thông tin cũ, thiếu tham chiếu, file kết quả mới chưa ghi vào §1.8; không ảnh hưởng an toàn | Ghi vào §1.11 (hoặc file kết quả nếu không được sửa HANDOFF); tiếp tục |
| RECOVERABLE | Checkpoint lệch nhưng khôi phục được bằng kiểm tra chỉ đọc (Git, mtime, nội dung, log) | Tự đối chiếu và ghi kết quả; tiếp tục phần chỉ đọc an toàn; **không** tự xác nhận trạng thái thay Agent khác, không sửa file Agent khác đang giữ khoá |
| BLOCKING | Không rõ phạm vi quyền, hai Agent cùng sửa, nguy cơ mất / ghi đè dữ liệu chưa commit | Chỉ dừng thao tác bị ảnh hưởng trực tiếp; báo Human |

**Báo Human (escalation)** chỉ khi Agent không giải quyết được trong quyền được cấp: cần quyết định nghiệp vụ, cấp
quyền, hoặc phân xử xung đột khoá. Việc đối chiếu, tổng hợp, tái dựng checkpoint từ bằng chứng là việc của Agent.

**Chống xung đột:**
- Mỗi task chỉ một Agent giữ khoá chỉnh sửa (§1.9). Làm song song ⇒ chia phạm vi file rõ ràng hoặc dùng worktree /
  branch riêng, ghi vào §1.9.
- Không `reset`, `clean`, `stash`, `checkout` / `restore` file, `merge`, `rebase` hay ghi đè thay đổi chưa commit của
  Agent khác. Thấy thay đổi lạ ⇒ dừng, báo.
- Independent Reviewer chỉ đọc, chạy test / check phù hợp, và ghi **một** file kết quả cho mỗi lượt review. Không sửa
  tài liệu đang review. Được ghi §1.3 (dòng task review của mình), §1.8, §1.9 (khoá của mình), §1.10, §1.11.

**Danh tính và trách nhiệm:** mỗi checkpoint ghi Agent thực hiện, thời điểm, commit code đã kiểm. Agent tiếp tục
implementation **không** được là reviewer độc lập của phần đó. Vai trò chi tiết: `docs/handoff/REVIEW_PHASE1.md` §6.

**Báo cáo cho Human khi chuyển giao** (≤ 8 dòng): Phase hiện tại · số task xong / còn lại · việc gần nhất · việc Agent
tiếp theo cần làm · việc cần Human quyết.

---

## 1. Phase hiện tại — CHECKPOINT

### 1.1 Tóm tắt

**Phase:** Governance Giai đoạn 1 — khôi phục khả năng hiểu và kiểm soát hệ thống của Human Supervisor.
**Mục tiêu:** một nguồn hiện trạng chức năng có bằng chứng, truy vết yêu cầu → code → test, tài liệu hiểu hệ thống 4
tầng, triage ADR, cổng kiểm soát tối thiểu, review độc lập, cơ chế chuyển giao giữa Agent.
**Tiến độ (2026-11-25, sau P1-13):** Technical Acceptance **PASS** (Codex, `REREVIEW_PHASE1_RESULT.md` §T0–T5) — Human
đã chấp nhận. Human đã quyết Q1–Q4, D-3…D-6, C-3, G-auto và backlog R-1…R-6 (sổ quyết định §1.5). **Formal Closure
Readiness: READY_FOR_HUMAN_CONFIRMATION** — không còn blocker kỹ thuật hay quyết định bắt buộc nào treo; chỉ còn chỉ thị
đóng P1-14 của Human (chưa cho phép ở lượt này). C-1 commit: chưa cho phép. Phase 1 **chưa đóng**.

**Checkpoint mới 2026-11-26.** Project Owner giao merged baseline readiness và AI-4.3 HOW-TO Engine trên local
`develop` đã gộp. Handoff cho lượt này ở [AI-4](../ai4/PROJECT_STATE.md). Các bảng governance Phase 1 bên dưới
vẫn ghi nhận trạng thái của lượt 25/11.

### 1.2 Kế hoạch và phạm vi đã được duyệt

Project Owner giao G6B ngày 26/11/2026, tích hợp typed WHY/WHAT-IF/HOW-TO vào Agent hiện có cho hai vai trò, giữ booking và HITL cùng hai đường fallback G6A. Phạm vi và checkpoint A–F ở [Recovery G6B](../ai4/G6B_RECOVERY_STATE.md).

Nguồn: tin nhắn của Human Supervisor trong phiên Claude Code ngày 2026-11-24 (duyệt Giai đoạn 1 có điều kiện; sau đó
duyệt cơ chế chuyển giao). Tóm tắt yêu cầu đã duyệt:
1. Một Feature Registry duy nhất; hệ mã ưu tiên PRD v0.4 nhưng **không mặc định PRD đúng hơn code**; có bảng ánh xạ
   mã cũ → mới, chỉ ra mã trùng khác nghĩa, yêu cầu triển khai khác tài liệu, chức năng bị đổi / bỏ / hoãn. Mâu thuẫn ảnh
   hưởng nghiệp vụ ⇒ đưa vào danh sách cần Human quyết. **Chỉ chuẩn hoá mã trong tài liệu**, không đổi tên trong code /
   API / DB / test.
2. Truy vết yêu cầu nghiệp vụ → chức năng → code → test → bằng chứng; không dùng test không tồn tại; tách test đạt / chưa
   chạy / bỏ qua / mock / thật / chưa có test / chưa có code; số từ báo cáo cũ ghi là LỊCH SỬ; bằng chứng gắn commit.
3. Kiến thức hệ thống đọc được theo 4 tầng (nghiệp vụ, kiến trúc, nguyên lý, kiểm chứng), mỗi chức năng quan trọng trả
   lời 11 câu (làm gì, vì sao, ở đâu, nhận / trả gì, nguyên lý, thuật toán, vì sao chọn, sai thì sao, bỏ thì sao, làm sao
   biết đúng). Ưu tiên sơ đồ và ví dụ nghiệp vụ.
4. Bản đồ kiến trúc hiện trạng theo code thật; tách rõ đã làm / kế hoạch; sơ đồ 3 luồng chính.
5. Triage ADR thành A (nghiệp vụ, Human duyệt) / B (uỷ quyền Tech Lead) / C (cần review độc lập) / D (lỗi thời) / E (đã
   chạy nhưng chưa duyệt). **Không tự duyệt ADR**; implementation không phải bằng chứng đã duyệt.
6. Cổng kiểm soát tối thiểu (test dẫn phải tồn tại, đường dẫn phải tồn tại, mã không mâu thuẫn, trạng thái có bằng
   chứng, không `Validated` chỉ vì có code, thay đổi quan trọng cần review độc lập). Tự động hoá cần sửa script / CI ⇒
   báo phạm vi, **xin duyệt riêng**.
7. Gói bàn giao cho Codex / agent độc lập; reviewer đối chiếu trực tiếp code, không mặc định audit đúng.
8. Chuyển giao kiến thức sau mỗi thay đổi quan trọng (7 câu hỏi).
9. Giao tiếp theo HACP (`docs/communication/HUMAN_AGENT_COMMUNICATION.md`).
10. Cơ chế chuyển giao giữa Agent (§0) + cập nhật hướng dẫn tiếp nhận trong `CLAUDE.md`.

**Được phép:** sửa / tạo tài liệu trong phạm vi trên; chạy lệnh chỉ đọc, test, check cục bộ; đọc `gh` (chỉ đọc).
**Không được phép:** đổi business logic; refactor code; đổi database schema; đổi API contract; đổi CI hoặc deploy
production; tự duyệt ADR; xây thêm framework / nền tảng quản trị; commit / push / merge (chưa được duyệt cho Phase này);
tạo tài liệu song song thay vì sửa tài liệu cũ.

**Phạm vi lượt 26/11.** Chỉ baseline merged và G5, gồm service deterministic, oracle, verification và tài liệu roadmap.
Đề xuất đồng bộ PRD/ADR-015 chờ nhóm duyệt. Dừng trước G6B. [Master Plan](../ai4/AI-4_MASTER_IMPLEMENTATION_PLAN.md)

### 1.3 Task Phase 1

**G6B — IN_PROGRESS.** Codex ghi G5 APPROVED và đối chiếu baseline trước checkpoint A.

**G5 (26/11) — READY_FOR_FINAL_ACCEPTANCE · HANDOFF_READY.** Targeted remediation F01–F04 đã qua 10 cổng. Tech Lead nhận nghiệm thu cuối.
[Báo cáo](../ai4/PHASE_4_3_REPORT.md) · [Recovery](../ai4/G5_RECOVERY_STATE.md)


| ID | Task | Tiêu chí hoàn thành | Trạng thái | Bằng chứng / nơi |
|---|---|---|---|---|
| P1-01 | Ánh xạ hệ mã, mã trùng khác nghĩa | Bảng cũ → mới; mỗi mã trùng có nơi còn dùng | XONG (chưa review) | `docs/FEATURE_REGISTRY.md` §1 |
| P1-02 | Feature Registry duy nhất | Mọi F1–F15 + lớp LLM có trạng thái 2 trục + rủi ro | XONG (chưa review) | registry §2 |
| P1-03 | Truy vết yêu cầu → test → bằng chứng | Mỗi FR có code / test / nhãn bằng chứng; không test ma | XONG (chưa review) | registry §3; tự kiểm G1/G2 24/11 |
| P1-04 | Triển khai khác tài liệu, cần điều tra, cần Human quyết | Danh sách có căn cứ | XONG (chưa review) | registry §4–§6 |
| P1-05 | Hiểu hệ thống 4 tầng | 4 tầng đọc độc lập; chức năng chính trả lời 11 câu | XONG (chưa review) | `docs/architecture_diagram.md` |
| P1-06 | Bản đồ kiến trúc + 3 luồng | Theo code thật; tách đã làm / kế hoạch | XONG (chưa review; Mermaid chưa kiểm hiển thị) | architecture_diagram §2 |
| P1-07 | Triage ADR | 19 ADR phân nhóm A–E; brief cho từng quyết định nhóm A | XONG (chưa review) | `docs/adr/README.md` §Phân loại |
| P1-08 | Cổng kiểm soát tối thiểu | 6 tiêu chí + phạm vi tự động hoá đề xuất | XONG (thủ công) | registry §7 |
| P1-09 | Gói review độc lập | Danh sách khẳng định + cách kiểm + định dạng kết quả | XONG | `docs/handoff/REVIEW_PHASE1.md` |
| P1-10 | Chuyển giao kiến thức + sửa tài liệu lỗi thời | 7 câu hỏi trong HACP; ARCHITECTURE / PRD / HANDOFF trỏ về registry | XONG | HACP §10; `ARCHITECTURE.md`; `docs/PRD.md` đầu file |
| P1-11 | Cơ chế chuyển giao giữa Agent | §0 + §1 file này; hướng dẫn tiếp nhận trong `CLAUDE.md`; `AGENTS.md` ở gốc cho Codex | XONG | file này; `CLAUDE.md` "Tiếp nhận công việc"; `AGENTS.md` |
| P1-12 | **Review độc lập** Phase 1 | Reviewer khác Implementation Agent kiểm K1–K15, ghi kết quả | **XONG** (Codex, 24/11 18:18–18:28): chưa đủ điều kiện đóng; phát hiện F1–F5 | `docs/handoff/REVIEW_PHASE1_RESULT.md` |
| P1-12a | Audit căn chỉnh backend ↔ simulator (ngoài kế hoạch, Human yêu cầu 24/11) | Chỉ đọc; nhãn ALIGNED / AMBIGUOUS / UNVERIFIED | XONG việc, **chưa bàn giao** tới 25/11 (không ghi HANDOFF vì khoá); là **tự audit**, chưa review độc lập | `docs/handoff/AUDIT_BACKEND_SIMULATOR_ALIGNMENT.md` (B1–B4, U1–U3) |
| P1-12b | **Remediation** F1–F5 (sửa tài liệu theo review) | Mỗi F có thay đổi + bằng chứng, hoặc ghi lý do hoãn / chuyển task | **XONG, HANDOFF_READY** (Claude Code, 25/11; Human duyệt 25/11). Chưa Re-review | `docs/handoff/REMEDIATION_PHASE1.md`; §1.12 |
| P1-12c | Re-review sau remediation | Codex kiểm F1–F5, K1–K15; targeted N2/N3/N4 sau P1-12e | **XONG, HANDOFF_READY** (Codex, 25/11): **Technical Acceptance PASS**; N2/N3/N4 RESOLVED, F1–F5 RESOLVED về governance; Mermaid 5/5 render và kiểm trực quan đạt. **Formal Closure NOT_READY**, chờ Human, chưa đóng Phase. FAIL trước P1-12e giữ trong lịch sử | `docs/handoff/REREVIEW_PHASE1_RESULT.md` §T0–T5 hiện hành; §R0–R9 lịch sử |
| P1-12e | **Targeted Remediation** N2 / N3 / N4 (chỉ tài liệu) | N2 hạ nhãn nguyên nhân; N3 sơ đồ A / B / C khớp source + kiểm render; N4 tiêu chí + phụ thuộc R-1…R-6 | **XONG, HANDOFF_READY** (Claude Code, 25/11; Human duyệt). Render Mermaid lúc đó: blocker (không có renderer), chỉ lint cú pháp — **đã gỡ**: Codex render 5/5 ở P1-12c (`REREVIEW` §T3) | `REMEDIATION_PHASE1.md` §8, §5.1 |
| P1-12d | Sửa cơ chế bàn giao (checkpoint + giao thức) | §1 khớp repository; §0 có Completion Checkpoint, phân loại sai lệch, escalation | **XONG, HANDOFF_READY** (Claude Code, 25/11) | §0, §1.12 file này; `AGENTS.md` bước 3; `CLAUDE.md` "Tiếp nhận công việc" |
| P1-13 | Human quyết Q1–Q4 + D-3…D-5 + các mục chờ ở §1.5 | Quyết định ghi vào §1.5 và ADR tương ứng | **XONG, HANDOFF_READY** (Human quyết 25/11; Claude ghi nhận 25/11). APPROVED / PROVISIONAL / DEFERRED ở §1.5 | §1.5; registry §6, §6.1; `docs/adr/README.md` §"Quyết định của Human Supervisor" |
| X-01 | **Cross-branch audit** `feature/ai-4`, `feature/be-fe-integration` (ngoài Phase 1, Human giao 25/11) | Chỉ đọc; verdict từng nhánh; finding có commit / source / evidence | **XONG, HANDOFF_READY** (Claude, 25/11; **không độc lập** với baseline — cần Codex kiểm). ai-4: READY_WITH_CONDITIONS · be-fe: NOT_READY | `docs/handoff/CROSS_BRANCH_ALIGNMENT_AUDIT.md`; ref `refs/audit/2026-11-25/*` |
| X-02 | Independent Cross-branch Review (Human giao 25/11) | Tái hiện safety, review G1/G2, X-BF-01…07 và ancestry bằng local refs; verdict riêng | **XONG, HANDOFF_READY** (Codex, 25/11): G1/G2 **CHANGES_REQUIRED**, BE–FE/cross-branch **NOT_READY**. Tái hiện baseline fork0→33kW; thêm S02 pending-fork, S03 delivery-gap, W01 Consent60/approved39; ancestry bác claim merge develop khôi phục code cũ | `docs/handoff/CROSS_BRANCH_INDEPENDENT_REVIEW.md` |
| D-01 | Documentation Rationalization Audit (Human giao 25/11, chỉ đọc) | Inventory, phân loại, mâu thuẫn, kế hoạch tinh gọn | **XONG, HANDOFF_READY** (Claude, 25/11; đồng bộ checkpoint muộn vì X-02 giữ khoá — theo mục "Checkpoint cần đồng bộ") | `docs/handoff/DOCUMENTATION_RATIONALIZATION_AUDIT.md` Phần I |
| D-02 | Ownership / purpose / member contribution audit (Human giao 25/11, chỉ đọc) | Định danh thành viên, ownership từng tài liệu, ma trận trách nhiệm, chính sách tài liệu | **XONG, HANDOFF_READY** (Claude, 25/11; không độc lập với phần LufkyMama) | cùng file, Phần II |
| D-03 | Bản phân công đề xuất 4 thành viên (Human giao 25/11) | Thẻ sứ mệnh, RACI, owner module / tài liệu, việc trước mắt, phụ thuộc, HD-8…HD-14 | **XONG, HANDOFF_READY** (Claude, 25/11). Mọi phân công **PROPOSED** tới khi Human + thành viên xác nhận | `DOCUMENTATION_RATIONALIZATION_AUDIT.md` Phần III |
| P1-14 | Đóng Phase 1 | Sửa tài liệu theo kết quả review; registry cập nhật mốc; Human xác nhận đóng | **CHỜ CHỈ THỊ HUMAN** — readiness: READY_FOR_HUMAN_CONFIRMATION (§1.13); Human 25/11: chưa cho phép đóng ở lượt này | §1.13 |

Ngoài task: HACP (protocol giao tiếp) đã áp dụng trước Phase 1 —
`docs/communication/HUMAN_AGENT_COMMUNICATION.md`, `docs/communication/RESPONSE_TEST_CASES.md`.

### 1.4 Kiểm thử và bằng chứng

**Merged develop `0f877f1`, Codex, 26/11.** Focused 399 pass, backend 808 pass + 8 forecast skips, standalone 180,
frontend 59, Golden 38/38 và frozen backend 100/100. **Patch G5** qua 24 focused, 180 regression G2/G3/G4/G6A,
832 backend + 8 forecast skips, standalone 180 và mọi cổng trong runner. **Sau remediation** đạt 30 G5, 137 hồi quy G2/G3/G4/G6A, 43 architecture, 838 backend + 8 forecast skips và standalone 180. [Evidence G5](../../eval/evidence/2026-11-26-ai4-g5/raw)

| Kiểm | Kết quả | Khi / ai | Commit code | Hiệu lực |
|---|---|---|---|---|
| `pytest tests -q` | 604 đạt, 8 bỏ qua (dự báo hoãn), 0 lỗi | 2026-11-24, Claude (Implementation) | `ce23136` | còn hiệu lực nếu `src/`, `tests/` chưa đổi |
| `pytest src/simulator/tests -q` | 180 đạt | như trên | `ce23136` | như trên |
| `npx vitest run` (frontend) | 30 đạt | như trên | `ce23136` | như trên |
| `scripts/check_docs.py` | PASS (chỉ quét `docs/guide/`) | như trên, sau khi sửa tài liệu | — | phải chạy lại sau mỗi lần sửa tài liệu |
| Tự kiểm G1 / G2 trên tài liệu Phase 1 | mọi test / đường dẫn được dẫn tồn tại, trừ các mục cố ý ghi "không tồn tại" | như trên (script tạm, không lưu vào repo) | — | phải chạy lại sau khi sửa |
| CI (`gh run list`) | `develop` @ `68692ee` thất bại (job frontend, 22/11); `feature/unified-core` chưa chạy CI | đọc 24/11 | — | thay đổi khi CI chạy lại |
| Benchmark baseline | 100 run, 0 vi phạm áp dụng **cho tải đã chạy**; đúng hạn TB 29–32% / policy — **chỉ là regression**: 40/160 sự cố bị bỏ, 60/100 run kịch bản legacy, tải vượt năng lực ⇒ không đo được MT1 / MT4 sự cố / chọn policy | LỊCH SỬ, tạo 24/11 | `a9def2f` | baseline đóng băng |
| Tái tính baseline + workload (Remediation) | Khớp Codex F1–F3; thêm: `connector_failure` trùng KPI `peak_evening` 20/20; `hybrid_evening` seed 1 AC 676 kWh > 528 kWh; VND / kWh M3b 2 328 < M3a 2 389 | 2026-11-25, Claude (Implementation, **không độc lập**) | `ce23136` | `REMEDIATION_PHASE1.md` §2 |
| G1 / G2 tự kiểm sau Remediation (script tạm) | Mọi tên test / đường dẫn trong registry, sơ đồ, ADR README, báo cáo Remediation tồn tại, trừ mục cố ý "không tồn tại" (4 test cũ §3.3, `scripts/check_registry.py` đề xuất, `src/simulator/base.py`) | 2026-11-25, Claude | `ce23136` | chạy lại sau mỗi lần sửa |
| `scripts/check_docs.py` sau Remediation | PASS (50 file md, 131 link) | 2026-11-25, Claude | — | như trên |
| P1-12e: G1 / G2, check_docs, `git diff --check` | G1 17 tên / G2 109 đường dẫn: chỉ thiếu mục cố ý "không tồn tại"; check_docs PASS; không lỗi khoảng trắng | 2026-11-25, Claude (không độc lập) | `ce23136` | `REMEDIATION_PHASE1.md` §8 |
| P1-12e: Mermaid | **Render CHƯA KIỂM CHỨNG** — không có renderer (`mmdc`, gói `mermaid` FE / global / npx cache, Python). Lint cú pháp thủ công 3 `sequenceDiagram`: đạt; 2 `flowchart` không lint | 2026-11-25, Claude | — | **Đã thay** bởi render 5/5 của Codex (`REREVIEW` §T3) |
| P1-12e: snapshot SHA-256 sau sửa | `docs/FEATURE_REGISTRY.md` `a4f57f5fb7eecc49d60e2a3f090fa8020ceb205da6890ab0efe0094f344c3bc4` · `docs/architecture_diagram.md` `2a88672d1cbe765b3945a45ed861e2c2e0d3884b3465cfd9ad33ef2f746639db` · `docs/adr/README.md` `585596a7d5d2657c4688a26db9ad69d144e10a6d8519a93ab0891ea27d390df4` (không đổi so với snapshot Codex) · `docs/handoff/REMEDIATION_PHASE1.md` `9278931edd90c6e30222ddb33eb4fb30ca8da64ed37bcd3a6243e36055362f0b`. HANDOFF không tự chứa hash | 2026-11-25, Claude | `ce23136` | so lại bằng `sha256sum` trước Re-review |

Các dòng trên do Implementation Agent tự chạy; kiểm độc lập ở `REVIEW_PHASE1_RESULT.md`, `REREVIEW_PHASE1_RESULT.md` (§T1–T3: snapshot khớp, 5/5 Mermaid render, 3 targeted tests).

### 1.5 Quyết định

**Đã được Human Supervisor duyệt (2026-11-24, trong hội thoại Claude Code):**
- Áp dụng HACP cho dự án và rút gọn quy tắc giao tiếp trong `~/.claude/CLAUDE.md` cá nhân.
- Giai đoạn 1 governance với các điều kiện ở §1.2.
- Cơ chế chuyển giao giữa Agent + cập nhật `CLAUDE.md` phần tiếp nhận công việc.
- Tạo `AGENTS.md` ở gốc (chỉ trỏ về `CLAUDE.md`, file này, quy tắc governance; không chép nội dung).
- **Chưa commit** tài liệu Phase 1 cho tới khi có kết quả review độc lập; handoff dựa trên workspace chung, commit
  không phải điều kiện handoff. Giữ nguyên mọi thay đổi chưa commit.
- Bàn giao review độc lập cho Codex; Implementation Agent dừng.
- **2026-11-25:** Human xác nhận chưa từng giao Remediation, không có workspace / báo cáo Remediation khác; **duyệt chính
  thức Remediation** (chỉ sửa tài liệu; không đổi code / optimizer / simulator / policy / test / API / DB / CI; không
  duyệt ADR, commit, push, merge, deploy; phải đạt HANDOFF_READY cho Codex Re-review).
- (Trước đó, ghi trong ADR-019) hướng Unified Core và Phase 0–1 của refactor (2026-11-23).

**Sổ quyết định Human 2026-11-25** (chỉ thị trong phiên Claude Code; ghi nhận bởi Claude, P1-13). Human chấp nhận
Technical Acceptance PASS (`REREVIEW_PHASE1_RESULT.md` §T0–T5). **Không ADR nào chuyển `Accepted`**; header 19 ADR giữ
`Proposed`. Nhãn: APPROVED · PROVISIONAL (tạm giữ, có điều kiện xét lại) · DEFERRED (hoãn, có điều kiện mở lại).
Danh sách "đang chờ" cũ (24/11) đã được thay bằng bảng này.

| # | Quyết định | Nhãn | Điều kiện xét lại / mở lại | Ghi ở |
|---|---|---|---|---|
| Q1 (ADR-015) | Ưu tiên AI-4 WHY | APPROVED | — | ADR README, registry §2 F8, §6 |
| Q1 (ADR-015) | AI-1 Negotiation đầy đủ hoãn, không loại khỏi roadmap | DEFERRED | Khi phạm vi và năng lực triển khai được đánh giá | registry §2 F7, §6 |
| Q2 (ADR-010) | Bãi hiện tại = giả định mô phỏng có nhãn, không phải dữ liệu VinFast / Vinhomes | APPROVED | Có thông số thật / đổi topology | ADR README, registry §6 |
| Q3 (ADR-018) | M3a mặc định tạm; B0 / M2b / M3a / M3b version `"1"` giữ nguyên | PROVISIONAL | Sau R-2, R-3 | như trên |
| Q4 (ADR-013 / 014) | Nguyên tắc AI: facts / trace, quyền phía server, không tự đổi cam kết, không apply sandbox khi chưa được phép | APPROVED (nguyên tắc) | Chi tiết kỹ thuật review riêng | như trên |
| D-3 | Offline demo có nhãn ở dev / test; giữ cấm `mock` production | APPROVED | Offline tại production cần duyệt riêng | registry §6 |
| D-4 | Hướng chuẩn hoá workload feasibility, request fulfillment, accepted booking on-time rate, admission rate; báo mẫu số, điều kiện khả thi, mẫu số = 0 | APPROVED (hướng) · PROVISIONAL (định nghĩa chính xác) | Review trong R-2 | registry §6 |
| D-5 | Đổi mã định danh source / test | DEFERRED | Human lên lịch task riêng; tới đó dùng registry §1.1 | registry §1.1, §6 |
| D-6 | Consent tạm ở backend; không đổi frozen policies | PROVISIONAL | Sau R-4 | ADR README, registry §4, §6 |
| C-3 | Sửa nhãn forecast trong tài liệu | APPROVED — đã làm (`CLAUDE.md` ×2, `ARCHITECTURE.md` ×1 → "F12 (= F6 cũ)") | — | registry §6 |
| G-auto | Agent Command Protocol, Shared Skill Pack, Skill Observability, Automated Governance vào **kế hoạch Phase 2** | APPROVED (kế hoạch) · DEFERRED (implementation) | Human duyệt implementation Phase 2 | registry §6 |
| R-1…R-6 | Giữ backlog, chưa giao thực thi. Ưu tiên P0: R-1, R-2, R-6 · P1: R-3, R-4 · P2: R-5 | DEFERRED | Từng task: registry §6.1 (vai trò theo dõi, phụ thuộc, điều kiện giao) | registry §6.1; tiêu chí `REMEDIATION_PHASE1.md` §5.1 |
| C-1 | Commit tài liệu Phase 1 | **Chưa cho phép** | Chỉ thị riêng | — |
| P1-14 | Đóng Phase 1 chính thức | **Chưa cho phép** ở lượt 25/11 | Chỉ thị riêng (§1.13) | — |

**Chờ Human (mới, từ X-01, 25/11):** H-1 cho phép đưa sửa lõi an toàn của `feature/ai-4` (G1) vào `unified-core` sau review độc lập · H-2 phạm vi AI-4 có gồm WHAT-IF / HOW-TO không (ADR-015 hoãn HOW-TO; Q1 chỉ duyệt WHY) · H-3 `feature/be-fe-integration` port lại trên `unified-core` (khuyến nghị) hay merge · H-5 cho phép cập nhật registry F5 / F8 / FR19 / FR20 theo audit. (H-4 = C-1.) Brief: `CROSS_BRANCH_ALIGNMENT_AUDIT.md` §7.

**Chờ Human (mới, từ D-01 / D-02, 25/11):** HD-1…HD-7 (tinh gọn tài liệu) và HD-8…HD-14 (phân trách nhiệm, nghĩa "Tech Lead", cấm tự merge thay đổi lõi, owner deliverable, owner lõi an toàn, duyệt PRD v0.4, việc hiện tại của HaiVuu). Brief: `DOCUMENTATION_RATIONALIZATION_AUDIT.md` Phần I §8, Phần II §II.11. Mọi ô "Đề xuất" trong ma trận II.5 **không có hiệu lực** tới khi Human duyệt.
**D-03 (25/11):** phương án cho HD-8…HD-14 + HD-8a (giảm tải LufkyMama), exception sửa lõi đóng băng cho W-S02 / W-S03, ưu tiên demo 26/11 — `DOCUMENTATION_RATIONALIZATION_AUDIT.md` §III.9. Việc trước mắt W-* (§III.5) **chưa giao**.

**Uỷ quyền Tech Lead (chưa thực hiện):** ADR nhóm B, đánh dấu Superseded ADR-011 (một phần) / ADR-016.

### 1.6 Giả định chưa xác minh

- Tài liệu Phase 1 đã qua review độc lập (P1-12, P1-12c: Technical Acceptance PASS). **Riêng sổ quyết định P1-13
  (25/11)** do Implementation Agent ghi, chưa có reviewer đối chiếu với chỉ thị Human (khuyến nghị, không chặn — §1.13).
- Audit backend ↔ simulator (P1-12a) là tự audit, chưa review độc lập; U1–U3 chưa tái hiện.
- Mermaid: Codex render 5/5 (Mermaid CLI 12.2.0, Chrome headless cục bộ); chưa kiểm trên mọi renderer / GitHub.
- Test chạy trên Windows, SQLite tạm, LLM giả lập; chưa chạy với Postgres thật, LLM thật, bản deploy.
- Kịch bản benchmark có phải "khả thi" theo MT1 không (registry I-1, task R-2). I-2 đã đóng (F14 có mô phỏng).
- Mục "Việc tiếp theo" 22/11 ở phần lịch sử bên dưới chưa đối chiếu lại.

### 1.7 Rủi ro và blocker

| Rủi ro / blocker | Ảnh hưởng | Xử lý đề xuất |
|---|---|---|
| Tài liệu Phase 1 chưa commit (C-1 chưa cho phép, 25/11) | Mất nếu có lệnh reset / clean / checkout / stash trên workspace chung | Cấm các lệnh đó (§0, `AGENTS.md`, `CLAUDE.md`); mọi agent kiểm `git status` + `git diff --stat` trước khi làm |
| CI đỏ trên `develop`, nhánh refactor chưa chạy CI | Không có kiểm tra tự động trên server | Ngoài phạm vi Phase 1; báo Human |
| Sprint kết thúc 26/11, AI-1 / AI-4 chưa có code | Demo thiếu tính năng AI chính | Q1 đã quyết: ưu tiên AI-4 WHY, AI-1 DEFERRED; AI-4 vẫn chưa có code (chưa giao) |
| Nhiều worktree cũ (`.claude/worktrees/*`, `D:\VIN\P-019-wt\*`) | Agent dễ sửa nhầm chỗ | Không xoá; luôn làm ở `D:\VIN\P-019` trừ khi §1.9 ghi khác |
| Ghi chú cũ của Agent (memory) nói "không push origin" trong khi nhánh đã có trên origin | Agent sau có thể làm sai về push | Không push khi chưa có duyệt rõ ràng |
| Baseline benchmark có thể bị trình bày như nghiệm thu (đúng hạn, an toàn sự cố, policy rẻ nhất) | Quyết định sai về policy / phạm vi an toàn | Registry §3.1 đã ghi "chỉ regression"; R-1…R-3 trong backlog DEFERRED (registry §6.1) |
| Consent backend (B1) làm backend có thể khác simulator R&D | Khẳng định "backend = simulator" quá mức | Ghi ở registry §4; D-6 PROVISIONAL (backend), xét lại sau R-4; không sửa code |

### 1.8 Trạng thái Git

**G6B.** `feature/ai-4-how-to` tại `64c85f1`, local và remote develop tại `0f877f1`. Chênh lệch với checkpoint G5 trước commit là RECOVERABLE. Cây lúc tiếp nhận sạch. Xác minh provenance và delta tại [Recovery G6B](../ai4/G6B_RECOVERY_STATE.md).

- **26/11 G5.** `feature/ai-4-how-to` tại `0f877f1`, cùng `develop` và `origin/develop`. Working tree ban đầu sạch.
  Cây code/config/test/frontend trùng blob với mirror `20bb246`. Checkpoint Phase 1 cũ là RECOVERABLE. Tệp G5 và
  provenance ở [báo cáo](../ai4/PHASE_4_3_REPORT.md). Targeted remediation giữ HEAD và cập nhật 2 file recommendation,
  thêm oracle hybrid và verification bundle có SHA-256. Các thay đổi ở working tree.

- Repo `D:\VIN\P-019`, branch `feature/unified-core`, HEAD `ce23136` — trùng `origin/feature/unified-core`.
- **Thay đổi chưa commit của Phase 1** (chỉ tài liệu, không được reset / ghi đè):
  sửa (6) `ARCHITECTURE.md`, `CLAUDE.md`, `docs/PRD.md`, `docs/adr/README.md`, `docs/architecture_diagram.md`,
  `docs/handoff/HANDOFF.md`; mới (5) `AGENTS.md`, `docs/FEATURE_REGISTRY.md`,
  `docs/communication/HUMAN_AGENT_COMMUNICATION.md`, `docs/communication/RESPONSE_TEST_CASES.md`,
  `docs/handoff/REVIEW_PHASE1.md`; kết quả review / audit (3): `docs/handoff/REVIEW_PHASE1_RESULT.md` (Codex 24/11),
  `docs/handoff/AUDIT_BACKEND_SIMULATOR_ALIGNMENT.md` (Claude 24/11), `docs/handoff/REREVIEW_PHASE1_RESULT.md` (Codex
  25/11), `docs/handoff/REMEDIATION_PHASE1.md` (Claude 25/11, P1-12b). Đối chiếu: `git status --short` phải ra đúng
  danh sách này + 4 mục `eval/results/` bên dưới. Ngày 25/11 Claude sửa thêm `HANDOFF.md`, `AGENTS.md` (bước 3),
  `CLAUDE.md` (mục Tiếp nhận) — P1-12d.
- **Remediation P1-12b (25/11, Claude) sửa:** `docs/FEATURE_REGISTRY.md`, `docs/architecture_diagram.md`,
  `docs/adr/README.md`, `docs/handoff/REVIEW_PHASE1.md` (một ghi chú §4), `CLAUDE.md` (10 bảng; phạm vi chokepoint),
  `ARCHITECTURE.md` (10 bảng), file này; tạo `docs/handoff/REMEDIATION_PHASE1.md`. Kiểm sau khi sửa: `git status
  --short` = danh sách trên (không file lạ), HEAD `ce23136`, không đổi gì ngoài `.md`.
- **Không thuộc Phase 1, có từ trước:** `eval/results/benchmark.json`, `benchmark.md`, `manifest.json`,
  `eval/results/merged-sim/` (đầu ra benchmark chưa track) — không xoá, không commit.
- Không có thay đổi nào trong `src/`, `tests/`, `frontend/`, `config/`, `migrations/`, `.github/`.
- Re-review P1-12c (25/11, Codex): chỉ ghi tiếp `docs/handoff/REREVIEW_PHASE1_RESULT.md` và các ô checkpoint được cấp quyền trong file này; không thêm đường dẫn mới. Git vẫn `feature/unified-core` @ `ce23136`. Báo cáo §R8 có snapshot tài liệu remediation, lệnh kiểm và kết quả 3 targeted tests chạy mới; suite 814/8 là evidence lịch sử.
- **D-01 / D-02 (25/11, Claude):** tạo và mở rộng `docs/handoff/DOCUMENTATION_RATIONALIZATION_AUDIT.md`; sửa ô trạng thái file này. Không sửa / xoá / di chuyển tài liệu khác. `git fetch --prune` gỡ 3 ref theo dõi của nhánh đã xoá trên remote (`origin/feature/hybrid-backend`, `origin/fix/booking-charging-state`, `origin/fix/review-issues`) — không đụng working tree, `refs/audit/*` giữ nguyên.
- **Cross-branch audit X-01 (25/11, Claude):** tạo `docs/handoff/CROSS_BRANCH_ALIGNMENT_AUDIT.md`; sửa file này (ô trạng thái). Không sửa tài liệu đã nghiệm thu. Ngoài working tree: `git fetch` 4 nhánh (ref `origin/*`), tạo ref chỉ đọc `refs/audit/2026-11-25/{unified-core,ai-4,be-fe-integration,develop}`. `git status --short` = danh sách trên + file audit.
- **Independent Cross-branch Review X-02 (25/11, Codex):** mới `docs/handoff/CROSS_BRANCH_INDEPENDENT_REVIEW.md`, sửa các ô checkpoint được phép trong file này. Chỉ thêm đường dẫn báo cáo này so checkpoint X-01; không đổi source/test/migration/policy/optimizer/tài liệu đã nghiệm thu, không đổi refs. Git vẫn `feature/unified-core` @ `ce23136`. Snapshots và tests/probes/logs ở Temp riêng; báo cáo §2/§8 ghi đường dẫn/hash/lệnh và phân biệt kết quả chạy mới với gate lịch sử.
- **Targeted Remediation P1-12e (25/11, Claude) sửa:** `docs/FEATURE_REGISTRY.md` (§3.1 MT1 / MT2, §6.1),
  `docs/architecture_diagram.md` (§2.5 luồng A / B / C), `docs/handoff/REMEDIATION_PHASE1.md` (§2 F2, §5.1, §8 mới),
  file này. Không tạo file mới; không đổi gì ngoài `.md`; `docs/adr/README.md` không đổi. HEAD `ce23136`.
- **Targeted Independent Re-review sau P1-12e (25/11, Codex):** bốn hash §1.4 khớp và vẫn khớp cuối lượt; chỉ cập nhật báo cáo hiện có và checkpoint được cấp quyền trong HANDOFF. Không thêm file repo, không sửa tài liệu review/source/test/baseline/CI. Technical Acceptance **PASS**, Formal Closure **NOT_READY**; evidence hiện hành ở báo cáo §T0–T5. Đã render thực tế đủ5 sơ đồ bằng Mermaid CLI12.2.0 trong cache tạm riêng, ảnh nằm ngoài repo trong Temp (đường dẫn/hash/lệnh ở §T3); không đổi dependency dự án. Trạng thái render chưa kiểm ở §1.4/P1-12e là evidence lịch sử, được thay bởi kết quả độc lập này.

### 1.9 Agent và khoá chỉnh sửa

**G6B (2026-11-26).** Codex nhận khoá cập nhật quyết định G5 và implementation G6B gồm chat, services/models, API, frontend tích hợp, tests và tài liệu AI-4. Baseline local `64c85f1`, cây ban đầu sạch, một worktree, các khoá G5 đã nhả. [Recovery G6B](../ai4/G6B_RECOVERY_STATE.md)

**G5 targeted remediation.** Codex đã nhận khoá F01–F04 theo review `9ecb1af`, đối chiếu đủ năm hash của patch cũ và chạy lại 10 cổng trên candidate mới. Chênh lệch checkpoint là RECOVERABLE. Đã nhả khoá sau HANDOFF_READY.

**AI-4 G5 (2026-11-26).** Codex nhận khoá implementation, tests, roadmap và evidence G5 trên `feature/ai-4-how-to` tại merged develop `0f877f1`. Đã nhả khoá sau HANDOFF_READY. Review độc lập chuyển Tech Lead. [Checkpoint G5](../ai4/PROJECT_STATE.md)

**X-02 (2026-11-25): Codex đã nhả khóa báo cáo `CROSS_BRANCH_INDEPENDENT_REVIEW.md` và checkpoint sau khi hoàn tất HANDOFF_READY. Không giữ khóa implementation hoặc tài liệu đã nghiệm thu; chưa có Agent nhận remediation X-02.**

| Vai | Agent | Thời điểm | Code đã kiểm |
|---|---|---|---|
| Implementation Phase 1 (P1-01…P1-11) | Claude Code, model `claude-opus-5-5`, phiên trên máy `D:\VIN\P-019` | 2026-11-24 | `ce23136` |
| Independent Review (P1-12) | Codex | 2026-11-24 18:18–18:28 (xong) | `ce23136` + working tree |
| Tự audit backend ↔ simulator (P1-12a) | Claude Code (`claude-opus-5-5`) | 2026-11-24 ~19:04 (xong) | `ce23136` |
| Re-review (P1-12c) | Codex | 2026-11-25: targeted N2/N3/N4 **xong, HANDOFF_READY, đã nhả khóa**; Technical Acceptance PASS, Formal Closure NOT_READY; không duyệt ADR/đóng Phase | `ce23136` |
| Sửa cơ chế bàn giao (P1-12d) | Claude Code (`claude-opus-5-5`), phiên 2026-11-25 | nhận khoá ~01:10, **nhả** khi xong | `ce23136` |
| Remediation (P1-12b) | Claude Code (`claude-opus-5-5`), phiên 2026-11-25 (Human duyệt chính thức) | nhận khoá 25/11, **nhả** khi xong (25/11) | `ce23136` |
| Targeted Remediation N2/N3/N4 (P1-12e) | Claude Code (`claude-opus-5-5`), phiên 2026-11-25 (Human duyệt) | nhận khoá 25/11, **nhả** khi xong (25/11) | `ce23136` |
| Ghi nhận quyết định Human (P1-13) | Claude Code (`claude-opus-5-5`), phiên 2026-11-25 | nhận khoá 25/11, **nhả** khi xong (25/11) | `ce23136` |
| Cross-branch audit (X-01) | Claude Code (`claude-opus-5-5`), phiên 2026-11-25 (Human giao) | nhận khoá 25/11, **nhả** khi xong (25/11) | `ce23136`; `ai-4` `4658b1f`; `be-fe` `b92e61a` |
| Ownership / purpose audit (D-02) | Claude Code (`claude-opus-5-5`), phiên 2026-11-25 (Human giao) | nhận khoá 25/11, **nhả** khi xong (25/11) | `ce23136` |
| Member mission / ownership proposal (D-03) | Claude Code (`claude-opus-5-5`), phiên 2026-11-25 (Human giao) | nhận khoá 25/11, **nhả** khi xong (25/11) | `ce23136` |

**Khoá chỉnh sửa (2026-11-25, sau P1-12b):**
- Tài liệu Phase 1 (registry, sơ đồ, ADR README, ARCHITECTURE, PRD, HACP, REVIEW_PHASE1, REMEDIATION_PHASE1):
  **đóng băng để Re-review** — không ai sửa cho tới khi Codex ghi kết quả Re-review. Sửa tiếp chỉ khi Human giao lượt
  Remediation mới.
- P1-13 (25/11, Claude): đã sửa registry §2 / §6 / §6.1, ADR README (sổ quyết định), `CLAUDE.md` / `ARCHITECTURE.md`
  (nhãn forecast), file này; **đã nhả khoá**. Không ai giữ khoá; tài liệu Phase 1 giữ đóng băng, sửa tiếp chỉ khi Human giao.
- `HANDOFF.md` §1 và báo cáo Re-review: Codex **đã nhả khóa** sau targeted N2/N3/N4 (25/11). Không có Agent đang nhận việc sửa tiếp. Technical Acceptance PASS không cấp quyền sửa implementation/ADR hoặc tự đóng Phase; bước tiếp thuộc Human theo §1.10.
- Không có Agent nào khác được xác định đang sửa (kiểm 25/11: mtime, `.ai-log/session.jsonl`, `git worktree list`).

### 1.10 Việc Agent tiếp theo cần làm

**G5 APPROVED. G6B được giao.** Codex tiến hành checkpoint A–F theo [Recovery G6B](../ai4/G6B_RECOVERY_STATE.md). G7 chờ chỉ thị riêng.

1. **Human — việc duy nhất còn lại để đóng Phase 1:** chỉ thị P1-14 khi muốn đóng. Tuỳ chọn trước đó: giao reviewer
   (Codex) đối chiếu sổ quyết định §1.5 với chỉ thị 25/11 (chỉ đọc, không chặn). C-1 commit là chỉ thị riêng (nên cân
   nhắc trước hoặc cùng lúc đóng vì tài liệu chưa commit có rủi ro mất — §1.7).
2. **Cross-branch — Human cần quyết:** X-02 đã xong, xem `CROSS_BRANCH_INDEPENDENT_REVIEW.md` §1/§3/§4/§9. Giao (hoặc chưa giao) remediation **S02** fork mất hard-pending interlock, **S03** event timeline mất sau safety ack, **W01** WHY gọi minimum60kW là approved dù actual approved39kW; xác nhận phạm vi exception sửa lõi an toàn frozen. Sau remediation, review lại phản ví dụ trước khi port G1/WHY. Chọn port BE–FE theo component/contract nền core (báo cáo §6–§7), bảo toàn safety_holds/safety_pending và decision_lock ở approval. Không merge/cherry-pick tự động; claim merge ref develop cũ kéo lại code đã bị ancestry bác bỏ. H-1…H-5 chưa được coi là duyệt bởi báo cáo.
3. **Không Agent nào có việc implementation đang giao.** R-1…R-6 DEFERRED, chưa giao (registry §6.1). Không tự triển khai, không tự sửa
   header ADR, không commit / push / merge / deploy.
4. **Nếu Human đóng Phase 1:** Agent được giao ghi `CLOSED` vào §1.3 P1-14 và §1.11; lập kế hoạch Phase 2 theo G-auto
   (chỉ kế hoạch, implementation chưa duyệt).

### 1.11 Nhật ký checkpoint

**26/11, Codex.** Ghi Tech Lead APPROVED cho G5. Đối chiếu candidate G5 với local HEAD và nhận khoá G6B.

**26/11, Codex.** Targeted remediation G5–F01–F04 đã qua 10 cổng. Hai file recommendation thay đổi, 24 tests trước
remediation khớp byte và thêm 6 tests. Đã đóng gói bằng chứng, ghi READY_FOR_FINAL_ACCEPTANCE và nhả khoá.
[Báo cáo và bundle](../ai4/PHASE_4_3_REPORT.md)

**26/11, Codex.** Đã khôi phục checkpoint từ merged develop, ghi quyết định roadmap, triển khai G5 và xác minh patch cuối.
**HANDOFF_READY**, nhả khoá và dừng chờ Tech Lead. [Báo cáo G5](../ai4/PHASE_4_3_REPORT.md)

| Thời điểm | Agent | Sự kiện |
|---|---|---|
| 2026-11-24 | Claude Code (opus-5-5) | HACP áp dụng; personal `CLAUDE.md` rút gọn quy tắc giao tiếp |
| 2026-11-24 | Claude Code (opus-5-5) | Audit chỉ đọc; Human duyệt Giai đoạn 1 có điều kiện |
| 2026-11-24 | Claude Code (opus-5-5) | P1-01…P1-10 viết xong; test chạy lại @ `ce23136` (604/8, 180, 30) |
| 2026-11-24 | Claude Code (opus-5-5) | P1-11 cơ chế chuyển giao |
| 2026-11-24 | Claude Code (opus-5-5) | Human: không commit trước review; tạo `AGENTS.md`; Claude dừng implementation, khoá tài liệu, giao P1-12 cho Codex |
| 2026-11-24 18:28 | Codex | *(khôi phục sau sự kiện)* P1-12 xong: chưa đủ điều kiện đóng, F1–F5. Không cập nhật HANDOFF (đúng quy tắc cũ) |
| 2026-11-24 19:04 | Claude Code (opus-5-5) | *(khôi phục sau sự kiện)* P1-12a tự audit backend ↔ simulator; không ghi HANDOFF vì khoá (audit dòng 8–9) |
| 2026-11-25 01:00 | Codex | *(khôi phục sau sự kiện)* P1-12c Re-review dừng ở cổng: checkpoint lệch (N1) |
| 2026-11-25 ~01:10 | Claude Code (opus-5-5) | P1-12d: khôi phục checkpoint §1.12, RCA, bổ sung §0 (Completion Checkpoint, phân loại sai lệch, escalation); nhả khoá |
| 2026-11-25 | Human | Xác nhận chưa giao Remediation trước đó; duyệt chính thức P1-12b |
| 2026-11-25 | Claude Code (opus-5-5) | Nhận khoá P1-12b. Git khớp §1.8 (HEAD `ce23136`, không file lạ) |
| 2026-11-25 | Claude Code (opus-5-5) | P1-12b xong: kiểm chứng F1–F5 (5 đúng, 0 bác, 3 bổ sung), sửa registry / sơ đồ / ADR README / CLAUDE / ARCHITECTURE / brief, tạo `REMEDIATION_PHASE1.md`; G1/G2 + check_docs PASS. **HANDOFF_READY**; nhả khoá, chuyển Codex (P1-12c) |
| 2026-11-25 | Codex (Independent Reviewer) | P1-12c tiếp tục và xong: checkpoint khớp `ce23136`; F1/F3/F4 RESOLVED, F2/F5 PARTIALLY_RESOLVED; Technical Acceptance FAIL, Formal Closure NOT_READY. Báo cáo `REREVIEW_PHASE1_RESULT.md` §R0–R9; 3 targeted tests mới đạt, check_docs PASS; không chạy toàn suite/CI/benchmark mới. Đã đồng bộ các mục trạng thái được cấp quyền, **HANDOFF_READY**, nhả khóa; bước tiếp: Human giao remediation tài liệu N2/N3/N4. |
| 2026-11-25 | Human | Duyệt Targeted Remediation N2 / N3 / N4 (chỉ tài liệu governance) |
| 2026-11-25 | Claude Code (opus-5-5) | Nhận khoá P1-12e. Git khớp §1.8 (HEAD `ce23136`, không file lạ) |
| 2026-11-25 | Claude Code (opus-5-5) | P1-12e xong: N2 hạ nhãn nguyên nhân (MT1 / MT2, REMEDIATION F2); N3 vẽ lại A (vòng thử lại), B (phạm vi gộp), C (đổi trạng thái trước sự kiện) theo source; N4 tiêu chí + phụ thuộc R-1…R-6. F1 / F3 / F4 giữ nguyên. G1 / G2, check_docs PASS; render Mermaid **blocker** (không có renderer). SHA-256 ở §1.4. **HANDOFF_READY**; nhả khoá, chuyển Codex |

| 2026-11-25 | Codex (Independent Reviewer) | Targeted Independent Re-review N2/N3/N4 sau P1-12e: snapshot 4/4 MATCH; source/test/baseline không đổi @`ce23136`; N2/N3/N4 RESOLVED, F1/F3/F4 tái sử dụng hợp lệ, F2/F5 đóng về governance. Mermaid CLI12.2.0 cài cache tạm và Chrome headless chạy với quyền được cấp: 5/5 render thành công, đã xem đủ5 ảnh; check_docs PASS. **Technical Acceptance PASS; Formal Closure NOT_READY**. Báo cáo hiện hành `REREVIEW_PHASE1_RESULT.md` §T0–T5 (bảng quyết định Human ở T4); không chạy suite/benchmark/CI, không duyệt ADR/commit/đóng Phase. **HANDOFF_READY**, đã nhả khóa; chuyển Human quyết định hoặc ghi hoãn và xác nhận closure. |
| 2026-11-25 | Human | Chấp nhận Technical Acceptance PASS; quyết Q1–Q4, D-3…D-6, C-3, G-auto, backlog R-1…R-6 (P0 / P1 / P2); C-1, P1-14 chưa cho phép |
| 2026-11-25 | Claude Code (opus-5-5) | P1-13: nhận khoá; Git khớp §1.8, SHA-256 4 tài liệu khớp §1.4 trước khi sửa |
| 2026-11-25 | Claude Code (opus-5-5) | P1-13 xong: sổ quyết định §1.5, registry §2 / §6 / §6.1, ADR README, C-3. Readiness READY_FOR_HUMAN_CONFIRMATION (§1.13). check_docs PASS; SHA-256 mới ở §1.13. **HANDOFF_READY**; nhả khoá |
| 2026-11-25 | Human | Giao cross-branch audit `feature/ai-4`, `feature/be-fe-integration` (chỉ đọc) |
| 2026-11-25 | Claude Code (opus-5-5) | X-01 xong: ai-4 READY_WITH_CONDITIONS, be-fe NOT_READY; tái hiện độc lập R01–R05 của ai-4 trên `ce23136`; test ai-4 864 đạt / be-fe 623 + 44 FE đạt (trên nền riêng); merge thử: ai-4 sạch, be-fe 9 file xung đột. Không đổi Technical Acceptance Phase 1. **HANDOFF_READY**; nhả khoá |

| 2026-11-25 | Codex (Independent Reviewer) | **X-02 xong, HANDOFF_READY**: chỉ local refs ce23136/4658b1f/b92e61a/68692ee; xuất git archive Temp, không fetch/merge/reset/commit. Baseline14 fail/2 pass cùng16 assertions; AI-4 targeted130 pass, oracle31/31+8/8 mutation, BF6 API pass. Probes reviewer xác nhận baseline fork33kW/live0, final đã giữ hold nhưng còn pending-fork33kW (S02), event timeline mất sau safe readback (S03), WHY minimum60/approved39 (W01). Bỏ kwargs safety mô phỏng conflict làm G1-F03 quay lại. G1/G2 CHANGES_REQUIRED; BF/cross-integration NOT_READY. Develop là ancestor core nên claim merge develop khôi phục code cũ bị bác. Báo cáo mới `CROSS_BRANCH_INDEPENDENT_REVIEW.md`; source/tài liệu nghiệm thu không đổi, nhả khóa; chuyển Human quyết remediation/port phạm vi rõ. |
| 2026-11-25 | Claude Code (opus-5-5) | D-01 audit tài liệu chỉ đọc xong (ghi "Checkpoint cần đồng bộ" vì X-02 giữ khoá) — chép vào đây ở lượt D-02 |
| 2026-11-25 | Claude Code (opus-5-5) | D-02 xong: 4 thành viên + template + 3 tác nhân AI định danh; ownership 192 tài liệu; RACI 13 nhóm; tự merge 8/8 PR, 0 review người; "Tech Lead" ba nghĩa; dòng `LiveStation` trong tài liệu simulator do commit `c801084` (LufkyMama) chèn; HD-8…HD-14. Đính chính X-01 theo X-02 (merge `develop` không khôi phục code). **HANDOFF_READY**; nhả khoá |
| 2026-11-25 | Claude Code (opus-5-5) | D-03 xong: thẻ sứ mệnh 4 thành viên, RACI, owner module / tài liệu, việc W-S02 / S03 / W01 / G1 / CT / BF / MT9 / DOC / GOV gắn X-02, phụ thuộc, HD-8…HD-14 (PROPOSED; HaiVuu cần xác nhận). Không giao việc, không đổi ownership. **HANDOFF_READY**; nhả khoá |

### 1.12 Bản ghi khôi phục sau sự kiện (2026-11-25, Claude Code) — Remediation và nguyên nhân lệch checkpoint

Bản ghi này **tái dựng từ bằng chứng chỉ đọc**, không phải báo cáo do Agent làm việc lúc đó viết.

**Bằng chứng đã kiểm (25/11):**
- Git: branch `feature/unified-core`, HEAD `ce23136`, `git status --short` = danh sách §1.8. Không có commit mới.
- Thời điểm sửa cuối: mọi tài liệu Phase 1 ≤ 24/11 18:20:36 (`REVIEW_PHASE1.md`); `REVIEW_PHASE1_RESULT.md` 18:27:49;
  sau đó chỉ có `AUDIT_BACKEND_SIMULATOR_ALIGNMENT.md` (19:04) và `REREVIEW_PHASE1_RESULT.md` (25/11 01:00).
- Nội dung: registry vẫn ghi I-2 (F14) "chưa thấy test", I-3 (F10) "chưa tìm thấy test riêng" — đúng điều F4 yêu cầu
  sửa; `CLAUDE.md` / `ARCHITECTURE.md` vẫn ghi 9 bảng (F4: thực tế 10).
- Log prompt `.ai-log/session.jsonl` (Claude, repo này): sau 24/11 18:19 chỉ có câu hỏi optimizer (18:48), yêu cầu audit
  backend ↔ simulator (18:59), và yêu cầu này (25/11 01:06). Không có yêu cầu Remediation. Không tìm thấy file phiên
  Codex để đối chiếu. `git worktree list`: không worktree nào chứa tài liệu sửa sau review.

**Trạng thái F1–F5:**

| F | Nội dung review | Đã xử lý? | Chuyển thành |
|---|---|---|---|
| F1 | Baseline bỏ 40/160 sự cố (A05), trộn kịch bản legacy | Không có bằng chứng | Đề xuất task kỹ thuật riêng: dataset nghiệm thu sự cố (ngoài Phase 1, chưa giao) |
| F2 | "Khả thi từng xe" ≠ khả thi cả bãi; workload vượt năng lực | Không có bằng chứng | Gắn D-4 (§1.5) + audit B4; task kỹ thuật riêng (chưa giao) |
| F3 | Giá rẻ hơn chưa chứng minh M3a tốt nhất | Không có bằng chứng | Gắn Q3 (§1.5) — Human quyết |
| F4 | Registry bỏ sót test F10/F14, thiếu FR10–11/AC/MT, 9 vs 10 bảng | **Chưa** (đã kiểm nội dung) | P1-12b (sửa tài liệu) |
| F5 | Sơ đồ A/B/C sai thứ tự; phạm vi lời Guard | Không có bằng chứng | P1-12b (sửa tài liệu) |

Các cột "chuyển thành" là **đề xuất** của bản khôi phục, chưa có Agent hay Human nhận.

**Cập nhật sau Remediation P1-12b (2026-11-25, Claude Code)** — thay bảng trên; chi tiết `REMEDIATION_PHASE1.md`:

| F | Kiểm chứng lại | Governance đã sửa (tài liệu) | Chuyển task kỹ thuật (chưa giao) |
|---|---|---|---|
| F1 | Đúng + bổ sung: `connector_failure` trùng KPI `peak_evening` | Registry §2 F9, §3.1 MT4, §3.2 FR10; sơ đồ §1.3 F9, Tầng 4 | R-1 |
| F2 | Đúng + bổ sung: `hybrid_evening` seed 1 cũng vượt năng lực AC | Registry §2 F2, §3.1 MT1–MT2, §4 (B4), §5 I-1, §6 D-4 | R-2 (sau D-4) |
| F3 | Đúng + làm rõ: VND / kWh, M3b rẻ nhất theo kWh | Registry §3.1 MT3, §6 D-2; ADR README Q3 | R-3; Q3 vẫn chờ Human |
| F4 | Đúng | Registry §1.1, §2 F10 / F14, §3.2 FR17 / FR18 / FR42–44, §3.4 AC1–AC17, §5 I-2 / I-3 đóng; 10 bảng ở CLAUDE / ARCHITECTURE | — |
| F5 | Đúng | Sơ đồ luồng A / B / C theo code, §2.1, §2.4, Tầng 3 (consent); registry MT6; `CLAUDE.md` chokepoint; ADR README nhóm C = 6 | R-4 (sau D-6) |
| Audit B1–B4, U1–U3 | B1, B2, B4 kiểm lại đúng; B3, U1–U3 không kiểm lại | Registry §4, §5 I-7, §6 D-6; sơ đồ Tầng 3 | R-4, R-5, R-6 |

**Quyết định còn chờ Human:** §1.5 (Q1–Q4, D-3…D-5, G-auto, C-1, C-3) + mới: hướng Remediation (§1.10 mục 2) + câu hỏi
B1 của audit (consent là ràng buộc Planning Core hay business rule backend).

**Nguyên nhân checkpoint lệch (RCA):**

| Giả thuyết | Kết luận | Bằng chứng |
|---|---|---|
| HANDOFF bị khoá | **XÁC NHẬN** | §1.9 cũ: "KHOÁ — không ai sửa", trạng thái review "không ghi vào file này"; audit dòng 8–9 ghi rõ không cập nhật §1.11 vì khoá |
| Quy trình không có người chịu trách nhiệm cập nhật | **XÁC NHẬN** | §1.10 cũ giao đồng bộ cho "Implementation Agent (sau review)" nhưng không có điều kiện kích hoạt, không ai được giao; reviewer bị cấm sửa HANDOFF |
| Xong task nhưng chưa xong thủ tục bàn giao | **XÁC NHẬN** cho P1-12 và P1-12a | Hai file kết quả tồn tại, không có dòng §1.3 / §1.8 / §1.11 nào |
| Quy tắc chưa đủ rõ | **XÁC NHẬN một phần** | §0 không định nghĩa "xong" gồm bàn giao; mọi lệch đều buộc dừng, không phân loại |
| Agent quên cập nhật | **Không đủ bằng chứng** | Các Agent tuân đúng quy tắc khoá lúc đó |
| Remediation đã làm nhưng không ghi | **Không đủ bằng chứng; bằng chứng hiện có cho thấy chưa làm** trong workspace này | Mtime, nội dung registry, log prompt ở trên |

Khắc phục: §0 bổ sung "Checkpoint có thể khôi phục", "Hoàn tất bắt buộc" (`WORK_COMPLETED` ≠ `HANDOFF_READY`), mục
"Checkpoint cần đồng bộ" khi HANDOFF bị khoá, khoá review không chặn các mục trạng thái, phân loại sai lệch
MINOR / RECOVERABLE / BLOCKING và quy tắc escalation.


### 1.13 Kiểm tra Formal Closure Readiness (2026-11-25, Claude Code, P1-13)

**Kết luận: READY_FOR_HUMAN_CONFIRMATION** — đủ điều kiện để Human xác nhận đóng; Phase 1 **chưa đóng** (P1-14 chưa cho
phép ở lượt này).

| Điều kiện đóng | Trạng thái | Bằng chứng |
|---|---|---|
| Technical Acceptance độc lập | ĐẠT — PASS, Human chấp nhận 25/11 | `REREVIEW_PHASE1_RESULT.md` §T4 |
| F1–F5, N2–N4 | RESOLVED về governance | §T2; nguyên nhân kỹ thuật ở backlog R-1…R-6 |
| Quyết định Human bắt buộc | ĐẠT — mỗi mục có nhãn APPROVED / PROVISIONAL / DEFERRED và điều kiện xét lại | §1.5 |
| Mermaid render | ĐẠT (5/5, cục bộ) | §T3 |
| Chỉ sửa tài liệu | ĐẠT — HEAD `ce23136`; diff `src tests frontend config migrations .github eval/evidence` rỗng | kiểm 25/11 |
| Bàn giao | ĐẠT — HANDOFF_READY, không ai giữ khoá | §1.9 |
| Chỉ thị đóng của Human (P1-14) | **CHƯA** | — |

Không chặn đóng nhưng cần biết: (1) sổ quyết định do Implementation Agent ghi, chưa có reviewer đối chiếu; (2) tài liệu
chưa commit (C-1) — rủi ro mất nếu workspace bị reset; (3) CI chưa kiểm chứng (runner tắt chủ ý); (4) ADR nhóm B / D uỷ
quyền Tech Lead chưa xử lý, header 19 ADR giữ `Proposed`; (5) R-1…R-6 chưa giao ⇒ MT1, MT4 với sự cố, chọn policy **không**
được dùng để nghiệm thu sản phẩm.

Snapshot SHA-256 sau P1-13 (HANDOFF không tự chứa hash):
`docs/FEATURE_REGISTRY.md` `7f94dca1f7fe7e21d26b89da6b77a84916b69ee085c383ee6f2d116b0fcfadb8` · `docs/adr/README.md` `f90a42b77e9ecabea93a404f6dbacb941e575f87a66f24de404f8cabb201a51c` · `CLAUDE.md` `36ac0e23e81fadd5e78ea19bea26ef33c6b96303b44507b57283396a6e2e910a` · `ARCHITECTURE.md` `9f7e7766feb1068b466b0c3812948beb6f3d2f88903e9cb80e9709d192ea2ef4` · không đổi: `docs/architecture_diagram.md` `2a88672d…39db`, `docs/handoff/REMEDIATION_PHASE1.md` `9278931e…2f0b`. Không file `docs/adr/ADR-*.md` nào bị sửa.
---

## Trạng thái 24/11 (lịch sử gần nhất) — Unified Core đã nghiệm thu và ĐÓNG BĂNG

- Refactor kết thúc: `docs/refactor/FINAL_ACCEPTANCE_REPORT.md` (+ `FINAL_REVIEW_FIX_REPORT.md`). Không refactor thêm;
  việc tiếp theo là nghiên cứu MVP-3.5 (Tech Lead / Codex).
- `/simulation/benchmark` + S8 = baseline đóng băng `eval/evidence/2026-11-24-unified-core-frozen-baseline/`
  (provenance theo policy). S8 lấy danh sách policy từ `GET /simulation/policies`.
- `guard.after_apply_failsafe: true` mặc định; sự kiện của `sync_clock` không còn bị bỏ.
- Nhánh `feature/unified-core` đã push lên P-019 `origin` để mở PR vào `develop`. Nhánh `feature/be-fe-integration`
  (FE G1–G24) cần merge `develop` mới: lệch import `src.agents.*` → `src.llm_chat.*`, `quote_change` phải dùng
  admission async + consent thật, sơ đồ bãi G24 nên đọc `rt.store` và không phát trong bản fork / benchmark, `budget_kw`
  của G23 đang là trần vật lý (không phải ngân sách optimizer), frontend dùng `policy_id ?? strategy`.
- Chưa kiểm chứng: E2E Postgres thật, LLM thật, deploy Render sau refactor; một worker.
- Governance Giai đoạn 1: xem §1 ở đầu file.

## Trạng thái 23/11 (lịch sử) — refactor Unified Core, Phase 4

Đọc `docs/refactor/TECHLEAD_PHASE4_DECISIONS.md` + `docs/refactor/PHASE4_*_REPORT.md`. Hiện trạng kiến trúc (thay mọi
mô tả `LiveStation` / A–D ở mục 22/11 bên dưới):
- Backend = `HybridStation` trên **một kernel** `StationKernel` dùng chung với `HybridSimulator` (ADR-018, ADR-019).
  `LiveStation`, LP backend A–D (`lp_model`, `assignment`, `mpc`, `baselines`, `strategies`) **đã xoá**;
  `STATION_ENGINE` chỉ còn `hybrid`. `LIVE_STRATEGY` ∈ B0 / M2b / M3a / M3b (A–D bị từ chối khi đọc cấu hình).
- Quote / booking / đổi yêu cầu = admission trên bản fork của trạm (`src/services/admission.py`), trả **ước tính có
  điều kiện** (`ScheduleProposal.certainty`, `assumptions`, số phê duyệt chờ) — không phải SLA.
- (Lịch sử) S8 từng đọc baseline tạm `eval/evidence/2026-11-23-refactor-phase3-baseline/`; nay là baseline đóng băng ở trên. Bảng A–D cũ: archive deprecated ở
  `eval/results/archive/2026-11-22-pre-refactor/`.
- Alembic `0003` (`0003_drop_lp_strategy_plans.py`) xoá lịch lưu của A–D → sau deploy chạy `make migrate` / `alembic upgrade head`.

## Trạng thái 22/11 (lịch sử — kiến trúc `LiveStation` / A–D nay đã bỏ)

**Đã merge vào `develop`:** PR #8 (backend chạy thật: DB, auth, Guard, optimizer, `LiveStation`, WebSocket), PR #9
(job CI `deploy` qua Docker Hub + Render Deploy Hook), PR #10 (hiện trạng deploy, `docs/plan/56`).

**Đang chạy:** web https://p019-web.vercel.app (Vercel CLI, team *SWP391's projects*) → backend test
https://p019-backend-develop.onrender.com (Render Free, image `minhmama/p019-backend`) → Neon nhánh `dev`. CI chạy trên
runner `team-19` = VM `p019-runner` trên laptop (phải bật mới có CI / deploy). Chi tiết: `docs/plan/56` §0.

**Nhánh `fix/booking-charging-state`** (PR vào `develop`):
- `fix(optimizer)`: LP tôn trọng `consent.max_start_delay_minutes` (trước đó xe walk-in cắm cổng 0 kW hàng giờ).
- `feat(ops)`: deploy bật `CONTROL_LOOP_ENABLED=true` — trạm tự chạy theo thời gian; test hành vi cho `run_forever`.
- `docs`: rà toàn bộ tài liệu theo hiện trạng (backend dùng `LiveStation`, ADR-016); dọn tài liệu cũ.

**Nhánh `fix/guard-simulator-contract`** (PR vào `develop`): lớp vật lý của Guard backend gọi thẳng Guard của
HybridSimulator qua `src/guard/physical.py` (ADR-017) — trần vùng `physical_zone_cap_kw` 22/120 thay cho ngân sách 22/78, nguồn `independent`, không cấp điện
cổng trống / xe đầy, chỉ gán xe đang chờ. Benchmark A–D: 0 lệnh bị chặn, 0 vi phạm. Chưa làm: hạ trần tủ theo sự kiện,
công suất nhận theo đường sạc DC (cần nối HybridSimulator).

**Nhánh `feature/hybrid-backend`** (chưa commit, gồm cả phần Guard ở trên): backend chạy engine simulator (ADR-018) —
`src/simulator/hybrid_station.py` (trạm dựng từ QueueController + EV2GymAdapter, phát lại `mvp1` khớp HybridSimulator),
`src/services/hybrid_planner.py` (B0 / M2b / M3a / M3b từ `benchmark_mvp3.POLICIES`), `STATION_ENGINE` / `LIVE_STRATEGY`,
ev2gym `--no-deps` trong Dockerfile / CI / `make install`. Bằng chứng `eval/evidence/2026-11-23/`. Còn: đo RAM image trong
Docker, profile DC VinFast cho xe đến dần (đã làm ở Final Review 4.2), consent cư dân trong thuật toán simulator, nhóm chọn
`LIVE_STRATEGY` (M3a rẻ hơn nhưng đúng hạn thấp hơn A_edf trên kịch bản backend).

**Việc tiếp theo:**
1. Sau merge: Render → Environment đặt `CONTROL_LOOP_ENABLED=true` (service tạo từ image, không đọc `render.yaml`).
2. Nhóm chốt chính sách tạm dừng: với `allow_power_reduction=true`, LP sạc bước đầu rồi tạm dừng tới giờ thấp điểm
   (booking vẫn "đang sạc"). Chọn: giữ + sửa UI / mức công suất tối thiểu / mặc định không cho giảm.
3. ~~Nhóm duyệt ADR-016~~ — đã giải quyết: ADR-018 thay ADR-016, ADR-019 xoá `LiveStation` (differential test
   CLI ↔ backend thay cho "live = research").
4. Production: PR `develop` → `main`, service Render riêng (Starter trước demo), Neon nhánh `main`,
   `RENDER_DEPLOY_HOOK_PROD`, đổi `NEXT_PUBLIC_API_URL` Production trên Vercel (plan 56 §3.5).
5. Giới hạn tần suất `/chat` theo user; sửa regex phút trong `src/llm_chat/mock_llm.py` (nhận tới 99).
6. Runner: giữ VM laptop hay thuê VPS x86_64 (4 vCPU / 8 GB) — nhóm quyết.
7. Deliverable BTC: `README.md`, `JOURNAL.md`, `WORKLOG.md` đã điền theo dự án (22/11). Còn thiếu: mã sinh viên trong
   README, phần tuần 1 của JOURNAL ("[nhóm bổ sung]"), video demo, pitch deck, `eval/results/report.md` với LLM thật.
8. `docs/mockups/` + `docs/plan/22-ui-work-split.md`: bản thiết kế / kế hoạch UI đã xong, giữ làm **tham khảo**; UI thật
   là `frontend/`, spec là `docs/plan/21-ui-spec.md`.
9. Câu hỏi mở cho nhóm / mentor: Guard bao nhiêu luật, FR4a, FR23b, F15, F9 Should hay Must; redesign "đêm sạc" của
   mockup chưa vào spec 21 §1.1.

## Xác minh nhanh khi tiếp tục

```bash
git status --short && git log --oneline -5
.venv/Scripts/python.exe -m ruff check src tests && .venv/Scripts/python.exe -m ruff format --check src tests
.venv/Scripts/python.exe -m pytest tests/ -q                    # 24/11 @ce23136: 604 passed, 8 skipped
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/check_docs.py
curl https://p019-backend-develop.onrender.com/ready            # Free ngủ: lần đầu chờ ~50 s
cd frontend && npm run typecheck && npm test
```

## Bẫy đã gặp (lỗi + cách xử lý)

**Môi trường Windows / công cụ**
- `python` / `ruff` / `pytest` trên PATH không có package → luôn dùng `.venv/Scripts/python.exe -m …`.
- Console cp1258: đặt `PYTHONIOENCODING=utf-8` (`python -I` bỏ qua biến này → `python -I -X utf8`). `alembic.ini` phải ASCII.
- `.env` của máy dev trỏ Postgres local → `tests/__init__.py` ép SQLite tạm; chạy app local thì đặt `DATABASE_URL` cho phiên.
- Shell của công cụ có thể đổi thư mục sau `cd` → luôn `cd /d/VIN/P-019` ở đầu lệnh. Git Bash + `docker exec … sh -c
  '/đường/dẫn'` bị đổi đường dẫn → `MSYS_NO_PATHCONV=1`.
- Python trong `.venv` trên Windows là launcher: đo RAM / PID phải lấy process **con**.
- `ruff check .` báo lỗi sẵn có ở `scripts/` — CI chỉ kiểm `src/ tests/`.

**Backend**
- Autogenerate Alembic sinh `astext_type=Text()` thiếu `sa.` → sửa tay. Không có relationship ORM → flush user trước booking.
- Tool async của LangChain không hỗ trợ `.invoke` (raise NotImplementedError — dễ nhầm thành 501) → node dùng `ainvoke`.
- `eval/run_eval.py` ghi đè file được track trong `eval/results/` → chạy thử thì `--out` ra thư mục tạm.
  `eval/run_benchmark.py` ghi `eval/results/benchmark.{json,md}` (kind `generated`); S8 không đọc file này mà đọc
  baseline có version — muốn đổi baseline thì tạo thư mục `eval/evidence/<ngày>-...-baseline/` có `manifest.json`.
- HiGHS lỗi native khi đổi thread → mọi lần giải LP qua `src/services/solver.py` (một worker thread).
- Lỗi không phải `OpenAIError` trong `/chat/stream` làm luồng đứt im lặng (web chỉ thấy "Máy chủ gặp lỗi") → xem log Render.
  Ví dụ đã gặp: `OPENAI_API_KEY` còn chuỗi mẫu tiếng Việt → `UnicodeEncodeError: 'ascii'` khi dựng header.

**Deploy / CI**
- VM runner treo ở `Loading essential drivers` khi máy có Hyper-V và thiếu RAM → `VBoxManage controlvm p019-runner reset`;
  bật VM khi máy còn ≥ 6 GB trống. Lỗi mạng tạm (`DeadlineExceeded`, `ConnectionTimeout`) → `gh run rerun --failed`.
- Pip cache tải mãi `Received 0 of …` → `SEGMENT_DOWNLOAD_TIMEOUT_MINS=2` (đã có trong `ci.yml`).
- `pytest` trần không thấy package `src` ở `src/simulator/tests` → `pytest.ini` có `pythonpath = .`.
- Render *Existing Image*: tag dùng dấu `:`; báo "credential invalid" khi tag **chưa được push**; region không đổi được.
- Org BTC chặn GitHub App → Render / Vercel không nối repo; Vercel tạo team mới cần thẻ thanh toán.
- Secret (JWT, key, chuỗi Neon) không tạo / dán trong khung chat AI — hook ai-log gửi prompt lên server BTC.

**Frontend / tài liệu**
- Next 16 bật Cache Components: tham số động bọc `<Suspense>`; `LayoutProps<"/route">` cần `next typegen` trước `tsc`;
  đọc `frontend/AGENTS.md` trước khi viết code web. `frontend/.gitignore` chặn `.env*` → có `!.env.example`.
- `.dockerignore`: mẫu không có `**/` chỉ khớp ở thư mục gốc.
- Mermaid `sequenceDiagram`: không đặt alias participant là `OPT` / `ALT` / `LOOP` / `PAR` / `END` (trùng từ khoá).
- Mockup / xuất Figma (`docs/mockups/_figma/`): `export.mjs --only …` ghi đè `plugin/code.js` → chạy lại bản đầy đủ trước
  khi bàn giao; SVG không nhận biến CSS → dùng mã hex.
