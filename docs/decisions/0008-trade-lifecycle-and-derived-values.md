# 0008: Trade lifecycle and derived values

- **Status:** Accepted
- **Date:** 2026-10-27
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

The brief fixes a trade's lifecycle: `planned → open → closed` and `planned → cancelled`, with 409 for illegal transitions. It also fixes the derived values: P/L, R per share, R-multiple and hold time, which are computed and never accepted from the client. Four questions were still open:

- where the state machine lives, and how concurrent requests are handled
- the exact R-multiple definition (fees? planned or actual entry?) and rounding
- what PATCH may change after a trade is entered
- how decimals and durations appear in JSON

## Decision

### Lifecycle

- **The transition table** lives in `domain/lifecycle.py`: `{planned: {open, cancelled}, open: {closed}}`.
  - Every transition endpoint calls `ensure_can_transition`. It raises `ConflictError`, and the API maps that to 409 with a message like "Cannot close a trade that is planned".
  - A test derives the full 4×3 status/action matrix from the table and checks every cell through the API.
- **Pessimistic locking:** each transition loads the trade with `SELECT … FOR UPDATE`. If two "close" requests arrive together, the second waits for the first to commit, then sees `closed` and gets a 409.
- **Defence in depth:** the `ck_trades_status_fields` CHECK (ADR 0004) makes an inconsistent row unstorable even if a code path skips the check.

### Derived values

They're pure functions in `domain/calculations.py`, on `Decimal` only. Stage 5 analytics reuses them.

| Value | Definition | When it's set |
|---|---|---|
| `pnl` | `(exit − entry) × qty` for a long, `(entry − exit) × qty` for a short, **minus fees** | closed |
| `r_per_share` | `abs(planned_entry − planned_stop)`, the **planned** risk | always |
| `r_multiple` | `(pnl ÷ qty) ÷ r_per_share`: net of fees, using the **actual** entry | closed |
| `hold_time` | `exit_at − entry_at` (an ISO 8601 duration such as `P2DT4H30M`) | closed |
| `exposure` | bullish or bearish ([ADR 0007](0007-short-vs-inverse-etf.md)) | always |

- **Rounding:** P/L is quantized to 8 decimal places (the `NUMERIC(20,8)` scale) and the R-multiple to 4, both with `ROUND_HALF_EVEN` (banker's rounding, which doesn't bias sums upward). Calculations run with 50 digits of precision, because the product of two `NUMERIC(20,8)` values can exceed Python's default of 28.
- **Inputs are normalized to their stored form:** decimals to 8 places, timestamps to UTC. A response built right after a write is then identical to a later read from the database.
- **Decimals go out as JSON strings** (`"98.00000000"`), Pydantic's default for `Decimal`. A JSON number would be parsed as a float by most clients, which reintroduces the very error `NUMERIC` avoids.

### PATCH

- **The plan** (symbol, side, asset type, leverage, entry, stop, target, thesis) can change **only while the trade is `planned`**. Afterwards it's the record that `followed_plan` and plan adherence are judged against; editing it would rewrite history. Trying returns 409.
- **`strategy_id`** can change in any status. Re-labelling a trade's setup is classification, not history.
- **Only the fields sent are applied** (`exclude_unset`). `"strategy_id": null` clears it, while omitting it leaves it alone. `null` for a required field is a 422.
- **The merged result is re-validated** (stop side, leverage only on ETFs) *before* anything is modified, so a rejected PATCH leaves nothing half-applied.
- **Unknown fields are rejected** with 422 (`extra="forbid"` on every request model). Otherwise a typo like `planed_stop` would return 200 and silently change nothing.

## Alternatives considered

- **Optimistic locking** (a version column, `UPDATE … WHERE version = :seen`, and 409 or retry on a mismatch). That's the EF Core `[ConcurrencyCheck]`/rowversion approach. It suits long edit sessions where a conflict is rare and blocking is costly. Transitions here are single short transactions, so a row lock is simpler and needs no schema change.
- **A conditional update** (`UPDATE trades SET status = 'closed' WHERE id = :id AND status = 'open'`, then check the row count). It's atomic with no lock held, but it pushes the state machine into SQL and makes the error message ("why did it fail?") harder to get right.
- **A state-machine library** (`transitions`, `python-statemachine`): a dependency for a three-edge graph.
- **Gross R** (before fees) or **R from the planned entry.** Both make results look better than they were. Net R from the actual entry is the honest number, and it's what the brief describes.
- **Storing the derived values.** It's faster to query, but they can drift from their inputs, and the brief forbids accepting them. Stage 5 can add indexed generated columns if analytics needs them.
- **Decimals as JSON numbers.** Friendlier to read, but lossy in JavaScript and in most JSON parsers.

## Consequences

- Every rule the brief states is enforced in one place, with a test per rule, and the database backs up the structural ones.
- A transition holds a row lock for the length of one short transaction. That's harmless at this scale; long-running work must never happen inside a transition.
- Clients must treat money fields as strings and parse them with a decimal type.
- Fixing a mistake in an entered trade's plan means deleting the trade and planning it again, which is deliberate friction. Corrections to entry and exit data aren't supported in v1. If that's needed, it becomes an explicit "amend" endpoint with its own audit trail, not a PATCH loophole.
