# Milestone 5 — implementation, security and validation

Recorded 2026-11-11 (Asia/Seoul). This is the Judge Execution Foundation: a strict protocol and trusted synthetic Broker harness, with real untrusted execution still unavailable. GitHub delivery status is recorded separately below and in the final PR description.

## A. Implementation

### Preflight and baseline

Started from clean local/remote main `ea796f69554947d6d04fec4d269f14e5d1cea65e` (M4, PR #14). GitHub had no open PRs or open Dependabot, CodeQL or Secret Scanning alerts; main CI/CodeQL had succeeded. The active main ruleset retained five strict required checks and no bypass actors. A separate `feat/m5-execution-broker` branch preserves main and all existing database volumes. No unrelated user changes were present.

Read AGENTS, README, CONTRIBUTING, SECURITY, engineering workflow, M4 validation, roadmap, module/evaluation contracts and the M4 sandbox threat model/proposal. Current `ExecutionBackend` and external evaluator methods were unavailable; built-in evaluation was the only execution authorized in process. M5 implements Phase 1 of that proposal. The new Judge queue does not repurpose AI `Job`/`WorkspaceRun` or provider-token accounting.

Direct baseline before source changes on macOS arm64, Python 3.13.5, Node 24.11.0 and Docker PostgreSQL 18.6:

| Check | Baseline |
| --- | --- |
| PostgreSQL Python, including synthetic backup/restore | 298 passed, 1 live-provider skip; 79.51 s |
| Default SQLite Python | 281 passed, 18 skipped; 46.68 s |
| Frontend | 33 passed; 3.29 s |
| TypeScript/Vite | Passed; JS 274.37 kB / gzip 82.90 kB; CSS 31.23 kB / gzip 7.45 kB |

SQL fixtures use disposable schemas; backup verification additionally uses only generated synthetic databases. Existing application data is retained. Baseline/final suite duration differs in test count and concurrent host load, so it is not an application speed comparison.

### Delivered structure and contracts

- `praxioj.execution.protocol`: version 1.0 immutable nested contracts for request/result, input snapshot, policy, runtime identity, limits, criterion definitions, artifact declarations/content metadata, usage, cleanup, capabilities, availability and policy validation. Authority includes request/job/attempt/session, fence, problem/evaluator versions, input/policy/image digests and deadline. UTF-8 JSON is bounded to 64 KiB, has explicit wire versions, rejects duplicate keys/nonfinite values/excess structure and freshly revalidates model copies.
- `praxioj.execution.backends`: immediate deterministic in-memory Mock scenarios for success, evaluated failure, execution failure, cancellation, timeout and corrupted results. Real backend selection remains unavailable; unknown runtime/policy never selects Mock or host execution. Legacy unavailable workspace methods are preserved.
- `praxioj.evaluation.execution`: validates and maps the synthetic result into the existing `EvaluationResult` shape inside `SyntheticExecutionAssessment`. It always records Mock provenance and `independent_execution_evidence=false`. Execution completion and criterion success are separate. Existing built-ins and the original stored Evaluation remain unchanged.
- `praxioj_api.judge`: separately persisted Broker admission, claims, single-attempt opaque authority, heartbeat/fencing, current source validation, result acceptance, cancellation and bounded reconciliation. One attempt per job; a new request is explicit rather than an automatic replay. No database transaction spans the backend await.
- `praxioj_api.judge_routes`: default-unavailable administrator test harness, restricted to the authenticated administrator's own fixed `release-plan` fixture. Request bodies accept submission/request identifiers and the registered fixture only; they cannot select source, commands, modules, URLs, images or policy. Runtime introspection returns the fixed synthetic fixture and declared capabilities. HTTP never returns a result capability or accepts an arbitrary uploaded result.
- Data lifecycle: original Trace checkpoint and Evaluation are preserved. Minimal Judge lifecycle diagnostics go to separate audit records. Export includes safe Judge projections, omitting private request/capability/worker fields. Active Judge work blocks erasure; terminal jobs/attempts cascade with the account's solve data. Trace expiry revokes active authority and releases reservations; remaining fixed synthetic outputs carry expired evidence availability in exports. Independent maintenance reconciles Judge leases without a Judge executor.

`0008_judge_execution`, following `0007_operations`, adds only `judge_jobs` and `judge_attempts`, indexes, unique idempotency/fence constraints and foreign keys. It does not transform or delete M4 rows. Populated M4 migration tests retain user, submission, original Evaluation and Trace head. Backup schema validation and API readiness require the new head; restored databases remain quarantined across every new Broker authority entrypoint. The existing development volume was upgraded through the additive migration, without reset.

Default Judge settings: backend `unavailable`; 2 active/32 retained jobs per account, 16 pending/2 running and 256 retained globally, 2 MiB/16 MiB active output reservations per account/system, 15-second lease. Each active job reserves 64 KiB. Admission counts under the existing global gate serialize capacity checks; terminalization releases exactly once. These are logical storage/job limits; no host CPU/memory/disk enforcement or billing measurement is inferred. Mock resource usage remains unknown (`None`). No package, broker service or monitoring infrastructure was added.

## B. Security

### M5 acceptance gates

| Gate | Verified M5 portion | Evidence and boundary |
| --- | --- | --- |
| A1 | Default unavailable, strict runtime/policy selection and no fallback | Default HTTP 503 with no job, Unavailable never invokes Mock, unknown configuration denied, Mock process/network/filesystem tripwires, external evaluator still unavailable |
| A2 | Existing auth/CSRF/Origin/body/rate boundaries plus administrator AND owner checks | Positive authenticated fixture; anonymous/participant/foreign-admin denial; bad source binding, arbitrary authority fields and hostile Origin/absent CSRF rejection |
| A3 | Server-state job/attempt capability, current lease/fence, input/policy/image/request correlation, replay/cancel control | Real PostgreSQL concurrent creation/claim/result and cancellation races; wrong token/audience/operation/job/attempt/worker/fence; expiry, role loss, source drift, rollback and repeatable recovery |
| A9 | Strict bounded result and inline artifact validation | Actual synthetic UTF-8 bytes vs declared size/hash; exact criterion IDs/maxima/sums/pass-state; duplicate/path-prefix/case/encoding/depth/size/version/correlation and undeclared-artifact rejection |

These are **protocol, authorization and inline-data** gates. Actual OS objects (links/devices/FIFO/socket), hostile processes, host separation, kernel escape resistance, filesystem/network isolation, external resource enforcement and complete teardown are not implemented or passed. A4–A8 and the real-host portions of A9–A12 remain pending; existing M4 backup controls and M5 reviews do not complete those execution gates.

Capabilities have 32 random bytes of entropy, hash-only persistence, one audience/operation/attempt, expiry and a live fence/lease. Hash comparison alone is insufficient: completion rechecks current active administrator, owner/session/submission/problem, pinned source and Trace availability under locks before consuming authority and committing. Cancellation/expiry/accepted results revoke further use. Incorrect tokens cannot terminalize a valid attempt. Authorized stale/damaged source failures revoke and release capacity in a committed transaction, then return a controlled rejection; invalid raw results are never stored as an assessment.

The trusted Broker remains inside the Platform's database trust boundary. Mock receives the execution request only, without application settings, cookies/CSRF, plaintext capability, DB access or provider credentials. The local smoke driver's role CLI and optional API-container restart are **trusted operator test actions outside Mock**; they do not create an executable backend. Future runner deployment needs a separate identity/host and narrowly authenticated broker channel.

A fresh-context independent architecture review retained full effective-resource bindings and source evidence before threat-model synthesis. An independent Codex Security diff scan (`0ce936bd-33cb-4235-8c71-7fca61845840`) reviewed all **20 preserved source/config/script items**, including untracked source, and sealed with **zero findings**. Its exact source inventory hash is `4107c7b22ba84fa9aa4949e1a8cfa76c80391cc475c15a1a0d926cf8bd205cf0`. The later restart-driver and quarantine-test changes received a separate supplemental review with no reportable issue; the other 18 source items remained byte-identical. Neither reviewer claimed application execution, and scanner silence is not proof of absence of vulnerabilities. Managed canonical artifacts stay outside Git; repository documentation contains supported architecture facts and limitations.

Known boundaries remain explicit: localhost development only; no public deployment approval, verified identity/MFA/recovery, secret vault, application backup encryption or external deletion-ledger replication. Host/DB operators are trusted. Metadata/hash validation is distinct from confinement and cannot authenticate a privileged writer replacing both data and digests. Native Windows and real model inference remain unverified.

## C. Validation

| Check | Final local result |
| --- | --- |
| PostgreSQL Python including backup/restore | 404 passed, 1 live-provider skip; 105.22 s |
| Default SQLite Python | 384 passed, 21 skipped; 63.96 s |
| Framework targeted | 161 passed, including 61 new protocol/backend cases |
| Broker targeted PostgreSQL | 36 passed; 14.82 s |
| Broker targeted SQLite | 33 passed, 3 PostgreSQL race skips; 9.24 s |
| HTTP/lifecycle targeted PostgreSQL, final quarantine case included | 9 passed; 3.83 s |
| Frontend | 33 passed; 3.17 s |
| TypeScript/Vite | Passed; same JS/CSS sizes as baseline |
| Dependency consistency / notice synchronization / npm audit | Passed; zero npm vulnerabilities |
| Docker images and localhost health | Passed with existing volume preserved |
| Existing M1–M4 HTTP smokes | All passed |
| Default Judge HTTP | Passed: unavailable, no Mock execution, synthetic account erased |
| Opt-in Mock Judge HTTP | Passed: accepted synthetic assessment, original grade/Trace unchanged, idempotence, replay/cancel denial, export and own synthetic erasure |
| Pending Judge job across actual API-container restart | Passed: the same pending job survived restart and completed with the original grade/Trace preserved |

Commands actually used (development credentials shown are public local defaults):

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
npm --prefix apps/web audit --audit-level=moderate
docker compose -f compose.yaml -f compose.native.yaml up --build -d --wait
python3 scripts/smoke.py
python3 scripts/smoke-m2.py
python3 scripts/smoke-m3.py --base-url http://127.0.0.1:5173
python3 scripts/smoke-m4.py --base-url http://127.0.0.1:5173
python3 scripts/smoke-m5.py --expect-unavailable
PRAXIOJ_JUDGE_BACKEND=mock docker compose -f compose.yaml -f compose.native.yaml up -d --wait api
python3 scripts/smoke-m5.py --restart-api
```

The original full M5 run passed 403 PostgreSQL tests/1 skip and 383 SQLite tests/21 skips before adding the final explicit quarantine-entrypoint regression. That case passed in the nine-case HTTP/lifecycle PostgreSQL suite, and the table records the repeated final full inventory. PostgreSQL-only Judge races use separate database connections/transactions and threads, not a real remote Judge fleet. Existing AI worker process/crash/restart regressions remain in the suite. Broker reconstruction preserves the pinned request and policy. Quarantine tests verify enqueue, claim, heartbeat, completion, failure, cancellation and recovery all deny before mutation.

PostgreSQL skips only the explicitly opt-in live-provider test. SQLite skips 19 PostgreSQL-only race/process cases, real PostgreSQL backup/restore and the live-provider case. No API key was generated and no paid model call occurred. Tests create/drop only synthetic schemas/databases/accounts. Existing data and volumes remain intact.

The README and protocol Python examples were executed successfully. Frontend source is unchanged, so M5 adds no rendering, polling or bundle cost. Actual Docker/HTTP validates the new internal harness; M5 does not claim a new browser-based Judge UI or repeat the historical Chrome result as a new run. Known Starlette/httpx test-client and historical SQLite datetime-adapter deprecation warnings remain visible.

Unverified: native Windows, a real isolated runner/Linux/KVM, OS artifact collection, hostile execution/escape/network/resource/teardown behavior, production DB failover/load and recovery objectives, encrypted off-host backups/current external erasure ledger and actual LLM inference.

## D. Dedicated optimization and hardening

The post-implementation review separately inspected parsing/copying/hashing, database round trips, lock order, reservation races, authority checks, lifecycle errors, dependencies and module boundaries. It removed duplicate fresh validation only after measuring the working implementation; every required authority/content check remains. There is no public unchecked or “already trusted” result bypass.

Comparable **same-version equivalent pipelines**, not old-release production benchmarks:

| Workload | Redundant reference path | Current path | Measurement |
| --- | --- | --- | --- |
| Fixed 1,812-byte request, Mock generation; 20 warmups then 7×500 calls per path | Two fresh parses: median 0.411373 ms, 20,877-byte peak/100 calls | One fresh parse: 0.254809 ms, 17,748-byte peak | About 38.1% lower median in this rerun; no DB or execution runtime |
| Fixed 1,504-byte result, validation plus assessment; 20 warmups then 7×100 calls per path | Two full validations: median 0.777575 ms, 33,110-byte peak/100 calls | Combined full validation/map: 0.441622 ms, 26,140-byte peak | About 43.2% lower median in this rerun; exact equivalent outputs asserted |

Environment: Python 3.13.5, macOS arm64, in-process fixed UUID/digest/fixture inputs, `perf_counter` batches and `tracemalloc`. Request ranges were 0.382706–0.419998 vs 0.245062–0.269203 ms; result ranges 0.776311–0.786786 vs 0.428757–0.449559 ms. The host was not isolated from other work. Earlier repeats observed 0.362027→0.247317 ms for Mock and 0.819255→0.453070 ms for result validation; compare within each run, not across runs or versions. No sandbox, PostgreSQL throughput or user-facing latency gain is asserted.

Reproduce with `.venv/bin/python scripts/benchmark-judge-mock.py` and `.venv/bin/python scripts/benchmark-judge-broker.py`. The reference wrapper simulates the former duplicate parsing/checking in the current version. Production paths use the single fresh parser and combined validated mapping; unsafe model-copy, malformed-schema, false runtime and forged digest regressions still pass.

| Remaining review area | Decision and trade-off |
| --- | --- |
| Request creation / DB query count | Reviewed; no justified optimization. Owner/session/source locks and bounded admission aggregates favor correctness; retained capacity is small. Do not remove source/role checks or cache authority to save queries. |
| Transactions / concurrency | Preserve User → SolveSession → JudgeJob → Attempt, admission last. Recovery uses skip-locked eligible ownership; retention holds a session and takes only descendant locks. Invalid-authority races and reservation release have real PostgreSQL tests. The shared admission gate may bottleneck at future scale. |
| Input storage / hashing | Store a pinned request template and required metadata, with no copied raw Trace. Result/assessment duplication is bounded and keeps the audit distinction explicit; no content-addressed store or index added without workload evidence. |
| Oversized data / serialization | Reject at strict 64 KiB and structure/field/file limits; verify actual inline byte hashes. Do not skip validation because Mock is trusted. Future OS collectors require a separate bounded implementation. |
| Failure handling | Controlled codes omit raw backend exception/result data. Invalid tokens do not cancel legitimate work; authorized expired/drifted authority terminalizes and releases once. Quarantined databases reject every authority entrypoint. |
| Frontend / infrastructure | Reviewed; no justified optimization or dependency change. M5 has an internal test harness and pure contracts, with no new UI, global polling, broker package or execution service. |
| Dispatcher / retention | Current immediate Mock uses a one-shot HTTP dispatcher with a 30-second wait and no heartbeat loop; its default lease is 15 seconds. A delayed fixture can lose authority and fail closed. A real runner needs heartbeats. Retained jobs have fixed caps but no individual purge/delete endpoint; capacity persists until account erasure. This test-harness limit is not a production lifecycle policy. |

## E. GitHub and documentation

README now explains the actual M5 interfaces, fixed Mock role, safe default, executable standalone example, local smoke commands and M6 prerequisites. SECURITY records new invariants/reportable boundaries without weakening exclusions. Architecture, protocol, capability/artifact rules, quota/lifecycle integration, setup, data governance, backup revision and roadmap are consistent. Apache-2.0, Copyright 2026 DoHyun Choi and contributor/third-party rights remain intact.

Delivery is tracked in [PR #15](https://github.com/casing1/praxioj/pull/15). Its final delivery section carries exact CI/CodeQL links, the verified head, protected squash commit and post-merge main checks. One coherent integration PR with focused commits avoids merging a broken cross-dependent protocol/Broker/schema slice. Main protection, scanner settings and check names remain active; no bypass, force push or direct main push is used. Integration is complete only after required checks pass and the PR merges. Final identifiers are maintained in the PR delivery record rather than embedded as a self-referential commit hash here.

## F. Next milestone

M6 requires a dedicated disposable Linux execution host/VM, supported kernel/KVM facilities, runtime/image provenance and patching, minimal launcher privileges, narrow remote job capabilities, secrets exclusion, default-deny egress, read-only inputs/root, bounded scratch/output, cgroup/VM CPU/memory/PID/storage controls, and an independent deadline/reaper. Evaluate Firecracker where KVM is available and gVisor as an alternative only against measured workload/host acceptance evidence; neither is installed or approved by M5. Native macOS/Windows/Docker Desktop cannot silently substitute an ordinary process/container.

Complete pending A4–A8, OS-level A9 and real failure/teardown/recovery/review portions of A10–A12 before enabling hostile code. Add real runner heartbeat/revocation, retained-job lifecycle, host/resource accounting and independent security review. Keep contestant and author evaluator environments separate, validate every result/artifact, and retain the original source/score/provenance distinction. Production identity, encrypted remote backup/erasure recovery and public deployment remain separate prerequisites.
