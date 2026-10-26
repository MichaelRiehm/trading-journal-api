import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from trading_journal.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self._session.add(user)
        self._session.flush()
        return user

    def get(self, user_id: uuid.UUID) -> User | None:
        return self._session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(User.email == email))
