# Resource quotas and admission

M4 adds server-side account, problem and system policy budgets. These are local-development controls, not a billing guarantee or complete Sybil/abuse defense. Existing manifest-level message, model, tool, file, response and time bounds remain enforced. Creating a new session does not reset an account's daily budget.

## Admission and storage capacity

The API authenticates and locks the account before mutating its session. It then locks the singleton admission row to check account concurrency and shared queue/storage capacity. The same transaction creates the session or pending job. A failed transaction reserves nothing. A repeated successful run request UUID returns the existing run before admission checks; it does not consume another slot.

| Setting (`PRAXIOJ_` prefix) | Default | Policy |
| --- | --- | --- |
| `ACCOUNT_ACTIVE_SESSIONS` | 10 | Active, unexpired solve sessions per account |
| `ACCOUNT_RETAINED_SESSIONS` / `SYSTEM_RETAINED_SESSIONS` | 100 / 10000 | All retained sessions, including closed ones |
| `ACCOUNT_ACTIVE_RUNS` | 2 | Queued plus running jobs per account |
| `QUEUE_MAX_PENDING` | 100 | Shared pending jobs; excess admission returns 429 |
| `WORKER_MAX_RUNNING` | 4 | Shared running jobs; claim transactions serialize the capacity check |
| `SESSION_ARTIFACT_MAX_BYTES` | 1048576 | Further caps the problem's logical workspace allocation |
| `ACCOUNT_ARTIFACT_CAPACITY_BYTES` / `SYSTEM_ARTIFACT_CAPACITY_BYTES` | 16777216 / 268435456 | Sum of reserved per-session workspace capacities |
| `SESSION_TRACE_MAX_BYTES` / `SESSION_TRACE_MAX_EVENTS` | 8388608 / 2000 | Regular logical trace payload capacity per session |
| `ACCOUNT_TRACE_CAPACITY_BYTES` / `SYSTEM_TRACE_CAPACITY_BYTES` | 268435456 / 2147483648 | Reserved trace capacities including fixed finalization space |

Capacity reservation deliberately uses the maximum possible allocation, not only current file size. Repeated file replacement cannot overrun a session's allocation. Workspace capacity remains reserved until the session/account is erased; Trace capacity is released after physical retention purge. Ended sessions still retain data and capacity. These byte counts concern logical payloads and do not include PostgreSQL pages, indexes, WAL, filesystem overhead or backups. They are not disk-space monitoring.

Every new trace event is measured as compact UTF-8 JSON before persistence. Regular appends stop at the snapshotted byte/event cap. Finalization has a separate **4 MiB / 128-event** reserve: a provider response has at most 32 pending tool calls and a 1 MiB wire bound, so cancellation can preserve denied requests/results and terminal events without truncating the original arguments. Once regular capacity is exhausted, new runs/calls are denied; submission or session closure remains possible. File mutation and its events commit together or both roll back. A completed provider's usage metadata uses finalization capacity, so exhausting ordinary trace space does not discard a received usage report.

Migration 0007 preserves existing history. It records a fixed historical byte/sequence baseline, using conservative stored JSON byte length. Older traces above a new cap can consume only bounded finalization space beyond that baseline; normal work is blocked. The baseline never grows after initialization. Storage admission includes this larger historical reservation. New records use compact logical byte accounting. A database administrator remains trusted and can alter policy/counters; this is an application boundary, not hostile-database isolation.

## Daily attempts and uncertain usage

Budgets reset at UTC midnight. Account, problem (across immutable versions), and system rows are locked in a deterministic order. Provider attempt creation, its policy reservation, and start event share one transaction before network I/O. Multiple API/worker processes cannot reserve the same remaining call allowance twice. No database lock remains held during the provider request.

| Scope | `*_DAILY_MODEL_CALLS` | `*_DAILY_TOOL_CALLS` | `*_DAILY_TOKEN_ALLOWANCE` |
| --- | --- | --- | --- |
| `ACCOUNT` | 200 | 400 | 2000000 |
| `PROBLEM` | 2000 | 4000 | 20000000 |
| `SYSTEM` | 10000 | 20000 | 100000000 |

Before dispatch, a call reserves the larger of `PRAXIOJ_CALL_TOKEN_RESERVATION` (16384 by default) and the UTF-8 input bytes plus configured output allowance. These are **policy reservation units**, not measured tokens or estimated invoices. Their practical conservatism depends on the provider/tokenizer; they cannot establish a universal hard billing or token cap.

- A complete non-estimated usage report replaces the reservation with its reported input/output counts.
- Missing, partial, estimated (including Mock), cancelled or lost results retain their full reservation for that UTC budget window. Their underlying `ProviderCall` usage stays nullable/estimated. The daily public view separately labels exact reports, uncertain calls and reserved policy units.
- A provider reporting more actual usage than reserved is recorded truthfully; later calls are blocked if the allowance is exhausted. One completed call may exceed a pre-dispatch estimate. Provider-side spending controls remain necessary for paid integrations.
- Started attempts remain consumed after cancellation/failure. Cancelling a **pending** job frees concurrency without creating provider usage. Cancellation never claims to undo a remote charge.
- Tool attempts, including denied tool policy requests, consume the daily tool allowance. A quota rejection does not execute or mutate a file.

Old terminal reservations and daily buckets are removed in bounded maintenance batches after two days. Windows still referenced by an unsettled reservation are retained, preventing late recovery from recreating counters and subtracting into negative balances. Deleting an account removes its own usage rows; aggregate problem/system counters remain anonymous until this short retention expires.

## Public and privileged views

`GET /api/account/usage` reports only the authenticated account's active/retained sessions, active jobs, capacity reservations, daily observed usage and policy limits. `GET /api/author/problems/{id}/usage` permits the owning author or administrator to see aggregate problem usage without participant IDs or work content. `GET /api/admin/operations` exposes internal queue/worker information only after backend administrator authorization.

Admission rejection returns HTTP 429, `Retry-After` and `X-RateLimit-Policy`. A running job that reaches a budget becomes `FAILED` with a safe policy code, preserves prior work and allows explicit later submission/retry. Retry-after for active/capacity limits is advisory: time alone does not free retained data or a still-running slot.

See [worker operations](persistent-jobs.md), [authentication](../development/authentication.md), and [data retention](trace-retention.md). No Redis, broker or monitoring platform was added.
