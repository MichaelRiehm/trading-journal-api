# 0011: Analytics definitions

- **Status:** Accepted
- **Date:** 2026-10-27
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

Stage 5 adds `/analytics/summary`, `/equity-curve`, `/breakdown` and `/frequency`. The brief lists the metrics but not their exact definitions, and several of them have more than one common meaning:

- **How a breakeven trade counts.** Issue #5 asks for this to be decided.
- **What a win rate divides by.**
- **Where a drawdown is measured from.**
- **What "no data" looks like.**

Two traders using different definitions can disagree about the same trades. So each definition has to be explicit, testable, and the same everywhere it appears, including the weekly review (ADR 0012).

## Decision

### Which trades

- **Only closed trades count.** The date filters (`start_date`, `end_date`: inclusive, UTC) apply to the close time, `exit_at`.
- **The one exception is `/frequency`,** which by definition counts trades *opened* (open or closed, by `entry_at`). Cancelled trades never opened, so they don't count.

### Outcome: the sign of net P/L

- **Win** if net P/L after fees > 0, **loss** if < 0, **breakeven** if exactly 0.
- **Breakeven is its own bucket,** reported as `breakevens`.
- **Fees are a real cost:** a trade that gained less than its fees is a loss.

### Rates divide by all closed trades

- **`win_rate = wins / trade_count`,** so breakevens are in the denominator. The same goes for `plan_adherence_rate`, the share of closed trades with `followed_plan = true`.
- **The rates add up:** win rate + loss rate + breakeven rate = 1.
- **Expectancy is exactly the mean P/L.** The textbook formula `win_rate × average_win + loss_rate × average_loss` gives the same number, because breakevens contribute 0. A unit test checks this identity.

### Expectancy

- **`expectancy`** is the mean net P/L per closed trade, in dollars.
- **`expectancy_r`** is the mean R-multiple. The brief lists "average R" and "expectancy in R" separately, but they're the same number by definition, so the API reports it once.
- **`average_win_r` and `average_loss_r`** show what it's made of.
- **The means are taken over the per-trade values exactly as `TradeRead` shows them:** P/L at 8 dp and R at 4 dp. So anyone can check them by hand from the trade list.

### Max drawdown

- **What it measures:** the largest fall from a running peak to a later point of the **per-trade** cumulative net P/L, in dollars, as a positive number.
- **The peak starts at 0,** before the first trade. Losing from the very first trade is a drawdown. A curve that never falls has a drawdown of 0.
- **It's measured on exactly the points `/equity-curve` returns** (one per trade, ordered by `exit_at`, then by id). So the two always agree.

### Undefined is `null`, not 0

- **What is `null`:** an average or rate with nothing to average. Examples:
  - every rate and mean when there are no trades
  - `average_win` when there are no wins
  - `average_hold_time_losers` when there are no losses
- **What is 0:** counts and totals, which are 0 when empty, and so is `max_drawdown`.
- **Why:** a 0% win rate (all losses) and "no trades yet" are different facts, and a client can tell them apart.

### Formats

- **Rates** are fractions from 0 to 1 (`"0.6667"`), rounded to 4 dp.
- **Money** uses 8 dp and **R** uses 4 dp, rounded with ROUND_HALF_EVEN, like ADR 0008.
- **Hold times** are ISO 8601 durations, like `TradeRead.hold_time`.
- **Every decimal goes out as a fixed-point string.**
  - `str(Decimal)` switches to exponent notation for small values: zero at 8 dp prints as `"0E-8"`.
  - That already happened for a trade closed with no fees.
  - A shared `DecimalOut` type (`schemas/base.py`) now serializes every response decimal as `"0.00000000"`.

### Where it's computed

- **In Python, as pure functions** in `domain/analytics.py`, over the filtered closed trades the repository loads.
- **The functions take a small frozen `ClosedTrade` dataclass,** built with the same `calculations` functions as the trade responses, and never ORM objects. So the unit tests run without a database.

### Time zone

- **UTC for date filters and weeks.** Users have no time zone yet.
- **For US-listed swing trades the UTC date is the trading day,** because the regular session (13:30 to 21:00 UTC) falls within one UTC date.

### Grouping

- **`/breakdown?by=`** takes `strategy`, `symbol`, `side`, `asset_type` or `exposure`, and returns the full summary per group, the largest groups first.
- **`exposure`** goes beyond the brief. It reuses ADR 0007, so a long position in an inverse ETF groups with shorts as bearish.
- **For strategies:** the key is the strategy id and the label is its name. Trades without a strategy form one "No strategy" group.

## Alternatives considered

- **Win rate = wins / (wins + losses), ignoring breakevens.** It's common in trading software. But it flatters the number: 1 win, 1 loss and 8 scratches would show 50%, when only 10% of trades made money. It also breaks the expectancy identity above.
- **Breakeven as a tiny band** (say, ±$1) rather than exactly 0. Any band is arbitrary and depends on position size; one in R would be less arbitrary, but still a parameter to argue about. Exactly 0 is objective, and with fees counted, a true 0 is rare.
- **Breakeven counted as a win or a loss.** Either choice distorts the average win or the average loss with zeros.
- **Aggregating in SQL** (`SUM`, `AVG`, window functions for drawdown). It's faster on large data, but the brief requires the math in pure, database-free functions. Drawdown needs ordered, per-trade Decimal math, and the result would be split between SQL and Python. A swing trader closes hundreds of trades a year, not millions. If a profile ever shows loading the trades is the bottleneck, the totals can move into SQL behind the same function signatures.
- **Drawdown on a daily curve.** One point per close date is easier to chart. But it hides a loss followed by a recovery within the same day, and the per-trade curve is what actually happened.
- **Drawdown as a percentage.** That needs account equity, which the API doesn't track.
- **0 for empty averages.** It's simpler for clients, but ambiguous: it would make "no wins yet" look like "wins averaged $0".
- **A user time zone now.** It needs a new column and, on Windows, the `tzdata` package for `zoneinfo`. UTC is right for the current user's US trades; per-user time zones can come later without changing these definitions.

## Consequences

- **Every metric has one definition**, used by the summary, each breakdown group and the weekly review, all through `summarize()`.
- **The numbers can be checked by hand:** the API tests assert a full summary computed on paper, and the end-to-end run matched it.
- **Clients must handle `null`** in rates and averages.
- **Decimals always serialize as fixed-point strings.** A trade closed with no fees now shows `"fees": "0.00000000"` instead of `"0E-8"`. Clients that used `Decimal.Parse` with the defaults could have choked on the old form.
- **A trader in a non-US time zone,** or trading after-hours across midnight UTC, sees dates in UTC until per-user time zones exist.
