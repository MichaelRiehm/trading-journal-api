# 0010: Journal phases can't run ahead of the trade

- **Status:** Accepted
- **Date:** 2026-10-27
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

Every journal entry has a phase: `pre` (before entry), `during` (while open) or `post` (after it's over). The brief doesn't say whether the phase must match the trade's status, and issue #4 asks for that to be decided. The weekly review (Stage 5) groups entries by trade and phase, so nonsense phases would pollute the feature the journal exists for.

Two real usage patterns pull in opposite directions:

- **Live journaling:** write the plan, note thoughts while the trade runs, then reflect after closing. Here phase matches status naturally.
- **Backfilling:** log a trade after the fact (plan, open and close within a minute), then write down what you were thinking *before* entry. A `pre` note on a closed trade is legitimate.

## Decision

**A phase may not run ahead of the trade. Writing about the past is allowed.**

| Trade status | Allowed phases | Default when `phase` is omitted |
|---|---|---|
| planned | pre | pre |
| open | pre, during | during |
| closed | pre, during, post | post |
| cancelled | pre, post | post |

- **A violation returns 409** ("A post entry needs a closed or cancelled trade; this one is open"). The request is well-formed but conflicts with the trade's current state, the same category as an illegal lifecycle transition (ADR 0008).
- **A cancelled trade never opened**, so `during` is impossible. `post` is allowed, because "why I skipped this setup" is exactly the reflection the brief keeps cancelled trades for.
- **The rule applies on create, and on a PATCH that changes `phase`.**
- **The rules are data:** `ALLOWED_PHASES` and `DEFAULT_PHASE` in `domain/journal_rules.py`, next to the lifecycle table. The API tests derive their 4×3 matrix from it.
- **Entries can be edited and deleted at any time.** `updated_at` is in every response, so an after-the-fact edit is visible rather than hidden.
- **No row lock.** Trade transitions lock the row (ADR 0008); journal writes don't need to. Statuses only move forward, and along every legal transition the allowed set only grows (planned ⊂ open ⊂ closed, and planned ⊂ cancelled). So if an entry was valid when its check ran, a transition committed a moment later leaves it still valid. A unit test asserts this property over the lifecycle table. If a future change ever breaks it, that test fails and the locking question comes back.

## Alternatives considered

- **Strict match** (only `pre` while planned, only `during` while open, only `post` after). It's simple, but it blocks backfilling, which is a primary use. It would also make the phase field redundant, since it could always be derived.
- **No rule.** It's flexible, but it allows a `post` "lessons learned" on a trade that hasn't finished, and a `during` note on a trade that never opened. The weekly review would show them as if they were real.
- **422 instead of 409.** 422 means the request is invalid in itself. A `post` entry is perfectly valid for a closed trade; it's only wrong *for this trade's current state*, which is what 409 is for.
- **Locking `pre` entries once the trade opens,** by analogy with the plan lock in ADR 0008. The plan is structured data that analytics (plan adherence) measures against. The journal is free-text reflection that no number depends on. A lock would add friction without protecting anything, so transparency (`updated_at`) is the lighter tool.
- **Storing a `user_id` on entries.** That would allow a direct ownership filter instead of a join, but it duplicates data the trade already holds, and the two could disagree. Ownership through the trade, with a join on `trades.user_id`, has been the design since Stage 1.

## Consequences

- Live journaling needs no phase at all: the default follows the trade.
- Backfilling works for every earlier phase. Only the future is closed off.
- An edit made after the fact can be spotted (`updated_at > created_at`), and Stage 5's weekly review can flag it.
- Adding a status or phase later means extending two small tables. The growth-property test then checks the new combination too.
