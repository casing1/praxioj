# Changelog

[한국어](docs/i18n/ko/CHANGELOG.md) · [Documentation](docs/README.md)

User-relevant changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) style. Future published versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html); this file does not create releases or tags. New unpublished changes belong under `Unreleased`.

## [Unreleased]

### Added

- Add acknowledged Judge lease renewal, a bounded synthetic dispatch heartbeat loop, and a strict in-memory Runner communication foundation without enabling a public endpoint or real code execution.

### Changed

- Bound terminal Judge evidence/history retention (default 7/30 days). Maintenance removes eligible payload/capability records, exposes unavailable evidence on retained assessments, and later removes summaries; original submission grades remain separate. Payload capacity recovers after purge while summary records have a separate bounded cap. Migration `0009_judge_lifecycle` preserves existing records at upgrade.

### Documentation

- Introduce Issue-first GitHub development governance, matched Milestone/assignee/label metadata, detailed PR evidence, and retained protected squash merging. See [governance Issue #16](https://github.com/casing1/praxioj/issues/16).
- Add a documentation index, design/specification/validation/security-review templates, and an English canonical/Korean maintained translation policy with reciprocal links and deterministic documentation checks.
- Establish separate [M6-A](https://github.com/casing1/praxioj/milestone/1) and [M6-B](https://github.com/casing1/praxioj/milestone/2) planning objects without enabling an untrusted-code runner or treating planned work as implemented.
- Record measured development-host facts, official Linux runtime prerequisites and the unverified M6-B isolation acceptance requirements.
- Publish M6-A regression, security-review, optimization and protected-delivery evidence with synchronized English/Korean status; retain explicit M6-B non-goals.

## Historical milestone records

These entries summarize verifiable development history, not published version releases. No historical release date, version or tag is inferred.

- **M5:** Versioned execution protocol, persistent synthetic Judge Broker, narrow capabilities, strict results/artifacts and deterministic Mock Judge; actual execution remains unavailable by default. [PR #15](https://github.com/casing1/praxioj/pull/15), [validation](docs/development/validation-m5.md).
- **M4:** Localhost operational controls, shared quotas, account export/deletion, worker maintenance and quarantined PostgreSQL restore verification. [PR #14](https://github.com/casing1/praxioj/pull/14), [validation](docs/development/validation-m4.md).
- **M3:** Accounts, server sessions, roles/CSRF, immutable publishing, separate leased AI workers and Trace evidence integrity. [PR #12](https://github.com/casing1/praxioj/pull/12), [validation](docs/development/validation-m3.md).
- **M1–M2:** Standalone Framework, Problem SDK, Runtime/Mock contracts, evaluation, Platform and AI Workspace with compatible provider adapters and bounded logical tools. [Initial public source](https://github.com/casing1/praxioj/commit/bfe6e13), [M1 validation](docs/development/validation.md), [M2 validation](docs/development/validation-m2.md).
