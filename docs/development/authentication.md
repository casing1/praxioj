# Authentication and authorization

Milestone 4 extends the M3 account foundation with explicit password confirmation, password changes, owned-session management, generic registration responses, request admission and authentication audit. It remains a localhost development platform. Public deployment, account recovery, email verification, MFA, breach-password screening, production TLS/proxy configuration, and distributed abuse monitoring are not implemented.

## Accounts and credentials

`POST /api/auth/register` and `/api/auth/login` accept `{username, password}`. Usernames normalize to lowercase ASCII and use 3–64 letters, digits, dots, underscores, or hyphens. Passwords require 12–1024 characters and at most 4096 UTF-8 bytes; their exact bytes are hashed without trimming or normalization. Registration always creates a participant. Supplying a role or unknown request field fails validation.

Passwords use the maintained [argon2-cffi high-level PasswordHasher](https://argon2-cffi.readthedocs.io/en/stable/api.html), explicitly configured for Argon2id with 64 MiB, three passes, four lanes, a random 16-byte salt, and a 32-byte output. These are the [RFC 9106 low-memory profile](https://www.rfc-editor.org/rfc/rfc9106.html#section-4) parameters. Successful login checks whether a stored hash needs rehashing. Invalid usernames and passwords receive the same login error, with dummy Argon2 verification for missing/inactive accounts.

Registration now returns **202** and the same generic `{message}` for available and existing valid usernames. It performs one Argon2 hash in either branch, never changes an existing password and never sets login cookies. The user must explicitly sign in afterward. This intentionally changes M3's 201/automatic-login contract; SDK callers and smoke helpers must register, then log in. Generic response shape, dummy work, and throttles reduce direct account enumeration; database work and network timing are not perfectly indistinguishable. Open username registration still permits attempts to claim unused names and then sign in; stronger resistance would need a separately trusted enrollment workflow. This does not establish verified real-world identity.

No default administrator or password exists. First register an ordinary account, then use the trusted local operator CLI:

```sh
.venv/bin/python -m praxioj_api.cli set-role your_username administrator
.venv/bin/python -m praxioj_api.cli set-role author_username author
```

The CLI requires an active registered account, changes its role, and revokes all existing login sessions. Sign in again afterward. CLI access and database access are trusted operator capabilities; there is no HTTP privilege-bootstrap route.

## Session and CSRF protocol

Successful login returns `{user: {id, username, role}, csrf_token, expires_at, reauthenticated_until}`. `GET /api/auth/me` returns the same projection or HTTP 401. A new login has `reauthenticated_until=null`. Authentication creates fresh independent 256-bit random session and CSRF tokens. Only SHA-256 token digests are stored in `auth_sessions`; the password hash is separate in `users`. The presented session for the same account is revoked when login rotates it. When switching accounts, log out first to revoke the old account's session; signing into a different account replaces browser cookies without revoking that other account's server sessions. The default cap is five live sessions; `PRAXIOJ_AUTH_MAX_SESSIONS` accepts 1–10. New logins revoke the oldest sessions beyond that cap.

The `praxioj_session` and `praxioj_csrf` cookies are both HttpOnly, SameSite=Strict, host-only, path `/`, and have explicit Max-Age/Expires. Their default lifetime is eight hours; `PRAXIOJ_AUTH_SESSION_SECONDS` permits 60 seconds through 24 hours. There is no sliding extension. `PRAXIOJ_COOKIE_SECURE=true` sets Secure for a separately configured HTTPS development environment; localhost HTTP defaults to false. Allowed origins must match the development server settings. Never expose the HTTP setup publicly.

Both cookies remain unavailable to JavaScript. The same-origin `/api/auth/me` endpoint verifies the CSRF cookie against the stored digest and returns its value to the frontend. The frontend holds that token in memory and sends `X-CSRF-Token` for authenticated state changes. The server compares its digest using constant-time comparison. Login and registration additionally require an explicit allowed Origin. Every mutation retains the existing JSON-content-type, Origin, Sec-Fetch-Site, host, and body-size guards; there is no permissive CORS configuration. A non-browser client must supply an allowed Origin to authenticate and the issued CSRF token on later writes.

`POST /api/auth/logout` with JSON `{}` and a valid CSRF header revokes the current server session and clears both cookies. Expired, revoked, inactive, or incomplete sessions cannot authenticate. Login does not adopt a caller-supplied session token. Passwords, session tokens, and CSRF tokens are excluded from Trace; validation errors omit submitted input values and contexts.

`GET /api/auth/sessions` lists at most ten owned active sessions with only `{id, created_at, expires_at, current}`. `POST /api/auth/sessions/{id}/revoke` with JSON `{}` revokes an owned session; repeating the same revocation is safe. Another account's identifier yields 404. Revoking the current session clears its cookies. No IP addresses, token hashes or other users' sessions are exposed.

`POST /api/auth/password` accepts `{current_password,new_password}`. It verifies the current password under the account lock, updates its Argon2id hash, revokes **all** login sessions and confirmations, and returns 204 with cleared cookies. Sign in again. A wrong current password returns 403 and does not change credentials. Concurrent changes serialize; a session revoked by the first change cannot authorize a stale second change.

## Explicit confirmation for sensitive data actions

`POST /api/auth/reauthenticate` accepts `{password}` and requires a valid session, CSRF and normal origin/body boundaries. A successful verification stores `AuthSession.reauthenticated_at` and returns `{expires_at}`. The confirmation lasts 300 seconds by default (`PRAXIOJ_AUTH_REAUTHENTICATION_SECONDS`, 60–900), never longer than the underlying login. It is bound to that one server session, not the account as a whole. Login alone is not confirmation. Expiry, logout, session revocation and password change invalidate authority. Export/deletion use `require_recent_reauthentication`, which acquires the account mutation lock and refreshes session revocation before checking the marker. Wrong confirmation passwords return 403 without pretending the authenticated session expired.

MFA and password recovery need a separately trusted enrollment/recovery channel, recovery-code handling, key storage and abuse controls. No temporary email, guessed recovery answers, administrator default credentials or insecure reset shortcut is provided.

## Persistent throttles

Registration and login share a PostgreSQL-backed fixed-window throttle: 30 attempts per socket peer and 10 per normalized username in five minutes (`PRAXIOJ_AUTH_IP_LIMIT`, `PRAXIOJ_AUTH_ACCOUNT_LIMIT`, `PRAXIOJ_AUTH_RATE_WINDOW_SECONDS`; account ≤ peer ≤ 1000 and window 1–3600 seconds). Registration plus a subsequent login consumes two attempts. Password confirmation/change use separately namespaced peer/account counters with those same bounds. PostgreSQL row locks serialize updates across API instances; failed attempts commit counters rather than rolling them back. A fixed window expires normally and does not permanently lock an account.

API admission adds a separate peer budget before route transactions: 600 requests per 60 seconds by default (`PRAXIOJ_API_IP_LIMIT`, 1–10000; `PRAXIOJ_API_RATE_WINDOW_SECONDS`, 1–3600). Failed and nonexistent routes consume capacity. `/health` and `/api/health` are the only liveness exceptions. The bounded SQL work runs off the async event loop, commits before account locks, and fails closed with safe 503 if the rate store is unavailable. It does not open a nested connection while an account mutation holds one. Account-level resource quotas independently limit expensive work.

Over-limit requests return 429 with `Retry-After`, `RateLimit-Limit`, `RateLimit-Remaining` and `RateLimit-Reset` (seconds until that window resets). Permitted responses expose the relevant remaining budget; authentication-specific headers take precedence over general API headers. Stored keys are purpose-specific hashes; raw IP addresses, passwords and tokens are not stored in these counters. Expired rows are pruned by bounded maintenance rather than an unbounded delete on every login. Account login also removes that account's expired login rows.

Each bucket reservation uses a single atomic `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`. Its fixed-window decision and bounded denial counter are returned by the same statement. Authentication still acquires peer then account buckets and stops at an exhausted peer before creating arbitrary account rows. No correctness decision depends on a later unlocked read. Confirmation uses a separate purpose so account-first mutations do not invert login bucket/account lock order.

Only the transport peer is used. The shipped Uvicorn commands disable proxy-header interpretation with `--no-proxy-headers`; arbitrary `X-Forwarded-For` and `Forwarded` values cannot select a rate bucket. Requests through nginx conservatively share nginx's peer budget. A future deployment must explicitly define trusted proxies before extracting forwarded addresses; no production trust-proxy mode is currently provided. These limits are not DDoS protection, and a distributed attacker can still consume a known account's short authentication window.

Authentication audit records contain controlled action/reason codes and bounded pseudonymous IDs, never submitted passwords, session/CSRF tokens or raw usernames/IPs. Successful registration/login/logout, confirmation, password changes and session revocation are recorded separately from participant Trace. Permitted failed authentication attempts are recorded; repeated blocked attempts produce only one persistent throttle audit per bucket/window, avoiding an unbounded audit flood. Structured API rejection logs contain controlled codes without request payloads. The audit retention policy remains independently bounded.

## Resource authorization

All solve-session, conversation, run, tool-result, file, submission, evaluation, and participant Trace operations require an active account and server-enforced ownership. A missing login yields 401; missing roles yield 403; an inaccessible owner resource yields 404. User and role identifiers supplied by clients never establish identity. Authenticated writes lock the account before session/job resources so role changes and account deletion serialize with those mutations.

Public problem projections remain readable without login and exclude private evaluator configuration. `GET/POST /api/author/problems` require author or administrator. An author publishes immutable versions only for their own problem; another author's problem and legacy operator-managed problems cannot be adopted. An administrator can publish versions of any problem. `GET /api/admin/users` requires administrator and returns only account identifiers, usernames, and roles, bounded to 100 records. The trusted CLI can still register operator-managed sample manifests without an author owner.

## Migration and data handling

Migration `0003_authentication` adds nullable usernames/password hashes and inactive status for existing M1/M2 identities. It does not infer passwords, accept old cookies, or promote legacy roles. Existing problems retain a null author and remain operator-managed. Historical sessions, messages, submissions, and evaluation data are preserved in quarantine; ordinary registration creates a new account with a different ID. No automatic claim/reassignment workflow is provided. Operators must address legacy retention explicitly rather than treating the old cookie as proof of account ownership.

Migration `0006_auth_hardening` adds only nullable `reauthenticated_at`. Existing login sessions remain usable until expiry but are unconfirmed; no historical timestamp is invented. Downgrade removes that confirmation column and does not restore revoked sessions or former passwords. API clients relying on registration auto-login must be updated with the M4 server/frontend together.

## Optimization and verification evidence

The M4 review identified a redundant insert/select/update sequence per rate bucket. The initial working M4 implementation made 11 SQL statements per invalid login (general API reservation, authentication reservations, user lookup and audit); replacing bucket reservations with atomic UPSERT reduced that to **5 statements**, a **54.5% reduction in statement count** for that exact path. Fixed-window, saturation, first-denial audit, concurrent authentication and multi-API admission tests verify the decisions remain correct. Removing the unbounded expired-counter deletion from authentication also makes per-request work independent of the historical expired-row backlog; maintenance now owns bounded cleanup.

Reproduce the synthetic workload with `.venv/bin/python scripts/benchmark-auth.py`. Recorded environment: macOS 27.0.1 arm64, Python 3.13.5, temporary SQLite database, ASGI TestClient, eight invalid-password requests for an existing account and eight for a missing account, unchanged Argon2id parameters. Initial M4 medians were 37.32/36.96 ms with 11 statements; optimized medians were 46.81/43.32 ms with 5 statements. Host load was not isolated, so these latency samples do **not** establish a speedup or production throughput. The demonstrated improvement is fewer SQL round trips, with the security/reliability trade-off of retaining database admission on every non-health request. M3's earlier baseline was 8 statements and 48.30/49.05 ms before API admission/audit existed; it is a compatibility baseline, not the optimization comparison.

Argon2 parameters were not weakened, authentication work remains off the async route loop, and no cache replaces authoritative session/role checks. More complex scheduler infrastructure, hash tuning or broad auth refactoring was reviewed; no justified optimization was identified for this development-scale workload. PostgreSQL remains the concurrency validation backend; SQLite measurements do not establish PostgreSQL throughput.

The authentication dependencies introduced in M3 retain their own licenses: argon2-cffi 25.1.0 and argon2-cffi-bindings 26.1.0 (MIT), cffi 2.1.1 (MIT-0), and pycparser 3.12 (BSD-3-Clause). Dependencies are installed separately and preserve their installed license files; PraxiOJ remains Apache-2.0. Actual binary/container distributions still require the artifact review described in [licensing](licensing.md).
