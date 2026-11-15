# Validation report template

[한국어](../i18n/ko/templates/validation.md) · [Documentation policy](../development/documentation-policy.md)

Template only. Replace prompts with actual results. A planned or skipped check must never be reported as passing.

## Target Milestone

State the objective, acceptance criteria, scope, non-goals and linked Milestone/Issues.

## Commit / Environment

Identify the tested revision, baseline revision, platform, runtime versions, data fixtures and relevant settings without secrets.

## Baseline

Record commands and results captured before changes. Explain which comparisons are valid.

## Implementation

Describe actual behavior and contracts delivered, source paths and architecture decisions.

## Security Tests

Map trust boundaries and invariants to actual positive/negative/race tests and review findings.

## Unit / Integration / E2E Tests

Record commands, environments, exact counts, meaningful observations and evidence locations.

## Results & Skips

Separate passed, failed, skipped, blocked and unverified checks; explain each material limitation.

## Optimization Measurements

Record the dedicated review, workload, comparable before/after measurements, units, repetitions, trade-offs and regression results. If no change is justified, state "reviewed; no justified optimization" and explain why.

## Regression Validation

Record retained behavior and relevant migration/data-lifecycle compatibility checks.

## Known Limitations

Name residual risks, unsupported environments, external integrations and unverified guarantees.

## GitHub PR / CI Results

Link actual Issues, Milestone, PRs, head/merge revisions and CI/CodeQL runs. Confirm assignees, labels, milestone and review results from queried metadata; distinguish local checks from remote CI.

## Final Status

Compare each exit condition with evidence. State unfinished work and follow-up Issues. Close a Milestone only after its mandatory work is resolved and verified. Link the corresponding translation.
