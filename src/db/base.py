"""DeclarativeBase chung + quy ước đặt tên ràng buộc.

Vì sao có naming convention: SQLite cần tên ràng buộc tường minh để Alembic chạy được
batch migration (ALTER bằng cách tạo lại bảng), và tên giống nhau trên SQLite lẫn Postgres
thì một revision chạy được cả hai.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
