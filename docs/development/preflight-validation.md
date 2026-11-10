# GitHub preflight remediation and validation

Reviewed on **2026-11-10 (Asia/Seoul)** for [casing1/praxioj](https://github.com/casing1/praxioj). All nine existing dependency PRs have been reviewed and resolved. The separate preflight remediation PR and its final CI remain pending, as does GitHub's refresh of two dependency alerts. This report covers Phase 0; it does not declare Milestone 3 complete.

PraxiOJ remains an independent personal hobby open-source project, with no official university, laboratory, or corporate affiliation. Its project license remains Apache-2.0, with `Copyright 2026 DoHyun Choi`.

## Initial repository and security state

The initial local commit was `bfe6e13966b6a1a8221540067ef2cb8c1978492a`. The remote review base was `0c60b1b59a6ce5485166de83e9bf8a42693229f4`, which already included the GitHub security baseline from PR #1. Remote state and local working-tree state were considered separately; the Actions review did not check out or modify Dependabot branches.

The coordinating review recorded the following initial GitHub state:

| Surface | Initial observed state |
| --- | --- |
| Open Dependabot alerts | 4, for setuptools 82.0.1 in the two Python build-system manifests |
| Open code scanning alerts | 0 |
| Open secret scanning alerts | 0 |
| Private vulnerability reports | 0 |
| Private vulnerability reporting | Enabled |
| Open dependency PRs | 9: #2 through #10 |

Zero reported alerts is a point-in-time observation, not proof that a repository or its history contains no vulnerabilities or sensitive information. The latest post-remediation state is recorded below.

### Four initial Dependabot alerts

Both `apps/api/pyproject.toml` and `packages/framework/pyproject.toml` pinned setuptools 82.0.1 as a build backend. Each manifest therefore produced one alert for each advisory:

| Alerts | Advisory | Reported severity | Affected behavior | First fixed version |
| --- | --- | --- | --- | --- |
| #1, #3 | [GHSA-h35f-9h28-mq5c / CVE-2026-59890](https://github.com/advisories/GHSA-h35f-9h28-mq5c) | Medium | Unicode normalization differences can bypass `MANIFEST.in` exclusions when building source distributions. | 83.0.0 |
| #2, #4 | [GHSA-xmj3-9gf7-h52w](https://github.com/advisories/GHSA-xmj3-9gf7-h52w) | Low | Malicious legacy wheel namespace metadata can escape the intended destination, including Windows path forms. | 84.1.0 |

These are build-tool findings. They were not characterized as a demonstrated remote exploit of the running PraxiOJ API. The remediation selects setuptools **84.2.1** consistently for both build manifests and the shared dependency lock. The packaging regressions exercise actual source-distribution exclusion and legacy namespace-metadata handling using synthetic files in temporary directories; they do not run submitted problem code or install a malicious artifact.

## Dependency PR decisions

All nine PRs were authored by `dependabot[bot]`. Accepted updates were squash merged after their final-head required checks passed; the remaining proposals were closed with explanations.

| PR | Proposed change | Decision and rationale | Outcome |
| --- | --- | --- | --- |
| [#2](https://github.com/casing1/praxioj/pull/2) | `actions/setup-node` 4 → 7.1.0 | Accept. Official verified release SHA and compatible workflow inputs. | Squash merged: [9b2cde1](https://github.com/casing1/praxioj/commit/9b2cde1ea0e3df598fb471a7926888d01ae9afa4). |
| [#3](https://github.com/casing1/praxioj/pull/3) | `actions/setup-python` 5 → 7.1.0 | Accept. Official verified release SHA and compatible Python 3.13 configuration. | Squash merged: [634e394](https://github.com/casing1/praxioj/commit/634e39404217bcfc665edfffe0005b8ede3a7b44). |
| [#4](https://github.com/casing1/praxioj/pull/4) | `actions/checkout` 4 → 7.0.1 | Accept. Official verified release SHA; existing triggers and credential policy remain compatible. | Squash merged: [62e21d5](https://github.com/casing1/praxioj/commit/62e21d561eba6dc43774f377370810af93a8fe23). |
| [#5](https://github.com/casing1/praxioj/pull/5) | Framework setuptools 82.0.1 → 84.2.1 | Accept the patched build backend, coordinated with the API and shared lock. | Squash merged: [f2c4b80](https://github.com/casing1/praxioj/commit/f2c4b80ec47fc2f3f348b2d5f95e690eb712ea1e). |
| [#6](https://github.com/casing1/praxioj/pull/6) | `@types/node` 24.19.2 → 26.6.6 | Retain the Node 24 type baseline: Node 26 definitions can expose APIs absent from the supported Node 24 runtime. No reported security alert required this major update. Isolated tests and build passed; this was a compatibility-policy decision, not a test failure. | Closed with explanation, not merged. |
| [#7](https://github.com/casing1/praxioj/pull/7) | API setuptools 82.0.1 → 84.1.0 | Superseded by the API 84.2.1 update in #9. | Closed with supersession comment. |
| [#8](https://github.com/casing1/praxioj/pull/8) | Framework setuptools 82.0.1 → 84.1.0 | Superseded by the Framework 84.2.1 update in #5. | Closed with supersession comment. |
| [#9](https://github.com/casing1/praxioj/pull/9) | API setuptools 82.0.1 → 84.2.1 | Accept the patched build backend, coordinated with the Framework and shared lock. | Squash merged: [378e04e](https://github.com/casing1/praxioj/commit/378e04e74c1f8037f017e1d6c735d16380dee29f). |
| [#10](https://github.com/casing1/praxioj/pull/10) | jsdom 27.4.0 → 31.0.0 | Hold the major dev-tool update: its Node engine requirement excludes some currently declared supported versions, and npm emitted `EBADENGINE` on the Node 24.11 host. Isolated tests and build passed; no reported security alert required the update. | Closed with explanation, not merged. |

The frontend review ran isolated `npm ci --ignore-scripts`, all 18 frontend tests, and production builds for both proposals; both passed, with no reported npm audit vulnerabilities. For #10, jsdom 31 requires `^22.22.2 || ^24.15.0 || >=26.0.0`, while the project declares `^22.12.0 || ^24.0.0 || >=26.0.0`. Its major CSS/parser/canvas changes also warrant a deliberate compatibility update. Neither closure is represented as a failing test result or a security fix.

### Actions review: exact provenance and scope

Each proposed full commit SHA was checked against the release tag in the official `actions/*` repository through GitHub's API. All three tag refs resolved directly to the proposed commits, and GitHub reported `commit.verification.verified = true` with reason `valid` for each commit. This establishes the inspected tag/commit relationship and GitHub signature-verification result; it is not a complete audit of all upstream action dependencies.

| PR | Reviewed PR head | Official action release commit | Changed files |
| --- | --- | --- | --- |
| #2 | `2d756486e11ef2bd952b3034614b409b101e420f` | `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1` (v7.1.0) | `.github/workflows/ci.yml`: one action reference |
| #3 | `326816cc7085ba4614e0af68382dd2e7a9f36b73` | `actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` (v7.1.0) | `.github/workflows/ci.yml`: one action reference |
| #4 | `bb59e734684a1e8147d29f98df3a5123aa0a33b7` | `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1) | `.github/workflows/ci.yml`: three references; `.github/workflows/codeql.yml`: one reference |

The diffs changed only action versions and their comments. They did not expand workflow permissions or change application dependencies, package locks, or application source. Checkout retained `persist-credentials: false` in every reviewed invocation.

Compatibility was checked against the README at each exact upstream commit:

- **[setup-node 7.1.0](https://github.com/actions/setup-node/blob/949feb2413d6458794dcd2491c4babbbce0c15c1/README.md):** its newer Node 24 action runtime requires runner 2.327.1 or newer. The repository uses hosted `ubuntu-latest`, and the observed CI ran successfully. ESM changes do not alter the configured inputs. Changes to automatic npm caching do not change this workflow's explicit `cache: npm` and lockfile path. Removal of `always-auth` and the dummy `NODE_AUTH_TOKEN` fallback does not affect this workflow, which supplies neither `always-auth` nor a registry/authentication setup.
- **[setup-python 7.1.0](https://github.com/actions/setup-python/blob/6d4fd22b20465ccc0f7354476588e8df7c9ca0e0/README.md):** its Node 24 action runtime has the same runner requirement. The ESM migration documents no input/output or behavior changes. The existing `python-version: "3.13"` remains supported; no removed installation input is used.
- **[checkout 7.0.1](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/README.md):** the newer default restriction on fork PR checkout under `pull_request_target` or `workflow_run` does not affect the current `push`, `pull_request`, `workflow_dispatch`, and scheduled CodeQL triggers. Credential-storage changes do not enable persistence because every checkout explicitly disables it. The release also contains parsing and escaping fixes. Successful hosted CI covers the Node 24 runtime requirement for the inspected workflows.

All five required checks completed successfully for every reviewed Actions PR head:

| PR | CI run | CodeQL run |
| --- | --- | --- |
| #2 | [42739569757](https://github.com/casing1/praxioj/actions/runs/42739569757) | [42739569692](https://github.com/casing1/praxioj/actions/runs/42739569692) |
| #3 | [42739583734](https://github.com/casing1/praxioj/actions/runs/42739583734) | [42739583750](https://github.com/casing1/praxioj/actions/runs/42739583750) |
| #4 | [42739591760](https://github.com/casing1/praxioj/actions/runs/42739591760) | [42739591665](https://github.com/casing1/praxioj/actions/runs/42739591665) |

These links identify the initial reviewed runs. After sequential branch updates, all checks also passed on the final heads: #2 `8ce8598f` (six successful checks), #3 `dffed02ae1de39a90a4e41837a3f1e64fa3d92fa`, #4 the original head above, #5 `019042b790dc65b4ea8eba43dc984e15138f516b`, and #9 `c2c72c37d76b511758d5af6cee2327410de1de3f`. The final #9 runs were [CI 42743485953](https://github.com/casing1/praxioj/actions/runs/42743485953) and [CodeQL 42743485612](https://github.com/casing1/praxioj/actions/runs/42743485612), both successful.

## Ruleset preservation

The active `Protect main` ruleset (ID `26909462`) was inspected without mutation. It had no bypass actors, prohibited deletion and non-fast-forward updates, required linear history and pull requests, required resolved review threads, and required branches to be up to date before merging. The five required checks were:

- `Node 24 / frontend`
- `Python 3.13 / PostgreSQL 18`
- `Compose configuration`
- `CodeQL / python`
- `CodeQL / javascript-typescript`

The required approving-review count was zero; this report does not imply that a human approval was required or received. The repository's selected integration method was squash merge.

The strict up-to-date condition was retained because passing checks against an older base do not demonstrate that the combined dependency updates still pass. Remaining branches were updated and checked before squash merging. The final Ruleset inspection confirmed it remained active with no bypass actors and the same five strict required checks. No required check was weakened, and no direct main push, force push, or Ruleset bypass was used.

## Local validation of the coordinated remediation

The following are actual results reported by the coordinating implementation/validation pass. They are separate from the read-only Actions review above and from pending final GitHub status checks.

| Check | Observed result |
| --- | --- |
| Full Python suite with PostgreSQL | **168 passed, 1 skipped** in 11.81 seconds; includes both PostgreSQL-only regression cases and seven packaging cases |
| Skipped Python case | Opt-in live provider integration; no real provider credentials or paid API calls used |
| New packaging/security regressions | **7 passed** with the updated build tooling |
| Differential check against setuptools 82.0.1 | The two reported behavior checks failed as expected on the old affected version; this was a controlled regression comparison, not a failure of the patched suite |
| Independent post-patch review | No blocking findings reported; packaging cases passed |
| Frontend tests | **18 passed** |
| TypeScript and Vite production build | Passed |
| Docker Compose configuration and image build | Passed |
| Running Compose stack | All services healthy; API health endpoint and web HTTP request returned 200 |
| `pip check` | Passed |
| Canonical license-copy consistency | Passed |
| `npm audit` | 0 reported vulnerabilities at the time of validation |

The packaging checks also enforce agreement among the installed test environment, both pinned build-system requirements, and `requirements.lock`. Windows-specific namespace path strings are rejected in the tests, but the recorded local execution was not a native Windows run. A build passing is not a claim that the full application was re-exercised in a browser during this preflight; previous end-to-end evidence remains in [Milestone 2 validation](validation-m2.md).

## License and distribution review

The `LICENSE` file at each inspected upstream Actions release SHA declares the **MIT License**, with `Copyright (c) 2018 GitHub, Inc. and contributors`. These actions execute in CI; the version-reference changes do not vendor action source into the PraxiOJ application or static web bundle. No new application-bundle notice was identified as necessary for these three reference changes. Upstream copyright and license terms remain intact; the actions are not relicensed as Apache-2.0.

Setuptools 82.0.1 and 84.2.1 both use MIT; the update introduces no project-license change. Version 84.2.1 requires Python 3.10 or newer and supports the project's Python 3.13 baseline. Its third-party license remains its own. Both built PraxiOJ wheels retain Apache-2.0 metadata and byte-identical project LICENSE/NOTICE copies. The root NOTICE preserves project attribution and contributor/third-party ownership; no new project NOTICE attribution was identified as necessary for this build-tool update.

This review is scoped to the actual changes. It does not replace a release-artifact license inventory of Python dependencies, native wheel contents, container operating-system packages, or future dependencies. Existing distribution considerations are documented in [licensing](licensing.md).

## Latest GitHub state and remaining work

After the nine decisions, open PRs were **0**. Dependabot alerts **#3/#4 were fixed**; **#1/#2 remained open pending GitHub refresh**, although both build manifests on main now pin 84.2.1. No alert was dismissed as a false positive or suppressed. There were **0 open code scanning alerts** and **0 open secret scanning alerts**. No Critical/High finding was identified in this reviewed set. Private Vulnerability Reporting remained enabled.

`SECURITY.md` and `CONTRIBUTING.md` now point to the enabled [private reporting channel](https://github.com/casing1/praxioj/security/advisories/new), without publishing a personal email address. README and repository-description review retained the independent-project identity and localhost-development limitation. The eight requested topics were set: `online-judge`, `ai-evaluation`, `human-ai-collaboration`, `llm`, `ai-agent`, `python`, `fastapi`, and `open-source`.

A high-confidence token/private-key pattern scan inspected **187 Git blobs across all refs** and found no matches. This was a limited heuristic scan, not proof that arbitrary secrets or personal data cannot exist. No secret values were printed.

The separate remediation branch is `chore/preflight-security-remediation`. Its tested implementation commit is `2dcfae88289fa273ede8d3ebe303ccd5733dad2e`; a normal merge of updated `origin/main` produced `6ec99cb9bb7bb548540b494c469c735f2446fb8b`, preserving history without rebasing or force pushing. **Creating the separate preflight PR, passing its final CI/CodeQL, and squash merging it remain pending**, along with confirmation of alert #1/#2 refresh. Phase 0 is not yet declared complete.

No live hosted LLM, local inference model, or paid provider call was required for this preflight. Public authentication, hardened multi-user isolation, distributed execution, and a secure untrusted-code sandbox are not established by these dependency changes. Existing localhost-development restrictions still apply.
