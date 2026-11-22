"""S1 — đăng nhập 2 vai trò (FR1, AC8). Owner: TV3. Task: T1.7."""

from fastapi import APIRouter

from src.api.deps import CurrentUser
from src.models.api import LoginRequest, TokenResponse, UserProfile
from src.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    """Đăng nhập → JWT + vai trò (frontend điều hướng resident → S2, operator → S5)."""
    return auth_service.authenticate(body.email, body.password)


@router.get("/me", response_model=UserProfile)
async def me(user: CurrentUser) -> UserProfile:
    return user
