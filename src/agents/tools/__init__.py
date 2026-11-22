"""Tool registry — MỘT chỗ duy nhất liệt kê tool agent được dùng.

Vì sao tồn tại: reason node cần biết tool hợp lệ để validate quyết định
của LLM (LLM bịa tên tool → fail loudly thay vì KeyError ở xa chỗ lỗi).
Tool rủi ro đánh dấu qua RISKY_TOOL_NAMES để graph route HITL.

ChargePilot: tool nghiệp vụ sạc ở charging.py (F1). Bốn tool demo của template vẫn
giữ vì harness tests (test_graph, test_hitl, test_routes) và eval/run_eval.py đang dùng
chúng. T2.5: khi tool sạc chạy thật → chuyển các test đó sang tool sạc rồi gỡ demo,
để LLM không bị phân tâm bởi tool không liên quan.
"""

from src.agents.tools.charging import (
    confirm_booking,
    estimate_charging_energy,
    explain_schedule,
    get_queue_status,
    lookup_vehicle,
    propose_charging_plan,
)
from src.agents.tools.knowledge import calculate, search_knowledge
from src.agents.tools.mcp_tool import mcp_knowledge_lookup
from src.agents.tools.risky_tools import RISKY_TOOL_NAMES, send_email

TOOL_REGISTRY: dict = {
    # ChargePilot F1 (T2.5)
    "lookup_vehicle": lookup_vehicle,
    "estimate_charging_energy": estimate_charging_energy,
    "propose_charging_plan": propose_charging_plan,
    "confirm_booking": confirm_booking,
    "get_queue_status": get_queue_status,
    "explain_schedule": explain_schedule,
    # Demo của template — gỡ ở T2.5
    "search_knowledge": search_knowledge,
    "calculate": calculate,
    "mcp_knowledge_lookup": mcp_knowledge_lookup,
    "send_email": send_email,
}

# Ẩn khỏi prompt của LLM (describe_tools) — chỉ còn để test harness dùng. Gỡ hẳn ở T2.5 khi T2.2 xong.
TEMPLATE_DEMO_TOOL_NAMES = frozenset({"search_knowledge", "calculate", "mcp_knowledge_lookup", "send_email"})

__all__ = [
    "TOOL_REGISTRY",
    "RISKY_TOOL_NAMES",
    "TEMPLATE_DEMO_TOOL_NAMES",
    "lookup_vehicle",
    "estimate_charging_energy",
    "propose_charging_plan",
    "confirm_booking",
    "get_queue_status",
    "explain_schedule",
    "search_knowledge",
    "calculate",
    "mcp_knowledge_lookup",
    "send_email",
]
