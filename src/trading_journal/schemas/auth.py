from typing import Literal

from pydantic import BaseModel


class TokenResponse(BaseModel):
    """The OAuth2 token response shape, which the Swagger UI "Authorize" button reads."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (the OAuth2 token type)
    expires_in: int  # seconds
