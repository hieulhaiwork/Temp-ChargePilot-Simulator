"""Bảo vệ điện khẩn cấp (FR13 dòng 2, AC5) — ĐỘC LẬP với AI và với bộ tối ưu.

Khi nguồn giảm đột ngột (vd 35 → 20 kW), không chờ MPC giải lại: hạ công suất NGAY
bằng luật đơn giản, xác định (chia tỉ lệ để Σ ≤ new_limit_kw), source=EMERGENCY.
Lệnh khẩn cấp vẫn qua checker (luật tổng / đầu nối) nhưng KHÔNG chờ phê duyệt — cư dân
đã đồng ý trước (ConsentScope.emergency_curtailment). Thông báo cư dân SAU, ghi log.
Sau đó control_loop mới tính lại lịch tối ưu với giới hạn mới (FR8).

Owner: TV3. Task: T3.2.
"""

import math
from datetime import datetime

from src.models.control import Command, CommandSource, CommandType
from src.models.station import StationState


def curtail_to_limit(state: StationState, new_limit_kw: float, now: datetime, efficiency: float = 1.0) -> list[Command]:
    """Sinh lệnh SET_POWER để tổng tải phía lưới (Σ cổng / efficiency) ≤ new_limit_kw ngay lập tức.

    Chia tỉ lệ đều cho mọi cổng đang cấp điện; làm tròn XUỐNG 3 chữ số để không vượt do sai số.
    Đã dưới giới hạn → không lệnh nào (không bật-tắt thừa).
    """
    output_budget = new_limit_kw * efficiency
    total = state.total_power_kw
    if total <= output_budget + 1e-9:
        return []
    factor = output_budget / total
    return [
        Command(
            type=CommandType.SET_POWER,
            connector_id=c.connector_id,
            power_kw=math.floor(c.power_kw * factor * 1000) / 1000,
            booking_id=c.booking_id,
            source=CommandSource.EMERGENCY,
            issued_by="emergency",
            based_on_schedule_version=state.schedule_version,
            based_on_state_at=state.timestamp,
            created_at=now,
            reason=f"Nguồn giảm còn {new_limit_kw:g} kW — hạ công suất theo tỉ lệ (AC5)",
        )
        for c in state.connectors
        if c.power_kw > 0
    ]
