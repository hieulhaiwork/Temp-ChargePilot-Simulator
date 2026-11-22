# Evidence 2026-11-21 — chạy lại để làm căn cứ cho ADR-010…015 và PRD v0.4

Mọi số trong thư mục này là **output thật** của lệnh ghi ở dòng đầu mỗi file `raw/*.txt`. Không có số nào được gõ tay
hay chỉnh sửa. Kết quả fail cũng được giữ nguyên.

## Môi trường

| Mục | Giá trị |
|---|---|
| Máy | Windows 11 (10.0.26300), AMD64 Family 25 Model 80, 12 logical CPU |
| Python | 3.12.10 (`D:\VIN\simulation\.venv-rd` cho simulator; `.venv` của repo cho skeleton) |
| EV2Gym | 2.0.0 |
| Giờ chạy | 2026-11-20T18:34Z (= 21/11 01:34 giờ VN) |

## 1. Simulator v1.2 — `feature/simulator` @ `d15871a` (worktree chỉ đọc `D:\VIN\P-019-simulator-ref`)

| Lệnh | Kết quả | File |
|---|---|---|
| `python -m pytest src/simulator/tests -q` (encoding mặc định cp1258) | **109 passed, 3 failed** — `UnicodeDecodeError` ở 3 test CLI đọc file không ghi `encoding` | `raw/sim-v12-pytest.txt` |
| `PYTHONUTF8=1 python -m pytest src/simulator/tests -q` | **112 passed** | `raw/sim-v12-pytest-utf8.txt` |
| `python -m src.simulator.run --scenario mvp1` | xem bảng KPI | `raw/sim-v12-run-mvp1.txt` |
| `... --scenario mvp1 --algorithms src/simulator/config/algorithms_edf_demo.json` | xem bảng KPI | `raw/sim-v12-run-mvp1-edf.txt` |
| `... --scenario vinfast_dc_2port_120kw` | xem bảng KPI | `raw/sim-v12-run-vinfast_dc_2port_120kw.txt` |

KPI trích từ `report.json` của từng run (`raw/sim-v12-kpis.txt`):

| Kịch bản | Đúng hạn | Wait mean / p95 (phút, started only) | Peak lưới (kW) | Điện lưới / pin (kWh) | Còn thiếu (kWh) | Rejected / applied violation |
|---|---|---|---|---|---|---|
| `mvp1` FIFO/FCFS (lưới 106) | 9/9 | 51,11 / 135 | 105,263 | 239,527 / 223,000 | 0 | 0 / 0 |
| `mvp1` + EDF demo | 9/9 | 54,56 / 135 | 86,316 | 239,527 / 223,000 | 0 | 0 / 0 |
| `vinfast_dc_2port_120kw` (lưới 150, DC budget 120) | 8/9 | 44,78 / 135 | 149,474 | 219,099 / 203,982 | 26,189 | 0 / 0 |

Nhận xét chỉ rút từ số trên:

- Số `mvp1` khớp số bàn giao trong master context §6 (9/9; 51,11 / 135; 105,263; 239,527; 223,000).
- Master context ghi "112 simulator tests pass": đúng khi chạy với `PYTHONUTF8=1`; với encoding mặc định của Windows thì
  3 test fail. Đây là lỗi của test, cần sửa trước khi merge.
- `mvp1` không phân biệt FIFO với EDF về số xe đúng hạn (cùng 9/9). EDF có wait mean cao hơn (54,56 so với 51,11) và
  peak lưới thấp hơn (86,316 so với 105,263) trên đúng fixture này. Không suy rộng ra kịch bản khác.

## 2. Skeleton — `feature/research-sc16-alignment` @ `8f6f08a` (= `feature/chargepilot-skeleton`)

| Lệnh | Kết quả | File |
|---|---|---|
| `ruff check src/ tests/` | All checks passed | `raw/skeleton-baseline-check.txt` |
| `ruff format --check src/ tests/` | 128 files already formatted | như trên |
| `pytest tests/ -q` | **247 passed, 94 skipped** | như trên |

## 3. R&D (nhánh `experiment/claude-chargepilot-fullstack-ai`)

Chạy lại bởi agent phụ; kết quả và bảng đối chiếu "số đã báo vs số chạy lại" ở [`RD_RERUN.md`](RD_RERUN.md).
