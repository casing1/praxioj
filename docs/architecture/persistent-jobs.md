# Persistent jobs and worker lifecycle

M3 separates request handling from AI execution. The API validates the authenticated owner, problem policy and resource budget, then commits the user message, run, `PENDING` job and Trace events in one transaction. It returns HTTP 202 without launching an API-process task. A separate process runs `python -m praxioj_api.worker`; `--once` is available for controlled integration tests and operator runs. No Redis, message broker or external evaluator is introduced.

## State and ownership

| Job state | Meaning |
| --- | --- |
| `PENDING` | Persisted and eligible at `available_at`; no provider request has started |
| `RUNNING` | Acquired by one worker with a random claim token, generation counter, lease and absolute deadline |
| `COMPLETED` | Runtime and tool loop committed successfully |
| `FAILED` | Safe error retained, including timeout, provider failure or expired ownership |
| `CANCELLED` | Owner cancellation committed and the worker's authority revoked |

Existing WorkspaceRun API states remain `queued`, `running`, `completed`, `failed` and `cancelled`. The job projection adds execution/recovery status without exposing claim tokens or worker identifiers. The same session/request ID returns the existing run; reusing it with different input returns 409. Creating another request after a terminal failure is an explicit new action, not a replay of the old request.

PostgreSQL row locks serialize mutations in **session → run → job** order. Acquisition first locks an eligible session with `FOR UPDATE OF solve_sessions SKIP LOCKED`, then locks and rechecks the specific run/job before claiming. Independent workers can progress on other sessions without acquiring the same job. PostgreSQL documents `SKIP LOCKED` as suitable for queue consumers; it is not a general consistent-read mechanism. See the [PostgreSQL SELECT reference](https://www.postgresql.org/docs/18/sql-select.html).

Every executor persistence boundary revalidates the worker ID, random claim token, monotonic fence, job state, active session run, unexpired lease and absolute deadline while holding these locks. This includes provider-attempt creation, provider-result accounting, assistant messages, tool dispatch/artifact mutation and finalization. No database transaction or connection spans a provider await. PostgreSQL's clock is used for cross-process lease decisions; SQLite is only a fast test backend and does not establish concurrency guarantees.

## Heartbeat, cancellation and recovery

Defaults are a 15-second lease, 3-second heartbeat and 0.5-second idle poll. `PRAXIOJ_WORKER_LEASE_SECONDS`, `PRAXIOJ_WORKER_HEARTBEAT_SECONDS` and `PRAXIOJ_WORKER_POLL_SECONDS` configure bounded intervals. A heartbeat must be shorter than half the lease, cannot revive an expired claim, and never extends beyond the job's absolute deadline. The deadline is derived from the problem's bounded run limit.

Cancellation commits the terminal run/job and Trace records, clears only that run's active-session reference and revokes its claim before returning. A late response cannot update the cancelled run, append tool results, or clear a newer active run. The worker observes cancellation through lease validation/heartbeat and cancels its local await. This does **not** guarantee that the provider stopped or avoided charging.

Every worker poll reconciles expired `RUNNING` jobs. Expired ownership becomes `FAILED` with `lease_expired`; an absolute deadline becomes `job_timeout`. Started calls receive unknown token counts and safe failure metadata. Pending tool requests receive explicit non-executed results so conversation context remains well-formed. Reconciliation, run state and Trace writes share a transaction. Repeated reconciliation does not append duplicate terminal events.

A queued run whose session retention period has expired fails before contacting a provider. Workers also run a bounded retention batch on startup and approximately once per minute; live runs are reconciled before their traces can be purged. Retention and job recovery use separate short transactions.

An expired job is **never automatically retried**. Its provider may have received the request or produced effects before the response was saved. `external_effect_uncertain` records an unfinished provider attempt, and usage remains incomplete. A stale worker cannot reclaim the old generation or overwrite recovery. Graceful termination attempts a `worker_stopped` failure; a killed process is reconciled after lease expiry by another/restarted worker. Recovery requires an available database and a worker or the M4 standalone maintenance command; stopping every worker does not create a hidden scheduler in the API.

## Migration and deployment boundary

`0004_jobs` adds the durable queue. M2 unfinished runs are marked `legacy_run_quarantined`, unfinished usage stays unknown, and their active-run references are cleared. Safe migration error/state events are appended while historical envelopes remain intact. They are not automatically converted into runnable authenticated work. Historical completed runs remain available to an authorized operator under the legacy-data policy.

Run API and worker processes with the same server-side provider configuration. Participants cannot supply a provider URL or credential. Existing Mock and compatible providers, logical file tools and budgets are retained. M3 supports multiple workers contending through PostgreSQL; this is not a distributed untrusted-code judge or secure execution sandbox. Tool execution remains restricted to trusted built-in logical-file handlers.

Provider calls cannot be guaranteed exactly once. Fencing protects committed platform state, while external-side-effect uncertainty remains explicit. Database outage, stopped workers, clock-service failure, and operator configuration changes remain operational dependencies. M4 adds bounded admission, FIFO policy and minimal operational views below. Production monitoring, controlled credential rollout and external usage reconciliation still need further work.

## Verification

`tests/api/test_jobs.py` covers API-only persistence/restart, idempotency, mock tool/evaluation flow, heartbeat extension, timeout, cancellation, stale-token/fence rejection, unknown usage, safe failure logging and scheduling. PostgreSQL-only cases exercise competing row-lock claims, skip-locked progress, two separate worker processes, local HTTP tool calling through submission/evaluation, and a killed process during a local HTTP request followed by expired-lease recovery without replay. These tests never use paid-provider credentials.

Existing M2 API regressions use an explicit `worker_thread(app)` test harness. Application startup has no test-only auto-execution switch or authentication bypass. Local HTTP fixtures demonstrate protocol/lifecycle behavior, not commercial model reasoning quality.

## M4 operations and admission

The API now enforces [account/system admission and daily quotas](resource-quotas.md). A shared admission row serializes queue depth and running-capacity checks. Each worker process executes one job at a time; `PRAXIOJ_WORKER_MAX_RUNNING` bounds the number of running jobs across processes. `PRAXIOJ_QUEUE_MAX_PENDING` rejects excess submissions before message/job creation. Slots are derived from authoritative job states rather than separate counters requiring crash refunds.

Scheduling is FIFO by `(available_at, run_id)` among eligible unlocked sessions. `SKIP LOCKED` permits progress around a busy session. The account queued-plus-running cap prevents one account filling the whole default queue; it is not weighted fair scheduling or a latency guarantee. A permanently locked row, unavailable database or stopped workers can still prevent progress. Oldest pending age is observable; no hidden automatic retry or priority escalation occurs.

Workers record a random instance ID, start/heartbeat times, `IDLE`, `BUSY`, `DRAINING` and `STOPPED` states, current job ID and bounded operational counters. No hostname, PID, provider credential or conversation appears in this registry. Administrator views derive `STALE` when a heartbeat is older than twice the lease. Idle registry writes occur at the heartbeat interval, not every queue poll. Job heartbeats continue during drain. Compose allows 15 seconds before forced termination; if increasing the drain setting, also increase `stop_grace_period` to cover drain plus bounded persistence cleanup.

SIGINT/SIGTERM stop new claims and allow the current execution to finish for up to `PRAXIOJ_WORKER_SHUTDOWN_SECONDS` (default 5, allowed 0–30). After the drain expires, cancellation attempts a fenced terminal transition with explicit unknown external effects. Database operations remain subject to database connection/statement timeouts; this is not an unconditional process-termination deadline. Abrupt kills or persistence outages retain durable ownership records until lease recovery; old workers still cannot write after fencing.

`python -m praxioj_api.maintenance` runs one bounded, restartable maintenance pass independently of the AI worker. It recovers expired running leases, fails expired pending sessions without executing them, purges eligible traces, and cleans expired authentication records, old quota records and worker records older than seven days. It emits safe aggregate counts and an audit event. Recovery and cleanup use separate short transactions, so interruption can commit a prefix; re-execution safely completes remaining work. Workers also invoke this pass on startup and about once a minute. Running every worker is no longer necessary if the operator schedules this command, but no built-in external scheduler is implied.

Restored test databases have a quarantine marker. API startup, worker startup/iterations, direct job claims and maintenance entry points reject that marker. Backup validation cannot accidentally turn copied pending jobs into new model requests.

### Minimal observability

`GET /api/admin/operations` returns queue depth, oldest pending age, active/failed/completed counts, configured limits, live worker capacity and registry states. Retained worker counters expose completed/failed counts, mean wait/run duration and recovery counts. They are operational samples: a crash can omit a registry completion update, while durable job rows remain authoritative. Registry retention is seven days; this is not indefinite billing/history storage.

A payload-free JSON `api_request` log contains only a fixed route category, normalized method, response status and duration. It omits URLs, query strings, IPs, credentials and user/model content. API request and 429/error counters are explicitly **process-local since startup**. A collector can aggregate logs later; no external monitoring system is required or configured. Maintenance emits aggregate deletion/recovery counts. Ordinary participant run projections continue to omit worker IDs and claim tokens.
