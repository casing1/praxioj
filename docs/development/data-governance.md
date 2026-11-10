# Account export and deletion

These controls apply to the localhost development platform. They do not establish a legal retention policy, verified identity or a production privacy certification.

## Confirming sensitive actions

An authenticated client first sends `POST /api/auth/reauthenticate` with its current password, allowed Origin and CSRF header. Password confirmation belongs to that particular server session and expires after the configured short interval (default five minutes). Logging in alone does not count as this confirmation. Export and deletion require it in addition to ordinary account authentication and CSRF authorization. Passwords and login tokens are never included in exports or audit details.

## Downloading your own records

`POST /api/auth/export` accepts `{ "limit": 25, "after_session_id": null }`. The limit is 1–100. The response is a JSON attachment containing the profile, owner-only usage counters, solve sessions, messages, logical files, submissions, evaluations, AI runs, provider usage and available Trace events. `next_cursor` is either the last included session ID or null. Pass the returned cursor to request the next page. The account UI exposes page downloads rather than silently omitting remaining sessions.

Each page holds the account and selected solve-session locks while reading. Ordering is stable by session ID. A page is a consistent bounded read; several pages are not a single database-wide snapshot. New UUIDs created between pages can fall before a cursor. Stop creating/changing work while collecting a complete multi-page archive, or repeat the export after work ends. Conversations/artifacts may exist after their Trace expires; they remain separate account data.

The export has an encoded size limit of 16 MiB by default (`PRAXIOJ_EXPORT_MAX_BYTES`, maximum 64 MiB) and 10,000 total records (`PRAXIOJ_EXPORT_MAX_ROWS`, maximum 100,000). An oversized page fails with HTTP 413 and no export audit success. Request fewer sessions. A single session that cannot fit requires a separately reviewed operator export procedure; the endpoint never silently truncates that session. Queries use owner-scoped session IDs, bounded result counts and batched reads, without a child-table query for each session.

Exports omit authentication/CSRF/password hashes, session tokens, provider credentials/URLs, internal worker ownership and private evaluator configuration. They retain content digests and original Trace hashes/checkpoints, which are evidence metadata, not login credentials. An export is not an integrity certificate: use the existing session integrity endpoint to check the chain. Expired Trace payloads are omitted, and related sessions/evaluations explicitly report `trace_availability=expired`.

Downloaded files contain private account content. Browser downloads are outside server retention control. Store them privately, remove copies when no longer needed and never commit them. Responses have `Cache-Control: no-store`; the server does not create an export file or durable download token.

## Erasing an account

`POST /api/auth/delete` requires the same recent password confirmation. Cancel queued/running AI work first; an active run produces HTTP 409. Deletion holds the account lock and ordered session locks, removes private solve records, files, messages, provider records/reservations, jobs, submissions, evaluations, Trace payloads, owner quota counters and every login session in one transaction. A failure rolls back the whole operation, so an authenticated client can retry. After success, repeated HTTP requests receive 401 because the credential has been revoked; the internal erasure operation is idempotent and does not duplicate its audit record.

An inactive pseudonymous user tombstone remains for immutable public problem ownership. Previously published author problems and anonymous problem/system usage aggregates are retained; deletion does not transfer author ownership to a newly registered username. A minimal `account_erased` audit contains pseudonymous ID and deletion counts, never the erased content. The configured audit retention remains capped at 90 days.

Deletion does **not** retroactively rewrite offline backups or browser downloads. See [backup and restore](backup-restore.md) for the quarantined restore barrier, bounded backup retention and the required separate deletion-ledger review. No automatic promotion of restored data is supported.

## Optimization review

Before M4, account deletion issued a child-delete sequence per session. An in-memory SQLite fixture with one synthetic Trace per session measured 14/95/455 SQL executions for 1/10/50 sessions. The M4 implementation retains the same owner/session lock ordering and atomic transaction but uses one deletion per table and a subquery restricted to the owner. Repeating the same workload measured **15/15/15** executions: one additional deletion for the new private quota table, but 96.7% fewer executions at 50 sessions. Run `.venv/bin/python scripts/measure-erasure.py` to reproduce the current measurement. The test suite guards constant query count and transaction rollback. This is a SQL round-trip reduction, not a claim about production latency; observed single-run in-memory wall times were noisy and are not used to claim a speedup. Exports are new functionality and have no comparable M3 performance baseline.
