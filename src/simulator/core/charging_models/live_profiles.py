"""Vehicle-profile provider cho trạm nhận xe DẦN (backend `HybridStation`) — Final Review 4.2.

Vì sao tồn tại: simulator offline biết trước mọi xe nên `VehicleProfilesDCModel.from_scenario` resolve profile một lần;
trạm backend nhận xe khi booking được upsert. Provider này resolve profile KHI XE ĐƯỢC ĐĂNG KÝ, bằng ĐÚNG code của
offline (`VehicleProfilesDCModel.from_scenario` trên scenario chỉ có xe đó: cùng bảng model, cùng kiểm dung lượng pin),
rồi tính acceptance / năng lượng bằng ĐÚNG các method của `VehicleProfilesDCModel` (gán lại làm method, không chép thân
hàm, không sửa class gốc). Cùng xe + cùng profile ⇒ cùng công suất / SOC với simulator offline.

Có trạng thái (bảng profile theo xe) ⇒ có `fork()` cho bản fork admission / WHAT-IF: đăng ký xe trên bản fork không làm
đổi bản live.

[GIẢ ĐỊNH] Xe không resolve được profile (model lạ không có dữ liệu, dung lượng pin khác profile): mặc định dùng
fallback synthetic như xe không nhãn của offline và ghi lý do vào `unresolved` + log; `strict=True` thì raise.
"""

from dataclasses import replace
from logging import getLogger
from types import MappingProxyType

from src.models.charging_physics import DCChargingModel
from src.models.simulation_core import Scenario, Vehicle

from .synthetic_dc import SyntheticTaperV1
from .vehicle_profiles import VehicleProfilesDCModel

LOGGER = getLogger(__name__)


class DynamicVehicleProfilesDCModel:
    """`VehicleProfilesDCModel` với bảng profile mở rộng được khi xe đến (`register_vehicle`)."""

    # Cùng thân hàm với model offline (một implementation): chỉ đọc self.profiles / self.fallback / self._profile.
    _profile = VehicleProfilesDCModel._profile
    acceptance_kw = VehicleProfilesDCModel.acceptance_kw
    stored_kwh = VehicleProfilesDCModel.stored_kwh
    metadata_for = VehicleProfilesDCModel.metadata_for

    def __init__(self, *, strict: bool = False, fallback: DCChargingModel | None = None) -> None:
        self._profiles: dict = {}
        self.profiles = MappingProxyType(self._profiles)  # view sống — cùng tên thuộc tính với model offline
        self.fallback = SyntheticTaperV1() if fallback is None else fallback
        self.strict = strict
        self.unresolved: dict[str, str] = {}

    def register_vehicle(self, vehicle: Vehicle, scenario: Scenario) -> None:
        """Resolve profile cho một xe (đến mới hoặc đổi thông số) bằng đúng `from_scenario` của offline."""
        self.forget_vehicle(vehicle.id)
        if vehicle.zone != "DC" or vehicle.vehicle_model is None:
            return  # như offline: xe không nhãn / xe AC dùng fallback
        try:
            single = VehicleProfilesDCModel.from_scenario(replace(scenario, vehicles=(vehicle,)))
        except ValueError as exc:
            if self.strict:
                raise
            self.unresolved[vehicle.id] = str(exc)
            LOGGER.warning("Không resolve được profile DC cho %s — dùng fallback synthetic: %s", vehicle.id, exc)
            return
        self._profiles.update(single.profiles)

    def forget_vehicle(self, vehicle_id: str) -> None:
        self._profiles.pop(vehicle_id, None)
        self.unresolved.pop(vehicle_id, None)

    def clear(self) -> None:
        self._profiles.clear()
        self.unresolved.clear()

    def fork(self) -> "DynamicVehicleProfilesDCModel":
        """Bản độc lập (profile là dataclass frozen nên dùng chung được; bảng theo xe thì tách)."""
        twin = DynamicVehicleProfilesDCModel(strict=self.strict, fallback=self.fallback)
        twin._profiles.update(self._profiles)
        twin.unresolved.update(self.unresolved)
        return twin

    def __deepcopy__(self, memo) -> "DynamicVehicleProfilesDCModel":
        return self.fork()  # MappingProxyType không deepcopy được; bản sao sâu = fork
