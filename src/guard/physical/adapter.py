"""Adapter backend → Physical Guard gốc (`src/guard/physical/validator.py`, chuyển từ simulator ở ADR-019 Phase 2), ADR-017.

Vì sao tồn tại: nhóm lấy simulator làm chuẩn an toàn vật lý. Thay vì viết lại logic tương đương (dễ trôi), module
này dịch `StationConfig` + `StationState` + lô lệnh sang kiểu của simulator rồi gọi đúng các hàm kiểm của nó:

  - `validate_dispatch`: gán cổng — cổng trống, xe đã đến và đang chờ, đúng vùng, một xe một cổng.
  - `guard`: công suất — xe đủ điều kiện, 0 ≤ kW ≤ min(cổng, xe), Σ tủ, Σ vùng ≤ trần vùng, nguồn chung / độc lập.

Simulator báo lỗi bằng `ConstraintViolationError`; ở đây đổi thành thông điệp để luật trả `Violation`.
Không import gì kéo theo ev2gym (gói `safety` / `scenario` / `observations` thuần Python).
"""

from collections.abc import Mapping
from math import inf

from src.guard.physical.validator import guard as simulator_guard
from src.guard.physical.validator import validate_dispatch
from src.models.charging import Booking
from src.models.physical_constraints import TOL, ConstraintViolationError
from src.models.physical_limits import EffectiveLimits
from src.models.scheduling.dispatch import DispatchObservation
from src.models.scheduling.observations import Candidate, VehicleObservation
from src.models.simulation_core import Cabinet, Vehicle
from src.models.station import ConnectorSpec, ConnectorState, ConnectorStatus, StationConfig, StationState, SupplyMode

EMPTY_PREFIX = "(cổng trống) "  # mã "xe" giả cho cổng không có xe — không bao giờ là ứng viên hợp lệ


def effective_limits(config: StationConfig, state: StationState) -> EffectiveLimits:
    """Giới hạn hiện hành theo đúng kiểu `EffectiveLimits` của simulator (`safety/limits.py`).

    Lưới = `state.available_power_kw` (đã giảm khi có sự cố nguồn). Trần vùng = `config.zone_cap_kw`
    (trần thiết bị, vắng thì ngân sách — như scenario cũ của simulator).
    """
    zones = {str(c.zone) for c in config.connectors}
    zone_caps = {z: cap for z in sorted(zones) if (cap := config.zone_cap_kw(z)) is not None}
    independent = None
    if config.supply_mode == SupplyMode.INDEPENDENT and config.independent_grid_input_limit_kw:
        independent = {str(z): kw for z, kw in config.independent_grid_input_limit_kw.items()}
    return EffectiveLimits(
        minute=0,
        conversion=config.power_conversion_efficiency,
        grid_input_kw=state.available_power_kw,
        zone_output_kw=zone_caps,
        cabinet_output_kw={c.cabinet_id: c.output_limit_kw for c in config.cabinets},
        independent_grid_input_kw=independent,
    )


def _cabinet(config: StationConfig, spec: ConnectorSpec, *, port_kw: float | None = None) -> Cabinet:
    """Tủ của cổng theo kiểu simulator; `port_kw` lấy của chính cổng (cổng cùng tủ có thể khác công suất)."""
    cab = next((c for c in config.cabinets if c.cabinet_id == spec.cabinet_id), None)
    return Cabinet(
        id=cab.cabinet_id if cab else f"port:{spec.connector_id}",
        zone=str(spec.zone),
        ports=1,
        port_kw=spec.max_power_kw if port_kw is None else port_kw,
        output_kw=cab.output_limit_kw if cab else spec.max_power_kw,
    )


def _vehicle_id(connector_id: str, occupant: str | None) -> str:
    return occupant if occupant else f"{EMPTY_PREFIX}{connector_id}"


def _eligible(current: ConnectorState, occupant: str | None) -> bool:
    """Simulator chỉ cấp điện cho xe CHARGING: cổng có xe, không lỗi, xe chưa sạc xong."""
    if occupant is None or current.status == ConnectorStatus.FAULT:
        return False
    return not (current.status == ConnectorStatus.FINISHED and occupant == current.booking_id)


def check_connector_allocation(
    config: StationConfig,
    current: ConnectorState,
    occupant: str | None,
    target_kw: float,
    booking: Booking | None,
) -> str | None:
    """Một cổng: xe đủ điều kiện và 0 ≤ kW ≤ min(cổng, xe). Chỉ xét lệnh CẤP điện (target > 0)."""
    if target_kw <= TOL:
        return None
    spec = next(c for c in config.connectors if c.connector_id == current.connector_id)
    vid = _vehicle_id(current.connector_id, occupant)
    candidates = {}
    if _eligible(current, occupant):
        allowed = min(spec.max_power_kw, booking.max_charge_power_kw) if booking else spec.max_power_kw
        candidates[vid] = Candidate(_cabinet(config, spec), allowed)
    only_port = EffectiveLimits(0, 1.0, inf, {}, {}, None)  # tầng tủ / vùng / lưới do check_site_allocation
    try:
        simulator_guard(None, candidates, {vid: target_kw}, {}, limits=only_port)
    except ConstraintViolationError as exc:
        return _explain(exc, current, occupant)
    return None


def check_site_allocation(
    config: StationConfig,
    state: StationState,
    power_after: Mapping[str, float],
    occupants: Mapping[str, str | None],
) -> str | None:
    """Cả bãi sau lô: Σ tủ ≤ trần tủ, Σ vùng ≤ trần vùng, nguồn chung Σ/η ≤ lưới hoặc nguồn độc lập từng vùng.

    Tính hợp lệ từng xe đã do `check_connector_allocation` kiểm, nên ở đây mọi cổng có điện đều là ứng viên.
    """
    limits = effective_limits(config, state)
    specs = {c.connector_id: c for c in config.connectors}
    candidates, plan = {}, {}
    for connector_id, kw in power_after.items():
        if kw <= TOL or connector_id not in specs:
            continue
        vid = _vehicle_id(connector_id, occupants.get(connector_id))
        candidates[vid] = Candidate(_cabinet(config, specs[connector_id], port_kw=inf), inf)
        plan[vid] = kw
    try:
        simulator_guard(None, candidates, plan, limits.zone_output_kw, limits=limits)
    except ConstraintViolationError as exc:
        return f"Guard simulator: {exc}"
    if not limits.shared_supply:
        # Nguồn độc lập: simulator chỉ kiểm từng vùng; backend còn giới hạn hiện hành khi có sự cố nguồn.
        grid_kw = sum(plan.values()) / limits.conversion
        if grid_kw > state.available_power_kw + TOL:
            return f"Tổng phía lưới {grid_kw:.2f} kW > giới hạn hiện hành {state.available_power_kw:g} kW"
    return None


def check_dispatch(
    config: StationConfig,
    state: StationState,
    connector_id: str,
    booking_id: str,
    booking: Booking | None,
) -> str | None:
    """Gán cổng: đúng `validate_dispatch` của simulator — cổng trống, xe đã đến + đang chờ, cùng vùng."""
    spec = next(c for c in config.connectors if c.connector_id == connector_id)
    zone = str(spec.zone)
    zone_ports = {c.connector_id for c in config.connectors if str(c.zone) == zone}
    empty_ports = tuple(
        c.connector_id
        for c in state.connectors
        if c.connector_id in zone_ports and c.booking_id is None and c.status != ConnectorStatus.FAULT
    )
    session = next((s for s in state.sessions if s.booking_id == booking_id), None)
    vehicles, waiting = {}, ()
    if session is not None:
        vehicle_zone = str(booking.request.zone) if booking else zone
        vehicle = Vehicle(booking_id, vehicle_zone, 0, 0, 1.0, 0.0, 1.0, spec.max_power_kw)
        state_name = "QUEUED" if session.connector_id is None else "CHARGING"
        vehicles[booking_id] = VehicleObservation(vehicle, state_name, 0.0, session.connector_id, None, None)
        if session.connector_id is None:
            waiting = (booking_id,)
    observation = DispatchObservation(0, zone, empty_ports, waiting, vehicles)
    try:
        validate_dispatch(observation, {connector_id: booking_id})
    except ConstraintViolationError as exc:
        return _explain_dispatch(exc, state, connector_id, session, booking, zone)
    return None


# ---- thông điệp cho màn S7 (tiếng Việt + nguyên văn của simulator) -------------------------------


def _explain(exc: ConstraintViolationError, current: ConnectorState, occupant: str | None) -> str:
    cid = current.connector_id
    if occupant is None:
        reason = f"cổng {cid} không có xe"
    elif current.status == ConnectorStatus.FAULT:
        reason = f"đầu nối {cid} đang lỗi"
    elif current.status == ConnectorStatus.FINISHED and occupant == current.booking_id:
        reason = f"xe {occupant} ở {cid} đã sạc xong"
    else:
        reason = f"công suất vượt giới hạn cổng / xe ở {cid}"
    return f"{reason} (Guard simulator: {exc})"


def _explain_dispatch(exc, state, connector_id, session, booking, zone) -> str:
    current = next(c for c in state.connectors if c.connector_id == connector_id)
    if session is None:
        reason = "xe chưa có mặt ở bãi"
    elif session.connector_id is not None:
        reason = f"xe đang ở cổng {session.connector_id}, chỉ gán xe đang chờ"
    elif current.status == ConnectorStatus.FAULT:
        reason = f"đầu nối {connector_id} đang lỗi"
    elif current.booking_id is not None:
        reason = f"đầu nối {connector_id} đang có xe {current.booking_id}"
    elif booking is not None and str(booking.request.zone) != zone:
        reason = f"xe vùng {booking.request.zone} không cắm được cổng {zone} (ADR-010)"
    else:
        reason = "gán cổng không hợp lệ"
    return f"{reason} (Guard simulator: {exc})"
