from fastapi import APIRouter

from trading_journal.api.deps import CurrentUser
from trading_journal.api.errors import UNAUTHORIZED
from trading_journal.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["users"], responses=UNAUTHORIZED)


@router.get("/me")
def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
