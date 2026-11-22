"""Hợp đồng của tầng services: sync/async đúng theo ADR-007 + test skip cho logic chưa làm.

Phần "chữ ký" chạy thật — đổi nhầm một hàm phát sự kiện về `def` sẽ làm router `await` một giá
trị không phải coroutine, lỗi chỉ lộ lúc chạy thật.
"""

import inspect

import pytest

from src.guard import dispatcher
from src.services import auth, charging_service, control_loop, event_bus, simulation_service, station_service

ASYNC_FUNCTIONS = [
    charging_service.book,
    charging_service.cancel,
    charging_service.change,
    station_service.replan,
    station_service.manual_assign,
    simulation_service.inject_incident,
    control_loop.on_event,
    control_loop.run_forever,
    control_loop.resolve_approval,
    event_bus.publish,
    dispatcher.submit,
    dispatcher.execute_approved,
]
SYNC_FUNCTIONS = [
    charging_service.quote,
    charging_service.current_booking,
    charging_service.session_view,
    charging_service.queue_status,
    charging_service.explain,
    station_service.overview,
    station_service.load_history,
    station_service.current_plan,
    station_service.connector_detail,
    station_service.recent_events,
    station_service.list_bookings,
    auth.authenticate,
    auth.decode_token,
]


@pytest.mark.parametrize("fn", ASYNC_FUNCTIONS, ids=lambda f: f"{f.__module__.rsplit('.', 1)[-1]}.{f.__name__}")
def test_event_publishing_functions_are_async(fn):
    assert inspect.iscoroutinefunction(fn)


@pytest.mark.parametrize("fn", SYNC_FUNCTIONS, ids=lambda f: f"{f.__module__.rsplit('.', 1)[-1]}.{f.__name__}")
def test_read_only_functions_are_sync(fn):
    assert not inspect.iscoroutinefunction(fn)


def test_no_tool_or_service_takes_resident_id_from_keyword_default():
    """ADR-006: resident_id luôn là tham số BẮT BUỘC do phía gọi lấy từ token — không có giá trị mặc định."""
    for fn in (charging_service.quote, charging_service.book, charging_service.cancel, charging_service.queue_status):
        assert inspect.signature(fn).parameters["resident_id"].default is inspect.Parameter.empty


def test_dispatch_sinks_are_immutable():
    sinks = dispatcher.DispatchSinks(log_decision=print, save_approval=print, notify=print)
    with pytest.raises(AttributeError):
        sinks.log_decision = len  # frozen dataclass


# ---- T1.7 auth ---------------------------------------------------------------------------

SEED = (
    '[{"email":"Res@Example.invalid","password":"pw-res-1","role":"resident","display_name":"R","vehicle_model":"VF3"},'
    ' {"email":"op@example.invalid","password":"pw-op-1","role":"operator","display_name":"O"}]'
)


@pytest.fixture
def seeded(clean_db, monkeypatch):
    from src.config import get_settings

    monkeypatch.setattr(get_settings(), "seed_users_json", SEED)
    assert auth.ensure_seed_users() == 2


def test_token_roundtrip(seeded):
    """FR1. Given tài khoản resident đã seed. When authenticate rồi decode_token. Then nhận UserProfile đúng user_id/role."""
    token = auth.authenticate("res@example.invalid", "pw-res-1")
    assert token.role == "resident" and token.user_id.startswith("res-")
    user = auth.decode_token(token.access_token)
    assert (user.user_id, user.role, user.vehicle_model) == (token.user_id, "resident", "VF3")
    assert auth.decode_token(auth.authenticate("op@example.invalid", "pw-op-1").access_token).role == "operator"


@pytest.mark.parametrize(("email", "password"), [("res@example.invalid", "wrong"), ("nobody@example.invalid", "x")])
def test_wrong_password_is_unauthenticated(seeded, email, password):
    """Given mật khẩu sai hoặc email không tồn tại. Then cùng DomainError UNAUTHENTICATED (không lộ email nào có thật)."""
    from src.models.api import ErrorCode
    from src.services.errors import DomainError

    with pytest.raises(DomainError) as err:
        auth.authenticate(email, password)
    assert err.value.code == ErrorCode.UNAUTHENTICATED
    assert err.value.detail == "Email hoặc mật khẩu không đúng"


def test_expired_or_tampered_token_is_rejected(seeded, monkeypatch):
    """Given token hết hạn / sai chữ ký / thuật toán 'none'. Then DomainError UNAUTHENTICATED, không trả user rỗng."""
    from datetime import UTC, datetime, timedelta

    import jwt

    from src.services.errors import DomainError

    good = auth.authenticate("res@example.invalid", "pw-res-1")
    claims = jwt.decode(good.access_token, options={"verify_signature": False})
    expired = jwt.encode({**claims, "exp": datetime.now(UTC) - timedelta(minutes=1)}, auth._secret(), algorithm="HS256")
    forged = jwt.encode(claims, "another-secret-another-secret-123", algorithm="HS256")
    unsigned = jwt.encode(claims, None, algorithm="none")
    escalated = jwt.encode({**claims, "role": "operator"}, "x" * 40, algorithm="HS256")
    for bad in (expired, forged, unsigned, escalated, good.access_token[:-3] + "abc", "not-a-jwt"):
        with pytest.raises(DomainError):
            auth.decode_token(bad)


def test_deleted_account_token_stops_working(seeded):
    from src.services.errors import DomainError

    token = auth.authenticate("res@example.invalid", "pw-res-1")
    auth.delete_account(token.user_id)
    with pytest.raises(DomainError):
        auth.decode_token(token.access_token)
    with pytest.raises(DomainError):
        auth.authenticate("res@example.invalid", "pw-res-1")


def test_password_hash_is_salted_and_verifiable():
    """Given cùng mật khẩu băm 2 lần. Then 2 chuỗi khác nhau, verify_password đúng cho cả hai, sai với mật khẩu khác."""
    h1, h2 = auth.hash_password("s3cret"), auth.hash_password("s3cret")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert auth.verify_password("s3cret", h1) and auth.verify_password("s3cret", h2)
    assert not auth.verify_password("other", h1)
    assert not auth.verify_password("s3cret", "garbage")


def test_seed_users_is_idempotent(seeded):
    """Given SEED_USERS_JSON có 2 tài khoản. When ensure_seed_users chạy 2 lần. Then vẫn 2 tài khoản, đăng nhập được."""
    from src.services import repository

    first = repository.get_user_by_email("res@example.invalid").user_id
    assert auth.ensure_seed_users() == 2
    assert repository.get_user_by_email("res@example.invalid").user_id == first
    assert auth.authenticate("res@example.invalid", "pw-res-1").user_id == first


def test_bad_seed_json_does_not_raise(clean_db, monkeypatch):
    from src.config import get_settings

    monkeypatch.setattr(get_settings(), "seed_users_json", "{not json")
    assert auth.ensure_seed_users() == 0
    monkeypatch.setattr(get_settings(), "seed_users_json", "")
    assert auth.ensure_seed_users() == 0


def test_profile_update_and_unknown_vehicle(seeded):
    from src.models.api import ProfileUpdateRequest
    from src.models.charging import ConsentScope
    from src.services.errors import DomainError

    uid = auth.authenticate("res@example.invalid", "pw-res-1").user_id
    prof = auth.update_profile(
        uid,
        ProfileUpdateRequest(default_soc_target=80, consent=ConsentScope(max_start_delay_minutes=30)),
    )
    assert prof.default_soc_target == 80 and prof.consent.max_start_delay_minutes == 30
    assert prof.vehicle_model == "VF3"
    assert auth.get_profile(uid) == prof
    with pytest.raises(DomainError):
        auth.update_profile(uid, ProfileUpdateRequest(vehicle_model="NOPE"))
