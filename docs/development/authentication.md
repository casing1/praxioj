# Authentication and authorization

Milestone 3 replaces the M2 browser identity with registered accounts and revocable server sessions. It remains a localhost development platform. Public deployment, account recovery, email verification, MFA, breach-password screening, production TLS/proxy configuration, and distributed abuse monitoring are not implemented.

## Accounts and credentials

`POST /api/auth/register` and `/api/auth/login` accept `{username, password}`. Usernames normalize to lowercase ASCII and use 3–64 letters, digits, dots, underscores, or hyphens. Passwords require 12–1024 characters and at most 4096 UTF-8 bytes; their exact bytes are hashed without trimming or normalization. Registration always creates a participant. Supplying a role or unknown request field fails validation.

Passwords use the maintained [argon2-cffi high-level PasswordHasher](https://argon2-cffi.readthedocs.io/en/stable/api.html), explicitly configured for Argon2id with 64 MiB, three passes, four lanes, a random 16-byte salt, and a 32-byte output. These are the [RFC 9106 low-memory profile](https://www.rfc-editor.org/rfc/rfc9106.html#section-4) parameters. Successful login checks whether a stored hash needs rehashing. Invalid usernames and passwords receive the same login error; registration still reports that a requested username is unavailable. This is not a claim of perfectly uniform timing or account-enumeration resistance.

No default administrator or password exists. First register an ordinary account, then use the trusted local operator CLI:

```sh
.venv/bin/python -m praxioj_api.cli set-role your_username administrator
.venv/bin/python -m praxioj_api.cli set-role author_username author
```

The CLI requires an active registered account, changes its role, and revokes all existing login sessions. Sign in again afterward. CLI access and database access are trusted operator capabilities; there is no HTTP privilege-bootstrap route.

## Session and CSRF protocol

Successful registration/login returns `{user: {id, username, role}, csrf_token, expires_at}`. `GET /api/auth/me` returns the same projection or HTTP 401. Authentication creates fresh independent 256-bit random session and CSRF tokens. Only SHA-256 token digests are stored in `auth_sessions`; the password hash is separate in `users`. The presented session for the same account is revoked when login rotates it. When switching accounts, log out first to revoke the old account's session; signing into a different account replaces browser cookies without revoking that other account's server sessions. Each account has at most five live sessions.

The `praxioj_session` and `praxioj_csrf` cookies are both HttpOnly, SameSite=Strict, host-only, path `/`, and have explicit Max-Age/Expires. Their default lifetime is eight hours; `PRAXIOJ_AUTH_SESSION_SECONDS` permits 60 seconds through 24 hours. There is no sliding extension. `PRAXIOJ_COOKIE_SECURE=true` sets Secure for a separately configured HTTPS development environment; localhost HTTP defaults to false. Allowed origins must match the development server settings. Never expose the HTTP setup publicly.

Both cookies remain unavailable to JavaScript. The same-origin `/api/auth/me` endpoint verifies the CSRF cookie against the stored digest and returns its value to the frontend. The frontend holds that token in memory and sends `X-CSRF-Token` for authenticated state changes. The server compares its digest using constant-time comparison. Login and registration additionally require an explicit allowed Origin. Every mutation retains the existing JSON-content-type, Origin, Sec-Fetch-Site, host, and body-size guards; there is no permissive CORS configuration. A non-browser client must supply an allowed Origin to authenticate and the issued CSRF token on later writes.

`POST /api/auth/logout` with JSON `{}` and a valid CSRF header revokes the current server session and clears both cookies. Expired, revoked, inactive, or incomplete sessions cannot authenticate. Login does not adopt a caller-supplied session token. Passwords, session tokens, and CSRF tokens are excluded from Trace; validation errors omit submitted input values and contexts.

## Persistent throttles

Registration and login share a PostgreSQL-backed fixed-window throttle: 30 attempts per socket peer and 10 per normalized username in five minutes. PostgreSQL locks serialize updates. Failed attempts commit their counters; opening another browser or changing `X-Forwarded-For` cannot reset them. Over-limit requests return 429 with Retry-After. Stored keys are purpose-specific hashes; raw IP addresses and passwords are not stored in these counters. Expired counter rows are pruned during authentication. Expired login sessions are pruned when that same account authenticates again. These basic limits are not a distributed denial-of-service defense, and an attacker can deliberately exhaust an account's short window.

## Resource authorization

All solve-session, conversation, run, tool-result, file, submission, evaluation, and participant Trace operations require an active account and server-enforced ownership. A missing login yields 401; missing roles yield 403; an inaccessible owner resource yields 404. User and role identifiers supplied by clients never establish identity. Authenticated writes lock the account before session/job resources so role changes and account deletion serialize with those mutations.

Public problem projections remain readable without login and exclude private evaluator configuration. `GET/POST /api/author/problems` require author or administrator. An author publishes immutable versions only for their own problem; another author's problem and legacy operator-managed problems cannot be adopted. An administrator can publish versions of any problem. `GET /api/admin/users` requires administrator and returns only account identifiers, usernames, and roles, bounded to 100 records. The trusted CLI can still register operator-managed sample manifests without an author owner.

## Migration and data handling

Migration `0003_authentication` adds nullable usernames/password hashes and inactive status for existing M1/M2 identities. It does not infer passwords, accept old cookies, or promote legacy roles. Existing problems retain a null author and remain operator-managed. Historical sessions, messages, submissions, and evaluation data are preserved in quarantine; ordinary registration creates a new account with a different ID. No automatic claim/reassignment workflow is provided. Operators must address legacy retention explicitly rather than treating the old cookie as proof of account ownership.

The new runtime dependencies retain their own licenses: argon2-cffi 25.1.0 and argon2-cffi-bindings 26.1.0 (MIT), cffi 2.1.1 (MIT-0), and pycparser 3.12 (BSD-3-Clause). Dependencies are installed separately and preserve their installed license files; PraxiOJ remains Apache-2.0. Actual binary/container distributions still require the artifact review described in [licensing](licensing.md).
