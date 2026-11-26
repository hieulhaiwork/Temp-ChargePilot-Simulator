"""Tools nghiệp vụ sạc cho Agent F1 — Agent HIỂU yêu cầu, CODE tính toán và quyết định.

Ranh giới (FR5; khoá bởi tests/test_architecture.py): tools chỉ gọi src/services/*,
không import optimizer/guard/simulator. Agent không tự quyết công suất, không gửi lệnh
trạm, không ghi đè điều kiện an toàn — và KHÔNG có tool nào tạo Command.

Luồng đặt lịch qua chat (AC1):
    propose_charging_plan (what-if, màn S3 — kết quả đã gồm kWh do code tính)
    → confirm_booking  [RISKY → HITL interrupt: cư dân bấm "Xác nhận" ở S3 = resume approve]

Danh tính (ADR-006): `resident_id` KHÔNG phải tham số của tool. Tool nhận `config: RunnableConfig`
do LangChain tiêm — tham số này không nằm trong schema gửi cho LLM — và đọc
config["configurable"]["resident_id"] mà router đã đặt từ token đăng nhập.

Tham số `request: ChargeRequest` → LLM phải trả đúng schema; validator (target > now,
datetime có múi giờ, deadline sau giờ đến) chạy NGAY tại ranh giới tool (schema-first).

Trạng thái: lookup_vehicle, estimate_charging_energy và phần lấy resident_id chạy thật. Các tool
còn lại gọi charging_service đang là stub [T2.2/T2.5]; act_node ghi TOOL_ERROR vào trace.
Owner: TV3. Task: T2.5.
"""

import json

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.config import get_settings
from src.models.api import ErrorCode
from src.models.charging import ChargeRequest
from src.services import catalog, charging_demo, charging_service
from src.services.energy import estimate_energy
from src.services.errors import DomainError

PROPOSAL_TOOL_NAME = "propose_charging_plan"  # act_node lưu kết quả tool này vào state.proposal (payload S3)
CONFIRM_TOOL_NAME = "confirm_booking"  # RISKY — có trong RISKY_TOOL_NAMES


def _svc():
    """Chọn charging_demo khi bật AGENT_DEMO_SERVICES=true (chạy thử khi T2.2 còn stub)."""
    return charging_demo if get_settings().agent_demo_services else charging_service


def _current_resident_id(config: RunnableConfig) -> str:
    """resident_id lấy từ phía server (token đăng nhập → routes.chat → config), KHÔNG do LLM điền.

    Nếu LLM điền được resident_id, một prompt injection có thể xem/sửa lịch của cư dân khác.
    Thiếu thì raise ngay — không có giá trị mặc định, không đoán.
    """
    resident_id = (config.get("configurable") or {}).get("resident_id")
    if not resident_id:
        raise DomainError(
            ErrorCode.UNAUTHENTICATED, "Không xác định được cư dân đang chat (thiếu resident_id phía server)"
        )
    return str(resident_id)


def _chat_idempotency_key(config: RunnableConfig) -> str | None:
    """Khoá idempotency của luồng chat (ADR-008): resume hai lần không tạo hai booking."""
    thread_id = (config.get("configurable") or {}).get("thread_id")
    return f"chat:{thread_id}" if thread_id else None


@tool
def lookup_vehicle(vehicle_model: str) -> str:
    """Tra thông số một mẫu xe trong danh mục ChargePilot: dung lượng pin khả dụng, công suất sạc AC tối đa.

    Args:
        vehicle_model: Mã xe trong danh mục, vd "DEMO-60". Truyền chuỗi rỗng "" để nhận danh sách mã hợp lệ.

    Returns:
        JSON thông số xe, hoặc JSON {"error": ..., "valid_models": [...]} nếu mã không có.
    """
    vehicles = catalog.load_vehicle_catalog()
    if vehicle_model in vehicles:
        return vehicles[vehicle_model].model_dump_json()
    return json.dumps(
        {"error": "unknown_vehicle_model", "vehicle_model": vehicle_model, "valid_models": sorted(vehicles)},
        ensure_ascii=False,
    )


@tool
def estimate_charging_energy(vehicle_model: str, soc_now: float, soc_target: float) -> str:
    """Tính điện năng cần nạp (kWh) bằng công thức FR3 của hệ thống. KHÔNG tự tính kWh bằng suy luận.

    Args:
        vehicle_model: Mã xe trong danh mục (xem lookup_vehicle).
        soc_now: % pin hiện tại, 0–100.
        soc_target: % pin mong muốn, 0–100, phải lớn hơn soc_now.

    Returns:
        JSON gồm battery_energy_kwh (nạp vào pin), grid_energy_kwh (lấy từ lưới), efficiency.
    """
    spec = catalog.get_vehicle(vehicle_model)
    return estimate_energy(spec, soc_now, soc_target).model_dump_json()


@tool
def propose_charging_plan(request: ChargeRequest, config: RunnableConfig) -> str:
    """Hỏi bộ tối ưu phương án sạc (what-if, CHƯA giữ chỗ): đầu nối, khung giờ, kWh, chi phí ước tính, lý do.

    Kết quả đã gồm kWh do hệ thống tính — không cần gọi estimate_charging_energy trước.
    Nếu không kịp hạn, kết quả kèm phương án thay thế (giờ khác, mức pin thấp hơn, vào hàng đợi).
    Thiếu trường nào trong request thì HỎI LẠI cư dân trước, không tự đoán.

    Args:
        request: Yêu cầu sạc; thời gian theo ISO 8601 CÓ múi giờ, vd "2026-11-17T07:00:00+07:00".
    """
    return _svc().quote(request, _current_resident_id(config)).model_dump_json()


@tool
async def confirm_booking(request: ChargeRequest, config: RunnableConfig) -> str:
    """[RISKY — cần cư dân xác nhận ở màn S3] Chốt lịch sạc theo phương án vừa đề xuất.

    Chỉ gọi SAU propose_charging_plan, khi cư dân muốn chốt. Hệ thống sẽ dừng để cư dân bấm Xác nhận.

    Args:
        request: Đúng yêu cầu đã dùng cho propose_charging_plan.

    Returns:
        JSON biên nhận gồm mã và trạng thái đặt lịch, đầu nối, khung giờ, điện năng và chi phí ước tính.
    """
    booking = await _svc().book(request, _current_resident_id(config), idempotency_key=_chat_idempotency_key(config))
    return booking.model_dump_json(
        include={
            "booking_id": True,
            "status": True,
            "connector_id": True,
            "planned_start": True,
            "planned_end": True,
            "estimated_cost_vnd": True,
            "energy": {"battery_energy_kwh", "grid_energy_kwh"},
        }
    )


@tool
def get_queue_status(config: RunnableConfig) -> str:
    """Vị trí trong hàng đợi và thời gian chờ dự kiến của cư dân đang chat (dùng khi cư dân đến mà hết đầu nối)."""
    return _svc().queue_status(_current_resident_id(config)).model_dump_json()


@tool
def explain_schedule(config: RunnableConfig) -> str:
    """Lý do lịch sạc hiện tại của cư dân được xếp hoặc bị thay đổi — lấy từ nhật ký quyết định, không suy diễn."""
    return json.dumps(_svc().explain(_current_resident_id(config)), ensure_ascii=False)


@tool
def get_tariff_info(time_hhmm: str | None = None) -> str:
    """Tra biểu giá điện theo khung giờ của trạm sạc (áp dụng chung cho cả trụ AC và DC).

    Args:
        time_hhmm: Giờ cụ thể định dạng 24h 'HH:MM' (vd '22:00' cho 10 giờ tối). Bỏ trống để lấy toàn bộ biểu giá các khung giờ.
    """
    from datetime import time as dt_time

    tariff = catalog.load_tariff()
    station = catalog.load_station_config()
    ac_kw = max((c.max_power_kw for c in station.connectors if c.zone.value == "AC"), default=0.0)
    dc_kw = max((c.max_power_kw for c in station.connectors if c.zone.value == "DC"), default=0.0)
    periods_out = [
        {
            "period": p.name,
            "start": p.start.strftime("%H:%M"),
            "end": p.end.strftime("%H:%M"),
            "price_vnd_per_kwh": p.price_per_kwh,
        }
        for p in tariff.periods
    ]
    result: dict = {
        "applies_to": f"Cả trụ AC ({ac_kw:g} kW) và trụ DC ({dc_kw:g} kW) dùng chung biểu giá theo khung giờ",
        "verified": tariff.verified,
        "source_note": tariff.source,
        "periods": periods_out,
    }
    if time_hhmm:
        raw = time_hhmm.strip()
        parts = raw.split(":")
        parsed_time: dt_time | None = None
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                parsed_time = dt_time(h, m)
        if parsed_time is None:
            result["time_error"] = f"Giờ '{time_hhmm}' không đúng định dạng 24h HH:MM (vd '22:00')."
        else:
            result["queried_time"] = parsed_time.strftime("%H:%M")
            result["queried_price_vnd_per_kwh"] = tariff.price_at(parsed_time)
            for p in tariff.periods:
                in_period = (p.start <= p.end and p.start <= parsed_time < p.end) or (
                    p.start > p.end and (parsed_time >= p.start or parsed_time < p.end)
                )
                if in_period:
                    result["queried_period"] = p.name
                    result["queried_window"] = f"{p.start.strftime('%H:%M')}–{p.end.strftime('%H:%M')}"
                    break
    return json.dumps(result, ensure_ascii=False)


CHARGING_TOOLS = [
    lookup_vehicle,
    estimate_charging_energy,
    propose_charging_plan,
    confirm_booking,
    get_queue_status,
    explain_schedule,
    get_tariff_info,
]
