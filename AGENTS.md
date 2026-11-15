# PraxiOJ — Codex repository instructions

Scope: this repository. Follow [CONTRIBUTING.md](CONTRIBUTING.md) and [the engineering workflow](docs/development/engineering-workflow.md) for every change.

## Non-negotiable boundaries

- PraxiOJ is an independent personal Apache-2.0 project. Preserve contributor copyright, notices, and third-party attribution.
- Preserve the Framework / Platform separation. No FastAPI, database ORM, or React dependencies inside the standalone Framework.
- This remains a localhost development preview until separately reviewed for deployment. Do not claim a production-grade sandbox or deploy publicly.
- Do not add secrets, API keys, actual participant data, local databases, or untrusted code execution. Never run paid/live LLM integrations unless the maintainer explicitly requests them.
- Preserve user changes and data. Do not force push, reset, rewrite Git history, or bypass the protected `main` ruleset.

## Mandatory development cycle (every feature, fix, and milestone)

1. **Preflight and tracking:** inspect Git status, current `main`, open PRs/relevant alerts, affected contracts, and current tests. Check or create the actual GitHub Milestone and Issue before development; define acceptance criteria and dependencies. Work on an Issue-linked focused branch, not `main`.
2. **Plan and baseline:** state acceptance criteria, security/compatibility risks, and which existing measurements/tests are relevant. For performance-sensitive work, capture comparable baseline measurements *before* editing.
3. **Implement and test:** make the smallest sound change; add positive, negative, regression, and relevant boundary cases.
4. **Optimization gate (explicit):** review the changed path for avoidable database queries/locks, resource usage, latency, redundant work, unnecessary dependencies, readability, maintainability, and security/performance trade-offs. Profile or benchmark suspected bottlenecks where feasible. Optimize only when justified; otherwise record **"reviewed; no justified optimization"** with a brief rationale. Never claim an improvement without before/after evidence.
5. **Docs gate (explicit):** review `README.md` and `CHANGELOG.md` on **every** PR. Update them when capabilities, limitations, quickstart commands, configuration, architecture overview, supported environments, milestone status, or relevant user impact changes. If not changed, state why in the PR. Keep affected detailed docs, the documentation index, English canonical sources, maintained Korean counterparts, and validation reports consistent. Do not churn README or changelog text for purely internal maintenance with no user-facing impact.
6. **Delivery:** run relevant checks; record actual outputs, skips, and unverified paths. Fill the PR description with context, change summary, validation, README decision, optimization review, security/compatibility implications, and outstanding limitations. Create/update the PR on the feature branch. Merge with squash only after all required checks succeed.

## Pull requests and milestones

- Use `.github/PULL_REQUEST_TEMPLATE.md` as the **content structure**, including when creating PRs via `gh` or an API that does not auto-populate templates.
- Do not leave placeholder text or unchecked sections without an explanation. Update the PR body after final tests and before merge.
- On **every milestone**, schedule a dedicated post-implementation optimization-and-hardening pass before final sign-off. Record the baseline, findings, changes (or reason no change was warranted), and regression results in the milestone validation report.
- Keep `README.md` and `docs/development/roadmap.md` accurate for completed milestones, without advertising unimplemented features.
- Prefer measurable, reversible changes. Do not weaken tests, disable scanners, or inflate performance numbers to make a milestone appear complete.

## Durable GitHub governance

- Follow **Milestone → Issue → Feature Branch → PR → Validation → Squash Merge** for M6 and all later development. Inspect existing objects first; reuse equivalent Milestones, Issues and labels. Do not invent historical work, releases or completion dates.
- A Milestone is a real GitHub object with objective, scope, deliverables, acceptance criteria, dependencies, security requirements, non-goals, verification and exit conditions. Use `M6-A — …`, `M6-B — …`, then `M7 — …`, `M8 — …`. Set no speculative due date. Keep planned or unverified work open.
- Before implementation, define the Issue's Summary, Motivation, Scope, Non-goals, Acceptance Criteria, Security & Compatibility, Validation and Dependencies. Apply a work-type label, appropriate `area:*` label(s), priority and the actual Milestone. Assign maintainer-led work to `casing1`; preserve other contributors' valid assignees and labels.
- Use a branch such as `feat/123-judge-heartbeat`, including its Issue number. Use concise English Conventional Commits and PR titles: `<type>(<scope>): <summary>` with `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `ci`, `build` or `chore`.
- Apply actual work-type and component labels, assignee and Milestone to each PR. Use `Closes #123` for completed work or `Refs #123` for partial work; the linked Issue and PR must have the same Milestone. After creating or updating a PR, re-query GitHub to verify metadata and linked Issues; text in a template does not apply metadata.
- Preserve external contributor and Dependabot authorship. Maintainers triage their Issues, labels and Milestones before merge without granting additional repository permissions. Read-only advisory metadata checks for those PRs do not waive maintainer review or existing required checks.
- Prefer a draft PR for ongoing work, then ready it for review. Inspect actual CI, CodeQL, review submissions and unresolved threads before squash merge. Never assume an automatic Codex review ran; record unavailable or unexecuted reviews honestly.
- Perform the separate Optimization & Hardening pass; record actual tests, skips, limitations, README/changelog decisions and translation synchronization in the PR and milestone report. Use the documentation templates when appropriate; empty templates are not completed documents.
- After merge, query the merged PR, required-check results, linked Issue states and Milestone progress. Close a Milestone only after all required Issues and exit conditions are verified. Final reports must use observed GitHub state and link the actual objects.
