# 0006: Password handling

- **Status:** Accepted
- **Date:** 2026-10-26
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

The API stores passwords, so it must store them in a way that survives a database leak. The brief names pwdlib with Argon2. The remaining choices were:

- the password policy
- how to handle login for an unknown email
- what happens when the hashing parameters change
- what registration reveals

## Decision

- **Hashing:** `PasswordHash.recommended()` from pwdlib, which uses Argon2id with pwdlib's current recommended parameters. The stored value is the standard PHC string (`$argon2id$v=19$m=...,t=...,p=...$salt$hash`), so the parameters and salt travel with each hash.
- **Policy: 12–128 characters, no composition rules.** This follows the NIST SP 800-63B direction: length matters, and "one digit, one symbol" rules mostly produce `Password1!`. The 128-character cap stops someone from submitting megabyte-long passwords to burn CPU. Passwords are never logged or returned, and `UserRead` has no hash field.
- **Login timing is the same for known and unknown emails.** When the email doesn't exist, the service still verifies the password against a precomputed dummy hash. Without this, "unknown email" returns after one quick database lookup, while "wrong password" also pays for a deliberately slow Argon2 verify, which lets anyone check whether an email is registered. Both cases return the same 401 and message.
- **Rehash on login.** Login uses `verify_and_update`. If the stored hash was made with older or weaker parameters, a successful login stores a fresh hash with the current ones. Parameter upgrades roll out as users log in, with no migration.
- **Emails are normalized** (trimmed and lowercased) before any lookup or insert. The database also enforces lowercase (`ck_users_email_lowercase`), so `A@x.com` and `a@x.com` can't both register.
- **Brute-force protection** (rate limiting `/auth/token`) is deferred to Phase 2. There it belongs at the ingress or load balancer, rather than in each API process.

## Alternatives considered

- **bcrypt.** It's battle-tested, but it isn't memory-hard, so GPUs and ASICs crack it much faster than Argon2. It also silently truncates passwords at 72 bytes. OWASP lists Argon2id first.
- **scrypt.** Also memory-hard and fine, but Argon2id is the newer standard and is what the brief and pwdlib recommend.
- **Hiding duplicate emails on register** (always return 201, and email the owner instead). That closes the enumeration channel, but needs email delivery, which is out of scope. The issue specifies 409.
- **Composition rules or a breached-password check (HIBP).** Composition rules are out, for the reason above. A breached-password check is worth adding later. It's a network call to an external service, which v1 doesn't otherwise need.

## Consequences

- **Each login and registration costs real CPU time,** tens of milliseconds by design. Endpoints are plain `def` ([ADR 0002](0002-sync-database-access.md)), so hashing runs on the thread pool and doesn't block other requests.
- **`POST /auth/register` reveals whether an email is registered** (409). Login doesn't. That's an accepted trade-off for a personal journal, and the fix is documented above if it ever matters.
- **Until Phase 2 adds rate limiting,** online guessing is slowed only by Argon2's cost and the 12-character minimum.
- **Tests run the real hasher.** It adds about a second to the suite, and that's worth it, because the tests prove real hashes verify.
