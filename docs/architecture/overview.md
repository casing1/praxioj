# Architecture overview

PraxiOJ supplies infrastructure for evaluating observable human–AI work. Authors choose tasks, permitted assistance and criteria. Framework and Platform remain independent: the installable Framework never imports FastAPI, SQLAlchemy or browser code.

```mermaid
flowchart LR
    Browser[Authenticated React workspace] --> API[FastAPI API]
    API --> DB[(PostgreSQL accounts, jobs, traces)]
    Worker[Separate worker process] --> DB
    Worker --> Runtime[Framework AI Runtime]
    Runtime --> Mock[Offline Mock]
    Runtime --> Provider[Server-configured compatible endpoint]
    Worker --> Tools[Authorized logical file tools]
    Tools --> DB
    API --> Judge[Trusted Framework evaluator]
    Python[Independent Python caller] --> Judge
```

## Boundaries and lifecycle

1. A participant registers or signs in. Argon2id verifies passwords; random HttpOnly session cookies refer to hashed server-side records with fixed expiry. CSRF headers protect authenticated writes. Registration grants only participant status.
2. An author publishes a strict declarative manifest through an authorized API. A trusted local operator can register examples. Problem versions are immutable and sessions pin a version, profile, model policy and retention deadline.
3. The API atomically stores the user message, Run, PENDING Job and trace. A request UUID identifies a retry; different content under the same UUID conflicts.
4. A worker claims a job with PostgreSQL locks, assigns a lease/token/fence and commits before provider I/O. Heartbeats renew the lease. Every result/tool/terminal transaction rechecks ownership. The API has no background execution task.
5. Tool requests are separately validated and authorized before operating on session-local database text files. Nothing executes shell commands, participant Python, containers or general network tools.
6. Persistent cancellation revokes ownership. An expired lease becomes a failed job with explicit uncertainty; the remote call is not silently replayed. Pending work survives API/worker restart. Recovery requires a running worker.
7. Submission snapshots text and artifacts, collects authorized trace/usage, and invokes a trusted deterministic Framework evaluator. Final and process criteria can be composed independently. Scores cite observable evidence; they do not establish human understanding.
8. Trace v1.1 is append-oriented with a SHA-256 chain and a stored session checkpoint. Review reads lock the session while comparing events and checkpoint. Legacy traces remain unverified. Retention removes expired trace payloads and records a minimal separate deletion audit.

## Persistence

```mermaid
erDiagram
    User ||--o{ AuthSession : authenticates
    User ||--o{ Problem : authors
    User ||--o{ SolveSession : owns
    Problem ||--|{ ProblemVersion : versions
    ProblemVersion ||--o{ SolveSession : pins
    SolveSession ||--o{ ConversationMessage : records
    SolveSession ||--o{ TraceEvent : records
    SolveSession ||--o{ WorkspaceRun : requests
    WorkspaceRun ||--o| Job : schedules
    WorkspaceRun ||--o{ ProviderCall : attempts
    SolveSession ||--o{ WorkspaceFile : isolates
    SolveSession ||--o| Submission : finalizes
    Submission ||--|| Evaluation : evaluates
```

`AuthRateLimit` stores bounded hashed login buckets; `AuditRecord` stores operational metadata separately from participant events. Migrations 0003–0005 add accounts, jobs, and retention/checkpoints. Old browser identities retain their data but cannot log in, claim a new account, or become administrators. Old unfinished runs are quarantined, not replayed. No migration rehashes old evidence as proof of its original integrity.

## Compatibility and limits

Original M1/M2 manifest digests and Mock/provider contracts remain supported. Existing Run statuses remain `queued/running/completed/failed/cancelled`; the added Job projection exposes `PENDING/RUNNING/COMPLETED/FAILED/CANCELLED`. The legacy synchronous Mock/no-tool `/messages` route remains authenticated and bounded. Evaluation remains synchronous because only small trusted deterministic built-ins execute in process.

PostgreSQL provides durable transactions and row locks. SQLite is a unit-test convenience and does not establish worker concurrency safety. There is no additional broker. Multiple worker processes are tested; this is not a distributed untrusted-code Judge or a production operations system. The network stack stays on localhost. Full public deployment hardening, account recovery/MFA, global abuse quotas, encrypted secrets/storage, externally anchored integrity and an execution sandbox remain future work.

See [authentication](../development/authentication.md), [worker lifecycle](persistent-jobs.md), [retention](trace-retention.md), [evaluation](../specifications/evaluation-contract.md), and [security boundaries](../../SECURITY.md).
