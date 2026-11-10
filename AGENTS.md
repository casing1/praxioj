# PraxiOJ — Codex repository instructions

Scope: this repository. Follow [CONTRIBUTING.md](CONTRIBUTING.md) and [the engineering workflow](docs/development/engineering-workflow.md) for every change.

## Non-negotiable boundaries

- PraxiOJ is an independent personal Apache-2.0 project. Preserve contributor copyright, notices, and third-party attribution.
- Preserve the Framework / Platform separation. No FastAPI, database ORM, or React dependencies inside the standalone Framework.
- This remains a localhost development preview until separately reviewed for deployment. Do not claim a production-grade sandbox or deploy publicly.
- Do not add secrets, API keys, actual participant data, local databases, or untrusted code execution. Never run paid/live LLM integrations unless the maintainer explicitly requests them.
- Preserve user changes and data. Do not force push, reset, rewrite Git history, or bypass the protected `main` ruleset.

## Mandatory development cycle (every feature, fix, and milestone)

1. **Preflight:** inspect Git status, current `main`, open PRs/relevant alerts, affected contracts, and current tests. Work on a focused branch, not `main`.
2. **Plan and baseline:** state acceptance criteria, security/compatibility risks, and which existing measurements/tests are relevant. For performance-sensitive work, capture comparable baseline measurements *before* editing.
3. **Implement and test:** make the smallest sound change; add positive, negative, regression, and relevant boundary cases.
4. **Optimization gate (explicit):** review the changed path for avoidable database queries/locks, resource usage, latency, redundant work, unnecessary dependencies, readability, maintainability, and security/performance trade-offs. Profile or benchmark suspected bottlenecks where feasible. Optimize only when justified; otherwise record **"reviewed; no justified optimization"** with a brief rationale. Never claim an improvement without before/after evidence.
5. **Docs gate (explicit):** review `README.md` on **every** PR. Update it whenever capabilities, limitations, quickstart commands, configuration, architecture overview, supported environments, or milestone status changes. If not changed, state why in the PR. Keep the affected detailed docs and validation report consistent with the implementation. Do not churn README text for purely internal maintenance with no user-facing impact.
6. **Delivery:** run relevant checks; record actual outputs, skips, and unverified paths. Fill the PR description with context, change summary, validation, README decision, optimization review, security/compatibility implications, and outstanding limitations. Create/update the PR on the feature branch. Merge with squash only after all required checks succeed.

## Pull requests and milestones

- Use `.github/PULL_REQUEST_TEMPLATE.md` as the **content structure**, including when creating PRs via `gh` or an API that does not auto-populate templates.
- Do not leave placeholder text or unchecked sections without an explanation. Update the PR body after final tests and before merge.
- On **every milestone**, schedule a dedicated post-implementation optimization-and-hardening pass before final sign-off. Record the baseline, findings, changes (or reason no change was warranted), and regression results in the milestone validation report.
- Keep `README.md` and `docs/development/roadmap.md` accurate for completed milestones, without advertising unimplemented features.
- Prefer measurable, reversible changes. Do not weaken tests, disable scanners, or inflate performance numbers to make a milestone appear complete.
