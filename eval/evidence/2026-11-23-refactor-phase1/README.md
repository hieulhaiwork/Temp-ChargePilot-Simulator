# Bằng chứng 2026-11-23 — refactor Unified Core, Phase 1 (tách hợp đồng, ADR-019)

**Mục đích:** chứng minh Phase 1 (di chuyển hợp đồng/DTO sang `src/models`, shim ở vị trí cũ) **không đổi hành vi**.
Đây không phải benchmark để so thuật toán. Không so với benchmark của cấu hình thời gian khác (ADR-019 §6).

## Môi trường và mốc

| Mục | Giá trị |
|---|---|
| Code đo | nhánh `feature/unified-core`: working tree của commit chứa README này (gốc `dad6e6b` + thay đổi Phase 1) |
| Baseline so sánh | `68692ee` (`origin/develop`), số đo Phase 0 ở `docs/refactor/raw/phase0/` |
| OS / Python | Windows 11 / 3.12.10 |
| ev2gym / numpy / scipy | 2.0.0 / 2.5.5 / 1.18.1 |
| Trạm backend | `HybridStation` (`STATION_ENGINE=hybrid`) |

## 1. Benchmark backend

Lệnh (ghi ra thư mục tạm, **không** ghi `eval/results/`):

```bash
python -c "import sys,pathlib; sys.path.insert(0,'eval'); import run_benchmark as rb; \
  rb.RESULTS_DIR=pathlib.Path('<tmp>'); sys.exit(rb.main(['--seeds','1,2,3,4,5']))"
```

- Scenario: `connector_failure`, `hybrid_evening`, `hybrid_power_drop`, `peak_evening`, `power_drop`.
- Chiến lược (policy): `A_fcfs`, `A_edf`, `B`, `C`, `D` (LP backend `src/optimizer/`); `B0`, `M2b`, `M3a`, `M3b`
  (thuật toán simulator, `src/services/hybrid_planner.py POLICIES`).
- Seed: 1, 2, 3, 4, 5 → 225 run.
- Kết quả: **225/225 run có KPI giống hệt baseline Phase 0** (mọi trường trừ `replan_p95_seconds`, vốn là thời gian
  tường); `notes` giống hệt.
- File: [`raw/backend_benchmark_seeds1-5.json`](raw/backend_benchmark_seeds1-5.json),
  [`raw/backend_benchmark_seeds1-5.md`](raw/backend_benchmark_seeds1-5.md), trung bình 5 seed:
  [`raw/backend_benchmark_seeds1-5_mean.md`](raw/backend_benchmark_seeds1-5_mean.md).

## 2. Simulator standalone (MVP-1/2/3)

So với raw evidence [`../2026-11-22/raw/sim-hardware/`](../2026-11-22/raw/sim-hardware/). Bằng chứng hợp lệ là
lần kiểm lại bằng `cmpbench.py` bản chặt: so mọi trường trừ thời gian tường, chỉ cho phép khác ở
`/metadata/{run_id,command,algorithms/*/config_source}`, lệch thì exit 1. Kết quả: 11/11 cặp OK (Phase 0 và Phase 1),
xem [`raw/recheck_strict_cmpbench.txt`](raw/recheck_strict_cmpbench.txt).
[`raw/golden_vs_evidence_2026-11-22.txt`](raw/golden_vs_evidence_2026-11-22.txt) là output của bản cũ. Bản cũ bỏ sót
`rejected_solver_plan_count` và luôn trả exit 0 (xem PHASE1_REPORT §9); file này chỉ giữ để tham khảo.

| Lệnh | Khác biệt KPI |
|---|---|
| `python -m src.simulator.benchmark_mvp3` | 0 |
| `python -m src.simulator.benchmark --vinfast-sensitivity` | 0 |
| `python -m src.simulator.run --scenario mvp1 --decision-trace` | 0 (chỉ `run_id`, `command`) |
| `python src/simulator/run.py --scenario …/mvp1.json` (script mode) | 0 (chỉ `run_id`, `command`) |
| `… --scenario mvp1 --algorithms …/algorithms_mvp3.json` | 0 (chỉ `run_id`, `command`, đường dẫn tuyệt đối) |
| `… --scenario vinfast_dc_2port_120kw` | 0 (chỉ `run_id`, `command`, đường dẫn tuyệt đối) |

Đường dẫn máy local trong log được thay bằng `<REPO>` / `<LOCAL_TMP>` / `<REPO_2026-11-22>`.

## 3. Test

`pytest`: 448 passed, 8 skipped. `pytest src/simulator/tests …`: 163 passed. Log: `docs/refactor/raw/phase1/`.
