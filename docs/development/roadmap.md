# Roadmap

## Completed foundation

M1 provides the independent Problem SDK, Runtime/Mock contracts, trace/evaluation interfaces, PostgreSQL API and original sample. M2 adds compatible providers, bounded logical tools, persistent conversation/drafts, usage, cancellation and the Workspace UI. Their manifest digests and core regression scenarios remain supported.

M3 adds Argon2id accounts and server sessions, CSRF and backend roles, immutable author publishing, a PostgreSQL job repository and separate workers, ownership leases/fencing, trace integrity/retention and deterministic evidence criteria. It preserves Mock and local fixture testing without credentials. See [M3 validation](validation-m3.md) and the [GitHub preflight report](preflight-validation.md) for actual checks and remaining limits.

## Milestone 4 recommendations

1. Conduct a deployment-focused security review before any public hosting: TLS/proxy trust, registration abuse controls, global/account quotas, request budgets, monitoring and incident procedures. Add MFA, account recovery and verified identities where the product needs them.
2. Expand worker operations: deployment migrations separated from API startup, queue fairness, worker health/metrics, maintenance scheduling independent of worker availability, operator recovery tools and long-running load/fault tests. Preserve explicit uncertain provider outcomes instead of transparent retries.
3. Mature data governance: participant export/deletion UI, backup lifecycle, field-level minimization, encrypted storage/secret management, audited author review UX and externally anchored or signed evidence when justified. Distinguish retained evaluation results from expired underlying evidence.
4. Extend author evaluation contracts only with observable, validated evidence. Build a separately isolated execution boundary before accepting external Python evaluators or contestant code. Current workers and containers do not provide that isolation.
5. Add opt-in real provider/model conformance, usage reconciliation and price-version handling. Fixture success proves protocol behavior, not model quality, universal provider compatibility or exact billing. Streaming can follow a concrete usability need.

Contests, billing, leaderboards, general browser automation, unrestricted terminal access and distributed untrusted Judge workers remain separate future scopes. PraxiOJ remains an independent hobby project under Apache-2.0; contributor and third-party rights remain intact.
