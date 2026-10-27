import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from trading_journal.domain.enums import JournalPhase
from trading_journal.schemas.base import RequestModel

# Plain text; Markdown is fine, the API doesn't render it.
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)]


class JournalEntryCreate(RequestModel):
    # Omitted: the phase the trade is in now (planned -> pre, open -> during, else post).
    phase: JournalPhase | None = None
    body: Body


class JournalEntryUpdate(RequestModel):
    """Only the fields sent are changed. Neither may be null."""

    phase: JournalPhase | None = None
    body: Body | None = None

    @model_validator(mode="after")
    def fields_not_null(self) -> JournalEntryUpdate:
        nulled = sorted(n for n in self.model_fields_set if getattr(self, n) is None)
        if nulled:
            raise ValueError(f"cannot be null: {', '.join(nulled)}")
        return self


class JournalEntryRead(BaseModel):
    """updated_at later than created_at means the entry was edited afterwards."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trade_id: uuid.UUID
    phase: JournalPhase
    body: str
    created_at: datetime
    updated_at: datetime
