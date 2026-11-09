# Trace event contract 1.0, additive M2 fields

`TraceEnvelope` contains unique `event_id`, owning `session_id`, positive session-local `sequence_number`, `event_type`, UTC `timestamp`, redacted JSON `payload`, `schema_version="1.0"`, `source`, `actor`, and related `resource_ids`. M2 adds optional `correlation_id` and `parent_event_id`. Run, provider-call, tool-call, message, artifact, submission, and evaluation IDs link related observations.

Events cover `SESSION_STARTED`, `USER_MESSAGE`, `ASSISTANT_MESSAGE`, `PROVIDER_CALL_STARTED`, `PROVIDER_CALL_COMPLETED`, `TOOL_CALL_REQUESTED`, `TOOL_CALL_AUTHORIZED`, `TOOL_CALL_COMPLETED`, `ARTIFACT_UPDATED`, `SESSION_STATE_CHANGED`, `SUBMISSION_CREATED`, `EVALUATION_COMPLETED`, `SESSION_ENDED`, and `ERROR`. Authorization can be denied; a tool request is not evidence of successful execution. Runtime failures and cancellation have explicit outcomes.

The legacy synchronous Mock route preserves its M1 sequence: start, user, assistant, final artifact, submission, evaluation, end. M2 asynchronous runs additionally record state changes and provider/tool events in actual committed order. Logical file writes emit artifact revisions/hashes. Draft saving is explicit persistence, not keystroke tracking. Sessions may end without submission.

## Ordering and duplicates

Short PostgreSQL transactions lock the session row and allocate contiguous sequence numbers. `(session_id, sequence_number)` and event IDs are unique. Read by sequence, not timestamp; no cross-session total order is promised. Provider network waits occur outside these transactions. Related state/data and corresponding events commit together.

`POST /sessions/{id}/runs` binds a request UUID to session/content. Identical retries return the existing run without replaying provider calls or events; conflicting reuse returns 409. Duplicate upstream tool-call IDs are rejected before re-execution. File updates and tool results commit together. After a crash, interrupted calls/runs are marked failed with uncertain usage; there is no silent remote replay or guarantee of exactly-once provider billing. The old `/messages` route has no request UUID, so clients must not automatically retry it.

The standalone in-memory collector treats identical event-ID retries as no-ops and rejects conflicting duplicates/gaps. It is not durable or thread-safe storage. The API creates only server events and exposes no participant-controlled event ingestion. External ingestion remains deferred.

## Public evidence and internal diagnostics

Only the session owner can retrieve its trace. The evaluator receives only the authorized trace supplied by its caller, not access to the database. Public data contains safe statuses, identifiers, selected content, limits, and nullable usage. Provider credentials, endpoint configuration, HTTP headers, raw error bodies, and internal exceptions are excluded. The separate internal runtime logger records safe operation/error identifiers; it is not exposed by a participant API and does not log raw prompts or provider bodies.

Known secret keys/token patterns and the configured provider credential are scrubbed before new persisted participant/provider text and trace payloads. This is best-effort filtering, not complete secret/PII detection or retroactive cleaning of old rows. Do not enter secrets. Provider errors use stable safe codes; cancellation may leave usage unknown. Resource hashes and model/settings snapshots aid auditing, but traces do not reveal private model reasoning or guarantee deterministic replay of real AI responses.
