"""Xác thực 2 vai trò resident / operator (FR1, AC8) + hồ sơ cư dân (F8) — ADR-006.

Thiết kế (docs/plan/10-backend.md §4.3):
- Tài khoản ở bảng `users`, đọc/ghi qua services.repository. KHÔNG có mật khẩu nào trong repo:
  tài khoản demo seed lúc khởi động từ biến môi trường SEED_USERS_JSON (ensure_seed_users).
- Mật khẩu: hashlib.scrypt của stdlib, so sánh bằng hmac.compare_digest.
- Token: JWT HS256 ký bằng settings.jwt_secret (PyJWT). Claim: sub = user_id GIẢ DANH, role,
  name, iat, exp (settings.jwt_ttl_minutes). Không có refresh token.
- Lỗi xác thực ném DomainError(UNAUTHENTICATED) — không trả user rỗng.
- JWT_SECRET bắt buộc ở production (validator trong src/config.py). Ngoài production, thiếu secret thì
  dùng một secret ngẫu nhiên theo process (token mất hiệu lực khi restart) và ghi cảnh báo.

Owner: TV3. Task: T1.7 (xác thực), T2.8 (hồ sơ).
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import uuid4

import jwt

from src.config import get_settings
from src.models.api import ErrorCode, ProfileUpdateRequest, ResidentProfile, TokenResponse, UserProfile
from src.models.charging import BookingStatus
from src.models.control import Role
from src.models.identity import UserRecord
from src.services import catalog, repository
from src.services.errors import DomainError

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
# scrypt: N=2^14, r=8, p=1 (~16 MB RAM) — mức khuyến nghị cho đăng nhập tương tác, vừa gói free.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
_BAD_CREDENTIALS = "Email hoặc mật khẩu không đúng"
# Hash giả để email không tồn tại vẫn tốn đúng một lần scrypt (không lộ email nào có thật qua thời gian phản hồi).
_DUMMY_HASH: str | None = None


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    """Băm scrypt, trả chuỗi tự mô tả dạng `scrypt$n$r$p$salt_b64$hash_b64`."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = password_hash.split("$")
        if scheme != "scrypt":
            return False
        expected_raw = _unb64(expected)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected_raw)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected_raw)


@lru_cache(maxsize=1)
def _ephemeral_secret() -> str:
    logger.warning("JWT_SECRET trống — dùng secret ngẫu nhiên của process (chỉ dev/test; token mất khi restart)")
    return secrets.token_urlsafe(48)


def _secret() -> str:
    return get_settings().jwt_secret or _ephemeral_secret()


def _issue_token(user: UserRecord) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user.user_id,
        "role": user.role.value,
        "name": user.display_name,
        "iat": now,
        "exp": now + timedelta(minutes=get_settings().jwt_ttl_minutes),
    }
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def authenticate(email: str, password: str) -> TokenResponse:
    global _DUMMY_HASH
    user = repository.get_user_by_email(email)
    if user is None or user.deleted_at is not None or not user.password_hash:
        _DUMMY_HASH = _DUMMY_HASH or hash_password(secrets.token_urlsafe(8))
        verify_password(password, _DUMMY_HASH)
        raise DomainError(ErrorCode.UNAUTHENTICATED, _BAD_CREDENTIALS)
    if not verify_password(password, user.password_hash):
        raise DomainError(ErrorCode.UNAUTHENTICATED, _BAD_CREDENTIALS)
    return TokenResponse(
        access_token=_issue_token(user), role=user.role, user_id=user.user_id, display_name=user.display_name
    )


def decode_token(token: str) -> UserProfile:
    """Giải mã + kiểm chữ ký/hạn token. Token sai phải raise lỗi 401, không trả user rỗng.

    Đọc lại user từ DB: tài khoản đã xoá thì token cũ hết hiệu lực ngay; vehicle_model luôn mới nhất.
    """
    try:
        claims = jwt.decode(token, _secret(), algorithms=[_ALGORITHM], options={"require": ["sub", "exp", "role"]})
    except jwt.PyJWTError as exc:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn") from exc
    user = repository.get_user(str(claims["sub"]))
    if user is None or user.deleted_at is not None or user.role.value != claims["role"]:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn")
    return UserProfile(
        user_id=user.user_id, role=user.role, display_name=user.display_name, vehicle_model=user.vehicle_model
    )


def ensure_seed_users() -> int:
    """Tạo/cập nhật tài khoản demo từ SEED_USERS_JSON (upsert theo email); trả số tài khoản đã xử lý.

    Gọi trong lifespan (Render free không có shell để seed tay).
    Thiếu biến môi trường hoặc JSON hỏng → không seed, ghi log cảnh báo, không raise.
    """
    raw = get_settings().seed_users_json.strip()
    if not raw:
        logger.warning("SEED_USERS_JSON trống — không seed tài khoản demo")
        return 0
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            raise ValueError("SEED_USERS_JSON phải là một mảng JSON")
    except ValueError as exc:
        logger.warning("SEED_USERS_JSON không hợp lệ — bỏ qua seed: %s", exc)
        return 0
    count = 0
    for item in items:
        try:
            email = str(item["email"]).strip().lower()
            existing = repository.get_user_by_email(email)
            role = Role(item.get("role", "resident"))
            prefix = "res" if role == Role.RESIDENT else "op"
            repository.upsert_user(
                UserRecord(
                    user_id=existing.user_id if existing else f"{prefix}-{uuid4().hex[:8]}",
                    email=email,
                    password_hash=hash_password(str(item["password"])),
                    role=role,
                    display_name=item.get("display_name") or email.split("@")[0],
                    vehicle_model=item.get("vehicle_model"),
                    default_soc_target=item.get("default_soc_target"),
                    consent=existing.consent if existing else {},
                    created_at=existing.created_at if existing else datetime.now(UTC),
                )
            )
            count += 1
        except (KeyError, ValueError, TypeError) as exc:
            # Không log nội dung item (có mật khẩu).
            logger.warning("Bỏ qua một tài khoản seed không hợp lệ: %s", type(exc).__name__)
    logger.info("Đã seed %d tài khoản demo", count)
    return count


def _resident(user_id: str) -> UserRecord:
    user = repository.get_user(user_id)
    if user is None or user.deleted_at is not None:
        raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy tài khoản")
    return user


def _to_profile(user: UserRecord) -> ResidentProfile:
    return ResidentProfile(
        user_id=user.user_id,
        display_name=user.display_name,
        vehicle_model=user.vehicle_model,
        default_soc_target=user.default_soc_target,
        consent=user.consent,
    )


def get_profile(user_id: str) -> ResidentProfile:
    return _to_profile(_resident(user_id))


def update_profile(user_id: str, patch: ProfileUpdateRequest) -> ResidentProfile:
    """NFR riêng tư: cho phép sửa thông tin. vehicle_model phải có trong danh mục."""
    user = _resident(user_id)
    changes = patch.model_dump(exclude_none=True)
    if "vehicle_model" in changes:
        try:
            catalog.get_vehicle(changes["vehicle_model"])
        except catalog.UnknownVehicleError:
            raise DomainError(
                ErrorCode.NOT_FOUND, f"Không có mẫu xe {changes['vehicle_model']!r} trong danh mục"
            ) from None
    updated = UserRecord.model_validate({**user.model_dump(), **changes})
    repository.upsert_user(updated)
    return _to_profile(updated)


def delete_account(user_id: str) -> None:
    """NFR riêng tư: cho phép xoá. Ẩn danh hoá (repository.anonymize_user) + huỷ booking đang hiệu lực.

    Booking cũ và nhật ký quyết định giữ lại dưới user_id giả danh để FR14 còn nguyên vẹn. Lịch được
    tính lại ở lần sự kiện / TICK kế tiếp của control loop.
    """
    _resident(user_id)
    active = repository.active_booking(user_id)
    if active is not None:
        repository.save_booking(active.model_copy(update={"status": BookingStatus.CANCELLED}))
    repository.anonymize_user(user_id, datetime.now(UTC))
