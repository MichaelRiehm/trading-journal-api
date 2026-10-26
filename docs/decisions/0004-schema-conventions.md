# 0004: Schema conventions

- **Status:** Accepted
- **Date:** 2026-10-26
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

This schema holds money and trading history for multiple users. The brief requires:
- exact decimals (never float)
- ownership on every row, with 404, not 403, for other users' data
- a planned stop on the losing side of the entry
- a strict lifecycle (planned → open → closed, planned → cancelled)
- room for Phase 3 imports (`source`, `external_id`)

The service layer (Stage 3) will validate all of this. The question is how much the database enforces on its own.

## Decision

1. **Primary keys are UUIDv7**, generated in Python with `uuid.uuid7()` (stdlib since 3.14).
   - They're time-ordered, so inserts land at the end of the index like a sequence would.
   - They're unguessable, so ids in URLs don't reveal how many rows exist or invite enumeration. That supports the 404-not-403 rule.
2. **Money, prices, quantities and fees are `NUMERIC(20, 8)`**, mapped to `Decimal`.
   - 12 integer digits and 8 decimals cover stock prices, sub-cent crypto prices (`0.00001234`) and fractional crypto quantities.
   - No float columns anywhere.
3. **Enums are `VARCHAR` plus a `CHECK` constraint**, not native Postgres `ENUM` types. Python `StrEnum` classes in `trading_journal.domain.enums` are the source of truth.
4. **Timestamps are `timestamptz`**, stored in UTC. `created_at` and `updated_at` are set by the database.
5. **The database enforces invariants as a backstop**, through CHECK constraints:
   - prices and quantity > 0, and fees ≥ 0
   - leverage in {2, 3, -2, -3}
   - the planned stop on the losing side for the trade's side
   - `exit_at >= entry_at`
   - **status/field consistency:** a planned or cancelled trade has no entry or exit fields; an open trade has entry fields only; a closed trade has all of them, including `followed_plan`
6. **The database enforces ownership:**
   - Strategy names are unique per user, emails are unique and stored lowercased, and `external_id` is unique per (user, source).
   - **A composite foreign key `trades(strategy_id, user_id) → strategies(id, user_id)` means a trade can't reference another user's strategy**, even through a bug.
   - Deleting a user cascades to their data. A strategy that still has trades can't be deleted (`RESTRICT`).
7. **A naming convention** on the metadata (`ck_trades_status_fields`, `fk_trades_strategy_id_user_id_strategies`, and so on) gives migrations deterministic names and makes errors readable.

## Alternatives considered

- **Auto-increment integer ids.** Simpler and smaller, but sequential ids leak counts and invite enumeration. **Random UUIDv4** fixes that, but scatters inserts across the index; v7 has the benefits of both.
- **`float` or unbounded `NUMERIC`.** Floats can't represent 0.1 exactly, which is unacceptable for P/L. Unbounded `NUMERIC` would silently accept nonsense precision.
- **Native Postgres `ENUM`.** Type-safe, but adding a value means `ALTER TYPE`, which has transaction caveats, and removing one is painful. `source` will grow in Phases 3 and 4.
- **Validation only in the service layer.** It's needed anyway for good error messages. On its own, though, one missed check or a manual SQL fix can store an impossible trade, and analytics would silently count it.

## Consequences

- Illegal states are hard to store, and analytics can trust the data.
- The service layer still validates first, so users get 422 or 409 with clear messages; the constraints are the safety net.
- Each constraint has a test in `tests/test_constraints.py`, because Alembic autogenerate doesn't detect CHECK constraint changes. A CHECK change needs a hand-written migration.
- Changing a lifecycle rule now means changing the `status_fields` constraint as well as the service.
