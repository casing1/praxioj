# Execution protocol, capability and result validation

Protocol **1.0** is a Framework-only contract for Judge request/result exchange. It has no FastAPI, SQLAlchemy or runtime-specific dependency. M5 supplies a deterministic in-memory Mock and an unavailable backend; no participant code or external evaluator executes. Platform orchestration and test-only HTTP access are described in [Execution Broker](../architecture/execution-broker.md).

## Strict parsing and canonical identity

`ProtocolModel` forbids unknown fields, rejects implicit scalar coercion and nonfinite numbers, freezes models and revalidates model instances. Nested collections use tuples and typed models. `parse_execution_request()` and `validate_execution_result()` reconstruct the message through bounded primitive data and a fresh schema parse, including when given an existing model or `model_copy()` result. A mutated or unvalidated typed object is not proof of validation.

The protocol envelope is at most **65,536 encoded UTF-8 bytes**, with at most 10,000 visited values, keys and containers and nesting depth 16. Raw JSON duplicate keys, invalid Unicode and NaN/Infinity literals are rejected. Integer resources use strict bounded integers; a JSON boolean is not an integer allowance. Structural and byte limits apply before a result is stored. An encoded result also must fit the pinned policy's possibly smaller result limit.

`canonical_json()` serializes supported primitive values with sorted keys, compact separators, UTF-8 and finite JSON numbers. SHA-256 digests use that canonical representation. `snapshot_digest()`, `policy_digest()` and `request_digest()` bind their complete respective objects. `result_output_digest()` binds status/reason, artifacts and inline bytes, stdout/stderr, usage, evaluation, cleanup, error and provenance; it excludes correlation fields and the digest itself. Correlation is independently compared with the request. Checksums detect disagreement; they are not signatures, proof of truthful execution or protection from a privileged writer replacing both data and hashes.

## Execution request

| Field | Contract |
| --- | --- |
| `protocol_version` | Required literal `"1.0"`; omission and other versions fail explicitly |
| `request_id`, `job_id`, `attempt_id`, `session_id` | UUIDs fixed by the broker for the current attempt |
| `fence` | Positive bounded generation counter |
| `execution_type` | Names `synthetic_evaluation`, `participant_code`, `external_evaluator`; only the first is supported by Mock |
| `problem_id`, `problem_version` | Pinned problem identity and semantic version |
| `evaluator_id`, `evaluator_version` | Explicit evaluator identity/version; Mock uses `mock.synthetic-rubric/1.0.0` |
| `input_snapshot`, `input_digest` | Fixed synthetic submission identity/content/hash, submitted-artifact metadata and authorized Trace checkpoint; digest must match |
| `policy`, `policy_digest` | Pinned resource/output limits, operation and declared artifacts; digest must match |
| `runtime_image` | Explicit ID/digest; Mock uses a synthetic identity, not a pulled OCI image |
| `deadline` | Timezone-aware UTC-normalized absolute deadline |
| `criteria` | 1–100 unique criterion IDs, titles and positive bounded maximum scores |

`ExecutionInputSnapshot` contains `fixture_id="praxioj.mock-judge/1"`, a submission UUID, the exact `MOCK_SUBMISSION_CONTENT` literal and its recomputed digest, at most 100 `SubmittedArtifactMetadata` entries, and a `TraceCheckpoint`. The checkpoint binds the session UUID, stored head hash, next sequence and `availability="available"`. A null head is allowed only for an empty checkpoint with next sequence 1. It is not the full Trace payload. The Platform verifies authorized stored evidence before pinning that checkpoint and rejects later drift/expiry.

Submitted-artifact metadata records ID, name, media type, encoded size and SHA-256. It represents bytes checked by the trusted Platform before metadata projection; no host path or submitted-artifact contents are passed to Mock. Output artifacts have the stronger relative-path/declaration rules below.

`ExecutionPolicy` currently accepts only `praxioj.synthetic-policy/1` and exactly the operation `submit_result`. Its default output declaration is `id="mock-result"`, `relative_path="result.txt"`, `media_type="text/plain"`, `role="output"`. Unknown policy/runtime/type does not select a fallback executor. The selected backend's `validate_policy()` and `availability()` must explicitly permit the request even when its abstract schema is valid.

| Resource field | Default / validation bound |
| --- | --- |
| `cpu_seconds`, `wall_seconds` | 30 / 60; each 1–3,600 |
| `memory_mb` | 256; 16–16,384 |
| `disk_mb` | 64; 1–4,096 |
| `pids` | 64; 1–1,024 |
| `network_policy` | Literal `deny` |
| `max_result_bytes` | 65,536; 1,024–65,536 |
| `max_stdout_bytes`, `max_stderr_bytes` | 4,096 each; 0–16,384 |
| `max_artifacts` | 10; 0–100 |
| `max_artifact_bytes`, `max_total_artifact_bytes` | Defaults 16,384 / 32,768; bounds 1–32,768 / 1–65,536; per-file cap cannot exceed the total |

These are declared budgets validated by the protocol. M5 does not enforce CPU, RAM, PIDs or disk against hostile processes because no such process exists.

## Execution result and assessment

`ExecutionResult` carries required `schema_version="1.0"`, request/job/attempt/fence correlation, request/input/policy/runtime-image digests, status/exit reason, artifacts, stdout/stderr, nullable resource usage, optional evaluation, cleanup/error category, provenance and output digest.

| Status | Required exit reason | Error category | Evaluation/artifacts |
| --- | --- | --- | --- |
| `completed` | `synthetic_completed` | null | Evaluation required; validated declared artifacts allowed |
| `failed` | `synthetic_failed` | `execution_failed` | No evaluation or accepted artifacts |
| `cancelled` | `synthetic_cancelled` | `cancelled` | No evaluation or accepted artifacts |
| `timed_out` | `synthetic_timeout` | `timeout` | No evaluation or accepted artifacts |
| `unavailable` | `backend_unavailable` | `unavailable` | No evaluation or accepted artifacts |

A completed evaluation reports finite criterion scores, maxima and pass flags, plus exact aggregate sums. Result criterion IDs and maximum scores must exactly match the pinned request; duplicate, missing or unknown criteria fail. Scores cannot exceed their corresponding maximum. A completed execution whose evaluated criteria failed remains a valid completed execution with low/zero points. It does not become a runtime failure.

M5 accepts only `provenance="synthetic_mock"`, null CPU/wall/peak-memory observations and `cleanup={"status":"not_required","reason":"synthetic_no_resources"}`. These values avoid inventing resource measurements or teardown evidence. The schemas name future cleanup states, but the current synthetic validator rejects a claim that a real runtime completed cleanup.

`assess_synthetic_execution()` returns a `SyntheticExecutionAssessment` containing the existing `EvaluationResult` shape, request/output digests, validated artifact metadata, synthetic provenance and `independent_execution_evidence=false`. It preserves the synthetic evaluator identity and a deterministic assessment UUID derived from the execution request. `validate_and_assess_synthetic_execution()` returns both the fresh validated result and assessment from one validation pass; it has no unchecked/already-trusted flag. This wrapper cannot be used as an attestation that independent submitted code ran, and Platform storage keeps it separate from the original built-in evaluation.

## Artifact and output validation

`ExecutionArtifactMetadata` extends a declared artifact with required `schema_version="1.0"`, `size_bytes`, SHA-256 and associated `attempt_id`. `ExecutionArtifact` carries the metadata plus bounded inline text. The validator encodes the actual text as strict UTF-8 and recomputes byte size/hash; metadata alone cannot assert those bytes.

Output paths are 1–128 ASCII characters composed of portable relative segments. Absolute paths, empty/dot/dot-dot segments, backslashes, drive/URI syntax, percent-encoded alternatives, control characters, non-ASCII encodings, trailing dots and reserved device names are rejected. IDs are unique. Paths are compared case-insensitively and parent/file collisions such as `a` with `a/b` are rejected, including declared paths.

Every result artifact must match a request declaration's ID/path/media type/role and current attempt. The validator checks per-file/total encoded size, file count, stdout/stderr byte limits and complete result size. Undeclared artifacts, duplicate IDs, conflicting paths or wrong content hashes fail. Output data is never interpreted as shell, Python, trusted Trace events, SQL or an evaluator registration.

M5 collects only trusted synthetic inline fixture text. It does not open OS filesystem objects. Symlink/hardlink/device/FIFO/socket validation, descriptor-relative collection, archive expansion, mount isolation and race-free OS path resolution are future A9 collector requirements. Metadata validation is not filesystem isolation.

## Capability authorization

Capability enforcement belongs to the Platform `JudgeBroker`; the Framework request contains no login secret, database URL, provider key or capability token.

A claimed attempt receives an opaque token from `secrets.token_urlsafe(32)`. Only its hash is persisted. Its authority is bound to job/attempt/request IDs, worker identity, current fence, audience `mock-judge`, operation `submit_result`, absolute expiry, current lease, the complete request digest and its input/policy/image bindings. The broker retains plaintext only in a representation-hidden `JudgeLease`. Neither HTTP job projections, Mock arguments, audit nor participant Trace expose it.

Before heartbeat or completion, the broker locks current rows and checks account activity/role, owned source association, current attempt/fence/job state, hash comparison, audience/operation, unconsumed/unrevoked authority, lease/expiry/deadline and current source snapshot. Capability possession does not bypass any binding. Heartbeat renews only the existing lease before expiry and remains bounded by the original deadline.

Successful validation consumes the capability and stores the result/assessment in the same transaction as terminalization and active-reservation release. A duplicate result cannot overwrite completion. Invalid result data fails the job and revokes authority without accepting a score. Wrong tokens, audiences, operations and stale/replayed attempts are rejected without terminating unrelated live work. A matching current capability that has expired or whose source/request binding changed commits a failed transition and revocation before rejection. Independent maintenance closes expired work that never delivers a result. Cancellation invalidates result acceptance before returning, and no failed attempt is automatically replayed. Existing tokens cannot authorize changed snapshots or replacement attempts.

This is a server-state capability prototype, not an implemented remote runner credential protocol. M5 has no public result-upload endpoint; its trusted synthetic dispatcher holds the lease and calls `complete()` after the backend returns.

## Backend selection and deterministic Mock use

`BackendCapabilities` explicitly declares supported execution types, audiences and operations, `synthetic_only=true`, `untrusted_code_execution=false` and `host_isolation_verified=false`. `RuntimeAvailability` reports `available/unavailable` with a controlled reason. `PolicyValidation` reports whether the selected runtime/type/policy combination is supported. The legacy workspace interface remains fail closed.

`MockJudgeBackend` accepts a trusted-constructor scenario: `success`, `evaluation_failed`, `failure`, `cancelled`, `timeout`, `malformed`, `oversized` or `bad_digest`. The same request/scenario yields the same fixture response. Error scenarios test the validator; malformed results are not accepted merely because Mock produced them. Scenario selection is not part of the HTTP job request. The backend performs no subprocess, filesystem, network or dynamic participant-module operations.

```python
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from praxioj.execution import (
    MockJudgeBackend, build_mock_request, canonical_json,
    validate_execution_result,
)
from praxioj.evaluation.execution import assess_synthetic_execution

request = build_mock_request(
    request_id=uuid4(), job_id=uuid4(), attempt_id=uuid4(), session_id=uuid4(),
    fence=1, submission_id=uuid4(), trace_head_sha256=None,
    trace_next_sequence_number=1,
    deadline=datetime.now(UTC) + timedelta(seconds=60),
    criteria=({"id": "fixture-check", "max_score": 1.0},),
)
raw = asyncio.run(MockJudgeBackend("evaluation_failed").execute(request))
result = validate_execution_result(request, raw)
assessment = assess_synthetic_execution(request, raw)
assert result.status == "completed"
assert assessment.evaluation.score == 0
assert assessment.independent_execution_evidence is False
encoded_request = canonical_json(request)
```

The empty checkpoint is only a standalone synthetic contract example. It does not bypass the Platform's authorized persisted-Trace verification. Native macOS, Windows or Docker Desktop never selects host execution when a sandbox is absent. The unavailable backend returns an explicit unavailable envelope without invoking Mock or any real runner.

See [M5 validation](../development/validation-m5.md) for actual positive, negative, race and regression results. Schema/metadata checks do not claim that future Linux/KVM, host isolation or resource-enforcement acceptance gates have passed.
