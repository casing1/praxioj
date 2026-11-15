# AuthZest workflow reference and PraxiOJ decisions

[한국어](../i18n/ko/development/governance-reference.md) · [Documentation index](../README.md)

## Purpose and status

This record explains the evidence used to establish PraxiOJ's ongoing GitHub development process in [Issue #16](https://github.com/casing1/praxioj/issues/16). It is an analysis of a separate public project's practices, not a transfer of its product design or a claim that M6-A is implemented. M5 is the completed product baseline for this governance PR. The [engineering workflow](engineering-workflow.md) is the normative PraxiOJ policy.

## Reviewed evidence

AuthZest was inspected at commit `36bf3831d59039a73bde432da404dca14965b298`. File links below pin that snapshot; GitHub metadata describes the state observed during this work and may subsequently change.

| Source | Observed practice |
| --- | --- |
| [CONTRIBUTING.md](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/CONTRIBUTING.md) and [branch rules](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/docs/development/BRANCH_RULES.md) | Issue-linked feature branches, Conventional Commits, explicit contributor and review responsibilities |
| [PR template](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/.github/pull_request_template.md) | Concrete scope, verification, metadata and documentation information |
| [CHANGELOG.md](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/CHANGELOG.md) | User-facing change history separated from implementation details |
| [Documentation index](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/docs/README.md), [development plan](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/docs/development/DEVELOPMENT_PLAN.md) and [Korean documentation](https://github.com/casing1/authzest/tree/36bf3831d59039a73bde432da404dca14965b298/docs/i18n/ko) | Navigable document hierarchy, reciprocal language links, planned versus implemented scope |
| [Milestones](https://github.com/casing1/authzest/milestones?state=all), [Issues](https://github.com/casing1/authzest/issues) and [labels](https://github.com/casing1/authzest/labels) | Six milestone objects: 1–3 closed and 4–6 open, without due dates; work-type/component labels and actual issue assignments |
| Recent [PR #167](https://github.com/casing1/authzest/pull/167), [PR #166](https://github.com/casing1/authzest/pull/166) and [PR #165](https://github.com/casing1/authzest/pull/165) | Actual `casing1` assignment, shared `06 - Evaluation and course delivery` milestone, relevant work-type/component labels, and `Refs` links for partial work such as [#152](https://github.com/casing1/authzest/issues/152) and [#150](https://github.com/casing1/authzest/issues/150) |

Repository metadata showed AuthZest allowing merge commits. PraxiOJ retains its existing squash-only policy and protected-main required checks. The analysis adopts process ideas in original PraxiOJ wording rather than copying product code, licensing notices or domain-specific security assumptions.

## Adoption and deliberate differences

| Practice | PraxiOJ decision |
| --- | --- |
| Define work through Issues | Milestone → Issue with acceptance criteria → issue-number feature branch → PR → validation → protected squash merge. The governance change itself follows this order. |
| Match real metadata | Query and apply appropriate labels, assignee and matched Milestone to Issues/PRs; preserve existing valid metadata and contributor/Bot identity. Text in a template does not set GitHub metadata. |
| Conventional changes | English PR titles use `<type>(<scope>): <summary>`; link complete work with `Closes` and partial work with `Refs`. Do not close partially completed work. |
| Detailed review evidence | Preserve five existing required CI/CodeQL checks, inspect actual reviews and update the PR after final tests. Do not assume an automatic Codex review ran. |
| Documentation history | Add a current documentation index, templates, `Unreleased` changelog and scoped English/Korean correspondence. Do not fabricate historical release tags or translate all old documents in one change. |
| Project-specific constraints | Keep Python 3.13, Node 24, the independent Framework/Platform boundary, Apache-2.0 and personal ownership. Do not copy AuthZest's runtime choices, product domain or merge-commit rule. |
| Security and resources | Keep localhost-only development, no paid/live LLM calls and no untrusted code execution. Synthetic protocol validation cannot establish OS isolation. |

## Actual tracking and acceptance

The governance change is tracked by [Issue #16](https://github.com/casing1/praxioj/issues/16), under [M6-A — Judge Lifecycle & Remote Runner Foundation](https://github.com/casing1/praxioj/milestone/1). Implementation is split into [heartbeat #17](https://github.com/casing1/praxioj/issues/17), [retention #18](https://github.com/casing1/praxioj/issues/18), [remote protocol #19](https://github.com/casing1/praxioj/issues/19), [Linux preflight #20](https://github.com/casing1/praxioj/issues/20), [security/concurrency testing #21](https://github.com/casing1/praxioj/issues/21) and [documentation/optimization/validation #22](https://github.com/casing1/praxioj/issues/22). Their creation is tracking evidence, not implementation acceptance.

[M6-B — Isolated Linux Runner Validation](https://github.com/casing1/praxioj/milestone/2) remains a separate open scope. Its planning Issues cover [host/runtime isolation #23](https://github.com/casing1/praxioj/issues/23), [resource limits #24](https://github.com/casing1/praxioj/issues/24), [network denial #25](https://github.com/casing1/praxioj/issues/25), [cleanup #26](https://github.com/casing1/praxioj/issues/26) and [independent security acceptance #27](https://github.com/casing1/praxioj/issues/27). No due date or OS security acceptance is inferred.

The governance PR must demonstrate actual metadata, deterministic documentation checks, appropriate regression checks and all required CI/CodeQL results before squash merge. Its final PR body is the delivery record for exact head/merge revisions and remote run links. M6-A is complete only after its mandatory Issues are implemented, verified and resolved; M6-B cannot close on Mock evidence.

## Optimization and limitations

Reviewed; no justified optimization to the product Runtime: this governance PR changes process, documentation and their validation only. Lightweight offline checks avoid network dependency and do not grant write permissions to contributor code. Translation checks establish file/link correspondence, while semantic consistency and source accuracy require human or agent review. Actual rulesets, alerts, reviews and checks must be queried again for each subsequent PR.
