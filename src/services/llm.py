"""LLM router — chọn NHÀ CUNG CẤP (openai | local | mock) và MODEL theo loại việc.

Đổi nhà cung cấp = đổi `LLM_PROVIDER` trong .env, không sửa code:

- openai: gọi API OpenAI. Cascade theo task — model rẻ cho classify, model mạnh cho generate.
- local:  server OpenAI-compatible tự host (Ollama, vLLM, LM Studio… trên VM). Cùng client ChatOpenAI,
          chỉ khác `base_url` — nên lỗi kết nối vẫn là OpenAIError → routes trả 503 như API thật.
- mock:   KHÔNG có LLM. Graph dùng bộ não luật cố định ở src/agents/mock_llm.py (xem graph.py).
          Gọi get_llm() khi mock là bug → raise ngay.

Task type:
- "classify": reason node / routing — temperature 0
- "generate": câu trả lời cuối
- "judge":    chấm eval — PHẢI khác model generate (self-preference bias, bài học team 002)
"""

from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.config import Settings, get_settings

TaskType = Literal["classify", "generate", "judge"]


def _model_name(settings: Settings, task_type: TaskType) -> str:
    if settings.llm_provider == "local":
        return settings.local_llm_judge_model if task_type == "judge" else settings.local_llm_model
    return {"classify": settings.model_classify, "generate": settings.model_generate, "judge": settings.model_judge}[
        task_type
    ]


def get_llm(task_type: TaskType = "generate") -> BaseChatModel:
    """LLM cho một loại task, theo LLM_PROVIDER hiện hành.

    Raises:
        RuntimeError: LLM_PROVIDER=mock (không có LLM thật để trả về).
        ValueError: judge trùng model generate (hoặc chưa cấu hình judge local).
    """
    settings = get_settings()
    if settings.llm_provider == "mock":
        raise RuntimeError("LLM_PROVIDER=mock không có LLM thật — graph phải dùng src/agents/mock_llm.py")

    model = _model_name(settings, task_type)
    if task_type == "judge" and (not model or model == _model_name(settings, "generate")):
        raise ValueError(
            "Model judge phải khác model generate — judge trùng generator gây self-preference bias "
            "(team 002). Sửa MODEL_JUDGE (openai) hoặc LOCAL_LLM_JUDGE_MODEL (local) trong .env."
        )

    is_local = settings.llm_provider == "local"
    base_url = settings.local_llm_base_url if is_local else (settings.openai_base_url or None)
    return ChatOpenAI(
        model=model,
        api_key=settings.local_llm_api_key if is_local else settings.openai_api_key,
        base_url=base_url,
        # classify/judge cần ổn định, không sáng tạo.
        temperature=0.0 if task_type in ("classify", "judge") else settings.llm_temperature,
        # Quá hạn / lỗi nhà cung cấp → OpenAIError → routes.py trả 503 llm_unavailable → web dùng form.
        timeout=settings.llm_timeout_seconds,
        max_retries=3,
    )


def get_structured_llm(task_type: TaskType, schema: type[BaseModel]) -> Runnable:
    """LLM trả về đúng `schema` (Pydantic). Model local dùng cách ép schema cấu hình được.

    Model nhỏ tự host thường không hỗ trợ tool-calling ổn định → mặc định `json_schema`
    (Ollama ≥ 0.5 và vLLM đều hỗ trợ). API OpenAI giữ mặc định của langchain.
    """
    settings = get_settings()
    llm = get_llm(task_type)
    if settings.llm_provider == "local":
        return llm.with_structured_output(schema, method=settings.local_llm_structured_method)
    if settings.openai_base_url and "googleapis.com" in settings.openai_base_url:
        return llm.with_structured_output(schema, method="json_mode")
    return llm.with_structured_output(schema)


def describe_provider() -> dict:
    """Tóm tắt cấu hình LLM đang dùng (KHÔNG chứa key) — cho /status và trang playground."""
    settings = get_settings()
    if settings.llm_provider == "mock":
        return {"provider": "mock", "model": "rule-based (src/agents/mock_llm.py)"}
    info = {"provider": settings.llm_provider, "model": _model_name(settings, "generate")}
    if settings.llm_provider == "local":
        info["base_url"] = settings.local_llm_base_url
    else:
        info["model_classify"] = settings.model_classify
    return info
