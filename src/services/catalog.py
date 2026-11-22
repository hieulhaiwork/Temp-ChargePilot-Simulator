"""Nạp tham số cấu hình từ config/*.yaml — trạm, danh mục xe, biểu giá, kịch bản.

Vì sao tồn tại: PRD yêu cầu tham số mô phỏng nằm trong file cấu hình (không hardcode)
để phân tích độ nhạy chỉ cần đổi YAML. Đây là chỗ DUY NHẤT đọc các file đó và validate
bằng Pydantic: file sai thì raise ngay lúc nạp (fail loudly), không chạy tiếp với số liệu
hỏng. Kết quả cache bằng lru_cache — đổi YAML thì khởi động lại server.
"""

from functools import lru_cache
from pathlib import Path

import yaml

from src.models.charging import VehicleSpec
from src.models.simulation import Scenario
from src.models.station import StationConfig, Tariff

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
SCENARIO_DIR = CONFIG_DIR / "scenarios"


class UnknownVehicleError(KeyError):
    """Mã xe không có trong danh mục — Agent phải hỏi lại cư dân, không tự đoán."""


class UnknownScenarioError(KeyError):
    """Không có file config/scenarios/<scenario_id>.yaml."""


def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} phải là một mapping YAML")
    return data


@lru_cache(maxsize=1)
def load_station_config() -> StationConfig:
    return StationConfig.model_validate(_read_yaml(CONFIG_DIR / "station.yaml"))


@lru_cache(maxsize=1)
def load_vehicle_catalog() -> dict[str, VehicleSpec]:
    raw = _read_yaml(CONFIG_DIR / "vehicles.yaml").get("vehicles") or []
    vehicles = [VehicleSpec.model_validate(item) for item in raw]
    catalog = {v.vehicle_model: v for v in vehicles}
    if len(catalog) != len(vehicles):
        raise ValueError("config/vehicles.yaml có vehicle_model bị trùng")
    return catalog


def get_vehicle(vehicle_model: str) -> VehicleSpec:
    """Tra một mẫu xe. Raise UnknownVehicleError nếu không có trong danh mục."""
    try:
        return load_vehicle_catalog()[vehicle_model]
    except KeyError:
        raise UnknownVehicleError(vehicle_model) from None


@lru_cache(maxsize=1)
def load_tariff() -> Tariff:
    return Tariff.model_validate(_read_yaml(CONFIG_DIR / "tariff.yaml"))


def load_scenario(scenario_id: str) -> Scenario:
    """Nạp một kịch bản. Tên file phải trùng scenario_id."""
    path = SCENARIO_DIR / f"{scenario_id}.yaml"
    if not path.is_file():
        raise UnknownScenarioError(scenario_id)
    scenario = Scenario.model_validate(_read_yaml(path))
    if scenario.scenario_id != scenario_id:
        raise ValueError(f"{path.name}: scenario_id={scenario.scenario_id!r} không khớp tên file")
    return scenario


def list_scenarios() -> list[Scenario]:
    return [load_scenario(p.stem) for p in sorted(SCENARIO_DIR.glob("*.yaml"))]
