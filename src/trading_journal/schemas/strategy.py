import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from trading_journal.schemas.base import RequestModel

StrategyName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Description = Annotated[str, StringConstraints(max_length=2000)]


class StrategyCreate(RequestModel):
    name: StrategyName
    description: Description | None = None


class StrategyUpdate(RequestModel):
    """Only the fields sent are changed. description may be null; name may not."""

    name: StrategyName | None = None
    description: Description | None = None

    @model_validator(mode="after")
    def name_not_null(self) -> StrategyUpdate:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class StrategyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
