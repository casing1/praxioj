# GitHub governance foundation — validation record

[한국어](../i18n/ko/development/validation-governance.md) · [Documentation index](../README.md)

## Target and status

This separate governance change implements [Issue #16](https://github.com/casing1/praxioj/issues/16) before M6-A Runtime development. It establishes reusable development rules, documentation standards and lightweight checks. M5 remains the completed product baseline; heartbeat, retention, remote Runner and Linux preflight implementation are pending subsequent feature PRs. Creating tracking objects does not satisfy their acceptance criteria.

## Commit and environment

Preflight found clean local/remote `main` at `cb05a77207a2034b0488a16f601b1ddc51026798`, with M5 complete. Work uses `docs/16-github-governance`, preserving protected main, existing user data and PostgreSQL volumes. The final PR delivery record identifies the exact tested head, squash merge revision and remote CI links; this document does not invent a future commit hash.

Local baseline: macOS arm64, Python 3.13.5, Node 24.11.0 and Docker PostgreSQL 18.6. No live/paid Provider calls, credentials, actual participant data, public deployment or untrusted code execution are involved.

## Baseline and regression evidence

The maintainer's validation run recorded the following before M6-A Runtime changes:

| Check | Actual result |
| --- | --- |
| PostgreSQL Python, including synthetic backup/restore | 404 passed, 1 live-provider skip; 107.17 s |
| Authorized SQLite Python | 384 passed, 21 skipped; 64.38 s |
| Frontend | 33 passed; 3.67 s |
| TypeScript/Vite | Passed; JS 274.37 kB / gzip 82.90 kB, CSS 31.23 kB / gzip 7.45 kB |
| `pip check`, vendored license synchronization, Compose configuration | Passed |
| New governance tooling tests | 25 passed; test-level behavior is recorded in the PR |

The first SQLite invocation in the restricted tool environment could not open local fixture sockets: 341 passed, 21 skipped and 43 setup errors in 58.32 s. The authorized local rerun above passed. This is an environment limitation observed and resolved for the run, not a suppressed product failure. SQLite skips include PostgreSQL-only concurrency and credentialed/live or environment-specific tests; exact collection output belongs to the associated run. SQLite does not validate PostgreSQL locking.

The governance diff changes policies, documentation, issue/PR templates and their checks, without changing product Runtime behavior or dependencies. Existing smoke/Compose runtime paths are exercised by the unchanged required CI stack checks; their outcome must be taken from the actual PR runs, not inferred from baseline tests.

## GitHub objects and metadata

The objects below were actually created and read back, assigned to `casing1` and given work-type/component/priority labels as applicable. No dates were imposed. Existing equivalent labels were preserved.

| Object | Scope |
| --- | --- |
| [M6-A](https://github.com/casing1/praxioj/milestone/1) | Judge Lifecycle & Remote Runner Foundation |
| [#16](https://github.com/casing1/praxioj/issues/16) | Governance and documentation standard |
| [#17](https://github.com/casing1/praxioj/issues/17) | Judge heartbeat and lease renewal |
| [#18](https://github.com/casing1/praxioj/issues/18) | Judge retention, purge and quota recovery |
| [#19](https://github.com/casing1/praxioj/issues/19) | Remote Runner protocol and authentication boundary |
| [#20](https://github.com/casing1/praxioj/issues/20) | Linux compatibility and isolation preflight |
| [#21](https://github.com/casing1/praxioj/issues/21) | Lifecycle security and PostgreSQL concurrency tests |
| [#22](https://github.com/casing1/praxioj/issues/22) | M6-A documentation, optimization and final validation |
| [M6-B](https://github.com/casing1/praxioj/milestone/2) | Separate, open isolated Linux Runner validation |
| [#23](https://github.com/casing1/praxioj/issues/23), [#24](https://github.com/casing1/praxioj/issues/24), [#25](https://github.com/casing1/praxioj/issues/25), [#26](https://github.com/casing1/praxioj/issues/26), [#27](https://github.com/casing1/praxioj/issues/27) | Open planning work for dedicated host/runtime isolation, resource limits, network denial, cleanup and independent security acceptance |

The policy covers `enhancement`, `bug`, `documentation`, `maintenance`, `security`, `testing`, `performance`; relevant `area:framework`, `area:api`, `area:broker`, `area:runner`, `area:database`, `area:frontend`, `area:ci`, `area:docs`; and Issue priorities `priority:P0/P1/P2`. A security label describes work type, not proof of a vulnerability. PR text cannot substitute for actual metadata. The PR delivery gate re-queries labels, assignee, matched Milestone and linked Issues after creation and again before merge.

## Implementation and documentation

- Root AGENTS, CONTRIBUTING and the engineering workflow now define Issue-first work, issue-number branches, Conventional Commit PR titles, real metadata verification, English/Korean consistency, README/CHANGELOG review and dedicated optimization/hardening.
- Issue templates and the PR template capture acceptance criteria, dependencies, validation, security/compatibility, limitations and delivery evidence.
- The [documentation policy](documentation-policy.md), [index](../README.md), four document templates and explicit translation manifest establish English canonical/Korean maintained pairs. Existing document paths and historical English records are preserved.
- README and CHANGELOG describe current capabilities and future tracking separately. Historical changelog entries cite actual PRs/reports and do not fabricate releases or tags.
- [AuthZest analysis](governance-reference.md) pins source evidence and preserves PraxiOJ's own squash policy, supported toolchain, personal ownership and security boundaries.

## Security and optimization review

The added tooling checks documentation and PR metadata with minimal read permissions. It does not check out untrusted PR code with elevated credentials, assign privileges, modify GitHub objects automatically or grant Bot/contributor authority. Existing required check names and scanner enforcement remain in place. External contributors and Dependabot retain their authorship and have a documented metadata workflow without requiring repository write access.

Reviewed; no justified optimization to the product Runtime. The change has no product database queries, leases or request serialization to optimize. The documentation checker is local and deterministic; no external URL crawling or dependency was introduced. Tooling tests cover positive, negative and boundary cases rather than claiming application latency improvement.

## CI, limitations and exit conditions

Required CI/CodeQL and any actual review findings must be inspected before squash merge. Their final links and results belong in the governance PR's delivery record. At document preparation, remote results and the final merge revision are pending; no automatic Codex review is assumed.

Offline link/translation checks cannot establish semantic translation quality, external URL availability or production safety. M6-A Runtime features and OS-level M6-B isolation remain unimplemented at this governance stage. M6-A stays open until all mandatory work is resolved and verified; M6-B stays open pending dedicated Linux acceptance. No historical M1–M5 Milestones/Issues were backfilled as completed objects.


Final delivery: [PR #28](https://github.com/casing1/praxioj/pull/28) merged as `5e47b4976e91e0310016d3dd09839efc78636da2` after all required checks. Its final CI recorded 429 passed/1 skip; CodeQL and additive Governance checks passed. Issue #16 closed. M6-A implementation then proceeded separately in [PR #29](https://github.com/casing1/praxioj/pull/29); see [M6-A validation](validation-m6a.md) for current product status. The pending wording above describes preparation-time scope, not current delivery.
