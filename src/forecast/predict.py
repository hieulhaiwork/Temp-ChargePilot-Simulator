"""DepartureForecaster — dự báo lúc xe RÚT đầu nối cho một phiên đang cắm.

Ba cài đặt, so với nhau theo MAE (MT7):
  - DeclaredTimeForecaster     mốc 1: giờ cư dân khai báo
  - HistoricalMedianForecaster mốc 2: trung vị thời gian đỗ lịch sử
  - LightGBMForecaster         mô hình chính (artifact ở settings.forecast_model_path)

Chỉ chiến lược C của bộ tối ưu dùng kết quả này, và chỉ để ước lượng lúc đầu nối
được giải phóng — KHÔNG nới deadline (FR9).

Owner: TV2. Task: T2.3. Trạng thái: STUB.
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from src.models.charging import ChargingSession


class DepartureForecaster(Protocol):
    def predict(self, session: ChargingSession, history: Sequence[ChargingSession]) -> datetime: ...


class DeclaredTimeForecaster:
    def predict(self, session: ChargingSession, history: Sequence[ChargingSession]) -> datetime:
        raise NotImplementedError("[T2.3] DeclaredTimeForecaster — dùng declared_departure (mốc 1)")


class HistoricalMedianForecaster:
    def predict(self, session: ChargingSession, history: Sequence[ChargingSession]) -> datetime:
        raise NotImplementedError("[T2.3] HistoricalMedianForecaster — trung vị dwell của user/mô hình chung (mốc 2)")


class LightGBMForecaster:
    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path  # nạp lười ở predict() để app khởi động được khi chưa có artifact

    def predict(self, session: ChargingSession, history: Sequence[ChargingSession]) -> datetime:
        raise NotImplementedError("[T2.3] LightGBMForecaster — nạp artifact + build_features + predict")
