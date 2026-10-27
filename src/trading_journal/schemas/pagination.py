import uuid

from pydantic import BaseModel


class Page[T](BaseModel):
    """One page of a keyset-paginated list (ADR 0009).

    Pass next_cursor back as ?cursor= to get the next page; it is null on the last one.
    """

    items: list[T]
    next_cursor: uuid.UUID | None
