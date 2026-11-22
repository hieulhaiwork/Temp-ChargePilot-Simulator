"""Engine + session cho cả SQLite (local, CI) và Postgres/Neon (deploy).

Truy cập ĐỒNG BỘ (ADR-005). Mỗi hàm của services/repository.py mở một session ngắn bằng
session_scope(); không giữ session qua nhiều request.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def normalize_url(url: str) -> str:
    """Cho phép dán nguyên chuỗi kết nối của Neon (`postgresql://…`) vào DATABASE_URL.

    SQLAlchemy mặc định `postgresql://` sang psycopg2; dự án dùng psycopg 3 nên đổi tiền tố.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        in_memory = parsed.database in (None, "", ":memory:")
        if not in_memory:
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url,
            # Router chạy trong threadpool → nhiều thread dùng chung engine.
            connect_args={"check_same_thread": False},
            # DB trong RAM chỉ tồn tại trên MỘT kết nối → giữ đúng một kết nối.
            **({"poolclass": StaticPool} if in_memory else {}),
        )

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")  # SQLite tắt khoá ngoại theo mặc định
            if not in_memory:
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        return engine
    # Neon tự tạm dừng khi không dùng → kiểm kết nối trước khi dùng, thay kết nối cũ.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=0,
        connect_args={"connect_timeout": 10},
    )


def configure(url: str) -> None:
    """Đặt engine dùng chung. Gọi lại với URL khác thì đóng engine cũ trước."""
    global _engine, _factory
    dispose()
    _engine = make_engine(url)
    _factory = sessionmaker(bind=_engine, expire_on_commit=False)


def is_configured() -> bool:
    return _engine is not None


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("DB chưa được cấu hình — gọi services.repository.init() trước")
    return _engine


def dispose() -> None:
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """Một giao dịch: commit khi xong, rollback khi lỗi, luôn đóng session."""
    if _factory is None:
        raise RuntimeError("DB chưa được cấu hình — gọi services.repository.init() trước")
    session = _factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
