# Roadmap

## Milestone 1: foundation

The foundation provides the independent Problem SDK, provider/runtime contracts and Mock Provider, trace envelope, deterministic evaluation, execution interfaces, PostgreSQL REST API, and participant workflow. Those interfaces and the original sample remain supported.

## Milestone 2: AI Workspace

M2 implements a compatible Chat Completions adapter, explicit provider capabilities, asynchronous conversational runs, saved drafts, constrained logical file tools, authorization events, usage/cost-estimate accounting, cancellation/recovery, and participant trace inspection. No credentials are required for Mock or local HTTP fixture tests. See [M2 validation](validation-m2.md) for executed checks and unverified live-provider behavior.

## Milestone 3: recommended priorities

1. **Identity and access:** real authentication, administrator/author/participant permissions, renewable sessions, account recovery, TLS, per-user/global quotas and rate limits. Complete a deployment security review before public hosting.
2. **Durable scheduling:** worker ownership/leases, queued runs, per-attempt provenance, crash reconciliation, and a cancellation protocol before using multiple API processes. Preserve idempotency and do not silently retry possibly billed calls.
3. **Trace and data lifecycle:** private vulnerability reporting, retention/deletion/export, access audit, encrypted storage/secrets management, configurable redaction, and process-oriented evaluation with validated evidence references.
4. **Provider conformance:** opt-in real endpoint tests, model-specific compatibility, streaming if needed, usage reconciliation, and pricing versions. Fixture success proves protocol handling, not every provider/model's behavior.
5. **Author workflows and judging:** authenticated version publishing, protected private resources, richer rubrics and reproducible evaluator metadata. Design and prove an isolated worker boundary before accepting external evaluators or contestant code; logical files are not a sandbox.

Distributed judges, contests, leaderboards, billing, generic browser automation, and unrestricted terminal access remain outside M2. Add infrastructure only when the product needs it.

## Public repository versus public service

Publishing Apache-2.0 source does not make the application safe to expose publicly. Preserve contributor copyright, bundled third-party notices, and the project's independent personal identity. Review source and generated artifacts for secrets before publishing. Keep current deployments on localhost until authentication, abuse controls, data handling, and any necessary execution isolation have been implemented and reviewed.
