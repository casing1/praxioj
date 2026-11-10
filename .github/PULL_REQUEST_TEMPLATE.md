## Why / context

Explain the problem or motivation. Link an issue or milestone if applicable. Describe the desired outcome in plain language.

## Changes and scope

Summarize the implementation, important architecture decisions, and intentional non-goals. Highlight behavior changes rather than only listing files.

## Verification

- [ ] Relevant Python tests (including PostgreSQL where applicable)
- [ ] Relevant frontend tests and TypeScript/Vite build
- [ ] Real localhost smoke/integration testing where relevant
- [ ] CI and CodeQL checked before merge
- [ ] No secrets, private user data, local databases, or unrelated generated files

**Actual commands, results and skips** (include counts and explain not-run checks):

## Optimization and hardening gate

- [ ] Reviewed changed code for performance, resource usage, needless I/O/SQL, reliability, security boundaries, and maintainability

**Baseline / finding:** Describe the relevant measurement or reason a benchmark is not applicable.

**Change and comparison:** List measured before/after results and workload when claiming an improvement, or state **"reviewed; no justified optimization"** with a reason. Identify trade-offs and regression checks.

## README and documentation

Select one and provide details:

- [ ] `README.md` updated for user-visible behavior, setup, architecture, milestone status, or limitations
- [ ] `README.md` reviewed; no change needed because: ...

**Other docs updated:** Link contracts, roadmap, validation records, migration/runbook updates as appropriate.

## Risks, security and compatibility

Note migration/backward compatibility, authorization and data boundaries, provider/tool behavior, operational changes, known limitations, and rollback considerations. If none, explain why.

## Licensing

Confirm third-party attribution, contributor copyrights, and required Apache-2.0 notices are preserved.

## Final delivery

Update this PR description after implementation/tests. Merge only after required CI/CodeQL checks pass; do not bypass the `main` ruleset.
