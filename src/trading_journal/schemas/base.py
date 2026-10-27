from pydantic import BaseModel, ConfigDict


class RequestModel(BaseModel):
    """Base for request bodies. Unknown fields are a 422, not silently ignored.

    Otherwise a typo in a PATCH ("planed_stop") returns 200 and changes nothing, and a
    client sending a derived value like "pnl" would think it had been stored.
    """

    model_config = ConfigDict(extra="forbid")
