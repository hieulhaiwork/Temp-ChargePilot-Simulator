# ADR-014: DecisionTrace, counterfactual sandbox không bao giờ apply, và vòng đời đề nghị HITL cho AI-4 / AI-1

- Trạng thái: Proposed — chờ nhóm duyệt
- Ngày: 2026-11-21
- Sửa đổi một phần: ADR-005 (bảng mới), ADR-006 (Operator được dùng Copilot), ADR-007 (job nền cho tác vụ dài),
  ADR-008 (mã lỗi mới)
- Liên quan: ADR-011 (`SimulatorGateway`), ADR-013 (LLM hai đầu), ADR-015 (phạm vi)
- Nguồn: master context v1.0 §8 (AI-4, AI-1), §9.4 (grounding), §10.5; RESEARCH SC-16 Hướng 1 và Hướng 4

## Bối cảnh

MVP-4 chốt **AI-4 Decision Copilot (WHY + WHAT-IF)** là tính năng chính và **AI-1 phát hiện xung đột + thương lượng SLA
có HITL** là luồng bổ trợ. Cả hai dùng chung hai lõi: vết quyết định và mô phỏng phản thực tế. RESEARCH nhấn mạnh:
"những lựa chọn này phải do Optimizer tính ra, không được LLM tự bịa phần trăm pin hay thời gian", và "Optimizer phải
cung cấp thông tin giải thích, không chỉ mảng power_allocations".

Skeleton hiện chưa có các lõi này. ADR-006 chỉ cho `resident` dùng `/chat`; ADR-007 xử lý sự kiện ngay trong request,
trong khi R&D báo sinh phương án AI-1 mất nhiều giây (xem §Bằng chứng).

## Quyết định

### 1. DecisionTrace (sinh từ engine, không từ LLM)

Mỗi lần quyết định ghi: `policy_id`, `optimizer_status`, `fallback_reason`, `limits` hiệu lực (lưới / vùng / tủ tại t),
`binding_constraints` (kèm ID tủ / vùng), từng xe (`soc`, kWh còn thiếu, `slack_minutes`, requested / allowed / actual
kW), hàng chờ, `at_risk_vehicles`, kết quả Guard (vật lý và chính sách), `state_version`, `config_hash`, metadata đường
sạc. Mỗi mục có `evidence_ref` ổn định để câu trả lời trỏ về.

### 2. WHY

Trả `{kind, status: ok|no_data|forbidden|unsupported, subject_id, decision_time, reasons[{code, text, evidence_ref}],
facts, assumptions, policy_id, state_version}`. Chỉ nêu nguyên nhân có `reason_code` + `evidence_ref` đúng đối tượng và
đúng interval; thiếu chứng cứ nhân quả thì trả "không đủ bằng chứng xác định nguyên nhân". Không tự suy "ưu tiên giờ
rẻ" khi trace không ghi.

### 3. WHAT-IF (counterfactual sandbox)

- Chỉ dùng thông tin `known_at(T)`; không biết trước xe đến / sự cố chưa công bố; ghi giả định persistence.
- Patch có schema, whitelist `revise_vehicle`, `site_limit`, `outage`; từ chối trường lạ / ID lạ; tối đa 5 thao tác.
- Chạy baseline và patched bằng **cùng engine, cùng `Algorithms` (ADR-011), cùng charging model, cùng seed, cùng sự kiện
  ngoài**; trả delta KPI, xe đổi trạng thái đúng hạn, `base_config_hash`, `sandbox_config_hash`, `state_version`.
- **`applied: false` luôn.** Sandbox không sửa booking, kế hoạch hay live session. Nâng nguồn vượt mức lắp đặt bắt buộc
  nhãn `hypothetical_infrastructure`.
- Cách cài đầu tiên: deep-copy config + `HybridSimulator` mới + replay từ đầu (như R&D). Chỉ làm checkpoint / fork sâu
  hơn nếu số đo latency hoặc tính đúng đòi hỏi.

### 4. AI-1 và vòng đời đề nghị

`detect_conflicts` → liệt kê có giới hạn các thay đổi ứng viên → mỗi ứng viên chạy counterfactual + Guard + kiểm ảnh
hưởng xe khác → hiện phương án khả thi kèm giả định và cái giá nhượng bộ → người có quyền đồng ý / từ chối → kiểm
`state_version` và mô phỏng lại ngay trước khi apply → ghi `vehicle_revisions` hiệu lực từ T → audit + thông báo.

Trạng thái: `PROPOSED → APPROVED | REJECTED | EXPIRED → APPLIED | APPLY_FAILED`, có TTL (mặc định 15 phút, tham số
YAML), idempotency, kiểm chủ sở hữu. Không apply đề nghị stale hoặc chưa được đồng ý. Không có phương án khả thi thì
nói rõ, không bịa.

Ba mức can thiệp: (1) đổi setpoint trong vùng không vi phạm SLA → engine tự làm dưới Guard; (2) đổi target / deadline
đã cam kết → phải có đồng ý của cư dân; (3) sự cố / khẩn cấp / override → Operator duyệt theo luật cấu hình; bảo vệ
khẩn cấp chạy trước, thương lượng sau. LLM không vượt cấp nào.

KPI phải báo cả **SLA theo cam kết gốc** và **SLA sau thương lượng**; không đổi SLA gốc thành SLA mới để báo cải thiện.

### 5. Grounding gate

Kiểm số trong câu LLM có trong `facts` là **chưa đủ**. Gate kiểm thêm: đúng xe / đối tượng, đúng thời điểm, đúng đơn
vị, và quan hệ nhân quả khớp `reason_code`. Không qua thì dùng template hoặc "không đủ bằng chứng".

### 6. Phân quyền (sửa ADR-006)

Copilot có cho cả hai vai trò, quyền lấy từ JWT, không từ LLM. Resident: chỉ hỏi WHY về xe mình, chỉ patch
`revise_vehicle` của xe mình, chỉ thấy số tổng hợp không định danh về xe khác. Operator: WHY cấp bãi, patch
`site_limit` / `outage`, duyệt đề nghị mức 3. Lọc theo vai trò ở REST, WebSocket và evidence của Copilot. `/chat` hiện
tại giữ cho resident; thêm endpoint Copilot theo vai trò (ví dụ `/api/v1/copilot/*`) khi làm task tương ứng.

### 7. Job nền (sửa ADR-007)

`replan` vẫn chạy đồng bộ trong request (MT5 p95 ≤ 2 s, [MỤC TIÊU]). Sinh phương án AI-1 và WHAT-IF nặng chạy **job nền
trong cùng process** (một worker, ADR-007), có `job_id`, trạng thái, kết quả từng phần; ưu tiên: bảo vệ khẩn cấp >
phương án AI-1 > WHAT-IF theo yêu cầu.

### 8. Persistence và lỗi (sửa ADR-005, ADR-008)

- Bảng mới qua Alembic: `proposals` (vòng đời §4), `consents` (ai đồng ý gì, lúc nào), `vehicle_revisions`. Audit dùng
  `decision_log` hiện có. `approvals` hiện có giữ cho phê duyệt của Operator.
- Mã lỗi thêm: `stale_state_version` (409), `patch_not_allowed` (403 — patch ngoài quyền), `job_pending` (202 cho kết
  quả chưa xong). Mã đã có giữ nguyên (`proposal_expired`, `llm_unavailable`…). Idempotency áp cho approve / reject /
  apply revision như `POST /resident/bookings`.

## Bằng chứng

- Thiết kế dựa trên prototype R&D (`D:\VIN\simulation\experimental\{core,ai1_negotiation,ai4_copilot}`), **chưa merge**.
- Chạy lại 21/11 trên R&D @ `1736d41` ([`RD_RERUN.md`](../../eval/evidence/2026-11-21/RD_RERUN.md) §4, §7):
  - AI-1, 15 xung đột / 45 quyết định: sinh phương án **p50 5,93 s, max 10,47 s**. Đây là căn cứ cho §7 (job nền).
    Số 10,2 / 26,3 s trong báo cáo R&D cũ không tái lập; khả năng là bản trước khi song song hoá, nhưng **chưa kiểm
    chứng**.
  - AI-1, SLA sau thương lượng: 0 % (chỉ thông báo) / 26,7 % (luật cố định) / 55,6 % (đề nghị có HITL). Hồ sơ đồng ý
    là **synthetic**, nên đây không phải bằng chứng hành vi cư dân thật.
  - AI-4: WHAT-IF p50 ≈ 1,0 s; WHY p50 0,4 ms; các bộ kiểm WHY của R&D đều đạt 1,0 trên kịch bản R&D. LLM: BLOCKED
    (chưa có key).
- Kịch bản phải có test trước khi gọi là xong (master context §11.3): normal load không bịa xung đột; site cap drop;
  DC queue pressure; cabinet outage; independent supply; không có phương án khả thi; đề nghị stale; nhiều WHAT-IF không
  ảnh hưởng nhau và không sửa live; prompt injection / sai vai trò bị chặn ở backend.

## Hệ quả

- `src/models` thêm `DecisionTrace`, `WhyAnswer`, `WhatIfPatch`, `WhatIfResult`, `Proposal`, `VehicleRevision`;
  OpenAPI + `npm run gen:api` (ADR-009).
- `tests/test_architecture.py`: Copilot service chỉ đọc qua `SimulatorGateway`; không module nào ngoài
  `apply_approved_revision` ghi `vehicle_revisions`.
- Eval MVP-4 đo: faithfulness theo từng claim, tỉ lệ khẳng định không có căn cứ, độ đúng patch, phương án khả thi,
  latency WHAT-IF (tính cả replay) tách khỏi latency solver.
