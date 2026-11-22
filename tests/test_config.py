import pytest
from pydantic import ValidationError

from src.config import Settings


def test_agent_max_iterations_default_matches_env_example():
    assert Settings(_env_file=None).agent_max_iterations == 8


def test_env_example_value_is_accepted(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "8")
    assert Settings(_env_file=None).agent_max_iterations == 8


def test_production_requires_openai_api_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None)


def test_production_with_key_is_accepted(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    assert Settings(_env_file=None).app_env == "production"


@pytest.mark.parametrize("secret", ["", "too-short"])
def test_production_requires_strong_jwt_secret(monkeypatch, secret):
    """T1.7 / ADR-006: không có JWT_SECRET đủ dài ở production → app không khởi động (fail-fast)."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("JWT_SECRET", secret)
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None)


def test_development_without_key_is_allowed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert Settings(_env_file=None).openai_api_key == ""


def test_empty_database_url_falls_back_to_sqlite(monkeypatch):
    """Hosting để biến chưa điền thành chuỗi rỗng → dùng SQLite mặc định, không nổ lúc chạy migration."""
    monkeypatch.setenv("DATABASE_URL", "")
    assert Settings(_env_file=None).database_url == "sqlite:///./data/app.db"


def test_background_loop_is_off_by_default(monkeypatch):
    """ADR-004 / ADR-007: không bật vòng nền khi nó còn là stub — app phải khởi động được."""
    monkeypatch.delenv("CONTROL_LOOP_ENABLED", raising=False)
    assert Settings(_env_file=None).control_loop_enabled is False
