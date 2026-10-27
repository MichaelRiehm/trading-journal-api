# 0007: Short positions vs inverse ETFs

- **Status:** Accepted
- **Date:** 2026-10-27
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

Michael bets on falling prices in two different ways:

1. **A direct short:** sell shares he doesn't own and buy them back later. He profits when the price falls.
2. **A long position in an inverse ETF** (SQQQ, SPXU, SOXS): buy shares of a fund that moves opposite to an index, often at 2× or 3×. He profits when *the fund's* price rises, which happens when the index falls.

Both are "bearish trades", but the money works differently. The brief requires an ADR on how the journal models this.

## Decision

- **`side` is the direction of the position actually held.**
  - A direct short is `side = short`.
  - Buying SQQQ is `side = long` with `leverage_factor = -3`.
- **`leverage_factor`** is optional and must be one of 2, 3, -2 or -3:
  - **positive:** a leveraged ETF (TQQQ = 3)
  - **negative:** an inverse ETF (SQQQ = -3, SDS = -2)
  - **null:** no leverage
- **Leverage is only allowed on ETFs** (`asset_type = etf`). The service returns 422 otherwise, and the `ck_trades_leverage_only_etf` CHECK constraint (migration 0002) backs it up.
- **P/L uses only `side`:** `(exit − entry) × qty` for a long, the reverse for a short. The leverage is already in the ETF's price, so it never enters the math.
- **`exposure` is a computed field** (`bullish` or `bearish`) on every trade response. It's bearish for a short, or for a long with negative leverage. Shorting an inverse ETF is bullish, since the two negatives cancel. It's derived, never stored, so it can't disagree with `side` and `leverage_factor`.

## Alternatives considered

- **Record an inverse-ETF trade as `side = short`.** It reads naturally ("I was short the Nasdaq"), but the P/L sign comes out wrong. Buying SQQQ at 20 and selling at 24 is a +4 per share gain. As a short, the formula gives −4. Every analytics number for these trades would be inverted.
- **Store the leverage as a multiplier in the P/L formula.** That double-counts it: a 3× ETF's price already moves 3× the index. The P/L in dollars is simply what the shares did.
- **A separate `direction` column the user sets.** It would duplicate information already in `side` and `leverage_factor`, and the two could drift apart. Computing it removes that possibility.
- **Model the underlying index** (SQQQ → "short QQQ at 3×"). That's more faithful for analysis, but it needs a symbol-to-underlying lookup the journal doesn't have. It's out of scope for v1. `exposure` captures the part that matters for reviews.

## Consequences

- P/L, R-multiple and expectancy are correct for both kinds of bearish trade without special cases.
- Stage 5 analytics can break results down by `exposure` ("how do my bearish bets do?") as well as by `side` ("how do my actual shorts do?"). Those answer different questions, and both are useful.
- A short in a margin account and a long in an inverse ETF have different risks (unlimited loss vs. ETF decay), and the journal doesn't distinguish them beyond `side`. Thesis and journal entries carry that nuance.
- **Adding `-1` or `1` later** (single inverse ETFs like SH) is a one-line change to the CHECK constraint and the schema's `Literal`.
