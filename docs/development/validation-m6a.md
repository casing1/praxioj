# M6-A — Judge Lifecycle & Remote Runner Foundation validation

[한국어](../i18n/ko/development/validation-m6a.md) · [Documentation index](../README.md)

## Target, revision and status

M6-A implements issue-first GitHub governance, acknowledged Judge renewal, bounded terminal retention, a synthetic Runner communication boundary and a non-executing Linux preflight. Implementation, full local regression, independent managed review and protected feature delivery are complete. This record preserves their actual evidence; final documentation delivery and the post-merge GitHub closure audit are governed by Issue #22. M6-B remains open and unimplemented.

Preflight on 2026-11-15 (Asia/Seoul) found clean local/remote M5 main `cb05a77207a2034b0488a16f601b1ddc51026798`, no open PRs/Issues/Milestones and zero open Dependabot, CodeQL and Secret Scanning alerts. Squash-only repository settings and active main Ruleset `26909462` retain five strict required checks with no bypass actors. No existing participant data or PostgreSQL volume was reset.

Governance was implemented first on `docs/16-github-governance`: [PR #28](https://github.com/casing1/praxioj/pull/28), final head `e17d2bd300d624d75514e135a0bcec2366df2a59`, protected squash `5e47b4976e91e0310016d3dd09839efc78636da2`. Feature work starts from that merged main on `feat/17-judge-lifecycle-runner`. Lifecycle and Runner changes share the acknowledged renewal/cancellation contract and are delivered together to validate that boundary coherently; final documentation and GitHub acceptance are a separate PR. Exact feature heads/merge/check links belong to their PR delivery records and the final delivery section below.

Native environment: macOS 27.0.1 arm64, Python 3.13.5, Node 24.11.0; local Docker PostgreSQL 18.6. Compose uses the repository's pinned development images. Timings below are observations on a shared development host, not production latency/capacity guarantees. Tests use random disposable schemas and synthetic backup/restore databases. No live/paid model, generated API key, real participant data, public deployment or untrusted execution was used.

## GitHub governance and actual objects

The AuthZest [reference analysis](governance-reference.md) records inspected source and actual Issue/PR metadata, adopting tracking/verification and bilingual documentation practices while retaining PraxiOJ's own squash policy, supported versions, domain and personal Apache-2.0 ownership.

| Actual object | Scope and state at implementation validation |
| --- | --- |
| [M6-A Milestone 1](https://github.com/casing1/praxioj/milestone/1) | Open until every required Issue and final exit condition is verified |
| [#16](https://github.com/casing1/praxioj/issues/16) / [PR #28](https://github.com/casing1/praxioj/pull/28) | Governance resolved and squash merged before product changes |
| [#17](https://github.com/casing1/praxioj/issues/17), [#18](https://github.com/casing1/praxioj/issues/18) | Heartbeat/lease and staged retention/quota recovery |
| [#19](https://github.com/casing1/praxioj/issues/19), [#20](https://github.com/casing1/praxioj/issues/20) | Runner boundary and Linux preflight |
| [#21](https://github.com/casing1/praxioj/issues/21), [#22](https://github.com/casing1/praxioj/issues/22) | Security/concurrency acceptance and final docs/optimization/validation |
| [M6-B Milestone 2](https://github.com/casing1/praxioj/milestone/2), [#23](https://github.com/casing1/praxioj/issues/23)–[#27](https://github.com/casing1/praxioj/issues/27) | Open planning for dedicated host/provenance, isolation/quotas, network/secrets, teardown and independent OS acceptance; no M6-B implementation |

Both milestones have objective, scope, deliverables, acceptance, dependencies, security, non-goals, verification and exit conditions. Neither has an invented due date. All Issues were assigned to `casing1` and read back with actual work/area/priority labels and matching Milestones. Existing valid labels were preserved. Work labels include enhancement/bug/documentation/maintenance/security/testing/performance; maintained areas cover Framework/API/Broker/Runner/database/frontend/CI/docs; priorities are P0/P1/P2. The security label is not a vulnerability verdict. No M1–M5 objects/releases/tags were fabricated.

AGENTS, CONTRIBUTING, engineering workflow and templates now require Milestone → Issue → issue-number branch → PR → validation → squash merge, actual metadata re-query, README/CHANGELOG decisions, English/Korean consistency, explicit optimization/hardening and post-merge audit. The additive read-only Governance workflow runs its metadata checker from trusted base code; external/Bot metadata is advisory for maintainer triage without changing authorship or granting write authority. The first PR's missing-base checker was explicitly bootstrapped and manually run against actual GitHub metadata. The independent source review found a rendered-anchor correctness issue; it was fixed with regression cases before merge.

## Baseline and observed regression

| Check | Before M6-A product changes | Current local result |
| --- | --- | --- |
| PostgreSQL Python, real synthetic backup/restore enabled | 404 passed, 1 live-provider skip; 107.17 s | **510 passed, 1 live-provider skip; 144.77 s** |
| SQLite Python | 384 passed, 21 skipped; 64.38 s | **483 passed, 28 skipped; 89.81 s** |
| Frontend | 33 passed; 3.67 s | **33 passed; 3.78 s** |
| TypeScript/Vite | Passed | Passed; unchanged JS 274.37 kB / gzip 82.90 kB; CSS 31.23 kB / gzip 7.45 kB |
| Governance tooling | Added after baseline | 25 passed; local Markdown/translation checker run before delivery |
| Framework | M5 foundation 161 cases | 182 passed, including 21 new Runner cases |
| M5 + lifecycle targeted PostgreSQL | M5 retained | 83 passed; 44.98 s |
| New lifecycle SQLite | Not present | 32 passed, 6 PostgreSQL-only skips; 15.94 s |
| Runner targeted PostgreSQL | Not present | 43 passed; 12.02 s |
| Runner targeted SQLite | Not present | 42 passed, 1 PostgreSQL race skip; 6.79 s |

The total adds 25 governance, 38 lifecycle and 43 Runner cases. PostgreSQL skips only explicitly opt-in live inference. SQLite's 28 skips include 26 PostgreSQL-specific clock/lock/process cases, real PostgreSQL backup/restore and live inference. SQLite is never treated as PostgreSQL locking evidence. Existing Starlette/httpx TestClient deprecation and historical SQLite adapter warnings remain visible; scanners/tests were not disabled. Different suite sizes and concurrent host activity prevent interpreting total test duration as application performance.

The first restricted baseline SQLite run had 341 passed/21 skipped/43 setup errors because localhost fixture sockets were prohibited, followed by the successful authorized run above. A Runner-targeted PostgreSQL setup similarly required authorized loopback access; its successful 43-case rerun is reported, without hiding that environment failure. No product assertion was weakened to address either environment restriction.

## Implementation and architecture decisions

- `JudgeBroker.renew()` preserves `heartbeat() -> bool` while returning DB-observed lease/capability/deadline metadata. Authority checks run after owner/session/job/attempt locks using PostgreSQL `clock_timestamp()`. Expiry is rechecked after source/result validation; cancellation/recovery cannot revive old authority. Dispatcher renews while awaiting Mock and joins the loop before terminalization, without a DB transaction across execution.
- Migration `0009_judge_lifecycle` preserves M5 records, adds the purge marker/terminal index and updates readiness/backup schema validation. Result retention defaults to 7 days, metadata 30 days with integer bounds `1 <= result <= metadata <= 90`. Bounded maintenance preserves active/protected authority, purges result/private request/attempt payloads, retains a safe assessment explicitly marked unavailable, and later deletes summaries. Original Evaluation and Trace remain separate. Payload capacity recovers; all metadata is bounded at four times configured retained-job caps. Idempotency history expires with its job record.
- `praxioj.execution.runner` adds strict separate version-1.0 wire contracts and `MockRunnerTransport`; the Framework stays ORM/web independent with no new dependency. A trusted Platform `JudgeRunnerGateway` holds the original Broker lease privately, binds separately observed identity and exact request/attempt/fence/digests, and stores at most three operation-grant hashes. Heartbeat rotation and single result submission reject replay. Cancellation requires persisted owner cancellation; cleanup accepts only fixed synthetic no-resource status. Default unavailable selection and existing HTTP fixture routes remain.
- The chosen channel is bounded in-memory serialized data, not a public remote endpoint. It isolates interfaces, not hostile code in the same process. Gateway restart/closure loses transient grants and leaves persisted lease expiry/recovery authoritative. No DB/LLM/account credential crosses into Mock; the backend sees only the execution request. Operational TLS/peer authentication and dedicated Linux runtime remain M6-B prerequisites.
- [Linux preflight](linux-runner-preflight.md) records actual Darwin/macOS and Docker VM metadata separately from unknown VM KVM/device/permission behavior. Official Firecracker/gVisor/kernel requirements inform pending host acceptance. No host was provisioned, virtualization/firewall altered, runtime installed or guest executed.

The English/Korean [lifecycle](../architecture/judge-lifecycle.md) and [Runner specification](../specifications/runner-protocol.md) provide detailed contracts. Existing API/Framework request/result contracts and original grading remain compatible; evidence fields are additive. Retention is an intentional data-lifecycle change, and downgrading code/schema cannot recreate purged evidence.

## Security acceptance and independent review

Observed tests cover successful/concurrent heartbeat, wrong worker/attempt/fence/token, capability/lease/deadline expiry, DB-clock skew, expiry during validation, policy/digest tampering, replay, cancellation and worker failure, stale result denial, owner isolation, runtime unavailable, malformed/oversized wire/result data, credential omission, one-use cleanup correlation, idempotent/bounded cleanup, protected active authority, quota recovery, export/erasure, populated migration and quarantine. PostgreSQL uses independent connections/transactions for renewal/cancel/recover/cleanup/admission/result-controller races. No actual remote Runner fleet or OS confinement is implied.

SECURITY was inventoried/resolved and updated with M6-A invariants without adding exclusions, severity changes or accepted risks. The dependency-local `expect-type` policy does not govern these source paths. Managed independent Codex Security diff scan `6dfa601d-4bcb-4298-b0e9-43fb9a8b0174` was sealed and read back as complete: **zero findings, 20 surfaces, zero deferred/exclusions**. It covered all 13 managed changed source/config/script paths plus 7 supplemental configuration/test/benchmark paths. Inventory SHA-256 is `22aa3a6fe9755f42d48f2547ee14962323e1fcdd1e5e9f7595c931c35337a84c`; all 20 file hashes were unchanged at completion. A fresh architecture worker verified 16 resource boundaries, 8 resolved questions and 186 citations across 32 files. A supplementary discovery-worker thread limit was handled by the independent reviewer reading every preserved source directly. The original snapshot `61b909e7dbdaf7acb878f73d293de9013a833a051ff47e0d66ddc59e355aa3ef` and the managed warning about later documentary changes are preserved: the scan covers that source snapshot, while final documentation continues separately. The reviewer ran no application tests and reported root/implementation measurements as external evidence. Scanner silence is not proof of absence of vulnerabilities. Automatic GitHub Codex review is not assumed; actual submitted reviews/threads must be read before merge.

## Docker, HTTP and data preservation

Current Compose images built and all services became healthy on localhost with existing `praxioj_postgres_data` preserved. The additive migration ran without resetting the volume. Existing M1/M2 HTTP smokes, M3 through the web proxy, M4 account/quotas/export/deletion and default-unavailable Judge smoke passed. Explicit Mock Judge HTTP also passed with the same pending job surviving an actual API-container restart, accepted assessment, replay/cancel denial, safe export and own synthetic account erasure. Original grades and verified Trace remained unchanged; additive evidence statuses were checked. Independent maintenance ran successfully with all reported recovery/purge counts zero in the application database, and the API was returned to default unavailable settings. Positive aged cleanup is covered in disposable-schema tests/benchmarks, not inferred from that zero-count integration run.

The M1–M3 historical smoke scripts leave their synthetic demonstration accounts by design; M4/M5 remove their own generated accounts. PostgreSQL suite tests drop only their own random schemas and backup databases. No participant data or application volume is truncated. No new Judge UI/browser flow is claimed: frontend source is unchanged, frontend unit/build and actual web-proxy HTTP regressions were run.

Common-secret-pattern checks found no matches in 229 working-tree text files and in 368 unique text blobs (up to 2 MB) across all 50 reachable Git commits at that observation. No values were printed. This heuristic does not establish absence of every secret, inspect unreachable history or replace GitHub Secret Scanning.

Actual full-suite commands:

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
.venv/bin/python scripts/check-docs.py
docker compose -f compose.yaml -f compose.native.yaml up --build -d --wait
```

Displayed DB credentials are the repository's public local development defaults. Additional actual HTTP commands are the existing `scripts/smoke.py`, `smoke-m2.py`, `smoke-m3.py --base-url http://127.0.0.1:5173`, `smoke-m4.py --base-url http://127.0.0.1:5173`, and `smoke-m5.py --expect-unavailable`. No credentialed provider test was enabled.

## Dedicated optimization and hardening

The separate post-implementation pass reviewed heartbeat round trips, row-lock order/contention, claim fairness, cleanup/index/batch cost, serialization, repeated authorization, capacity accounting, failure recovery and API/AI-worker separation. It retained security checks and avoided an unchecked trust flag, broad delete, new service or dependency.

| Workload and observation | Actual result and interpretation |
| --- | --- |
| M5 before product edits: one fixed pending/claimed fixture, no background AI worker, 20 warmups + 7×100 heartbeat calls | 14 SQL/call; median 6.90287708 ms, range 5.98575–8.48312291 ms |
| Working implementation before/after reusing the already DB-observed authorization instant for source binding, with a fresh final renewal time check retained | SQL 14 → 13/call. Separate-run medians 5.51311291 → 7.25459458 ms; **no latency improvement claim** |
| Same-process equivalent extra-clock reference vs current; alternating order, 20 warmups/path + 7×100/path | 14 vs 13 SQL/call; medians 5.22951834 vs 5.07445458 ms. Reference range 4.95826083–7.11807375; current 4.93581–5.34921959. Shared-host noise/overlap and prior opposite direction prevent an API latency claim |
| Current cleanup, 100 terminal jobs plus one live job in a disposable schema | Payload stage 685.016459 ms / 1003 SQL / 100 payloads+attempts removed; metadata stage 501.685292 ms / 1003 SQL / 100 summaries removed; live job retained and repeated cleanup zero |
| Actual 100-row retention selector EXPLAIN | Limit → Index Scan, planning 0.112 ms / execution 0.077 ms; observed plan only, not a production-scale guarantee |

Reproduce the development-only benchmark with the same local test environment and an explicit path, for example `.venv/bin/python -m pytest -q -s tests/api/benchmark_judge_lifecycle.py -k paired` or `-k cleanup`. It is excluded from default `test_*.py` collection. The paired reference is a same-version equivalent redundant-clock path, not a timed old-release API. No M5 purge implementation existed, so no cleanup before/after speedup is asserted.

One fewer heartbeat round trip is justified by observed query counts. Claim/source/owner checks remain intentional; no speculative cache or fairness rewrite is warranted. Cleanup deliberately uses short per-job locked transactions (10 SQL/job plus 3 batch statements) with quarantine/audit rather than blind bulk deletion. Runner uses one authoritative Broker renewal per accepted heartbeat and a bounded three-grant registry. Serialization is strictly bounded/freshly validated. Frontend polling/bundle and dependencies are unchanged. For these remaining paths: **reviewed; no justified optimization** beyond the measured query reduction. Default 15-second lease means renewal scheduling at 5 seconds only while an explicit dispatch is running; this is not a new global Judge poller.

## Documentation and GitHub delivery

README/CHANGELOG and their Korean counterparts describe actual lifecycle/retention/Runner scope and safe defaults under Unreleased. New lifecycle, Runner and Linux documents have maintained English/Korean pairs and index/manifest entries. Existing setup/data/backup/Broker guides receive focused updates, with detailed new policy available in paired documents; the unrelated historical archive is not mass translated. Root security guidance is synchronized with implemented boundaries. Roadmap/final report are updated for final acceptance, preserving M6-B open status and Apache-2.0/contributor/third-party notices.

Governance PR required [CI 43688372075](https://github.com/casing1/praxioj/actions/runs/43688372075), [CodeQL 43688372081](https://github.com/casing1/praxioj/actions/runs/43688372081) and additive [Governance 43688397694](https://github.com/casing1/praxioj/actions/runs/43688397694) succeeded; CI directly recorded 429 passed/1 skip and frontend 33, plus pending Judge persistence across actual API restart. Post-merge main CI `43688685676`, CodeQL `43688685679` and Governance `43688685696` also succeeded. PR #28 had no submitted reviews/open threads; the independent local source review and fix are separately disclosed.

Feature [PR #29](https://github.com/casing1/praxioj/pull/29) was verified at head `fa8571538890f5f779e9555b3e5a90f506ba26c7` and protected squash merged as `cc57923821c1f59f55c12f37f8501fb2f6315035`; the two trees were compared equal. Actual labels, casing1 assignment, Milestone 1 and closing Issues #17–#20 were read back. [CI 43691097829](https://github.com/casing1/praxioj/actions/runs/43691097829), [CodeQL 43691097845](https://github.com/casing1/praxioj/actions/runs/43691097845) and [Governance 43691152863](https://github.com/casing1/praxioj/actions/runs/43691152863) succeeded. CI recorded 510 passed/1 skip in 155.90 s, frontend 33 and successful API-restart persistence. Actual submitted reviews/open threads were empty; no GitHub Codex review submission was observed. This is distinct from the sealed independent source scan.

Feature post-merge main [CI 43691430291](https://github.com/casing1/praxioj/actions/runs/43691430291), [CodeQL 43691430223](https://github.com/casing1/praxioj/actions/runs/43691430223) and [Governance 43691430268](https://github.com/casing1/praxioj/actions/runs/43691430268) also succeeded on `cc57923821c1f59f55c12f37f8501fb2f6315035`.

Issue #16 and implementation Issues #17–#20 are closed. Final acceptance Issues #21/#22 close through the final documentation PR only after its required checks and review/metadata audit. Milestone 1 closes only after all required Issues/PRs are actually resolved; Milestone 2 and Issues #23–#27 remain open. The final PR delivery record carries its own immutable head, checks, merge revision and post-merge main/closure readback, avoiding a self-referential source commit hash in this file.

The final documentation pass reviewed README/CHANGELOG, paired roadmap/status, links and evidence/limits; **reviewed; no justified optimization** for that prose-only change. Runtime source/config/tests/scripts remain identical to the independently reviewed and fully tested feature tree. Local services were restored to Judge unavailable, stopped cleanly and the original named PostgreSQL volume was verified present.

Final documentation and acceptance are delivered by [PR #30](https://github.com/casing1/praxioj/pull/30), assigned to casing1 with actual documentation/security/testing and area:docs labels, Milestone 1 and closing links to Issues #21/#22. Its delivery record reports the latest required checks, actual review state, protected squash and final GitHub closure readback. [M6-A](https://github.com/casing1/praxioj/milestone/1) is closed only after those exit conditions; [M6-B](https://github.com/casing1/praxioj/milestone/2) stays open.

## Known limitations and M6-B exit work

Real isolated Linux/KVM/gVisor execution, authenticated remote networking, host CPU/memory/PID/storage limits, filesystem object collection, default-deny egress, secret canary tests, runtime/image provenance acceptance and independent guest teardown/host recovery are **not implemented or validated**. The Docker VM's metadata and synthetic cleanup cannot pass those gates. M6-B Issues #23–#27 remain open.

Localhost preview restrictions, no public deployment, trusted host/DB operators, no production identity recovery/MFA, no application backup encryption/external deletion-ledger replication or restore promotion remain. Real model inference, native Windows, actual remote-network partitions, large production load/failover and OS isolation are unverified. A failed/disconnected maintenance scheduler delays physical retention cleanup. Metadata caps can still reject new work rather than delete protected history early. Transient Runner grants do not support restart resume. No production sandbox, exact billing or exactly-once external execution guarantee is claimed.
