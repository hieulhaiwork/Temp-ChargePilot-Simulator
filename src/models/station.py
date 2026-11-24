"""Hợp đồng dữ liệu của bãi sạc: cấu hình, đầu nối, trạng thái, biểu giá.

Vì sao tồn tại: optimizer (TV1), guard + simulator (TV3) và dashboard (TV4) cùng
đọc MỘT trạng thái trạm. Định nghĩa một lần ở đây để 4 người không tự chế 4 kiểu
dict khác nhau. Module thuần dữ liệu — không import package nào khác trong src/
(tests/test_architecture.py khoá quy tắc này).

Đơn vị: công suất kW, điện năng kWh, thời gian luôn có múi giờ (AwareDatetime).
"""

from datetime import time
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class ChargerZone(StrEnum):
    """Vùng sạc của bãi hybrid (ADR-010). Xe AC không vào cổng DC và ngược lại."""

    AC = "AC"
    DC = "DC"


class SupplyMode(StrEnum):
    """Cách hai vùng lấy điện (ADR-010). `shared` là [GIẢ ĐỊNH] — chưa có số liệu lưới tại site."""

    SHARED = "shared"  # một giới hạn lưới, coordinator chia ngân sách AC/DC
    INDEPENDENT = "independent"  # mỗi vùng có independent_grid_input_limit_kw riêng, không chuyển công suất xuyên nguồn


class CabinetSpec(BaseModel):
    """Một tủ sạc (ADR-010): nhiều cổng chung một giới hạn đầu ra (cap vật lý)."""

    cabinet_id: str = Field(min_length=1, description="Mã tủ, vd AC-01, DC-01")
    zone: ChargerZone
    output_limit_kw: float = Field(gt=0, description="Giới hạn tổng đầu ra của tủ (Σ cổng của tủ)")


class ConnectorSpec(BaseModel):
    """Thông số tĩnh của một đầu nối / cổng (config/station.yaml). Topology nền: ADR-010."""

    connector_id: str = Field(min_length=1, description="Mã cổng, vd AC-01-1, DC-01-2 (ADR-010)")
    max_power_kw: float = Field(gt=0, description="Công suất tối đa của cổng (giá trị lấy từ config, ADR-003/010)")
    cabinet_id: str | None = Field(default=None, description="Tủ chứa cổng; phải có trong StationConfig.cabinets")
    zone: ChargerZone = Field(default=ChargerZone.AC, description="Vùng của cổng; phải trùng vùng của tủ")
    bay_id: str | None = Field(default=None, description="Ô đỗ gắn với cổng (tuỳ chọn)")


class GuardSettings(BaseModel):
    """Ngưỡng của Safety Guard (FR12) — nạp từ khối `guard:` của station.yaml."""

    max_state_age_seconds: float = Field(gt=0, description="Luật stale_state")
    flap_window_minutes: int = Field(gt=0, description="Cửa sổ đếm bật/tắt — luật anti_flapping")
    flap_max_toggles: int = Field(gt=0, description="Số lần bật/tắt tối đa trong cửa sổ")
    approval_ttl_minutes: int = Field(
        default=15, gt=0, description="Hạn trả lời yêu cầu phê duyệt (AC4: hết hạn = không làm)"
    )
    after_apply_failsafe: bool = Field(
        default=False,
        description=(
            "Final Review §4.5b: vi phạm trần cứng phát hiện SAU khi áp → phát sự kiện hard_limit_violated và giảm "
            "tải khẩn cấp qua dispatcher. Mặc định tắt (chỉ đếm + log như trước)"
        ),
    )


class OptimizerSettings(BaseModel):
    """Hệ số hàm mục tiêu của bài LP (FR6) — nạp từ khối `optimizer:` của station.yaml.

    Công thức đầy đủ: docs/plan/30-ai.md §5.2. Đặt ở config (ADR-003) để phân tích độ nhạy
    không phải sửa code.
    """

    unmet_penalty_factor: float = Field(gt=0, description="λ_u = hệ số × giá cao nhất — điện thiếu trội tuyệt đối")
    early_charge_factor: float = Field(ge=0, description="ε = hệ số × giá thấp nhất — cùng giá thì sạc sớm hơn")
    smoothing_factor: float = Field(ge=0, description="μ = hệ số × giá thấp nhất — hạn chế đổi công suất liên tục")
    dc_turnover_factor: float = Field(
        default=0.0,
        ge=0,
        description="Phạt theo bước cho phiên DC (× giá cao nhất) — sạc DC xong sớm để giải phóng cổng",
    )
    planning_step_minutes: int = Field(
        default=15,
        gt=0,
        le=60,
        description="Độ phân giải thời gian của LP (MT5 ≤ 2 s); simulator vẫn bước step_minutes",
    )


class StationConfig(BaseModel):
    """Cấu hình bãi sạc mô phỏng — topology hybrid AC/DC của ADR-010 (fixture nền `mvp1`).

    Ràng buộc ba tầng (ADR-010), cùng nghĩa với `EffectiveLimits` của HybridSimulator (ADR-017):
    cổng ≤ max_power_kw; Σ cổng của tủ ≤ output_limit_kw; Σ vùng ≤ trần vùng (physical_zone_cap_kw, vắng thì
    zone_budgets_kw); nguồn chung: Σ cổng / η ≤ grid_input_limit_kw, nguồn độc lập: Σ vùng / η ≤
    independent_grid_input_limit_kw[vùng]. Các field mới đều có default để config / client cũ vẫn nạp được.
    """

    station_id: str
    name: str
    timezone: str = "Asia/Ho_Chi_Minh"
    power_limit_kw: float = Field(
        gt=0,
        description="ALIAS một vòng của grid_input_limit_kw (ADR-010). Giữ cho client cũ; code mới đọc grid_input_limit_kw",
    )
    grid_input_limit_kw: float | None = Field(
        default=None, gt=0, description="Giới hạn đầu vào lưới của cả khu (kW). None ⇒ bằng power_limit_kw"
    )
    zone_budgets_kw: dict[ChargerZone, float] | None = Field(
        default=None,
        description="Ngân sách CHÍNH SÁCH theo vùng (Fixed Share, `default_zone_budget_kw` của simulator), phía đầu ra tủ",
    )
    physical_zone_cap_kw: dict[ChargerZone, float] | None = Field(
        default=None,
        description=(
            "Trần THIẾT BỊ theo vùng, phía đầu ra tủ — Guard chặn theo số này. None ⇒ ngân sách vùng là trần "
            "(như scenario cũ của simulator)"
        ),
    )
    independent_grid_input_limit_kw: dict[ChargerZone, float] | None = Field(
        default=None, description="Giới hạn đầu vào lưới riêng từng vùng — bắt buộc khi supply_mode=independent"
    )
    power_conversion_efficiency: float = Field(
        default=1.0, gt=0, le=1, description="η chuyển đổi lưới → đầu ra tủ. E_grid = E_output / η"
    )
    supply_mode: SupplyMode = Field(default=SupplyMode.SHARED, description="shared là [GIẢ ĐỊNH] (ADR-010)")
    dc_unplug_delay_minutes: int = Field(
        default=5, ge=0, description="Xe DC rút cổng sau N phút khi xong (F14 FINISHED_PLUGGED, ADR-015)"
    )
    cabinets: list[CabinetSpec] = Field(default_factory=list, description="Tủ sạc; rỗng = config cũ không khai tủ")
    step_minutes: int = Field(gt=0, le=60, description="Bước MPC (FR6)")
    horizon_hours: int = Field(gt=0, le=48, description="Cửa sổ xem trước của MPC (FR6)")
    default_charging_efficiency: float = Field(gt=0, le=1, description="Giả định FR3")
    guard: GuardSettings
    optimizer: OptimizerSettings
    connectors: list[ConnectorSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_connector_ids(self) -> "StationConfig":
        ids = [c.connector_id for c in self.connectors]
        if len(ids) != len(set(ids)):
            raise ValueError(f"connector_id bị trùng: {ids}")
        return self

    @model_validator(mode="after")
    def _check_topology(self) -> "StationConfig":
        """Tủ không trùng mã; cổng trỏ tới tủ có thật và cùng vùng; ngân sách vùng không vượt lưới (ADR-010)."""
        cabinet_ids = [c.cabinet_id for c in self.cabinets]
        if len(cabinet_ids) != len(set(cabinet_ids)):
            raise ValueError(f"cabinet_id bị trùng: {cabinet_ids}")
        cabinets = {c.cabinet_id: c for c in self.cabinets}
        for conn in self.connectors:
            if conn.cabinet_id is None:
                continue
            cabinet = cabinets.get(conn.cabinet_id)
            if cabinet is None:
                raise ValueError(f"{conn.connector_id}: cabinet_id={conn.cabinet_id!r} không có trong cabinets")
            if cabinet.zone != conn.zone:
                raise ValueError(
                    f"{conn.connector_id}: zone={conn.zone} khác zone={cabinet.zone} của tủ {cabinet.cabinet_id}"
                )
        if self.grid_input_limit_kw is None:
            self.grid_input_limit_kw = self.power_limit_kw
        elif self.grid_input_limit_kw != self.power_limit_kw:
            # power_limit_kw là alias trong một vòng: hai số khác nhau thì không biết số nào đúng.
            raise ValueError(
                f"power_limit_kw={self.power_limit_kw} khác grid_input_limit_kw={self.grid_input_limit_kw} (alias)"
            )
        for name in ("physical_zone_cap_kw", "independent_grid_input_limit_kw"):
            values = getattr(self, name)
            if values is not None and any(v <= 0 for v in values.values()):
                raise ValueError(f"{name} phải > 0: {values}")
        independent = self.independent_grid_input_limit_kw
        if self.supply_mode == SupplyMode.INDEPENDENT and not independent:
            raise ValueError("supply_mode=independent cần independent_grid_input_limit_kw cho từng vùng")
        if self.supply_mode == SupplyMode.SHARED and independent:
            raise ValueError("independent_grid_input_limit_kw chỉ dùng với supply_mode=independent")
        if self.zone_budgets_kw:
            if any(v <= 0 for v in self.zone_budgets_kw.values()):
                raise ValueError(f"zone_budgets_kw phải > 0: {self.zone_budgets_kw}")
            caps = self.physical_zone_cap_kw or {}
            over = {z: v for z, v in self.zone_budgets_kw.items() if z in caps and v > caps[z] + 1e-9}
            if over:
                raise ValueError(f"zone_budgets_kw vượt physical_zone_cap_kw: {over}")
            if self.supply_mode == SupplyMode.INDEPENDENT:
                for zone, budget in self.zone_budgets_kw.items():
                    if zone in independent and budget > independent[zone] * self.power_conversion_efficiency + 1e-9:
                        raise ValueError(
                            f"Ngân sách {zone} {budget} kW vượt nguồn riêng {independent[zone]} kW × η (independent)"
                        )
            if self.supply_mode == SupplyMode.SHARED:
                grid_needed = sum(self.zone_budgets_kw.values()) / self.power_conversion_efficiency
                if grid_needed > self.grid_input_limit_kw + 1e-9:
                    raise ValueError(
                        f"Σ zone_budgets_kw / η = {grid_needed:.3f} kW vượt grid_input_limit_kw="
                        f"{self.grid_input_limit_kw} kW (supply_mode=shared)"
                    )
        return self

    @property
    def nameplate_power_kw(self) -> float:
        """Tổng công suất danh định của mọi cổng (Σ max_power_kw), chưa tính cap tủ / ngân sách / lưới."""
        return sum(c.max_power_kw for c in self.connectors)

    def zone_cap_kw(self, zone: ChargerZone) -> float | None:
        """Trần đầu ra của vùng mà Guard áp: trần thiết bị nếu khai báo, không thì ngân sách (simulator `limits.py`)."""
        if self.physical_zone_cap_kw is not None:
            return self.physical_zone_cap_kw.get(zone)
        return (self.zone_budgets_kw or {}).get(zone)


class ConnectorStatus(StrEnum):
    """Trạng thái đầu nối — màu trên lưới cột của màn S5."""

    IDLE = "idle"  # ⚪ trống
    CHARGING = "charging"  # 🟢 đang sạc
    THROTTLED = "throttled"  # 🟡 đang bị giảm công suất
    FINISHED = "finished"  # xe đã đủ pin nhưng CHƯA rút — vẫn chiếm cổng (F14 FINISHED_PLUGGED; F6 hoãn, ADR-015)
    FAULT = "fault"  # 🔴 lỗi


class ConnectorState(BaseModel):
    """Trạng thái động của một đầu nối tại một thời điểm."""

    connector_id: str
    status: ConnectorStatus
    power_kw: float = Field(ge=0, description="Công suất đang cấp")
    max_power_kw: float = Field(gt=0)
    booking_id: str | None = None


class SessionProgress(BaseModel):
    """Tiến độ sạc của một booking đang có mặt ở bãi — do simulator báo.

    Vì sao tồn tại: MPC là cửa sổ trượt nên mỗi bước cần biết còn thiếu bao nhiêu kWh
    (grid_energy_kwh − delivered_grid_kwh); màn S2 cần % pin ước tính (FR15).
    """

    booking_id: str
    connector_id: str | None = Field(default=None, description="None = đang chờ trong hàng đợi")
    arrived_at: AwareDatetime
    plugged_in_at: AwareDatetime | None = None
    delivered_grid_kwh: float = Field(default=0, ge=0, description="Điện đã lấy từ lưới cho phiên này")


class StationState(BaseModel):
    """Snapshot trạng thái trạm — đầu vào của optimizer, guard và dashboard.

    `schedule_version` tăng mỗi lần áp lịch mới; Guard dùng nó để chặn lệnh dựa
    trên lịch đã cũ (FR12).
    """

    timestamp: AwareDatetime
    available_power_kw: float = Field(ge=0, description="Giới hạn hiện hành (giảm khi sự cố nguồn)")
    connectors: list[ConnectorState]
    queue: list[str] = Field(default_factory=list, description="booking_id đang chờ đầu nối, đầu hàng trước")
    sessions: list[SessionProgress] = Field(default_factory=list, description="Tiến độ của các xe đang ở bãi")
    schedule_version: int = Field(ge=0)

    @property
    def total_power_kw(self) -> float:
        return sum(c.power_kw for c in self.connectors)


class LoadPoint(BaseModel):
    """Một điểm trên biểu đồ tải 24h (S5) và trong trace mô phỏng (KPI MT4)."""

    timestamp: AwareDatetime
    total_power_kw: float = Field(ge=0)
    power_limit_kw: float = Field(ge=0)


class TariffPeriod(BaseModel):
    """Một khung giá. `end < start` nghĩa là khung qua nửa đêm (vd 22:00 → 04:00)."""

    name: str
    start: time
    end: time
    price_per_kwh: float = Field(gt=0)

    def contains(self, local_time: time) -> bool:
        if self.start < self.end:
            return self.start <= local_time < self.end
        return local_time >= self.start or local_time < self.end


class Tariff(BaseModel):
    """Biểu giá mô phỏng (config/tariff.yaml)."""

    currency: str = "VND"
    source: str
    verified: bool = False
    periods: list[TariffPeriod] = Field(min_length=1)

    @model_validator(mode="after")
    def _covers_whole_day_exactly_once(self) -> "Tariff":
        """Mỗi phút trong ngày thuộc ĐÚNG một khung giá — không hở, không chồng."""
        for minute in range(24 * 60):
            moment = time(minute // 60, minute % 60)
            hits = sum(1 for p in self.periods if p.contains(moment))
            if hits != 1:
                raise ValueError(f"Biểu giá phủ {hits} lần lúc {moment:%H:%M} (cần đúng 1)")
        return self

    def price_at(self, local_time: time) -> float:
        """Giá tại một giờ địa phương của trạm (caller tự đổi sang múi giờ trạm)."""
        for period in self.periods:
            if period.contains(local_time):
                return period.price_per_kwh
        raise ValueError(f"Không có khung giá cho {local_time}")  # validator đã chặn — phòng hờ
