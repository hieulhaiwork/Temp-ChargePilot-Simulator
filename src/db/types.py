"""Kiểu cột dùng chung cho SQLite và Postgres."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """Thời điểm lưu ở UTC, vào/ra LUÔN có múi giờ.

    Vì sao tồn tại: SQLite không giữ múi giờ — đọc lại ra `datetime` naive, trong khi hợp đồng
    dữ liệu dùng AwareDatetime (src/models/). Lúc ghi: đổi sang UTC, TỪ CHỐI giá trị naive
    (fail loudly). Lúc đọc: gắn lại UTC. Múi giờ gốc của người dùng vẫn nằm trong cột `payload`.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UtcDateTime chỉ nhận datetime có múi giờ")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


# JSON chung; trên Postgres dùng JSONB. KHÔNG viết truy vấn vào bên trong JSON: cần lọc theo
# field nào thì thêm cột khoá + migration (docs/plan/40-database.md §4).
JsonDoc = JSON().with_variant(JSONB(), "postgresql")
