# Local setup

Run commands from the repository root. Milestone 4 adds quotas, worker operations and private data management, but remains a localhost development preview. Use the same browser host (`127.0.0.1` or `localhost`) throughout a session. No API key is needed for the default Mock provider.

## Docker Compose

With Docker Compose v2 and a running engine:

```sh
docker compose config --quiet
docker compose up --build -d --wait
```

Open http://127.0.0.1:5173, register an account and explicitly sign in. Registration uses a generic acknowledgement without issuing a cookie. There is no default administrator or password. API documentation is at http://127.0.0.1:8000/api/docs; health is at http://127.0.0.1:8000/api/health.

The API waits for PostgreSQL, applies migrations, and idempotently registers `release-plan`, `workspace-plan`, and `evidence-plan`. The worker starts after API health succeeds and polls the durable queue. Web serves the UI and proxies `/api`. API startup itself does not execute queued AI work. The worker uses the same image and server-side environment as the API; it publishes no port. Both run as an unprivileged container user.

```sh
docker compose ps
docker compose logs --tail=100 api worker
python3 scripts/smoke.py
python3 scripts/smoke-m2.py
python3 scripts/smoke-m3.py --base-url http://127.0.0.1:5173
python3 scripts/smoke-m4.py --base-url http://127.0.0.1:5173
```

Only API and web loopback ports are published. PostgreSQL shares an internal backend network with API/worker and is unpublished by default. API/worker also use the normal bridge network for configured provider connections. Outbound networking is not isolated; these containers are not an untrusted-code sandbox. Use `config --quiet`, not an expanded configuration dump that could reveal optional credentials.

To grant a role to an account already registered through the UI:

```sh
docker compose exec api python -m praxioj_api.cli set-role your_username author
```

Replace `your_username` with the registered username. The role can be `participant`, `author`, or `administrator`; the command revokes that account's login sessions and records a role-change audit. Sign in again afterward. Operator shell/database access is trusted. Legacy M2 browser identities cannot be promoted using this command.

Stop the local stack with:

```sh
docker compose down
```

This preserves the database volume. Do not remove the volume to fix a migration or version conflict. A changed problem needs a new immutable version.

## Native API, worker, and Vite

Use Python 3.13 and Node 24 LTS. The frontend also declares support for Node 22.12+ on the 22.x line and Node 26+; the recorded host runtime is Node 24.11.0. Install the pinned dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -c requirements.lock -e packages/framework -e 'apps/api[test]'
npm --prefix apps/web ci
```

Start PostgreSQL with its optional loopback port. If the full Compose stack is already running, stop its API/worker/web first so the native setup has one intended set of executors:

```sh
docker compose stop api worker web
docker compose -f compose.yaml -f compose.native.yaml up -d --wait db
```

The native override attaches PostgreSQL to the normal bridge for `127.0.0.1:5432` publishing. Alternatively use another local PostgreSQL database. These displayed database credentials are public development defaults, not production secrets.

In terminal 1, migrate, register all three examples, and start the API:

```sh
export DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj'
export PRAXIOJ_ENV=development
export PRAXIOJ_DEFAULT_PROFILE=mock
make migrate register
make api
```

In terminal 2, from the same repository root, start the separate worker with the same database and provider configuration:

```sh
export DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj'
export PRAXIOJ_ENV=development
export PRAXIOJ_DEFAULT_PROFILE=mock
make worker
```

In terminal 3:

```sh
make web
```

Open http://127.0.0.1:5173, register or sign in, and choose a problem. Vite proxies `/api` to the native API. The commands start one API and one worker; PostgreSQL claim/fence tests also exercise competing workers. The API's development reloader does not restart the worker, so restart `make worker` after changing worker code or configuration.

Native processes read exported environment variables, not an implicit `.env` file. Export settings separately in **both** API and worker terminals. Compose reads its optional root `.env` and supplies the shared runtime environment automatically. See [.env.example](../../.env.example); do not commit an actual `.env` or use `VITE_` variables for secrets. Keep native API/Vite bound to `127.0.0.1`; do not use public tunnels or expose this preview on a public interface.

Native role management uses the same database environment:

```sh
.venv/bin/python -m praxioj_api.cli set-role your_username author
```

See [authentication](authentication.md) for cookie/CSRF behavior, session expiry, rate limits, and legacy identity quarantine. `PRAXIOJ_COOKIE_SECURE=false` supports the documented localhost HTTP flow; HTTPS development can set it to true. This flag does not install TLS or make a public deployment supported.

`make api` and the container startup script pass `--no-proxy-headers` to Uvicorn. Do not silently re-enable forwarded client-address trust. The local reverse proxy shares one transport-IP quota among its clients. A public trusted-proxy configuration is not provided. Uvicorn default access logs and nginx access logs are disabled; the API emits JSON request categories, methods, status and elapsed time without raw paths, query strings, IPs or bodies. Do not put credentials in URLs or enable verbose third-party HTTP/SQL diagnostics.

Native API/worker database connections use a five-second connection/pool/row-lock wait, ten-second statement deadline and fifteen-second idle-transaction deadline. Caller `search_path` options are preserved. These bounds can reject a long operation or contended transaction with a safe error; they are not a hard real-time guarantee for an entire shutdown. Operator migrations and backup procedures have separate execution budgets.

## Operations and private data

Account and data offers own-session revocation, password changes, allowance views and confirmation-protected export/deletion. Export pages are bounded and expired traces are omitted. Password changes sign out every login. Administrators can inspect the Operations view after explicit role assignment. See [quota policy](../architecture/resource-quotas.md), [worker operations](../architecture/persistent-jobs.md), [data governance](data-governance.md), and [backup/restore](backup-restore.md).

Run an independent bounded maintenance batch even when all workers are stopped:

```sh
make maintenance
# Or with the Compose API container running:
docker compose exec api python -m praxioj_api.maintenance
```

The command reconciles expired leases and cleans eligible traces, expired/revoked login records, old rate/quota buckets and stale worker records. Rerunning is safe after interruption. Scheduling it when no worker is available remains an operator responsibility. Restored databases are quarantined; the API, worker and supported operational entry points must not promote them to a serving environment.

## Validation

With the Python dependencies installed:

```sh
.venv/bin/python -m pytest
npm --prefix apps/web test -- --run
npm --prefix apps/web run build
.venv/bin/python -m pip check
.venv/bin/python scripts/sync-licenses.py --check
```

The default suite uses isolated SQLite test storage where applicable. PostgreSQL-only concurrency/process cases explicitly skip without a database URL; the opt-in live-provider test also skips. Vitest uses controlled fetch responses. To run the complete Python suite, including PostgreSQL migrations, row locks, separate worker processes, and local HTTP fixture cases:

```sh
PRAXIOJ_RUN_LIVE_TESTS=0 \
PRAXIOJ_TEST_DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj' \
PRAXIOJ_TEST_BACKUP_CONTAINER=praxioj-db-1 \
.venv/bin/python -m pytest
```

Each API test creates a unique temporary schema, migrates it, and drops it afterward. The backup test additionally creates and removes its own randomly named synthetic source/restore databases; the test role needs database-creation and backup inspection privileges. `PRAXIOJ_TEST_BACKUP_CONTAINER` selects matching PostgreSQL 18 tools in that local container. Without the explicit container/native-tool setup the real backup case skips. Normal application tables and the existing volume are not truncated. Use a disposable local database, never a production connection. SQLite does not establish PostgreSQL locking guarantees.

Against the running API **and worker**, run the actual HTTP flows:

```sh
python3 scripts/smoke.py
python3 scripts/smoke-m2.py
python3 scripts/smoke-m3.py
python3 scripts/smoke-m3.py --base-url http://127.0.0.1:5173
python3 scripts/smoke-m4.py --base-url http://127.0.0.1:5173
```

The M1–M3 scripts register synthetic accounts and leave their demonstration sessions/results in the local database. `smoke.py` preserves the foundation flow; `smoke-m2.py` checks tools, drafts, idempotency and ownership; `smoke-m3.py` uses the six-criterion `evidence-plan` rubric and verifies Trace integrity. `smoke-m4.py` adds account budgets, confirmation/export, session revocation, password rotation and erasure of only its newly created synthetic account. The web-proxy variant includes nginx or Vite routing. A successful build alone does not verify this flow. M1–M3 reports remain historical records; current results belong in [M4 validation](validation-m4.md).

## Troubleshooting

- **Cannot connect to Docker:** start the engine and confirm `docker info` succeeds. Compose configuration validation does not start containers.
- **Database unavailable:** inspect service health and `DATABASE_URL`; `db` is a container hostname, while native processes use `127.0.0.1`.
- **Run remains queued:** ensure the worker is running against the same database and migrated schema. API health does not imply worker availability.
- **Run failed after a worker crash:** lease recovery records a terminal failure without automatically replaying an uncertain provider request. Inspect the safe job error; an explicit new attempt consumes a new allowance.
- **Login expired or role changed:** sign in again. Authentication restores access to the same account's stored sessions; old M2 browser cookies do not become accounts.
- **401/403 from an API client:** authenticate with an allowed Origin, preserve cookies, and send the returned `X-CSRF-Token` on authenticated writes. The UI handles this protocol.
- **429 while authenticating:** wait for the fixed throttle window. Forwarded IP headers do not bypass it.
- **Trace expired:** evaluation results remain available with expired evidence references; the worker performs physical cleanup. See [retention](../architecture/trace-retention.md).
- **Version registration conflict:** the existing ID/version has different canonical content. Increment the version instead of editing stored history.
- **Port or Origin mismatch:** use the documented loopback URLs. New ports require a deliberate server allowlist change.
- **A secret was entered:** treat local storage as containing it. Best-effort redaction does not recognize every secret or historical row. Rotate the credential with its provider and handle the affected data.

For the credential-free compatible-provider demonstration, continue with [AI Workspace setup](ai-workspace.md).
