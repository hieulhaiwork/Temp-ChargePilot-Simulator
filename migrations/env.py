"""Môi trường chạy Alembic — dùng chung engine và metadata với ứng dụng (ADR-005).

Thứ tự lấy chuỗi kết nối: `-x url=…` → `sqlalchemy.url` do code đặt (test) → settings.database_url.
`render_as_batch=True` vì SQLite không ALTER được phần lớn thay đổi (Alembic tạo lại bảng).
"""

from logging.config import fileConfig

from alembic import context

from src.config import get_settings
from src.db import tables  # noqa: F401 — import để 9 bảng đăng ký vào Base.metadata
from src.db.base import Base
from src.db.session import make_engine, normalize_url
from src.db.types import UtcDateTime

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return (
        context.get_x_argument(as_dictionary=True).get("url")
        or config.get_main_option("sqlalchemy.url")
        or get_settings().database_url
    )


def _render_item(type_: str, obj, autogen_context):
    """Revision KHÔNG import code ứng dụng: UtcDateTime được ghi thành kiểu gốc của nó."""
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=normalize_url(_database_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_database_url())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                render_item=_render_item,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
