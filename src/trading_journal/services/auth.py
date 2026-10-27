import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trading_journal import security
from trading_journal.config import Settings
from trading_journal.domain.errors import AuthenticationError, ConflictError
from trading_journal.models import User
from trading_journal.repositories import UserRepository


def normalize_email(email: str) -> str:
    # The database only stores lowercase emails (ck_users_email_lowercase).
    return email.strip().lower()


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)

    def register(self, email: str, password: str) -> User:
        email = normalize_email(email)
        if self._users.get_by_email(email) is not None:
            raise ConflictError("Email is already registered")
        try:
            user = self._users.add(email=email, password_hash=security.hash_password(password))
        except IntegrityError as exc:
            # Two registrations raced past the check above; the unique constraint caught it.
            self._session.rollback()
            raise ConflictError("Email is already registered") from exc
        self._session.commit()
        return user

    def authenticate(self, email: str, password: str) -> str:
        """Return an access token, or raise AuthenticationError."""
        user = self._users.get_by_email(normalize_email(email))
        if user is None:
            security.verify_password(password, security.DUMMY_HASH)
            raise AuthenticationError("Incorrect email or password")
        valid, new_hash = security.verify_password(password, user.password_hash)
        if not valid:
            raise AuthenticationError("Incorrect email or password")
        if new_hash is not None:
            user.password_hash = new_hash
            self._session.commit()
        return security.create_access_token(user.id, self._settings)

    def user_from_token(self, token: str) -> User:
        user_id: uuid.UUID = security.decode_access_token(token, self._settings)
        user = self._users.get(user_id)
        if user is None:
            # A valid token for a user that has since been deleted.
            raise AuthenticationError("Could not validate credentials")
        return user
