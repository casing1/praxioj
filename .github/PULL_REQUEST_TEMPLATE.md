## Summary

Explain the concrete problem, why it matters and the resulting behavior.

## Linked Issue & Milestone

Use `Closes #123` for fully resolved acceptance criteria or `Refs #123` for partial work. Link the actual GitHub Milestone. Apply the matching Milestone, assignee and labels through GitHub, then re-query them; this text does not set metadata.

## Update Type

State the relevant categories: Added, Changed, Fixed, Security, Performance, Documentation.

## Implementation Details

Describe changed behavior, contracts, important code paths, architecture decisions and intentional non-goals. Note schema/configuration changes and rollback considerations.

## Verification

Record actual commands, environment, pass/fail/skip counts and reasons. Link actual CI/CodeQL runs and reviews, distinguish local tests from CI, and identify checks not run. Do not assume an automatic review ran.

## Optimization & Hardening

Record the explicit review of database round trips/locks, latency, resource use, redundant work, dependencies, readability, reliability and security boundaries.

For a performance claim, provide comparable before/after measurements, workload, environment, repetitions and trade-offs. Otherwise state **"reviewed; no justified optimization"** with a reason. Link the dedicated milestone pass when applicable.

## Documentation

State the README decision and CHANGELOG decision, with a reason for either unchanged file. Link affected contracts, runbooks, roadmap, validation report and index entries. Describe English/Korean synchronization or explain a scoped translation exception.

## Compatibility & Security

Describe API/Framework/DB compatibility, authentication/authorization, runtime boundaries, user-data and resource effects. Confirm Apache-2.0, contributor copyrights and third-party notices are preserved. Call out migrations and limitations rather than implying production isolation.

## Limitations

State unsupported or unverified behavior and remaining work. Explain when a section or check does not apply.

## Checklist

- [ ] Actual Issue and PR Milestones match; linked Issue uses `Closes` or `Refs` appropriately
- [ ] Actual labels and assignee applied and re-queried; external/Bot authorship and valid existing metadata preserved
- [ ] Issue-linked feature branch and concise `<type>(<scope>): <summary>` PR title
- [ ] Relevant positive, negative, regression and boundary tests run; skips/not-run paths explained
- [ ] PostgreSQL concurrency and localhost integration checked where applicable
- [ ] README, CHANGELOG, detailed docs, index and maintained English/Korean counterparts reviewed
- [ ] Explicit Optimization & Hardening review recorded with evidence or justified no-op
- [ ] No secrets, participant data, local databases or unrelated generated files; licensing/attribution preserved
- [ ] Latest required CI/CodeQL succeeded; actual reviews and unresolved threads inspected before squash merge
- [ ] PR body reflects final implementation and validation; post-merge Issue/Milestone verification planned

Explain any non-applicable or not-yet-completed item. Never bypass the protected `main` ruleset or treat this checklist as proof that GitHub metadata/checks were actually applied.
