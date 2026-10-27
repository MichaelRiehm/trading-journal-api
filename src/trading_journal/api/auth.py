from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from trading_journal.api.deps import AuthServiceDep, SettingsDep
from trading_journal.schemas.auth import TokenResponse
from trading_journal.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Email is already registered"}},
)
def register(body: UserCreate, auth: AuthServiceDep) -> UserRead:
    user = auth.register(body.email, body.password)
    return UserRead.model_validate(user)


@router.post(
    "/token",
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Incorrect email or password"}},
)
def token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth: AuthServiceDep,
    settings: SettingsDep,
) -> TokenResponse:
    """OAuth2 password flow. The form's `username` field is the email."""
    access_token = auth.authenticate(form.username, form.password)
    return TokenResponse(
        access_token=access_token, expires_in=settings.access_token_expire_minutes * 60
    )
