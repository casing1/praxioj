# Milestone 1 validation record

Validated on **2026-11-09 (Asia/Seoul)** in the supplied macOS ARM64 workspace. The repository was initially empty. No Git commit, push, or public deployment was performed.

## Results

| Check | Observed result |
| --- | --- |
| Final Framework + API pytest suite with PostgreSQL | **58 passed**: 30 Framework tests and 28 API/database tests; no skipped tests |
| API suite using isolated SQLite test databases | **26 passed**, 2 PostgreSQL-specific concurrency tests intentionally skipped |
| Frontend Vitest | **6 passed** |
| TypeScript check and Vite production build | Passed on the host and in the web image |
| Python dependency consistency | `pip check` passed |
| Independent Framework installation | Installed into a separate temporary virtual environment containing no FastAPI or SQLAlchemy; standalone example produced 100/100 |
| Docker Compose | Actual image builds and startup passed; PostgreSQL, API, and web all became healthy |
| Real PostgreSQL migration | Applied `0001_initial` and registered the sample with the CLI; test suite also exercised downgrade/upgrade and checked migration/ORM schema agreement |
| HTTP smoke, direct API | Passed: persisted conversation, submission, evaluation 100/100, 7 ordered events, and 3 ownership-denial checks |
| HTTP smoke, nginx web proxy | Same full flow passed through `http://127.0.0.1:5173`, including after final image replacement |
| Actual desktop Chrome UI | Problem library → detail → start session → send message → view mock reply → submit answer → completed evaluation with 100/100, all 3 criteria and 7 activity events |

Host runtimes: Python **3.13.5**, Node **24.11.0**, Docker Engine **29.4.3**. Actual built images used Python **3.13.18**, Node **24.22.2**, PostgreSQL **18.6**, and nginx **1.30.6**. See [version choices](versions.md) for exact tags and dependency pins.

## Commands and coverage

Install and host validation:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e packages/framework -e 'apps/api[test]'
.venv/bin/python -m pip check
npm --prefix apps/web ci
npm --prefix apps/web test -- --run
npm --prefix apps/web run build
```

The resolved Python dependencies were recorded in `requirements.lock`; subsequent clean installs and Docker builds were constrained by that file. The frontend lockfile was also exercised by `npm ci` inside Docker.

Real PostgreSQL validation used a dedicated local test database:

```sh
docker compose -f compose.yaml -f compose.native.yaml up -d --wait db
docker compose exec -T db createdb -U praxioj praxioj_test
TEST_DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj_test' .venv/bin/pytest -q
```

`createdb` is needed only once. Each test uses its own temporary schema. The suite checks manifest/version registration, historical session version pinning, browser ownership, public/private fields, bad requests, limits, provider and evaluator failures, trace ordering, immutable submissions, score/evidence serialization, OpenAPI, migrations, and database uniqueness. Real simultaneous requests verify row locking: two messages produce contiguous event positions, while two final submissions produce one success and one conflict.

Framework checks also cover bounded package loading, symlink/path rejection, duplicate JSON keys, deterministic mock replies and scores, redaction, trace deduplication, hash validation, frozen artifact/submission snapshots, unavailable execution methods, and forbidden Platform imports.

The six frontend tests use mocked HTTP, not a database. They exercise the complete participant journey, retries, rejection with draft preservation, rendering untrusted HTML as plain text, in-flight duplicate prevention, and missing browser ownership. The real HTTP and desktop Chrome checks above separately establish that the UI and live API connect correctly.

Actual full-stack commands:

```sh
docker compose build api web
docker compose up -d --wait
python3 scripts/smoke.py
python3 scripts/smoke.py --base-url http://127.0.0.1:5173
```

The initial in-app browser access host was unavailable. Native Chrome was used through the computer-use tool instead; the final result was visibly inspected. Desktop list and workspace layouts were also inspected. Mobile and cross-browser rendering were not tested.

## Issues found and resolved

- An internal-only Compose network prevented host port publishing in this Docker setup. The final configuration keeps PostgreSQL on the internal backend network, attaches API/web to a separate normal bridge, and adds the DB to that bridge only in the native-development override. The default setup exposes only API/web loopback ports.
- Pydantic assignment validation alone did not protect content/hash snapshots after a rejected mutation. `SubmissionData` and `Artifact` are now frozen; a regression test confirms failed assignment preserves both content and the evaluated score.
- Sensitive-key redaction originally matched token-usage counters. It now preserves `input_tokens`, `output_tokens`, and `max_output_tokens` while filtering credential fields.

One non-failing upstream warning remains: Starlette's TestClient deprecates its HTTPX transport and recommends `httpx2`. The pinned HTTPX transport passed the suite; migration can be handled with a focused dependency update. No warning was suppressed.

## Boundaries of this evidence

This validates the local Milestone 1 path, not production authentication, a security sandbox, arbitrary evaluator execution, commercial AI providers, distributed workers, load capacity, or complete replay of AI behavior. Those features are deliberately unavailable. Tests do not claim to evaluate actual human–AI collaboration quality; the sample rubric is a deterministic infrastructure fixture.

Test-created local sessions remain in the named PostgreSQL volume. Project containers are stopped after validation without removing that volume. Start them again with `docker compose up -d --wait` or rebuild with the README command.
