"""Bộ tối ưu — trụ 2: "Bộ tối ưu tính phương án". Một nơi sở hữu thuật toán điều phối / lập lịch (ADR-019).

Gói này KHÔNG import gì lúc nạp: simulator standalone import các gói con thuần (không Pydantic / FastAPI / DB).

    dispatch/       FCFS/FIFO, EDF, LLF (gán xe chờ → cổng trống)        — code gốc simulator MVP-1/2/3
    zones/          AC 2-stage LP, DC rolling LP, equal share, deadline first — code gốc simulator
    coordination/   Fixed budget / Fixed share, Dynamic slack             — code gốc simulator
    registry.py     MỘT registry thuật toán + bảng policy B0/M2b/M3a/M3b
    strategies.py   chiến lược backend A–D (`get_scheduler`) — LP / MPC cũ, còn dùng cho quote/booking
    base.py, baselines.py, mpc.py, lp_model.py, horizon.py, assignment.py — LP backend cũ (chưa xoá)

Ranh giới (tests/test_architecture.py): không import simulator, guard, services, agents, api, db, forecast.
"""

_COMPAT = {"get_scheduler", "PlanningContext", "Scheduler"}


def __getattr__(name: str):
    """Tương thích tạm (ADR-019 Phase 2, xoá ở Phase 6): `from src.optimizer import get_scheduler` vẫn chạy.

    Chỉ nạp `strategies` (kéo theo Pydantic) khi có người truy cập đúng các tên cũ này, nên `import src.optimizer.dispatch`
    của simulator standalone không chạm stack backend.
    """
    if name in _COMPAT:
        from src.optimizer import strategies

        return getattr(strategies, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
