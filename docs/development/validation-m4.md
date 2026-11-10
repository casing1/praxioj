# Milestone 4 implementation and validation

Recorded on 2026-11-10. M4 strengthens the existing localhost development preview; it does not authorize public deployment or enable untrusted code. The GitHub delivery record at the end distinguishes local results from remote checks.

## Preflight and baseline

Starting main: `733f4928aa368aea627aab7442fe27109ce0b7b4`, the engineering-workflow change after M3. The clean local checkout was fast-forwarded; no user changes or database volume were discarded. GitHub had no open PRs, Dependabot alerts, code-scanning alerts or secret-scanning alerts. Main CI and CodeQL were successful. Protect main remains active with five strict required checks and no bypass actors.

The baseline was directly rerun before implementation on macOS/Apple Silicon, Python 3.13.5, Node 24.11.0 and Docker PostgreSQL 18.6:

| Check | M3 baseline | Final M4 local result |
| --- | --- | --- |
| PostgreSQL Python | 247 passed, 1 live-provider skip; 46.98 s | **298 passed, 1 live-provider skip; 91.04 s** |
| Default SQLite Python | Historical M3: 238 passed, 10 skipped; not separately rerun before editing | **281 passed, 18 skipped; 55.30 s** |
| Frontend | 24 passed; 3.22 s | **31 passed; 3.43 s** |
| TypeScript/Vite | Passed; JS 262.96 kB / gzip 80.43 kB | **Passed; JS 273.87 kB / gzip 82.74 kB** |
| CSS | 30.85 kB / gzip 7.36 kB | 31.23 kB / gzip 7.45 kB |

Final Python suites ran concurrently, and M4 adds 51 cases; total suite times are not a comparable performance benchmark. SQL tests use disposable schemas; backup tests additionally create/drop only their own UUID-named synthetic databases. The named application volume is preserved. Docker builds used Python 3.13.18, Node 24.22.2 and PostgreSQL 18.6. Native Windows is not validated.

## Implementation and compatibility

- **Authentication:** fresh login cookies, fixed expiry, bounded multi-session listing/revocation, per-login recent password confirmation and password changes that revoke every login. Registration intentionally changes to generic **202 followed by explicit login**, eliminating duplicate-registration response disclosure. Existing clients/tests/smokes were updated. Argon2id parameters remain 64 MiB/t3/p4. Atomic database IP/account throttle buckets and a separate API transport-IP limit work across processes; untrusted forwarded headers are ignored. No recovery-email or MFA shortcut was added.
- **Resource policy:** account/problem/system daily call/tool budgets, conservative provider reservations, active/retained session limits, account concurrency, global queue/running limits, logical artifact and Trace capacity. Unavailable, partial or estimated provider usage retains reservation units; these are not exact tokens or billing. Calls are not refunded on uncertain cancellation. Ownership and quota enforcement occur on server paths, including the legacy synchronous Mock route.
- **Worker operations:** lifecycle/heartbeat records, bounded graceful drain, persistent cancellation/fencing, pending/lease cleanup, account admission caps, FIFO among eligible unlocked jobs, queue backpressure and role-protected metrics. A standalone maintenance command works with every AI worker stopped. Exactly-once remote execution and strict starvation freedom are not promised.
- **Data governance:** owner-only paged JSON export after recent confirmation, bounded byte/row limits, expired-Trace omission, transactional table-wise erasure with reference tombstones and credential revocation. Private evaluator configuration and authentication secrets are excluded. Active runs must finish/cancel before erasure. Published authored problems retain their pseudonymous ownership reference.
- **Backup:** trusted local PostgreSQL CLI with private external files, standard custom-format dumps, bounded checksum/archive validation and pruning, native/container cluster identity checks, generated restore DBs, schema validation and restored-session revocation. A marker blocks serving/executing restored data. Archives are unencrypted; independently managed encrypted storage is required for sensitive data. Automatic promotion, off-site deletion-ledger replication and production recovery orchestration are absent.
- **Frontend:** account/session controls, confirmation-protected downloads and erasure, allowance reporting, retry-window guidance and administrator operations. Existing problem, AI/tool, Trace and evaluation screens remain intact.
- **Schema:** additive `0006_auth_hardening` and `0007_operations`; new reauthentication timestamp, admission gate, quota buckets, provider reservations, Trace usage checkpoints and worker records. Migration regression preserves populated M1/M3 history. Existing development volume upgraded without reset. Framework dependencies/contracts remain independent from Platform infrastructure.

The quota, auth, erasure/export and worker changes share locks, settings, model imports and an ordered migration chain. Delivery uses one coherent M4 PR with focused commits, rather than separately merging incomplete cross-dependent slices. No new package, Redis, RabbitMQ, Kubernetes or monitoring service was introduced.

## Optimization and hardening

### Performance findings and measurements

Before implementation, synthetic workloads identified unnecessary ORM materialization and per-session erasure statements. After working implementations, a separate hardening pass reviewed the complete change and applied the following measured improvements.

| Target / method | Before | After | Interpretation |
| --- | --- | --- | --- |
| `usage_for`, SQLite in-memory, 100 provider calls + 100 runs; seven batches of 100 warm reads, Python 3.13 | Median 1.025556 ms/read; 397,918-byte traced peak; 200 ORM rows; 2 SQL queries | Median 0.345495 ms/read; 18,368-byte peak; 2 aggregate rows; 2 SQL queries | 66.3% lower median, 95.4% lower peak in this fixture. Query count unchanged. No PostgreSQL throughput claim. |
| Account erasure, synthetic SQLite accounts, statement counter | 1/10/50 sessions: 14/95/455 SQL statements | 1/10/50 sessions: 15/15/15 statements | Table-wise deletes make statement count constant; 96.7% fewer statements at 50 sessions. One-session case adds a quota cleanup statement. No latency claim. |
| Invalid login, eight existing/missing username samples each | M3: 8 statements; medians 48.30/49.05 ms. Initial M4 controls: 11 statements; 37.32/36.96 ms | Atomic throttle UPSERT: 5 statements; medians 46.81/43.32 ms | 54.5% fewer statements than initial M4, 37.5% fewer than M3. Host timing is noisy; no latency speedup or constant-time proof claimed. |
| Frontend gzip JavaScript | 80.43 kB | 82.74 kB | +2.31 kB for account/operations functionality; no new library. |

Reproduce the final workloads with `.venv/bin/python scripts/benchmark-usage.py`, `scripts/measure-erasure.py` and `scripts/benchmark-auth.py`. Baselines were captured before the corresponding change; scripts report only synthetic data. A subsequent usage read median of 0.318572 ms confirms ordinary measurement variation; the comparison above uses the first equivalent post-change run. Authentication retains the same expensive password hash on nonexistent-account failures.

### Dedicated final review and trade-offs

| Area reviewed | Result and decision |
| --- | --- |
| Backend queries, N+1, serialization | Replaced usage object loading and per-session erasure with aggregates/table-wise deletes. Export has explicit row/byte/page caps and one owner/session lock scope; it is not a streaming large-account export service. |
| Transactions, locks, pool | Preserve user → session → run/job order, with global admission and deterministically sorted quota rows last. Provider waits stay outside transactions. PostgreSQL connection/pool/lock waits are 5 s, statements 10 s and idle transactions 15 s, preserving search-path options. Bounds trade unbounded waits for explicit failures under contention; no production pool sizing claim. |
| Worker claim, polling, heartbeat | Reviewed; no justified optimization to polling/heartbeat defaults. Existing indexed state/lease lookups, SKIP LOCKED and bounded polling retain simple recovery behavior. Added caps and drain rather than speculative batching; per-process one-job capacity and shared admission lock can constrain scale. No automatic provider retry after an uncertain call. |
| Trace storage/query/hash/cleanup | Added bounded regular capacity plus a fixed terminal reserve; a claim that cannot append its start event fails terminally instead of remaining queued. Preserve historical over-capacity records and linear hash verification against the stored checkpoint. Reviewed; no justified extra index or hash shortcut without a larger workload. Existing session/sequence access and bounded cleanup are retained. |
| Resource accounting edge cases | Preserve unknown reservations across cancel/crash; do not clean a bucket still needed by an unresolved call. Legacy Mock quota failures roll back partial message/Trace work while keeping provider accounting. Terminal headroom cannot grow on repeated failure. |
| Frontend rendering/requests | Account/operations views fetch on entry or explicit refresh, with no added global polling or duplicate auto-retry. Password fields clear after requests. Existing workspace polling remains tied to active jobs. Reviewed; no justified state library or bundle splitting for this measured increment. |
| Logging and authorization | Fixed-category JSON metrics exclude raw URLs, query strings, bodies, IPs and tokens. Disable default Uvicorn/nginx access logs; avoid global INFO/debug settings that expose HTTP/SQL internals. Operator views require server role checks. Export/deletion require owner plus recent per-login confirmation and CSRF. |
| Backup and restored data | Compare native SQL/tool cluster/database/role identities before mutations. Restore only new quarantined DBs and revoke restored sessions. Standard tool execution is bounded; no tuning of backup compression/concurrency without realistic I/O evidence. |
| Dependencies/abstractions | Reviewed; no justified new infrastructure or package. Keep policy persistence in Platform and tool/execution contracts in Framework. Existing test-client deprecation is documented rather than hidden or patched by an unrelated dependency migration. |

### Security review

An independent architecture review preceded the sandbox threat-model synthesis. A separate Codex Security diff scan reviewed **40/40 source inventory files**, found **no reportable vulnerability**, and sealed scan `a1e53bcc-4875-44e7-b02f-e6c18767edb9` against baseline `733f4928aa368aea627aab7442fe27109ce0b7b4`. The later payload-free logger/access-log changes received a separate static delta review. These are bounded reviews, not evidence of absence of all vulnerabilities; the review agent did not claim independent test execution. Canonical artifacts remain in local Codex Security storage, outside Git; public repository documents contain the supported architecture and limitations, not machine-local paths.

The [threat model](../architecture/sandbox-threat-model.md) and [future execution proposal](../architecture/sandbox-architecture.md) cover malicious packages/evaluators/code, prompt-induced actions, escape, cross-session access, exfiltration and resource exhaustion. They specify acceptance gates without enabling execution. Current trusted workers share application database/provider authority; logical file isolation and Docker packaging do not create a hostile-code boundary.

### Remaining bottlenecks

The global admission row intentionally serializes capacity changes; large accounts may require asynchronous export/deletion and contention profiling. Trace verification is linear in retained events. Counters and polling incur database work; worker observations can omit crash-time completion metrics. API metrics are per process and worker aggregates span retained records, not a full monitoring history. Bulk backup/load, real failure injection against the PostgreSQL service, deployment latency, tail latency, sustained fairness and multi-host scaling remain unmeasured.

## Regression validation

Commands actually executed:

```sh
PRAXIOJ_RUN_LIVE_TESTS=0 \
PRAXIOJ_TEST_DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj' \
PRAXIOJ_TEST_BACKUP_CONTAINER=praxioj-db-1 .venv/bin/python -m pytest -q
PRAXIOJ_RUN_LIVE_TESTS=0 PRAXIOJ_TEST_DATABASE_URL= TEST_DATABASE_URL= \
PRAXIOJ_TEST_BACKUP_CONTAINER= .venv/bin/python -m pytest -q
npm --prefix apps/web test -- --run
npm --prefix apps/web run build
.venv/bin/python -m pip check
.venv/bin/python scripts/sync-licenses.py --check
docker compose -f compose.yaml -f compose.native.yaml up --build -d --wait
python3 scripts/smoke.py
python3 scripts/smoke-m2.py
python3 scripts/smoke-m3.py --base-url http://127.0.0.1:5173
python3 scripts/smoke-m4.py --base-url http://127.0.0.1:5173
```

- Python counts are in the baseline table. PostgreSQL covered real row-lock admission/rate/password/provider-reservation races, competing worker processes, worker crash/fencing, pending work across API restart, local HTTP provider delays/cancellation and backup/restore. Native API subprocess testing verified spoofed forwarded headers cannot evade its IP quota. An actual row-lock timeout verified bounded PostgreSQL waits. Connection/heartbeat fault handling uses controlled injection, not a physical production database outage.
- SQLite skips 16 PostgreSQL-only concurrency/process cases, the real backup test and the explicitly opt-in live-provider test. PostgreSQL skips only the live-provider test. No external key was generated and no paid/external model call occurred.
- Data tests cover export ownership/reauthentication, byte/row bounds, omission of expired traces, active-run erasure rejection, transactional rollback/retry, integrity/reference cleanup, real custom-format backup/restore, schema rejection, quarantine, revoked restored sessions, target collision and cluster identity mismatch.
- Worker tests cover graceful drain and forced shutdown with unknown usage, independent repeatable maintenance without workers, expired pending jobs, stale leases, queue/global/account limits, metrics roles and safe fault logs. Finite concurrency tests do not establish strict starvation freedom under sustained adversarial load.
- All M1–M4 localhost HTTP smokes passed. M4 returned score **100/100**, six satisfied criteria and verified Trace, with two model calls, one tool call and unknown/estimated usage retained as reservations. It verified owner-only export, denial of participant admin access, login revocation, password rotation and erasure of only its own newly created synthetic account.
- Actual Chrome UI verification: generic registration then explicit login; account allowance/session controls; confirmed JSON export download and cleared password field; problem → session → queued/completed Mock run → authorized file write → saved draft → **100/100 with 6/6 criteria and 19 verified events**; exact/estimated usage distinction on the account view; current-login revocation returning to sign-in. Browser passwords were not saved. Destructive data/password changes were tested through the dedicated synthetic HTTP flow and frontend tests rather than applied to any real account.
- Docker builds and service health passed with existing volume preserved. Python dependency consistency and canonical Apache/third-party notice checks passed. `npm audit` found zero vulnerabilities. A filename-only common-secret-pattern scan of all 171 candidate source/document files found no matches; local Markdown links and `git diff --check` passed. This heuristic is not proof that arbitrary secrets cannot exist. No dependency lockfile change was necessary.
- Known warnings: Starlette deprecates its current httpx test-client integration; SQLite emits a legacy datetime-adapter warning in the historical migration fixture. Neither was suppressed. A future dependency migration can address them separately.

Unverified: Native Windows ACLs/process behavior, actual commercial/local-model inference, production TLS/proxy/identity, MFA/recovery, physical database failover/outage and restore RTO/RPO, encrypted remote backups/PITR, external erasure-ledger replication, multi-host sustained load and any real untrusted-code isolation.

## GitHub delivery and README gate

README is updated for M4 features, explicit registration/login, account/operations UI, quotas, maintenance, backup quarantine, local-only security limits and links to current reports/designs. SECURITY, architecture/module boundaries, authentication, quota/worker/retention contracts, setup, governance/backup runbooks and roadmap were updated. Apache-2.0, Copyright 2026 DoHyun Choi and contributor/third-party notices are preserved.

Delivery is tracked in [PR #14](https://github.com/casing1/praxioj/pull/14). Its final delivery section is the authoritative record of the verified PR head, required CI/CodeQL runs, squash commit and post-merge main checks; these identifiers are recorded there to avoid embedding a self-referential commit hash in this document. Integration requires every required check to pass before the protected squash merge. Main is never pushed directly, force pushed, reset or merged through a bypass.

At PR submission, GitHub Dependabot, CodeQL and secret-scanning open-alert counts were all zero; main protection retained five strict required checks with no bypass actors. A common-secret-pattern diff scan of 36 reachable local commits found no matches without printing potential values. The final remote alert/check status is rechecked in the PR delivery record. This remains a bounded heuristic and platform scan, not a guarantee that every possible secret format is detectable.
