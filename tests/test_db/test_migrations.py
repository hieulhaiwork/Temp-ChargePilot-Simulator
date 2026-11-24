"""Migration Alembic phải khớp src/db/tables.py, và các ràng buộc mức DB phải có hiệu lực thật (ADR-005)."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from src.db import tables
from src.db.base import Base
from src.db.session import make_engine, normalize_url

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 16, 19, 0, tzinfo=timezone(timedelta(hours=7)))


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def migrated_engine(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(_alembic_config(url), "head")
    engine = make_engine(url)
    yield engine
    engine.dispose()


def test_upgrade_head_creates_every_table(migrated_engine):
    assert set(inspect(migrated_engine).get_table_names()) >= set(Base.metadata.tables)


def test_head_matches_metadata(migrated_engine):
    """Sửa tables.py mà quên viết revision → test này đỏ (docs/plan/40-database.md §7)."""
    with migrated_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)
    assert diff == [], f"Schema lệch migration — chạy `alembic revision --autogenerate`: {diff}"


def test_downgrade_to_base_removes_tables(tmp_path):
    url = f"sqlite:///{(tmp_path / 'd.db').as_posix()}"
    cfg = _alembic_config(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    engine = make_engine(url)
    try:
        assert not set(inspect(engine).get_table_names()) & set(Base.metadata.tables)
    finally:
        engine.dispose()


def _user(user_id: str) -> tables.UserRow:
    return tables.UserRow(
        user_id=user_id,
        email=f"{user_id}@example.invalid",
        password_hash=None,
        role="resident",
        display_name="Test",
        consent={},
        created_at=NOW,
    )


def _booking(booking_id: str, resident_id: str, status: str) -> tables.BookingRow:
    return tables.BookingRow(
        booking_id=booking_id,
        resident_id=resident_id,
        status=status,
        mode="walk_in",
        vehicle_model="DEMO-60",
        deadline=NOW + timedelta(hours=12),
        schedule_version=0,
        created_at=NOW,
        updated_at=NOW,
        payload={},
    )


def test_one_active_booking_per_resident_is_enforced_by_database(migrated_engine):
    """Mặc định Q6: hai request đồng thời cũng không tạo được 2 booking hiệu lực cho một cư dân."""
    with Session(migrated_engine) as session:
        session.add(_user("res-1"))
        session.flush()  # không khai báo relationship ORM → tự bảo đảm user được ghi trước booking
        session.add(_booking("b1", "res-1", "confirmed"))
        session.commit()
        session.add(_booking("b2", "res-1", "queued"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_finished_booking_does_not_block_a_new_one(migrated_engine):
    with Session(migrated_engine) as session:
        session.add(_user("res-1"))
        session.flush()
        session.add(_booking("b1", "res-1", "completed"))
        session.add(_booking("b2", "res-1", "cancelled"))
        session.add(_booking("b3", "res-1", "confirmed"))
        session.commit()
        assert len(session.scalars(select(tables.BookingRow)).all()) == 3


def test_foreign_keys_are_enforced_on_sqlite(migrated_engine):
    """SQLite tắt khoá ngoại theo mặc định — session.make_engine phải bật PRAGMA foreign_keys."""
    with Session(migrated_engine) as session:
        session.add(_booking("b1", "khong-co-user", "confirmed"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_utc_datetime_roundtrip_is_timezone_aware(migrated_engine):
    """SQLite trả datetime naive; UtcDateTime phải gắn lại UTC và giữ đúng thời điểm."""
    with Session(migrated_engine) as session:
        session.add(_user("res-1"))
        session.commit()
    with Session(migrated_engine) as session:
        created = session.get(tables.UserRow, "res-1").created_at
    assert created.tzinfo is not None
    assert created == NOW
    assert created.utcoffset() == timedelta(0)


def test_naive_datetime_is_rejected_on_write(migrated_engine):
    with Session(migrated_engine) as session:
        row = _user("res-1")
        row.created_at = datetime(2026, 11, 16, 19, 0)  # thiếu múi giờ
        session.add(row)
        with pytest.raises(StatementError, match="múi giờ"):
            session.commit()


def test_neon_connection_string_is_normalized_to_psycopg3():
    assert normalize_url("postgresql://u:p@host/db?sslmode=require").startswith("postgresql+psycopg://u:p@host/db")
    assert normalize_url("postgres://u:p@host/db").startswith("postgresql+psycopg://")
    assert normalize_url("sqlite:///./data/app.db") == "sqlite:///./data/app.db"


def test_utc_constant_used_in_tests_is_utc():
    assert NOW.astimezone(UTC).hour == 12


def _plan_row(version: int, strategy: str) -> tables.SchedulePlanRow:
    return tables.SchedulePlanRow(
        version=version,
        strategy=strategy,
        created_at=NOW,
        horizon_start=NOW,
        step_minutes=15,
        solve_time_s=None,
        payload={},
    )


def test_revision_0003_drops_plans_of_removed_lp_strategies(tmp_path):
    """Phase 4 quyết định 1: lịch lưu của A–D không đọc lại được (enum đã bỏ) → 0003 xoá, lịch B0–M3b giữ nguyên."""
    url = f"sqlite:///{(tmp_path / 'p.db').as_posix()}"
    cfg = _alembic_config(url)
    command.upgrade(cfg, "0001")
    engine = make_engine(url)
    try:
        with Session(engine) as session:
            for version, strategy in enumerate(["A_fcfs", "A_edf", "B", "C", "D", "B0", "M3a"], start=1):
                session.add(_plan_row(version, strategy))
            session.commit()
        command.upgrade(cfg, "head")
        with Session(engine) as session:
            kept = sorted(session.scalars(select(tables.SchedulePlanRow.strategy)).all())
        assert kept == ["B0", "M3a"]
    finally:
        engine.dispose()


def test_revision_0004_preserves_legacy_trace_summary_on_upgrade_and_downgrade(tmp_path):
    from sqlalchemy import text

    url = f"sqlite:///{(tmp_path / 'legacy-trace.db').as_posix()}"
    cfg = _alembic_config(url)
    command.upgrade(cfg, "0003")
    engine = make_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO decision_traces (correlation_id, decided_at, policy_id, schedule_version, "
                    "budget_deviation_kw_max, hard_violations, closed, payload) "
                    "VALUES ('legacy', '2026-11-24 10:00:00', 'M3a', 1, 0, 0, true, :summary)"
                ),
                {"summary": '{"correlation_id":"legacy","closed":true}'},
            )
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            summary, full = connection.execute(
                text("SELECT payload, full_payload FROM decision_traces WHERE correlation_id='legacy'")
            ).one()
            assert summary == '{"correlation_id":"legacy","closed":true}' and full is None
            assert connection.execute(text("SELECT COUNT(*) FROM decision_trace_bookings")).scalar_one() == 0
        command.downgrade(cfg, "0003")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT payload FROM decision_traces")).scalar_one() == summary
            assert "full_payload" not in {col["name"] for col in inspect(connection).get_columns("decision_traces")}
    finally:
        engine.dispose()
