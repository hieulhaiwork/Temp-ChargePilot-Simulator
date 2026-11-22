"""Bộ tối ưu (F2/F3) — trụ 2 của nguyên tắc: "Bộ tối ưu tính phương án". Owner: TV1.

Ranh giới (tests/test_architecture.py): optimizer là code THUẦN — nhận PlanningContext,
trả SchedulePlan. Không đọc file, không gọi API/LLM/DB, không gửi lệnh tới simulator.
Nhờ vậy benchmark A–D chạy cùng interface, cùng tập phiên, cùng biểu giá (PRD §8).

    base.py        PlanningContext + Scheduler Protocol
    baselines.py   A (FCFS, EDF) và D (oracle)
    mpc.py         B / C — MPC cửa sổ trượt
    lp_model.py    bài LP của một bước MPC (công thức ở docstring)
    assignment.py  gán đầu nối + hàng đợi (FR7)
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
