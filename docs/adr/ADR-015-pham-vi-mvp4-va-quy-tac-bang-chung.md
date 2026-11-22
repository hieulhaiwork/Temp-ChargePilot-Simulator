# ADR-015: Phạm vi MVP-4, các hạng mục hoãn, và quy tắc bằng chứng cho mọi con số

- Trạng thái: Proposed — chờ nhóm duyệt
- Ngày: 2026-11-21
- Liên quan: ADR-010…014; plan 30 §6 (Forecast F6) bị thay một phần
- Nguồn: RESEARCH SC-16 ("WHERE AI", bốn hướng AI, kết luận chọn AI-4 + AI-1); master context v1.0 §8, §11, §13

## Bối cảnh

Skeleton (PRD v0.2) coi dự báo lúc rút đầu nối F6 (LightGBM) là "phần chứng minh giá trị AI chính", và có
`src/forecast/`. RESEARCH SC-16 đánh giá bốn hướng AI và chốt: **tập trung AI-4, AI-1 phát triển trên nền AI-4**; AI-2
(ML anomaly) kém baseline ngưỡng; AI-3 (học lập lịch) kém thuật toán tối ưu. Master context hoãn forecasting trong sprint
20–26/11. Bản nháp PRD v0.3 lại đưa F12 dự báo hành vi, F13 mô hình mức linh hoạt, F14 chiếm cổng, HOW-TO lên Must —
lệch với hai nguồn trên.

Đồng thời, nhóm yêu cầu: **mọi thay đổi phải có benchmark / đánh giá thật, không bịa số để pass test.**

## Quyết định

### 1. Phạm vi MVP-4 (sprint 20–26/11)

| Hạng mục | Quyết định |
|---|---|
| AI-4 WHY + WHAT-IF | **Làm** — tính năng chính (ADR-014) |
| AI-1 phát hiện xung đột + thương lượng + HITL | **Làm** — vertical slice bổ trợ (ADR-014) |
| LLM intake (câu → phiếu có schema) | **Làm**, có chế độ offline (ADR-013) |
| HOW-TO tối ưu đa chiều / "tối thiểu bao nhiêu" | **HOÃN** — binary search giả định đơn điệu chưa chứng minh; dùng phương án AI-1 đã kiểm chứng làm gợi ý có điều kiện |
| Câu hỏi mở nhiều bước (FR30a) | **HOÃN** |
| F6 / F12 dự báo giờ rời, đỗ quá giờ, không đến | **HOÃN** — optimizer dùng giờ rời khai báo + giả định persistence ghi rõ |
| F13 mô hình mức linh hoạt học được | **HOÃN** — acceptance chỉ có hồ sơ synthetic; AI-1 hỏi theo thứ tự thay đổi nhỏ nhất bằng luật |
| F14 chiếm cổng sau sạc | **Should**, chỉ trạng thái `FINISHED_PLUGGED` (simulator đã mô phỏng); nhắc dời xe / phí → HOÃN |
| AI-2 anomaly | ML **HOÃN**; luật advisory là Could, không thay Guard |
| AI-3 learned scheduling | **Không chọn** cho MVP; lưu negative finding |
| RAG, vector DB, RL, multi-agent, OCPP thật, thanh toán, nhiều bãi | **Ngoài phạm vi** |

`src/forecast/` giữ nguyên code và test hiện có (không xoá), nhưng không trên critical path; `StationRuntime.forecaster`
cho phép `None`. Hoãn không có nghĩa là hướng đó vô giá trị vĩnh viễn.

### 2. Quy tắc bằng chứng

1. Mọi con số trong ADR, PRD, báo cáo, slide phải trỏ tới một file trong `eval/evidence/<ngày>/` ghi: lệnh chạy, branch,
   commit, môi trường (OS, CPU, Python, SciPy, EV2Gym…), scenario, seed, cấu hình thuật toán, output thô.
2. Số chưa chạy lại được mang nhãn **[R&D — CHƯA XÁC MINH]** kèm nguồn, và không làm căn cứ chính cho quyết định.
3. Mục tiêu ghi **[MỤC TIÊU]**; giả định mô phỏng ghi **[GIẢ ĐỊNH]**. Synthetic không được trình bày như thực địa.
4. So sánh chính sách: cùng scenario / seed / physics / charging model / định nghĩa metric, chỉ đổi chính sách. Báo cả
   thắng, hoà, thua. Fixture không phân biệt được (ví dụ `mvp1`: FIFO và EDF đều 9/9) không dùng để chứng minh tối ưu.
5. Không sửa test, ngưỡng hay dữ liệu để kết quả "đẹp". Test fail thì ghi nguyên văn và sửa nguyên nhân.
6. Latency: tách `decision_ms_p95` (solver / coordinator / Guard) khỏi latency WHAT-IF (gồm replay) và latency LLM / API.

## Bằng chứng

- 21/11: simulator v1.2 và golden `mvp1` (ADR-010, ADR-011); skeleton @ `8f6f08a` ruff sạch, pytest 247 passed /
  94 skipped. Log: `eval/evidence/2026-11-21/`.
- Chạy lại R&D @ `1736d41` ([`RD_RERUN.md`](../../eval/evidence/2026-11-21/RD_RERUN.md)):
  - **AI-2:** F1 của luật ngưỡng 0,8019; LOF 0,8013; GBDT 0,7833; IsolationForest 0,5385. ML không hơn luật, nên số
    liệu ủng hộ việc hoãn AI-2 ML.
  - **AI-3:** SLA baseline / learner / teacher = 0,7639 / 0,7546 / 0,8495 (8 cổng); 0,8148 / 0,7716 / 0,8734 (16);
    0,8441 / 0,7839 / 0,9167 (48). Learner kém baseline ở cả ba quy mô, nên số liệu ủng hộ việc không chọn AI-3.
  - **Benchmark MVP-2/3:** 225 run khớp 0 sai lệch với output R&D gốc. Mỗi ô chỉ có 5 seed và khoảng dao động chồng
    nhau, nên chưa đủ để chốt coordinator. Việc chọn `fixed_share` / `dynamic_slack` / `joint_lp` cho MVP-3 là
    **câu hỏi mở**.
  - **Latency:** số "p95 ≤ 14 ms ở 8 cổng / ≤ 92 ms ở 100 cổng" của R&D **không tái lập** với `joint_lp` (đo lại được
    19,93 / 125,8 ms). Không trích lại hai số đó.
- F12 / F13 / HOW-TO bị hoãn vì phạm vi và giả định chưa chứng minh (đơn điệu, hồ sơ synthetic), không phải vì có số
  đo cho thấy chúng kém.

## Hệ quả

- Plan 30 §6 (F6) và các task T2.3 forecast chuyển sang backlog sau sprint.
- `requirements-runtime.txt`: không bật `lightgbm` trong sprint.
- Eval MVP-4 so sánh tối thiểu ba nhánh: dashboard + template; LLM không tool (nếu có key); LLM + tool + evidence.
- Gate sprint (master context §13): Contract freeze 20/11 · Integration Gate 1 22/11 · MVP-3 + AI-4 Gate 24/11 · HITL
  E2E Gate 25/11 · Release Candidate 26/11. Gate chỉ được đánh dấu đạt khi có test / evidence.
