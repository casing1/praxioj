# Milestone 2 implementation and validation

Validated on **2026-11-09 (Asia/Seoul)** in the supplied macOS ARM64 workspace. No real API key was created or requested, no paid/external model API was called, and no Git commit, push, or public deployment was performed. Hosted package registries were used to rebuild the existing pinned dependencies; that is separate from model-provider testing.

## Implementation and M1 compatibility

The existing Framework/Platform boundary, Problem SDK, Mock Provider, Trace envelope, deterministic Judge Engine, ownership checks, and participant routes were inspected against the M1 design. M2 extends them without replacing the application. The legacy synchronous Mock route keeps its seven-event solve flow. New UI uses asynchronous runs so provider network waits do not hold database locks.

Implemented components:

- Provider-neutral Chat Completions adapter with server-only endpoint/key/model configuration, explicit capabilities, nullable reported usage, bounded JSON, deadlines, cancellation, safe errors, and local endpoint support.
- Persistent conversations, profile snapshots, asynchronous run state, idempotent request UUIDs, explicit draft save, cancellation/recovery, session closure, artifact snapshots, and existing final evaluation.
- Trusted logical read/write tools with strict input/output schemas, registry, separate authorization, permissions, traversal prevention, session scope, and file/count/aggregate quotas.
- Ordered correlated provider/tool/artifact/error/state events, separate safe internal diagnostics, known-secret scrubbing, model/tool attempt accounting, and explicitly configured cost estimates.
- UI provider selection, busy/cancel/retry handling, tools/results, files, usage, saved drafts, trace inspection, and unchanged result workflow.

The original `release-plan/1.0.0` manifest remains unchanged with SHA-256 `0c5425eba5f6b5a79c67d5471d80a341497bce7555c2820f59f7985fc4e2e32c`. Re-registration succeeds against the existing database. `workspace-plan/1.0.0` is an additional schema-1.1 demonstration. M2 schema defaults do not invalidate old schema-1.0 digests; non-default policy changes still affect identity.

Migration `0002_workspace` preserves M1 rows and reconstructs successful historical provider attempts from assistant messages and available trace usage. Unknown historical usage remains NULL. M1 failed attempts did not have complete call records and cannot be reconstructed. The migration does not invent their counts or retroactively redact historical data. Downgrade removes M2 data and is intended only for disposable test databases; back up data before any operational downgrade.

## Verification results

| Check | Observed result |
| --- | --- |
| Complete Python suite with PostgreSQL | **161 passed, 1 skipped**; skip is the opt-in live provider test |
| PostgreSQL API cases within that suite | **49 passed**, including both original PostgreSQL concurrency tests |
| Final API SQLite/local HTTP run | **47 passed**, 2 PostgreSQL-only cases skipped |
| Frontend Vitest | **18 passed** (original 6 + 12 M2 cases) |
| TypeScript and Vite production build | Passed on host and in Docker |
| Docker build and startup | API/web built; database/API/web healthy |
| Final nginx-proxy smoke | M1 and M2 Mock both passed: 100/100, 7/19 ordered events, 3/4 ownership checks |
| License copies / dependency consistency / Compose syntax | All passed |

The final PostgreSQL run includes 59 Framework and 53 offline Provider cases, plus 49 API/database cases. A non-failing Starlette TestClient deprecation warning recommends a future `httpx2` migration; the pinned transport passed. SQLite populated-migration checks additionally report upstream datetime-adapter deprecation warnings. No warning was suppressed.

The original **56 ordinary Python regression cases** remain in the suite. The two PostgreSQL-only concurrency cases were run using a local PostgreSQL 18.6 database, not treated as validated by SQLite. Frontend tests retain the original six behaviors and add twelve M2 cases.

Commands used:

```sh
PRAXIOJ_RUN_LIVE_TESTS=0 .venv/bin/python -m pytest
PRAXIOJ_TEST_DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj_test' .venv/bin/pytest tests/api -q
npm --prefix apps/web test -- --run
npm --prefix apps/web run build
python3 scripts/sync-licenses.py --check
.venv/bin/python -m pip check
docker compose config --quiet
```

Host runtimes were Python 3.13.5, Node 24.11.0, and Docker 29.4.3. Images used Python 3.13.18, Node 24.22.2, PostgreSQL 18.6, and nginx 1.30.6.

API tests use unique temporary schemas and real migrations; normal development tables are not truncated. PostgreSQL tests cover ownership, locking, uniqueness, populated M1 upgrade, ORM/migration agreement, and new run/tool accounting. Provider tests use HTTPX transports and actual loopback HTTP servers for request serialization, complete role-preserving context, tool calls/results, missing/partial usage, malformed/error responses, deadline and cancellation behavior, size bounds, and safe redaction. Opt-in `live_provider` is explicitly disabled for this work.

Frontend tests use mocked fetch and cover the full interaction, profile selection, tool/draft/result flow, uncertain request UUID reuse, restored failures, cancellation, incomplete usage, cost estimates, ownership loss, cross-tab conflicts, and polling versus unsaved-draft races. They are complemented by the running-stack checks below.

## Actual HTTP and browser integration

A native FastAPI server used PostgreSQL and `scripts/compatible-fixture.py` at loopback port 18081. This fixture is deterministic test data, not a local LLM. Its token counts are synthetic; fixture results do not establish real provider billing or model quality.

Through the actual Vite proxy at `http://127.0.0.1:5173`:

- Original `scripts/smoke.py`: passed, evaluation 100/100, seven ordered events, three cross-identity denial checks.
- `scripts/smoke-m2.py` with Mock: passed, two model calls, one file tool, nineteen events, evaluation 100/100, four cross-identity denial checks.
- The same M2 smoke with `--profile compatible`: passed through the local HTTP adapter, including request retry without duplicate file revision, saved draft/history, tool result, usage, submission and trace.

Actual desktop Chrome, driven through computer-use UI, completed: problem library → workspace sample → compatible fixture profile → session → message → tool authorization/result → `plan.txt` → load/save draft → browser refresh preserving conversation/draft → submit → completed 100/100 result and nineteen ordered events. Tool authorization details and correlated IDs were visibly inspected. This was a real frontend/backend/database connection, not mocked browser fetch. Mobile and cross-browser layouts were not tested.

Docker images were rebuilt from the pinned dependencies and all three services became healthy. Both final nginx-proxy smoke scripts passed on the rebuilt image: the M1 flow retained seven events; the M2 flow recorded two model calls, one tool call, nineteen events, and 100/100. Containers and locally started test servers are stopped after verification; database volumes and demonstration sessions are retained.

## Issues found and resolved

- Added schema defaults could change old manifest identity: compatibility digest handling preserves the original package hash.
- Historical M1 usage would otherwise appear as zero after upgrade: migration backfills known successful attempts and preserves unknown usage.
- Interrupted or quota-blocked pending tools need matching history and evidence: explicit denial/result events now accompany synthesized terminal tool messages without exceeding admitted-call counters.
- Persistence failures in a background task could expose SQL exception content through asyncio diagnostics: callbacks consume exceptions and log only safe operation/error identifiers.
- Returning from evaluation could show a stale draft: final submission persists the submitted answer, and polling avoids overwriting unsaved edits.
- Compatible providers may reuse a tool-call ID in a later completed turn: deduplication is scoped to a run, while correlation still rejects unresolved/malformed or duplicate calls within that run.
- A legal maximum-size logical file needs room for the serialized tool-result envelope: tool-message bounds account for the envelope while total provider request limits remain enforced.

## Publication, licensing, and verification limits

Apache-2.0, `Copyright 2026 DoHyun Choi`, contributor ownership, and third-party notices remain intact. Canonical notice copies match. `.gitignore` and `.dockerignore` exclude local environment files, databases, logs/caches and build artifacts; nested environment files are also excluded from image context. A source-pattern scan reported no long OpenAI-key, AWS access-key, or private-key-header candidates in the inspected source files, without printing secret values. This is a targeted check, not proof that arbitrary sensitive text cannot exist. The supplied directory has no `.git` repository, so there is no local Git history to inspect; no repository was initialized.

Not verified: actual OpenAI/other hosted providers, real local model inference, real usage/billing accuracy, production load, multi-process workers, public authentication, secure untrusted execution, complete PII detection, external evaluator execution, or deterministic replay of real model behavior. The live-provider test deliberately skips without opt-in settings/credentials. The built-in Judge still grades final text and does not claim to measure collaboration quality.

The service remains **localhost development only**. Browser capability cookies are not production accounts. Files are logically isolated DB text, not an OS sandbox. A synchronous DB/tool operation already in progress cannot be forcibly preempted by the run deadline. Observed-token budgets can overshoot by one response, and failed/cancelled provider calls can have unknown usage. Only one API process is supported; there is no distributed task ownership, global abuse protection, secret vault, or retention scheduler. The adapter is non-streaming, accepts bounded uncompressed JSON, and uses explicit capability settings rather than promising every compatible model works.

Recommended M3 work is real authentication/authorization and global quotas, durable worker ownership/cancellation, trace retention and evidence-based process evaluation, opt-in provider conformance, and an independently validated execution-isolation design before enabling untrusted code. See [roadmap](roadmap.md), [security boundaries](../../SECURITY.md), and [setup](ai-workspace.md).
