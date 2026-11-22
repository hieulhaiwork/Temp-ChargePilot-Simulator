# RD_RERUN — chạy lại R&D ngày 21/11 và đối chiếu với số đã báo

- Repo R&D: `D:\VIN\simulation`, branch `experiment/claude-chargepilot-fullstack-ai` @ `1736d41` (**chưa merge**, chỉ đọc).
- Môi trường: Windows 11 10.0.26300, AMD64 Family 25 Model 80 (12 logical CPU), Python 3.12.10, SciPy 1.18.1 (HiGHS),
  scikit-learn 1.9.1, EV2Gym 2.0.0, `PYTHONUTF8=1`. Cùng máy với lần chạy R&D gốc (19/11, commit `c91476e`).
- Ai chạy: test + benchmark MVP + latency + AI-1 do agent phụ (claude2) chạy. Agent này dừng vì hết hạn mức trước khi
  viết file này. AI-2 / AI-3 / AI-4 do agent chính chạy tiếp. Mọi số dưới đây lấy từ `raw/rd-*.txt`. Không có số nào
  được gõ tay.
- `raw/rd-original-outputs-2026-11-19/` là **bản sao output gốc của R&D** (19/11), dùng để so sánh. Đây **không** phải
  kết quả chạy lại.
- Khi chạy lại, AI-2 ghi đè `experimental/artifacts/ai2_models.joblib`. File mới có SHA256 trùng bản gốc
  (`3f8fda02…`). `git status` của repo R&D vẫn sạch.

## 1. Test

| Bộ test | Kết quả | File |
|---|---|---|
| `experimental/tests` | 49 passed (175 s) | `raw/rd-pytest-experimental.txt` |
| `src/simulator/tests` + `ev2gym_smoke.py` (bản R&D) | 154 passed | `raw/rd-pytest-simulator.txt` |
| `test_rnd_mvp23.py` + `test_golden_regression.py` | 42 passed. Golden `mvp1`, `mvp1_edf_demo`, `vinfast_dc_2port_120kw` khớp v1.2 | `raw/rd-pytest-rnd-mvp23-golden.txt` |

## 2. Benchmark MVP-2/3 (`--suite mvp --seeds 0 1 2 3 4`): 225 run

So với output gốc 19/11 (`raw/rd-bench-mvp-compare.txt`): 225/225 dòng có mặt, **0 sai lệch ở mọi trường tất định**
(SLA, shortfall, wait, cost, fairness, peak). 0 vi phạm, 0 lệnh bị chặn. Chỉ `decision_ms_p95` khác, vì đây là thời gian
đo trên máy.

SLA trung bình 5 seed, [min–max] (`raw/rd-bench-mvp.txt`):

| Họ kịch bản | Baseline B0 | Tốt nhất khi chạy lại | `dynamic_slack` (M3b) | `joint_lp` (M3c) | Ghi chú |
|---|---|---|---|---|---|
| `evening_mixed` | 0,8667 | **0,9444** M3b | 0,9444 | 0,9222 | Khớp số đã báo 0,867 → 0,944 |
| `dc_queue_pressure` | 0,6667 | **0,7444** M2d (LLF + DC LP) = M3a | 0,7111 | 0,7222 | EDF **thua** baseline (0,6333) |
| `site_drop` | 0,7667 | **0,9222** M3c | 0,8889 | 0,9222 | Khớp 0,767 → 0,922 |
| `dc_outage` | 0,9182 | 0,9272 (mọi chính sách LP) | 0,9272 | 0,9272 | Gần như hoà |
| `independent_supply` | 0,8556 | 0,8778 | 0,8778 | 0,8778 | Khớp 0,856 → ~0,878 |

**Lưu ý thống kê:** mỗi ô chỉ có 5 seed và khoảng [min–max] của các chính sách chồng nhau nhiều. Chưa có kiểm định ý
nghĩa thống kê. Các chênh lệch nhỏ (≤ 0,03) chưa đủ để nói chính sách nào tốt hơn.

## 3. Latency (`--suite latency --seeds 0 1 2 --sizes 4 8 16 50 100`): 45 run

So với output gốc (`raw/rd-bench-latency-compare.txt`): 45/45 dòng, 0 sai lệch ở các trường tất định. Size `50` sinh
**49** cổng.

| Cổng | B0 SLA | M3b SLA | M3c SLA | p95 quyết định M3b (ms) | p95 M3c (ms), chạy lại | p95 M3c (ms), gốc 19/11 |
|---|---|---|---|---|---|---|
| 4 | 0,7408 | 0,8148 | 0,7778 | 6,26 | 9,73 | 8,43 |
| 8 | 0,7778 | 0,8148 | 0,7778 | 6,95 | **19,93** | 13,59 |
| 16 | 0,8704 | 0,8704 | 0,8333 | 18,55 | 46,29 | 21,44 |
| 49 | 0,8532 | 0,8532 | 0,8349 | 27,00 | 62,14 | 44,36 |
| 100 | 0,8415 | 0,8415 | 0,8074 | 40,32 | **125,8** | 91,41 |

- **Không tái lập được:** R&D báo "p95 ≤ 14 ms ở 8 cổng, ≤ 92 ms ở 100 cổng". Với `joint_lp`, lần chạy lại cho 19,93 ms
  và 125,8 ms, tức là vượt cả hai mốc. Với `dynamic_slack` thì vẫn dưới hai mốc (6,95 ms và 40,32 ms). Mọi giá trị đều
  ≪ 2 s ([MỤC TIÊU] MT5), nhưng latency dao động theo tải máy, nên không được trích một con số cố định như kết quả.
- `joint_lp` **thua baseline** ở 16 / 49 / 100 cổng (khớp negative finding của R&D).
- `dynamic_slack` chỉ hơn baseline ở 4 và 8 cổng. Từ 16 cổng trở lên thì **hoà** baseline.

## 4. AI-1 (`experimental.ai1_negotiation.evaluate`), `raw/rd-ai1-eval.txt`

| Chỉ số | Đã báo (FEATURE_COMPARISON) | Chạy lại | Khớp? |
|---|---|---|---|
| Quyết định / xung đột | 45 / 15 | 45 / 15 | ✔ |
| SLA sau thương lượng: A notify / B luật / C đề nghị | 0 % / 26,7 % / 55,6 % | 0,0 / 0,267 / 0,556 | ✔ |
| C theo hồ sơ: time_flexible / soc_flexible / rigid | 100 / 66,7 / 0 % | 1,0 / 0,667 / 0,0 | ✔ |
| B làm xe khác trễ | 2 | 2 | ✔ |
| Xung đột không có phương án / phương án không có căn cứ | 0 / 0 | 0 / 0 | ✔ |
| Latency sinh phương án p50 / max | 10,2 s / 26,3 s | **5,93 s / 10,47 s** | ✘ lệch |

- Latency lệch có thể vì commit `1736d41` đã song song hoá việc đánh giá phương án ("process pool"), còn số 10,2 / 26,3 s
  là của bản trước. **Chưa kiểm chứng nguyên nhân.** Kết luận chắc chắn được: latency vẫn vài giây tới hơn 10 s, quá dài
  cho một request đồng bộ. Điều này ủng hộ quyết định đưa AI-1 sang job nền (ADR-014 §7).
- Giới hạn của đo lường: 55,6 % lấy từ **hồ sơ người dùng synthetic**, và `C_sla_met` suy từ phương án khả thi được
  chọn. Đây **không** phải bằng chứng cư dân thật sẽ đồng ý. LLM live: `BLOCKED` (không có API key); chỉ có đường template.

## 5. AI-2 (`experimental.ai2_anomaly.experiment`), `raw/rd-ai2_anomaly.txt`

| Phương pháp | Precision | Recall | F1 | Báo động giả / cổng·giờ |
|---|---|---|---|---|
| Luật ngưỡng (residual) | 0,8836 | 0,7340 | **0,8019** | 0,701 |
| LOF novelty | 0,9239 | 0,7074 | **0,8013** | 0,422 |
| GBDT có giám sát | 0,9256 | 0,6789 | 0,7833 | 0,396 |
| Luật OR GBDT | 0,8384 | 0,7657 | 0,8004 | 1,07 |
| IsolationForest | 0,7092 | 0,4340 | 0,5385 | 1,29 |

Khớp số đã báo (luật ~0,802, LOF ~0,801, GBDT ~0,783, IF ~0,539). ML **không** hơn luật về F1, nên số liệu ủng hộ việc
hoãn AI-2 ML (ADR-015). Dữ liệu là fault injector synthetic.

## 6. AI-3 (`experimental.ai3_learning.experiment`), `raw/rd-ai3_learning.txt`, `raw/rd-ai3_results-rerun.json`

| Quy mô (connectors_scale → cổng) | Baseline | Learner | Teacher (LP MPC) |
|---|---|---|---|
| 1 → 8 | 0,7639 | 0,7546 | 0,8495 |
| 2 → 16 | 0,8148 | 0,7716 | 0,8734 |
| 6 → 48 | 0,8441 | 0,7839 | 0,9167 |

Khớp số đã báo (0,764 / 0,755 / 0,850; 0,815 / 0,772 / 0,873; 0,844 / 0,784 / 0,917). Ở cả ba quy mô, learner kém cả
baseline, nên số liệu ủng hộ việc không chọn AI-3 (ADR-015).

## 7. AI-4 (`experimental.ai4_copilot.evaluate`), `raw/rd-ai4_copilot.txt`

- Kiểm WHY: site_claim 38/38, queue_claim 57/57, outage_claim 55/55, grounded 57/57, actual_kw 57/57 (đều đạt tỉ lệ 1,0).
- Gọi tool: what_if 40/40 ok, p50 1000,2 ms; why 10/10, p50 0,4 ms; how_to 10/10, p50 512,35 ms.
- So sánh với nhánh LLM: **BLOCKED**, vì không có key. Chỉ đánh giá `rule_parser + templates`.
- Giới hạn của đo lường: bộ kiểm do chính R&D viết, trên kịch bản R&D. Tỉ lệ 1,0 **không** có nghĩa là không hallucinate
  ngoài tập test, và chưa đo được giá trị của LLM.

## 8. Kết luận cho các quyết định

| Quyết định | Số chạy lại có ủng hộ không |
|---|---|
| Hoãn AI-2 ML (ADR-015) | **Có.** ML không hơn luật về F1 |
| Không chọn AI-3 (ADR-015) | **Có.** Learner < baseline ở 8 / 16 / 48 cổng |
| AI-1 chạy job nền (ADR-014 §7) | **Có.** Sinh phương án p50 5,93 s, max 10,47 s |
| Mặc định `dynamic_slack` thay vì `joint_lp` | **Một phần.** `dynamic_slack` nhanh hơn, không thua baseline ở mọi quy mô và họ kịch bản đã thử. Nhưng nó **không** tốt nhất ở `dc_queue_pressure` (0,711 so với 0,744) và `site_drop` (0,889 so với 0,922 của `joint_lp`), và chỉ hoà baseline từ 16 cổng. Chọn coordinator cho MVP-3 vẫn là **câu hỏi mở**, cần nhóm chốt dựa trên bảng này |
| `mvp1` không đủ phân biệt chính sách | **Có.** Xem `README.md` §1 |
| Mục tiêu p95 ≤ 2 s cho bước quyết định | Mọi lần đo < 0,13 s. Đây vẫn là số trên máy dev, chưa đo trên máy triển khai |
| Số latency "≤ 14 / ≤ 92 ms" của R&D | **Không tái lập được** với `joint_lp`. Không trích lại hai số này |
