"""Closed sets of values. Stored as their lowercase string values."""

from enum import StrEnum


class TradeStatus(StrEnum):
    PLANNED = "planned"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class Side(StrEnum):
    # "short" is a direct short. A long position in an inverse ETF is LONG with a
    # negative leverage_factor.
    LONG = "long"
    SHORT = "short"


class AssetType(StrEnum):
    STOCK = "stock"
    ETF = "etf"
    CRYPTO = "crypto"


class TradeSource(StrEnum):
    MANUAL = "manual"
    TRADINGVIEW = "tradingview"
    WEBULL = "webull"
    ALGO = "algo"


class JournalPhase(StrEnum):
    PRE = "pre"
    DURING = "during"
    POST = "post"
