"""Tầng persistence — package DUY NHẤT biết SQLAlchemy (ADR-005).

    base.py      DeclarativeBase + quy ước đặt tên khoá/index (để Alembic sinh tên ổn định)
    types.py     UtcDateTime (SQLite không giữ múi giờ), JsonDoc (JSON / JSONB)
    tables.py    9 bảng — cột khoá + cột `payload` chứa model Pydantic đã dump
    session.py   engine, session_scope(), chuẩn hoá URL Neon
    mappers.py   Pydantic ↔ hàng ORM — chỗ DUY NHẤT ghi cả cột khoá lẫn payload

Ranh giới (tests/test_architecture.py):
  - Chỉ src/db/** và src/services/repository.py được import sqlalchemy / src.db.
  - src/db/** chỉ import src.models và src.config — không import agents, api, services,
    guard, optimizer, simulator, forecast.
Schema thay đổi → sửa tables.py + viết revision Alembic trong migrations/versions/ CÙNG lúc
(tests/test_db/test_migrations.py fail nếu quên).
"""
