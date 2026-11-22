"""Hợp đồng của dự báo F6 (FR17, MT7) — docs/plan/30-ai.md §6. Trọng tâm: KHÔNG rò rỉ nhãn."""

import pytest

from src.forecast.features import FORBIDDEN_FEATURE_FIELDS
from src.models.charging import ChargingSession


def test_label_is_forbidden_as_feature():
    """FR17: giờ rút thật là NHÃN — không bao giờ là đầu vào."""
    assert "unplug_time" in FORBIDDEN_FEATURE_FIELDS


def test_forbidden_fields_exist_on_the_session_model():
    """Đổi tên field ở ChargingSession mà quên sửa danh sách cấm thì danh sách cấm thành vô nghĩa."""
    assert FORBIDDEN_FEATURE_FIELDS <= set(ChargingSession.model_fields)


@pytest.mark.skip(reason="[T2.3] features.build_features")
def test_unplug_time_never_leaks():
    """Given 1 phiên. When đổi unplug_time của CHÍNH phiên đó sang giá trị khác rồi build_features lại.

    Then hai bộ feature giống hệt nhau.
    """


@pytest.mark.skip(reason="[T2.3] features.build_features")
def test_history_only_uses_sessions_finished_before_plug_in():
    """Given history có phiên kết thúc SAU plug_in_time của phiên đang dự báo. Then phiên đó không ảnh hưởng feature."""


@pytest.mark.skip(reason="[T2.3] features.build_features — chốt ở T2.3 sau EDA")
def test_delivered_energy_is_not_a_feature_when_request_is_unknown():
    """Given bộ dữ liệu chỉ có kWh ĐÃ NẠP (biết sau khi phiên kết thúc). Then energy_kwh không nằm trong feature."""


@pytest.mark.skip(reason="[T2.3] features.build_features")
def test_user_with_little_history_falls_back_to_general_model():
    """FR17. Given user có < 5 phiên. Then feature lịch sử để trống + cờ has_history=0, không raise."""


@pytest.mark.skip(reason="[T2.3] datasets.temporal_split")
def test_split_is_temporal_not_random():
    """PRD §8. Given phiên trải 12 tháng. When temporal_split(test_from=T). Then max(train.plug_in) < T ≤ min(test.plug_in)."""


@pytest.mark.skip(reason="[T2.3] predict.*Forecaster")
def test_three_forecasters_share_one_interface():
    """MT7. Given cùng (session, history). Then cả 3 forecaster trả datetime có múi giờ ≥ plug_in_time."""


@pytest.mark.skip(reason="[T2.3] predict.LightGBMForecaster")
def test_missing_artifact_degrades_to_median_with_warning():
    """Given chưa có file mô hình. Then chiến lược C dùng HistoricalMedianForecaster và ghi cảnh báo, app không sập."""


@pytest.mark.skip(reason="[T2.1] FR9 — xem thêm test_forecast_never_relaxes_declared_deadline")
def test_forecast_only_changes_queue_start_never_deadline():
    """FR9. Given dự báo xe A rút muộn hơn hạn khai báo. Then hạn của mọi booking trong LP không đổi."""
