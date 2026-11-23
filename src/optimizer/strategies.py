"""Chiến lược backend A–D (LP / MPC / baseline cũ) — `get_scheduler` (ADR-019 Phase 2: tách khỏi `__init__.py`).

Vì sao tách: simulator standalone import `src.optimizer.dispatch|zones|coordination|registry`; nếu `__init__.py` của
gói import backend LP (Pydantic `StrategyName`, `PlanningContext`…) thì standalone phải kéo theo stack backend.

    base.py        PlanningContext + Scheduler Protocol
    baselines.py   A (FCFS, EDF) và D (oracle)
    mpc.py         B / C — MPC cửa sổ trượt
    lp_model.py    bài LP của một bước MPC (công thức ở docstring)
    assignment.py  gán đầu nối + hàng đợi (FR7)

Quote / booking (`services/charging_service._what_if`) vẫn dùng `assignment` + `lp_model` — chưa xoá (ADR-019 §6).
"""

from src.models.charging import StrategyName
from src.optimizer.base import PlanningContext, Scheduler
from src.optimizer.baselines import EdfScheduler, FcfsScheduler, OracleScheduler
from src.optimizer.mpc import MpcScheduler

__all__ = ["PlanningContext", "Scheduler", "get_scheduler"]


def get_scheduler(name: StrategyName) -> Scheduler:
    """Một chiến lược cho mỗi mã A–D — dùng chung cho benchmark và màn S8."""
    match name:
        case StrategyName.FCFS:
            return FcfsScheduler()
        case StrategyName.EDF:
            return EdfScheduler()
        case StrategyName.OPT_NO_ML:
            return MpcScheduler(use_forecast=False)
        case StrategyName.OPT_ML:
            return MpcScheduler(use_forecast=True)
        case StrategyName.ORACLE:
            return OracleScheduler()
    raise ValueError(f"Chiến lược không hỗ trợ: {name!r}")
