# Milestone 3 implementation and validation

Validated on **2026-11-10**, after [Preflight PR #11](https://github.com/casing1/praxioj/pull/11) merged as `4ad6e02afecf05138d8d0446a7faff2a67be4212`. Implementation is reviewed in [Milestone 3 PR #12](https://github.com/casing1/praxioj/pull/12), from `feat/milestone-3-secure-foundation`. GitHub delivery and current security-alert status are reported separately from these reproducible local results; source publication is not a production deployment.

## Implemented behavior

| Area | Implementation and principal files |
| --- | --- |
| Accounts and roles | `auth.py`, `security.py`, `auth_routes.py`, `cli.py`: Argon2id, random hashed server sessions, fixed expiry, logout/revocation, CSRF/Origin, DB login rate limits, participant registration, operator role assignment, author-owned immutable problem publishing |
| Durable execution | `job_models.py`, `jobs.py`, `worker.py`, `runs.py`: API enqueue transaction, separate worker, PostgreSQL claims/leases/heartbeat/fencing, persistent cancellation, bounded execution, explicit failure after crash without replay |
| Trace lifecycle | `services.py`, `retention.py`, `retention_models.py`, `review_routes.py`: append-oriented hash chains, checkpoint validation under session locks, expiry, bounded cleanup batches, reviewer projections, minimal audit and account data erasure |
| Framework assessment | Framework `problems`, `tracing`, `evaluation`: schema 1.2 author criteria, versioned deterministic evidence rubric, artifact/trace/tool/usage evidence, unsupported outcomes for unknown/estimated token evidence, legacy compatibility |
| UI | `auth.tsx`, `App.tsx`, `AuthorTools.tsx`, Workspace/Evaluation: registration/login/logout/expiry, role gating, author publishing, persisted Job state/uncertainty, restored work, criterion versions and trace integrity/expiry |
| Integration | Compose worker, `make worker`, three registered samples, authenticated smoke scripts, and CI Compose build plus real HTTP M3 smoke |

Framework never imports Platform authentication or SQL models. Built-in evaluation remains synchronous; the separate worker runs trusted AI/runtime/tools. No arbitrary Python, shell, untrusted container, browser automation tool or isolated Judge was added.

## Schema and migration decisions

- **0003_authentication:** nullable username/password fields and inactive-by-default legacy users; author ownership; AuthSession hash/expiry/revocation; shared AuthRateLimit buckets. Old browser tokens are not login credentials and cannot be promoted through the role CLI.
- **0004_jobs:** Job states, owner token, monotonic fence, availability, heartbeat/lease/deadline, attempt and uncertainty metadata. Existing unfinished M2 runs are failed/quarantined with explicit trace events; their external requests are not replayed.
- **0005_trace:** trace head checkpoint, per-session retention days/expiry/purge marker, and separate AuditRecord. Existing unhashed evidence is retained as unverified, never retroactively claimed to be original tamper-resistant evidence.

A request UUID plus session uniqueness gives enqueue idempotency. Session→run→job row locks and fresh token/fence/lease checks prevent stale workers from writing results or clearing a newer run. PostgreSQL supplies the shared lease clock. A lost remote response may still represent a billed/processed request, so expired jobs fail with uncertainty instead of automatically retrying.

Retention defaults to 30 days with a hard configurable ceiling of 90. Authors can shorten/request policy within that bound for new sessions. Expired trace reads and new work fail before physical cleanup. Workers periodically purge bounded batches; maintenance CLI is also available. Evaluations survive trace expiry but report unavailable references. Authenticated account erasure removes private solve data and revokes sessions; an inactive pseudonymous user tombstone preserves immutable public problem ownership. Audit metadata is separately bounded to at most 90 days. See [retention details](../architecture/trace-retention.md).

## Executed validation

| Check | Actual result |
| --- | --- |
| Full PostgreSQL-backed Python suite | **247 passed, 1 skipped** in 58.09 seconds |
| Default SQLite/offline suite | **238 passed, 10 skipped** in 37.97 seconds |
| Original PostgreSQL row-lock tests | Both passed; included in the full PostgreSQL run |
| PostgreSQL-only coverage | Nine cases passed: original two, shared authentication limit, worker races/heartbeat, process fixture integration, process crash recovery and concurrent recovery visibility |
| Framework | **100 passed**, including 41 added M3 tests; original M1/M2 canonical manifest digests preserved |
| Auth-specific PostgreSQL tests | **12 passed** |
| Queue-specific PostgreSQL tests | **19 passed** |
| Trace retention/reviewer/account erasure tests | **6 passed** in the full PostgreSQL and default suites |
| Frontend | **24 passed**, retaining the previous 18 participant/workspace scenarios |
| TypeScript and Vite | Passed |
| Dependency consistency / license copies | `pip check` and `scripts/sync-licenses.py --check` passed |
| Compose / containers | Configuration valid; API/web/worker images built; actual local PostgreSQL migrated; API/web/db healthy and separate worker running |
| Real HTTP M1 smoke | 100/100, seven legacy-flow events, three cross-account access checks |
| Real HTTP M2 through nginx | 100/100, two model attempts, one tool, 19 events, four cross-account checks |
| Real HTTP M3 through nginx | 100/100 across six evidence criteria, completed Job and verified hash chain, four cross-account checks |
| Native Chrome UI against running stack | Register → select evidence-plan → Mock tool request/result → file/draft save → reload restores conversation/draft → submit → six criteria met, 100/100 and Trace verified |
| Local OpenAI-compatible HTTP fixture with real worker process | Two provider requests with tool result/context, persisted file, submission and 100/100; no commercial endpoint |

The default suite skips the nine PostgreSQL-only cases plus one explicitly opt-in live Provider case. The PostgreSQL suite skips only that live Provider case. No real API key was created or paid/external LLM request made.

Worker failure tests start actual independent Python worker processes. Two processes competing for one job produce one successful claim. A worker killed during a slow local HTTP request is recovered after lease expiry by another worker; the fixture observes no automatic second request and usage remains unknown. Long calls retain ownership through heartbeats. Cancellation and old-worker completion cannot mutate a newer run. PostgreSQL migration tests include populated historical records and ORM/schema agreement.

Security boundaries exercised include password hashing/verification, rotation/expiry/logout, Secure cookies on HTTPS loopback, missing/forged CSRF, foreign/missing authentication Origin, role escalation rejection, problem ownership, session/run/file/trace/evaluation IDOR, legacy token quarantine, tool input/path/permission restrictions, redaction, resource budgets, event tampering/suffix deletion, expired reads/writes, reviewer projection, account erasure and audit expiry. A final-submission-only event cannot earn the example's workspace-history points.

The recorded runs emitted a Starlette TestClient deprecation warning for HTTPX. SQLite also emitted Python's legacy datetime-adapter warning. They did not fail tests. Native Windows behavior, long-duration production loads and actual commercial model inference remain unverified.

The first PR CI run passed Frontend, Compose E2E and both CodeQL language jobs, but exposed a race in the persistence-failure regression test: its log assertion ran before the background worker finished reconciliation. A second recovery correctly skipped the worker-locked row, and the test read before that transaction committed. The test now waits for an explicitly controlled worker iteration to complete before forcing lease expiry. Its sensitive-log and recovery assertions remain intact; production behavior and required checks were not weakened. Final-head CI results are recorded on PR #12.

The latest preflight alert read confirms all four original setuptools alerts fixed, with no dismissal or suppression. See [the alert report](preflight-validation.md#alert-reconciliation-follow-up) for remediation, timestamps and the earlier dependency-graph reconciliation delay.

## Reproduce

```sh
PRAXIOJ_RUN_LIVE_TESTS=0 PRAXIOJ_TEST_DATABASE_URL=postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj .venv/bin/python -m pytest -q
PRAXIOJ_RUN_LIVE_TESTS=0 PRAXIOJ_TEST_DATABASE_URL= TEST_DATABASE_URL= .venv/bin/python -m pytest -q
npm --prefix apps/web test
npm --prefix apps/web run build
.venv/bin/python -m pip check
.venv/bin/python scripts/sync-licenses.py --check
docker compose up --build -d --wait
python3 scripts/smoke.py
python3 scripts/smoke-m2.py --base-url http://127.0.0.1:5173
python3 scripts/smoke-m3.py --base-url http://127.0.0.1:5173
```

The database credentials above are published local-development defaults. Tests create and drop unique schemas; use a disposable local database. Smoke checks create synthetic local accounts and sessions. Native worker/fixture instructions are in [local setup](local-setup.md) and [AI Workspace](ai-workspace.md).

## Remaining limitations and next work

This is a local development foundation, not a production security certification. No MFA/recovery, public identity verification, full abuse/global quotas, storage encryption/secret vault, backup deletion/export, externally anchored evidence or untrusted-code sandbox is provided. Physical cleanup and lease reconciliation pause if every worker stops. The trusted worker does not provide an exactly-once guarantee for external requests or a distributed Judge. Logical tools do not isolate arbitrary code. Test fixture counts are synthetic, and Mock estimates are not provider billing.

[Milestone 4 priorities](roadmap.md) cover deployment review, worker operations, data governance, provider conformance and a separately designed isolated execution boundary. Apache-2.0, project independence and contributor/third-party copyright remain unchanged.
