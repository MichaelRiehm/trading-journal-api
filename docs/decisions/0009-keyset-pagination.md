# 0009: Keyset pagination

- **Status:** Accepted
- **Date:** 2026-10-27
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

`GET /trades` needs pagination. A swing trader accumulates hundreds of trades a year, and Phase 3 imports (TradingView alerts, Webull fills) can add many more. Trades are also created *while* a client pages through the list. Stage 6 will apply the same pattern to other lists.

## Decision

- **Keyset (cursor) pagination on the primary key**, newest first:
  - The request is `GET /trades?limit=50&cursor=<id>`, where `limit` defaults to 50 and must be between 1 and 200.
  - The response is `{"items": [...], "next_cursor": "<id>" | null}`. `next_cursor` is the last id on the page, and it's `null` on the last page.
  - The query is `WHERE user_id = :me [AND filters] AND id < :cursor ORDER BY id DESC LIMIT :limit + 1`. The extra row tells us whether another page exists, without a `COUNT(*)`.
- **This works because ids are UUIDv7** ([ADR 0004](0004-schema-conventions.md)): their leading bits are a millisecond timestamp, so ordering by id is creation order. The id is unique, so there are no ties to break, and the primary-key index serves the sort.
- **The cursor is the raw id,** not an encoded token. It reveals nothing a client doesn't already have, since it's the id of a trade on the page it just received.
- **Filters combine with the cursor.** A client must keep the same filters across pages; changing them mid-stream just starts a different list.
- **Strategies aren't paginated.** A user has a handful, returned sorted by name.

## Alternatives considered

- **Offset pagination** (`?page=3&size=50` → `OFFSET 100 LIMIT 50`). It's familiar and allows "jump to page 7", but it has two problems:
  - A trade inserted while paging shifts every later page, so rows get repeated or skipped. A test checks that ours doesn't.
  - `OFFSET n` still reads and discards `n` rows, so deep pages get slower.
  - Jumping to arbitrary pages isn't something an API client of a journal needs.
- **An opaque, encoded cursor** (base64 of `(created_at, id)`). That's needed when the sort key isn't unique. With UUIDv7 the id alone is both unique and time-ordered, so encoding would add a decode step and an error case for no gain. If the list ever needs another sort order (for example by `exit_at` in analytics), that endpoint switches to an encoded `(sort_key, id)` cursor.
- **No pagination with a hard cap.** It would hide data silently once the cap is hit.

## Consequences

- Pages are stable under concurrent inserts, and every page costs the same, however deep.
- Clients can only go forward. Going back means remembering earlier cursors, which is normal for feeds.
- There's no total count in the response. If a UI ever needs one, it's a separate `COUNT(*)` endpoint, so the list stays cheap.
- "Newest first" means newest by *creation*, not by entry or exit date. A backfilled trade from last year appears at the top. Analytics endpoints that care about trade dates sort by those explicitly.
- Ordering depends on UUIDv7's time prefix. The ids come from Python's `uuid.uuid7()`, which keeps them monotonic within a process. Across several API pods, ids created in the same millisecond can interleave, which is harmless here.
