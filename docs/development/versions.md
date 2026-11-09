# Dependency and image versions

Version selection was checked on 2026-11-09. Direct package requirements use exact pins; `apps/web/package-lock.json` locks the JavaScript dependency graph. `requirements.lock` pins the resolved Python runtime/test dependency graph and is used as pip constraints during platform installs. The two Python project files pin their direct requirements.

The framework uses Pydantic and HTTPX as third-party runtime dependencies. HTTPX 0.28.1 moved from test-only availability into the Framework runtime dependencies for M2; its version was already pinned in the shared lockfile. FastAPI/SQLAlchemy/Alembic/psycopg stay in the Platform. React/Vite/TypeScript and Vitest serve the requested frontend/test stack. No commercial AI SDK, message broker, task queue, or sandbox dependency is required for M2.

| Component | Selected line/image | Reason |
| --- | --- | --- |
| Pydantic | `2.14.3` | Strict shared schema validation and serialization without a platform dependency. |
| FastAPI | `0.162.2` | Typed REST and OpenAPI from the requested Python stack. |
| SQLAlchemy / Alembic | `2.1.8` / `1.20.1` | Modern ORM transactions and explicit migrations. |
| psycopg / Uvicorn | `3.3.8` / `0.54.0` | PostgreSQL driver with binary wheel support and ASGI serving. |
| pytest / HTTPX | `9.2.0` / `0.28.1` | Python behavior/integration tests and FastAPI TestClient transport. |
| React / React DOM | `19.3.1` | Current stable React runtime, kept in sync. |
| Vite / React plugin | `8.3.6` / `6.3.0` | Current Vite build and development server with the React plugin. |
| TypeScript / Vitest | `7.0.2` / `5.1.0` | Strict UI typing and request/interaction tests. |
| Testing Library | React `16.3.3`, user-event `14.6.8`, DOM `10.4.2`, jest-dom `7.0.1` | Accessible role-based interaction assertions rather than implementation snapshots. |
| jsdom | `27.4.0` | Deliberately held to support the installed Node 24.11.0; the current jsdom 31 line requires Node 24.15 or newer. |
| Type declarations | React / React DOM `19.3.0`, Node `24.19.2` | Match the selected runtime families; erased at build time. |
| Python | `python:3.13.18-slim-bookworm` | Current patch on the Python 3.13 line, matching the local interpreter's major/minor and broad wheel availability. |
| Node | `node:24.22.2-bookworm-slim` | Patched Node 24 LTS, suitable for Vite and frontend builds. |
| PostgreSQL | `postgres:18.6-bookworm` | Current stable PostgreSQL 18 image, transactional relational storage with explicit migration support. |
| nginx | `nginx:1.30.6-alpine3.24` | Stable nginx image for static assets and same-origin `/api` proxying. |

These exact tags were found in the upstream Docker Official Images manifests for [Python](https://github.com/docker-library/official-images/blob/master/library/python), [Node](https://github.com/docker-library/official-images/blob/master/library/node), [PostgreSQL](https://github.com/docker-library/official-images/blob/master/library/postgres), and [nginx](https://github.com/docker-library/official-images/blob/master/library/nginx). PostgreSQL 18's image stores versioned cluster data under the parent volume at `/var/lib/postgresql`; see the [image documentation](https://github.com/docker-library/docs/blob/master/postgres/README.md).

The host's Python 3.13.5 and Node 24.11.0 may be used for the local validation run; report that separately from container-image validation. Exact tags prevent silent major/minor upgrades, but are not immutable content digests. Production release automation should resolve and review image digests and refresh patches regularly.

Use package-maintainer/registry releases as the source of version availability. Upgrade a focused set of pins, regenerate the lockfile, then run the framework/API tests, PostgreSQL migration and concurrency checks, frontend tests/build, and real full-stack smoke flow before accepting an update.
