"""FR3 — tính điện năng cần nạp bằng CODE (LLM không tự tính).

    Điện nạp vào pin  ≈ dung lượng khả dụng × (% pin mong muốn − % pin hiện tại)
    Điện lấy từ lưới  ≈ điện nạp vào pin ÷ hiệu suất sạc

Hiệu suất: lấy của mẫu xe nếu có, không thì giả định chung trong config/station.yaml.
Dùng chung cho tool của Agent, API /energy/estimate và bộ tối ưu — AC1 yêu cầu kWh
hiển thị cho cư dân khớp đúng công thức này.
"""

from src.models.charging import EnergyEstimate, VehicleSpec
from src.services.catalog import load_station_config


def estimate_energy(vehicle: VehicleSpec, soc_now: float, soc_target: float) -> EnergyEstimate:
    """Tính kWh cần nạp cho một xe.

    Raises:
        ValueError: nếu không thoả 0 ≤ soc_now < soc_target ≤ 100.
    """
    if not 0 <= soc_now < soc_target <= 100:
        raise ValueError(f"Cần 0 ≤ soc_now < soc_target ≤ 100, nhận soc_now={soc_now}, soc_target={soc_target}")
    efficiency = vehicle.charging_efficiency or load_station_config().default_charging_efficiency
    battery_kwh = vehicle.usable_capacity_kwh * (soc_target - soc_now) / 100
    return EnergyEstimate(
        vehicle_model=vehicle.vehicle_model,
        soc_now=soc_now,
        soc_target=soc_target,
        battery_energy_kwh=battery_kwh,
        grid_energy_kwh=battery_kwh / efficiency,
        efficiency=efficiency,
    )
