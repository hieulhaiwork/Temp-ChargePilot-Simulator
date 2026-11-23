"""Physical Guard — kiểm HARD CONSTRAINTS vật lý, độc lập với LLM, policy và HITL (ADR-017, ADR-019).

    validator.py   Physical Guard gốc của simulator MVP-1/2/3 (chuyển nguyên văn từ src/simulator/src/safety/guard.py):
                   validate_dispatch, validate_budgets, guard, validate_response. Chỉ import src.models (stdlib) —
                   simulator standalone và backend gọi CÙNG implementation này.
    adapter.py     map StationConfig / StationState / Command của backend → validator (check_connector_allocation,
                   check_site_allocation, check_dispatch). Kéo theo Pydantic — chỉ backend dùng.

Gói này chỉ nạp `validator` lúc import, để simulator standalone không chạm stack backend. Business Guard (luật,
consent, HITL, dispatcher) ở `src/guard/*.py`, không ở đây.
"""

from src.guard.physical.validator import guard, valid_kw, validate_budgets, validate_dispatch, validate_response

__all__ = ["guard", "valid_kw", "validate_budgets", "validate_dispatch", "validate_response"]

# Tên công khai của `src/guard/physical.py` cũ (trước Phase 2), nay ở `adapter.py`.
_ADAPTER_NAMES = {
    "EMPTY_PREFIX",
    "check_connector_allocation",
    "check_dispatch",
    "check_site_allocation",
    "effective_limits",
    "simulator_guard",
}


def __getattr__(name: str):
    """Tương thích tạm (ADR-019 Phase 2, xoá ở Phase 6): `from src.guard.physical import check_dispatch` vẫn chạy.

    Chỉ nạp `adapter` (Pydantic) khi truy cập đúng các tên cũ; consumer trong repo đã import thẳng `adapter`.
    """
    if name in _ADAPTER_NAMES:
        from src.guard.physical import adapter

        return getattr(adapter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
