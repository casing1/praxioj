# Dependency and image versions

The original runtime/image baseline was checked on 2026-11-09; the GitHub preflight build-tool fix and M3 authentication dependencies were reviewed on 2026-11-10. This is a record of selected versions, not a promise that they remain the latest releases. Direct package requirements use exact pins; `apps/web/package-lock.json` locks the JavaScript dependency graph. `requirements.lock` pins the resolved Python runtime/test dependency graph and is used as pip constraints during platform installs. The two Python project files pin their direct requirements.

The framework uses Pydantic and HTTPX as third-party runtime dependencies. HTTPX 0.28.1 moved from test-only availability into the Framework runtime dependencies for M2; its version was already pinned in the shared lockfile. FastAPI/SQLAlchemy/Alembic/psycopg and the new Argon2 password-hashing dependency stay in the Platform. React/Vite/TypeScript and Vitest serve the requested frontend/test stack. M3 implements its persistent job repository and worker lifecycle using the existing SQLAlchemy/PostgreSQL stack. It adds no Redis, RabbitMQ, Celery, commercial AI SDK, or sandbox dependency. Framework imports remain independent of Platform authentication and persistence.

| Component | Selected line/image | Reason |
| --- | --- | --- |
| Pydantic | `2.14.3` | Strict shared schema validation and serialization without a platform dependency. |
| FastAPI | `0.162.2` | Typed REST and OpenAPI from the requested Python stack. |
| SQLAlchemy / Alembic | `2.1.8` / `1.20.1` | Modern ORM transactions and explicit migrations. |
| psycopg / Uvicorn | `3.3.8` / `0.54.0` | PostgreSQL driver with binary wheel support and ASGI serving. |
| setuptools | `84.2.1` | Both PEP 517 build backends and the shared test/constraint environment use the patched version; preflight regressions cover the two reported packaging advisories. |
| argon2-cffi / bindings | `25.1.0` / `26.1.0` | Maintained Argon2id password hashing for Platform accounts, with explicit RFC 9106 low-memory parameters. Both distributions declare MIT. |
| CFFI / pycparser | `2.1.1` / `3.12` | Pinned Argon2 binding dependencies; MIT-0 and BSD-3-Clause respectively. Their license files remain with the installed packages. |
| pytest / HTTPX | `9.2.0` / `0.28.1` | Python behavior/integration tests and FastAPI TestClient transport. |
| React / React DOM | `19.3.1` | Selected React 19 runtime baseline, with React DOM kept in sync. |
| Vite / React plugin | `8.3.6` / `6.3.0` | Selected Vite build and development server baseline with the React plugin. |
| TypeScript / Vitest | `7.0.2` / `5.1.0` | Strict UI typing and request/interaction tests. |
| Testing Library | React `16.3.3`, user-event `14.6.8`, DOM `10.4.2`, jest-dom `7.0.1` | Accessible role-based interaction assertions rather than implementation snapshots. |
| jsdom | `27.4.0` | Deliberately held to support the installed Node 24.11.0; the current jsdom 31 line requires Node 24.15 or newer. |
| Type declarations | React / React DOM `19.3.0`, Node `24.19.2` | Match the selected runtime families; erased at build time. |
| Python | `python:3.13.18-slim-bookworm` | Selected Python 3.13 image patch, matching the host interpreter's major/minor and available binary dependencies. |
| Node | `node:24.22.2-bookworm-slim` | Patched Node 24 LTS, suitable for Vite and frontend builds. |
| PostgreSQL | `postgres:18.6-bookworm` | Selected PostgreSQL 18 image, providing transactional storage, row-lock queue claims and explicit migrations. |
| nginx | `nginx:1.30.6-alpine3.24` | Selected nginx image for static assets and same-origin `/api` proxying. |

These exact tags were found in the upstream Docker Official Images manifests for [Python](https://github.com/docker-library/official-images/blob/master/library/python), [Node](https://github.com/docker-library/official-images/blob/master/library/node), [PostgreSQL](https://github.com/docker-library/official-images/blob/master/library/postgres), and [nginx](https://github.com/docker-library/official-images/blob/master/library/nginx). PostgreSQL 18's image stores versioned cluster data under the parent volume at `/var/lib/postgresql`; see the [image documentation](https://github.com/docker-library/docs/blob/master/postgres/README.md).

The host's Python 3.13.5 and Node 24.11.0 may be used for the local validation run; report that separately from container-image validation. Exact tags prevent silent major/minor upgrades, but are not immutable content digests. Production release automation should resolve and review image digests and refresh patches regularly.

M3 Argon2 versions and license expressions were checked against the official [argon2-cffi](https://pypi.org/project/argon2-cffi/25.1.0/), [bindings](https://pypi.org/project/argon2-cffi-bindings/26.1.0/), [CFFI](https://pypi.org/project/cffi/2.1.1/), and [pycparser](https://pypi.org/project/pycparser/3.12/) distributions. These libraries retain their own licenses and are not relicensed as Apache-2.0. See [authentication](authentication.md), [licensing](licensing.md), and the [preflight report](preflight-validation.md) for the corresponding boundaries and review evidence.

Use package-maintainer/registry releases as the source of version availability. Upgrade a focused set of pins, regenerate the lockfile, then run the framework/API tests, PostgreSQL migration, authentication, worker concurrency/crash checks, frontend tests/build, and actual HTTP smoke flows before accepting an update.
