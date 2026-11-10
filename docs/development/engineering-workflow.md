# Engineering workflow

This document is the reusable development process for PraxiOJ contributors and coding agents. The root [AGENTS.md](../../AGENTS.md) tells Codex to apply it. It is a project process, not evidence of production-readiness.

## One change at a time

| Gate | Required outcome | Evidence |
| --- | --- | --- |
| 0. Preflight | Inspect branch, open PRs, relevant alerts, affected APIs and tests. Preserve unrelated work. | Scope and risk notes |
| 1. Design / baseline | Define acceptance criteria, boundaries, rollback and measurable baselines when relevant. | Plan, baseline commands/results |
| 2. Implement | Change behavior incrementally; retain framework/platform boundaries and migrations. | Focused diff, tests |
| 3. Verify | Run targeted tests, then affected regression, database/frontend and real local smoke checks. | Commands, counts, skips |
| **4. Optimize / harden** | **Explicit review for each change and every milestone**, following the checklist below. | Before/after evidence or justified no-op |
| 5. Documentation | Review README for every PR; update it for user-visible changes and each milestone. Update specs/runbooks/report as relevant. | Changed docs or PR rationale |
| 6. Deliver | Create a descriptive PR; re-check security and CI; squash merge when all required checks pass. | PR body and check links |

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

Use `.github/PULL_REQUEST_TEMPLATE.md` and write complete prose, not a terse changelog. A high-quality PR should explain:

- **Why:** the issue, user need, or risk addressed.
- **What:** concrete behavior and architecture changed, with scope/non-goals.
- **How verified:** tests, exact commands and counts; separate CI, local E2E, skipped and not-run paths.
- **Optimization:** explicit review; baseline and before/after when a change is claimed, otherwise a defensible no-op.
- **Docs:** README updated, or explicit reason not required; linked design/runbook/report updates.
- **Risks:** security, compatibility, migration, rollback and remaining limitations.

Keep PR text current when implementation or test results change. Link relevant issues and CI runs. The PR template is guidance; GitHub UI may insert it automatically, but CLI/API PRs must populate it explicitly.

## Quality gates and honest reporting

- `make test` for the Python suite and frontend tests/build; PostgreSQL-specific checks with a disposable database whenever relevant.
- For changes in the local stack, run the appropriate smoke scripts, including the current milestone's flow; do not replace local integration tests with mocked UI tests.
- Use the repository's CI and CodeQL checks. No live provider API key or paid calls in default validation.
- Never merge failed required checks or hide warnings by suppressing tests. If an environment blocks a test, report it as **not run**.
- Apply Apache-2.0 and third-party licensing requirements.
