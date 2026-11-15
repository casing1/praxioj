# Engineering workflow

[한국어](../i18n/ko/development/engineering-workflow.md)

This document is the reusable development process for PraxiOJ contributors and coding agents. The root [AGENTS.md](../../AGENTS.md) tells Codex to apply it. It is a project process, not evidence of production-readiness.

## Issue-first tracking

Use **Milestone → Issue → Feature Branch → PR → Validation → Squash Merge** for M6 and every later development stage. Inspect current `main`, Git status, open PRs, relevant security alerts and existing tracking objects before starting. Preserve unrelated work and user data. Reuse equivalent Milestones, Issues and labels rather than duplicating them.

A major stage has a real GitHub Milestone named `M6-A — …`, `M6-B — …`, then `M7 — …`, `M8 — …`. Its description contains Objective, Scope, Deliverables, Acceptance Criteria, Dependencies, Security Requirements, Explicit Non-goals, Verification Requirements and Exit Conditions. Do not estimate a due date merely to populate the field. Creating the Milestone is not implementation; close it only after all required Issues and exit conditions are verified. Do not fabricate historical M1–M5 tracking or releases.

Before implementation, define an Issue using these sections:

- **Summary:** the concrete problem and intended result.
- **Motivation:** why the change is needed.
- **Scope / Non-goals:** affected modules and explicit exclusions.
- **Acceptance Criteria:** observable conditions that can be verified without assuming another unfinished Issue is complete.
- **Security & Compatibility:** authority, data, contracts and migration effects.
- **Validation:** positive, negative, regression, boundary and relevant concurrency checks.
- **Dependencies:** actual predecessor Issues/Milestones, or an explicit statement that none apply.

For maintainer-led work, assign `casing1`; retain other contributors' valid assignees. Set the actual Milestone and appropriate labels through GitHub's UI, API or CLI, then query them back. Template prose does not apply GitHub metadata. External contributors and Dependabot may submit a PR before maintainer triage; maintainers supply or link the tracking Issue and metadata before merge while preserving authorship and without granting repository write access.

## Labels, branches and titles

| Category | Labels | Application |
| --- | --- | --- |
| Work type | `enhancement`, `bug`, `documentation`, `maintenance`, `security`, `testing`, `performance` | Issue and PR; choose actual change types |
| Component | `area:framework`, `area:api`, `area:broker`, `area:runner`, `area:database`, `area:frontend`, `area:ci`, `area:docs` | Issue and PR; use only relevant maintained areas |
| Priority | `priority:P0`, `priority:P1`, `priority:P2` | Primarily Issues; urgent first, major work, follow-up respectively |

Inspect existing labels and retain equivalent labels and valid metadata. A `security` label identifies security-related work; it is not a confirmed vulnerability finding. A PR may span several areas; it need not duplicate the Issue's priority label.

Use a focused branch containing the Issue number, for example `feat/123-judge-heartbeat` or `docs/124-runner-contract`. Do not develop on or push directly to `main`. Commit and PR titles use concise English Conventional Commits: `<type>(<scope>): <summary>`. Allowed types are `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `ci`, `build` and `chore`. Prefer a concrete behavior such as `fix(broker): reject expired execution authority` over vague titles such as `changes`.

## One change at a time

| Gate | Required outcome | Evidence |
| --- | --- | --- |
| 0. Preflight / tracking | Inspect branch, current main, open PRs, alerts, contracts and tests. Check/create actual Milestone and Issue before an Issue-linked branch. Preserve unrelated work. | Actual tracking links and risk notes |
| 1. Design / baseline | Define acceptance criteria, boundaries, rollback and measurable baselines when relevant. | Plan, baseline commands/results |
| 2. Implement | Change behavior incrementally; retain framework/platform boundaries and migrations. | Focused diff, tests |
| 3. Verify | Run targeted tests, then affected regression, database/frontend and real local smoke checks. | Commands, counts, skips |
| **4. Optimize / harden** | **Explicit review for each change and every milestone**, following the checklist below. | Before/after evidence or justified no-op |
| 5. Documentation | Review README and CHANGELOG for every PR; keep specs, runbooks, reports, index and maintained English/Korean pairs accurate. | Changed docs or explicit no-change rationale |
| 6. Deliver | Verify PR metadata, actual reviews, security and required checks; squash merge only when they pass; re-query Issue/Milestone state. | PR/check links and observed final state |

## Mandatory optimization gate

Perform the review **after a working implementation and before the final validation/PR merge**. For larger milestones, reserve a distinct pass and document it in the milestone validation report. A gate means review with evidence, not forced code churn.

Consider these areas as applicable:

- **Performance:** wall time and tail latency for meaningful operations, SQL query count and indexes, lock contention, worker queue throughput/fairness, file size or memory allocations, network/model request overhead, frontend rendering and bundle size.
- **Efficiency:** unnecessary dependencies, repeated serialization, duplicate I/O, oversized Trace payloads, redundant requests and polling, unnecessary database round trips.
- **Security and reliability:** authz checks after refactoring, transaction/lease integrity, bounded resources, secret exposure, cancellation/failure semantics, and cleanup.
- **Maintainability:** unnecessary abstractions, duplicated logic, module boundaries, API clarity, type safety, and actionable errors.

**Measurement discipline**

1. State a hypothesis and choose a relevant baseline: script or test, dataset/workload, environment, repetitions, and metric units.
2. Measure before changes when a measurable optimization is justified. Keep the same workload/environment for the comparison. For noisy measures report multiple runs or ranges.
3. Apply a scoped change, repeat the measurement, and check correctness and regression tests. Record trade-offs and potential regressions.
4. If an optimization is unnecessary or cannot be measured meaningfully, say **"reviewed; no justified optimization"** and explain why. Do not invent speedups or treat arbitrary micro-optimizations as mandatory.
5. Separate **implementation**, **optimization**, and **validation** in milestone reports. Do not confuse a mocked LLM fixture with real model performance.

## README review at every PR

Read `README.md` and answer: does the PR change what a developer or evaluator can install, use, configure, run, expect, or safely deploy?

- **Update README in the same PR** when a feature, API/workflow, configuration, supported environment, status, limitation, or milestone changes. Verify examples and links.
- Update more detailed documents when contracts, schema, security boundaries, migrations, operational procedures, or test instructions change.
- For purely internal refactors, dependency fixes, and documentation-only cleanups without user-facing behavior changes, a README edit is optional—but the PR must state **"README reviewed; unchanged because …"**.
- Never advertise a planned feature as already implemented. A new milestone should update the summary, examples/commands if relevant, limitations, roadmap links, and validation links.

## Pull request writing standard

Use [.github/PULL_REQUEST_TEMPLATE.md](../../.github/PULL_REQUEST_TEMPLATE.md) and write complete prose, not a terse changelog. The required sections are Summary, Linked Issue & Milestone, Update Type, Implementation Details, Verification, Optimization & Hardening, Documentation, Compatibility & Security, Limitations and Checklist. Explain:

- **Why:** the issue, user need, or risk addressed.
- **What:** concrete behavior and architecture changed, with scope/non-goals.
- **How verified:** tests, exact commands and counts; separate CI, local E2E, skipped and not-run paths.
- **Optimization:** explicit review; baseline and before/after when a change is claimed, otherwise a defensible no-op.
- **Docs:** README updated, or explicit reason not required; linked design/runbook/report updates.
- **Risks:** security, compatibility, migration, rollback and remaining limitations.

Use `Closes #123` only for fully resolved Issue acceptance criteria; use `Refs #123` for partial work. Apply actual work-type and component labels, assignee and Milestone to the PR; its linked Issues must have the same Milestone. Query metadata after PR creation and after relevant updates. Preserve valid existing labels and assignments. Keep the body current as implementation or test results change, with exact validation/check links and explanations for non-applicable checklist items. CLI/API PRs must populate the template explicitly.

Prefer draft PRs during implementation and mark them ready after self-verification. Read actual review submissions and unresolved threads, including configured Codex reviews if they really ran. Record unavailable or unexecuted reviews as such. Address findings and rerun affected checks before squash merge. Automated metadata checks use read-only permissions, never `pull_request_target` to execute contributor code and never grant write permissions. The checker treats external/Bot metadata as advisory pending maintainer triage; maintainers still verify tracking before merge. Existing required CI and CodeQL remain mandatory for every PR.

The metadata job executes the checker from the trusted PR base SHA and reads current GitHub metadata. The initial governance PR has no checker on its old base, so its bootstrap job reports this limitation; run `python3 scripts/check-pr-metadata.py --repository casing1/praxioj --number N` manually for that PR. Later PRs use the merged base checker. This bootstrap does not waive existing required checks or manual metadata verification.

## Documentation and changelog gate

English is the canonical source; Korean is the maintained translation. New major technical documents have paired language links and an entry in [docs/README.md](../README.md). Substantially changed core documents update their maintained counterpart in the same PR. Keep identifiers, commands, API paths and technical names unchanged in translations. Scope existing untranslated material in a separate Issue rather than translating the whole archive during unrelated work. Use the [document templates](../templates/design.md) as guidance, removing non-applicable sections or explaining why they do not apply; unfilled templates are not completed evidence.

Review `CHANGELOG.md` on every PR alongside README. Add relevant user-facing capability, compatibility, security and operational changes under `Unreleased`; do not duplicate every refactor or invent released versions/tags. Record a no-change rationale for internal-only work. Keep README, changelog, roadmap, detailed contracts, English/Korean documents and validation reports consistent with actual implementation, not planned scope.

## Merge and milestone completion

Keep the existing protected `main` ruleset, strict required checks and CodeQL configuration. Never bypass them, disable scanners, force push or rewrite shared Git history. Verify the latest PR head, all required check results and actual review findings, update the PR body and squash merge. Re-query the merged PR, linked Issue states and Milestone progress. Close a Milestone only after all required acceptance and exit conditions are evidenced; retain planned M6-B work open until actual isolation acceptance succeeds. Final reports link actual GitHub objects and distinguish local tests, CI, security reviews, skips and unverified paths.

## Quality gates and honest reporting

- `make test` for the Python suite and frontend tests/build; PostgreSQL-specific checks with a disposable database whenever relevant.
- For changes in the local stack, run the appropriate smoke scripts, including the current milestone's flow; do not replace local integration tests with mocked UI tests.
- Use the repository's CI and CodeQL checks. No live provider API key or paid calls in default validation.
- Never merge failed required checks or hide warnings by suppressing tests. If an environment blocks a test, report it as **not run**.
- Apply Apache-2.0 and third-party licensing requirements.
