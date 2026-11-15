# Contributing to PraxiOJ

[한국어](docs/i18n/ko/CONTRIBUTING.md)

PraxiOJ welcomes bug reports, documentation improvements, tests, and focused code contributions. It is an independent personal hobby open-source project maintained by DoHyun Choi, not an official university, laboratory, or company project. The project name and use of the Apache License do not imply institutional sponsorship, endorsement, or affiliation with the Apache Software Foundation.

## Start with the problem

Development follows **Milestone → Issue → Feature Branch → PR → Validation → Squash Merge**. Check existing GitHub Milestones, Issues and PRs first, reuse equivalent objects, and define an Issue before implementation. This applies to small fixes as well as major features. An Issue must state Summary, Motivation, Scope, Non-goals, measurable Acceptance Criteria, Security & Compatibility, Validation and Dependencies. For a bug, also include expected/actual behavior, relevant versions and minimal reproduction. Remove credentials, participant data and private submissions from examples and logs.

Each major development stage uses a real GitHub Milestone; a Markdown heading alone is not tracking. Use titles such as `M6-A — Judge Lifecycle & Remote Runner Foundation`, `M6-B — Isolated Linux Runner Validation`, then `M7 — …`. Describe objective, scope, deliverables, acceptance criteria, dependencies, security requirements, explicit non-goals, verification and exit conditions. Do not invent due dates or retrospectively mark undocumented work complete. Close a Milestone only after all required Issues and exit conditions are verified.

Maintainers apply the Issue's work type, relevant `area:*` label(s), priority and actual Milestone. Maintainer-led work defaults to assignee `casing1`; existing valid assignees and labels are preserved. External contributors and Dependabot may open PRs before this triage; maintainers supply the tracking metadata before merge, preserve authorship and never require extra write permissions merely to contribute. See the [engineering workflow](docs/development/engineering-workflow.md) for label categories and metadata verification.

Read the [architecture](docs/architecture/overview.md), [module boundaries](docs/architecture/module-boundaries.md), and [roadmap](docs/development/roadmap.md). The current milestone intentionally leaves production authentication, untrusted execution, and external evaluator execution unavailable.

## Develop and validate

Fork the repository and use a focused Issue-linked branch such as `feat/123-judge-heartbeat`; never develop directly on `main`. Use concise English Conventional Commit and PR titles: `<type>(<scope>): <summary>`, with type `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `ci`, `build` or `chore`. Follow the [local setup guide](docs/development/local-setup.md) for supported Python, Node, Docker and PostgreSQL versions. The root [Makefile](Makefile) provides `make install`, `make test`, `make api`, `make web`, and Compose helpers.

Keep changes proportional to the problem and preserve these boundaries:

- The Framework must remain independent of FastAPI, SQLAlchemy, React, and platform-specific secrets. Extend providers, tools, evaluators, and execution backends through their contracts.
- New problems normally belong in directories containing validated `manifest.json` files. A manifest must never cause the API to import arbitrary Python code.
- Preserve existing problem versions once sessions reference them. Document manifest/event schema changes, migrations, version changes, and unimplemented behavior.
- Include appropriate tests for changed behavior and regressions. Update documentation when commands, contracts, or limitations change.

Run `make test` for the Python tests, frontend tests, and frontend build. If a relevant check cannot run, state that explicitly rather than reporting it as passing. For persistence, migrations, or locking changes, also run the PostgreSQL suite described in [local setup](docs/development/local-setup.md) against a disposable local database. A SQLite pass does not establish PostgreSQL transaction behavior. For API/UI integration changes, exercise the running stack and both `scripts/smoke.py` and `scripts/smoke-m2.py`; component tests alone do not verify the complete flow. Provider tests must use Mock or local fixtures by default; keep credentialed network tests opt-in and clearly skipped when unconfigured.

## Mandatory development and optimization process

All changes follow the [engineering workflow](docs/development/engineering-workflow.md). Coding agents should also follow the repository [AGENTS.md](AGENTS.md).

Every development cycle has explicit preflight, design/baseline, implementation, verification, **optimization/hardening**, documentation, and PR delivery gates. Before merging a change, review the affected code for unnecessary database round trips, latency, memory/resource usage, security/reliability regressions, and maintainability. Measure before and after when an optimization claim is made. If no optimization is justified, record **"reviewed; no justified optimization"** with a concise reason rather than changing code for its own sake.

**Review `README.md` in every PR.** Update it in the same PR whenever user-visible functionality, installation, commands, configuration, architecture summary, milestone status, or limitations change. If not updated, say why in the PR. Keep the relevant contracts, roadmap, security documentation, and validation reports consistent.

**Review `CHANGELOG.md` in every PR.** Record relevant user-facing behavior, compatibility and security changes under `Unreleased`; explain a no-change decision for internal-only maintenance. Do not invent releases or version tags. English is the canonical documentation language and Korean is a maintained translation. Add paired, reciprocal language links for new major technical documents, synchronize substantially changed core counterparts, and register new documents in the [documentation index](docs/README.md). Preserve code identifiers, commands and API paths. Existing untranslated documents need scoped follow-up work rather than an unrelated mass translation.

Each completed milestone must include a dedicated post-implementation optimization/hardening pass and document its findings (including a justified no-op), measurement limitations, tests and risks in the milestone validation report. Do not claim performance gains without comparable baseline data.

## Submit a pull request

Use [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md), including for CLI/API-created PRs. Explain the problem, resulting behavior, implementation and actual verification. Use `Closes #123` for an Issue fully resolved by the PR or `Refs #123` for partial work. Apply actual work-type and component labels, assignee and the same Milestone as the linked Issue; the PR body does not apply metadata. Re-query GitHub after creation and after relevant updates to confirm these fields. Include UI screenshots when useful and call out migrations, compatibility changes and limitations. Keep unrelated cleanup separate.

Prefer a draft PR during implementation, then mark it ready after self-verification. Inspect actual required CI, CodeQL results, submitted reviews and unresolved review threads; do not assume an automatic code/security review exists. Address findings, re-run affected tests and update the PR body before merge. External/Bot metadata checks are advisory while maintainers triage; this does not waive code review or required checks. Only squash merge after every required check succeeds, without bypassing the protected `main` ruleset. Do not force push, rewrite shared history or weaken scanners. After merge, verify Issue states and Milestone progress from GitHub before reporting completion.

Do not include local `.env` files, cookies, tokens, private submissions, generated databases, dependency caches, or unrelated generated files. Do include intentional dependency lockfile changes when dependencies change.

The maintainer reviews pull requests for correctness, scope, architecture, documentation, and licensing before merging. Respond to review comments and keep the pull request focused. This is a personal project, so review availability may vary. Discuss technical disagreements respectfully, provide evidence, and avoid personal attacks or harassment.

## Licensing and attribution

PraxiOJ uses the [Apache License, Version 2.0](LICENSE). Intentional contributions submitted for inclusion are offered under Apache-2.0 unless separately agreed in writing with the maintainer, consistent with [Section 5 of the license](https://www.apache.org/licenses/LICENSE-2.0). No contributor license agreement (CLA) is currently required. Contributors retain their copyrights; contribution does not assign copyright to the maintainer.

The original project notice is `Copyright 2026 DoHyun Choi`. It does not replace contributors' or third parties' rights. Preserve their applicable copyright and attribution notices.

Submit only material you have the right to contribute, including code, documentation, tests, fixtures, sample problems, and assets. For copied or adapted third-party material, identify its source, version or revision, and license in the pull request and retained attribution. Include required license and original notices, and add required modification notices to changed files, including prominent notices for modified Apache-licensed files. Dependencies retain their own licenses; adding a dependency does not relicense it under PraxiOJ's license.

## Security reports

Read [SECURITY.md](SECURITY.md) before reporting a vulnerability. Use the repository's enabled [GitHub private vulnerability reporting](https://github.com/casing1/praxioj/security/advisories/new) channel. Do not publish credentials, participant data, or exploit details against a live service in a public issue or pull request.
