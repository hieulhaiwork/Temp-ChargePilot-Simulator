"""Dữ liệu tham chiếu công khai: danh mục xe, công thức kWh (FR3), cấu hình trạm, biểu giá.

Đây là nhóm endpoint ĐÃ CHẠY THẬT trong skeleton — frontend (TV4) dùng được ngay cho
dropdown mẫu xe ở S2 và ô ước tính kWh ở S3.
"""

from fastapi import APIRouter, HTTPException, status

from src.models.api import EnergyEstimateRequest
from src.models.charging import EnergyEstimate, VehicleSpec
from src.models.station import StationConfig, Tariff
from src.services import catalog
from src.services.energy import estimate_energy

router = APIRouter(tags=["catalog"])


@router.get("/vehicles", response_model=list[VehicleSpec])
async def list_vehicles() -> list[VehicleSpec]:
    """Danh mục mẫu xe đã kiểm chứng (FR2) — cư dân chọn từ đây."""
    return list(catalog.load_vehicle_catalog().values())


@router.post("/energy/estimate", response_model=EnergyEstimate)
async def estimate(body: EnergyEstimateRequest) -> EnergyEstimate:
    """FR3 — cùng công thức với tool của Agent (AC1: kWh khớp công thức)."""
    try:
        spec = catalog.get_vehicle(body.vehicle_model)
    except catalog.UnknownVehicleError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Không có mẫu xe {body.vehicle_model!r}") from None
    return estimate_energy(spec, body.soc_now, body.soc_target)


@router.get("/station/config", response_model=StationConfig)
async def station_config() -> StationConfig:
    """Tham số bãi sạc mô phỏng — topology hybrid AC/DC lấy từ config/station.yaml (ADR-010)."""
    return catalog.load_station_config()


@router.get("/tariff", response_model=Tariff)
async def tariff() -> Tariff:
    """Biểu giá mô phỏng — để web giải thích "vì giờ thấp điểm rẻ hơn"."""
    return catalog.load_tariff()
