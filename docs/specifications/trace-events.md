# Trace events and integrity

`TraceEnvelope` contains a unique `event_id`, owning `session_id`, positive session-local `sequence_number`, event type, timestamp, redacted JSON payload, schema version, source, actor, related resource IDs, and optional correlation/parent event IDs. Run, provider-call, tool-call, message, artifact, submission, and evaluation IDs identify related observations.

Legacy schema `1.0` remains readable. Schema `1.1` adds `previous_hash` and `event_hash`. New records are redacted before they are sealed; a later projection that changes the envelope is not the original hash-verifiable record.

Events cover session start/end/state changes, user/assistant messages, provider start/completion, tool request/authorization/completion, artifact changes, submission creation, evaluation completion, errors, and `AUTHOR_EVENT`. The latter is a trusted recorder extension with a bounded named criterion, not participant-controlled event ingestion. A tool request is not evidence of permission or successful execution.

## Ordering and duplicate handling

Platform transactions lock the solve-session row and allocate contiguous sequence numbers. The database enforces unique event IDs and `(session_id, sequence_number)`. Read by sequence, not timestamp; no global cross-session order is promised. Related mutations and events commit together. Provider waits occur outside those transactions.

Run creation binds a request UUID to session and content. Identical retries return the existing run; conflicting reuse returns 409. Duplicate tool-call IDs in one run are rejected before execution. A provider can reuse a resolved ID in a different run, so evidence matching includes the run and parent event IDs. File updates and tool results commit together.

The standalone in-memory collector retains its M1/M2 semantics: exact event-ID retries are no-ops, conflicting duplicates and gaps fail, and reads return copies. It is neither durable nor thread-safe. The Platform exposes no arbitrary participant event append/update endpoint.

## Hash contract

`seal_trace_event(event, previous_hash=None)` returns a detached schema-1.1 envelope. `compute_event_hash(event)` serializes the validated envelope in Pydantic JSON form, excludes only `event_hash`, sorts object keys, uses compact separators and UTF-8, rejects non-finite numbers, and computes SHA-256. The predecessor, schema version, identity, sequence, timestamp, actor, resource references, and payload are all covered.

`verify_trace_chain(events, session_id=None, anchor_hash=None, start_sequence=1, expected_head=None, expected_next_sequence=None)` returns a structured status:

- `verified`: identities, sequences, session association, predecessor links, and content hashes agree.
- `unverified`: legacy/unhashed records are present; they are not retroactively certified.
- `invalid`: an envelope, identity, order, relationship, checksum, or supplied checkpoint disagrees.
- `empty`: no events exist and supplied checkpoints permit an empty sequence.

The result includes a safe reason, event count, and final hash where applicable. A trusted `expected_head` and `expected_next_sequence` detect a removed suffix; checking only the remaining events cannot do so. An explicit trusted predecessor anchor and starting sequence can validate a retained suffix. Legacy rows are not silently backfilled as if they were originally sealed.

This is an integrity check, **not a tamper-proof archive**. A writer able to alter all events and their database checkpoints can recompute the chain. The mechanism does not provide signatures, external timestamping, a protected transparency log, or proof of real-world actions. Database authorization, append-only application behavior, access auditing, and backups remain separate controls.

## Evaluation and retention

The evidence rubric consumes authorized server events before the matching submission boundary. It checks linked tool authorization/results and explicit event criteria; it does not treat generated text as system instructions or infer private model reasoning. See [the evaluation contract](evaluation-contract.md).

`ProblemManifest.trace_retention_days` is optional and bounded to 1–90 days; `None` delegates to operator policy. The Platform caps author policy with its configured bound, records the effective expiry, and performs bounded cleanup. Expiration removes trace data and records a deletion audit/checkpoint according to Platform policy. A retained evaluation may outlive its trace but must disclose unavailable evidence. A retained hash alone is not the deleted content or a claim that it can be rechecked.

## Access and diagnostic boundaries

The Platform authorizes participant ownership, author access to evaluation evidence for managed problems, and administrator audit access before reading records. The Framework itself does not query user data or enforce HTTP roles. Participant responses omit provider credentials, endpoint configuration, HTTP headers, raw provider errors, private evaluator configuration, and internal exception details. Role-specific projections must be distinguished from the complete persisted envelope when discussing checksums.

Recognized secret keys/token patterns and configured provider credentials are scrubbed before new text/trace persistence. This remains best-effort filtering, not arbitrary-secret/PII detection. Never paste secrets. Internal runtime diagnostics contain controlled error codes and operation IDs separately from participant traces.

Cancellation, timeouts, and worker crashes can leave provider usage or remote side effects uncertain. The persistent queue records safe terminal/recovery outcomes and does not silently replay an uncertain remote call. There is no guarantee of exactly-once provider execution or billing, and observable traces do not guarantee deterministic replay of a real model.
