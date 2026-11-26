"""Regression: repository.save_booking chỉ được báo BOOKING_CONFLICT ("đã có lịch hiệu lực") khi vi phạm
index duy nhất Q6 (một booking hiệu lực / cư dân). Lỗi khoá ngoại hay lỗi dữ liệu khác KHÔNG được báo nhầm
thành "lịch hiệu lực khác"."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.api import ErrorCode
from src.models.control import Role
from src.models.identity import UserRecord
from src.services import repository
from src.services.errors import DomainError
from tests.factories import booking as make_booking


def _make_resident(user_id: str) -> None:
    repository.upsert_user(
        UserRecord(
            user_id=user_id,
            email=f"{user_id}@example.test",
            role=Role.RESIDENT,
            display_name="Test",
            created_at=datetime.now(UTC),
        )
    )


def test_missing_resident_is_not_reported_as_active_booking_conflict(clean_db):
    # Cư dân chưa tồn tại → vi phạm khoá ngoại, KHÔNG phải vi phạm "một booking hiệu lực".
    orphan = make_booking("bk-orphan")
    with pytest.raises(IntegrityError):
        repository.save_booking(orphan)


def test_second_active_booking_for_same_resident_is_booking_conflict(clean_db):
    _make_resident("res-dup")
    first = make_booking("bk-dup-1").model_copy(update={"resident_id": "res-dup"})
    second = make_booking("bk-dup-2").model_copy(update={"resident_id": "res-dup"})
    repository.save_booking(first)
    with pytest.raises(DomainError) as exc:
        repository.save_booking(second)
    assert exc.value.code == ErrorCode.BOOKING_CONFLICT
