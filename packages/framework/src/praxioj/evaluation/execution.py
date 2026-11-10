"""Explicit synthetic assessment bridge; it cannot certify independent execution."""
from typing import Literal
from uuid import uuid5

from pydantic import Field

from praxioj.execution.protocol import (ExecutionArtifactMetadata, ExecutionRequest, ProtocolModel,
    ExecutionResult, _validated_execution_pair, request_digest)
from . import CriterionResult, EvaluationResult


class SyntheticExecutionAssessment(ProtocolModel):
    evaluation: EvaluationResult
    provenance: Literal["synthetic_mock"] = "synthetic_mock"
    independent_execution_evidence: Literal[False] = False
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[ExecutionArtifactMetadata, ...] = ()


def assess_synthetic_execution(request: ExecutionRequest, raw_result) -> SyntheticExecutionAssessment:
    return validate_and_assess_synthetic_execution(request, raw_result)[1]


def validate_and_assess_synthetic_execution(request: ExecutionRequest, raw_result) -> tuple[ExecutionResult, SyntheticExecutionAssessment]:
    # Parse and validate once, then map only that freshly validated request/result.
    # There is deliberately no public "already trusted" flag or unchecked mapper.
    request, result = _validated_execution_pair(request, raw_result)
    titles = {item.id: item.title for item in request.criteria}
    evaluation = result.evaluation
    mapped = EvaluationResult(id=uuid5(request.request_id, "synthetic-assessment"),
        status="completed" if evaluation else "unsupported", score=evaluation.score if evaluation else None,
        maximum_score=evaluation.maximum_score if evaluation else None,
        criteria=[CriterionResult(id=item.id, title=titles[item.id], score=item.score, maximum_score=item.maximum_score,
            passed=item.passed, feedback=item.feedback, evaluator_version=request.evaluator_version) for item in evaluation.criteria] if evaluation else [],
        feedback=["Synthetic Mock Judge fixture. No participant or evaluator code executed; not independent execution evidence."],
        evaluator_id=request.evaluator_id, evaluator_version=request.evaluator_version)
    assessment = SyntheticExecutionAssessment(evaluation=mapped, request_digest=request_digest(request),
        output_digest=result.output_digest, artifacts=tuple(item.metadata for item in result.artifacts))
    return result, assessment
