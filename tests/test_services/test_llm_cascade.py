"""Test cascade router — model rẻ cho task rẻ, model mạnh cho task mạnh."""

import pytest

from src.config import get_settings
from src.services.llm import describe_provider, get_llm, get_structured_llm


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch):
    """Mỗi test đọc lại Settings từ env — không dính cache của test khác."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MODEL_CLASSIFY", "gpt-4o-mini")
    monkeypatch.setenv("MODEL_GENERATE", "gpt-4o")
    monkeypatch.setenv("MODEL_JUDGE", "gpt-4o-mini")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_classify_uses_cheap_model():
    assert get_llm("classify").model_name == "gpt-4o-mini"


def test_generate_uses_strong_model():
    assert get_llm("generate").model_name == "gpt-4o"


def test_judge_uses_configured_model():
    assert get_llm("judge").model_name == "gpt-4o-mini"


def test_judge_same_model_as_generator_raises():
    get_settings.cache_clear()
    import os

    os.environ["MODEL_JUDGE"] = "gpt-4o"  # trùng MODEL_GENERATE
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="self-preference"):
        get_llm("judge")
    os.environ.pop("MODEL_JUDGE")


def test_classify_and_judge_run_at_low_temperature():
    settings = get_settings()
    settings.llm_temperature = 0.9  # generate có thể nóng
    assert get_llm("classify").temperature == 0.0
    assert get_llm("judge").temperature == 0.0
    assert get_llm("generate").temperature == 0.9


def test_local_llm_provider_points_to_vm_base_url_and_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://10.0.0.5:8000/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen2.5:14b-instruct")
    monkeypatch.setenv("LOCAL_LLM_JUDGE_MODEL", "llama3.1:8b-instruct")
    get_settings.cache_clear()

    gen = get_llm("generate")
    cls = get_llm("classify")
    jdg = get_llm("judge")

    assert gen.model_name == "qwen2.5:14b-instruct"
    assert cls.model_name == "qwen2.5:14b-instruct"
    assert jdg.model_name == "llama3.1:8b-instruct"
    assert str(gen.openai_api_base) == "http://10.0.0.5:8000/v1"
    assert describe_provider() == {
        "provider": "local",
        "model": "qwen2.5:14b-instruct",
        "base_url": "http://10.0.0.5:8000/v1",
    }


def test_local_judge_requires_distinct_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen2.5:7b-instruct")
    monkeypatch.setenv("LOCAL_LLM_JUDGE_MODEL", "")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="self-preference"):
        get_llm("judge")


def test_mock_provider_disallows_direct_get_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    assert describe_provider()["provider"] == "mock"
    with pytest.raises(RuntimeError, match="mock_llm"):
        get_llm("generate")


def test_structured_llm_builds_for_openai_and_local(monkeypatch):
    from src.models.schemas import FinalAnswer

    assert get_structured_llm("generate", FinalAnswer) is not None
    monkeypatch.setenv("LLM_PROVIDER", "local")
    get_settings.cache_clear()
    assert get_structured_llm("generate", FinalAnswer) is not None
