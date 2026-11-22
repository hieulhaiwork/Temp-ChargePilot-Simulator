"""Feature cho dự báo thời điểm rút đầu nối (FR17).

CẤM rò rỉ nhãn: không dùng giờ rút thật (`unplug_time`) hay bất kỳ thông tin nào xảy ra
SAU lúc cắm làm feature. Lịch sử của user chỉ được tính trên các phiên kết thúc TRƯỚC
phiên đang dự báo.

Gợi ý feature: giờ cắm, thứ trong tuần, kWh yêu cầu, giờ khai báo rời (nếu có), trung vị
thời gian đỗ lịch sử của user. User ít lịch sử → dùng mô hình chung (FR17).

Owner: TV2. Task: T2.3. Trạng thái: STUB.
"""

from collections.abc import Sequence

from src.models.charging import ChargingSession

# Field của ChargingSession không bao giờ được thành feature — test leakage sẽ dùng hằng này.
FORBIDDEN_FEATURE_FIELDS: frozenset[str] = frozenset({"unplug_time"})


def build_features(session: ChargingSession, history: Sequence[ChargingSession]) -> dict[str, float]:
    """Feature của một phiên, chỉ dùng `history` kết thúc trước session.plug_in_time."""
    raise NotImplementedError("[T2.3] build_features — không dùng FORBIDDEN_FEATURE_FIELDS")
