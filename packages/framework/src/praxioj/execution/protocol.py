"""Versioned, bounded Judge messages. Validation is not execution isolation."""
from datetime import UTC, datetime
from hashlib import sha256
import json
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

PROTOCOL_VERSION = "1.0"
MAX_PROTOCOL_BYTES = 65_536
MOCK_FIXTURE_ID = "praxioj.mock-judge/1"
MOCK_SUBMISSION_CONTENT = "Goal: ship a focused release.\nVerification: run regression tests and review results.\nRisk: regressions; mitigate with a rollback plan.\n"
FIXTURE_SUBMISSION_CONTENT = MOCK_SUBMISSION_CONTENT
MOCK_ARTIFACT_CONTENT = "Synthetic Mock Judge output; no submitted code was executed.\n"
MOCK_EVALUATOR_ID = "mock.synthetic-rubric"
MOCK_IMAGE_ID = "praxioj.mock-judge"
MOCK_IMAGE_DIGEST = sha256(b"praxioj.mock-judge/1").hexdigest()
Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
Version = Annotated[str, Field(strict=True, pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")]
_PATH = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*$")
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class ExecutionValidationError(ValueError):
    """A controlled classification; raw payloads and validation details stay private."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False,
                              revalidate_instances="always")


def validate_artifact_path(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or not _PATH.fullmatch(value):
        raise ValueError("Invalid artifact relative path")
    for part in value.split("/"):
        if part in {".", ".."} or part.endswith(".") or part.split(".")[0].casefold() in _RESERVED:
            raise ValueError("Invalid artifact relative path")
    return value


def _unique_paths(items):
    ids, paths = set(), set()
    for item in items:
        path = item.relative_path.casefold()
        if item.id in ids or path in paths or any(path.startswith(old + "/") or old.startswith(path + "/") for old in paths):
            raise ValueError("Duplicate or conflicting artifact identity/path")
        ids.add(item.id)
        paths.add(path)


class ExecutionResourceLimits(ProtocolModel):
    cpu_seconds: StrictInt = Field(default=30, ge=1, le=3600)
    wall_seconds: StrictInt = Field(default=60, ge=1, le=3600)
    memory_mb: StrictInt = Field(default=256, ge=16, le=16384)
    disk_mb: StrictInt = Field(default=64, ge=1, le=4096)
    pids: StrictInt = Field(default=64, ge=1, le=1024)
    network_policy: Literal["deny"] = "deny"


class ExecutionOutputLimits(ProtocolModel):
    max_result_bytes: StrictInt = Field(default=65_536, ge=1024, le=MAX_PROTOCOL_BYTES)
    max_stdout_bytes: StrictInt = Field(default=4096, ge=0, le=16_384)
    max_stderr_bytes: StrictInt = Field(default=4096, ge=0, le=16_384)
    max_artifacts: StrictInt = Field(default=10, ge=0, le=100)
    max_artifact_bytes: StrictInt = Field(default=16_384, ge=1, le=32_768)
    max_total_artifact_bytes: StrictInt = Field(default=32_768, ge=1, le=65_536)

    @model_validator(mode="after")
    def consistent_sizes(self):
        if self.max_artifact_bytes > self.max_total_artifact_bytes:
            raise ValueError("Per-artifact limit exceeds total artifact limit")
        return self


class ArtifactDeclaration(ProtocolModel):
    id: Identifier
    relative_path: str
    media_type: Literal["text/plain"] = "text/plain"
    role: Literal["output", "evidence", "log"] = "output"

    @field_validator("relative_path")
    @classmethod
    def safe_path(cls, value):
        return validate_artifact_path(value)


class ExecutionPolicy(ProtocolModel):
    policy_id: Literal["praxioj.synthetic-policy/1"] = "praxioj.synthetic-policy/1"
    resource_limits: ExecutionResourceLimits = Field(default_factory=ExecutionResourceLimits)
    output_limits: ExecutionOutputLimits = Field(default_factory=ExecutionOutputLimits)
    allowed_operations: tuple[Literal["submit_result"], ...] = ("submit_result",)
    declared_artifacts: tuple[ArtifactDeclaration, ...] = (ArtifactDeclaration(id="mock-result", relative_path="result.txt"),)

    @property
    def max_result_bytes(self):
        return self.output_limits.max_result_bytes

    @model_validator(mode="after")
    def declarations(self):
        if self.allowed_operations != ("submit_result",):
            raise ValueError("Unsupported operation policy")
        if len(self.declared_artifacts) > self.output_limits.max_artifacts:
            raise ValueError("Artifact declarations exceed file count limit")
        _unique_paths(self.declared_artifacts)
        return self


class RuntimeImageIdentity(ProtocolModel):
    id: Identifier
    digest: Digest


MOCK_RUNTIME_IMAGE = RuntimeImageIdentity(id=MOCK_IMAGE_ID, digest=MOCK_IMAGE_DIGEST)


class SubmittedArtifactMetadata(ProtocolModel):
    id: Identifier
    name: str = Field(min_length=1, max_length=128)
    media_type: str = Field(min_length=1, max_length=100)
    size_bytes: StrictInt = Field(ge=0, le=1_048_576)
    sha256: Digest


class TraceCheckpoint(ProtocolModel):
    session_id: UUID
    head_sha256: Digest | None
    next_sequence_number: StrictInt = Field(ge=1, le=100_000_000)
    availability: Literal["available"] = "available"

    @model_validator(mode="after")
    def empty_checkpoint(self):
        if self.head_sha256 is None and self.next_sequence_number != 1:
            raise ValueError("Missing nonempty trace checkpoint")
        return self


class ExecutionInputSnapshot(ProtocolModel):
    fixture_id: Literal[MOCK_FIXTURE_ID] = MOCK_FIXTURE_ID
    submission_id: UUID
    submission_content: Literal[MOCK_SUBMISSION_CONTENT] = MOCK_SUBMISSION_CONTENT
    submission_sha256: Digest
    artifacts: tuple[SubmittedArtifactMetadata, ...] = Field(default=(), max_length=100)
    trace_checkpoint: TraceCheckpoint

    @model_validator(mode="after")
    def fixed_fixture(self):
        if self.submission_sha256 != sha256(self.submission_content.encode()).hexdigest():
            raise ValueError("Submission snapshot digest mismatch")
        if len({item.id for item in self.artifacts}) != len(self.artifacts):
            raise ValueError("Duplicate submitted artifact ID")
        return self


class ExecutionCriterionDefinition(ProtocolModel):
    id: Identifier
    title: str = Field(default="Synthetic criterion", min_length=1, max_length=200)
    max_score: float = Field(gt=0, le=1_000_000)


class ExecutionRequest(ProtocolModel):
    protocol_version: Literal[PROTOCOL_VERSION]
    request_id: UUID
    job_id: UUID
    attempt_id: UUID
    session_id: UUID
    fence: StrictInt = Field(ge=1, le=2_147_483_647)
    execution_type: Literal["synthetic_evaluation", "participant_code", "external_evaluator"] = "synthetic_evaluation"
    problem_id: Identifier
    problem_version: Version
    evaluator_id: Identifier
    evaluator_version: Version
    input_snapshot: ExecutionInputSnapshot
    input_digest: Digest
    policy: ExecutionPolicy
    policy_digest: Digest
    runtime_image: RuntimeImageIdentity
    deadline: datetime
    criteria: tuple[ExecutionCriterionDefinition, ...] = Field(min_length=1, max_length=100)

    @field_validator("deadline")
    @classmethod
    def aware_deadline(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Deadline requires timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def consistent_snapshot(self):
        if self.session_id != self.input_snapshot.trace_checkpoint.session_id:
            raise ValueError("Snapshot session mismatch")
        if self.input_digest != snapshot_digest(self.input_snapshot) or self.policy_digest != policy_digest(self.policy):
            raise ValueError("Execution request digest mismatch")
        if len({item.id for item in self.criteria}) != len(self.criteria):
            raise ValueError("Duplicate criterion ID")
        return self


class ExecutionArtifactMetadata(ArtifactDeclaration):
    schema_version: Literal[PROTOCOL_VERSION]
    size_bytes: StrictInt = Field(ge=0, le=32_768)
    sha256: Digest
    attempt_id: UUID


class ExecutionArtifact(ProtocolModel):
    metadata: ExecutionArtifactMetadata
    content: str = Field(max_length=32_768)

    @model_validator(mode="after")
    def verified_bytes(self):
        try:
            data = self.content.encode("utf-8", errors="strict")
        except UnicodeError:
            raise ValueError("Invalid artifact encoding") from None
        if len(data) != self.metadata.size_bytes or sha256(data).hexdigest() != self.metadata.sha256:
            raise ValueError("Artifact content metadata mismatch")
        return self


class ExecutionCriterionResult(ProtocolModel):
    id: Identifier
    score: float = Field(ge=0, le=1_000_000)
    maximum_score: float = Field(gt=0, le=1_000_000)
    passed: bool
    feedback: str = Field(max_length=1000)

    @model_validator(mode="after")
    def bounded_score(self):
        if self.score > self.maximum_score:
            raise ValueError("Criterion score exceeds maximum")
        if self.passed != (self.score == self.maximum_score):
            raise ValueError("Criterion pass state does not match its score")
        return self


class ExecutionEvaluation(ProtocolModel):
    status: Literal["completed"] = "completed"
    score: float = Field(ge=0, le=100_000_000)
    maximum_score: float = Field(gt=0, le=100_000_000)
    criteria: tuple[ExecutionCriterionResult, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def total_score(self):
        if len({item.id for item in self.criteria}) != len(self.criteria):
            raise ValueError("Duplicate result criterion ID")
        if self.score != sum(item.score for item in self.criteria) or self.maximum_score != sum(item.maximum_score for item in self.criteria):
            raise ValueError("Evaluation aggregate mismatch")
        return self


class ExecutionResourceUsage(ProtocolModel):
    cpu_seconds: float | None = Field(default=None, ge=0, le=3600)
    wall_seconds: float | None = Field(default=None, ge=0, le=3600)
    peak_memory_bytes: StrictInt | None = Field(default=None, ge=0, le=17_179_869_184)


class CleanupResult(ProtocolModel):
    status: Literal["not_required", "completed", "failed", "unknown"]
    reason: Literal["synthetic_no_resources", "runtime_reported", "not_verified"]


class ExecutionResult(ProtocolModel):
    schema_version: Literal[PROTOCOL_VERSION]
    request_id: UUID
    job_id: UUID
    attempt_id: UUID
    fence: StrictInt = Field(ge=1, le=2_147_483_647)
    request_digest: Digest
    input_digest: Digest
    policy_digest: Digest
    runtime_image_digest: Digest
    status: Literal["completed", "failed", "cancelled", "timed_out", "unavailable"]
    exit_reason: Literal["synthetic_completed", "synthetic_failed", "synthetic_cancelled", "synthetic_timeout", "backend_unavailable"]
    artifacts: tuple[ExecutionArtifact, ...] = Field(default=(), max_length=100)
    stdout: str = Field(default="", max_length=16_384)
    stderr: str = Field(default="", max_length=16_384)
    resource_usage: ExecutionResourceUsage = Field(default_factory=ExecutionResourceUsage)
    evaluation: ExecutionEvaluation | None = None
    cleanup: CleanupResult
    error_category: Literal["execution_failed", "cancelled", "timeout", "unavailable"] | None = None
    provenance: Literal["synthetic_mock"] = "synthetic_mock"
    output_digest: Digest

    @model_validator(mode="after")
    def result_state(self):
        reasons = {"completed": ("synthetic_completed", None), "failed": ("synthetic_failed", "execution_failed"),
                   "cancelled": ("synthetic_cancelled", "cancelled"), "timed_out": ("synthetic_timeout", "timeout"),
                   "unavailable": ("backend_unavailable", "unavailable")}
        if (self.exit_reason, self.error_category) != reasons[self.status]:
            raise ValueError("Execution state/reason mismatch")
        if (self.status == "completed") != (self.evaluation is not None):
            raise ValueError("Only completed execution has an evaluation")
        if self.status != "completed" and self.artifacts:
            raise ValueError("Failed execution cannot supply accepted artifacts")
        _unique_paths([item.metadata for item in self.artifacts])
        return self


class BackendCapabilities(ProtocolModel):
    backend_id: str = Field(min_length=1, max_length=128)
    execution_types: tuple[Literal["synthetic_evaluation"], ...] = ()
    audiences: tuple[Literal["mock-judge"], ...] = ()
    allowed_operations: tuple[Literal["submit_result"], ...] = ()
    synthetic_only: Literal[True] = True
    untrusted_code_execution: Literal[False] = False
    host_isolation_verified: Literal[False] = False


class RuntimeAvailability(ProtocolModel):
    status: Literal["available", "unavailable"]
    reason: Literal["synthetic_mock_only", "backend_not_configured", "unsupported_execution_type", "unsupported_runtime", "unsupported_policy"]
    backend_id: str = Field(min_length=1, max_length=128)


class PolicyValidation(ProtocolModel):
    allowed: bool
    reason: Literal["synthetic_mock_only", "unsupported_policy", "unsupported_execution_type", "unsupported_runtime"]


def _bounded_primitives(value, depth=0, budget=None):
    if budget is None:
        budget = [10_000, 0]
    budget[0] -= 1
    if budget[0] < 0 or depth > 16:
        raise ExecutionValidationError("protocol_structure_limit")
    if isinstance(value, ProtocolModel):
        value = value.model_dump(mode="json", warnings=False)
    if value is None or type(value) in {bool, int, float, str}:
        if isinstance(value, str):
            try:
                budget[1] += len(value.encode("utf-8", errors="strict"))
            except UnicodeError:
                raise ExecutionValidationError("protocol_encoding") from None
        if budget[1] > MAX_PROTOCOL_BYTES:
            raise ExecutionValidationError("protocol_size_limit")
        return value
    if type(value) is dict:
        if len(value) > budget[0]:
            raise ExecutionValidationError("protocol_structure_limit")
        if any(type(key) is not str for key in value):
            raise ExecutionValidationError("protocol_schema")
        return {_bounded_primitives(key, depth + 1, budget): _bounded_primitives(item, depth + 1, budget) for key, item in value.items()}
    if type(value) in {list, tuple}:
        if len(value) > budget[0]:
            raise ExecutionValidationError("protocol_structure_limit")
        return [_bounded_primitives(item, depth + 1, budget) for item in value]
    raise ExecutionValidationError("protocol_schema")


def canonical_json(value) -> bytes:
    try:
        encoded = json.dumps(_bounded_primitives(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except ExecutionValidationError:
        raise
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise ExecutionValidationError("protocol_schema") from None
    if len(encoded) > MAX_PROTOCOL_BYTES:
        raise ExecutionValidationError("protocol_size_limit")
    return encoded


def canonical_digest(value) -> str:
    return sha256(canonical_json(value)).hexdigest()


def snapshot_digest(snapshot) -> str:
    return canonical_digest(snapshot)


def policy_digest(policy) -> str:
    return canonical_digest(policy)


def request_digest(request) -> str:
    return canonical_digest(request)


def result_output_digest(result) -> str:
    data = result.model_dump(mode="json", warnings=False) if isinstance(result, ProtocolModel) else dict(result)
    for name in ("schema_version", "request_id", "job_id", "attempt_id", "fence", "request_digest", "input_digest", "policy_digest", "runtime_image_digest", "output_digest"):
        data.pop(name, None)
    return canonical_digest(data)


def _unique_json(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ExecutionValidationError("protocol_duplicate_key")
        data[key] = value
    return data


def _parse(model, raw):
    try:
        if isinstance(raw, (str, bytes)):
            encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
            if len(encoded) > MAX_PROTOCOL_BYTES:
                raise ExecutionValidationError("protocol_size_limit")
            data = json.loads(encoded.decode("utf-8", errors="strict"), object_pairs_hook=_unique_json,
                              parse_constant=lambda _: (_ for _ in ()).throw(ExecutionValidationError("protocol_schema")))
        else:
            data = raw
        return model.model_validate_json(canonical_json(data))
    except ExecutionValidationError:
        raise
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ExecutionValidationError("protocol_schema") from None


def parse_execution_request(raw) -> ExecutionRequest:
    return _parse(ExecutionRequest, raw)


def validate_execution_result(request: ExecutionRequest, raw) -> ExecutionResult:
    return _validated_execution_pair(request, raw)[1]


def _validated_execution_pair(request: ExecutionRequest, raw) -> tuple[ExecutionRequest, ExecutionResult]:
    request = parse_execution_request(request)
    result = _parse(ExecutionResult, raw)
    if len(canonical_json(result)) > request.policy.max_result_bytes:
        raise ExecutionValidationError("result_size_limit")
    pairs = ((result.request_id, request.request_id), (result.job_id, request.job_id), (result.attempt_id, request.attempt_id),
             (result.fence, request.fence), (result.request_digest, request_digest(request)),
             (result.input_digest, request.input_digest), (result.policy_digest, request.policy_digest),
             (result.runtime_image_digest, request.runtime_image.digest))
    if any(left != right for left, right in pairs):
        raise ExecutionValidationError("result_binding_mismatch")
    from .backends import mock_policy_validation
    if not mock_policy_validation(request).allowed and result.status != "unavailable":
        raise ExecutionValidationError("unsupported_execution_policy")
    if result.output_digest != result_output_digest(result):
        raise ExecutionValidationError("output_digest_mismatch")
    limits = request.policy.output_limits
    if len(result.stdout.encode("utf-8")) > limits.max_stdout_bytes or len(result.stderr.encode("utf-8")) > limits.max_stderr_bytes:
        raise ExecutionValidationError("output_size_limit")
    if len(result.artifacts) > limits.max_artifacts or sum(item.metadata.size_bytes for item in result.artifacts) > limits.max_total_artifact_bytes:
        raise ExecutionValidationError("artifact_size_limit")
    declared = {item.id: item for item in request.policy.declared_artifacts}
    for item in result.artifacts:
        meta = item.metadata
        expected = declared.get(meta.id)
        if (expected is None or meta.attempt_id != request.attempt_id or meta.size_bytes > limits.max_artifact_bytes
                or (meta.relative_path, meta.media_type, meta.role) != (expected.relative_path, expected.media_type, expected.role)):
            raise ExecutionValidationError("artifact_binding_mismatch")
    if result.evaluation is not None:
        definitions = {item.id: item.max_score for item in request.criteria}
        observed = {item.id: item.maximum_score for item in result.evaluation.criteria}
        if definitions != observed:
            raise ExecutionValidationError("criterion_binding_mismatch")
    if result.cleanup != CleanupResult(status="not_required", reason="synthetic_no_resources") or result.resource_usage != ExecutionResourceUsage():
        raise ExecutionValidationError("synthetic_evidence_mismatch")
    return request, result


def default_mock_policy() -> ExecutionPolicy:
    return ExecutionPolicy()


def build_mock_request(*, request_id, job_id, attempt_id, session_id, fence, submission_id,
                       trace_head_sha256, trace_next_sequence_number, deadline, criteria,
                       policy=None, submitted_artifacts=()) -> ExecutionRequest:
    checkpoint = TraceCheckpoint(session_id=UUID(str(session_id)), head_sha256=trace_head_sha256,
                                 next_sequence_number=trace_next_sequence_number)
    snapshot = ExecutionInputSnapshot(submission_id=UUID(str(submission_id)),
        submission_sha256=sha256(MOCK_SUBMISSION_CONTENT.encode()).hexdigest(), trace_checkpoint=checkpoint,
        artifacts=tuple(item if isinstance(item, SubmittedArtifactMetadata) else SubmittedArtifactMetadata(**item) for item in submitted_artifacts))
    policy = policy or default_mock_policy()
    definitions = tuple(item if isinstance(item, ExecutionCriterionDefinition) else ExecutionCriterionDefinition(**item) for item in criteria)
    return ExecutionRequest(protocol_version=PROTOCOL_VERSION, request_id=UUID(str(request_id)), job_id=UUID(str(job_id)), attempt_id=UUID(str(attempt_id)),
        session_id=UUID(str(session_id)), fence=fence, problem_id="release-plan", problem_version="1.0.0",
        evaluator_id=MOCK_EVALUATOR_ID, evaluator_version="1.0.0", input_snapshot=snapshot,
        input_digest=snapshot_digest(snapshot), policy=policy, policy_digest=policy_digest(policy),
        runtime_image=MOCK_RUNTIME_IMAGE, deadline=deadline, criteria=definitions)
