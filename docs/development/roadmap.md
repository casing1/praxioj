# Roadmap

[한국어](../i18n/ko/development/roadmap.md)

## Completed foundation

M1 provides the independent Problem SDK, Runtime/Mock contracts, trace/evaluation interfaces, PostgreSQL API and original sample. M2 adds compatible providers, bounded logical tools, persistent conversation/drafts, usage, cancellation and the Workspace UI. Their manifest digests and core regression scenarios remain supported.

M3 adds Argon2id accounts and server sessions, CSRF and backend roles, immutable author publishing, a PostgreSQL job repository and separate workers, ownership leases/fencing, trace integrity/retention and deterministic evidence criteria. It preserves Mock and local fixture testing without credentials. See [M3 validation](validation-m3.md) and the [GitHub preflight report](preflight-validation.md) for actual checks and remaining limits.

## Milestone 4 operational foundation

M4 implements shared authentication/API throttles, session and password management, confirmation-protected export/deletion, account/problem/system quotas, bounded trace/artifact capacity, worker registry/metrics/graceful drain, independent maintenance and synthetic PostgreSQL backup/restore validation. Restore databases are blocked from API/worker use. It documents a future isolated execution architecture without enabling arbitrary code. See [M4 validation and optimization evidence](validation-m4.md).

## Milestone 5 execution foundation

M5 implements strict versioned execution contracts, an opt-in synthetic Execution Broker with separate persistent Job/Attempt state, opaque capability validation, lease/fencing/replay protection, bounded result/artifact validation and a synthetic evaluation bridge. Default backend selection remains unavailable. Administrator-owned fixed fixtures exercise the complete local HTTP path without enabling code execution or changing original grades. See [M5 validation](validation-m5.md), [execution protocol](../specifications/execution-protocol.md), and [Broker architecture](../architecture/execution-broker.md).

## M6-A — lifecycle and remote Runner foundation

[M6-A Milestone 1](https://github.com/casing1/praxioj/milestone/1) is complete: issue-first governance, DB-acknowledged heartbeat/fencing, bounded terminal Judge retention/quota recovery, a strict synthetic Runner communication boundary and non-executing Linux preflight. [Governance PR #28](https://github.com/casing1/praxioj/pull/28) merged before [feature PR #29](https://github.com/casing1/praxioj/pull/29); [final validation PR #30](https://github.com/casing1/praxioj/pull/30) delivered the evidence and closed Issue #22/M6-A. Full regression, independent source review and protected checks passed; [M6-A validation](validation-m6a.md) records exact results and remaining limits.

The Judge stays unavailable by default; explicit Mock retains administrator-owned fixed fixtures and synthetic provenance. The Runner channel is in-memory protocol testing, with no public endpoint, production peer authentication or hostile-code execution. Lifecycle and Runner share one authoritative renewal/cancellation contract and were delivered together; final milestone validation/documentation was delivered in a separate PR. New major stages use actual GitHub Milestones/Issues under the [engineering workflow](engineering-workflow.md).

## M6-B and later prerequisites

[M6-B — Isolated Linux Runner Validation](https://github.com/casing1/praxioj/milestone/2) and planning [Issues #23–#27](https://github.com/casing1/praxioj/issues/23) remain open. The [Issue #23 preflight](linux-runner-preflight.md) now records local read-only observations, a pinned Firecracker/gVisor comparison and integration requirements. No dedicated Linux host is available: operational runtime selection is Blocked, both candidates are Provisional, and actual host acceptance is not satisfied. None of the OS-isolation gates is implemented or established by synthetic tests; see the [Issue #23 validation](validation-issue23.md).

1. Prepare a dedicated disposable Linux execution host/VM and choose a supported kernel/runtime platform (with KVM where required) before implementing any hostile-code runner. Evaluate Firecracker first where KVM is available, with gVisor as an independently validated alternative. Record runtime/image provenance, privilege scope, resource overhead and language compatibility; fail closed on unsupported hosts. See the [isolation proposal](../architecture/sandbox-architecture.md).
2. Select and validate actual authenticated remote transport and identity provisioning before extending the M6-A in-memory channel to another host. Complete the pending host/network/filesystem/process/cleanup acceptance gates; versioned synthetic protocol tests do not establish OS confinement or operational network authentication.
3. Conduct a deployment-focused security review before any public hosting: verified TLS/proxy trust, multi-node load/abuse tests, identity recovery/MFA, incident response and secret management. Existing bounded localhost controls are not production certification.
4. Expand worker operations: separate deployment migrations, schedule independent maintenance, collect structured metrics centrally if scale warrants it, and exercise sustained load, DB failover and recovery. Preserve explicit uncertain provider outcomes instead of transparent retries.
5. Mature data governance: encrypted off-host backups with tested key recovery, durable external erasure-ledger replication and reviewed restore promotion, backup lifecycle automation, audited author review UX and externally anchored evidence when justified. Current restore quarantine intentionally blocks promotion.
6. Extend author evaluation contracts only with observable, validated evidence. Build a separately isolated execution boundary before accepting external Python evaluators or contestant code. Current workers and containers do not provide that isolation.
7. Add opt-in real provider/model conformance, usage reconciliation and price-version handling. Fixture success proves protocol behavior, not model quality, universal provider compatibility or exact billing. Streaming can follow a concrete usability need.

Contests, billing, leaderboards, general browser automation, unrestricted terminal access and distributed untrusted Judge workers remain separate future scopes. PraxiOJ remains an independent hobby project under Apache-2.0; contributor and third-party rights remain intact.
