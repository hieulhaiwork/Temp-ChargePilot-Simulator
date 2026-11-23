"""Bộ tối ưu — trụ 2: "Bộ tối ưu tính phương án". Một nơi sở hữu thuật toán điều phối / lập lịch (ADR-019).

Gói này KHÔNG import gì lúc nạp: simulator standalone import các gói con thuần (không Pydantic / FastAPI / DB).

    dispatch/       FCFS/FIFO, EDF, LLF (gán xe chờ → cổng trống)        — code gốc simulator MVP-1/2/3
    zones/          AC 2-stage LP, DC rolling LP, equal share, deadline first — code gốc simulator
    coordination/   Fixed budget / Fixed share, Dynamic slack             — code gốc simulator
    registry.py     MỘT registry thuật toán + bảng policy B0/M2b/M3a/M3b

LP backend A–D (base, baselines, mpc, lp_model, horizon, assignment, strategies) đã xoá ở Phase 3 (ADR-019,
docs/refactor/DELETION_MANIFEST.md): quote / booking / lịch chạy thật cùng dùng Planning Core của kernel.

Ranh giới (tests/test_architecture.py): không import simulator, guard, services, agents, api, db, forecast.
"""
