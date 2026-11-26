"""Thiết lập môi trường cho TOÀN BỘ test — chạy trước mọi import của `src`.

Vì sao ở đây (không ở conftest.py): `src.config.get_settings()` được cache ngay lần import đầu
(conftest import src.llm_chat.graph), nên biến môi trường phải được đặt TRƯỚC đó. Package
`tests` được import trước `tests.conftest`.

Test KHÔNG BAO GIỜ được chạm DB khai báo trong `.env` của máy dev (có thể là Postgres thật):
ép DATABASE_URL về một file SQLite tạm. Biến môi trường thắng giá trị trong `.env`.
"""

import os
import tempfile
from pathlib import Path

_TEST_DB = Path(tempfile.mkdtemp(prefix="chargepilot-test-")) / "test.db"
# TEST_DATABASE_URL: chỉ job `backend-postgres` của CI đặt, để chạy test repository trên Postgres thật.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_TEST_DB.as_posix()}"
# Cô lập test khỏi các cờ dev trong .env của máy local (test nào cần sẽ tự monkeypatch.setenv).
os.environ["LLM_PROVIDER"] = "openai"
os.environ["OPENAI_BASE_URL"] = ""
os.environ["AGENT_DEMO_SERVICES"] = "false"
