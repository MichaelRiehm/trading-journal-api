from fastapi import APIRouter, status

from trading_journal.api.deps import CurrentUser
from trading_journal.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", responses={status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated"}})
def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
