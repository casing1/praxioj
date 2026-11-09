# Local setup

All commands run from the repository root unless stated otherwise. This milestone is localhost-only. Keep the same browser host (`127.0.0.1` or `localhost`) throughout a solve so its cookie is retained.

## Docker Compose

Use Docker with Compose v2 and a running engine:

```sh
docker compose config --quiet
docker compose up --build -d --wait
```

Open http://127.0.0.1:5173. OpenAPI documentation: http://127.0.0.1:8000/api/docs. API health: http://127.0.0.1:8000/api/health.

The API waits for PostgreSQL health, applies Alembic migrations, registers both samples idempotently, then starts FastAPI. Web waits for the API. Images are explicitly versioned. The API runs as an unprivileged container user. Only web and API loopback ports are published. PostgreSQL and API share an internal backend network; API and web share a normal bridge network that permits Docker port publishing. The default database is unpublished. API/web outbound network access is not restricted by this setup; it is not an execution sandbox.

```sh
docker compose ps
docker compose logs api
python3 scripts/smoke.py
docker compose down
```

`down` preserves the database volume. Do not remove the volume unless you intend to delete all local sessions and submissions. A normal rebuild must not overwrite an existing problem version with modified content; bump its version instead.

## Native Python and Vite with PostgreSQL

Use Python 3.13 and Node 24 LTS. The frontend package also accepts Node 22.12+ on the 22.x line or Node 26+; Node 24.11.0 is the available local validation runtime. Install dependencies:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -c requirements.lock -e packages/framework -e 'apps/api[test]'
npm --prefix apps/web ci
```

Start only PostgreSQL with its optional loopback port (the override also attaches it to the normal bridge network so Docker can publish that port):

```sh
docker compose -f compose.yaml -f compose.native.yaml up -d --wait db
```

Alternatively, create a local PostgreSQL database and set its SQLAlchemy URL. The API uses environment variables, not implicit `.env` loading:

```sh
export DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj'
export PRAXIOJ_ENV=development
alembic -c apps/api/alembic.ini upgrade head
python -m praxioj_api.cli register examples/problems/release-plan
python -m praxioj_api.cli register examples/problems/workspace-plan
uvicorn praxioj_api.main:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal:

```sh
npm --prefix apps/web run dev -- --host 127.0.0.1
```

Vite proxies `/api` to the local API. No provider API key is needed. Do not set `--host 0.0.0.0` for native development or expose this service using a public tunnel.

## Validation

```sh
. .venv/bin/activate
python -m pytest
npm --prefix apps/web test -- --run
npm --prefix apps/web run build
python scripts/smoke.py
python scripts/smoke-m2.py
```

Framework/API unit tests use isolated test storage and run without a live AI provider. Vitest uses mocked fetch to check UI behavior. The smoke script uses actual HTTP, browser-style cookies, persisted sessions, chat, final submission, evaluation, and access checks against the running stack. It creates a new local sample session each run. Its default API endpoint is `http://127.0.0.1:8000`; use `--base-url http://127.0.0.1:5173` to also exercise the web proxy.

Run the same API/migration suite against PostgreSQL after starting the optional native database port:

```sh
PRAXIOJ_TEST_DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj' python -m pytest tests/api
```

The test fixture creates a uniquely named temporary schema per test, applies the real migration in it, and drops that schema afterward; the configured PostgreSQL user therefore needs schema-creation privileges. It does not truncate normal application tables. Use a disposable local database, not a production connection.

Migrations must be exercised against PostgreSQL as well as any SQLite test path. See [M2 validation record](validation-m2.md) and historical [M1 validation](validation.md) for the commands actually executed in this environment and their limitations. A SQLite pass does not establish PostgreSQL row-lock behavior; a web build does not establish a successful browser flow.

## Troubleshooting

- **Cannot connect to the Docker daemon:** start Docker Desktop/engine and wait for `docker info` to succeed. A Compose file validation does not start containers.
- **API cannot reach the database:** check `docker compose ps`, database health, and `DATABASE_URL`; `db` is a container hostname, while native Python uses `127.0.0.1`.
- **Port already in use:** stop the conflicting local process. The supported demo origins are explicit, so changing web ports also requires an intentional allowlist update.
- **Session not found after changing browsers/hosts:** local identities are cookie-scoped. Reopen the original host/profile or start a new session.
- **Registration conflict:** the same ID/version already exists with different canonical content. Choose a new version; do not mutate historical records.
- **Foreign Origin or Host rejected:** use the documented localhost URLs and same-origin proxy. This is a development boundary, not a deployment configuration option.
- **A secret was entered:** treat the database as containing that secret. Recognized tokens and the configured provider key are scrubbed before new conversation/draft/submission writes, but arbitrary text and historical rows can still contain unrecognized secrets. Rotate the exposed secret through its provider and handle the local data accordingly.

## AI Workspace and compatible providers

See [AI Workspace setup](ai-workspace.md) for capability flags, server-only provider configuration, cancellation/retry semantics, missing usage, and a loopback HTTP fixture that needs no credentials. The default remains Mock. Use a single API process; multiple Uvicorn workers are unsupported.
