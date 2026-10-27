import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Length over composition rules (NIST 800-63B). The cap stops huge inputs from being
# hashed. See docs/decisions/0006-password-handling.md.
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128


class UserCreate(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class UserRead(BaseModel):
    """Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    created_at: datetime
