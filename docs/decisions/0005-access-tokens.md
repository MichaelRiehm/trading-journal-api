# 0005: Access tokens

- **Status:** Accepted
- **Date:** 2026-10-26
- **Author:** Drafted by Claude. Not yet reviewed by Michael.

## Context

Every endpoint except `/health`, `/ready` and the two `/auth` endpoints needs to know who the caller is. The brief fixes some of the shape:

- the OAuth2 password flow at `POST /auth/token`
- PyJWT and pwdlib
- **no refresh tokens and no email verification in v1**

The API is the only thing that issues tokens and the only thing that checks them. Phase 2 runs it on EKS behind HTTPS, possibly with more than one replica.

## Decision

- **Format:** stateless JWT access tokens.
- **Algorithm:** HS256, signed with `JWT_SECRET_KEY`.
- **Claims:**

  | Claim | Value | Why |
  |---|---|---|
  | `sub` | the user's UUID | Who the token is for. The UUIDv7 id never changes, unlike the email. |
  | `iat` | issued-at time | Auditing, and a hook for "log out everywhere" later (reject tokens issued before a cutoff). |
  | `exp` | `iat` + `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60) | Limits how long a leaked token works. |
  | `iss` / `aud` | `"trading-journal-api"` | A token minted for some other service with the same key isn't accepted here. |

- **Decoding is strict:**
  - **`algorithms=["HS256"]` is pinned,** never read from the token header. This blocks `alg: none` and algorithm-confusion attacks.
  - **Every claim is required:** `exp`, `iat`, `sub`, `iss` and `aud`. `iss` and `aud` must match.
  - **`sub` must parse as a UUID.**
  - **The user is then loaded from the database,** so a deleted user's token stops working immediately.
- **Every failure looks the same to the client:** missing token, bad signature, expired, wrong audience or deleted user. Each gets the same 401 with `WWW-Authenticate: Bearer` (RFC 6750) and the same message.
- **The key:**
  - It's a `SecretStr` with no default and a minimum of 32 characters, and the app checks it at startup.
  - Startup errors never echo the rejected value (`hide_input_in_errors`).
  - Only the `api` container receives it. The `migrate` container reads `DatabaseSettings`, which doesn't include it.

## Alternatives considered

- **RS256 or EdDSA (asymmetric keys).** These let *other* services verify tokens with a public key while only the issuer holds the private key. Here, issuer and verifier are the same process, so asymmetric keys add key-pair management for no benefit. **Upgrade trigger:** a second service (the Phase 4 algo lab, say) needs to verify these tokens.
- **Server-side sessions** (an opaque id in a cookie or header, looked up per request). They give instant revocation, but cost a session store and a lookup on every request. We already load the user per request, so the lookup cost is similar. What sessions really add is a second piece of state to run, plus CSRF handling if cookies are used. Not worth it for v1.
- **Long-lived tokens (days).** Fewer logins, but a leaked token would work for days with no way to revoke it. Refresh tokens are the usual fix, and they're out of scope.
- **Opaque random tokens stored in the database.** That's essentially sessions, with the same trade-off as above.

## Consequences

- **No revocation before expiry.** Logging out only discards the token on the client. If a token leaks, it works for up to 60 minutes. Mitigations, if ever needed:
  - shorten the expiry
  - add a per-user "tokens issued before X are invalid" timestamp checked against `iat`
  - rotate the key, which invalidates *everyone's* tokens
- **Rotating the key logs everyone out.** That's acceptable for a personal journal. A `kid` header and a key ring would avoid it, at more complexity.
- **Clients re-login every hour.** That's fine for a Swagger UI and scripts. Phase 3 integrations authenticate differently: the TradingView webhook uses a shared secret, and the Webull sync is a server-side job.
- **Any replica can verify any token** with no shared state beyond the key. That suits Phase 2's multiple pods.
- **The OAuth2 password grant is deprecated in OAuth 2.1,** because it hands the password to the client. We use its *form shape* (which is what the `/docs` Authorize button speaks) for a first-party API. Nothing third-party ever sees the password.
