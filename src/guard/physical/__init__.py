"""Physical Guard — kiểm HARD CONSTRAINTS vật lý, độc lập với LLM, policy và HITL (ADR-017, ADR-019).

    validator.py   Physical Guard gốc của simulator MVP-1/2/3: validate_dispatch, validate_budgets, guard,
                   validate_response. Chỉ import src.models (stdlib) — simulator standalone và backend gọi CÙNG
                   implementation này.
    adapter.py     map StationConfig / StationState / Command của backend → validator (check_connector_allocation,
                   check_site_allocation, check_dispatch). Kéo theo Pydantic — chỉ backend dùng, import thẳng
                   `src.guard.physical.adapter`.

Gói này chỉ nạp `validator` lúc import, để simulator standalone không chạm stack backend. Business Guard (luật,
consent, HITL, dispatcher) ở `src/guard/*.py`, không ở đây.
"""

from src.guard.physical.validator import guard, valid_kw, validate_budgets, validate_dispatch, validate_response

__all__ = ["guard", "valid_kw", "validate_budgets", "validate_dispatch", "validate_response"]
