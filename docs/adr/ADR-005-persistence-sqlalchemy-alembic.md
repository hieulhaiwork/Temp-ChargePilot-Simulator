# ADR-005: Persistence bằng SQLAlchemy 2 + Alembic, nằm sau `services/repository.py`

- Trạng thái: Proposed — nhóm đã duyệt 2026-11-17, chờ mentor. **Sửa đổi một phần — xem ghi chú bên dưới.**
- Ngày: 2026-11-17
- Plan chi tiết: [`docs/plan/40-database.md`](../plan/40-database.md)


> **Sửa đổi một phần:** [ADR-014](ADR-014-decision-trace-counterfactual-hitl.md), 2026-11-21: công nghệ và cách lưu giữ nguyên. Thêm bảng `proposals`, `consents`, `vehicle_revisions` qua Alembic; audit dùng `decision_log`.

## Bối cảnh

Render free có đĩa không bền và tự ngủ. Booking, lịch gần nhất, phê duyệt và nhật ký quyết định (FR14) không được mất
khi backend khởi động lại. Máy local và CI cần chạy không phải cài Postgres. `src/services/repository.py` đã là điểm
vào duy nhất của tầng ứng dụng tới dữ liệu, nhưng chưa chốt công nghệ (ghi chú "quyết định còn mở" ở T1.6).

## Các lựa chọn

1. `sqlite3` của stdlib: không thêm dependency, nhưng phải viết SQL riêng cho từng hệ và tự làm migration.
2. **SQLAlchemy 2 (đồng bộ) + Alembic**, SQLite ở local/CI và Postgres (Neon) khi deploy.
3. SQLAlchemy async (asyncpg + aiosqlite): không chặn event loop, nhưng buộc đổi toàn bộ chữ ký `repository` và tool
   của Agent sang `async`.
4. Chuẩn hoá hoàn toàn mọi model lồng nhau thành bảng: truy vấn linh hoạt hơn, nhưng mỗi lần đổi contract Pydantic
   là một migration.

## Quyết định

Chọn (2), với cách lưu "cột khoá + `payload` JSON":

- Package mới `src/db/` là nơi duy nhất biết SQLAlchemy. `src/services/repository.py` nhận và trả model Pydantic của
  `src/models/`; không lớp ORM nào lọt ra ngoài.
- Mỗi bảng nghiệp vụ có các cột khoá để lọc/sắp xếp/ràng buộc và một cột `payload` chứa `model_dump(mode="json")`.
  `src/db/mappers.py` là chỗ duy nhất ghi cả hai.
- Driver Postgres: `psycopg` 3. `src/db/session.py` tự đổi tiền tố `postgresql://` thành `postgresql+psycopg://`.
- Thời gian lưu UTC qua `UtcDateTime` vì SQLite trả `datetime` không có múi giờ.
- Migration bằng Alembic, chạy `alembic upgrade head` trong `CMD` của container trước `uvicorn`.
- Truy cập đồng bộ; code `async` gọi qua `asyncio.to_thread`.

## Hệ quả

- Dependency mới: `sqlalchemy`, `alembic`, `psycopg[binary]`.
- `tests/test_architecture.py` khoá: chỉ `src/db/**` và `src/services/repository.py` được import `sqlalchemy` / `src.db`;
  `src/db/**` chỉ import `src.models` và `src.config`.
- `tests/test_db/test_migrations.py` fail khi `tables.py` đổi mà quên viết revision.
- Không viết truy vấn vào bên trong `payload`: cần lọc theo field nào thì thêm cột khoá + migration.
- Benchmark không ghi DB (sinks ghi vào bộ nhớ, ADR-007).
