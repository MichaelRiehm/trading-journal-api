from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer


class RequestModel(BaseModel):
    """Base for request bodies. Unknown fields are a 422, not silently ignored.

    Otherwise a typo in a PATCH ("planed_stop") returns 200 and changes nothing, and a
    client sending a derived value like "pnl" would think it had been stored.
    """

    model_config = ConfigDict(extra="forbid")


def _fixed_point(value: Decimal) -> str:
    # str(Decimal) switches to exponent notation for small values: 0 at 8 dp is "0E-8".
    # That's valid, but many clients (.NET's decimal.Parse, for one) reject it by default.
    return format(value, "f")


# Decimals in responses: always a fixed-point JSON string, "0.00000000", never "0E-8".
DecimalOut = Annotated[Decimal, PlainSerializer(_fixed_point, return_type=str, when_used="json")]
