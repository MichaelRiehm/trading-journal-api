"""Dependencies shared by routers: the database session, settings and the current user."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from trading_journal.config import Settings, get_settings
from trading_journal.db.session import get_session
from trading_journal.models import User
from trading_journal.services import AuthService, StrategyService, TradeService

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

# auto_error=False: a missing token raises our AuthenticationError (401 + WWW-Authenticate)
# like every other bad token, instead of FastAPI's own 401.
_bearer = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def get_auth_service(session: SessionDep, settings: SettingsDep) -> AuthService:
    return AuthService(session, settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_current_user(token: Annotated[str | None, Depends(_bearer)], auth: AuthServiceDep) -> User:
    return auth.user_from_token(token or "")


# Every protected route takes `user: CurrentUser`. Queries are then scoped by user.id,
# so another user's row is simply not found (404, not 403).
CurrentUser = Annotated[User, Depends(get_current_user)]


def get_strategy_service(session: SessionDep) -> StrategyService:
    return StrategyService(session)


def get_trade_service(session: SessionDep) -> TradeService:
    return TradeService(session)


StrategyServiceDep = Annotated[StrategyService, Depends(get_strategy_service)]
TradeServiceDep = Annotated[TradeService, Depends(get_trade_service)]
