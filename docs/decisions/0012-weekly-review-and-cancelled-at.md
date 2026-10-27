# 0012: The weekly review, and recording when a trade was cancelled

- **Status:** Accepted
- **Date:** 2026-10-27
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

`GET /reviews/weekly?week=2026-W42` is the reflection feature. For one week it shows:

- the trades closed and cancelled that week
- the week's summary and plan adherence
- every journal entry for those trades, grouped by trade and phase

Three questions needed answers:

1. **What exactly is "a week",** and how is a `week` value validated?
2. **When was a trade cancelled?** Closed trades have `exit_at`. Cancelled trades had no timestamp of their own. The only candidate was `updated_at`, which also moves when the strategy is reassigned, so a trade cancelled in W40 and re-tagged in W43 would show up in W43.
3. **How should the journal be loaded** without one query per trade?

## Decision

### Weeks are ISO 8601 weeks in UTC

- **Format:** `week` must match `YYYY-Www` exactly, and the week must exist; otherwise it's a 422.
  - Checked with a regex, then `date.fromisocalendar`.
  - That rejects `W00`, `W54`, and `W53` in a year that only has 52.
- **The window** runs from Monday 00:00 UTC up to (not including) the next Monday. A trade closed on Sunday at 23:59:59 belongs to that week; one closed at Monday 00:00:00 belongs to the next.
- **When `week` is omitted,** it defaults to the current ISO week.
- **The ISO year can differ from the calendar year:** 2025-12-29 is in `2026-W01`, and 2027-01-01 is in `2026-W53`.
- **UTC,** for the reasons in ADR 0011.

### A `cancelled_at` column (migration 0003)

- **What it is:** a nullable `timestamptz`, set by `POST /trades/{id}/cancel` and returned in `TradeRead`.
- **A CHECK enforces it:** the `status_fields` constraint is extended so that `cancelled_at` is set if, and only if, the status is `cancelled`.
- **Existing rows:** cancelled trades from before the migration are backfilled with `updated_at`, the best estimate available. A test runs the migration over pre-existing rows.
- **Index:** `(user_id, cancelled_at)`, matching the existing `(user_id, exit_at)` used for closed trades.
- **The migration copies its constraint SQL** rather than importing it from the model, so the migration keeps meaning the same thing when the model changes later.

### The response

- **`week`, `starts_at` and `ends_at`.**
- **`summary`:** the same metrics as `/analytics/summary` (ADR 0011), for the week's **closed** trades only. Cancelled trades have no P/L, so they don't count here.
- **`closed` and `cancelled`:** each a list of `{trade, journal: {pre, during, post}}`, with the trades in the order they closed or were cancelled, and the entries in each phase oldest first.
- **Edited entries:** each entry carries `created_at` and `updated_at`, so one edited after the fact is visible in the review.

### One query for the journal

- **How:** `JournalEntryRepository.list_for_trades` loads every entry for the week's trades in one `WHERE trade_id IN (...)` query, joined to `trades` for ownership. The entries are then grouped in Python.
- **The cost:** three queries per review (closed, cancelled, entries), whatever the number of trades.

## Alternatives considered

- **Infer the cancel time from `updated_at`.** That needs no migration, but it's wrong whenever a cancelled trade is edited afterwards (reassigning its strategy is allowed in any status).
- **A status-history table** (one row per transition, with a timestamp). It's more general: it would also record when a trade opened, separately from `entry_at`. But it's a larger change, and every timestamp it would hold already exists as a column except this one. It's worth revisiting if the brief ever needs a full audit trail.
- **Use `created_at` for cancelled trades.** A plan made on Monday and skipped on Thursday would then be in the wrong week for anything planned before the week began.
- **Calendar weeks (Sunday start) or a free date range.** ISO weeks are the international standard, unambiguous across year ends, and named in the brief's own example (`2026-W42`). A free range already exists in `/analytics` through `start_date` and `end_date`.
- **Requiring `week`.** Defaulting to the current week makes "how's my week going?" a parameter-free call, and a bad value is still a 422.
- **Loading journals per trade** (the N+1 pattern). It's simple, but the number of queries grows with the number of trades. One `IN` query costs the same for 3 trades or 300.

## Consequences

- **Cancelled trades land in the week they were actually cancelled,** whatever is edited later. Rows cancelled before the migration carry an estimate.
- **The `status_fields` CHECK grows by one column per status.** An impossible combination (a planned trade with `cancelled_at`, or a cancelled trade without it) can't be stored.
- **Open trades are not in the review.** That's deliberate: it reviews what finished or was skipped. `GET /trades?status=open` shows the rest.
- **The review's summary** is the same computation as `/analytics/summary` with that week's dates, so the two can't disagree.
