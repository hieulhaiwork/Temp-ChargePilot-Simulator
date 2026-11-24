# Tech Lead Decisions — Phase 3 Review → Phase 4 (2026-11-23, nguyên văn)

Đã review `PHASE3_REPORT.md` §9, `EXPECTED_FAILURES.md` và code trên mirror tại `99d90ed`. **Chấp nhận hướng kiến trúc
Phase 3, cho phép Phase 4 — Cleanup & Final Integration.**

1. **Loại bỏ A–D hoàn toàn.** Xoá A–D trong `StrategyName`, OpenAPI và Frontend S8. S8 dùng B0, M2b, M3a, M3b. Không
   khôi phục LP backend cũ. Evidence / benchmark A–D lịch sử giữ dạng archive, nhãn deprecated, không trộn với benchmark
   mới. Không triển khai lại EDF-only / Oracle; sau này cần thì đăng ký policy mới.
2. **Thêm `EventType.CHARGE_COMPLETED`.**
   - Kernel và Backend cùng nhận diện sự kiện hoàn tất sạc, tách khỏi `REPLAN_REQUESTED`.
   - Cập nhật OpenAPI, generated frontend types, UI S6, consumers.
   - Không tạo nhiều lần replan trong cùng timestamp.
   - Không đổi physics / completion semantics của golden cũ.
3. **0,01 kW/cổng = deadband cho command resolution, không dùng để che vi phạm điều phối.**
   - Hard physical constraint giữ tolerance `1e-7`.
   - Phân biệt command deadband / assigned-budget deviation / hard-cap violation trong trace, log, metrics.
   - **Root-cause sai lệch AC +1,97 kW** của Phase 3.
   - Nếu lệnh giảm công suất bị anti-flapping hoặc HITL chặn trong tình huống phải tuân thủ giới hạn an toàn, phải có cơ
     chế ưu tiên giảm tải / fail-safe hợp lệ.
   - Không kết luận đã giải quyết chỉ vì có replan.
4. **API công bố trước sự cố nguồn: chưa làm (MVP-3.5).** Phase 4 chỉ giữ xử lý mất / giảm nguồn tức thời; kiến trúc
   không chặn việc thêm `announced_at` / `effective_at` sau này (optimizer online chỉ thấy giới hạn đã công bố).
5. **Admission + HITL: tạm chấp nhận mô phỏng thận trọng** (lệnh chờ HITL chưa thực thi).
   - Không trình bày quote giả định thành SLA bảo đảm vô điều kiện.
   - Nếu kết quả phụ thuộc approval, API / UI thể hiện trạng thái điều kiện / chờ xác nhận.
   - Giữ test admission ↔ execution.
   - Ghi rõ giả định (sự cố tương lai, xe chưa biết, approval).
   - Không cần mô hình xác suất đồng ý.
6. **DecisionTrace đầy đủ cho Backend, cùng schema / facts / reason codes với simulator.** Liên kết:
   - scenario / state version, timestamp, policy / version;
   - observation + giới hạn hiệu lực;
   - coordinator budgets;
   - optimizer proposals + diagnostics;
   - consent adjustments, Guard / HITL decisions;
   - approved commands + actual applied results;
   - rejection, fallback, budget deviation, physical violations.

   Yêu cầu: có cấu trúc, có correlation ID. Tóm tắt vận hành trong DB, trace chi tiết dạng artifact / evidence có kiểm
   soát. Không lưu secret, token hay dữ liệu cá nhân không cần. Phải hỗ trợ replay, debug, benchmark, AI-4 WHY / WHAT-IF.
   Không dùng LLM tự tạo lý do ngoài evidence.
7. **Chuyển `StationKernel` vào `src/simulator/core/`** nếu giúp tách trách nhiệm.
   - Không tạo engine mới / package deploy riêng.
   - `HybridSimulator` và `HybridStation` vẫn dùng đúng một kernel.
   - Tách planning / physics / event theo trách nhiệm thực tế, không tạo lớp chỉ để tăng abstraction.
   - Được sửa import, test monkeypatch, API nội bộ. Không giữ shim vĩnh viễn.
   - Giữ differential tests + golden.
8. **Baseline mới = kết quả Backend Phase 3, có version.**
   - Lưu riêng cùng commit, scenario, policy, seed, time config, phiên bản thư viện.
   - Giữ evidence Phase 0–2, không ghi đè.
   - Không so Phase 2 với Phase 3 như cùng điều kiện.
   - Sửa lỗi thật ở Phase 4 được làm KPI đổi, nhưng phải có báo cáo trước / sau + lý do.
   - Sau khi xử lý budget deviation và nghiệm thu E2E, sinh baseline chính thức cuối refactor.
9. **EXPECTED_FAILURES phải giải quyết:**
   - S8 còn A–D;
   - `/simulation/benchmark` trả dữ liệu cũ;
   - config / README còn `STATION_ENGINE=live` (xoá / cập nhật, không khôi phục LiveStation);
   - script / tài liệu evidence mô tả kiến trúc lỗi thời.

   Không xoá evidence lịch sử chỉ vì chứa tên cũ; phân biệt archival evidence với tài liệu vận hành hiện hành.
10. **Quy trình:** replacement refactor. Cho phép Backend / Frontend tạm hỏng ở commit trung gian; được đổi internal API,
    schema, import, test consumer, xoá code cũ. Không dừng xin duyệt từng bước. Milestone nội bộ (được đổi thứ tự để
    giảm xung đột):
    1. API / Frontend cleanup + baseline migration;
    2. kernel / package cleanup, xoá shim, chuyển resident LLM chat (đã xong ở nhánh llmchat);
    3. DecisionTrace, điều tra budget deviation, safety hardening;
    4. full regression + integration / E2E acceptance + tài liệu cuối.

    **Chỉ escalate** nếu phải thay công thức vật lý, objective optimizer, cơ chế hard safety, cam kết SLA, hoặc quyền phê
    duyệt nghiệp vụ ngoài phạm vi đã chốt.

**Definition of Done:**
- Một Planning Core + một Physical Core.
- Một registry thuật toán chính thức.
- Admission cùng nguồn mô hình / thuật toán với thực thi.
- Thay AC / DC / Global optimizer qua registry / config mà không viết lại Backend.
- Không còn LiveStation, LP cũ, compatibility shim, consumer lỗi thời trong production.
- DecisionTrace backend dựa trên facts.
- Budget deviation có nguyên nhân + xử lý rõ.
- Frontend, Backend, LLM Chat, Simulator standalone, OpenAPI, E2E đều nghiệm thu.
- Golden + evidence lịch sử bảo toàn.

**Dừng ở final acceptance để review, không tự merge / deploy vào nhánh chính.**
