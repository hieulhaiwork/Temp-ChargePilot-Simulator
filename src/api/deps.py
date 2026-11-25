"""Dependency dùng chung cho router: user hiện tại + kiểm vai trò (FR1).

Test không cần token thật: app.dependency_overrides[get_current_user] = lambda: UserProfile(...).
Swagger UI có nút "Authorize" nhờ HTTPBearer.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import get_settings
from src.models.api import UserProfile
from src.models.control import Role
from src.services import auth as auth_service

_bearer = HTTPBearer(auto_error=False)
_BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]

DEMO_RESIDENT = UserProfile(
    user_id="demo-resident",
    role=Role.RESIDENT,
    display_name="Cư dân Demo",
    vehicle_model="DEMO-60",
)


async def get_current_user(
    credentials: _BearerCredentials,
) -> UserProfile:
    if get_settings().agent_playground and (credentials is None or credentials.credentials == "demo"):
        return DEMO_RESIDENT
    return await get_authenticated_user(credentials)


async def get_authenticated_user(credentials: _BearerCredentials) -> UserProfile:
    """Require JWT even when the legacy chat playground is enabled."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Thiếu Bearer token", headers={"WWW-Authenticate": "Bearer"})
    return auth_service.decode_token(credentials.credentials)


CurrentUser = Annotated[UserProfile, Depends(get_current_user)]
AuthenticatedUser = Annotated[UserProfile, Depends(get_authenticated_user)]


async def require_resident(user: CurrentUser) -> UserProfile:
    if user.role != Role.RESIDENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cần vai trò resident")
    return user


async def require_operator(user: CurrentUser) -> UserProfile:
    if user.role != Role.OPERATOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cần vai trò operator")
    return user


ResidentUser = Annotated[UserProfile, Depends(require_resident)]
OperatorUser = Annotated[UserProfile, Depends(require_operator)]
