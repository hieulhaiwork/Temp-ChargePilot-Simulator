"""Typed adapters for the application-owned Copilot service."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from src.models.api import UserProfile
from src.models.control import Role
from src.models.copilot_integration import (
    CopilotModel,
    CopilotNotice,
    HowToRequest,
    JobReply,
    WhatIfIntent,
    WhyIntent,
    WhyReply,
)
from src.services.copilot.integration import CopilotIntegration


@dataclass(frozen=True)
class ChatContext:
    user: UserProfile
    session: str
    copilot: CopilotIntegration | None


class JobLookup(CopilotModel):
    job_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    operation: Literal["status", "cancel"] = "status"


COPILOT_TOOLS = {
    "copilot_why": (WhyIntent, "Giải thích quyết định có dấu vết, theo đúng vai trò và thời điểm."),
    "copilot_what_if": (WhatIfIntent, "Mô phỏng một thay đổi đã xác định. Trả trạng thái tác vụ."),
    "copilot_how_to": (
        HowToRequest,
        "Kiểm chứng các phương án trong mục tiêu, giới hạn và quyền đánh đổi đã xác nhận.",
    ),
    "copilot_job": (JobLookup, "Xem trạng thái/kết quả hoặc huỷ tác vụ trong phiên chat này."),
}
SIMULATION_TOOLS = frozenset({"copilot_what_if", "copilot_how_to"})
MAX_COPILOT_TOOL_CALLS = 4
MAX_SIMULATIONS_PER_TURN = 1


def tool_schema(name: str, role: Role) -> dict:
    model = COPILOT_TOOLS[name][0]
    schema = model.model_json_schema()
    if name == "copilot_what_if":
        change = schema["properties"]["change"]
        allowed = {"revise_vehicle"} if role == Role.RESIDENT else {"site_limit", "outage"}
        mapping = change["discriminator"]["mapping"]
        change["discriminator"]["mapping"] = {op: ref for op, ref in mapping.items() if op in allowed}
        change["oneOf"] = [{"$ref": ref} for ref in change["discriminator"]["mapping"].values()]
    elif name == "copilot_how_to":
        goal = schema["properties"]["goal"]
        mapping = goal["discriminator"]["mapping"]
        goal["discriminator"]["mapping"] = {
            key: ref
            for key, ref in mapping.items()
            if (key == "min_tested_site_limit_for_sla") == (role == Role.OPERATOR)
        }
        goal["oneOf"] = [{"$ref": ref} for ref in goal["discriminator"]["mapping"].values()]
    elif name == "copilot_why":
        schema["properties"]["subject"]["enum"] = (
            ["own_booking", "booking"] if role == Role.RESIDENT else ["station", "booking"]
        )
    if "$defs" in schema:
        # Only advertise variant contracts that can be reached from this role's arguments.
        definitions = schema.pop("$defs")
        referenced = json.dumps(schema)
        included = {}
        while unused := {
            key: definition
            for key, definition in definitions.items()
            if key not in included and f'"#/$defs/{key}"' in referenced
        }:
            included.update(unused)
            referenced = json.dumps(unused)
        schema["$defs"] = included
    return schema


async def invoke_copilot_tool(
    name: str,
    args: dict,
    context: ChatContext,
    *,
    message: str,
    prior_user_messages: Sequence[str] = (),
    pending_clarify_field: str | None = None,
) -> WhyReply | JobReply | CopilotNotice:
    service = context.copilot
    if service is None:
        return CopilotNotice(code="structured_fallback", message="Trợ lý phân tích chưa sẵn sàng.")
    model = COPILOT_TOOLS[name][0]
    value = model.model_validate(args)
    match value:
        case WhyIntent():
            return await service.agent_why(
                context.user,
                value,
                message=message,
                prior_user_messages=prior_user_messages,
                pending_clarify_field=pending_clarify_field,
            )
        case WhatIfIntent():
            return await service.agent_what_if(
                context.user,
                value,
                context.session,
                message=message,
                prior_user_messages=prior_user_messages,
                pending_clarify_field=pending_clarify_field,
            )
        case HowToRequest():
            return await service.agent_how_to(
                context.user,
                value,
                context.session,
                message=message,
                prior_user_messages=prior_user_messages,
                pending_clarify_field=pending_clarify_field,
            )
        case JobLookup():
            return service.job(context.user, value.job_id, session=context.session, cancel=value.operation == "cancel")
    raise ValueError("Unknown Copilot tool")
