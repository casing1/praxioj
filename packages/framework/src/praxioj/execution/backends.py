"""Deterministic in-memory fixtures. No processes, files, network or imports."""
from hashlib import sha256
from typing import Literal

from .protocol import (BackendCapabilities, CleanupResult, ExecutionArtifact, ExecutionArtifactMetadata,
    ExecutionCriterionResult, ExecutionEvaluation, ExecutionRequest, ExecutionResourceUsage,
    MOCK_ARTIFACT_CONTENT, MOCK_EVALUATOR_ID, MOCK_RUNTIME_IMAGE, PolicyValidation, RuntimeAvailability,
    parse_execution_request, request_digest, result_output_digest)

MockScenario = Literal["success", "evaluation_failed", "failure", "cancelled", "timeout", "malformed", "oversized", "bad_digest"]


def mock_policy_validation(request: ExecutionRequest) -> PolicyValidation:
    if request.execution_type != "synthetic_evaluation":
        return PolicyValidation(allowed=False, reason="unsupported_execution_type")
    if request.runtime_image != MOCK_RUNTIME_IMAGE:
        return PolicyValidation(allowed=False, reason="unsupported_runtime")
    declarations = request.policy.declared_artifacts
    if (request.problem_id != "release-plan" or request.problem_version != "1.0.0"
            or request.evaluator_id != MOCK_EVALUATOR_ID or request.evaluator_version != "1.0.0"
            or len(declarations) != 1 or declarations[0].id != "mock-result"
            or declarations[0].relative_path != "result.txt" or declarations[0].role != "output"):
        return PolicyValidation(allowed=False, reason="unsupported_policy")
    return PolicyValidation(allowed=True, reason="synthetic_mock_only")


class MockJudgeBackend:
    """Trusted constructor selects fixtures; requests cannot select code or handlers."""
    capabilities = BackendCapabilities(backend_id="mock-judge", execution_types=("synthetic_evaluation",),
        audiences=("mock-judge",), allowed_operations=("submit_result",))

    def __init__(self, scenario: MockScenario = "success"):
        if scenario not in {"success", "evaluation_failed", "failure", "cancelled", "timeout", "malformed", "oversized", "bad_digest"}:
            raise ValueError("Unsupported synthetic fixture")
        self.scenario = scenario

    def validate_policy(self, request: ExecutionRequest) -> PolicyValidation:
        return mock_policy_validation(parse_execution_request(request))

    def availability(self, request: ExecutionRequest | None = None) -> RuntimeAvailability:
        validation = self.validate_policy(request) if request is not None else PolicyValidation(allowed=True, reason="synthetic_mock_only")
        return RuntimeAvailability(status="available" if validation.allowed else "unavailable",
            reason=validation.reason, backend_id="mock-judge")

    async def execute(self, request: ExecutionRequest) -> dict:
        request = parse_execution_request(request)
        # The entry point just parsed a fresh strict request; do not serialize
        # and parse it again merely to inspect the pinned backend policy.
        validation = mock_policy_validation(request)
        status = "completed"
        if not validation.allowed:
            status = "unavailable"
        elif self.scenario in {"failure", "cancelled", "timeout"}:
            status = {"failure": "failed", "cancelled": "cancelled", "timeout": "timed_out"}[self.scenario]
        reasons = {"completed": ("synthetic_completed", None), "failed": ("synthetic_failed", "execution_failed"),
                   "cancelled": ("synthetic_cancelled", "cancelled"), "timed_out": ("synthetic_timeout", "timeout"),
                   "unavailable": ("backend_unavailable", "unavailable")}
        evaluation = None
        artifacts = ()
        if status == "completed":
            criteria = tuple(ExecutionCriterionResult(id=item.id, score=0.0 if self.scenario == "evaluation_failed" else item.max_score,
                maximum_score=item.max_score, passed=self.scenario != "evaluation_failed", feedback="Synthetic fixture result; no code executed.") for item in request.criteria)
            evaluation = ExecutionEvaluation(score=sum(item.score for item in criteria),
                maximum_score=sum(item.maximum_score for item in criteria), criteria=criteria)
            metadata = ExecutionArtifactMetadata(schema_version="1.0", id="mock-result", relative_path="result.txt", size_bytes=len(MOCK_ARTIFACT_CONTENT.encode()),
                sha256=sha256(MOCK_ARTIFACT_CONTENT.encode()).hexdigest(), attempt_id=request.attempt_id)
            artifacts = (ExecutionArtifact(metadata=metadata, content=MOCK_ARTIFACT_CONTENT),)
        result = {"schema_version": "1.0", "request_id": str(request.request_id), "job_id": str(request.job_id),
            "attempt_id": str(request.attempt_id), "fence": request.fence, "request_digest": request_digest(request),
            "input_digest": request.input_digest, "policy_digest": request.policy_digest,
            "runtime_image_digest": request.runtime_image.digest, "status": status, "exit_reason": reasons[status][0],
            "artifacts": [item.model_dump(mode="json") for item in artifacts], "stdout": "Synthetic Mock Judge only.\n" if status == "completed" else "",
            "stderr": "", "resource_usage": ExecutionResourceUsage().model_dump(mode="json"),
            "evaluation": evaluation.model_dump(mode="json") if evaluation else None,
            "cleanup": CleanupResult(status="not_required", reason="synthetic_no_resources").model_dump(mode="json"),
            "error_category": reasons[status][1], "provenance": "synthetic_mock"}
        if self.scenario == "malformed" and validation.allowed:
            result["unexpected_authority"] = "not accepted"
        elif self.scenario == "oversized" and validation.allowed:
            result["stdout"] = "x" * (request.policy.output_limits.max_stdout_bytes + 1)
        elif self.scenario == "bad_digest" and artifacts and validation.allowed:
            result["artifacts"][0]["metadata"]["sha256"] = "0" * 64
        result["output_digest"] = result_output_digest(result)
        return result


def unavailable_result(request: ExecutionRequest) -> dict:
    request = parse_execution_request(request)
    data = {"schema_version": "1.0", "request_id": str(request.request_id), "job_id": str(request.job_id),
        "attempt_id": str(request.attempt_id), "fence": request.fence, "request_digest": request_digest(request),
        "input_digest": request.input_digest, "policy_digest": request.policy_digest,
        "runtime_image_digest": request.runtime_image.digest, "status": "unavailable", "exit_reason": "backend_unavailable",
        "artifacts": [], "stdout": "", "stderr": "", "resource_usage": ExecutionResourceUsage().model_dump(mode="json"),
        "evaluation": None, "cleanup": {"status": "not_required", "reason": "synthetic_no_resources"},
        "error_category": "unavailable", "provenance": "synthetic_mock"}
    data["output_digest"] = result_output_digest(data)
    return data
