"""Bộ não giả lập (LLM_PROVIDER=mock) — chạy thử toàn bộ tool và luồng S2→S3 mà không cần API key hay VM.

Thiết kế:
- Trích xuất 6 trường ChargeRequest theo luật/regex đơn giản, giữ bộ nhớ nhiều lượt qua `draft_request`.
- Đủ trường → gọi `propose_charging_plan`; thiếu trường → hỏi lại đúng phần thiếu (FR2).
- Cư dân nhắn "chốt" / "xác nhận" → gọi `confirm_booking` (RISKY → HITL interrupt cho màn S3).
- Hỗ trợ đủ 6 tool sạc: `lookup_vehicle`, `estimate_charging_energy`, `propose_charging_plan`,
  `confirm_booking`, `get_queue_status`, `explain_schedule`.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.llm_chat.schemas import AgentDecision, FinalAnswer
from src.llm_chat.state import AgentState
from src.services import catalog

_PCT_RE = re.compile(r"(\d{1,3})\s*%")
_TIME_RE = re.compile(r"(\d{1,2})\s*(?:h|giờ|:)\s*(\d{1,2})?", re.I)
_VEHICLE_RE = re.compile(r"\b(DEMO-\d+|VF\s*-?\s*\d+)\b", re.I)


def _now_local(state: AgentState) -> datetime:
    ctx = state.get("turn_context") or {}
    tz_name = ctx.get("timezone") or catalog.load_station_config().timezone
    tz = ZoneInfo(tz_name)
    raw_now = ctx.get("now")
    if raw_now:
        try:
            parsed = datetime.fromisoformat(raw_now)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=tz)
            return parsed.astimezone(tz)
        except ValueError:
            pass
    return datetime.now(tz)


def _resolve_time(
    base: datetime,
    hour: int,
    minute: int,
    *,
    force_next_day: bool = False,
    allow_same_day_if_future: bool = True,
) -> str:
    tz = base.tzinfo or ZoneInfo(catalog.load_station_config().timezone)
    base_local = base.astimezone(tz) if base.tzinfo is not None else base.replace(tzinfo=tz)
    target_date = base_local.date() + timedelta(days=1 if force_next_day else 0)
    candidate = datetime(target_date.year, target_date.month, target_date.day, hour, minute, 0, 0, tzinfo=tz)
    if not force_next_day and (not allow_same_day_if_future or candidate <= base_local):
        next_date = target_date + timedelta(days=1)
        candidate = datetime(next_date.year, next_date.month, next_date.day, hour, minute, 0, 0, tzinfo=tz)
    return candidate.isoformat()


def _fmt_dt(raw: object) -> str:
    if not isinstance(raw, str) or not raw:
        return "—"
    try:
        return datetime.fromisoformat(raw).strftime("%H:%M (%d/%m)")
    except ValueError:
        return raw


def _fmt_vnd(raw: object) -> str:
    if isinstance(raw, (int, float)):
        return f"{int(round(raw)):,}".replace(",", ".") + " VND"
    return f"{raw} VND"


def _fmt_num(raw: object) -> str:
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw)


def _extract_draft(state: AgentState) -> dict:
    query = state.get("query", "")
    low = query.lower()
    ctx = state.get("turn_context") or {}
    draft = dict(state.get("draft_request") or {})

    # 1. vehicle_model
    vm_match = _VEHICLE_RE.search(query)
    if vm_match:
        draft["vehicle_model"] = vm_match.group(1).upper().replace(" ", "")
    elif not draft.get("vehicle_model"):
        draft["vehicle_model"] = ctx.get("vehicle_model") or "DEMO-60"

    # 2. soc_now & soc_target (kèm kiểm tra thay đổi bất thường trong thời gian ngắn)
    now = _now_local(state)
    prev_soc_now = draft.get("soc_now")
    prev_soc_ts_raw = draft.get("_soc_now_ts")
    pcts = [float(m.group(1)) for m in _PCT_RE.finditer(query) if 0 <= int(m.group(1)) <= 100]
    if len(pcts) >= 2:
        draft["soc_now"], draft["soc_target"] = pcts[0], pcts[1]
        draft["_soc_now_ts"] = now.isoformat()
    elif len(pcts) == 1:
        val = pcts[0]
        if any(k in low for k in ("cần", "lên", "tới", "đầy", "mục tiêu", "target")):
            draft["soc_target"] = val
        elif any(k in low for k in ("còn", "hiện", "đang", "now", "h xe", "giờ xe")):
            if prev_soc_now is not None and abs(prev_soc_now - val) >= 20 and prev_soc_ts_raw:
                try:
                    elapsed_min = abs((now - datetime.fromisoformat(prev_soc_ts_raw)).total_seconds()) / 60
                    if elapsed_min <= 10:
                        draft["_soc_conflict"] = (prev_soc_now, val)
                except ValueError:
                    pass
            draft["soc_now"] = val
            draft["_soc_now_ts"] = now.isoformat()
        elif "soc_now" not in draft:
            draft["soc_now"] = val
            draft["_soc_now_ts"] = now.isoformat()
        else:
            draft["soc_target"] = val

    # 2b. zone ("AC" vs "DC" — Hybrid ADR-010)
    if any(k in low for k in ("sạc nhanh", "trụ dc", "cổng dc", " dc")):
        draft["zone"] = "DC"
    elif any(k in low for k in ("sạc chậm", "trụ ac", "cổng ac", " ac", "qua đêm")):
        draft["zone"] = "AC"

    # 3. mode ("walk_in" vs "reservation")
    if any(k in low for k in ("đang ở bãi", "vừa về", "vừa tới", "vừa đỗ", "vừa cắm", "đến ngay", "ở bãi", "walk_in")):
        draft["mode"] = "walk_in"
        draft["arrival_time"] = None
    elif any(k in low for k in ("đặt trước", "tối nay", "cắm xe", "về cắm", "sẽ tới", "reservation")):
        draft.setdefault("mode", "reservation")

    # 4. arrival_time & deadline
    times = [
        (int(m.group(1)), int(m.group(2) or 0))
        for m in _TIME_RE.finditer(query)
        if 0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2) or 0) <= 59
    ]
    has_today = any(w in low for w in ("hôm nay", "sáng nay", "trưa nay", "chiều nay", "tối nay", "đêm nay")) or bool(
        re.search(r"\bnay\b", low)
    )
    has_tomorrow = (
        "ngày mai" in low
        or "sáng mai" in low
        or "chiều mai" in low
        or "tối mai" in low
        or bool(re.search(r"\bmai\b", low))
    )
    if len(times) >= 2 and draft.get("mode") == "reservation":
        (h1, m1), (h2, m2) = times[0], times[1]
        arr_iso = _resolve_time(now, h1, m1, force_next_day="ngày kia" in low)
        arr_dt = datetime.fromisoformat(arr_iso)
        draft["arrival_time"] = arr_iso
        draft["deadline"] = _resolve_time(arr_dt, h2, m2)
    elif len(times) == 1:
        h, m = times[0]
        candidate = datetime(now.year, now.month, now.day, h, m, 0, 0, tzinfo=now.tzinfo)
        if 0 <= now.hour < 4 and has_tomorrow and not has_today:
            draft["_deadline_ambiguous"] = True
        elif (
            now.hour >= 12
            and 1 <= h <= 12
            and not has_today
            and not has_tomorrow
            and not any(w in low for w in ("sáng", "chiều", "tối", "đêm"))
        ):
            draft["_deadline_ambiguous"] = True
        elif has_today and not has_tomorrow and candidate <= now:
            draft["_deadline_past"] = True
        else:
            next_day = (has_tomorrow and not has_today) or ("sáng" in low and not has_today and now.hour >= 12)
            draft["deadline"] = _resolve_time(now, h, m, force_next_day=next_day)

    return draft


def _missing_fields(draft: dict) -> list[str]:
    missing = []
    if not draft.get("vehicle_model"):
        missing.append("mẫu xe (vd DEMO-60)")
    if draft.get("soc_now") is None:
        missing.append("% pin hiện tại")
    if draft.get("soc_target") is None:
        missing.append("% pin mong muốn")
    if not draft.get("mode"):
        missing.append("hình thức sạc (đang ở bãi hay đặt trước)")
    elif draft.get("mode") == "reservation" and not draft.get("arrival_time"):
        missing.append("giờ dự kiến cắm sạc")
    if not draft.get("deadline"):
        missing.append("giờ cần lấy xe")
    return missing


def try_deterministic_tariff_decision(query: str) -> AgentDecision | None:
    """0-RPM fast-path cho câu hỏi biểu giá điện — đọc trực tiếp từ config/tariff.yaml, không tốn LLM."""
    low = query.lower()
    if not any(
        k in low for k in ("giá điện", "biểu giá", "bao nhiêu tiền", "giờ rẻ", "thấp điểm", "cao điểm", "đơn giá")
    ):
        return None
    # Nếu cư dân đang đồng thời yêu cầu đặt lịch cụ thể (có % pin), để luồng đặt lịch xử lý.
    if _PCT_RE.search(query):
        return None

    tariff = catalog.load_tariff()
    period_labels = {"off_peak": "thấp điểm", "normal": "bình thường", "peak": "cao điểm"}

    def _fmt_price(vnd: float) -> str:
        return f"{int(round(vnd)):,}".replace(",", ".") + " VND/kWh"

    # Kiểm tra xem cư dân có hỏi 1 khung giờ cụ thể (vd "19h00", "10 tối", "10pm", "8h sáng") không
    times: list[tuple[int, int]] = []
    for m in _TIME_RE.finditer(query):
        h, mins = int(m.group(1)), int(m.group(2) or 0)
        if 0 <= h <= 23 and 0 <= mins <= 59:
            tail = low[m.end() : m.end() + 12]
            if h < 12 and any(k in tail for k in ("tối", "đêm", "chiều", "pm")):
                h += 12
            elif h == 12 and "đêm" in tail:
                h = 0
            times.append((h, mins))
    if not times:
        colloquial = re.search(
            r"\b(\d{1,2})\s*(?:giờ\s*)?(sáng|trưa|chiều|tối|đêm|am|pm)\b",
            low,
        )
        if colloquial:
            h = int(colloquial.group(1))
            meridiem = colloquial.group(2)
            if 0 <= h <= 23:
                if h < 12 and meridiem in ("chiều", "tối", "đêm", "pm"):
                    h += 12
                elif h == 12 and meridiem in ("đêm", "am"):
                    h = 0
                times.append((h, 0))
    note = f" (Lưu ý: {tariff.source}.)" if not tariff.verified else ""
    if len(times) == 1:
        h, m = times[0]
        from datetime import time as dt_time

        price = tariff.price_at(dt_time(h, m))
        matched = next(
            (
                p
                for p in tariff.periods
                if (
                    (p.start <= p.end and p.start <= dt_time(h, m) < p.end)
                    or (p.start > p.end and (dt_time(h, m) >= p.start or dt_time(h, m) < p.end))
                )
            ),
            None,
        )
        if matched:
            label = period_labels.get(matched.name, matched.name)
            answer = (
                f"Lúc {h:02d}:{m:02d} thuộc khung giờ {label} ({matched.start.strftime('%H:%M')}–{matched.end.strftime('%H:%M')}), "
                f"đơn giá là {_fmt_price(price)}. Biểu giá áp dụng theo khung giờ chung của trạm cho cả trụ AC và DC.{note}"
            )
        else:
            answer = f"Đơn giá lúc {h:02d}:{m:02d} là {_fmt_price(price)} (áp dụng chung cho cả AC và DC).{note}"
    else:
        lines = [
            f"• {period_labels.get(p.name, p.name).capitalize()} ({p.start.strftime('%H:%M')}–{p.end.strftime('%H:%M')}): {_fmt_price(p.price_per_kwh)}"
            for p in tariff.periods
        ]
        answer = (
            "Biểu giá điện tại trạm áp dụng theo khung giờ (chung cho cả trụ AC và DC):\n"
            + "\n".join(lines)
            + f"\nKhung rẻ nhất là 22:00–04:00 (1.200 VND/kWh).{note}"
        )

    return AgentDecision(
        thought="Câu hỏi biểu giá điện → trả lời trực tiếp từ config/tariff.yaml (0 RPM).",
        action="final",
        enough_data=True,
        final_answer=answer,
        suggestions=["Đang ở bãi, sạc AC", "Đang ở bãi, sạc nhanh DC", "Hẹn 22:00, sạc AC"],
    )


async def mock_reason(state: AgentState) -> AgentDecision:
    """Bước reason giả lập — hỗ trợ đủ 6 tool sạc và hội thoại nhiều lượt."""
    trace = state.get("tool_trace") or []
    if trace:
        return AgentDecision(
            thought="Đã có kết quả tool ở lượt này, chuyển sang tổng hợp câu trả lời.",
            action="final",
            enough_data=True,
            final_answer="Đã tổng hợp kết quả từ hệ thống.",
        )

    query = state.get("query", "")
    low = query.lower()

    # 0. Biểu giá điện (0 RPM, đọc từ config/tariff.yaml)
    tariff_decision = try_deterministic_tariff_decision(query)
    if tariff_decision is not None:
        return tariff_decision

    # 0b. Không thể gộp/mix AC và DC trong cùng một phiên
    if ("ac" in low and "dc" in low) and any(
        k in low for k in ("mix", "kết hợp", "gộp", "vừa ac vừa dc", "cả ac và dc")
    ):
        return AgentDecision(
            thought="Cư dân hỏi gộp AC và DC trong cùng một phiên — hai trụ khác nhau về vật lý.",
            action="final",
            enough_data=True,
            final_answer=(
                "Mỗi lịch sạc chỉ gắn với một trụ duy nhất (AC hoặc DC) vì trụ AC (11 kW) và trụ DC (60 kW) "
                "nằm ở hai vị trí đỗ và đầu cắm khác nhau, không thể tự động chuyển đổi giữa phiên. "
                "Bạn muốn chọn sạc AC tiết kiệm hay sạc nhanh DC nhé?"
            ),
            suggestions=["Đang ở bãi, sạc AC", "Đang ở bãi, sạc nhanh DC"],
        )

    # 1. Hàng đợi (US2)
    if any(k in low for k in ("hàng đợi", "xếp thứ mấy", "chờ bao lâu", "queue")):
        return AgentDecision(
            thought="Cư dân hỏi vị trí hàng đợi → gọi get_queue_status.",
            action="tool",
            tool_name="get_queue_status",
            tool_args={},
            enough_data=True,
        )

    # 2. Giải thích lịch (US3) hoặc đổi giờ khi chưa có lịch
    if any(k in low for k in ("vì sao", "tại sao", "sao lịch", "bị lùi", "giải thích", "explain")):
        return AgentDecision(
            thought="Cư dân hỏi lý do xếp lịch → gọi explain_schedule.",
            action="tool",
            tool_name="explain_schedule",
            tool_args={},
            enough_data=True,
        )

    if (
        any(k in low for k in ("đổi giờ", "sửa lịch", "dời lịch"))
        and not state.get("draft_request")
        and not state.get("history")
    ):
        draft = _extract_draft(state)
        return AgentDecision(
            thought="Cư dân yêu cầu đổi giờ nhưng chưa có lịch sạc nào đang giữ hoặc bản nháp trước đó.",
            action="final",
            enough_data=True,
            draft_request=draft,
            final_answer="Hiện bạn chưa có lịch sạc nào để đổi. Bạn có muốn đặt lịch mới với giờ lấy xe này không? Nếu có, cho mình biết thêm % pin hiện tại, % mục tiêu, vùng sạc (AC/DC) và thời điểm đến bãi nhé.",
            suggestions=["Đặt lịch sạc mới", "Đang ở bãi, sạc nhanh DC", "Đang ở bãi, sạc AC"],
        )

    # 3. Tra thông số mẫu xe
    if any(k in low for k in ("tra thông số", "tra giúp", "tra xe", "thông số xe", "danh mục xe", "lookup")):
        vm = _VEHICLE_RE.search(query)
        model_code = vm.group(1).upper().replace(" ", "") if vm else ""
        return AgentDecision(
            thought="Tra danh mục xe bằng lookup_vehicle.",
            action="tool",
            tool_name="lookup_vehicle",
            tool_args={"vehicle_model": model_code},
            enough_data=True,
        )

    # 4. Yêu cầu vượt quyền điều khiển trạm (FR5), ngoài phạm vi hoặc xâm phạm riêng tư cư dân khác
    if any(
        k in low
        for k in (
            "tăng công suất",
            "hạ công suất",
            "ngắt cột",
            "mở cột",
            "thời tiết",
            "là của ai",
            "mấy giờ họ rút",
            "xe của ai",
            "căn 1203",
        )
    ):
        return AgentDecision(
            thought="Yêu cầu nằm ngoài phạm vi hỗ trợ hoặc vi phạm quyền riêng tư / điều khiển trạm (FR5).",
            action="final",
            enough_data=True,
            final_answer=(
                "Mình không thể thực hiện yêu cầu này vì nằm ngoài phạm vi trợ lý đặt lịch sạc "
                "hoặc liên quan đến điều khiển trực tiếp trạm sạc / thông tin riêng tư của cư dân khác."
            ),
        )

    draft = _extract_draft(state)

    # 4b. Kiểm tra mẫu xe ngoài danh mục, hạn đã qua hoặc giờ mơ hồ
    vehicles = catalog.load_vehicle_catalog()
    if draft.get("vehicle_model") and draft["vehicle_model"] not in vehicles:
        bad_vm = draft.pop("vehicle_model")
        valid_list = ", ".join(sorted(vehicles))
        return AgentDecision(
            thought=f"Mẫu xe {bad_vm} không có trong danh mục.",
            action="final",
            enough_data=True,
            draft_request=draft,
            final_answer=(
                f"Mẫu xe {bad_vm} không có trong danh mục hỗ trợ (mẫu hợp lệ: {valid_list}). "
                "Bạn vui lòng cho mình xin lại mẫu xe hợp lệ nhé?"
            ),
        )

    if draft.pop("_deadline_past", False):
        return AgentDecision(
            thought="Hạn lấy xe đã qua so với thời điểm hiện tại.",
            action="final",
            enough_data=True,
            draft_request=draft,
            final_answer="Giờ lấy xe bạn chọn đã qua so với thời điểm hiện tại (không hợp lệ). Bạn cho mình xin lại giờ lấy xe nhé?",
        )

    if draft.pop("_deadline_ambiguous", False):
        return AgentDecision(
            thought="Giờ lấy xe mơ hồ (sáng hay tối / hôm nay hay ngày mai).",
            action="final",
            enough_data=True,
            draft_request=draft,
            final_answer="Giờ lấy xe bạn nêu còn mơ hồ (sáng hay tối / hôm nay hay ngày mai). Bạn xác nhận rõ thời điểm lấy xe giúp mình nhé?",
            suggestions=["07:00 sáng mai", "20:00 tối nay", "06:30 sáng mai"],
        )

    conflict = draft.pop("_soc_conflict", None)
    if conflict:
        old_soc, new_soc = conflict
        return AgentDecision(
            thought=f"% pin hiện tại thay đổi bất thường trong vài phút ({old_soc:g}% -> {new_soc:g}%).",
            action="final",
            enough_data=True,
            draft_request=draft,
            final_answer=(
                f"Vừa nãy bạn báo pin đang {old_soc:g}%, giờ lại báo {new_soc:g}%. "
                f"Bạn xác nhận giúp mình là muốn cập nhật pin hiện tại thành {new_soc:g}% và cần sạc lên bao nhiêu % nhé?"
            ),
            suggestions=[
                f"Pin hiện tại {new_soc:g}%, cần lên 80%",
                f"Pin hiện tại {new_soc:g}%, sạc nhanh DC lên 80%",
                f"Giữ pin hiện tại {old_soc:g}%",
            ],
        )

    # 5. Tính điện năng riêng (FR3)
    if any(k in low for k in ("tính kwh", "bao nhiêu kwh", "ước tính điện", "điện năng")) and (
        draft.get("vehicle_model") and draft.get("soc_now") is not None and draft.get("soc_target") is not None
    ):
        return AgentDecision(
            thought="Tính kWh bằng tool estimate_charging_energy.",
            action="tool",
            tool_name="estimate_charging_energy",
            tool_args={
                "vehicle_model": draft["vehicle_model"],
                "soc_now": draft["soc_now"],
                "soc_target": draft["soc_target"],
            },
            enough_data=True,
            draft_request=draft,
        )

    missing = _missing_fields(draft)

    # 6. Chốt lịch (RISKY → HITL màn S3)
    if any(k in low for k in ("chốt", "xác nhận", "đặt lịch này", "confirm", "book")) and not missing:
        return AgentDecision(
            thought="Cư dân yêu cầu chốt lịch → gọi confirm_booking (chờ xác nhận HITL ở màn S3).",
            action="tool",
            tool_name="confirm_booking",
            tool_args={"request": draft},
            enough_data=True,
            draft_request=draft,
        )

    # 7. Đủ 6 trường → kiểm tra hợp lệ cơ bản rồi gọi propose_charging_plan
    if not missing:
        if draft["soc_target"] <= draft["soc_now"]:
            return AgentDecision(
                thought="soc_target <= soc_now không hợp lệ.",
                action="final",
                enough_data=True,
                draft_request=draft,
                final_answer=(
                    f"Mức pin mong muốn ({draft['soc_target']:g}%) phải lớn hơn mức pin hiện tại "
                    f"({draft['soc_now']:g}%). Bạn vui lòng cho mình xin lại mức pin nhé?"
                ),
            )
        return AgentDecision(
            thought="Đã đủ 6 trường yêu cầu sạc → gọi propose_charging_plan.",
            action="tool",
            tool_name="propose_charging_plan",
            tool_args={"request": draft},
            enough_data=True,
            draft_request=draft,
        )

    # 8. Còn thiếu trường → hỏi lại cư dân (FR2) + gợi ý 1 chạm (ưu tiên AC/DC theo quỹ thời gian deadline - now)
    ask = ", ".join(missing)
    prefer_dc = False
    if draft.get("deadline"):
        try:
            dl_dt = datetime.fromisoformat(str(draft["deadline"]))
            prefer_dc = (dl_dt - _now_local(state)).total_seconds() <= 2.5 * 3600
        except ValueError:
            prefer_dc = False

    quick: list[str] = []
    if draft.get("soc_now") is None:
        # Option B: KHÔNG ép/đoán % pin hiện tại trong gợi ý 1 chạm.
        # Chỉ gợi ý các trường rời rạc (mode/zone/deadline) còn thiếu; nếu chỉ thiếu soc_now thì để trống để cư dân tự nhập/nói.
        if not draft.get("mode") or not draft.get("zone"):
            quick = (
                ["Đang ở bãi, sạc nhanh DC", "Đang ở bãi, sạc AC", "Hẹn 22:00, sạc AC"]
                if prefer_dc
                else ["Đang ở bãi, sạc AC", "Đang ở bãi, sạc nhanh DC", "Hẹn 22:00, sạc AC"]
            )
        elif not draft.get("deadline"):
            quick = ["Lấy 07:00 mai", "Lấy 06:30 mai", "Lấy 18:00 nay"]
        else:
            quick = []
    elif not draft.get("mode"):
        quick = (
            ["Đang ở bãi, sạc nhanh DC", "Đang ở bãi, sạc AC", "Hẹn 22:00, sạc AC"]
            if prefer_dc
            else ["Đang ở bãi, sạc AC", "Đang ở bãi, sạc nhanh DC", "Hẹn 22:00, sạc AC"]
        )
    elif draft.get("soc_target") is None:
        quick = ["Mục tiêu 80%", "Sạc đầy 100%", "Mục tiêu 90%"]
    elif not draft.get("deadline"):
        quick = ["Lấy 07:00 mai", "Lấy 06:30 mai", "Lấy 18:00 nay"]
    return AgentDecision(
        thought=f"Thiếu thông tin: {ask} → hỏi lại cư dân.",
        action="final",
        enough_data=True,
        draft_request=draft,
        final_answer=f"Để xếp lịch sạc chuẩn xác, bạn cho mình biết thêm: {ask} nhé?",
        suggestions=quick,
    )


async def mock_generate(state: AgentState, partial: bool = False) -> FinalAnswer:
    """Bước finalize giả lập — chỉ chép số liệu có trong tool_trace."""
    trace = state.get("tool_trace") or []
    used_tools = [t["tool"] for t in trace]

    if not trace:
        decision = state.get("last_decision") or {}
        draft_ans = decision.get("final_answer") or "Mình có thể giúp gì cho lịch sạc của bạn?"
        return FinalAnswer(
            answer=draft_ans,
            confidence=0.95,
            used_tools=[],
            suggestions=list(decision.get("suggestions") or []),
        )

    last = trace[-1]
    tool_name = last["tool"]
    raw_output = str(last["output"])

    if raw_output == "BLOCKED_BY_HUMAN":
        return FinalAnswer(
            answer="Đã huỷ thao tác chốt lịch theo lựa chọn của bạn. Bạn muốn điều chỉnh giờ lấy xe hay mức pin mục tiêu không?",
            confidence=1.0,
            used_tools=used_tools,
        )
    if raw_output.startswith("TOOL_ERROR"):
        return FinalAnswer(
            answer=f"Hiện chưa thực hiện được thao tác ({raw_output}). Bạn vui lòng kiểm tra lại hoặc thử lại sau nhé.",
            confidence=0.8,
            used_tools=used_tools,
        )

    try:
        data = json.loads(raw_output)
    except ValueError:
        return FinalAnswer(answer=raw_output, confidence=0.9, used_tools=used_tools)

    if tool_name == "propose_charging_plan" and isinstance(data, dict):
        energy = data.get("energy") or {}
        bat_kwh = round(float(energy.get("battery_energy_kwh") or 0), 1)
        grid_kwh = round(float(energy.get("grid_energy_kwh") or 0), 1)
        if data.get("feasible"):
            conditional = (
                " Lưu ý: kết quả còn phụ thuộc phê duyệt đang chờ, có thể đổi khi được duyệt."
                if data.get("certainty") == "conditional"
                else ""
            )
            return FinalAnswer(
                answer=(
                    f"Phương án đề xuất (ước tính): sạc tại đầu nối {data.get('connector_id')}, "
                    f"từ {_fmt_dt(data.get('planned_start'))} đến {_fmt_dt(data.get('planned_end'))}, "
                    f"nạp {bat_kwh} kWh vào pin ({grid_kwh} kWh từ lưới), "
                    f"chi phí ước tính {_fmt_vnd(data.get('estimated_cost_vnd'))} "
                    f"(dư {_fmt_num(data.get('slack_minutes'))} phút trước hạn).{conditional} "
                    "Bạn nhắn 'chốt' để xác nhận đặt lịch nhé."
                ),
                confidence=0.95,
                used_tools=used_tools,
                suggestions=["Chốt lịch này", "Đổi sang sạc nhanh DC", "Đổi giờ lấy xe 06:30"],
            )
        alts = "; ".join(a.get("description", "") for a in data.get("alternatives") or [])
        return FinalAnswer(
            answer=(f"Yêu cầu nạp {bat_kwh} kWh không kịp hạn lấy xe. Phương án thay thế: {alts}."),
            confidence=0.95,
            used_tools=used_tools,
        )

    if tool_name == "confirm_booking" and isinstance(data, dict):
        energy = data.get("energy") or {}
        bat_kwh = round(float(energy.get("battery_energy_kwh") or 0), 1)
        grid_kwh = round(float(energy.get("grid_energy_kwh") or 0), 1)
        return FinalAnswer(
            answer=(
                f"Đã chốt lịch sạc {data.get('booking_id')} ({data.get('status')}) tại đầu nối {data.get('connector_id')}, "
                f"khung giờ {_fmt_dt(data.get('planned_start'))} – {_fmt_dt(data.get('planned_end'))}, "
                f"điện năng {bat_kwh} kWh (lưới {grid_kwh} kWh), "
                f"chi phí ước tính {_fmt_vnd(data.get('estimated_cost_vnd'))}."
            ),
            confidence=0.98,
            used_tools=used_tools,
        )

    if tool_name == "estimate_charging_energy" and isinstance(data, dict):
        return FinalAnswer(
            answer=(
                f"Xe {data.get('vehicle_model')} sạc từ {data.get('soc_now')}% lên {data.get('soc_target')}% "
                f"cần nạp {data.get('battery_energy_kwh')} kWh vào pin "
                f"({data.get('grid_energy_kwh')} kWh từ lưới, hiệu suất {data.get('efficiency')})."
            ),
            confidence=0.98,
            used_tools=used_tools,
        )

    if tool_name == "lookup_vehicle" and isinstance(data, dict):
        if "error" in data:
            valid = ", ".join(data.get("valid_models") or [])
            return FinalAnswer(
                answer=f"Không tìm thấy mẫu xe {data.get('vehicle_model')}. Các mẫu hợp lệ: {valid}.",
                confidence=0.95,
                used_tools=used_tools,
            )
        return FinalAnswer(
            answer=(
                f"Mẫu xe {data.get('vehicle_model')} ({data.get('display_name')}): "
                f"pin khả dụng {data.get('usable_capacity_kwh')} kWh, sạc AC tối đa {data.get('max_ac_power_kw')} kW."
            ),
            confidence=0.98,
            used_tools=used_tools,
        )

    if tool_name == "get_queue_status" and isinstance(data, dict):
        pos = data.get("position")
        qlen = data.get("queue_length", 0)
        if pos is None:
            return FinalAnswer(
                answer=f"Bạn hiện không ở trong hàng đợi (tổng hàng đợi hiện tại: {qlen} xe).",
                confidence=0.95,
                used_tools=used_tools,
            )
        return FinalAnswer(
            answer=f"Bạn đang ở vị trí thứ {pos}/{qlen} trong hàng đợi (chờ dự kiến {data.get('estimated_wait_minutes')} phút).",
            confidence=0.95,
            used_tools=used_tools,
        )

    if tool_name == "explain_schedule" and isinstance(data, list):
        return FinalAnswer(
            answer=" ".join(str(item) for item in data),
            confidence=0.95,
            used_tools=used_tools,
        )

    return FinalAnswer(answer=raw_output, confidence=0.9, used_tools=used_tools)
