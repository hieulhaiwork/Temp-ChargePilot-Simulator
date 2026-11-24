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

from src.guard.physical import adapter as physical
from src.models.control import Command, CommandSource, CommandType
from src.models.station import StationConfig, StationState

FAILSAFE_SEARCH_STEPS = 40  # chia đôi hệ số co: 2^-40 ≈ 1e-12, dưới mọi sai số kW có nghĩa


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


def stop_faulty_vehicles(
    state: StationState, booking_ids, now: datetime, kinds=(), detail: str = "", *, force=()
) -> list[Command]:
    """Fail-safe cho vi phạm mà giảm tải tổng KHÔNG sửa được (Final Acceptance §1.4): lỗi charging model / acceptance /
    SOC của một xe. Ngắt công suất (SET_POWER 0, nguồn EMERGENCY) đúng các cổng đang cấp điện cho xe đó; runtime giữ
    an toàn (không cấp lại) và báo vận hành. Cổng đã ở 0 ⇒ không lệnh (không bật-tắt thừa), trừ booking trong `force`
    (lần đầu bị giữ: xoá cả setpoint đang giữ, vd. cổng hiển thị FAULT vì acceptance lỗi)."""
    wanted = set(booking_ids)
    force = set(force)
    label = ", ".join(str(k) for k in kinds) or "lỗi xe"
    reason = f"Vi phạm sau khi áp ({label}) — ngắt công suất cổng, chờ vận hành kiểm tra (fail-safe)"
    return [
        Command(
            type=CommandType.SET_POWER,
            connector_id=c.connector_id,
            power_kw=0.0,
            booking_id=c.booking_id,
            source=CommandSource.EMERGENCY,
            issued_by="emergency",
            based_on_schedule_version=state.schedule_version,
            based_on_state_at=state.timestamp,
            created_at=now,
            reason=f"{reason}: {detail}"[:500] if detail else reason,
        )
        for c in state.connectors
        if c.booking_id in wanted and (c.power_kw > 0 or c.booking_id in force)
    ]


def curtail_to_hard_limits(
    state: StationState, config: StationConfig, now: datetime, detail: str = ""
) -> list[Command]:
    """Fail-safe sau khi áp (Final Review §4.5b): co ĐỀU mọi cổng đang cấp điện để trạm về trong trần cứng.

    Trần cứng = đúng luật `total_power_limit` của Guard (`physical.check_site_allocation`: tủ, vùng, lưới chung / nguồn
    độc lập, theo `state.available_power_kw`) — không viết lại công thức. Hệ số co lớn nhất còn hợp lệ tìm bằng chia
    đôi (co đều làm mọi tổng giảm cùng tỉ lệ ⇒ đơn điệu); công suất làm tròn XUỐNG 3 chữ số. Trạm đang trong trần ⇒
    không lệnh nào. Lệnh nguồn EMERGENCY: là giảm tải an toàn nên không chờ HITL / anti-flapping, vẫn qua checker.
    """
    occupants = {c.connector_id: c.booking_id for c in state.connectors}
    power = {c.connector_id: c.power_kw for c in state.connectors}
    if physical.check_site_allocation(config, state, power, occupants) is None:
        return []
    low, high = 0.0, 1.0
    for _ in range(FAILSAFE_SEARCH_STEPS):
        mid = (low + high) / 2
        if physical.check_site_allocation(config, state, {k: v * mid for k, v in power.items()}, occupants) is None:
            low = mid
        else:
            high = mid
    reason = "Vi phạm trần cứng sau khi áp — giảm tải khẩn cấp (fail-safe)"
    return [
        Command(
            type=CommandType.SET_POWER,
            connector_id=c.connector_id,
            power_kw=math.floor(c.power_kw * low * 1000) / 1000,
            booking_id=c.booking_id,
            source=CommandSource.EMERGENCY,
            issued_by="emergency",
            based_on_schedule_version=state.schedule_version,
            based_on_state_at=state.timestamp,
            created_at=now,
            reason=f"{reason}: {detail}"[:500] if detail else reason,
        )
        for c in state.connectors
        if c.power_kw > 0
    ]
