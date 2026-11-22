# Bằng chứng 2026-11-22 — backend chạy thật (LiveStation + optimizer A–D + Guard)

Môi trường: Windows 11, Python 3.12.10, scipy 1.18.1, numpy 2.5.5. Branch `feature/chargepilot-skeleton`, working tree
chưa commit (đợt hoàn thiện backend).

## 1. Benchmark A–D

Lệnh (chạy lại được, cùng seed → cùng số):

```bash
python eval/run_benchmark.py --scenarios hybrid_evening,hybrid_power_drop --seeds 1,2,3,4,5
```

File gốc: [`raw/benchmark.json`](raw/benchmark.json), [`raw/benchmark.md`](raw/benchmark.md). Trung bình 5 seed:

| Kịch bản | Chiến lược | Đúng hạn | Điện thiếu (kWh) | Chi phí (VND) | Vượt giới hạn | Tính lại p95 (s) |
|---|---|---|---|---|---|---|
| hybrid_evening | A_fcfs | 50,1% | 301,9 | 840.367 | 0 | 0,003 |
| hybrid_evening | A_edf | 52,4% | 283,0 | 878.838 | 0 | 0,003 |
| hybrid_evening | B | 52,4% | 284,6 | 753.849 | 0 | 0,019 |
| hybrid_evening | C | 52,4% | 284,6 | 753.849 | 0 | 0,019 |
| hybrid_evening | D | 52,4% | 284,6 | 756.533 | 0 | 0,021 |
| hybrid_power_drop | A_fcfs | 45,0% | 324,3 | 763.871 | 0 | 0,003 |
| hybrid_power_drop | A_edf | 46,1% | 304,1 | 799.300 | 0 | 0,003 |
| hybrid_power_drop | B | 42,2% | 308,0 | 701.336 | 0 | 0,018 |
| hybrid_power_drop | C | 42,2% | 308,0 | 701.336 | 0 | 0,018 |
| hybrid_power_drop | D | 42,2% | 308,9 | 699.212 | 0 | 0,021 |

Đọc đúng các số này:

- **[ĐÃ XÁC MINH 22/11]** 0 lần vượt giới hạn (MT4) ở mọi chiến lược, kể cả khi nguồn rớt 106 → 40 kW và DC-01-2 lỗi.
  Tính lại p95 ≤ 0,021 s (MT5 mục tiêu ≤ 2 s) trên 4 cổng.
- **[ĐÃ XÁC MINH 22/11]** B rẻ hơn EDF khoảng 12–14% tiền điện; tỉ lệ đúng hạn **không tốt hơn** EDF (bằng ở
  hybrid_evening, kém ~4 điểm ở hybrid_power_drop). Không được tuyên bố "tối ưu đúng hạn tốt hơn baseline".
- C = B vì F6 hoãn (ADR-015): không có dự báo. Không tuyên bố AI cải thiện.
- Tỉ lệ đúng hạn thấp (~50%) là do **kịch bản tổng hợp cố ý quá tải**: 16 xe, chỉ 2 cổng AC và xe AC giữ cổng tới
  giờ rời (F14). Đây không phải số đo trạm thật; mục tiêu AC3 "≥ 95%" chưa được kiểm trên kịch bản khả thi.
- Simulator là `LiveStation` (ADR-016) — không so trực tiếp với số HybridSimulator ở `../2026-11-21/RD_RERUN.md`.

## 2. Lỗi native của HiGHS khi đổi thread (đã sửa)

[`raw/segfault-before-fix.log`](raw/segfault-before-fix.log): trước khi sửa, benchmark chạy LP qua `asyncio.to_thread`
(mỗi lần một thread khác) và process **Segmentation fault** sau 14 lần chạy. Cùng khối lượng chạy trên một thread cố
định thì không lỗi. Sửa: `src/services/solver.py` gom mọi lần giải LP về một worker thread; sau sửa, benchmark đầy đủ
(50 lần chạy) chạy hai lần liên tiếp đều exit 0.

## 3. Check

Kết quả check cuối (ruff, pytest, docs, OpenAPI, eval, frontend, Docker, Postgres) ghi ở báo cáo phiên; xem
`raw/final-check.txt` nếu có.
