from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "sqlite:///./data/app.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "ChargePilot"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM — cascade router: mỗi task type một model (bài học cost-management:
    # không đốt model mạnh cho việc classify). Judge PHẢI khác model generator
    # để tránh self-preference bias (bài học team 002 — eval judge riêng).
    openai_api_key: str = ""
    openai_base_url: str = ""  # tuỳ chọn: đổi endpoint OpenAI-compatible (vd Gemini / OpenRouter) ngay ở chế độ openai
    model_name: str = "gpt-4o"  # legacy alias cho model_generate
    model_classify: str = "gpt-4o-mini"  # cheap: classify / route / quyết định tool
    model_generate: str = "gpt-4o"  # strong: sinh câu trả lời cuối
    model_judge: str = "gpt-4o-mini"  # judge: khác model_generate mặc định
    # 0.2: câu trả lời của ChargePilot là diễn đạt lại dữ kiện do code tính, không cần sáng tạo.
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=20.0, gt=0, le=120)  # quá hạn → 503 llm_unavailable → frontend dùng form

    # LLM provider — đổi qua lại bằng 1 dòng .env, không sửa code (src/services/llm.py):
    #   openai = gọi API (OPENAI_API_KEY + MODEL_*)
    #   local  = server OpenAI-compatible tự host (Ollama / vLLM / LM Studio trên VM) — LOCAL_LLM_*
    #   mock   = bộ não luật cố định, KHÔNG gọi mạng (src/agents/mock_llm.py) — dev/test khi chưa có key/VM
    llm_provider: Literal["openai", "local", "mock"] = "openai"
    local_llm_base_url: str = "http://localhost:11434/v1"  # Ollama mặc định; vLLM: http://<vm-ip>:8000/v1
    local_llm_api_key: str = "local"  # Ollama bỏ qua; vLLM chạy với --api-key thì điền đúng key đó
    local_llm_model: str = "qwen2.5:7b-instruct"  # dùng cho cả classify lẫn generate
    local_llm_judge_model: str = ""  # eval judge — PHẢI khác LOCAL_LLM_MODEL; trống = không có judge local
    # Cách ép output theo schema: json_schema hợp với cả Ollama ≥ 0.5 và vLLM mà không cần cờ tool-calling.
    local_llm_structured_method: Literal["json_schema", "function_calling", "json_mode"] = "json_schema"

    # Agent dev tools (CHỈ dev/local — validator bên dưới chặn ở production):
    # AGENT_DEMO_SERVICES: tool sạc dùng dịch vụ giả lập trong bộ nhớ (services/charging_demo.py) tới khi T2.2 xong.
    agent_demo_services: bool = False
    # AGENT_PLAYGROUND: mở trang chat thử /dev/agent (không cần đăng nhập, cư dân demo cố định).
    agent_playground: bool = False

    # Agent loop — escape hatch chống loop vô hạn (bài học team 011:
    # luôn phải có một đường tới END dù LLM cứ đòi gọi tool mãi)
    agent_max_iterations: int = Field(default=8, ge=1, le=50)

    # Database
    database_url: str = DEFAULT_DATABASE_URL

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # ChargePilot — tham số trạm/xe/giá nằm ở config/*.yaml (services/catalog.py),
    # ở đây chỉ còn lựa chọn hạ tầng.
    simulator_backend: Literal["ev2gym", "acnsim"] = "ev2gym"  # FR11 — ACN-Sim dự phòng (Go/No-Go T1.4)
    forecast_model_path: str = "src/forecast/artifacts/departure_lgbm.txt"  # F6 — artifact nhỏ, commit được
    # FR1 / T1.7 — bắt buộc ở production (validator dưới + render.yaml/render.test.yaml + docker-smoke trong CI).
    jwt_secret: str = ""
    jwt_ttl_minutes: int = Field(
        default=480, ge=5, le=7 * 24 * 60
    )  # hết hạn thì đăng nhập lại (không có refresh token)
    # Tài khoản demo (ADR-006): JSON [{"email","password","role","display_name","vehicle_model"}].
    # Chỉ đặt ở .env local / dashboard hosting — KHÔNG commit giá trị. Trống = không seed.
    seed_users_json: str = ""
    # ADR-007: vòng nền (bước simulator, TICK → tính lại lịch, hết hạn phê duyệt) — trạm tự vận hành theo thời
    # gian, không cần request. Mặc định TẮT cho local / test (đồng hồ thật làm test không tất định); deploy BẬT
    # (render*.yaml, docs/plan/56). Sự kiện vẫn luôn được xử lý ngay trong request dù bật hay tắt.
    control_loop_enabled: bool = False
    sim_time_scale: float = Field(default=1.0, gt=0, le=3600)  # 1 = thời gian thật; 60 = 1 phút thật = 1 giờ mô phỏng
    # ADR-008: chỉ đặt ở backend TEST để nhận URL preview của Vercel; production dùng cors_origins chính xác.
    cors_origin_regex: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_database_url_means_default(cls, value: object) -> object:
        # Hosting hay để biến "chưa điền" thành chuỗi rỗng (Render `sync: false`). Coi như chưa đặt → SQLite mặc định,
        # thay vì để `alembic upgrade head` nổ với URL rỗng. Lưu ý: SQLite trên Render free KHÔNG bền (ADR-005).
        return value or DEFAULT_DATABASE_URL

    @model_validator(mode="after")
    def _require_secrets_in_production(self) -> "Settings":
        # Fail-fast: thiếu key trên hosting thì deploy fail ngay lúc khởi động,
        # thay vì app vẫn "healthy" rồi lỗi khi giám khảo gọi.
        if self.app_env != "production":
            return self
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when APP_ENV=production and LLM_PROVIDER=openai")
        if self.llm_provider == "mock":
            raise ValueError("LLM_PROVIDER=mock is for dev/test only — not allowed when APP_ENV=production")
        if self.agent_demo_services or self.agent_playground:
            raise ValueError("AGENT_DEMO_SERVICES / AGENT_PLAYGROUND are dev-only — turn them off in production")
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET (>= 32 characters) is required when APP_ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
