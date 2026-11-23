"""Guardrails 2 lớp — code layer validation cho mọi input/output của agent.

Vì sao tồn tại: template cũ không có guardrail — LLM nói gì thì chạy cái đó.
Thiết kế theo good practice #12 (Guardrails class của team 008 Buddy) và
#4 (schema-first Pydantic của team 012 ResearchKit):

  Lớp 1 (input):  check_input() — chặn prompt injection cơ bản bằng regex
                  trước khi query chạm vào LLM.
  Lớp 2 (output): validate_output() — mọi output LLM phải qua Pydantic
                  schema; sai schema là BỊA, phải fail loudly.

Nguyên tắc BẮT BUỘC: mọi except → log "FAILED" + raise. KHÔNG silent
fallback (như return "{}" rồi cho qua). Bài học RCA team 002: một except
im lặng che mất lỗi schema suốt 2 tuần — eval vẫn xanh vì agent fallback
về câu trả lời canned. Fail loud ngay tại chỗ sai > fail im lặng rồi
phát hiện lúc demo.
"""

from __future__ import annotations

import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("ai20k.guardrails")

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class GuardrailViolation(Exception):  # noqa: N818 — giữ tên theo pattern team 008, "violation" chính xác hơn "error"
    """Input/output vi phạm guardrail — caller PHẢI xử lý tường minh."""

    def __init__(self, violation_type: str, detail: str):
        self.violation_type = violation_type
        self.detail = detail
        super().__init__(f"[{violation_type}] {detail}")


# Prompt injection patterns — lớp phòng thủ ĐẦU (không thay thế được
# prompt hardening + least-privilege tools, nhưng chặn được payload phổ biến).
BANNED_INPUT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "prompt_injection_ignore_previous",
        re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?)", re.I),
    ),
    (
        "prompt_injection_reveal_system",
        re.compile(r"(reveal|show|print|repeat)\s+(me\s+)?(your\s+)?(system|developer)\s+(prompt|instructions?)", re.I),
    ),
    ("prompt_injection_disregard", re.compile(r"disregard\s+(all\s+)?(previous|your)\s+(instructions?|rules?)", re.I)),
    (
        "prompt_injection_new_instructions",
        re.compile(r"(from\s+now\s+on|you\s+are\s+now)\s+(you\s+are\s+)?(DAN|a\s+different|an?\s+unrestricted)", re.I),
    ),
    # ChargePilot — cư dân chat tiếng Việt. Chỉ chặn mẫu injection RÕ RÀNG; yêu cầu vượt quyền kiểu
    # "tăng công suất cột A03" KHÔNG chặn bằng regex (dễ chặn oan câu hỏi hợp lệ) mà bằng cấu trúc:
    # Agent không có tool nào ra lệnh trạm (FR5) + prompts/charging_safeguards.md + eval nhóm out_of_scope.
    (
        "prompt_injection_vi_ignore",
        re.compile(
            r"(bỏ qua|phớt lờ|quên)\s+(hết\s+|tất cả\s+|mọi\s+)?(các\s+)?(hướng dẫn|chỉ dẫn|chỉ thị|quy tắc)"
            r"\s+(trước|ở trên|phía trên|bên trên|cũ|của bạn|hệ thống)",
            re.I,
        ),
    ),
    (
        "prompt_injection_vi_reveal",
        re.compile(
            r"(in ra|hiển thị|cho\s+(tôi\s+|mình\s+)?xem|tiết lộ|lặp lại)\s+(toàn bộ\s+|nguyên văn\s+)?"
            r"(system prompt|prompt hệ thống|lời nhắc hệ thống|chỉ dẫn hệ thống)",
            re.I,
        ),
    ),
    (
        "data_exfiltration_tool_abuse",
        re.compile(r"(send|post|upload)\s+(all\s+)?(the\s+)?(system\s+prompt|api\s*key|secret)", re.I),
    ),
)

# Output không được chứa — chống agent tự lộ system prompt / key khi bị dí.
BANNED_OUTPUT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("system_prompt_leak", re.compile(r"you\s+are\s+an?\s+AI\s+assistant\s+that\s+was\s+instructed", re.I)),
    ("api_key_leak", re.compile(r"sk-[A-Za-z0-9]{20,}")),
)


class Guardrails:
    """Guardrails class tập trung — một chỗ duy nhất để audit an toàn.

    Theo team 008: check_input / check_output tách bạch, mỗi violation
    có type string để test + eval đếm được theo loại.
    """

    def check_input(self, text: str) -> None:
        """Lớp 1a — validate input của USER. Raise GuardrailViolation nếu chặn.

        Raises:
            GuardrailViolation: query chứa payload prompt injection đã biết.
        """
        for violation_type, pattern in BANNED_INPUT_PATTERNS:
            match = pattern.search(text)
            if match:
                logger.warning("FAILED check_input [%s] matched=%r", violation_type, match.group(0))
                raise GuardrailViolation(
                    violation_type,
                    f"Input khớp pattern cấm {violation_type}: {match.group(0)!r}",
                )

    def check_output_text(self, text: str) -> None:
        """Lớp 1b — validate TEXT cuối trước khi trả user (leak system prompt/key)."""
        for violation_type, pattern in BANNED_OUTPUT_PATTERNS:
            match = pattern.search(text)
            if match:
                logger.warning("FAILED check_output_text [%s] matched=%r", violation_type, match.group(0))
                raise GuardrailViolation(violation_type, f"Output chứa nội dung cấm: {match.group(0)!r}")

    def check_grounded_numbers(self, answer: str, tool_trace: list[dict]) -> None:
        """Lớp 3 (ChargePilot, FR3) — mọi con số kWh / mã đầu nối trong câu trả lời phải có trong tool trace.

        Vi phạm → raise GuardrailViolation("ungrounded_number", …).
        """
        corpus = " ".join(f"{t.get('args', '')} {t.get('output', '')}" for t in tool_trace)
        trace_numbers = {round(float(n.replace(",", ".")), 2) for n in re.findall(r"\d+(?:[.,]\d+)?", corpus)}

        for raw_kwh in re.findall(r"(\d+(?:[.,]\d+)?)\s*kwh\b", answer, flags=re.I):
            val = round(float(raw_kwh.replace(",", ".")), 2)
            if not any(abs(val - t) <= 0.11 for t in trace_numbers):
                logger.warning("FAILED check_grounded_numbers ungrounded kWh=%s", raw_kwh)
                raise GuardrailViolation(
                    "ungrounded_number",
                    f"Số điện năng {raw_kwh} kWh không xuất hiện trong kết quả tool (FR3: cấm tự tính kWh)",
                )

        for conn in re.findall(r"\b([AD]\d{2})\b", answer):
            if conn not in corpus:
                logger.warning("FAILED check_grounded_numbers ungrounded connector=%s", conn)
                raise GuardrailViolation(
                    "ungrounded_number",
                    f"Mã đầu nối {conn} không xuất hiện trong kết quả tool",
                )

    def validate_output(self, raw: object, schema: type[SchemaT], source: str) -> SchemaT:
        """Lớp 2 — ép mọi output qua Pydantic schema (schema-first, team 012).

        Args:
            raw: output cần validate (thường là dict/object từ LLM).
            schema: Pydantic model class.
            source: tên node/tool sinh ra output — để log truy được nguồn lỗi.

        Raises:
            ValidationError: propagate nguyên vẹn sau khi log FAILED —
                KHÔNG fallback về giá trị mặc định (xem RCA team 002 ở
                docstring module).
        """
        try:
            validated = schema.model_validate(raw)
        except ValidationError as exc:
            logger.error(
                "FAILED validate_output source=%s schema=%s errors=%s",
                source,
                schema.__name__,
                exc.errors(include_url=False),
            )
            raise  # re-raise nguyên vẹn — không nuốt, không sửa
        logger.info("OK validate_output source=%s schema=%s", source, schema.__name__)
        return validated


# Instance dùng chung toàn app (một chỗ để monkeypatch khi test).
guardrails = Guardrails()
