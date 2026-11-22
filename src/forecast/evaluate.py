"""Đánh giá dự báo (MT7) — MAE theo phút + phân tích ca thất bại (T2.3, T4.1).

Báo cáo tối thiểu: MAE tổng, MAE theo nhóm user nhiều/ít lịch sử, theo khung giờ cắm;
so 3 forecaster trong predict.py trên CÙNG tập test chia theo thời gian.

Owner: TV2. Trạng thái: STUB.
"""

from collections.abc import Sequence

from src.forecast.predict import DepartureForecaster
from src.models.charging import ChargingSession


def evaluate(
    forecaster: DepartureForecaster, test: Sequence[ChargingSession], history: Sequence[ChargingSession]
) -> dict[str, float]:
    """Trả {"mae_minutes": ..., "mae_minutes_low_history": ..., ...} để ghi vào eval/results/."""
    raise NotImplementedError("[T2.3] evaluate — MAE + chia nhóm cho phân tích ca thất bại")
