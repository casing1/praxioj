# Evaluation contract

The Framework defines evaluation data and trusted evaluator interfaces independently of HTTP, authentication, storage, and worker processes. The Platform authorizes a session and constructs `EvaluationInput`; the same contract is usable by standalone Python callers. A manifest can select a registered evaluator and declarative criteria. It cannot import Python, execute an expression, read host files, or run contestant code.

## Input and output

`EvaluationInput` combines:

- A validated, immutable-version `ProblemManifest` and hash-checked `SubmissionData`.
- Up to 100 immutable artifact snapshots, including their identifiers, names, content, and content hashes.
- Up to 10,000 ordered, authorized trace envelopes and `trace_availability` (`available`, `expired`, or `unavailable`).
- A `ResourceUsageSnapshot` containing nullable user-message, model-call, tool-call, input-token, and output-token counts, plus `usage_complete` and `estimated` flags.
- Optional structured `ToolExecutionEvidence` and evaluator configuration.

Missing measurements remain `None`. Known call counts can be evaluated even when provider token usage is unknown. Token-limit criteria are unsupported when usage is incomplete or estimated; a Mock token estimate is never represented as an exact token measurement or bill. The Platform must supply trustworthy counts and mark partial sums incomplete.

`EvaluationResult` reports status (`completed`, `failed`, or `unsupported`), nullable aggregate score, maximum score, criterion results, feedback, evidence references, evaluator ID/version, and optional trace-integrity results. Each criterion reports its ID/title, score, maximum score, pass state, evaluation status, evaluator version, feedback, and evidence. Evidence references identify `submission`, `artifact`, `trace`, or a named `usage` measurement. They do not expose private rubric configuration.

An unsupported criterion has `score=None` and `passed=None`. Independently evaluable criteria keep their results, but the combined result has `status=unsupported` and no aggregate score. Unknown evidence is not silently awarded zero or full credit. A deterministic criterion that was evaluated and not satisfied has zero points and `status=completed`.

## Existing final-text evaluator

`builtin.text-rubric` version `1.0.0` retains its M1/M2 scoring behavior. Every criterion privately configures `required_terms`; case-insensitive substring matching of all terms earns its maximum score, otherwise zero. This evaluator remains independent of trace availability and token measurements. The original `release-plan` manifest identity and scores are unchanged.

## Evidence rubric

`builtin.evidence-rubric` version `1.0.0` supports these strictly validated criterion configurations:

| `config.kind` | Fields | Observation |
| --- | --- | --- |
| `final_text` | `required_terms` (1–100 bounded strings) | All configured terms appear in the final submission. |
| `artifact` | `name`, optional `sha256` | A submitted artifact snapshot has the exact name and, if configured, content hash. Names are artifact labels, not host paths. |
| `event` | `event_type`, optional `actor`, `min_count` | The configured number of server events occurred before this submission. For `AUTHOR_EVENT`, optional `event_name` matches `payload.name`. |
| `tool_success` | `name`, `min_count` | A tool request, an allowed authorization, and a completed result have matching parent IDs, session/run/call IDs, and order. |
| `usage_limit` | `metric`, `maximum` | A known measurement is at or below the configured bound. Metrics are `user_messages`, `model_calls`, `tool_calls`, `input_tokens`, `output_tokens`, or `total_tokens`. |
| `constraints` | `rule` | `no_denied_tools`, `no_runtime_errors`, or `allowed_tools_only` holds over the inspected pre-submission trace. |

Scores are full points or zero for supported checks. Arbitrary predicates, regular expressions, dynamic imports, external evaluator code, and network calls are not part of this evaluator.

Trace-dependent criteria require an internally valid v1.1 hash chain, server-origin events, and exactly one `SUBMISSION_CREATED` event referring to the supplied immutable submission. Only earlier events are evaluated. A later validation event cannot earn pre-submission credit. Legacy, mixed-source, expired, or invalid evidence produces unsupported process criteria. The Platform additionally verifies its persisted head and sequence checkpoint to detect a missing suffix; checksums alone cannot authenticate a privileged writer.

A bare tool request or assistant claim of success is insufficient. Tool evidence must link `TOOL_CALL_REQUESTED` → `TOOL_CALL_AUTHORIZED` → `TOOL_CALL_COMPLETED`, with `allowed=true` and `status=completed`. Denied, failed, orphaned, ambiguous duplicate, or cross-run records do not count as successful execution. Supplied `ToolExecutionEvidence` cannot override the trace: mismatched projections make process evidence unsupported. The built-in logical-file aliases map `read_file` and `write_file` to their `workspace.*` policy IDs.

`AUTHOR_EVENT` is an extension point for a trusted recorder, for example a future trusted verification tool emitting `payload.name="validation.completed"`. No participant event-ingestion endpoint or arbitrary test runner is added. Text saying that tests passed is not such an event. Absence-based constraints cite the inspected events and submission boundary; they do not invent a successful action.

The `examples/problems/evidence-plan` package demonstrates final text, saved artifact, successful authorized write, artifact history, model-call count, and allowed-tool checks. With the Mock, asking to “save a release plan” and submitting the saved text can earn 100/100. This demonstrates infrastructure and explicit rules, not human understanding or the quality of AI collaboration.

## Responsibility and limitations

The Framework does not define a universal measure of AI competence. Authors choose observable criteria and published descriptions. Event presence does not establish understanding, judgment, causality, or the quality of the result. Authors and operators can inspect referenced evidence through authorized Platform interfaces while it remains retained.

The Platform snapshots files and trace context in the submission transaction and records evaluator identity/version with the result. Trace retention can remove referenced events later; retained scores must then disclose that supporting trace data is expired. Account-data deletion may remove the evaluation itself according to the Platform policy. Hashes and references are not permission to retain participant text indefinitely.

Trusted built-ins run in process. The persistent AI worker is not an isolated Judge Worker and does not authorize untrusted evaluator plugins. External evaluator execution still fails as unavailable. Regrading, arbitrary-code evaluation, and externally authenticated evidence archives require separate design and validation.
