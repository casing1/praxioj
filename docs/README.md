# Documentation

[한국어](i18n/ko/index.md) · [Project README](../README.md)

This index covers the current implementation and retained design records. English is the canonical source; Korean translations are maintained for the pairs listed in [the translation manifest](translations.json). Untranslated historical documents remain English references. See the [documentation policy](development/documentation-policy.md) before adding or substantially changing a document.

## Start here

- [Local setup and supported commands](development/local-setup.md)
- [AI Workspace and credential-free provider fixtures](development/ai-workspace.md)
- [Contributing](../CONTRIBUTING.md) and [engineering workflow](development/engineering-workflow.md)
- [Roadmap and implemented versus planned scope](development/roadmap.md)
- [Changelog](../CHANGELOG.md) and [licensing/distribution](development/licensing.md)

## Architecture

- [Overview](architecture/overview.md) and [module boundaries](architecture/module-boundaries.md)
- [Persistent AI jobs and worker lifecycle](architecture/persistent-jobs.md)
- [Resource quotas](architecture/resource-quotas.md) and [Trace retention](architecture/trace-retention.md)
- [Execution Broker](architecture/execution-broker.md)
- [Judge lifecycle and evidence retention](architecture/judge-lifecycle.md)
- [Execution foundation and future isolation proposal](architecture/sandbox-architecture.md)
- Historical [M1 implementation contract](architecture/implementation-contract.md) and [M2 implementation contract](architecture/milestone-2-contract.md)

## Specifications

- [Problem package format](specifications/problem-format.md)
- [Runtime, tools and resource accounting](specifications/runtime-and-tools.md)
- [Trace events and integrity](specifications/trace-events.md)
- [Evaluation contract](specifications/evaluation-contract.md)
- [Execution protocol, capabilities and result validation](specifications/execution-protocol.md)
- [Synthetic Runner channel and authentication boundary](specifications/runner-protocol.md)

## Development and governance

- [Engineering workflow](development/engineering-workflow.md)
- [Documentation and translation policy](development/documentation-policy.md)
- [AuthZest reference analysis and PraxiOJ decisions](development/governance-reference.md)
- [Governance foundation validation](development/validation-governance.md)
- [Dependency and environment versions](development/versions.md)
- [Roadmap](development/roadmap.md)
- [Linux Runner preflight and pending M6-B host acceptance](development/linux-runner-preflight.md)

## Operations and security guides

- [Security policy and private reporting](../SECURITY.md)
- [Execution-isolation threat model](architecture/sandbox-threat-model.md)
- [Authentication and authorization](development/authentication.md)
- [Account export and deletion](development/data-governance.md)
- [Local backup, restore verification and quarantine](development/backup-restore.md)

The Platform remains a localhost development preview. Protocol checks, Mock tests and Docker Compose do not establish an operating-system security sandbox or approve public deployment.

## Validation records

- [M6-A lifecycle and Runner validation](development/validation-m6a.md)
- [M5 execution foundation](development/validation-m5.md)
- [M4 operational controls](development/validation-m4.md)
- [M3 platform foundation](development/validation-m3.md)
- [GitHub preflight remediation](development/preflight-validation.md)
- [M2 AI Workspace](development/validation-m2.md)
- [M1 initial foundation](development/validation.md)

Each report describes its own revision, environment and verified scope. Historical counts are not current test results. M6-A's report distinguishes current local evidence from pending protected delivery and final acceptance.

## Document templates

- [Architecture/design](templates/design.md)
- [Technical specification](templates/specification.md)
- [Validation report](templates/validation.md)
- [Security review](templates/security-review.md)

Templates are prompts, not completed evidence. Remove inapplicable sections or state why they do not apply; replace all prompts before publishing a completed document.
